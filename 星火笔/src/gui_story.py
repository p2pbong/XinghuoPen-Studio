# -*- coding: utf-8 -*-
"""故事页：章节目录阅读 / 伏笔台账 / 生成日志 / 分支存档（if 线）。"""
import html
import os
import re
import threading

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QMessageBox, QPushButton,
                               QSpinBox, QTableWidget, QTableWidgetItem,
                               QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

import storage
import prompts
from gui_app import APP, busy_guard, current_project, engine_for, log_fn
from gui_generate import ChapterManagerDialog
from gui_theme import icon, T

_CHAPTER_RE = re.compile(r"^\s*第\s*[0-9一二三四五六七八九十百千万零两]+\s*章")


def _chapter_meta_html(chapter, store):
    """章节阅读时的元信息块：剧情点（主AI规划）/ 主AI审查结论 / 写后校对说明。

    这些记录存在章节 reasoning 里（打磨章节的关键上下文），阅读时一并展示。
    无记录返回空串。
    """
    reasoning = chapter.reasoning or {}
    lines = []
    cons = reasoning.get("consolidation") or {}
    pnote = str(cons.get("planning_note") or "").strip()
    if pnote:
        lines.append("本章意图（框架裁定）：%s" % pnote)
    # v1.32 选卡可见性：展示主AI本章选中/未选的情景规则卡（问题：运行记录看不到用了哪张卡）
    _sc_sel = [str(x).strip() for x in (cons.get("scene_cards") or []) if str(x).strip()]
    _sc_new = [str((x or {}).get("name") or "").strip()
               for x in (cons.get("new_scene_cards") or []) if isinstance(x, dict)]
    if _sc_sel or _sc_new:
        _sc_txt = "、".join(_sc_sel)
        if _sc_new:
            _sc_txt += ("（主AI自做：" + "、".join(_sc_new) + "）" if _sc_txt else "主AI自做：" + "、".join(_sc_new))
        lines.append("本章情景卡（写法参考）：%s" % _sc_txt)
    else:
        lines.append("本章情景卡：未选用（平淡铺垫/无匹配情景，按常规叙事）")
    beats = reasoning.get("beats") or []
    if beats:
        lines.append("本章剧情点（主AI规划）：%s"
                     % "　".join("①%s" % b for b in beats))
    review = reasoning.get("review") or {}
    if review:
        approved = str(review.get("approved")).strip().lower() == "true"
        r = "主AI审查：%s" % ("通过" if approved else "未通过（已自动重写）")
        issues = [str(x) for x in (review.get("issues") or []) if str(x).strip()][:4]
        if issues:
            r += "；问题：%s" % "；".join(issues)
        if review.get("pacing"):
            r += "；节奏：%s" % review["pacing"]
        sc = review.get("scores") or {}
        if sc:
            r += "；评分：沉浸%s/节奏%s/爽点%s/人设%s/自然%s" % (
                sc.get("immersion", "—"), sc.get("rhythm", "—"),
                sc.get("payout", "—"), sc.get("character", "—"),
                sc.get("natural", "—"))
        lines.append(r)
    cliches = [str(x) for x in (review.get("cliches") or []) if str(x).strip()]
    if cliches:
        lines.append("套路检测：%s" % "；".join(cliches[:4]))
    proof = reasoning.get("proofread") or {}
    notes = [str(x) for x in (proof.get("notes") or []) if str(x).strip()][:4]
    if notes:
        lines.append("写后校对：%s" % "；".join(notes))
    deai = reasoning.get("deai_report") or {}
    if deai:
        grade = deai.get("grade") or ""
        hits = deai.get("hits")
        lines.append("AI八股治理：命中 %s 处%s" % (
            hits if hits is not None else "?",
            "（等级：%s）" % grade if grade else ""))
    if not lines:
        return ""
    return (T("<div style='color:#8a93a3;font-size:12px;line-height:1.7;margin-bottom:8px;'>")
            + "<br>".join(html.escape(l) for l in lines) + "</div>")


def parse_novel_txt(text):
    """把完整小说 txt 按「第N章」标题拆分为 [{title, content}]；无标题则整篇一章。"""
    chapters = []
    cur = None
    for ln in (text or "").split("\n"):
        if _CHAPTER_RE.match(ln):
            if cur and cur["content"].strip():
                chapters.append(cur)
            cur = {"title": ln.strip(), "content": ""}
        else:
            if cur is not None:
                cur["content"] += ln + "\n"
    if cur and cur["content"].strip():
        chapters.append(cur)
    if not chapters and (text or "").strip():
        chapters.append({"title": "", "content": (text or "").strip()})
    return chapters


