# -*- coding: utf-8 -*-
"""一键成书（v0.54）：描述小说想法 + 章节数 → AI 自动立项（书名/剧情/世界观/规则）
→ 创建项目 → 自动生成核心角色 → 全自动连写 N 章；随时可停，停后项目留在书架正常管理。

与生成页其它对话框不同：本对话框内嵌自己的后台线程与信号桥（不占全局 running 锁，
避免与生成页的全自动互斥），进度用独立进度条 + 日志文本框展示。
"""
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPlainTextEdit, QProgressBar,
                               QPushButton, QScrollArea, QSpinBox, QTextBrowser,
                               QVBoxLayout, QWidget)

import llm
import main_ai
import storage
from gui_app import APP, current_project, engine_for, set_running
from gui_theme import T


class _BookWorker(QObject):
    """一键成书的后台线程载体：立项 + 连写，信号回传日志/进度/结果。"""

    log = Signal(str, str)      # (kind, msg)
    progress = Signal(int, int)  # (done_chapters, total_chapters)
    project_ready = Signal(str, str)  # v1.15 (dir, title)：立项完成（项目已建+三栏已写入）即通知 UI，不等第一章
    done = Signal(object)        # dict: {"ok", "msg", "dir", "title", "chapters"} 或 {"ok":False,"error"}

    def __init__(self):
        super().__init__()
        self._stop = threading.Event()

    def stop(self):
        self._stop.set()
        # 立即停止：主动 close 在途 LLM 请求连接（流式读取立刻抛 StopRequested→转 StopRequested 传播回 UI）
        import llm as _llm_abort
        _llm_abort.abort_active_resps()

    def run(self, idea, chapters, total_chapters=0, project_dir=None,
            style_note="", break_style="", style_ref="", main_prompt="",
            writer_prompt="", book_title="", scene_cards_active=(), auto_chapters=None):
        """一键成书：project_dir 为 None = 完整流程（AI 立项 + 建项目 + 连写）；
        给定 project_dir = 「继续写」模式：在已有项目上从 next_chapter 自动连写剩余章节
        （跳过立项/建项目/核心角色——失败或停止后可点「继续写」往前推进，不用从头）。

        style_note / break_style / style_ref / main_prompt / writer_prompt：v1.00 新建模式
        把面板全部 AI 设置写入新项目（主AI每章注入，控制生成质量）；继续模式不覆盖项目
        已有设置（中途改设置用面板「应用以上设置到当前项目」按钮，从下一章生效、
        不用删已生成章节）。

        scene_cards_active：v1.21 新建模式把面板从**总库**勾选的情景卡名复制进新项目
        （project.scene_cards，[{name,content,source}]，source="user"；与总库独立——
        主AI每章按正文类型从中选卡，缺匹配类型时自做一张只进本库）。

        book_title：v1.13 新建模式可选书名——用户手动指定书名/项目名；留空则 AI 按想法起名。

        chapters：新建模式 = 本次连写章数；继续模式 = 目标章号（绝对）；
        total_chapters：新建模式写入项目卷目标。
        auto_chapters（v1.73）：None/False = 手动模式（按 chapters/total_chapters 走）；
        True = 「AI 自动判断章节数」——AI 先按想法+设定判断全书总章数，本次连写
        也直接写到该数（判断失败回退 total_chapters，仍失败用默认 30）。
        """
        import llm as _llm
        _llm.set_abort(self._stop)
        try:
            logs = []
            sink = lambda k, m: (logs.append((k, m)), self.log.emit(k, m))
            project_dir = (project_dir or "").strip()
            store = eng = project = None
            done_init = 0
            title = ""
            if project_dir:
                # ① 继续模式：载入已有项目（不重新立项）
                store = storage.ProjectStore(project_dir)
                project = store.load_project()
                if project is None:
                    self.done.emit({"ok": False, "error": "项目不存在或已损坏，无法继续。"})
                    return
                done_init = max(0, int(project.state.get("next_chapter", 1)) - 1)
                # v1.80 全书完成后点「继续写」= 主动要求继续，解除完结标记再写
                # （生成页全自动连写受完结标记保护，不会误续写）
                if project.state.get("story_complete"):
                    project.state["story_complete"] = False
                    store.save_project(project)
                    self.log.emit("info", "已解除完结状态，继续自动连写剩余章节。")
                title = project.title or "当前项目"
                APP["project_dir"] = project_dir
                from gui_app import bus
                bus.projectChanged.emit()
                eng = engine_for(project_dir)
                self.log.emit("info", "继续模式：在《%s》上从第 %d 章继续自动连写…"
                              % (title, done_init + 1))
            else:
                self.log.emit("info", "开始一键成书：正在由 AI 立项…")

            if project_dir:
                pass
            else:
                # 1) 书名：用户手动指定优先（v1.13），留空才由 AI 按想法起名（失败回退自动名）
                title = (book_title or "").strip()
                if not title:
                    try:
                        title = main_ai.plan_title(idea)
                    except llm.LLMError as e:
                        sink("warn", "起书名失败（%s），使用自动书名。" % e)
                if not (title or "").strip():
                    # v1.97 不再产出「AI 新书」占位名：从想法抽关键词当临时名，并明确告知可改名
                    title = main_ai._fallback_title(idea)
                    sink("warn", "AI 尚未起出合适的书名，已用临时书名《%s》，可随时改名。" % title)
                sink("info", "书名确定：《%s》" % title)

                # 2) AI 起草三栏设定（剧情/世界观/规则）
                self.log.emit("info", "正在起草故事设定（剧情 / 世界观 / 特殊规则）…")
                data = main_ai.plan_story_ai("", idea, "%d 章" % chapters,
                                             ("story", "world", "rules"))
                if not isinstance(data, dict):
                    data = {}
                story = str(data.get("story") or "").strip()
                world = str(data.get("world") or "").strip()
                rules = str(data.get("rules") or "").strip()
                if not (story or world or rules):
                    self.done.emit({"ok": False, "error": "AI 没有生成出故事设定，请换个想法重试。"})
                    return
                sink("info", "故事设定起草完成（剧情 %d 字 / 世界观 %d 字 / 规则 %d 字）。"
                     % (len(story), len(world), len(rules)))

                # v1.73「AI 自动判断章节数」：按想法+三栏设定判断全书总章数，本次连写
                # 也直接写到该数（判断失败回退用户手填 total_chapters，再失败用默认 30）
                if auto_chapters:
                    ai_total = main_ai.plan_chapters(
                        idea, story=story, world=world, rules=rules,
                        author_constraint=idea,
                        default=(int(total_chapters or 0) or 30))
                    total_ch = max(1, int(ai_total))
                    chapters = total_ch
                    sink("info", "AI 自动判断：本书全书约 %d 章，本次连写直接写到该数。"
                         % total_ch)
                else:
                    total_ch = max(0, int(total_chapters or 0))

                # 3) 创建项目并填入设定，切为当前项目（停止后也能在书架看到）
                project = storage.create_project(title)
                store = storage.ProjectStore(project.dir_name)
                project.story_brief = story
                project.story_world = world
                project.story_rules = rules
                # v1.00 一键成书套用面板全部 AI 设置（主AI每章注入，控制生成质量）
                sn = (style_note or "").strip()
                bs = (break_style or "").strip()
                if sn:
                    project.story_style_note = sn
                    sink("info", "已套用文风参考·风格要点（%d 字）。" % len(sn))
                if bs:
                    project.story_break_style = bs
                    sink("info", "已套用拆书设计风格：%s（主AI每章学习其剧情设计技法）。" % bs)
                if (style_ref or "").strip():
                    project.story_style_ref = style_ref.strip()
                    sink("info", "已套用参考文风样本（%d 字）。" % len(style_ref.strip()))
                if (main_prompt or "").strip():
                    project.story_main_prompt = main_prompt.strip()
                    sink("info", "已套用主AI全局提示词（%d 字）。" % len(main_prompt.strip()))
                if (writer_prompt or "").strip():
                    project.story_writer_prompt = writer_prompt.strip()
                    sink("info", "已套用正文AI角色提示词（%d 字）。" % len(writer_prompt.strip()))
                # v1.21 本项目主AI可用情景卡库：面板从**总库**勾选的卡名 → 复制总库卡内容
                # 进新项目 project.scene_cards（source="user"；与总库独立，主AI每章按正文
                # 类型从这里选卡，缺匹配类型时自做一张只进本库）
                sc_names = [str(x).strip() for x in (scene_cards_active or [])
                            if str(x).strip()]
                if sc_names:
                    try:
                        import config as _cfg121
                        _by_name121 = {str(c.get("name") or "").strip(): c
                                       for c in (_cfg121.load_config()
                                                 .get("writer_scene_cards") or [])
                                       if isinstance(c, dict)
                                       and str(c.get("name") or "").strip()
                                       and str(c.get("content") or "").strip()}
                        project.scene_cards = [{"name": nm,
                                                "content": str(_by_name121[nm]
                                                               .get("content") or ""),
                                                "source": "user",
                                                # v1.29 补分类：一键成书立项从总库复制卡时
                                                # 保留 category，项目库不再全部变成未分类
                                                "category": str(_by_name121[nm]
                                                                .get("category") or "")}
                                               for nm in sc_names if nm in _by_name121]
                    except Exception:
                        project.scene_cards = []
                    if project.scene_cards:
                        sink("info", "已把 %d 张总库情景卡带入新项目（主AI每章按正文类型从中选卡，"
                             "缺匹配类型时自做一张只进本库）。" % len(project.scene_cards))
                # v1.80 修复：AI 自动判断出的章数要原样写进「全书计划」——此前这里无条件用
                # 面板手填值重新覆盖 total_ch，导致 AI 判断等于没生效（项目页/进度看到的
                # 还是手动填的数）
                if total_ch <= 0:
                    total_ch = max(0, int(total_chapters or 0))
                if total_ch > 0:
                    # 全书计划总章节：写入卷目标（主AI按此规划与判断完本）
                    project.volume_target = total_ch
                    project.state["volume_plan"] = {
                        "target_chapters": total_ch,
                        "description": "一键成书设定的全书总章节计划",
                    }
                store.save_project(project)
                APP["project_dir"] = project.dir_name
                from gui_app import bus
                bus.projectChanged.emit()
                # v1.15 立项完成即通知 UI：项目已建+三栏已写入，不等第一章写完就能看到
                self.project_ready.emit(project.dir_name, title)
                sink("info", "项目已创建：《%s》（书架里现在就能看到它）%s"
                     % (title, "；全书计划 %d 章" % total_ch if total_ch > 0 else ""))

                # 4) 自动生成核心角色 + 连写 N 章
                eng = engine_for(project.dir_name)

                def stop_check():
                    return self._stop.is_set()

                try:
                    eng.ensure_world(project)
                except llm.LLMError as e:
                    sink("warn", "自动生成核心角色失败（%s），将直接开始写作。" % e)

            # 连写循环（继续模式从断点绝对章号续写；新建模式从第 1 章写起）
            target_ch = max(1, int(chapters))
            if project_dir and target_ch <= done_init:
                sink("info", "《%s》已写到第 %d 章，没有需要继续写的章节。"
                     % (title, done_init))
                self.done.emit({
                    "ok": True,
                    "msg": "《%s》已写到第 %d 章，无需继续。" % (title, done_init),
                    "dir": project_dir, "title": title, "chapters": done_init})
                return
            last = done_init
            for ch_no in range(done_init + 1, target_ch + 1):
                if self._stop.is_set():
                    sink("info", "已收到停止指令，暂停自动生成（已写 %d 章，项目已建好可在书架继续）。"
                         % last)
                    break
                self.log.emit("info", "═══ 全自动连写 第 %d/%d 章 ═══" % (ch_no, target_ch))
                try:
                    ch = eng.generate_draft(project, beats_confirm=None)
                    if ch is not None:
                        eng.finalize_chapter(project, ch)
                except _llm.StopRequested:
                    sink("info", "已停止：立即中断当前章节写作（已写 %d 章，项目已建好可在书架继续）。"
                         % last)
                    break
                except _llm.LLMError as e:
                    sink("warn", "第 %d 章失败：%s（已写 %d 章，可点「继续写」往前推进）。"
                         % (ch_no, e, last))
                    break
                except Exception as e:
                    sink("error", "第 %d 章异常：%s" % (ch_no, e))
                    break
                self.progress.emit(ch_no, target_ch)
                last = ch_no
            done = last
            sink("info", "一键成书结束：共完成 %d 章。可在书架找到《%s》继续编辑/生成。"
                 % (done, title))
            self.done.emit({
                "ok": True,
                "msg": "已创建《%s》并完成 %d 章；停止后项目保留在书架，可随时继续。"
                       % (title, done),
                "dir": project.dir_name, "title": title, "chapters": done,
            })
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.done.emit({"ok": False, "error": "一键成书失败：%s" % e})
        finally:
            _llm.set_abort(None)
            set_running(False)


