# -*- coding: utf-8 -*-
"""小说导入成项目（v0.54 PC 端）：把一本 txt 小说「还原」成一个星火笔项目。

与一键成书面板同构：内嵌后台线程 + 信号桥（不占全局 running 锁），
进度用独立进度条 + 日志文本框展示。流程：
  选择 txt → 解析预览（卷/章/字数）→ 书名 → 选项（保存拆书风格/生成设定与角色卡/导入章节正文）
  → 开始导入（解析→拆书→设定合成→逐块人物抽取→角色卡→落库）→ 完成后项目进书架。
"""
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

import book_break
import config
import novel_import
from gui_app import APP, bus, set_running
from gui_break import BreakSettingsBox
from gui_theme import T


class _ImportWorker(QObject):
    """小说导入成项目的后台线程载体：全流程 + 信号回传日志/进度/结果。

    v0.55：断点续传（job 目录落盘各环节中间结果，中断/退出后对同一文本自动续传）；
    停止即立即中断当前 LLM 请求（llm.set_abort），清理未完成内容，已落盘中间结果保留。
    """

    log = Signal(str, str)         # (kind, msg)
    progress = Signal(str, int, int)  # (stage, done, total)
    done = Signal(object)          # {"ok", "dir", "title", "stats"} 或 {"ok":False,"error"}

    def __init__(self):
        super().__init__()
        self._stop = threading.Event()
        self._job_dir = None

    def stop(self):
        self._stop.set()
        # 立即停止：主动 close 在途 LLM 请求连接（流式读取立刻抛 StopRequested），不再等当前导入环节结束
        import llm
        llm.abort_active_resps()

    def _resumed(self, job_dir):
        if not job_dir:
            return False
        import os
        if os.path.exists(os.path.join(job_dir, "done.json")):
            return False
        return (os.path.exists(os.path.join(job_dir, "meta.json"))
                or os.path.isdir(os.path.join(job_dir, "chunks"))
                or os.path.isdir(os.path.join(job_dir, "cards"))
                or os.path.exists(os.path.join(job_dir, "settings.json")))

    def run(self, text, title, restart=False):
        import llm
        llm.set_abort(self._stop)
        try:
            def sink(kind, msg):
                self.log.emit(kind, msg)

            def progress(stage, done, total):
                self.progress.emit(stage, done, total)

            job_dir = None
            if restart:
                # v0.69 重新开始：不做断点续传，全部重来
                self.log.emit("info", "重新开始导入：已清除上次进度，全部重来（不再续传）…")
            else:
                settings = book_break.break_settings()
                job_dir = book_break.job_dir_for(text, settings, title, label="import")
                if self._resumed(job_dir):
                    self.log.emit("info", "检测到未完成的小说导入任务，自动续传（跳过已完成环节）…")
            importer = novel_import.NovelImporter(
                log=sink, stop_check=lambda: self._stop.is_set(),
                settings=settings)
            try:
                result = importer.run(text, title, None, progress_cb=progress,
                                      job_dir=job_dir)
            except llm.StopRequested:
                result = {"ok": False, "error": "已停止"}
            if result.get("ok"):
                # 完成后切为新项目并刷新书架
                APP["project_dir"] = result.get("dir") or APP["project_dir"]
                bus.projectChanged.emit()
                if job_dir:
                    book_break.rm_job(job_dir)
            self.done.emit(result)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.done.emit({"ok": False, "error": "导入失败：%s" % e})
        finally:
            llm.set_abort(None)


