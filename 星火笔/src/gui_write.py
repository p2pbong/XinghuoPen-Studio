# -*- coding: utf-8 -*-
"""码字页（AI 写作工作台，v1.66）：章节目录 + 标题/正文编辑 + AI 续写 + AI 段落工具。

对标写作软件的码字界面：
- 左侧章节目录（只读列出已归档章节标题+字数），点选载入；
- 右侧标题输入 + 大正文编辑区（实时字数统计）；
- AI 续写：以光标前文为衔接，续写指定长度插入光标处（后台线程，可停止）；
- AI 段落工具：选中文本 → 润色/扩写/缩写/去AI味（复用生成页 PolishParagraphDialog）；
- 保存：写回已归档章节（引擎 edit_chapter：自动备份旧稿进草稿箱 + git 归档）；
- 新建下一个章节（按 next_chapter 分配章号）、自动保存开关。
"""
import threading

from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QMessageBox, QPlainTextEdit,
                               QPushButton, QSpinBox, QVBoxLayout, QWidget)

import config
import llm
import main_ai
from gui_app import APP, current_project, engine_for, log_fn, set_running
from gui_theme import icon, T


def _continue_prompt(project, ahead, n, directive="", store=None):
    """构造续写提示：以光标前文为衔接，续写约 n 字。

    directive（v1.67）：用户附加要求（如「写男主发现妹妹是凶手」「节奏加快」），
    优先级最高，必须满足。
    store（v1.68）：传当前项目 store 时启用「涉及人物读取推理」。
    文风要求/主AI笔记/人物读取推理三块按 config tool_ctx_* 开关选择性注入（省 token 可关）。
    """
    import config as _cfg168
    _cfg = _cfg168.load_config()
    style = (project.story_style or "").strip() or "自然流畅的长篇小说文风"
    sys = ("你是资深网络小说作者，保持《%s》的文风与叙事节奏续写正文。"
           "要求：衔接自然、细节饱满、人物语言与情绪符合前文，禁止复述前文内容"
           "、禁止加作者旁白；只输出续写正文。" % (project.title or "本书"))
    user = "【前文】\n%s\n\n【续写要求】请紧接上文自然续写约 %d 字。" % (
        ahead[-1600:] if ahead else "（本书开篇）", n)
    if (directive or "").strip():
        user += "\n【用户指定方向（优先级最高，必须满足）】%s" % directive.strip()
    # v1.68 可配置上下文：正文AI文风要求 + 主AI笔记 + 涉及人物读取推理
    ctx_style = bool(_cfg.get("tool_ctx_style", True))
    ctx_notes = bool(_cfg.get("tool_ctx_notes", True))
    ctx_rp = bool(_cfg.get("tool_ctx_rp", True))
    blocks = prompts.writing_ctx_blocks(project, store, ctx_style=ctx_style,
                                        ctx_notes=ctx_notes, ctx_rp=ctx_rp)
    if blocks:
        user += "\n\n【任务上下文】\n" + "\n".join(blocks)
    return sys, user, style


class WriteWorker(QObject):
    """AI 续写后台线程：llm.chat_text 生成续写文本；可停止（StopRequested 优先）。"""

    done = Signal(object)   # 续写文本（str）或 {"error": ...}

    def __init__(self):
        super().__init__()
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()
        llm.abort_active_resps()

    def run(self, project, ahead, n, profile_name=None, directive="", store=None):
        import llm as _llm_mod
        import config as _cfg168
        _llm_mod.set_abort(self._stop)
        try:
            sys, user, _style = _continue_prompt(project, ahead, n, directive, store)
            # v1.68 后半程：设置页「码字AI（续写/段落工具）」指定 API 配置 → 续写用它（未指定跟随正文写作）
            if not profile_name:
                profile_name = str((_cfg168.load_config().get("role_profiles") or {})
                                   .get("write_tool") or "").strip() or None
            out = _llm_mod.chat_text(sys, user, role="write",
                                     profile=profile_name, max_tokens=min(n * 3, 1200))
            if not out:
                out = {"error": "模型返回为空，请重试。"}
        except llm.StopRequested:
            out = {"error": "已停止"}
        except Exception as e:
            out = {"error": "%s" % e}
        finally:
            _llm_mod.set_abort(None)
        self.done.emit(out)