class BookPanel(QWidget):
    """一键成书面板（v0.53 独立 UI）：描述 + 总章节数 + 本次生成到多少章 → 自动立项连写；可停止。

    既可作为项目页的独立 tab 页嵌入（与「新建项目」平级），也可包进对话框窗口使用。
    """

    def __init__(self, parent=None, show_title=True):
        super().__init__(parent)
        self._worker = None
        # v1.00 内容较高（AI 设置区多行）→ 内部包滚动容器，防小窗口/200% 缩放下压扁
        self._body = QWidget()
        lay = QVBoxLayout(self._body)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        if show_title:
            tip = QLabel("<h3 style='margin:0;'>✨ 一键成书（AI 自动立项 + 全自动连写）</h3>"
                         "描述你想要什么样的小说，AI 自动完成：起书名 → 起草剧情/世界观/特殊规则"
                         " → 创建项目（书架立即可见）→ 生成核心角色 → 全自动连写。\n"
                         "可随时点「停止」立即中断（不等本章写完）；已完成的章节保留在书架，"
                         "之后随时继续写/改设定/重写章节。")
        else:
            tip = QLabel("描述你想要什么样的小说，AI 自动完成：起书名 → 起草剧情/世界观/特殊规则"
                         " → 创建项目（书架立即可见）→ 生成核心角色 → 全自动连写。\n"
                         "可随时点「停止」立即中断（不等本章写完）；已完成的章节保留在书架，"
                         "之后随时继续写/改设定/重写章节。")
        tip.setWordWrap(True)
        tip.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lay.addWidget(tip)

        lay.addWidget(QLabel("基本提示词 / 小说想法（想写什么、什么题材、主角/基调/看点等）"))
        self.idea_edit = QPlainTextEdit()
        self.idea_edit.setPlaceholderText(
            "例：一个现代都市白领意外穿越到修仙废土，觉醒「捡垃圾」金手指——捡到的废铜烂铁都能变成神器碎片，"
            "从被人嘲笑的废柴一路逆袭，还要养一只话痨流浪狗…\n"
            "基调轻松诙谐带点热血，短章快节奏。")
        self.idea_edit.setMaximumHeight(120)
        lay.addWidget(self.idea_edit)

        # v1.13 书名/项目名可手动指定（留空则由 AI 按想法起名——立项时优先用这里的书名）
        brow = QHBoxLayout()
        brow.addWidget(QLabel("📖 书名 / 项目名（可选）"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("留空则 AI 按你的想法自动起名")
        brow.addWidget(self.title_edit, 1)
        lay.addLayout(brow)

        # 两个目标分列：全书总章节（写入项目计划） + 本次一键生成到多少章（本次连写）
        trow = QHBoxLayout()
        trow.addWidget(QLabel("小说总章节数（全书计划）"))
        self.total_spin = QSpinBox()
        self.total_spin.setRange(1, 3000)
        self.total_spin.setValue(30)
        self.total_spin.setToolTip("这本小说全书计划写多少章——会写入项目「当前卷目标」，"
                                   "主AI按此规划剧情节奏与完本判断；之后可以随时改")
        trow.addWidget(self.total_spin)
        trow.addSpacing(24)
        # v1.73「AI 自动判断章节数」：勾选后由 AI 按想法+设定判断全书总章数，
        # 本次连写也直接写到判断出的章数（可随时停止，项目保留）
        self.auto_chk = QCheckBox("AI 自动判断章节数")
        self.auto_chk.setToolTip("不手填章节数：立项时 AI 根据你的想法和故事设定自动判断这本书"
                                 "全书写多少章，本次连写也直接写到判断出的章数。\n"
                                 "（若 AI 判断失败则回退上面填写的总章节数）")
        self.auto_chk.toggled.connect(self._auto_toggled)
        trow.addWidget(self.auto_chk)
        trow.addSpacing(24)
        trow.addWidget(QLabel("本次一键生成到"))
        self.ch_spin = QSpinBox()
        self.ch_spin.setRange(1, 9999)
        self.ch_spin.setValue(5)
        self.ch_spin.setToolTip("这次让 AI 连写到多少章（可直接填本书的总章节数一次生成完；"
                                "约 2000~4000 字/章，全自动可随时停止、停止后项目保留可继续；"
                                "勾选「AI 自动判断章节数」后此值由 AI 决定）")
        trow.addWidget(self.ch_spin)
        trow.addWidget(QLabel("章"))
        trow.addStretch(1)
        lay.addLayout(trow)
        lay.addWidget(QLabel("提示：本次生成章数可以小于总章节数——先让 AI 写开头几章，"
                             "看完风格满意后，回到「项目」页或生成页继续写后面的章节。"),
                      alignment=Qt.AlignmentFlag.AlignLeft)

        # v1.00 AI 设置区（完整覆盖项目级 AI 设置，控制一键成书生成质量）：
        # 文风参考（风格要点，可写「你是一个……」规则类要求）/ 参考文风样本 /
        # 主AI全局提示词 / 正文AI角色提示词 / 拆书设计风格。
        # 新建一键成书时全部自动写入新项目；已生成几章后改这里 → 点「应用」→ 从下一章
        # 生效，**不用删掉已生成的章节**。
        lay.addWidget(QLabel("✏️ 文风参考 · 风格要点（可选）：正文AI按此写作；支持规则类要求，"
                             "如「你是一个擅长宏大战争场面的网文作家，写作时……」"))
        self.style_note_edit = QPlainTextEdit()
        self.style_note_edit.setPlaceholderText(
            "例：你是一个擅长冷峻白描的网文作家——短句切割节奏、重感官氛围、对话简洁克制；"
            "动作场景用快节奏短句；少用成语与空泛抒情…")
        self.style_note_edit.setMaximumHeight(76)
        lay.addWidget(self.style_note_edit)

        lay.addWidget(QLabel("📄 参考文风样本（可选）：一段具体小说文本作为文风标杆，"
                             "写作时模仿其语感句式，不抄内容"))
        self.style_ref_edit = QPlainTextEdit()
        self.style_ref_edit.setPlaceholderText(
            "可贴多段不同情景的笔调样本（打斗/文斗/日常/情绪酝酿等各一小段，总长不限），"
            "AI 写作时按章节所处情景取对应笔调模仿语感/句式/节奏/描写手法…")
        self.style_ref_edit.setMaximumHeight(200)
        lay.addWidget(self.style_ref_edit)

        lay.addWidget(QLabel("🎯 主AI全局提示词（可选）：对主AI的总要求，"
                             "影响决断/校验/写后校对等全流程（如：主线要快节奏不拖沓、"
                             "杜绝降智、伏笔要按时回收…）"))
        self.main_prompt_edit = QPlainTextEdit()
        self.main_prompt_edit.setPlaceholderText(
            "例：剧情推进要快，每 3 章必须有一次实质进展；主角不能降智；伏笔不许忘…")
        self.main_prompt_edit.setMaximumHeight(76)
        lay.addWidget(self.main_prompt_edit)

        lay.addWidget(QLabel("🖋 正文AI角色提示词（可选）：对正文AI的额外指示，"
                             "只影响正文写作（如：多用动作推进、对话短而有力…）"))
        self.writer_prompt_edit = QPlainTextEdit()
        self.writer_prompt_edit.setPlaceholderText(
            "例：对话不超过三行；场景切换用空行；每章至少一处留白钩子…")
        self.writer_prompt_edit.setMaximumHeight(76)
        lay.addWidget(self.writer_prompt_edit)

        srow = QHBoxLayout()
        srow.addWidget(QLabel("📚 拆书设计风格（可选）"))
        self.break_combo = QComboBox()
        self.break_combo.setToolTip("从拆书风格库选一部已拆书的设计风格——主AI每章会学习其"
                                    "剧情推动/伏笔设计技法（只学技法不抄情节）；需先在「拆书工坊」"
                                    "保存风格，这里会自动列出")
        srow.addWidget(self.break_combo, 1)
        self.apply_style_btn = QPushButton("✓ 应用以上设置到当前项目")
        self.apply_style_btn.setObjectName("accent")
        self.apply_style_btn.setToolTip("把上面的文风/参考样本/主AI与正文AI提示词/拆书风格写入"
                                        "当前项目——后续章节立即生效，不用删掉已生成的章节")
        self.apply_style_btn.clicked.connect(self._apply_style_to_project)
        srow.addWidget(self.apply_style_btn)
        lay.addLayout(srow)
        self._refresh_breaks()

        # v1.24 情景写作提示词：「加入」式——点「＋ 加入」从总库勾选要带入本项目的卡，
        # 列表只显示已加入的（不再全部并列勾选，卡多不淹没；总库为空时引导先建卡）
        self._added_scene_cards = []
        scrow = QHBoxLayout()
        scrow.addWidget(QLabel("🃏 情景写作提示词（点「＋ 加入」从总库勾选要带入本项目的卡）"))
        scrow.addStretch(1)
        pick_btn = QPushButton("＋ 加入")
        pick_btn.setObjectName("accent")
        pick_btn.setToolTip("弹出总库选择对话框：勾选 = 本项目要带，取消勾选 = 不带（已加入的默认勾选）")
        pick_btn.clicked.connect(self._card_pick)
        scrow.addWidget(pick_btn)
        goto_sc = QPushButton("去情景提示词页建卡")
        goto_sc.setToolTip("总库为空时点这里：到「情景提示词」页新增 / AI 一键生成 / 从文本提取情景卡，"
                           "保存后回到此处点「＋ 加入」勾选")
        goto_sc.clicked.connect(self._goto_scene_cards)
        scrow.addWidget(goto_sc)
        lay.addLayout(scrow)
        self.scene_cards_list = QListWidget()
        self.scene_cards_list.setMaximumHeight(110)
        self.scene_cards_list.setToolTip("已加入本项目的情景规则卡（主AI每章按正文类型从中选卡；"
                                         "本章类型没匹配卡时主AI会自做一张只进本库）。\n"
                                         "点「＋ 加入」从总库勾选/取消勾选管理，列表不淹没全部卡。")
        lay.addWidget(self.scene_cards_list)
        self._refresh_scene_cards()

        brow = QHBoxLayout()
        brow.addStretch(1)
        self.start_btn = QPushButton("开始一键成书")
        self.start_btn.setObjectName("primary")
        self.start_btn.setToolTip("从头开始：AI 重新立项并新建一个项目来写（同名会加后缀，旧项目保留）")
        self.start_btn.clicked.connect(self._start)
        brow.addWidget(self.start_btn)
        # v0.72 继续写：在上一轮一键成书创建的项目上从断点自动连写剩余章节
        # （失败/停止后点它往前推进，不用重新立项从头写）
        self.continue_btn = QPushButton("▶ 继续写")
        self.continue_btn.setEnabled(False)
        self.continue_btn.setToolTip("在上一轮一键成书创建的项目上，从断点继续自动连写"
                                     "（写到「本次一键生成到」指定章数）")
        self.continue_btn.clicked.connect(self._continue)
        brow.addWidget(self.continue_btn)
        self.stop_btn = QPushButton("■ 停止")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip("立即停止：中断当前 LLM 请求，不再等本章写完；项目已建好的章节保留在书架")
        self.stop_btn.clicked.connect(self._stop)
        brow.addWidget(self.stop_btn)
        lay.addLayout(brow)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("0 / 0 章")
        self.progress_bar.setVisible(False)
        lay.addWidget(self.progress_bar)

        self.log_view = QTextBrowser()
        self.log_view.setOpenExternalLinks(False)
        lay.addWidget(self.log_view, 1)

        self.hint = QLabel("")
        self.hint.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lay.addWidget(self.hint)

        # 内容包滚动容器（v1.00：AI 设置区多行后整体更高）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.frameShape().NoFrame)
        scroll.setWidget(self._body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self._log_items = []
        self._last_dir = None   # v0.72 上一轮一键成书创建的项目（「继续写」目标）
        self._worker = _BookWorker()
        self._worker.log.connect(self._on_log)
        self._worker.progress.connect(self._on_progress)
        self._worker.project_ready.connect(self._on_project_ready)
        self._worker.done.connect(self._on_done)

    # ---------- 内部 ----------
    def _refresh_breaks(self):
        """刷新拆书风格下拉（保留当前选择；风格库在拆书工坊保存/删除后调用）。"""
        cur = self.break_combo.currentText()
        self.break_combo.blockSignals(True)
        self.break_combo.clear()
        self.break_combo.addItem("不使用（默认）")
        try:
            import book_break
            for it in book_break.list_breaks():
                self.break_combo.addItem(it["name"])
        except Exception:
            pass
        if cur:
            idx = self.break_combo.findText(cur)
            if idx >= 0:
                self.break_combo.setCurrentIndex(idx)
        self.break_combo.blockSignals(False)

    def _current_style_values(self):
        """面板当前全部 AI 设置（空值表示不设置）：文风要点/参考样本/主AI提示词/
        正文AI提示词/拆书风格/本项目情景写作提示词卡名。"""
        def _t(w):
            return w.toPlainText().strip() if hasattr(w, "toPlainText") else str(w or "").strip()
        brk = self.break_combo.currentText().strip()
        if brk == "不使用（默认）":
            brk = ""
        # v1.24 加入式：本面板要带入项目的情景卡 = 已加入列表（点「＋ 加入」从总库勾选）
        sc = list(self._added_scene_cards)
        return {"note": _t(self.style_note_edit), "style_ref": _t(self.style_ref_edit),
                "main_prompt": _t(self.main_prompt_edit), "writer_prompt": _t(self.writer_prompt_edit),
                "break_style": brk, "scene_cards": sc}

    def _refresh_scene_cards(self, active=None):
        """v1.24 加入式：列表只显示已加入本面板的卡（不淹没全部总库卡）。

        active：可选，传入卡名列表时先重置已加入集合（兼容旧调用方）；None 用现集合。
        """
        try:
            import config as _cfg118
            lib = _cfg118.load_config().get("writer_scene_cards") or []
            lib_by_name = {str(c.get("name") or "").strip(): c for c in lib
                           if str(c.get("name") or "").strip()}
        except Exception:
            lib_by_name = {}
        if active is not None:
            self._added_scene_cards = [str(x).strip() for x in active if str(x).strip()]
        added = [n for n in self._added_scene_cards if n in lib_by_name]
        self.scene_cards_list.blockSignals(True)
        self.scene_cards_list.clear()
        if not added:
            if not lib_by_name:
                tip_txt = ("（总库为空——先点「去情景提示词页建卡」新增 / AI 一键生成 / 从文本提取"
                           "情景卡，保存后点「＋ 加入」勾选）")
            else:
                tip_txt = ("（未加入任何情景卡——点「＋ 加入」从总库勾选要带入本项目的卡）")
            tip = QListWidgetItem(tip_txt)
            tip.setFlags(Qt.ItemFlag.NoItemFlags)
            self.scene_cards_list.addItem(tip)
        else:
            for n in added:
                c = lib_by_name.get(n, {})
                cat = str(c.get("category") or "").strip()
                label = ("[%s] %s" % (cat, n) if cat else n)
                self.scene_cards_list.addItem(label)
        self.scene_cards_list.blockSignals(False)
        self._added_scene_cards = added

    def _card_pick(self):
        """v1.24 加入式：弹总库多选对话框，勾选 = 本面板要带的卡（已加入的默认勾选，全量替换）。"""
        try:
            import config as _cfg118
            lib = _cfg118.load_config().get("writer_scene_cards") or []
        except Exception:
            lib = []
        if not lib:
            self.hint.setText("总库为空——先点「去情景提示词页建卡」新增/AI 生成/从文本提取情景卡，"
                              "保存后再回来加入。")
            return
        from gui_scene_cards import _PickCardsDialog
        dlg = _PickCardsDialog(lib, set(), self, checked=list(self._added_scene_cards))
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        picked = dlg.picked()
        self._added_scene_cards = picked
        self._refresh_scene_cards()
        if picked:
            self.hint.setText("已选择 %d 张情景卡（勾选 = 本项目要带；可再点「＋ 加入」调整）。"
                              % len(picked))
            try:
                from gui_app import log_fn
                log_fn("info", "一键成书加入情景卡：%s" % "、".join(picked))
            except Exception:
                pass
        else:
            self.hint.setText("未勾选任何情景卡——点卡行或左侧勾选框选中后再点「确定」。")

    def _goto_scene_cards(self):
        """跳转到「情景提示词」功能页（总库为空时先建卡，保存后回来勾选）。"""
        try:
            pg = self
            while pg is not None:
                if hasattr(pg, "switch_page"):
                    pg.switch_page(11)
                    return
                pg = pg.parent()
        except Exception:
            pass
        self.hint.setText("请到左侧导航「情景提示词」页管理情景卡。")

    def _apply_style_to_project(self):
        """把面板全部 AI 设置写入当前项目——后续章节立即生效，不用删已生成章节。"""
        v = self._current_style_values()
        store, project = current_project()
        if not project:
            self.hint.setText("还没有项目：点「开始一键成书」后会自动套用面板上的 AI 设置。")
            return
        mapping = [("note", "story_style_note", "文风参考·风格要点"),
                   ("style_ref", "story_style_ref", "参考文风样本"),
                   ("main_prompt", "story_main_prompt", "主AI全局提示词"),
                   ("writer_prompt", "story_writer_prompt", "正文AI角色提示词"),
                   ("break_style", "story_break_style", "拆书设计风格")]
        changed = []
        for key, field, label in mapping:
            val = v.get(key) or ""
            cur = str(getattr(project, field) or "").strip()
            if val != cur:
                setattr(project, field, val)
                changed.append(label)
        # v1.21 本项目主AI可用情景卡库：面板从总库勾选的卡名 → 复制总库卡内容进
        # project.scene_cards（source="user"；与旧 scene_cards_active 卡名列表比对，无变化不重复保存）
        sc = v.get("scene_cards") or []
        cur_sc = [str(c.get("name") or "").strip() for c in
                  (getattr(project, "scene_cards", None) or []) if isinstance(c, dict)]
        if sc != cur_sc:
            try:
                import config as _cfg121b
                _by_name121b = {str(c.get("name") or "").strip(): c
                                for c in (_cfg121b.load_config()
                                          .get("writer_scene_cards") or [])
                                if isinstance(c, dict)
                                and str(c.get("name") or "").strip()
                                and str(c.get("content") or "").strip()}
                project.scene_cards = [{"name": nm,
                                        "content": str(_by_name121b[nm]
                                                       .get("content") or ""),
                                        "source": "user",
                                        # v1.29 补分类：应用面板设置复制总库卡时保留分类
                                        "category": str(_by_name121b[nm]
                                                        .get("category") or "")}
                                       for nm in sc if nm in _by_name121b]
            except Exception:
                project.scene_cards = []
            changed.append("情景写作提示词（%d 张）" % len(project.scene_cards))
        if not changed:
            self.hint.setText("面板设置与当前项目一致（或全为空）——没有需要应用的改动。")
            return
        store.save_project(project)
        done_n = max(0, int(project.state.get("next_chapter", 1)) - 1)
        self.hint.setText("✓ 已应用：%s —— 后续章节立即按此写作；已生成的 %d 章不受影响，无需删除。"
                          % ("、".join(changed), done_n))

    def _log_html(self, kind, msg):
        colors = {"info": T("#d7dce4"), "warn": T("#c9a832"), "error": T("#c96f6f")}
        return "<div style='color:%s;margin:3px 0;font-size:13px;'>%s</div>" % (
            colors.get(kind, T("#d7dce4")), msg.replace("<", "&lt;"))

    def _on_log(self, kind, msg):
        icon = {"warn": "▲ ", "error": "✖ "}.get(kind, "")
        self._log_items.append((kind, icon + msg))
        cursor = self.log_view.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertHtml(self._log_html(kind, icon + msg))
        bar = self.log_view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _on_progress(self, done, total):
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(done)
        self.progress_bar.setFormat("%d / %d 章" % (done, total))

    def _refresh_project_page(self):
        """刷新项目页（书架下拉 + 故事设定三栏回填），让新项目/新设定立即可见。"""
        from gui_app import bus
        bus.projectChanged.emit()
        try:
            pg = self.parent()
            while pg is not None:
                if hasattr(pg, "page_project") and hasattr(pg.page_project, "on_show"):
                    pg.page_project.on_show()
                    break
                if hasattr(pg, "refresh_projects") and hasattr(pg, "tabs"):
                    pg.on_show()
                    break
                pg = pg.parent()
        except Exception:
            pass

    def _on_project_ready(self, dir_name, title):
        """v1.15 立项完成即刷新：项目已建 + 三栏设定已写入——不等第一章写完，
        书架与故事设定页立刻能看到 AI 设计的剧情/世界观/特殊规则。"""
        self._refresh_project_page()
        self.hint.setText("✓ 项目《%s》已创建，AI 已生成剧情/世界观/特殊规则——"
                          "书架与「故事设定」现在就能看到；正在连写第一章…"
                          % (title or "未命名"))

    def _on_done(self, payload):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("■ 停止")
        self.progress_bar.setVisible(False)
        self.continue_btn.setEnabled(bool(self._last_dir) or bool(payload.get("dir")))
        if payload.get("ok") and payload.get("dir"):
            self._last_dir = payload["dir"]
        set_running(False)
        if payload.get("ok"):
            self.hint.setText("✓ " + payload["msg"])
            # 刷新项目页（一键成书界面在项目页 tab）让新项目立即可见
            self._refresh_project_page()
        else:
            self.hint.setText("✖ " + str(payload.get("error", "未知错误")))
            # v0.72 失败弹窗直接给出恢复入口：继续写 / 从头再来 / 取消
            try:
                mb = QMessageBox(self)
                mb.setWindowTitle("一键成书未完成")
                mb.setText("一键成书没有全部完成：\n%s\n\n接下来怎么处理？" % str(payload.get("error", "未知错误")))
                if self._last_dir:
                    b_go = mb.addButton("▶ 继续写（断点续写剩余章节）",
                                        QMessageBox.ButtonRole.AcceptRole)
                b_new = mb.addButton("从头再来（重新立项新建项目）",
                                     QMessageBox.ButtonRole.DestructiveRole)
                mb.addButton("取消", QMessageBox.ButtonRole.RejectRole)
                mb.exec()
                clicked = mb.clickedButton()
                if self._last_dir and clicked is b_go:
                    self._continue()
                elif clicked is b_new:
                    self._start()
            except Exception:
                pass
        self._worker = None

    def _auto_toggled(self, on):
        """v1.73「AI 自动判断章节数」勾选：禁用两个章节 spin（由 AI 判断），取消恢复。"""
        self.total_spin.setEnabled(not on)
        self.ch_spin.setEnabled(not on)

    def _start(self):
        idea = self.idea_edit.toPlainText().strip()
        if not idea:
            self.hint.setText("请先描述你想写什么小说（一句话也行）。")
            return
        if self._worker is None:
            self._worker = _BookWorker()
            self._worker.log.connect(self._on_log)
            self._worker.progress.connect(self._on_progress)
            self._worker.project_ready.connect(self._on_project_ready)
            self._worker.done.connect(self._on_done)
        self._log_items = []
        self.log_view.clear()
        self.hint.setText("一键成书进行中：可随时点「停止」，停后项目已在书架里。")
        self.start_btn.setEnabled(False)
        self.continue_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("正在立项…")
        chapters = self.ch_spin.value()
        total_chapters = self.total_spin.value()
        book_title = self.title_edit.text().strip()
        auto_chapters = self.auto_chk.isChecked()
        set_running(True)
        _sv = self._current_style_values()
        threading.Thread(target=self._worker.run,
                         args=(idea, chapters, total_chapters, None,
                               _sv["note"], _sv["break_style"], _sv["style_ref"],
                               _sv["main_prompt"], _sv["writer_prompt"]),
                         kwargs={"book_title": book_title,
                                 "scene_cards_active": list(_sv["scene_cards"]),
                                 "auto_chapters": auto_chapters},
                         daemon=True).start()

    def _continue(self):
        """v0.72 继续写：在上一轮一键成书创建的项目上，从断点自动连写剩余章节。"""
        if not self._last_dir:
            self.hint.setText("还没有可继续的项目——先「开始一键成书」从头创建。")
            return
        store = storage.ProjectStore(self._last_dir)
        project = store.load_project()
        if project is None:
            self.hint.setText("✖ 之前的项目已不存在，无法继续。")
            self.continue_btn.setEnabled(False)
            self._last_dir = None
            return
        cur = max(0, int(project.state.get("next_chapter", 1)) - 1)
        target = max(cur + 1, self.ch_spin.value())
        if target <= cur:
            self.hint.setText("《%s》已写到第 %d 章——把「本次一键生成到」设得比当前进度大即可继续写。"
                              % (project.title, cur))
            return
        ret = QMessageBox.question(
            self, "继续写",
            "将在《%s》上从第 %d 章继续自动连写，一直写到第 %d 章。\n\n"
            "（不会重新立项、不会覆盖已写章节；可随时「停止」。）\n\n确定继续吗？"
            % (project.title, cur + 1, target))
        if ret != QMessageBox.StandardButton.Yes:
            return
        if self._worker is None:
            self._worker = _BookWorker()
            self._worker.log.connect(self._on_log)
            self._worker.progress.connect(self._on_progress)
            self._worker.project_ready.connect(self._on_project_ready)
            self._worker.done.connect(self._on_done)
        self._log_items = []
        self.log_view.clear()
        self.hint.setText("继续写进行中：在《%s》上从第 %d 章连写到第 %d 章…"
                          % (project.title, cur + 1, target))
        self.start_btn.setEnabled(False)
        self.continue_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("正在续写…")
        set_running(True)
        threading.Thread(target=self._worker.run,
                         args=("", target, 0, self._last_dir), daemon=True).start()

    def _stop(self):
        if self._worker is not None:
            # 立即停止：置停止事件 + 主动 close 在途 LLM 请求连接（流式读取立刻抛 StopRequested），
            # 不再等当前章写完（与生成页 _auto_stop 的「立即中断」语义一致）
            import llm as _llm_abort
            self._worker.stop()
            _llm_abort.abort_active_resps()
            self.stop_btn.setEnabled(False)
            self.stop_btn.setText("正在停止…")
            self.hint.setText("正在停止…立即中断当前请求（已完成的章节保留在书架）。")


class AutoBookDialog(QDialog):
    """一键成书独立窗口（包装 BookPanel，供需要弹窗的入口使用）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("✨ 一键成书（AI 自动立项 + 全自动连写）")
        self.setMinimumWidth(680)
        self.resize(780, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.panel = BookPanel(self, show_title=True)
        lay.addWidget(self.panel)