class ImportPanel(QWidget):
    """小说导入成项目面板（v0.54 独立 UI）：txt → 完整项目还原，可停止。

    既可作为项目页的独立 tab 页嵌入（与「新建项目」「一键成书」平级），也可包进对话框使用。
    """

    def __init__(self, parent=None, show_title=True):
        super().__init__(parent)
        self._worker = None
        self._text = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(10)

        if show_title:
            tip = QLabel("<h3 style='margin:0;'>📥 小说导入成项目（把 txt 小说还原成完整项目）</h3>"
                         "选择一本 txt 小说，AI 自动：拆书（世界观/重要设定/剧情推动与伏笔技法）→ "
                         "按章节梳理人物与文风 → 建立角色卡（含分章状态轨迹）→ 章节正文原样入库。\n"
                         "还原后的项目与逐章生成的项目完全一致：可继续续写/改设定/重写章节；"
                         "删除章节后，角色卡会自动回退到对应章节。")
        else:
            tip = QLabel("选择一本 txt 小说，AI 自动：拆书（世界观/重要设定/剧情推动与伏笔技法）→ "
                         "按章节梳理人物与文风 → 建立角色卡（含分章状态轨迹）→ 章节正文原样入库。\n"
                         "还原后的项目与逐章生成的项目完全一致：可继续续写/改设定/重写章节；"
                         "删除章节后，角色卡会自动回退到对应章节。")
        tip.setWordWrap(True)
        tip.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lay.addWidget(tip)

        brow = QHBoxLayout()
        self.pick_btn = QPushButton("选择小说 txt…")
        self.pick_btn.setObjectName("primary")
        self.pick_btn.clicked.connect(self._pick_file)
        brow.addWidget(self.pick_btn)
        self.parse_info = QLabel("尚未选择文件。支持超长小说（数千章），会自动分卷分章分析。")
        self.parse_info.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        self.parse_info.setWordWrap(True)
        brow.addWidget(self.parse_info, 1)
        lay.addLayout(brow)

        nrow = QHBoxLayout()
        nrow.addWidget(QLabel("小说书名（作为项目名）"))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("留空则用文件标题/自动书名")
        self.title_edit.setMinimumWidth(280)
        nrow.addWidget(self.title_edit, 1)
        lay.addLayout(nrow)

        # ---------- 导入设置（拆书参数三档模式：与拆书工坊同款组件；小说规划/整体介绍专属） ----------
        set_lay = QVBoxLayout()
        set_lay.setContentsMargins(0, 0, 0, 0)
        set_lay.setSpacing(6)
        self.settings_box = BreakSettingsBox()
        set_lay.addWidget(self.settings_box)
        # 小说规划（整体介绍）：导入的大多是未完成的小说——把剧情设计/方向/主题/已有情节
        # 告诉 AI，拆书/逐章梳理人物/管理笔记时都会参考，防止因情节缺失被带偏、跑题
        srow2 = QHBoxLayout()
        srow2.addWidget(QLabel("小说规划（整体介绍，可选；导入的大多是未完成的小说，建议填）"))
        srow2.addStretch(1)
        self.save_set_btn = QPushButton("保存导入设置")
        self.save_set_btn.clicked.connect(self._save_import_settings)
        srow2.addWidget(self.save_set_btn)
        set_lay.addLayout(srow2)
        srow3 = QHBoxLayout()
        self.intro_edit = QPlainTextEdit()
        self.intro_edit.setMaximumHeight(64)
        self.intro_edit.setPlaceholderText(
            "介绍这本小说的整体情况：剧情设计 / 故事方向 / 主题 / 已有情节到哪 / 打算怎么发展 / 重要设定等。\n"
            "例：修仙宗门仙路争锋文，主角是剑宗弃徒，前 20 章已写完主角入狱的起因，"
            "后续打算写他靠一把残剑逆袭宗门；主题是「剑心即本心」；"
            "主线伏笔是残剑来历与师父失踪之谜。\n"
            "AI 在拆书、逐章梳理人物、做管理笔记时都会参考，避免因情节缺失被带偏、跑题。")
        srow3.addWidget(self.intro_edit, 1)
        set_lay.addLayout(srow3)
        lay.addLayout(set_lay)
        self._load_import_settings()

        brow2 = QHBoxLayout()
        brow2.addStretch(1)
        self.start_btn = QPushButton("开始导入成项目")
        self.start_btn.setObjectName("primary")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start)
        brow2.addWidget(self.start_btn)
        self.stop_btn = QPushButton("■ 停止")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.setToolTip("立即停止（中断当前请求）；已完成的拆书/分析结果已落盘，"
                                 "下次对同一文本点「开始」自动续传")
        self.stop_btn.clicked.connect(self._stop)
        brow2.addWidget(self.stop_btn)
        # v0.69 重新开始导入：清空进度全部重来（不做断点续传）
        self.restart_btn = QPushButton("重新开始导入")
        self.restart_btn.setToolTip("清除本次 txt 的导入进度，从头重新导入（不再续传）")
        self.restart_btn.setEnabled(False)
        self.restart_btn.clicked.connect(self._ask_restart)
        brow2.addWidget(self.restart_btn)
        lay.addLayout(brow2)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("就绪")
        self.progress_bar.setVisible(False)
        lay.addWidget(self.progress_bar)

        self.log_view = QTextBrowser()
        self.log_view.setOpenExternalLinks(False)
        lay.addWidget(self.log_view, 1)

        self.hint = QLabel("")
        self.hint.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lay.addWidget(self.hint)

        self._log_items = []
        self._worker = _ImportWorker()
        self._worker.log.connect(self._on_log)
        self._worker.progress.connect(self._on_progress)
        self._worker.done.connect(self._on_done)

    # ---------- 内部 ----------
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

    def _on_progress(self, stage, done, total):
        total = max(1, total)
        labels = {"parse": "解析", "break": "拆书", "settings": "设定合成",
                  "chunks": "人物抽取", "cards": "角色卡", "summary": "管理笔记",
                  "write": "落库"}
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(min(done, total))
        if stage in ("chunks", "cards"):
            self.progress_bar.setFormat("%s %d/%d" % (labels.get(stage, stage), done, total))
        else:
            self.progress_bar.setFormat(labels.get(stage, stage))

    def _load_import_settings(self):
        """从 config 回填导入设置（拆书参数三档组件 + 小说规划；API 配置在设置页用途分工选）。"""
        try:
            self.settings_box.load()
            s = book_break.break_settings()
            self.intro_edit.setPlainText(str(s.get("import_intro") or ""))
        except Exception:
            pass

    def _save_import_settings(self):
        """保存导入设置（拆书参数三档组件 + 小说规划；API 配置在设置页用途分工选）。"""
        s = self.settings_box.save()
        cfg = config.load_config()
        cfg["import_intro"] = self.intro_edit.toPlainText().strip()
        config.save_config(cfg)
        config._cache = None
        self.hint.setText(
            "✓ 导入设置已保存：%s模式 / 每部分 %d token%s / %s（并发 %d）%s；小说规划已更新；"
            "API 在「设置·API 配置·用途分工」选择。"
            % ({"simple": "简单", "smart": "智能", "advanced": "高级"}.get(s["mode"], "智能"),
               s["token_per_part"],
               ("，重叠 %d token" % s["overlap_token"]) if s["overlap_token"] else "",
               "并行" if s["parallel"] else "串行", s["parallel_n"],
               ("，L3 分批 %d 单元/批" % s["l3_batch"]) if s["l3_batch"] else ""))

    def _on_done(self, payload):
        self.start_btn.setEnabled(bool(self._text))
        self.restart_btn.setEnabled(bool(self._text))
        self.stop_btn.setEnabled(False)
        self.stop_btn.setText("■ 停止")
        self.progress_bar.setVisible(False)
        set_running(False)
        if payload.get("ok"):
            st = payload.get("stats") or {}
            self.hint.setText("✓ 已还原为项目《%s》：%d 卷 / %d 章 / %d 个角色，已加入书架。\n"
                              "删除章节后角色卡会自动回退到对应章节。"
                              % (payload.get("title", ""), st.get("volumes", 0),
                                 st.get("chapters", 0), st.get("characters", 0)))
            # 刷新项目页（本面板在项目页 tab）让新项目立即可见
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
        else:
            err = str(payload.get("error", "未知错误"))
            if err == "已停止":
                self.hint.setText("已停止：当前请求已中断，已完成的拆书/分析结果已保留，"
                                  "下次对同一文本点「开始」自动续传。")
            else:
                self.hint.setText("✖ " + err)
                # v0.72 失败弹窗直接给出恢复入口：继续导入（补跑）/ 重新开始 / 取消
                try:
                    mb = QMessageBox(self)
                    mb.setWindowTitle("导入未完成")
                    mb.setText("导入未全部完成：\n%s\n\n接下来怎么处理？" % err)
                    b_go = mb.addButton("继续导入（只补跑失败环节）",
                                        QMessageBox.ButtonRole.AcceptRole)
                    b_rst = mb.addButton("重新开始导入（清空进度从头来）",
                                         QMessageBox.ButtonRole.DestructiveRole)
                    mb.addButton("取消", QMessageBox.ButtonRole.RejectRole)
                    mb.exec()
                    clicked = mb.clickedButton()
                    if clicked is b_go:
                        self._start(restart=False)
                    elif clicked is b_rst:
                        self._start(restart=True)
                except Exception:
                    pass
        self._worker = None

    def _pick_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择要导入的小说 txt", "", "小说文本 (*.txt *.md);;所有文件 (*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            self.hint.setText("✖ 读取文件失败：%s" % e)
            return
        if not (text or "").strip():
            self.hint.setText("✖ 文件内容为空。")
            return
        self._text = text
        parsed = book_break.parse_novel_full(text)
        vols = parsed["volumes"] or []
        if vols:
            self.parse_info.setText("已选择：%s\n共 %d 卷 / %d 章 / %.1f 万字，可开始导入成项目。"
                                    % (path.rsplit("\\", 1)[-1], len(vols),
                                       parsed["total_chapters"], parsed["total_chars"] / 10000))
            self.start_btn.setEnabled(True)
            base = path.rsplit("\\", 1)[-1].rsplit(".", 1)[0].strip()
            if base and not self.title_edit.text().strip():
                self.title_edit.setText(base)
        else:
            self.parse_info.setText("未能解析出章节：文件可能不是带章节标题的小说文本。")
            self.start_btn.setEnabled(False)

    def _start(self, restart=False):
        if not self._text:
            self.hint.setText("请先选择小说 txt。")
            return
        # 界面看到什么，跑起来就用什么：先把拆书参数与小说规划写回 config
        self.settings_box.save()
        cfg = config.load_config()
        cfg["import_intro"] = self.intro_edit.toPlainText().strip()
        config.save_config(cfg)
        config._cache = None
        if self._worker is None:
            self._worker = _ImportWorker()
            self._worker.log.connect(self._on_log)
            self._worker.progress.connect(self._on_progress)
            self._worker.done.connect(self._on_done)
        self._log_items = []
        self.log_view.clear()
        title = self.title_edit.text().strip()
        self.hint.setText("导入进行中（解析 → 拆书 → 设定合成 → 人物抽取 → 角色卡 → 管理笔记 → 落库），"
                          "可随时点「停止」（立即中断，下次自动续传）。")
        self.start_btn.setEnabled(False)
        self.restart_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_bar.setVisible(True)
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("准备中…")
        set_running(True)
        threading.Thread(target=self._worker.run,
                         args=(self._text, title, restart), daemon=True).start()

    def _ask_restart(self):
        """v0.69 重新开始导入：清空进度全部重来（不做断点续传）。"""
        from gui_app import busy_guard
        if busy_guard(self):
            return
        ret = QMessageBox.question(
            self, "重新开始导入",
            "将清除本次 txt 的导入进度，从头重新导入（不再续传）。\n\n确定继续吗？")
        if ret == QMessageBox.StandardButton.Yes:
            self._start(restart=True)

    def _stop(self):
        if self._worker is not None:
            self._worker.stop()
            self.stop_btn.setEnabled(False)
            self.stop_btn.setText("正在停止…")
            self.hint.setText("正在停止（立即中断当前请求）…")


class ImportDialog(QDialog):
    """小说导入成项目独立窗口（包装 ImportPanel，供需要弹窗的入口使用）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📥 小说导入成项目")
        self.setMinimumWidth(680)
        self.resize(780, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.panel = ImportPanel(self, show_title=True)
        lay.addWidget(self.panel)