class WritePage(QWidget):
    """码字页（index 1，导航第二位）。"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._worker = None
        self._cur_index = None      # 当前编辑的正式章节号
        self._dirty = False

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)

        # 顶行：标题 + 新建/保存/自动保存
        top = QHBoxLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("本章标题（保存后生效）")
        self.title_edit.textChanged.connect(lambda _t: self._mark_dirty())
        top.addWidget(QLabel("标题"))
        top.addWidget(self.title_edit, 1)
        new_btn = QPushButton("＋ 新建下一章")
        new_btn.setToolTip("新建下一章（章号为项目下一章），保存后正式归档")
        new_btn.clicked.connect(self._new_chapter)
        top.addWidget(new_btn)
        save_btn = QPushButton("💾 保存")
        save_btn.setObjectName("primary")
        save_btn.setToolTip("保存本章（自动备份旧稿到草稿箱 + git 归档）")
        save_btn.clicked.connect(self._save)
        top.addWidget(save_btn)
        self.auto_chk = QCheckBox("自动保存（30秒）")
        self.auto_chk.setToolTip("编辑后 30 秒无操作自动保存；关闭则仅手动保存")
        self.auto_chk.toggled.connect(self._toggle_auto)
        top.addWidget(self.auto_chk)
        root.addLayout(top)

        # 主体：左目录 + 右编辑区
        body = QHBoxLayout()
        body.setSpacing(12)
        left = QWidget()
        left.setFixedWidth(260)
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(6)
        llay.addWidget(QLabel("章节目录"))
        self.ch_list = QListWidget()
        self.ch_list.itemClicked.connect(self._pick_chapter)
        llay.addWidget(self.ch_list, 1)
        # v1.68 手动重跑角色卡/主AI笔记（保存后自动处理若因 API 出错可对本章重跑）
        self.rerun_btn = QPushButton("⟳ 重跑本章角色卡/笔记")
        self.rerun_btn.setToolTip("对当前载入（或目录选中）的已保存章节，重新执行角色卡更新 + 主AI笔记压缩，"
                                  "并保存章节快照。\n用于保存后自动处理因 API 出错/中断没跑成时手动补救；"
                                  "后台执行不阻塞码字。")
        self.rerun_btn.clicked.connect(self._rerun_chapter_auto)
        llay.addWidget(self.rerun_btn)
        left_hint = QLabel("点击章节载入编辑；点「＋新建下一章」从下一章写起。")
        left_hint.setStyleSheet(T("color:#5b6470;font-size:11px;"))
        left_hint.setWordWrap(True)
        llay.addWidget(left_hint)
        body.addWidget(left)

        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(0, 0, 0, 0)
        rlay.setSpacing(6)
        self.edit = QPlainTextEdit()
        self.edit.setPlaceholderText("在这里码字……可选中段落用下方 AI 工具，或点「AI 续写」接着写。")
        self.edit.textChanged.connect(self._mark_dirty)
        self.edit.setMinimumHeight(420)
        rlay.addWidget(self.edit, 1)

        # AI 工具行
        arow = QHBoxLayout()
        arow.addWidget(QLabel("AI 续写"))
        self.cont_hint = QLineEdit()
        self.cont_hint.setPlaceholderText("想写什么（可选）：如 男主与师妹重逢，引出误会…")
        self.cont_hint.setClearButtonEnabled(True)
        arow.addWidget(self.cont_hint, 1)
        self.len_spin = QSpinBox()
        self.len_spin.setRange(100, 2000)
        self.len_spin.setValue(400)
        self.len_spin.setSingleStep(100)
        self.len_spin.setSuffix(" 字")
        arow.addWidget(self.len_spin)
        self.cont_btn = QPushButton("✍ 续写")
        self.cont_btn.setObjectName("primary")
        self.cont_btn.setToolTip("以光标前文为衔接，续写指定字数并插入光标处（可填写想写的内容方向）")
        self.cont_btn.clicked.connect(self._continue)
        arow.addWidget(self.cont_btn)
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop_worker)
        arow.addWidget(self.stop_btn)
        arow.addSpacing(12)
        self.polish_btn = QPushButton("✨ AI 段落工具")
        self.polish_btn.setToolTip("选中任意段落 → 润色 / 扩写 / 缩写 / 去AI味 → 预览替换")
        self.polish_btn.clicked.connect(self._polish)
        arow.addWidget(self.polish_btn)
        self.chars_lbl = QLabel("0 字")
        self.chars_lbl.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        arow.addStretch(1)
        arow.addWidget(self.chars_lbl)
        rlay.addLayout(arow)

        # v1.68 上下文行：码字页也能直接开关「续写/段落工具」注入哪些上下文（与设置页同键同步）
        ctx_row = QHBoxLayout()
        ctx_row.setSpacing(8)
        ctx_lab = QLabel("任务上下文")
        ctx_lab.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        ctx_row.addWidget(ctx_lab)
        self.ctx_style_chk = QCheckBox("正文AI文风")
        self.ctx_notes_chk = QCheckBox("故事设定+笔记")
        self.ctx_rp_chk = QCheckBox("人物读取推理")
        ctx_tip = ("控制「AI 续写」与「AI 段落工具」在提示词中附带多少上下文（与设置页\n"
                   "「生成参数 → 常用 → 码字 AI 任务上下文」同一组开关，改动两边同步）：\n"
                   "· 正文AI文风：正文AI提示词 + 文风参考/风格要点；\n"
                   "· 故事设定+笔记：剧情发展/世界观/特殊规则 + 管理笔记/重要角色档案/灵感/知识库；\n"
                   "· 人物读取推理：按近几章出场 + 笔记点名的角色卡读取并推理其言行。\n"
                   "默认全开保证效果；省 token 时可关，只影响提示词内容不改变流程。")
        for chk in (self.ctx_style_chk, self.ctx_notes_chk, self.ctx_rp_chk):
            chk.setToolTip(ctx_tip)
            chk.toggled.connect(self._save_ctx_switches)
            ctx_row.addWidget(chk)
        self.ctx_goto_btn = QPushButton("设置页…")
        self.ctx_goto_btn.setToolTip("打开设置页（可在「码字AI（续写/段落工具）」行单独选 API 配置）")
        self.ctx_goto_btn.clicked.connect(self._goto_settings)
        ctx_row.addWidget(self.ctx_goto_btn)
        ctx_row.addStretch(1)
        rlay.addLayout(ctx_row)
        body.addWidget(right, 1)
        root.addLayout(body, 1)

        # 自动保存定时器
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._auto_save)
        self._save_done.connect(self._on_save_done)

    # ---------- 状态 ----------
    def on_show(self):
        self._refresh_list()
        self._refresh_ctx_switches()

    # v1.68 码字页上下文开关：与设置页同键 tool_ctx_*，改动即存 config（续写/段落工具每次调用前现读）
    def _refresh_ctx_switches(self):
        import config as _cfg168
        cfg = _cfg168.load_config()
        self.ctx_style_chk.blockSignals(True)
        self.ctx_notes_chk.blockSignals(True)
        self.ctx_rp_chk.blockSignals(True)
        self.ctx_style_chk.setChecked(bool(cfg.get("tool_ctx_style", True)))
        self.ctx_notes_chk.setChecked(bool(cfg.get("tool_ctx_notes", True)))
        self.ctx_rp_chk.setChecked(bool(cfg.get("tool_ctx_rp", True)))
        self.ctx_style_chk.blockSignals(False)
        self.ctx_notes_chk.blockSignals(False)
        self.ctx_rp_chk.blockSignals(False)

    def _save_ctx_switches(self, _chk=None):
        import config as _cfg168
        cfg = _cfg168.load_config()
        cfg["tool_ctx_style"] = self.ctx_style_chk.isChecked()
        cfg["tool_ctx_notes"] = self.ctx_notes_chk.isChecked()
        cfg["tool_ctx_rp"] = self.ctx_rp_chk.isChecked()
        _cfg168.save_config(cfg)
        log_fn("info", "码字任务上下文开关：文风=%s 笔记=%s 人物推理=%s"
               % (cfg["tool_ctx_style"], cfg["tool_ctx_notes"], cfg["tool_ctx_rp"]))

    def _goto_settings(self):
        # 设置页 index=9（v1.66 码字页插入后：项目0 码字1 角色2 生成3 去AI味4 文风5 拆书6
        # AI对话7 故事8 设置9 教程10 情景提示词11）
        try:
            if self.app is not None and hasattr(self.app, "switch_page"):
                self.app.switch_page(9)
        except Exception:
            pass

    def _mark_dirty(self):
        self._dirty = True
        self._update_chars()

    def _update_chars(self):
        n = len(self.edit.toPlainText())
        self.chars_lbl.setText("%d 字" % n)

    def _toggle_auto(self, on):
        if on:
            self._timer.start(30000)
        else:
            self._timer.stop()

    def _refresh_list(self):
        store, project = current_project()
        self.ch_list.blockSignals(True)
        self.ch_list.clear()
        if project:
            for seq, meta in store.chapter_summaries():
                self.ch_list.addItem("第%d章 · %s（%d字）" % (
                    seq, str(meta.get("title") or "第%d章" % seq),
                    int(meta.get("chars", 0))))
        self.ch_list.blockSignals(False)

    # ---------- 章节操作 ----------
    def _pick_chapter(self, item):
        if self._dirty and not self._confirm_discard():
            return
        store, project = current_project()
        if not project:
            return
        # 列表顺序即序号升序；从文本取章号
        text = item.text()
        try:
            idx = int(text.split("·")[0].replace("第", "").replace("章", "").strip())
        except (ValueError, IndexError):
            QMessageBox.warning(self, "提示", "无法识别该章节号。")
            return
        ch = store.load_chapter(idx)
        if not ch:
            QMessageBox.warning(self, "提示", "章节数据缺失。")
            return
        self._cur_index = idx
        self.title_edit.setText(ch.title or "第%d章" % idx)
        self.edit.setPlainText(ch.content or "")
        self._dirty = False
        self._update_chars()

    def _new_chapter(self):
        if self._dirty and not self._confirm_discard():
            return
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目（项目页新建或打开）。")
            return
        nxt = int((project.state or {}).get("next_chapter", 1))
        # 若 next_chapter 落后于现有最大章号则取 max+1（避免覆盖已归档章节）
        done = store.list_chapter_indices()
        if done:
            nxt = max(nxt, max(done) + 1)
        self._cur_index = nxt
        self.title_edit.setText("第%d章" % nxt)
        self.edit.setPlainText("")
        self._dirty = False
        self._update_chars()
        log_fn("info", "码字：开始写第 %d 章（保存后正式归档）。" % nxt)

    def _confirm_discard(self):
        ret = QMessageBox.question(self, "有未保存修改",
                                   "当前内容尚未保存，切换章节将丢失这些修改。继续？")
        return ret == QMessageBox.StandardButton.Yes

    def _save(self):
        if self._cur_index is None:
            QMessageBox.warning(self, "提示", "请先选择或新建章节。")
            return
        text = self.edit.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "正文不能为空。")
            return
        title = self.title_edit.text().strip() or "第%d章" % self._cur_index
        eng = engine_for(APP["project_dir"])
        idx = self._cur_index
        save_title = title

        def work():
            import models
            old = eng.store.load_chapter(idx)
            ch = old or models.Chapter(index=idx)
            ch.title = save_title
            ch.content = text
            eng.edit_chapter(ch)
            return idx

        threading.Thread(target=self._save_work, args=(work,), daemon=True).start()
        self.chars_lbl.setText("正在保存第 %d 章…" % idx)

    def _save_work(self, work):
        try:
            idx = work()
            self._save_done.emit(("ok", idx))
        except Exception as e:
            log_fn("warn", "保存章节失败：%s" % e)
            self._save_done.emit(("err", "%s" % e))

    _save_done = Signal(tuple)

    def _on_save_done(self, payload):
        kind, val = payload
        if kind == "ok":
            self._dirty = False
            self._refresh_list()
            log_fn("info", "第 %d 章已保存（旧稿已备份草稿箱 + git 归档）。" % val)
            self.chars_lbl.setText("第 %d 章已保存。" % val)
            self._start_bg_auto(val)
        else:
            QMessageBox.warning(self, "保存失败", val)

    # ---------- 保存后自动角色卡/主AI笔记（v1.67 后台异步，不阻塞写下一章） ----------
    _bg_busy = False
    _bg_pending = None

    def _start_bg_auto(self, idx):
        """保存成功后后台自动更新角色卡（update_world）+ 主AI笔记（compress_summary）。

        后台线程执行、daemon 不阻塞编辑；若已有处理线程在跑，则排队补处理最新章节。
        """
        store, project = current_project()
        if not project or not store:
            return
        ch = store.load_chapter(idx)
        if not ch:
            return
        if self._bg_busy:
            self._bg_pending = idx   # 处理线程结束后补处理本章
            return
        self._bg_busy = True
        self.chars_lbl.setText("已保存。后台更新角色卡/主AI笔记中…（可继续码字）")
        threading.Thread(target=self._bg_auto_work, args=(store, project, ch),
                         daemon=True).start()

    def _rerun_chapter_auto(self):
        """v1.68 手动重跑：对当前载入/选中的已保存章节重跑角色卡+主AI笔记+快照。

        复用同一后台流程（_bg_auto_work，含防并发与排队）；作「保存后自动处理
        因 API 出错/中断没跑成」的手动补救入口。
        """
        store, project = current_project()
        if not project or not store:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        item = self.ch_list.currentItem()
        if self._cur_index is None and item is None:
            QMessageBox.warning(self, "提示", "请先在章节目录选择或载入一个已保存章节。")
            return
        idx = self._cur_index
        if idx is None and item is not None:
            try:
                idx = int(item.text().split("·")[0].replace("第", "").replace("章", "").strip())
            except (ValueError, IndexError):
                QMessageBox.warning(self, "提示", "无法识别该章节号。")
                return
        ch = store.load_chapter(idx)
        if not ch:
            QMessageBox.warning(self, "提示", "第 %d 章数据缺失，无法重跑。" % idx)
            return
        log_fn("info", "手动重跑：第 %d 章角色卡/主AI笔记（快照一并更新）。" % idx)
        if self._bg_busy:
            self._bg_pending = idx
            self.chars_lbl.setText("已有后台处理进行中，第 %d 章稍后自动补跑。" % idx)
            return
        self._bg_busy = True
        self.chars_lbl.setText("正在后台重跑第 %d 章角色卡/主AI笔记…（可继续码字）" % idx)
        threading.Thread(target=self._bg_auto_work, args=(store, project, ch),
                         daemon=True).start()

    def _bg_auto_work(self, store, project, chapter):
        """后台：更新角色卡与信息库 → 主AI笔记压缩写回（仿 engine.finalize_chapter 战后更新）。"""
        try:
            eng = engine_for(APP["project_dir"])
            # ① 角色卡/信息库更新（update_world → _apply_world_updates）
            try:
                world = main_ai.update_world(project, store, chapter)
                eng._apply_world_updates(project, chapter, world)
                log_fn("info", "后台：第 %d 章角色卡/信息库已更新。" % chapter.index)
            except Exception as e:
                log_fn("warn", "后台角色卡更新失败：%s" % e)
            # ② 主AI笔记压缩写回（哦管理笔记 + 角色档案 + 灵感 + 知识库）
            try:
                summary_data = main_ai.compress_summary(project, store)
                if isinstance(summary_data, dict):
                    note = str(summary_data.get("note") or "").strip()
                    if note:
                        project.story_summary = note
                    kcs = summary_data.get("key_characters") or []
                    if isinstance(kcs, list):
                        project.story_characters = [
                            {"name": str(x.get("name", "")).strip(),
                             "info": str(x.get("info", "")).strip()}
                            for x in kcs if isinstance(x, dict) and str(x.get("name", "")).strip()]
                    ideas = summary_data.get("ideas") or []
                    if isinstance(ideas, list):
                        project.story_ideas = [str(x).strip() for x in ideas if str(x).strip()]
                    knowledge = str(summary_data.get("knowledge") or "").strip()
                    if knowledge:
                        old_kb = (project.story_knowledge or "").strip()
                        project.story_knowledge = (old_kb + "\n" + knowledge).strip() if old_kb else knowledge
                    eng._apply_archive_suggestions(summary_data.get("archive") or [])
                store.save_project(project)
                # v1.68 章节快照：保存本章完成后的世界状态（角色卡/信息库/伏笔/笔记），
                # 供日后章节重写/回滚（与引擎 finalize_chapter 的存档节奏一致）
                try:
                    eng.store.save_world_snapshot(chapter.index)
                except Exception as e:
                    log_fn("warn", "后台章节快照保存失败：%s" % e)
                log_fn("info", "后台：第 %d 章主AI笔记已更新（%d 个角色档案、%d 条灵感）。"
                       % (chapter.index, len(project.story_characters),
                          len(project.story_ideas)))
            except Exception as e:
                log_fn("warn", "后台主AI笔记更新失败：%s" % e)
        finally:
            self._bg_busy = False
            pending = self._bg_pending
            self._bg_pending = None
            if pending is not None:
                pending_store, pending_project = current_project()
                pch = pending_store.load_chapter(pending) if pending_store else None
                if pending_project and pch:
                    self._bg_busy = True
                    self.chars_lbl.setText("已保存。后台更新角色卡/主AI笔记中…（可继续码字）")
                    threading.Thread(target=self._bg_auto_work,
                                     args=(pending_store, pending_project, pch),
                                     daemon=True).start()

    # ---------- AI 续写 ----------
    def _continue(self):
        if self._worker is not None:
            return
        ahead = self.edit.toPlainText()
        if len(ahead) > 1600:
            ahead = ahead[-1600:]
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        if self._cur_index is None:
            self._new_chapter()
        n = self.len_spin.value()
        directive = self.cont_hint.text().strip()
        if directive:
            log_fn("info", "AI 续写：%d 字（用户方向：%s…）" % (n, directive[:40]))
        self.cont_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        worker = WriteWorker()
        self._worker = worker
        set_running(True)
        worker.done.connect(self._on_continue)
        threading.Thread(target=worker.run, args=(project, ahead, n),
                         kwargs={"directive": directive, "store": store},
                         daemon=True).start()

    def _on_continue(self, payload):
        self.cont_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._worker = None
        set_running(False)
        if isinstance(payload, dict) and payload.get("error"):
            if "已停止" not in str(payload.get("error", "")):
                QMessageBox.warning(self, "续写失败", str(payload["error"]))
            self.chars_lbl.setText("续写未完成。")
            return
        text = str(payload or "").strip()
        if not text:
            return
        cursor = self.edit.textCursor()
        cursor.beginEditBlock()
        cursor.insertText(text if not text.endswith("\n") else text)
        cursor.endEditBlock()
        self.edit.setTextCursor(cursor)
        self.edit.setFocus()
        self._mark_dirty()
        self.chars_lbl.setText("已续写 %d 字。" % len(text))

    def _stop_worker(self):
        if self._worker is not None:
            self._worker.stop()

    # ---------- AI 段落工具（复用生成页 PolishParagraphDialog） ----------
    def _polish(self):
        cursor = self.edit.textCursor()
        text = cursor.selectedText().replace("\u2029", "\n").strip()
        if not text:
            QMessageBox.information(self, "提示", "请先在正文中选中要处理的一段文字。")
            return
        from gui_generate import PolishParagraphDialog
        dlg = PolishParagraphDialog(text, self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            new_text = dlg.result_text()
            if not new_text:
                return
            cursor.beginEditBlock()
            cursor.removeSelectedText()
            cursor.insertText(new_text)
            cursor.endEditBlock()
            self.edit.setTextCursor(cursor)
            self.edit.setFocus()
            self._mark_dirty()
            log_fn("info", "AI 段落工具：%d 字 → %d 字" % (len(text), len(new_text)))

    def _auto_save(self):
        if self._dirty and self._cur_index is not None and self.auto_chk.isChecked():
            self._save()