def chapters_from_folder(folder):
    """从分章文件夹（每章一个 txt，文件名带章节序号）导入为 [{title, content}]。"""
    import os
    files = [f for f in os.listdir(folder) if f.lower().endswith(".txt")]

    def num_key(fn):
        m = re.search(r"(\d+)", fn)
        return int(m.group(1)) if m else 10 ** 9

    files.sort(key=num_key)
    out = []
    for fn in files:
        try:
            with open(os.path.join(folder, fn), encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue
        title = re.sub(r"^第?\s*\d+\s*章?[\s_\-—]+", "", os.path.splitext(fn)[0]).strip() \
            or os.path.splitext(fn)[0]
        lines = content.split("\n")
        if lines and (lines[0].strip() == title or _CHAPTER_RE.match(lines[0])):
            lines = lines[1:]
        if lines and lines[0].strip().startswith("-" * 3):
            lines = lines[1:]
        body = "\n".join(lines).strip()
        if body:
            out.append({"title": title, "content": body})
    return out


def export_novel(parent):
    """导出当前项目小说：同时生成 ①完整拼接 txt 与 ②分章文件夹（每章一个 txt）。

    供故事页工具栏与「章节管理」对话框共用（章节管理里也能直接导出）。
    """
    store, project = current_project()
    if not project:
        QMessageBox.warning(parent, "提示", "请先载入项目。")
        return
    indices = store.list_chapter_indices()
    if not indices:
        QMessageBox.warning(parent, "提示", "还没有已写章节可导出。")
        return
    from PySide6.QtWidgets import QFileDialog
    import export_utils
    path, _ = QFileDialog.getSaveFileName(
        parent, "导出小说（完整txt + 分章文件夹）", export_utils.default_novel_path(project.title),
        "文本文件 (*.txt)")
    if not path:
        return
    # ① 完整拼接 txt（原逻辑：设定/风格/全部章节/日志）
    lines = ["%s" % project.title, "=" * 40, ""]
    if (project.story_style or "").strip():
        lines += ["【主AI风格】%s" % project.story_style, ""]
    if (project.story_brief or "").strip():
        lines += ["【故事设定】%s" % project.story_brief, ""]
    last_vol = None
    for i in indices:
        ch = store.load_chapter(i)
        if not ch:
            continue
        vol = int(getattr(ch, "volume", 1) or 1)
        if vol != last_vol:
            last_vol = vol
            lines += ["", "═" * 24, "第 %d 卷" % vol, "═" * 24, ""]
        lines += ["", "%s" % ch.title, "-" * 30, ch.content, ""]
    log_text = store.read_log(300)
    if log_text.strip():
        lines += ["", "=" * 40, "【生成日志】", log_text]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    # ② 分章文件夹：同目录 <文件名>_分章/ 按卷分子目录、每章一个 txt
    base, _ext = os.path.splitext(path)
    folder = base + "_分章"
    os.makedirs(folder, exist_ok=True)
    for i in indices:
        ch = store.load_chapter(i)
        if not ch:
            continue
        safe = re.sub(r'[\\/:*?"<>|\n\r]+', "_", ch.title or "第%d章" % i).strip()
        if not safe:
            safe = "第%d章" % i
        vol_dir = os.path.join(folder, "第%d卷" % int(getattr(ch, "volume", 1) or 1))
        os.makedirs(vol_dir, exist_ok=True)
        with open(os.path.join(vol_dir, "第%03d章_%s.txt" % (i, safe)),
                  "w", encoding="utf-8") as f:
            f.write("%s\n%s\n\n%s\n" % (ch.title or "第%d章" % i, "-" * 30, ch.content))
    log_fn("info", "已导出小说：完整版 %s；分章版 %s（%d 章，按卷分组）" % (path, folder, len(indices)))
    QMessageBox.information(
        parent, "导出成功",
        "已同时导出两种形式（按卷分组）：\n\n"
        "① 完整版（全书拼接，卷与卷之间有分隔页）：\n%s\n\n"
        "② 分章版（文件夹内每卷一个子目录、每章一个 txt）：\n%s\n（共 %d 章，文件名按章节排序）"
        % (path, folder, len(indices)))


class StoryPage(QWidget):

    _import_done = Signal(object)   # (导入章数, 起始章号)：后台导入完成后回主线程刷新
    _timeline_ready = Signal(object)  # [(行号, 梗概), ...]：时间线旧章节梗概后台补载完成

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._import_done.connect(self._on_import_done)
        self._timeline_ready.connect(self._on_timeline_ready)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        tool = QHBoxLayout()
        tool.addWidget(QLabel("故事档案"))
        tool.addStretch(1)
        manage_btn = QPushButton("章节管理")
        manage_btn.setToolTip("阅读 / 编辑 / 删除已归档章节")
        manage_btn.clicked.connect(self._manage_chapters)
        import_btn = QPushButton("导入章节")
        import_btn.setToolTip("把已有正文导入为正式章节：完整 txt（按「第N章」拆分）或分章文件夹（每章一个 txt）")
        import_btn.clicked.connect(self._import_chapters)
        self.import_btn = import_btn
        export_btn = QPushButton("导出小说为文本")
        export_btn.clicked.connect(self._export_novel)
        epub_btn = QPushButton("导出 EPUB")
        epub_btn.setToolTip("导出为 EPUB3 电子书（手机/阅读器可直接打开阅读）")
        epub_btn.clicked.connect(self._export_epub)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh_all)
        tool.addWidget(manage_btn)
        tool.addWidget(import_btn)
        tool.addWidget(export_btn)
        tool.addWidget(epub_btn)
        tool.addWidget(refresh_btn)
        lay.addLayout(tool)

        split = QHBoxLayout()
        split.setSpacing(12)

        # 左侧：章节目录
        self.ch_list = QListWidget()
        self.ch_list.setFixedWidth(240)
        self.ch_list.currentRowChanged.connect(self._view_chapter)
        split.addWidget(self.ch_list)

        # 右侧：正文（跟随全局缩放主题的字号）
        self.ch_view = QTextBrowser()
        split.addWidget(self.ch_view, 1)
        # 正文占 60%、下方页签占 40%：阅读不憋屈
        lay.addLayout(split, 3)

        # 下方：伏笔 + 管理笔记 + 日志
        tabs = QTabWidget()
        # 伏笔看板：统计栏（待回收/已回收/逾期/回收率）+ 一键回收 + 逾期标红
        fore_box = QWidget()
        fore_lay = QVBoxLayout(fore_box)
        fore_lay.setContentsMargins(6, 8, 6, 6)
        fore_lay.setSpacing(6)
        fore_top = QHBoxLayout()
        self.fore_stats = QLabel("伏笔统计：—")
        self.fore_stats.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        fore_top.addWidget(self.fore_stats)
        fore_top.addStretch(1)
        self.fore_resolve_btn = QPushButton("标记已回收")
        self.fore_resolve_btn.setObjectName("primary")
        self.fore_resolve_btn.setToolTip("把选中的「待回收」伏笔标记为已回收（记录回收章）")
        self.fore_resolve_btn.clicked.connect(self._fore_resolve)
        self.fore_reopen_btn = QPushButton("恢复待回收")
        self.fore_reopen_btn.setToolTip("把选中的「已回收」伏笔恢复为待回收（误标时找回）")
        self.fore_reopen_btn.clicked.connect(self._fore_reopen)
        fore_top.addWidget(self.fore_resolve_btn)
        fore_top.addWidget(self.fore_reopen_btn)
        fore_lay.addLayout(fore_top)
        self.fore_table = QTableWidget(0, 5)
        self.fore_table.setAlternatingRowColors(True)
        self.fore_table.setHorizontalHeaderLabels(["状态", "类型", "内容", "依托角色", "埋设/回收章"])
        self.fore_table.horizontalHeader().setStretchLastSection(True)
        self.fore_table.verticalHeader().setVisible(False)
        self.fore_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        fore_lay.addWidget(self.fore_table, 1)
        fore_hint = QLabel("逾期 = 埋设后超过 %d 章未回收（长篇「欠账」，主AI决断/校验/审查会优先提醒回收；"
                           "阈值可在设置页·高级设置调整）。选中行可直接点「标记已回收」。"
                           % prompts._foreshadow_overdue_chapters())
        fore_hint.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        fore_hint.setWordWrap(True)
        fore_lay.addWidget(fore_hint)
        tabs.addTab(fore_box, "伏笔台账")

        # 时间线：按章事件流（章号/标题/状态/字数/梗概/伏笔埋收），大项目毫秒级出列、梗概后台补载
        tl_box = QWidget()
        tl_lay = QVBoxLayout(tl_box)
        tl_lay.setContentsMargins(6, 8, 6, 6)
        tl_lay.setSpacing(6)
        tl_hint = QLabel("全书时间线：按章节顺序列出剧情梗概与伏笔埋设/回收节点，一眼看进度与事件流；"
                         "「埋/收」标记 = 该章埋设/回收的伏笔。")
        tl_hint.setWordWrap(True)
        tl_hint.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        tl_lay.addWidget(tl_hint)
        # v0.51 分卷：工具行（分卷管理对话框：归卷/卷合并/卷分布）
        tl_row = QHBoxLayout()
        self.vol_btn = QPushButton("分卷管理")
        self.vol_btn.setIcon(icon("journal-text", 14))
        self.vol_btn.setIconSize(QSize(14, 14))
        self.vol_btn.setToolTip("分卷 = 章节归入第几卷（时间线按卷分组展示）。\n"
                                "操作：先在时间线选中某章 → 此对话框输卷号归卷；"
                                "或把整卷合并到另一卷（如第 2 卷并入第 3 卷）。\n"
                                "导出 TXT/EPUB 时会按卷分组。")
        self.vol_btn.clicked.connect(self._manage_volumes)
        tl_row.addWidget(self.vol_btn)
        tl_row.addStretch(1)
        tl_lay.addLayout(tl_row)
        self.timeline_table = QTableWidget(0, 6)
        self.timeline_table.setAlternatingRowColors(True)
        self.timeline_table.setHorizontalHeaderLabels(
            ["章号", "标题", "状态", "字数", "剧情梗概", "伏笔（埋/收）"])
        self.timeline_table.horizontalHeader().setStretchLastSection(True)
        self.timeline_table.verticalHeader().setVisible(False)
        self.timeline_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # 窄列固定宽度，梗概列伸展
        self.timeline_table.setColumnWidth(0, 56)
        self.timeline_table.setColumnWidth(2, 70)
        self.timeline_table.setColumnWidth(3, 64)
        tl_lay.addWidget(self.timeline_table, 1)
        tabs.addTab(tl_box, "时间线")

        self.summary_view = QTextBrowser()
        tabs.addTab(self.summary_view, "主AI管理笔记")

        self.kb_view = QTextBrowser()
        tabs.addTab(self.kb_view, "主AI知识库")

        self.log_view = QTextBrowser()
        tabs.addTab(self.log_view, "生成日志")

        # 分支存档（if 线）
        btab = QWidget()
        blat = QVBoxLayout(btab)
        blat.setContentsMargins(6, 8, 6, 6)
        blat.setSpacing(8)
        btip = QLabel(
            "分支 = 当前项目的完整存档（设定/进度/角色卡与信息库/全部章节/伏笔）。"
            "用于「剧情分歧（if 线）」：\n"
            "① 关键抉择点前点「保存当前为分支」留一条线；② 继续写另一条线；"
            "③ 任何时候点「载入此分支」整体切回，随时来回切换不污染主线。\n"
            "载入会替换当前项目内容——未存档的当前线会丢失，切换前记得先保存。")
        btip.setWordWrap(True)
        btip.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        blat.addWidget(btip)
        row = QHBoxLayout()
        row.addWidget(QLabel("分支名"))
        self.branch_name = QLineEdit()
        self.branch_name.setPlaceholderText("例：选择救青梅 / 选择救发小")
        save_branch_btn = QPushButton("保存当前为分支")
        save_branch_btn.setObjectName("primary")
        save_branch_btn.clicked.connect(self._save_branch)
        row.addWidget(self.branch_name, 1)
        row.addWidget(save_branch_btn)
        blat.addLayout(row)
        self.branch_list = QListWidget()
        blat.addWidget(self.branch_list, 1)
        brow = QHBoxLayout()
        load_branch_btn = QPushButton("载入此分支")
        load_branch_btn.setObjectName("primary")
        load_branch_btn.clicked.connect(self._load_branch)
        del_branch_btn = QPushButton("删除此分支")
        del_branch_btn.setObjectName("danger")
        del_branch_btn.clicked.connect(self._delete_branch)
        brow.addWidget(load_branch_btn)
        brow.addWidget(del_branch_btn)
        brow.addStretch(1)
        blat.addLayout(brow)
        tabs.addTab(btab, "分支存档")

        lay.addWidget(tabs, 2)

    def on_show(self):
        self.refresh_all()

    def _manage_chapters(self):
        """打开章节管理（阅读/编辑/删除）。"""
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        ChapterManagerDialog(self.app).exec()

    def _import_chapters(self):
        """把已有正文导入为正式章节（完整 txt 按「第N章」拆分 / 分章文件夹）。"""
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        if not busy_guard(self):
            return
        from PySide6.QtWidgets import QInputDialog, QFileDialog
        mode, ok = QInputDialog.getItem(
            self, "导入章节", "选择导入来源：",
            ["从完整 txt 导入（自动按「第N章」拆分）", "从分章文件夹导入（每章一个 txt）"],
            0, False)
        if not ok:
            return
        chapters = []
        if mode.startswith("从完整 txt"):
            path, _ = QFileDialog.getOpenFileName(self, "选择小说正文 txt", "",
                                                  "文本文件 (*.txt)")
            if not path:
                return
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except Exception as e:
                QMessageBox.warning(self, "读取失败", "无法读取文件：%s" % e)
                return
            chapters = parse_novel_txt(text)
        else:
            folder = QFileDialog.getExistingDirectory(self, "选择分章文件夹（每章一个 txt）", "")
            if not folder:
                return
            chapters = chapters_from_folder(folder)
        if not chapters:
            QMessageBox.information(
                self, "导入章节",
                "没有解析出任何章节：完整 txt 需含「第N章」标题，文件夹需含章节 txt 文件。")
            return
        nxt = int(project.state.get("next_chapter", 1))
        ret = QMessageBox.question(
            self, "确认导入",
            "解析出 %d 章，将从第 %d 章开始导入为正式章节（标题保留原文）。\n\n确定导入？"
            % (len(chapters), nxt))
        if ret != QMessageBox.StandardButton.Yes:
            return
        # 大量章节写入 + git 全仓库归档在后台线程执行，避免导入期间界面卡死
        self.import_btn.setEnabled(False)
        self.import_btn.setText("导入中…")

        target_dir = APP["project_dir"]   # 固定导入目标，避免线程启动前用户切换了项目

        def work():
            try:
                eng = engine_for(target_dir)
                n = eng.import_chapters(project, chapters)
            except Exception as e:
                log_fn("warn", "导入章节失败：%s" % e)
                n = 0
            self._import_done.emit((int(n), nxt))

        threading.Thread(target=work, daemon=True).start()

    def _on_import_done(self, payload):
        self.import_btn.setEnabled(True)
        self.import_btn.setText("导入章节")
        n, nxt = payload
        self.refresh_all()
        try:
            self.app.page_generate._update_progress()
        except Exception:
            pass
        if n:
            log_fn("info", "已导入 %d 章（第 %d-%d 章）。" % (n, nxt, nxt + n - 1))

    # ---------- 分支存档（if 线） ----------
    def _refresh_branches(self):
        store, project = current_project()
        self.branch_list.clear()
        if not project:
            return
        for b in store.list_branches():
            self.branch_list.addItem("%s（%d章 · %s）"
                                     % (b["name"], b["chapters"], b["saved_at"]))
            self.branch_list.item(self.branch_list.count() - 1).setData(
                Qt.ItemDataRole.UserRole, b["name"])
        if self.branch_list.count():
            self.branch_list.setCurrentRow(0)

    def _selected_branch(self):
        row = self.branch_list.currentRow()
        if row < 0:
            return None
        return self.branch_list.item(row).data(Qt.ItemDataRole.UserRole)

    def _save_branch(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        name = self.branch_name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请先填写分支名。")
            return
        if os.path.exists(store.branch_path(name)):
            ret = QMessageBox.question(self, "覆盖分支",
                                       "已存在同名分支《%s》，覆盖？" % name)
            if ret != QMessageBox.StandardButton.Yes:
                return
        store.save_branch(name)
        self._refresh_branches()
        log_fn("info", "分支已保存：《%s》" % name)

    def _load_branch(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        name = self._selected_branch()
        if not name:
            QMessageBox.information(self, "提示", "请先在列表中选择一个分支。")
            return
        if not busy_guard(self):
            return
        ret = QMessageBox.question(
            self, "载入分支",
            "将把当前项目整体替换为分支《%s》的状态（设定/进度/角色卡与信息库/章节/伏笔）。\n"
            "当前未存档的内容会丢失，建议先「保存当前为分支」。\n\n确定载入？" % name)
        if ret != QMessageBox.StandardButton.Yes:
            return
        data = store.load_branch(name)
        if not data:
            QMessageBox.warning(self, "提示", "分支数据缺失或已损坏。")
            return
        store.apply_branch(data, name)
        # 刷新各页与当前分支列表
        self.refresh_all()
        try:
            self.app.page_generate._update_progress()
            self.app.page_project.on_show()
        except Exception:
            pass
        log_fn("info", "已载入分支：《%s》。" % name)

    def _delete_branch(self):
        store, project = current_project()
        if not project:
            return
        name = self._selected_branch()
        if not name:
            QMessageBox.information(self, "提示", "请先在列表中选择一个分支。")
            return
        ret = QMessageBox.question(self, "删除分支",
                                   "确定删除分支《%s》？删除后不可恢复。" % name)
        if ret != QMessageBox.StandardButton.Yes:
            return
        store.delete_branch(name)
        self._refresh_branches()
        log_fn("info", "分支已删除：《%s》" % name)

    def refresh_all(self):
        store, project = current_project()
        self.ch_list.blockSignals(True)
        self.ch_list.clear()
        if project:
            for i, m in store.chapter_summaries():
                self.ch_list.addItem("第%d章·%s" % (i, m["title"]))
        self.ch_list.blockSignals(False)
        self._fill_foreshadows()
        self._fill_timeline()
        self._fill_summary()
        self._fill_log()
        self._refresh_branches()
        self.ch_view.setHtml("")

    def _fill_summary(self):
        store, project = current_project()
        if project and (project.story_summary or "").strip():
            self.summary_view.setPlainText(project.story_summary)
        else:
            self.summary_view.setPlainText(
                "（还没有管理笔记——每 N 章（设置页可配）或卷末主AI会自动压缩卷信息生成。\n"
                "它相当于主AI的剧情压缩卷：主线进度 / 角色现状 / 伏笔状态 / 未兑现承诺，"
                "正文AI写作时也会读到。）")
        if project and (project.story_knowledge or "").strip():
            self.kb_view.setPlainText(project.story_knowledge)
        else:
            self.kb_view.setPlainText(
                "（知识库为空——主AI会把联网搜索的灵感、重要设定确认、关键伏笔落定等"
                "值得长期记住的内容记在这里，只有主AI读取，正文AI看不到。）")

    def _fill_foreshadows(self):
        store, project = current_project()
        self.fore_table.setRowCount(0)
        if not project:
            self.fore_stats.setText("伏笔统计：—")
            return
        fs = store.load_foreshadows()
        current_no = project.written_chapters()
        self.fore_table.setRowCount(len(fs))
        n_open = n_done = n_over = 0
        for r, f in enumerate(fs):
            if f.status == "resolved":
                st, color = "✓ 已回收", T("#7d8b99")
                n_done += 1
            elif prompts._overdue_mark(f, current_no):
                st, color = "⚠ 逾期", T("#e06c5a")
                n_over += 1
                n_open += 1
            else:
                st, color = "🕳 开放", T("#8a93a3")
                n_open += 1
            ft = {"plant": "埋设", "payoff": "回收", "echo": "呼应"}.get(f.f_type, f.f_type)
            for col, val in ((0, st), (1, ft), (2, f.text), (3, f.target_char or "—"),
                             (4, "%d / %s" % (f.planted_chapter, f.resolved_chapter or "—"))):
                item = QTableWidgetItem(val)
                if col == 0:
                    item.setForeground(QColor(color))
                self.fore_table.setItem(r, col, item)
        total = n_open + n_done
        rate = ("%.0f%%" % (n_done * 100.0 / total)) if total else "—"
        self.fore_stats.setText(
            "伏笔统计：待回收 %d · 已回收 %d · ⚠逾期 %d · 回收率 %s（%d/%d）"
            % (n_open, n_done, n_over, rate, n_done, total))

    def _selected_foreshadows(self, status):
        """返回表格中选中行、且状态与 status 匹配的伏笔列表。"""
        store, project = current_project()
        if not project:
            return []
        fs = store.load_foreshadows()
        rows = sorted(r.row() for r in self.fore_table.selectedIndexes())
        rows = list(dict.fromkeys(rows))
        out = []
        for r in rows:
            if 0 <= r < len(fs) and fs[r].status == status:
                out.append(fs[r])
        return out

    def _fore_resolve(self):
        """把选中的待回收伏笔标记为已回收（记录回收章 = 当前已写章节）。"""
        store, project = current_project()
        if not project:
            return
        sel = self._selected_foreshadows("open")
        if not sel:
            QMessageBox.information(self, "提示", "请先选中「待回收」的伏笔行。")
            return
        if QMessageBox.question(
                self, "确认回收",
                "将下列 %d 条伏笔标记为已回收（记录回收章为当前进度）？\n%s"
                % (len(sel), "\n".join("· %s" % f.text[:40] for f in sel[:5])) +
                ("\n…等" if len(sel) > 5 else "")) != QMessageBox.StandardButton.Yes:
            return
        fs = store.load_foreshadows()
        resolved_ch = max(1, project.written_chapters())
        sel_ids = {f.id for f in sel}   # load_foreshadows 每次新建对象，按 id 匹配
        for f in fs:
            if f.status == "open" and f.id in sel_ids:
                f.status = "resolved"
                f.resolved_chapter = resolved_ch
        store.save_foreshadows(fs)
        self._fill_foreshadows()
        log_fn("info", "已手动回收 %d 条伏笔。" % len(sel))

    def _fore_reopen(self):
        """把选中的已回收伏笔恢复为待回收（误标找回）。"""
        store, project = current_project()
        if not project:
            return
        sel = self._selected_foreshadows("resolved")
        if not sel:
            QMessageBox.information(self, "提示", "请先选中「已回收」的伏笔行。")
            return
        fs = store.load_foreshadows()
        sel_ids = {f.id for f in sel}
        for f in fs:
            if f.status == "resolved" and f.id in sel_ids:
                f.status = "open"
                f.resolved_chapter = 0
        store.save_foreshadows(fs)
        self._fill_foreshadows()
        log_fn("info", "已恢复 %d 条伏笔为待回收。" % len(sel))

    def _fill_log(self):
        store, project = current_project()
        if project:
            text = store.read_log(500)
        else:
            text = ""
        self.log_view.setPlainText(text)

    # ---------- 时间线（按章事件流） ----------
    def _fill_timeline(self):
        store, project = current_project()
        self.timeline_table.setRowCount(0)
        if not project:
            return
        summaries = store.chapter_summaries()
        # v0.51 分卷：按卷插入卷头行；记录 (行号→章号) 供归卷对话框定位
        rows_out = []
        last_vol = None
        for i, m in summaries:
            vol = m.get("vol", 1)
            if vol != last_vol:
                last_vol = vol
                rows_out.append(("header", vol))
            rows_out.append(("ch", i, m))
        self._tl_row2seq = {r: x[1] for r, x in enumerate(rows_out) if x[0] == "ch"}
        # 伏笔埋设/回收节点：{章号: [(标记, 内容), ...]}
        fs_map = {}
        for f in store.load_foreshadows():
            if int(f.planted_chapter or 0) > 0:
                fs_map.setdefault(int(f.planted_chapter), []).append(("埋", f.text))
            if int(f.resolved_chapter or 0) > 0:
                fs_map.setdefault(int(f.resolved_chapter), []).append(("收", f.text))
        self.timeline_table.setRowCount(len(rows_out))
        missing = []
        for r, item in enumerate(rows_out):
            if item[0] == "header":
                vol = item[1]
                cnt = sum(1 for x in rows_out
                          if x[0] == "ch" and x[2].get("vol", 1) == vol)
                cell = QTableWidgetItem("第 %d 卷 · %d 章" % (vol, cnt))
                cell.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                font = cell.font()
                font.setBold(True)
                cell.setFont(font)
                cell.setForeground(QBrush(QColor(T("#e3c87f"))))
                self.timeline_table.setItem(r, 0, cell)
                self.timeline_table.setSpan(r, 0, 1, 6)
                self.timeline_table.setRowHeight(r, 30)
                continue
            i, m = item[1], item[2]
            brief = m.get("brief") or ""
            if not brief:
                missing.append((r, i))
                brief = "（梗概补载中…）"
            fs = fs_map.get(i) or []
            fs_text = "；".join("%s:%s" % (k, t[:18]) for k, t in fs) or "—"
            st = {"approved": "已归档", "draft": "草稿"}.get(m["status"], m["status"])
            vals = (str(i), m["title"], st, str(m["chars"]), brief, fs_text)
            for col, val in enumerate(vals):
                self.timeline_table.setItem(r, col, QTableWidgetItem(val))
        if missing:
            threading.Thread(target=self._load_timeline_briefs,
                             args=(missing,), daemon=True).start()

    def _manage_volumes(self):
        """分卷管理对话框：选中章节归卷 / 整卷合并 / 卷分布一览（v0.51）。"""
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        summaries = store.chapter_summaries()
        vol_map = {}
        for _i, m in summaries:
            v = m.get("vol", 1)
            vol_map[v] = vol_map.get(v, 0) + 1
        dlg = QDialog(self)
        dlg.setWindowTitle("分卷管理")
        dlg.setMinimumWidth(400)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        table = QTableWidget(len(vol_map), 2)
        table.setHorizontalHeaderLabels(["卷号", "章节数"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setStretchLastSection(True)
        for r, (v, cnt) in enumerate(sorted(vol_map.items())):
            table.setItem(r, 0, QTableWidgetItem("第 %d 卷" % v))
            table.setItem(r, 1, QTableWidgetItem(str(cnt)))
        lay.addWidget(table)
        # 归卷：先在时间线选中章节行
        sel = self.timeline_table.currentRow()
        if sel >= 0 and sel in self._tl_row2seq:
            sel_seq = self._tl_row2seq[sel]
            lay.addWidget(QLabel("时间线选中：第 %d 章（未选中则此操作无效）" % sel_seq))
        else:
            sel_seq = None
            lay.addWidget(QLabel("时间线未选中章节：归卷无效，请先在时间线点选一行。"))
        r1 = QHBoxLayout()
        vol_spin = QSpinBox()
        vol_spin.setRange(1, 999)
        vol_spin.setValue(1)
        set_btn = QPushButton("归到此卷")
        set_btn.setObjectName("primary")
        r1.addWidget(QLabel("章号 → 卷号"))
        r1.addWidget(vol_spin)
        r1.addWidget(set_btn)
        lay.addLayout(r1)
        # 整卷合并
        r2 = QHBoxLayout()
        old_spin = QSpinBox()
        old_spin.setRange(1, 999)
        new_spin = QSpinBox()
        new_spin.setRange(1, 999)
        merge_btn = QPushButton("整卷合并")
        r2.addWidget(QLabel("把第"))
        r2.addWidget(old_spin)
        r2.addWidget(QLabel("卷并入第"))
        r2.addWidget(new_spin)
        r2.addWidget(QLabel("卷"))
        r2.addWidget(merge_btn)
        lay.addLayout(r2)
        hint = QLabel("整卷合并 = 把某卷全部章节移到另一卷（如第 2 卷并入第 3 卷，删除空卷）。")
        hint.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        hint.setWordWrap(True)
        lay.addWidget(hint)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(dlg.accept)
        lay.addWidget(close_btn)

        def _set_vol():
            if sel_seq is None:
                QMessageBox.information(dlg, "提示", "请先在时间线选中要归卷的章节行。")
                return
            if store.set_chapter_volume(sel_seq, vol_spin.value()):
                self._fill_timeline()
                log_fn("info", "第 %d 章归入第 %d 卷" % (sel_seq, vol_spin.value()))
                QMessageBox.information(dlg, "完成", "第 %d 章已归入第 %d 卷。" % (sel_seq, vol_spin.value()))
                dlg.accept()
            else:
                QMessageBox.warning(dlg, "提示", "归卷失败：章节不存在或卷号非法。")

        def _merge_vol():
            n = store.rename_volume(old_spin.value(), new_spin.value())
            if n > 0:
                self._fill_timeline()
                log_fn("info", "第 %d 卷 %d 章并入第 %d 卷" % (old_spin.value(), n, new_spin.value()))
                QMessageBox.information(dlg, "完成", "已把第 %d 卷的 %d 章并入第 %d 卷。" %
                                        (old_spin.value(), n, new_spin.value()))
                dlg.accept()
            else:
                QMessageBox.warning(dlg, "提示", "没有可合并的章节（卷号相同/不存在/非法）。")

        set_btn.clicked.connect(_set_vol)
        merge_btn.clicked.connect(_merge_vol)
        dlg.exec()

    def _load_timeline_briefs(self, missing):
        """后台补载旧章节梗概（不读正文全文，只取 brief/首段），完成后经 Signal 回主线程。"""
        store, project = current_project()
        if not project:
            return
        rows = [(r, store.chapter_brief(i) or "（无梗概）") for r, i in missing]
        self._timeline_ready.emit(rows)

    def _on_timeline_ready(self, rows):
        for r, brief in rows:
            if 0 <= r < self.timeline_table.rowCount():
                item = self.timeline_table.item(r, 4)
                if item:
                    item.setText(brief)

    def _view_chapter(self, row):
        if row < 0 or not hasattr(self, "_tl_row2seq"):
            return
        seq = self._tl_row2seq.get(row)
        if seq is None:
            return
        store, project = current_project()
        if not project:
            return
        ch = store.load_chapter(seq)
        if not ch:
            return
        md = T("<h2 style='color:#e8c87a;'>%s</h2>") % html.escape(ch.title or "第%d章" % ch.index)
        names = "、".join(self._name_of(cid) for cid in ch.characters) or "无"
        md += T("<p style='color:#8a93a3;'>第%d卷 · 出场角色：%s</p>") % (
            ch.volume, html.escape(names))
        md += _chapter_meta_html(ch, store)
        md += T("<hr style='border-color:#262e3a;'>")
        md += "<div style='line-height:1.8;'>" + html.escape(ch.content or "").replace("\n", "<br>") + "</div>"
        self.ch_view.setHtml(md)

    def _name_of(self, cid):
        store, _ = current_project()
        card, _ = store.load_character(cid)
        return card.name if card else cid

    def _export_novel(self):
        """导出小说：同时生成 ①完整拼接 txt 与 ②分章文件夹（每章一个 txt）。"""
        export_novel(self)

    def _export_epub(self):
        """导出 EPUB3 电子书（手机/阅读器可直接打开）。"""
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        indices = store.list_chapter_indices()
        if not indices:
            QMessageBox.warning(self, "提示", "还没有已写章节可导出。")
            return
        from PySide6.QtWidgets import QFileDialog
        import export_utils
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 EPUB 电子书", export_utils.default_epub_path(project.title),
            "EPUB 电子书 (*.epub)")
        if not path:
            return
        ok = export_utils.export_novel_epub(project, store, path)
        if ok:
            log_fn("info", "已导出 EPUB：%s（%d 章）" % (path, len(indices)))
            QMessageBox.information(
                self, "导出成功",
                "EPUB3 电子书已导出：\n%s\n（共 %d 章，手机/阅读器可直接打开阅读）" % (path, len(indices)))
        else:
            QMessageBox.warning(self, "导出失败", "EPUB 导出失败，请检查目标路径是否可写。")