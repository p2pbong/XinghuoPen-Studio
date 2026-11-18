# -*- coding: utf-8 -*-
"""事件范例库（v1.134）。

本职：接替已下线的情景卡——给正文AI提供「同一类事件怎么写具体」的完整范例。
每条必须是一个有始有终的完整事件（打斗从起手到收手/分胜负、突破从铺垫到代价）。

页面结构：左=按事件类型分组的树（带计数、标题、字数、碎片标记），右=全文编辑器；
工具条提供单键多格式导入、AI 按完整事件划分整本小说、AI 分类整理（可选 API）、导出。
"""
import datetime
import json
import os
import re
import uuid

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog,
                               QDialogButtonBox, QFileDialog, QFrame, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QProgressDialog,
                               QPushButton, QSplitter, QTableWidget,
                               QTableWidgetItem, QTextEdit, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

import config
from gui_app import current_project, log_fn
from gui_theme import T

EVENT_PRESETS = ["兵刃对决", "突破渡劫", "谈判对峙", "追逐逃杀", "群战围攻",
                 "宴席试探", "情感爆发", "其他"]
_CHAPTER_RE = re.compile(
    r"^\s*(?:第\s*[零一二三四五六七八九十百千万0-9]+\s*[章节回]"
    r"|卷\s*[零一二三四五六七八九十0-9]+|Chapter\s+\d+)", re.IGNORECASE)


def split_novel_text(text, mode="chapter", min_chars=80):
    """机械切分（仅兜底保留）：chapter=按第X章，blank=按空行，whole=整段。"""
    raw = (text or "").replace("\r\n", "\n").strip()
    if not raw:
        return []
    if mode == "whole":
        return [raw]
    segs = []
    if mode == "chapter":
        cur = []
        for line in raw.split("\n"):
            if _CHAPTER_RE.match(line) and "".join(cur).strip():
                segs.append("\n".join(cur).strip())
                cur = [line]
            else:
                cur.append(line)
        if "".join(cur).strip():
            segs.append("\n".join(cur).strip())
    else:
        for blk in re.split(r"\n\s*\n+", raw):
            if blk.strip():
                segs.append(blk.strip())
    merged = []
    for seg in segs:
        if merged and len(seg) < min_chars:
            merged[-1] = merged[-1] + "\n" + seg
        else:
            merged.append(seg)
    return [s for s in merged if len(s) >= 20]


def _text(s):
    return str((s or {}).get("text") or "").strip()


def _normalize(items):
    out = []
    for x in items or []:
        if isinstance(x, str):
            x = {"text": x}
        if not isinstance(x, dict):
            continue
        t = _text(x)
        if not t:
            continue
        ev = str(x.get("event") or "").strip()
        out.append({"id": str(x.get("id") or uuid.uuid4().hex[:8]), "text": t,
                    "note": str(x.get("note") or "").strip(),
                    "event": ev if ev in EVENT_PRESETS else (ev or ""),
                    "title": str(x.get("title") or "").strip()[:18],
                    "flag": "fragment" if str(x.get("flag") or "") == "fragment" else "",
                    "used": max(0, int(x.get("used", 0) or 0))})
    return out


def profile_choices():
    """设置里已配置的 API 名称（供 AI 任务单独指定）。"""
    try:
        cfg = config.load_config()
        return [str(p.get("name") or "") for p in (cfg.get("api_profiles") or [])
                if str(p.get("name") or "").strip()]
    except Exception:
        return []


# ---------------- 线程 ----------------
class _ExtractWorker(QThread):
    progress = Signal(str)
    done = Signal(list, str)

    def __init__(self, jobs, profile=None):
        super().__init__()
        self.jobs = jobs
        self.profile = profile
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        import ref_extract
        out = []
        try:
            for name, text in self.jobs:
                if self._stop:
                    break
                self.progress.emit("正在分析：%s" % name)
                got = ref_extract.extract_events(
                    text, profile=self.profile,
                    progress=lambda d, t, m: self.progress.emit("%s · %s" % (name, m)),
                    should_stop=lambda: self._stop)
                for g in got:
                    g["_src"] = name
                out.extend(got)
            self.done.emit(out, "")
        except Exception as e:      # noqa: BLE001
            self.done.emit([], str(e))


class _ClassifyWorker(QThread):
    progress = Signal(str)
    done = Signal(list, str)

    def __init__(self, items, profile=None):
        super().__init__()
        self.items = items
        self.profile = profile

    def run(self):
        import ref_classify
        try:
            got = ref_classify.classify_items(
                self.items, profile=self.profile,
                progress=lambda d, t, m: self.progress.emit(m))
            self.done.emit(got, "")
        except Exception as e:      # noqa: BLE001
            self.done.emit([], str(e))


# ---------------- 对话框 ----------------
class _CandidateDialog(QDialog):
    """AI 划分结果：勾选要入库的完整事件。"""

    def __init__(self, parent, items):
        super().__init__(parent)
        self.setWindowTitle("AI 划分结果（勾选要入库的完整事件）")
        self.resize(940, 580)
        self.items = items
        lay = QVBoxLayout(self)
        tip = QLabel("每行是一条按「完整事件」切出的原文片段（未改写）。只勾选真正完整的；"
                     "双击可看全文。")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        self.table = QTableWidget(len(items), 5)
        self.table.setHorizontalHeaderLabels(["", "事件类型", "字数", "标题", "预览"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        for c, w in ((0, 30), (1, 100), (2, 60), (3, 160)):
            self.table.setColumnWidth(c, w)
        self.table.horizontalHeader().setStretchLastSection(True)
        for i, it in enumerate(items):
            c = QTableWidgetItem("")
            c.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            c.setCheckState(Qt.Checked)
            self.table.setItem(i, 0, c)
            self.table.setItem(i, 1, QTableWidgetItem(it.get("event") or "其他"))
            self.table.setItem(i, 2, QTableWidgetItem(str(len(it.get("text") or ""))))
            self.table.setItem(i, 3, QTableWidgetItem(it.get("note") or ""))
            prev = (it.get("text") or "").replace("\n", " ")
            self.table.setItem(i, 4, QTableWidgetItem(prev[:90] + ("…" if len(prev) > 90 else "")))
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        for t, v in (("全选", True), ("全不选", False)):
            b = QPushButton(t)
            b.clicked.connect(lambda _=False, _v=v: self._check(_v))
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("导入勾选")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)
        self.table.itemDoubleClicked.connect(lambda _it: self._preview())

    def _check(self, on):
        st = Qt.Checked if on else Qt.Unchecked
        for i in range(self.table.rowCount()):
            self.table.item(i, 0).setCheckState(st)

    def _preview(self):
        r = self.table.currentRow()
        if 0 <= r < len(self.items):
            dlg = QDialog(self)
            dlg.setWindowTitle(str(self.items[r].get("note") or "事件预览"))
            dlg.resize(780, 600)
            lay = QVBoxLayout(dlg)
            e = QTextEdit(self.items[r].get("text") or "")
            e.setReadOnly(True)
            lay.addWidget(e)
            b = QDialogButtonBox(QDialogButtonBox.Close)
            b.rejected.connect(dlg.reject)
            lay.addWidget(b)
            dlg.exec()

    def selected(self):
        return [self.items[i] for i in range(self.table.rowCount())
                if self.table.item(i, 0).checkState() == Qt.Checked]


class _ClassifyDialog(QDialog):
    """AI 分类整理：选择 API/范围 → 结果预览（勾选应用）。"""

    def __init__(self, parent, items, selected=None):
        super().__init__(parent)
        self.setWindowTitle("AI 分类整理范例库")
        self.resize(920, 620)
        self.items = items
        self.selected = [dict(x) for x in (selected or [])]
        self.results = []
        lay = QVBoxLayout(self)
        tip = QLabel("让 AI 给每条范例判定事件类型、起一句话标题，并标出「是不是完整事件」。"
                     "碎片只做标记（可筛选后自己删），不会自动删。")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        row = QHBoxLayout()
        row.addWidget(QLabel("用哪套 API："))
        self.profile = QComboBox()
        self.profile.addItem("（跟随设置·按用途）", None)
        for name in profile_choices():
            self.profile.addItem(name, name)
        row.addWidget(self.profile, 1)
        row.addWidget(QLabel("范围："))
        self.scope = QComboBox()
        self.scope.addItem("全部 %d 条" % len(items), "all")
        self.scope.addItem("只处理未分类/碎片", "todo")
        if self.selected:
            self.scope.addItem("只处理当前选中 %d 条" % len(self.selected), "sel")
        row.addWidget(self.scope)
        run = QPushButton("开始分析")
        run.setObjectName("primary")
        run.clicked.connect(self._run)
        row.addWidget(run)
        lay.addLayout(row)
        self.status = QLabel("")
        self.status.setStyleSheet("color:%s" % T("#8a93a3"))
        lay.addWidget(self.status)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["", "标题", "事件类型", "完整性", "判断依据"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setColumnWidth(0, 30)
        self.table.setColumnWidth(1, 200)
        self.table.setColumnWidth(2, 100)
        self.table.setColumnWidth(3, 90)
        self.table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.table, 1)
        btns = QDialogButtonBox(QDialogButtonBox.Apply | QDialogButtonBox.Close)
        btns.button(QDialogButtonBox.Apply).setText("应用勾选结果")
        btns.button(QDialogButtonBox.Apply).setEnabled(False)
        self._apply_btn = btns.button(QDialogButtonBox.Apply)
        btns.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _targets(self):
        scope = self.scope.currentData()
        if scope == "sel":
            return list(self.selected)
        if scope == "todo":
            return [x for x in self.items
                    if (x.get("event") or "") not in EVENT_PRESETS[:-1]
                    or x.get("flag") == "fragment" or not x.get("title")]
        return list(self.items)

    def _run(self):
        targets = self._targets()
        if not targets:
            self.status.setText("没有需要处理的条目。")
            return
        dlg = QProgressDialog("正在分析…", "后台运行", 0, 0, self)
        dlg.setWindowTitle("AI 分类整理")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        worker = _ClassifyWorker(targets, self.profile.currentData())

        def _done(rows, err):
            dlg.close()
            if err:
                self.status.setText("失败：%s" % err)
                return
            self.results = rows
            self._fill()
            self._apply_btn.setEnabled(bool(rows))
            self.status.setText("完成 %d 条（勾选后点「应用勾选结果」）。" % len(rows))

        worker.progress.connect(lambda m: dlg.setLabelText(m))
        worker.done.connect(_done)
        worker.start()
        dlg.exec()
        worker.wait(2000)

    def _fill(self):
        by_id = {str(x.get("id")): x for x in self.items}
        self.table.setRowCount(len(self.results))
        for i, r in enumerate(self.results):
            c = QTableWidgetItem("")
            c.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            c.setCheckState(Qt.Checked)
            self.table.setItem(i, 0, c)
            self.table.setItem(i, 1, QTableWidgetItem(r.get("title") or ""))
            self.table.setItem(i, 2, QTableWidgetItem(r.get("event") or ""))
            q = "完整" if r.get("quality") == "complete" else "碎片"
            it = QTableWidgetItem(q)
            it.setForeground(QColor("#c0392b") if q == "碎片" else QColor("#1e7b45"))
            self.table.setItem(i, 3, it)
            self.table.setItem(i, 4, QTableWidgetItem(r.get("reason") or ""))

    def picked(self):
        return [self.results[i] for i in range(self.table.rowCount())
                if self.table.item(i, 0) and self.table.item(i, 0).checkState() == Qt.Checked]

    def _apply(self):
        self._applied = self.picked()
        self.accept()


# ---------------- 页面 ----------------
class RefLibraryPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._rows = []
        self._raw_rows = []
        self._cur_id = ""
        self._cur_raw_id = ""
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 12)
        lay.setSpacing(10)

        head = QHBoxLayout()
        t = QLabel("事件范例库")
        t.setStyleSheet("font-size:19px;font-weight:700;")
        head.addWidget(t)
        self.chip_total = self._chip("0 条")
        self.chip_ok = self._chip("0 完整")
        self.chip_frag = self._chip("0 碎片")
        for c in (self.chip_total, self.chip_ok, self.chip_frag):
            head.addWidget(c)
        head.addStretch(1)
        lay.addLayout(head)

        desc = QLabel(
            "接替已下线的情景卡：写章时从「已整理案例」里按事件挑 1~2 条完整事件，"
            "示范这一类事该怎么写具体、节奏怎么分——人物、招式、因果仍用本书自己的。\n"
            "「素材库（未整理）」只放整本原文，不参与写章；用『划分素材』把它切成完整事件、"
            "勾选后才进已整理区。分类按图书分类规则（A 战斗 / B 言语 / C 成长 / D 情感 / E 其他）。")
        desc.setWordWrap(True)
        desc.setStyleSheet("color:%s;font-size:12px;" % T("#8a93a3"))
        lay.addWidget(desc)

        # ---- 工具条 ----
        bar = QFrame()
        bar.setObjectName("panel")
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(10, 8, 10, 8)
        bl.addWidget(QLabel("AI 任务用："))
        self.profile_combo = QComboBox()
        self.profile_combo.addItem("跟随设置（按用途）", None)
        for name in profile_choices():
            self.profile_combo.addItem(name, name)
        self.profile_combo.setToolTip("只影响本页的『AI 智能划分』和『AI 分类整理』，不改全局设置")
        bl.addWidget(self.profile_combo)
        for text, tip, fn, obj in (
                ("＋ 新建", "清空右侧，写一条新的完整事件", self._new, ""),
                ("导入案例…", "进入已整理区：JSON / TXT / MD 多选，自动识别", self._import_files, ""),
                ("导入整本小说…", "整本丢进「素材库（未整理）」，不参与写章；之后用 AI 划分慢慢处理",
                 self._import_raw, ""),
                ("🤖 划分素材", "从素材库选整本 → 主AI 按完整事件判界 → 勾选入已整理区",
                 self._ai_split, ""),
                ("🏷 AI 分类整理", "按图书分类规则归类、起标题、标碎片（可选 API）", self._ai_classify, ""),
                ("🌐 联网找范例", "库里找不到同类时联网检索；只收明确出自真实小说的片段",
                 self._web_find, ""),
                ("导出…", "有选中导选中，否则全部；按扩展名出 JSON/TXT", self._export, "")):
            b = QPushButton(text)
            b.setToolTip(tip)
            if obj:
                b.setObjectName(obj)
            b.clicked.connect(fn)
            bl.addWidget(b)
        bl.addStretch(1)
        lay.addWidget(bar)

        # ---- 主体 ----
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        fr = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索标题/正文/备注…")
        self.search.textChanged.connect(self._refresh_tree)
        fr.addWidget(self.search, 1)
        self.only_frag = QCheckBox("只看碎片")
        self.only_frag.stateChanged.connect(self._refresh_tree)
        fr.addWidget(self.only_frag)
        lv.addLayout(fr)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.currentItemChanged.connect(self._on_tree_sel)
        self.tree.itemDoubleClicked.connect(lambda *_: self.text_edit.setFocus())
        lv.addWidget(self.tree, 1)
        split.addWidget(left)

        right = QFrame()
        right.setObjectName("panel")
        rv = QVBoxLayout(right)
        rv.setContentsMargins(12, 10, 12, 10)
        rv.setSpacing(8)
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("标题："))
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText("一句话概括这起事件（可留空）")
        r1.addWidget(self.title_edit, 2)
        r1.addWidget(QLabel("事件类型："))
        self.event_combo = QComboBox()
        self.event_combo.setEditable(True)
        self.event_combo.addItems(EVENT_PRESETS)
        r1.addWidget(self.event_combo, 1)
        rv.addLayout(r1)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("备注："))
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText("出处 / 适用场景 / 备注，可空")
        r2.addWidget(self.note_edit, 1)
        self.frag_check = QCheckBox("标记为碎片（不完整）")
        self.frag_check.setToolTip("只做标记，方便筛选清理；不影响写章匹配时的完整性优先")
        r2.addWidget(self.frag_check)
        rv.addLayout(r2)
        rh = QHBoxLayout()
        rh.addWidget(QLabel("范例正文（完整事件，可直接编辑）："))
        self.len_label = QLabel("")
        self.len_label.setStyleSheet("color:%s;font-size:12px;" % T("#8a93a3"))
        rh.addStretch(1)
        rh.addWidget(self.len_label)
        rv.addLayout(rh)
        self.text_edit = QTextEdit()
        self.text_edit.setMinimumHeight(280)
        self.text_edit.setPlaceholderText(
            "从事件开始写到收束：\n"
            "打斗=起手—试探—吃亏/占先—变招—建立优势—胜负落地—收势；\n"
            "突破=铺垫与风险—临界—过程—成败与代价；\n"
            "谈判=落座试探—亮底牌—交锋—让步/谈崩—收束。")
        self.text_edit.textChanged.connect(self._update_len)
        rv.addWidget(self.text_edit, 1)
        r3 = QHBoxLayout()
        save = QPushButton("💾 保存修改")
        save.setObjectName("primary")
        save.clicked.connect(lambda: self._save(False))
        r3.addWidget(save)
        save_new = QPushButton("另存为新范例")
        save_new.clicked.connect(lambda: self._save(True))
        r3.addWidget(save_new)
        dele = QPushButton("删除选中")
        dele.setObjectName("danger")
        dele.clicked.connect(self._delete)
        r3.addWidget(dele)
        r3.addStretch(1)
        self.msg = QLabel("")
        self.msg.setStyleSheet("color:%s;font-size:12px;" % T("#8a93a3"))
        r3.addWidget(self.msg)
        rv.addLayout(r3)
        split.addWidget(right)
        split.setSizes([340, 760])
        lay.addWidget(split, 1)
        self.reload()

    @staticmethod
    def _chip(text):
        l = QLabel(text)
        l.setStyleSheet("background:%s;color:%s;border-radius:9px;padding:2px 9px;font-size:12px;"
                        % (T("#eef1f6"), T("#5b6470")))
        return l

    # ---------- 数据 ----------
    def _data(self):
        store, project = current_project()
        if not project:
            return None, None, []
        return store, project, [dict(s) for s in
                                (getattr(project, "story_ref_samples", None) or [])
                                if isinstance(s, dict)]

    def _persist(self, store, project, samples):
        project.story_ref_samples = samples
        store.save_project(project)

    def on_show(self):
        self.reload()

    def reload(self):
        self._refresh_tree()

    def _raw_data(self):
        store, project = current_project()
        if not project:
            return None, None, []
        return store, project, [dict(s) for s in
                                (getattr(project, "story_ref_raw", None) or [])
                                if isinstance(s, dict)]

    def _persist_raw(self, store, project, items):
        project.story_ref_raw = items
        store.save_project(project)

    def _refresh_tree(self):
        store, project, samples = self._data()
        _s2, _p2, raws = self._raw_data()
        kw = self.search.text().strip().lower()
        only_frag = self.only_frag.isChecked()
        cats = {}
        for s in samples:
            ev = s.get("event") or "其他"
            hay = "%s %s %s %s %s" % (s.get("title") or "", s.get("note") or "",
                                      s.get("text") or "", ev, s.get("code") or "")
            if kw and kw not in hay.lower():
                continue
            if only_frag and s.get("flag") != "fragment":
                continue
            cats.setdefault(ev, []).append(s)
        self.tree.blockSignals(True)
        self.tree.clear()
        self._rows = []
        self._raw_rows = [r for r in raws
                          if not kw or kw in ("%s %s %s" % (r.get("title") or "",
                                                            r.get("source") or "",
                                                            r.get("text") or "")).lower()]
        root_ok = QTreeWidgetItem(["已整理案例（%d）" % sum(len(v) for v in cats.values())])
        root_ok.setFlags(Qt.ItemIsEnabled)
        f = root_ok.font(0)
        f.setBold(True)
        root_ok.setFont(0, f)
        self.tree.addTopLevelItem(root_ok)
        import ref_taxonomy as _tax
        for cname, subs in _tax.groups():
            ev_rows = [(code, ev, cats.get(ev) or []) for code, ev in subs]
            if not any(rows for _, _, rows in ev_rows):
                continue
            cnode = QTreeWidgetItem(["%s（%d）" % (cname, sum(len(r) for _, _, r in ev_rows))])
            cnode.setFlags(Qt.ItemIsEnabled)
            f = cnode.font(0)
            f.setBold(True)
            cnode.setFont(0, f)
            root_ok.addChild(cnode)
            for code, ev, rows in ev_rows:
                if not rows:
                    continue
                enode = QTreeWidgetItem(["%s %s（%d）" % (code, ev, len(rows))])
                enode.setFlags(Qt.ItemIsEnabled)
                cnode.addChild(enode)
                for s in rows:
                    title = s.get("title") or ""
                    prev = _text(s).replace("\n", " ")
                    label = "%s%s（%d字）" % (("【碎片】" if s.get("flag") == "fragment" else ""),
                                             title or prev[:16], len(_text(s)))
                    it = QTreeWidgetItem([label])
                    it.setData(0, Qt.UserRole, str(s.get("id") or ""))
                    it.setToolTip(0, "%s\n\n%s" % (s.get("note") or "", _text(s)[:500]))
                    enode.addChild(it)
                    self._rows.append(s)
        root_raw = QTreeWidgetItem(["素材库·未整理（%d）" % len(self._raw_rows)])
        root_raw.setFlags(Qt.ItemIsEnabled)
        f = root_raw.font(0)
        f.setBold(True)
        root_raw.setFont(0, f)
        self.tree.addTopLevelItem(root_raw)
        for r in self._raw_rows:
            it = QTreeWidgetItem(["%s（%d字）" % (r.get("title") or r.get("source") or "未命名",
                                                 len(r.get("text") or ""))])
            it.setData(0, Qt.UserRole, "raw:" + str(r.get("id") or ""))
            it.setToolTip(0, "整本素材，不参与写章；选中后点「划分素材」处理。")
            root_raw.addChild(it)
        self.tree.expandAll()
        self.tree.blockSignals(False)
        total = len(samples)
        frag = sum(1 for s in samples if s.get("flag") == "fragment")
        kinds = len({s.get("event") or "其他" for s in samples})
        self.chip_total.setText("%d 条 · %d 类" % (total, kinds))
        self.chip_ok.setText("%d 完整" % max(0, total - frag))
        self.chip_frag.setText("%d 碎片" % frag)
        if project is None:
            self.msg.setText("请先载入项目。")
        if self._cur_id:
            self._select_by_id(self._cur_id)

    def _select_by_id(self, sid):
        for it, _p in self._iter_tree_items():
            if it.data(0, Qt.UserRole) == sid:
                self.tree.setCurrentItem(it)
                return

    def _iter_tree_items(self):
        def walk(node):
            for i in range(node.childCount()):
                c = node.child(i)
                yield c, node
                for x, p in walk(c):
                    yield x, p
        for i in range(self.tree.topLevelItemCount()):
            t = self.tree.topLevelItem(i)
            yield t, None
            for x, p in walk(t):
                yield x, p

    def _on_tree_sel(self, cur, _prev):
        if not cur:
            return
        sid = cur.data(0, Qt.UserRole)
        if not sid:
            return
        if str(sid).startswith("raw:"):
            rid = str(sid)[4:]
            r = next((x for x in self._raw_rows if str(x.get("id")) == rid), None)
            if not r:
                return
            self._cur_raw_id = rid
            self._cur_id = ""
            self.title_edit.setText(r.get("title") or "")
            self.event_combo.setCurrentText("")
            self.note_edit.setText(r.get("source") or "")
            self.frag_check.setChecked(False)
            self.text_edit.setPlainText(r.get("text") or "")
            self._update_len()
            self.msg.setText("整本素材（不参与写章）：可直接改原文；点「划分素材」切成完整事件后再入库。")
            return
        self._cur_raw_id = ""
        s = next((x for x in self._rows if str(x.get("id")) == sid), None)
        if not s:
            return
        self._cur_id = sid
        self.title_edit.setText(s.get("title") or "")
        self.event_combo.setCurrentText(s.get("event") or "")
        self.note_edit.setText(s.get("note") or "")
        self.frag_check.setChecked(s.get("flag") == "fragment")
        self.text_edit.setPlainText(_text(s))
        self._update_len()

    def _update_len(self):
        n = len(self.text_edit.toPlainText())
        self.len_label.setText("%d 字%s" % (n, "" if n >= 200 else "（太短，可能不是完整事件）"))

    def _new(self):
        self._cur_id = ""
        self._cur_raw_id = ""
        self.title_edit.clear()
        self.event_combo.setCurrentText("")
        self.note_edit.clear()
        self.frag_check.setChecked(False)
        self.text_edit.clear()
        self.text_edit.setFocus()
        self.msg.setText("新建：填好后点「另存为新范例」。")

    def _save(self, as_new):
        store, project, samples = self._data()
        if not project:
            return
        body = self.text_edit.toPlainText().strip()
        if len(body) < 20:
            self.msg.setText("正文太短——请放一个完整事件。")
            return
        if self._cur_raw_id:
            _s2, _p2, raws = self._raw_data()
            for i, r in enumerate(raws):
                if str(r.get("id")) == self._cur_raw_id:
                    raws[i]["title"] = self.title_edit.text().strip() or r.get("title") or ""
                    raws[i]["source"] = self.note_edit.text().strip()
                    raws[i]["text"] = body
                    raws[i]["chars"] = len(body)
                    break
            self._persist_raw(_s2, _p2, raws)
            self._refresh_tree()
            self.msg.setText("素材原文已保存。")
            return
        import ref_taxonomy as _tax
        ev = self.event_combo.currentText().strip()
        row = {"text": body,
               "title": self.title_edit.text().strip()[:18],
               "event": ev,
               "code": _tax.code_for_event(ev),
               "note": self.note_edit.text().strip(),
               "flag": "fragment" if self.frag_check.isChecked() else "",
               "used": 0}
        if as_new or not self._cur_id:
            row["id"] = uuid.uuid4().hex[:8]
            samples.append(row)
            self._persist(store, project, samples)
            self._cur_id = row["id"]
            self._refresh_tree()
            self.msg.setText("已新增 1 条。")
            log_fn("info", "事件范例新增 1 条（%s，%d 字）。" % (row["event"] or "未分类", len(body)))
            return
        for i, s in enumerate(samples):
            if str(s.get("id")) == self._cur_id:
                row["id"] = self._cur_id
                row["used"] = int(s.get("used", 0) or 0)
                samples[i] = row
                break
        self._persist(store, project, samples)
        self._refresh_tree()
        self.msg.setText("已保存修改。")

    def _selected_ids(self):
        ids = []
        for it in self.tree.selectedItems():
            sid = it.data(0, Qt.UserRole)
            if sid and not str(sid).startswith("raw:"):
                ids.append(str(sid))
        if not ids and self._cur_id:
            ids = [self._cur_id]
        return ids

    def _delete(self):
        ids = set(self._selected_ids())
        raw_ids = set()
        for it in self.tree.selectedItems():
            sid = str(it.data(0, Qt.UserRole) or "")
            if sid.startswith("raw:"):
                raw_ids.add(sid[4:])
        if not ids and not raw_ids:
            self.msg.setText("请先在左边选中要删除的条目。")
            return
        if raw_ids:
            _s3, _p3, raws = self._raw_data()
            keep_raw = [r for r in raws if str(r.get("id")) not in raw_ids]
            self._persist_raw(_s3, _p3, keep_raw)
        store, project, samples = self._data()
        keep = [s for s in samples if str(s.get("id")) not in ids]
        self._persist(store, project, keep)
        self._cur_id = ""
        self._cur_raw_id = ""
        self._new()
        self._refresh_tree()
        self.msg.setText("已删除：案例 %d 条、素材 %d 本。" % (len(samples) - len(keep), len(raw_ids)))
        log_fn("info", "事件范例删除 %d 条、素材 %d 本。" % (len(samples) - len(keep), len(raw_ids)))

    # ---------- 导入 ----------
    def _merge(self, samples, items):
        have = {_text(s) for s in samples}
        added = skipped = 0
        for x in items:
            t = _text(x)
            if not t or t in have:
                skipped += 1
                continue
            have.add(t)
            samples.append(x)
            added += 1
        return added, skipped

    def _read(self, path):
        try:
            return open(path, "r", encoding="utf-8", errors="replace").read()
        except Exception:
            return ""

    def _parse_any(self, path):
        raw = self._read(path)
        if not raw.strip():
            return [], "空文件"
        if path.lower().endswith(".json") or raw.lstrip()[:1] in "[{":
            try:
                data = json.loads(raw)
            except Exception:
                return [], "JSON 解析失败"
            if isinstance(data, dict):
                data = data.get("samples") or data.get("items") or []
            return _normalize(data if isinstance(data, list) else []), ""
        ev = self.event_combo.currentText().strip()
        return ([{"id": uuid.uuid4().hex[:8], "text": raw.strip(),
                  "note": os.path.basename(path), "event": ev,
                  "title": "", "flag": "", "used": 0}], "")

    def _import_files(self):
        store, project, samples = self._data()
        if not project:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "导入范例（JSON / TXT / MD，可多选）", "",
            "范例文件 (*.json *.txt *.md);;所有文件 (*.*)")
        if not paths:
            return
        items, bad = [], []
        for p in paths:
            got, errmsg = self._parse_any(p)
            if errmsg:
                bad.append("%s（%s）" % (os.path.basename(p), errmsg))
            items.extend(got)
        added, skipped = self._merge(samples, items)
        self._persist(store, project, samples)
        self._refresh_tree()
        msg = "导入完成：新增 %d 条，跳过重复/空 %d 条。" % (added, skipped)
        if bad:
            msg += " 未导入：" + "；".join(bad)
        self.msg.setText(msg)
        log_fn("info", msg)

    def _import_raw(self):
        """整本小说进「素材库（未整理）」——不切块、不参与写章。"""
        store, project, raws = self._raw_data()
        if not project:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "导入整本小说（txt / md，可多选）", "",
            "小说文本 (*.txt *.md);;所有文件 (*.*)")
        if not paths:
            return
        added = 0
        for p in paths:
            text = self._read(p).strip()
            if len(text) < 200:
                continue
            raws.append({"id": uuid.uuid4().hex[:8],
                         "title": os.path.splitext(os.path.basename(p))[0],
                         "source": os.path.basename(p),
                         "text": text, "chars": len(text),
                         "added": datetime.datetime.now().strftime("%Y-%m-%d")})
            added += 1
        if not added:
            QMessageBox.information(self, "提示", "文件太短，没有导入。")
            return
        self._persist_raw(store, project, raws)
        self._refresh_tree()
        self.msg.setText("已导入 %d 本到素材库（未整理）。选中后点「划分素材」处理。" % added)
        log_fn("info", "整本小说素材导入 %d 本（不参与写章，待 AI 划分）。" % added)

    # ---------- AI ----------
    def _profile(self):
        return self.profile_combo.currentData()

    def _ai_split(self):
        store, project, samples = self._data()
        _s2, _p2, raws = self._raw_data()
        if not project:
            return
        sel_raw = []
        for it in self.tree.selectedItems():
            sid = str(it.data(0, Qt.UserRole) or "")
            if sid.startswith("raw:"):
                sel_raw.append(sid[4:])
        targets = [r for r in raws if str(r.get("id")) in set(sel_raw)] if sel_raw else raws
        if not targets:
            QMessageBox.information(
                self, "素材库是空的",
                "请先用「导入整本小说…」把整本丢进素材库；选中某一本再点「划分素材」可只处理它。")
            return
        if QMessageBox.question(
                self, "划分素材",
                "将处理 %d 本（共 %d 字），交给主AI 按完整事件判界；结果预览勾选后才入已整理区。\n"
                "使用的 API：%s\n继续？"
                % (len(targets), sum(len(r.get("text") or "") for r in targets),
                   self.profile_combo.currentText())) != QMessageBox.Yes:
            return
        jobs = [(r.get("title") or r.get("source") or "素材", r.get("text") or "")
                for r in targets]
        dlg = QProgressDialog("准备中…", "取消", 0, 0, self)
        dlg.setWindowTitle("AI 划分完整事件")
        dlg.setWindowModality(Qt.WindowModal)
        dlg.setMinimumDuration(0)
        dlg.setMinimumWidth(480)
        result = {"items": [], "err": ""}
        worker = _ExtractWorker(jobs, self._profile())
        worker.progress.connect(lambda m: dlg.setLabelText(m))
        worker.done.connect(lambda items, err: (result.update(items=items, err=err), dlg.close()))
        dlg.canceled.connect(worker.stop)
        worker.start()
        dlg.exec()
        worker.wait(2000)
        if result["err"]:
            QMessageBox.warning(self, "划分失败", result["err"])
            return
        if not result["items"]:
            QMessageBox.information(self, "提示",
                                    "没有识别出完整事件。可换更完整的章节文本，或整段导入后手改。")
            return
        cd = _CandidateDialog(self, result["items"])
        if cd.exec() != QDialog.Accepted:
            return
        picked = cd.selected()
        import ref_taxonomy as _tax
        for it in picked:
            it.pop("_src", None)
            it.pop("chars", None)
            it["id"] = uuid.uuid4().hex[:8]
            it["title"] = it.get("note") or ""
            it["code"] = _tax.code_for_event(it.get("event"))
            it["flag"] = ""
            it["used"] = 0
        added, skipped = self._merge(samples, picked)
        self._persist(store, project, samples)
        self._refresh_tree()
        self.msg.setText("AI 划分入库：新增 %d 条（跳过重复 %d 条）。" % (added, skipped))
        log_fn("info", "AI 智能划分入库 %d 条（候选 %d 条）。" % (added, len(result["items"])))

    def _ai_classify(self):
        store, project, samples = self._data()
        if not project or not samples:
            QMessageBox.information(self, "提示", "范例库是空的。")
            return
        sel = self._selected_ids()
        sel_items = [x for x in samples if str(x.get("id")) in set(sel)]
        dlg = _ClassifyDialog(self, samples, sel_items)
        if dlg.exec() != QDialog.Accepted:
            return
        picked = getattr(dlg, "_applied", [])
        if not picked:
            return
        by_id = {r["id"]: r for r in picked}
        changed = 0
        for i, s in enumerate(samples):
            r = by_id.get(str(s.get("id")))
            if not r:
                continue
            s = dict(s)
            s["event"] = r.get("event") or s.get("event") or "其他"
            if r.get("title"):
                s["title"] = r["title"]
            s["flag"] = "fragment" if r.get("quality") == "fragment" else ""
            if r.get("code"):
                s["code"] = r["code"]
            samples[i] = s
            changed += 1
        self._persist(store, project, samples)
        self._refresh_tree()
        self.msg.setText("已应用 %d 条的 AI 分类结果。" % changed)
        log_fn("info", "AI 分类整理应用 %d 条（按完整事件/碎片标记）。" % changed)

    # ---------- 联网 / 导出 ----------
    def _web_find(self):
        """库内找不到同类时，联网检索真实小说片段（只收有明确出处的，不编造）。"""
        from PySide6.QtWidgets import QInputDialog
        import web_search
        store, project, samples = self._data()
        if not project:
            return
        ev = self.event_combo.currentText().strip() or "事件"
        kw, ok = QInputDialog.getText(
            self, "联网找范例",
            "要写的这类事件（如：剑斗对决 长街 枪）：\n"
            "只接受明确出自真实小说的片段；搜不到就换关键词，不要编造。",
            text=ev)
        if not ok or not kw.strip():
            return
        try:
            results = web_search.search(kw.strip() + " 小说 原文 片段", max_results=8)
        except Exception as e:
            QMessageBox.warning(self, "搜索失败", str(e))
            return
        if not results:
            QMessageBox.information(self, "提示", "没有搜到可用结果，换个关键词试试。")
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("联网检索结果（只导入明确出处的片段）")
        dlg.resize(900, 560)
        l = QVBoxLayout(dlg)
        tip = QLabel("下面是检索到的网页摘要。**不是所有摘要都是小说原文**——"
                     "请点开链接确认是完整事件、且出自明确的小说，再勾选导入；"
                     "导入后可在右侧编辑全文。禁止用模型改写/编造。")
        tip.setWordWrap(True)
        l.addWidget(tip)
        t = QTableWidget(len(results), 4)
        t.setHorizontalHeaderLabels(["", "标题", "来源", "摘要"])
        t.verticalHeader().setVisible(False)
        t.setEditTriggers(QAbstractItemView.NoEditTriggers)
        t.setColumnWidth(0, 30)
        t.setColumnWidth(1, 240)
        t.setColumnWidth(2, 220)
        t.horizontalHeader().setStretchLastSection(True)
        for i, r in enumerate(results):
            c = QTableWidgetItem("")
            c.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            c.setCheckState(Qt.Unchecked)
            t.setItem(i, 0, c)
            t.setItem(i, 1, QTableWidgetItem(str(r.get("title") or "")))
            t.setItem(i, 2, QTableWidgetItem(str(r.get("url") or "")))
            t.setItem(i, 3, QTableWidgetItem(str(r.get("snippet") or "")[:200]))
        l.addWidget(t, 1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("导入勾选（作为待编辑素材）")
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        l.addWidget(bb)
        if dlg.exec() != QDialog.Accepted:
            return
        picked = [results[i] for i in range(t.rowCount())
                  if t.item(i, 0).checkState() == Qt.Checked]
        if not picked:
            return
        import ref_taxonomy as _tax
        added = 0
        for r in picked:
            body = str(r.get("snippet") or "").strip()
            if len(body) < 40:
                continue
            samples.append({"id": uuid.uuid4().hex[:8], "text": body,
                            "title": (str(r.get("title") or "")[:18] or ev),
                            "event": ev, "code": _tax.code_for_event(ev),
                            "note": "来源：%s %s" % (r.get("title") or "", r.get("url") or ""),
                            "flag": "fragment", "used": 0})
            added += 1
        self._persist(store, project, samples)
        self._refresh_tree()
        self.msg.setText("已导入 %d 条检索结果（标记为碎片，请核对出处并补全全文后取消标记）。" % added)
        log_fn("info", "联网找范例：导入 %d 条待核对片段。" % added)

    def _export(self):
        store, project, samples = self._data()
        if not project:
            return
        ids = set(self._selected_ids())
        chosen = [s for s in samples if str(s.get("id")) in ids] if ids else samples
        if not chosen:
            QMessageBox.information(self, "提示", "没有可导出的范例。")
            return
        title = re.sub(r"[\\/:*?\"<>|]+", "_", (project.title or "项目"))
        default = "%s_事件范例_%s.json" % (title, datetime.date.today().strftime("%Y%m%d"))
        path, flt = QFileDialog.getSaveFileName(
            self, "导出范例（%d 条）" % len(chosen), default,
            "JSON (*.json);;文本 (*.txt)")
        if not path:
            return
        try:
            if path.lower().endswith(".txt") or "文本" in (flt or ""):
                blocks = []
                for i, s in enumerate(chosen, 1):
                    head = ["范例%d" % i]
                    for key, lab in (("event", "事件类型"), ("title", "标题"), ("note", "备注")):
                        if s.get(key):
                            head.append("%s：%s" % (lab, s[key]))
                    head.append("字数：%d" % len(_text(s)))
                    blocks.append("### " + "｜".join(head) + "\n\n" + _text(s))
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n\n----------\n\n".join(blocks))
            else:
                payload = {"kind": "xinghuobi_ref_samples", "version": 1,
                           "project": project.title,
                           "exported_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                           "samples": chosen}
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(payload, f, ensure_ascii=False, indent=1)
        except Exception as e:
            QMessageBox.warning(self, "导出失败", str(e))
            return
        self.msg.setText("已导出 %d 条到 %s" % (len(chosen), os.path.basename(path)))
        log_fn("info", "导出事件范例 %d 条：%s" % (len(chosen), path))
