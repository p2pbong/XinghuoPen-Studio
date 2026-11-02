# -*- coding: utf-8 -*-
"""去AI味页：对已生成章节做后处理润色（不改剧情）——①按规则清洗 ②句式/词形替换 ③AI重写（整章/局部）。

处理结果暂存为「待定稿」（项目内 deai/，跨启动保留），对比满意后再合并回原文
（合并前自动备份到草稿箱可恢复），也支持导出润色稿。
"""
import threading

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFrame, QGroupBox,
                               QHBoxLayout, QLabel, QListWidget,
                               QMessageBox, QPlainTextEdit, QPushButton,
                               QRadioButton, QScrollArea, QSpinBox, QSplitter,
                               QVBoxLayout, QWidget)

import config as app_config
import main_ai
from gui_app import APP, busy_guard, current_project, engine_for, log_fn, set_running
from prompts import DEAI_DEFAULT_RULES
from gui_theme import T

MODE_TEXT = {"clean": "按规则清洗", "replace": "句式/词形替换", "rewrite": "AI 重写"}


class _DeaiWorker(QObject):
    """后台去AI味线程：先整体审查（找问题位置）→ 再处理 → 存待定稿（信号跨线程回传，不碰 UI）。"""

    done = Signal(int, object)     # (chapter_no, error_or_None)
    audit = Signal(int, object)    # (chapter_no, issues 或 None)：整体审查结果（供界面展示）
    finished = Signal()

    def run(self, project, store, chapters, mode, rules, selected_text, directive,
            with_audit=True, style_ref=""):
        for idx in chapters:
            try:
                ch = store.load_chapter(idx)
                if ch is None:
                    self.done.emit(idx, ValueError("章节缺失"))
                    continue
                # ① 整体审查：先通读整章找出 AI 味问题位置，再交给处理环节
                issues = []
                if with_audit:
                    try:
                        issues = main_ai.deai_audit(project, store, ch, rules) or []
                    except Exception:
                        issues = []
                    self.audit.emit(idx, issues or None)
                # ② 处理（清洗/替换/重写）：优先覆盖审查命中的位置；v1.02 注入参考文风样本
                out = main_ai.deai_chapter(project, store, ch, mode, rules,
                                           selected_text, directive, audit_issues=issues,
                                           style_ref=style_ref)
                if not (out or "").strip():
                    self.done.emit(idx, ValueError("模型未返回有效内容"))
                    continue
                store.save_deai_draft(idx, out, mode, rules)
                self.done.emit(idx, None)
            except Exception as e:
                self.done.emit(idx, e)
        self.finished.emit()


class _AutoDeaiWorker(QObject):
    """v1.04 一键自动去AI味后台线程：逐章 改写→验收→不达标带反馈重写，达标自动合并回原文。

    只跑引擎工作流（不碰任何 QWidget）：进度经 event 信号回主线程槽刷新；绝不直接调
    QMessageBox/.exec（后台线程直接弹框会卡死 UI，见 v1.03 教训）。
    """

    event = Signal(str, object)   # (kind, data)：chapter_start/round_done/chapter_done/chapter_fail/stopped/error
    finished = Signal()

    def run(self, project_dir, store, chapters, rules, style_ref,
            threshold, max_rounds, length_tol, stop_event):
        import llm
        # v1.16 停止立即生效：绑定 abort 事件后，正在进行的 LLM 调用（改写/验收）会被
        # 中断并抛 StopRequested，不等当前请求跑完（此前只做轮间 stop_check，必须等完成才停）
        llm.set_abort(stop_event)
        passed = failed = 0
        try:
            for kind, data in main_ai.deai_auto_workflow(
                    store.load_project(), store, chapters, rules, style_ref,
                    threshold, max_rounds, length_tol,
                    stop_check=lambda: stop_event.is_set(), log=log_fn):
                if kind == "chapter_done":
                    passed += 1
                elif kind == "chapter_fail":
                    failed += 1
                self.event.emit(kind, data)
        except llm.StopRequested:
            self.event.emit("stopped", {"passed": passed, "failed": failed})
        except Exception as e:
            self.event.emit("error", {"msg": str(e)})
        finally:
            llm.set_abort(None)
        self.finished.emit()


class DeaiPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self._sel_text = ""
        self._worker = None
        self._queued = []     # 本次处理队列
        self._auto_stop = threading.Event()   # v1.04 一键自动去AI味停止信号（轮间检查）

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        self.scroll.setWidget(host)
        outer.addWidget(self.scroll)

        # ---------- 顶部说明 + 模式 ----------
        head = QLabel("对已生成的章节做去AI味——**不改剧情**，只改表达、描写、用词。"
                      "每章先做**整体文风审查**（找出所有 AI 味问题位置）再处理，处理结果存为「待定稿」，"
                      "对比满意后再合并回原文（合并前旧稿自动备份到草稿箱，可随时恢复）。")
        head.setWordWrap(True)
        head.setStyleSheet(T("color:#5b6470;"))
        lay.addWidget(head)

        mbox = QGroupBox("处理方式")
        mrow = QVBoxLayout(mbox)
        r1 = QHBoxLayout()
        self.rb_clean = QRadioButton("① 按规则清洗（只改规则命中的内容，其余逐字不动）")
        self.rb_clean.setChecked(True)
        self.rb_replace = QRadioButton("② 句式/词形替换（只换个别用词句式，改动最小）")
        self.rb_rewrite = QRadioButton("③ AI 重写（保证剧情不变，重写文字表达）")
        r1.addWidget(self.rb_clean)
        r1.addWidget(self.rb_replace)
        r1.addWidget(self.rb_rewrite)
        mrow.addLayout(r1)
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("　重写范围："))
        self.rb_whole = QRadioButton("整章")
        self.rb_whole.setChecked(True)
        self.rb_part = QRadioButton("局部（在中间「原文预览」里用鼠标拖选要重写的文字，选区即目标）")
        r2.addWidget(self.rb_whole)
        r2.addWidget(self.rb_part)
        self.directive_edit = QPlainTextEdit()
        self.directive_edit.setPlaceholderText("改为局部重写时，可在这里写你想怎么改（例：这段写得太平，加个反转/改为侧写对手的反应…）")
        self.directive_edit.setMaximumHeight(56)
        r2.addWidget(self.directive_edit, 1)
        mrow.addLayout(r2)
        lay.addWidget(mbox)

        # ---------- 主区三列（QSplitter 可拖动调整各栏宽度） ----------
        main = QSplitter(Qt.Orientation.Horizontal)
        main.setChildrenCollapsible(False)

        # 左：待处理章节（多选）+ 去AI味规则（编辑规则时可看中间全文对照）
        lbox = QGroupBox("已写章节（多选要处理的章）")
        llay = QVBoxLayout(lbox)
        self.ch_list = QListWidget()
        self.ch_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.ch_list.itemSelectionChanged.connect(self._on_ch_sel)
        llay.addWidget(self.ch_list, 1)
        lr = QHBoxLayout()
        self.sel_all_btn = QPushButton("全选")
        self.sel_all_btn.clicked.connect(lambda: self.ch_list.selectAll())
        self.sel_none_btn = QPushButton("清空")
        self.sel_none_btn.clicked.connect(lambda: self.ch_list.clearSelection())
        self.sel_count = QLabel("已选 0 章")
        self.sel_count.setStyleSheet(T("color:#8a93a3;"))
        lr.addWidget(self.sel_all_btn)
        lr.addWidget(self.sel_none_btn)
        lr.addWidget(self.sel_count)
        lr.addStretch(1)
        llay.addLayout(lr)
        # 左列下半：去AI味规则（编辑时可对照中间原文全文）
        rbox = QGroupBox("去AI味规则（可编辑；清洗/替换按它执行，重写也参考）")
        rlay = QVBoxLayout(rbox)
        self.rules_edit = QPlainTextEdit()
        rlay.addWidget(self.rules_edit)
        # v1.02 参考文风样本：光靠规则不够，贴一段想要的味道让 AI 往那个语感上改（不抄内容）
        # v1.07：放开"几百字"限制——可贴多段不同情景的笔调（打斗/文斗/日常/情景酝酿等），
        # AI 按原文所处情景取对应笔调模仿；编辑框加大，注入端不再截断到几百字。
        ref_lbl = QLabel("参考文风样本（可选）：可贴**多段不同情景的笔调样本**——打斗、文斗、日常对话、"
                         "情景酝酿等各贴一小段（每类一小段即可，总长不限），"
                         "AI 去AI味时按原文所处情景取对应笔调模仿（只学味道，不照抄内容）；留空=只按规则改")
        ref_lbl.setWordWrap(True)
        ref_lbl.setStyleSheet(T("color:#8a93a3;font-size:12px;margin-top:6px;"))
        rlay.addWidget(ref_lbl)
        self.style_ref_edit = QPlainTextEdit()
        self.style_ref_edit.setMaximumHeight(260)
        self.style_ref_edit.setPlaceholderText(
            "例：打斗段落一段 + 文斗/日常/情绪酝酿各一段（每类一小段，总长不限）；"
            "去AI味时会按原文所处情景取对应笔调模仿其语感/句式/节奏…")
        rlay.addWidget(self.style_ref_edit)
        rrow = QHBoxLayout()
        save_rules = QPushButton("保存规则与参考文本")
        save_rules.setObjectName("primary")
        save_rules.clicked.connect(self._save_rules)
        reset_rules = QPushButton("恢复默认")
        reset_rules.clicked.connect(self._reset_rules)
        rrow.addWidget(save_rules)
        rrow.addWidget(reset_rules)
        rrow.addStretch(1)
        rlay.addLayout(rrow)
        llay.addWidget(rbox, 1)
        main.addWidget(lbox)

        # 中：对比预览（原文 / 润色稿）
        cbox = QGroupBox("对比预览（原文在上，润色稿在下）")
        clay = QVBoxLayout(cbox)
        split = QSplitter(Qt.Orientation.Vertical)
        self.orig_view = QPlainTextEdit()
        self.orig_view.setReadOnly(True)
        # 只读但允许鼠标拖选：拖选的文本自动成为「局部重写」目标
        self.orig_view.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard)
        self.orig_view.selectionChanged.connect(self._on_orig_selection)
        self.orig_view.setPlaceholderText("点击左侧章节后，这里显示原文（可读）；\n"
                                          "改「AI 重写·局部」时，直接用鼠标拖选要重写的文字——选区即重写目标")
        self.polish_view = QPlainTextEdit()
        self.polish_view.setReadOnly(True)
        self.polish_view.setPlaceholderText("该章的润色稿（待定稿）")
        split.addWidget(self.orig_view)
        split.addWidget(self.polish_view)
        split.setStretchFactor(0, 1)
        split.setStretchFactor(1, 1)
        split.setSizes([400, 400])
        clay.addWidget(split, 1)
        pr = QHBoxLayout()
        pr.addWidget(QLabel("③局部重写目标："))
        self.sel_text_lbl = QLabel("未选择（在原文预览里拖选文字即可选中）")
        self.sel_text_lbl.setStyleSheet(T("color:#8a93a3;"))
        self.sel_text_lbl.setWordWrap(True)
        pr.addWidget(self.sel_text_lbl, 1)
        clay.addLayout(pr)
        main.addWidget(cbox)

        # 右：待定稿
        dbox = QGroupBox("待定稿（暂存，未合并）")
        dlay = QVBoxLayout(dbox)
        self.draft_list = QListWidget()
        self.draft_list.currentRowChanged.connect(self._on_draft_sel)
        dlay.addWidget(self.draft_list, 1)
        dr = QHBoxLayout()
        self.apply_btn = QPushButton("应用此稿")
        self.apply_btn.setObjectName("primary")
        self.apply_btn.clicked.connect(self._apply_selected)
        self.rework_btn = QPushButton("重新处理")
        self.rework_btn.clicked.connect(self._rework_selected)
        self.discard_btn = QPushButton("丢弃")
        self.discard_btn.setObjectName("danger")
        self.discard_btn.clicked.connect(self._discard_selected)
        dlay.addLayout(dr)
        dr.addWidget(self.apply_btn)
        dr.addWidget(self.rework_btn)
        dr.addWidget(self.discard_btn)
        d2 = QHBoxLayout()
        merge_all_btn = QPushButton("全部合并回原文")
        merge_all_btn.setToolTip("把全部待定稿批量写回正式章节（每章写回前自动备份旧稿到草稿箱）")
        merge_all_btn.clicked.connect(self._merge_all)
        export_btn = QPushButton("导出待定稿（txt）")
        export_btn.clicked.connect(self._export_drafts)
        d2.addWidget(merge_all_btn)
        d2.addWidget(export_btn)
        d2.addStretch(1)
        dlay.addLayout(d2)
        main.addWidget(dbox)

        main.setStretchFactor(0, 3)
        main.setStretchFactor(1, 6)
        main.setStretchFactor(2, 3)
        lay.addWidget(main, 1)

        # ---------- v1.04 一键自动去AI味（结合文风校对的「评分→优化→达标自动通过」验收循环） ----------
        autobox = QGroupBox("一键自动去AI味（批量验收自动通过）")
        alay = QVBoxLayout(autobox)
        anote = QLabel(
            "对左侧已选章节批量运行：每章按规则+参考文风样本改写 → 自动验收"
            "（文风契合度 + 剧情一致性 + 字数容差）→ **达标自动合并回原文**（旧稿自动备份草稿箱可恢复）；\n"
            "未达标自动把验收反馈带回下一轮重写，直到达标或达到最大轮次；**每章取已跑轮次中评分最高的一轮作为成果**"
            "（不是直接用最后一轮），轮次耗尽仍不达标的章节保留原文、不合并。")
        anote.setWordWrap(True)
        anote.setStyleSheet(T("color:#8a93a3;"))
        alay.addWidget(anote)
        arow = QHBoxLayout()
        arow.addWidget(QLabel("相似度阈值："))
        self.auto_thresh_spin = QSpinBox()
        self.auto_thresh_spin.setRange(0, 100)
        self.auto_thresh_spin.setSuffix(" 分")
        self.auto_thresh_spin.setValue(80)
        self.auto_thresh_spin.setToolTip("文风契合度达标线（有参考样本=与样本语感契合度，无样本=去AI味完成度），达到即自动通过")
        arow.addWidget(self.auto_thresh_spin)
        arow.addWidget(QLabel("最大轮次："))
        self.auto_rounds_spin = QSpinBox()
        self.auto_rounds_spin.setRange(1, 999)
        self.auto_rounds_spin.setSuffix(" 轮")
        self.auto_rounds_spin.setValue(3)
        self.auto_rounds_spin.setToolTip("每章最多重写优化几轮：第 1 轮改写后验收，不达标自动带反馈重写，直到达标或达到上限（不设死，自行决断）")
        arow.addWidget(self.auto_rounds_spin)
        arow.addWidget(QLabel("字数容差："))
        self.auto_tol_spin = QSpinBox()
        self.auto_tol_spin.setRange(100, 99999)
        self.auto_tol_spin.setSuffix(" 字")
        self.auto_tol_spin.setValue(500)
        self.auto_tol_spin.setSingleStep(100)
        self.auto_tol_spin.setToolTip("去AI味后与原文允许相差的字数（默认 ±500 字，与正文写作的篇幅标准一致；上限不设死，自行决断）：超出即不通过——保证篇幅基本维持原本的样子")
        arow.addWidget(self.auto_tol_spin)
        arow2 = QHBoxLayout()
        arow2.addWidget(QLabel("前后章节参考："))
        self.auto_nearby_spin = QSpinBox()
        self.auto_nearby_spin.setRange(0, 20)
        self.auto_nearby_spin.setSuffix(" 章")
        self.auto_nearby_spin.setValue(2)
        self.auto_nearby_spin.setToolTip("去AI味/写后校对照前后各几章的衔接参考（人物状态/地点/时间线/"
                                         "已发生事件必须与前后文一致，防剧情偏移）；0=只看本章")
        arow2.addWidget(self.auto_nearby_spin)
        nearby_lbl = QLabel("（去AI味与写后校对共用：AI 对照前后文核对剧情衔接，防止偏移；0=只看本章）")
        nearby_lbl.setStyleSheet(T("color:#8a93a3;"))
        arow2.addWidget(nearby_lbl)
        arow2.addStretch(1)
        self.auto_btn = QPushButton("一键自动去AI味（达标自动合并回原文）")
        self.auto_btn.setObjectName("primary")
        self.auto_btn.clicked.connect(self._start_auto)
        arow.addWidget(self.auto_btn)
        alay.addLayout(arow)
        alay.addLayout(arow2)
        lay.addWidget(autobox)

        # ---------- 操作行（放底部：看着预览/规则决定方案后点开始） ----------
        ops = QHBoxLayout()
        self.start_btn = QPushButton("开始处理（存为待定稿）")
        self.start_btn.setObjectName("primary")
        self.start_btn.clicked.connect(self._start)
        self.stop_btn = QPushButton("停止")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        ops.addWidget(self.start_btn)
        ops.addWidget(self.stop_btn)
        self.progress_lbl = QLabel("")
        self.progress_lbl.setStyleSheet(T("color:#d4a44c;"))
        ops.addWidget(self.progress_lbl)
        ops.addStretch(1)
        lay.addLayout(ops)

    # ---------- 刷新 ----------
    def on_show(self):
        self._load_config_rules()
        self._refresh_chapters()
        self._refresh_drafts()

    def _load_config_rules(self):
        cfg = app_config.load_config()
        rules = cfg.get("deai_rules")
        self.rules_edit.setPlainText(rules if rules else DEAI_DEFAULT_RULES)
        # v1.02 参考文风样本回填（全局配置；留空=只按规则改）
        self.style_ref_edit.setPlainText(cfg.get("deai_style_ref") or "")
        # v1.04 一键自动去AI味验收设置回填（阈值/轮次/字数容差；v1.05 容差改字、默认 500 与正文写作一致）
        self.auto_thresh_spin.setValue(int(cfg.get("deai_auto_threshold", 80) or 80))
        self.auto_rounds_spin.setValue(int(cfg.get("deai_auto_max_rounds", 3) or 3))
        _tol = cfg.get("deai_auto_length_tol")
        try:
            _tol = int(_tol)
        except (TypeError, ValueError):
            _tol = 500
        if _tol <= 50:   # v1.04 旧百分比语义（5-50%）迁移为字（默认 500）
            _tol = 500
        self.auto_tol_spin.setValue(max(100, min(5000, _tol)))
        # v1.07 前后章节参考回填（去AI味与写后校对共用；0=只看本章）
        try:
            _nearby = int(cfg.get("deai_nearby_chapters", 2) or 2)
        except (TypeError, ValueError):
            _nearby = 2
        self.auto_nearby_spin.setValue(max(0, min(20, _nearby)))

    def _save_rules(self):
        cfg = app_config.load_config()
        cfg["deai_rules"] = self.rules_edit.toPlainText().strip()
        cfg["deai_style_ref"] = self.style_ref_edit.toPlainText().strip()
        app_config.save_config(cfg)
        log_fn("info", "去AI味规则与参考文本已保存。")
        self.progress_lbl.setText("规则与参考文本已保存")

    def _reset_rules(self):
        cfg = app_config.load_config()
        cfg.pop("deai_rules", None)
        cfg.pop("deai_style_ref", None)
        app_config.save_config(cfg)
        self.rules_edit.setPlainText(DEAI_DEFAULT_RULES)
        self.style_ref_edit.clear()
        self.progress_lbl.setText("已恢复默认规则并清空参考文本")

    def _refresh_chapters(self):
        store, project = current_project()
        self.ch_list.blockSignals(True)
        self.ch_list.clear()
        if project:
            for i, m in store.chapter_summaries():
                self.ch_list.addItem("第%d章 · %s" % (i, m["title"]))
        self.ch_list.blockSignals(False)
        self.sel_count.setText("已选 0 章")

    def _on_ch_sel(self):
        n = len(self.ch_list.selectedItems())
        self.sel_count.setText("已选 %d 章" % n)
        # 选中章节即把原文加载到预览框（可直接查看/选中文本设为局部重写目标）
        store, project = current_project()
        if not project:
            return
        rows = sorted(r.row() for r in self.ch_list.selectedIndexes())
        all_idx = store.list_chapter_indices()
        if rows and 0 <= rows[0] < len(all_idx):
            ch = store.load_chapter(all_idx[rows[0]])
            if ch:
                self.orig_view.setPlainText(ch.content or "")

    def _selected_chapters(self):
        rows = sorted(r.row() for r in self.ch_list.selectedIndexes())
        indices = []
        store, _ = current_project()
        if store:
            all_idx = store.list_chapter_indices()
            indices = [all_idx[r] for r in rows if 0 <= r < len(all_idx)]
        return indices

    def _mode(self):
        if self.rb_replace.isChecked():
            return "replace"
        if self.rb_rewrite.isChecked():
            return "rewrite"
        return "clean"

    def _directive(self):
        return self.directive_edit.toPlainText().strip()

    # ---------- 处理 ----------
    def _start(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        chapters = self._selected_chapters()
        if not chapters:
            QMessageBox.warning(self, "提示", "请先在左侧勾选要处理的章节。")
            return
        if not busy_guard(self):
            return
        mode = self._mode()
        rules = self.rules_edit.toPlainText().strip() or DEAI_DEFAULT_RULES
        selected_text = ""
        if self.rb_rewrite.isChecked() and self.rb_part.isChecked():
            selected_text = self._sel_text.strip()
            if not selected_text:
                QMessageBox.warning(self, "提示",
                                    "局部重写需要在「原文预览」里选中文本并点「设为局部目标」。")
                return
        directive = self._directive()
        self._queued = list(chapters)
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_lbl.setText("正在处理 0/%d 章…" % len(chapters))
        set_running(True)

        self._worker = _DeaiWorker()
        self._worker.done.connect(self._on_done)
        self._worker.audit.connect(self._on_audit)
        self._worker.finished.connect(self._on_finished)
        _ref = self.style_ref_edit.toPlainText().strip()
        threading.Thread(target=self._worker.run,
                         args=(project, store, chapters, mode, rules, selected_text,
                               directive, True, _ref),
                         daemon=True).start()

    def _start_auto(self):
        """v1.04 一键自动去AI味：批量章节 改写→验收→达标自动合并回原文（未达标带反馈重写）。"""
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        chapters = self._selected_chapters()
        if not chapters:
            QMessageBox.warning(self, "提示", "请先在左侧勾选要自动去AI味的章节。")
            return
        if not busy_guard(self):
            return
        # 验收设置随运行持久化（下次打开自动回填）
        cfg = app_config.load_config()
        cfg["deai_auto_threshold"] = self.auto_thresh_spin.value()
        cfg["deai_auto_max_rounds"] = self.auto_rounds_spin.value()
        cfg["deai_auto_length_tol"] = self.auto_tol_spin.value()
        cfg["deai_nearby_chapters"] = self.auto_nearby_spin.value()   # v1.07 前后章节参考
        app_config.save_config(cfg)
        rules = self.rules_edit.toPlainText().strip() or DEAI_DEFAULT_RULES
        _ref = self.style_ref_edit.toPlainText().strip()
        self._queued = list(chapters)
        self._auto_stop = threading.Event()
        self._auto_done = 0
        self._auto_failed = 0
        self.start_btn.setEnabled(False)
        self.auto_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_lbl.setText("自动去AI味：准备处理 %d 章（阈值 %d 分 · 最多 %d 轮 · 字数容差 ±%d 字）…"
                                  % (len(chapters), self.auto_thresh_spin.value(),
                                     self.auto_rounds_spin.value(), self.auto_tol_spin.value()))
        set_running(True)
        self._auto_worker = _AutoDeaiWorker()
        self._auto_worker.event.connect(self._on_auto_event)
        self._auto_worker.finished.connect(self._on_auto_finished)
        threading.Thread(target=self._auto_worker.run,
                         args=(APP["project_dir"], store, chapters, rules, _ref,
                               self.auto_thresh_spin.value(), self.auto_rounds_spin.value(),
                               self.auto_tol_spin.value(), self._auto_stop),
                         daemon=True).start()

    def _on_auto_event(self, kind, data):
        """自动去AI味进度（主线程槽）：按事件更新状态栏与日志，绝不弹框。"""
        if kind == "chapter_start":
            d = data or {}
            self.progress_lbl.setText("自动去AI味：第 %d/%d 章《%s》开始…"
                                      % (d.get("chapter", 0), d.get("total", 0), d.get("title", "")))
        elif kind == "round_done":
            d = data or {}
            flag = "✓ 通过" if d.get("passed") else "✗ 未达标"
            self.progress_lbl.setText(
                "自动去AI味：第 %d 章 第 %d 轮 → 得分 %.0f（文风 %.0f · 字数差 %d 字 · 剧情%s）%s"
                % (d.get("chapter", 0), d.get("round", 0), d.get("score", 0.0),
                   d.get("tfidf", 0.0), d.get("diff", 0),
                   "一致" if d.get("plot_ok") else "不一致", flag))
            log_fn("info", "自动去AI味第%d章第%d轮：得分%.0f，字数差%d字（原文为基准），剧情%s，%s。"
                   % (d.get("chapter", 0), d.get("round", 0), d.get("score", 0.0),
                      d.get("diff", 0), "一致" if d.get("plot_ok") else "不一致", flag))
        elif kind == "chapter_done":
            d = data or {}
            self._auto_done += 1
            self.progress_lbl.setText("自动去AI味：第 %d 章达标，取最高分第 %d 轮（%.0f 分）已自动合并回原文 ✓"
                                      % (d.get("chapter", 0), d.get("best_round", d.get("rounds", 0)),
                                         d.get("score", 0.0)))
            log_fn("info", "自动去AI味：第 %d 章达标（共 %d 轮，取最高分第 %d 轮 %.0f 分），"
                   "已合并回原文（旧稿备份草稿箱）。"
                   % (d.get("chapter", 0), d.get("rounds", 0), d.get("best_round", 0),
                      d.get("score", 0.0)))
            self._refresh_pages()
        elif kind == "chapter_fail":
            d = data or {}
            self._auto_failed += 1
            self.progress_lbl.setText("自动去AI味：第 %d 章未达标（最高 %d 分/第 %d 轮）：%s（保留原文，未合并）"
                                      % (d.get("chapter", 0), d.get("score", 0.0),
                                         d.get("best_round", 0), d.get("reason", "未知原因")))
            log_fn("warn", "自动去AI味：第 %d 章未达标（最高 %.0f 分/第 %d 轮）：%s（保留原文）。"
                   % (d.get("chapter", 0), d.get("score", 0.0), d.get("best_round", 0),
                      d.get("reason", "未知原因")))
        elif kind == "stopped":
            d = data or {}
            self.progress_lbl.setText("自动去AI味已停止：已通过 %d 章，未达标 %d 章"
                                      "（已合并的保留，未达标的保留原文）。"
                                      % (d.get("passed", 0), d.get("failed", 0)))
            log_fn("warn", "自动去AI味已停止：通过 %d 章，未达标 %d 章。"
                   % (d.get("passed", 0), d.get("failed", 0)))
        elif kind == "error":
            d = data or {}
            self.progress_lbl.setText("自动去AI味出错：%s" % d.get("msg", ""))
            log_fn("error", "自动去AI味出错：%s" % d.get("msg", ""))

    def _on_auto_finished(self):
        self.start_btn.setEnabled(True)
        self.auto_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        set_running(False)
        self.progress_lbl.setText(
            "自动去AI味结束：通过 %d 章 / 未达标 %d 章（达标的已自动合并回原文，未达标的保留原文）。"
            % (getattr(self, "_auto_done", 0), getattr(self, "_auto_failed", 0)))
        log_fn("info", "自动去AI味结束：通过 %d 章 / 未达标 %d 章。"
               % (getattr(self, "_auto_done", 0), getattr(self, "_auto_failed", 0)))

    def _stop(self):
        self._queued = []
        self._auto_stop.set()
        # 立即停止：主动 close 在途 LLM 请求连接（流式读取立刻抛 StopRequested），
        # 不再等当前章/当前轮写完（工作线程已 llm.set_abort(stop_event) 绑定停止事件）
        llm.abort_active_resps()
        self.progress_lbl.setText("正在停止…立即中断当前 LLM 请求（已处理完成的章节保留）。")
        self.stop_btn.setEnabled(False)

    def _on_done(self, idx, err):
        if self._queued:
            self._queued.pop(0)
        if err is None:
            self.progress_lbl.setText("第 %d 章处理完成。" % idx)
        else:
            self.progress_lbl.setText("第 %d 章处理失败：%s" % (idx, err))
        self._refresh_drafts()

    def _on_audit(self, idx, issues):
        """整体审查结果展示：发现的问题数 + 最突出的几类。"""
        if issues:
            n = len(issues)
            probs = []
            for it in issues[:4]:
                p = str(it.get("problem") or "").strip()
                if p and p not in probs:
                    probs.append(p)
            q = str(issues[0].get("quote") or "").strip()
            self.progress_lbl.setText(
                "第 %d 章整体审查：发现 %d 处问题（%s%s）。正在按审查结果处理…"
                % (idx, n, " / ".join(probs[:3]) if probs else "AI味问题",
                   ("；例：「%s…」" % q[:22]) if q else ""))
            log_fn("info", "第 %d 章去AI味整体审查发现 %d 处问题（%s）。"
                   % (idx, n, "、".join(probs[:5]) or "待处理"))
        else:
            self.progress_lbl.setText("第 %d 章整体审查：未发现明显问题，继续按规则处理…" % idx)
            log_fn("info", "第 %d 章去AI味整体审查：未发现明显问题。" % idx)

    def _on_finished(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        set_running(False)
        self.progress_lbl.setText("处理结束：结果在右侧「待定稿」，可对比后应用或丢弃。")
        self._refresh_drafts()

    # ---------- 局部目标 ----------
    def _on_orig_selection(self):
        """原文预览里的鼠标选区即「局部重写」目标（实时生效，无需点按钮）。"""
        sel = self.orig_view.textCursor().selectedText().replace("\u2029", "\n").strip()
        if sel:
            self._sel_text = sel
            self.sel_text_lbl.setText("已选 %d 字（%s…%s）——可直接「开始处理」，也可切换整章/清洗等模式后重新选"
                                      % (len(sel), sel[:20], sel[-10:]))
            self.sel_text_lbl.setStyleSheet(T("color:#d4a44c;"))
            self.rb_rewrite.setChecked(True)
            self.rb_part.setChecked(True)
            self.progress_lbl.setText("局部重写目标已选定（%d 字）" % len(sel))
        else:
            self.sel_text_lbl.setText("未选择（在原文预览里拖选文字即可选中）")
            self.sel_text_lbl.setStyleSheet(T("color:#8a93a3;"))
            self._sel_text = ""

    # ---------- 待定稿操作 ----------
    def _refresh_drafts(self):
        store, project = current_project()
        self.draft_list.blockSignals(True)
        self.draft_list.clear()
        if project:
            for d in store.list_deai_drafts():
                self.draft_list.addItem("第%d章 · %s（%s · %s）"
                                        % (d["chapter"], d["title"],
                                           MODE_TEXT.get(d["mode"], d["mode"]), d["created_at"]))
                self.draft_list.item(self.draft_list.count() - 1).setData(
                    Qt.ItemDataRole.UserRole, d["chapter"])
        self.draft_list.blockSignals(False)
        if self.draft_list.count():
            self.draft_list.setCurrentRow(0)
        else:
            self.orig_view.setPlainText("")
            self.polish_view.setPlainText("")

    def _selected_draft_chapter(self):
        row = self.draft_list.currentRow()
        if row < 0:
            return None
        return self.draft_list.item(row).data(Qt.ItemDataRole.UserRole)

    def _on_draft_sel(self, _row):
        store, project = current_project()
        if not project:
            return
        idx = self._selected_draft_chapter()
        if idx is None:
            return
        ch = store.load_chapter(idx)
        draft = store.load_deai_draft(idx)
        self.orig_view.setPlainText(ch.content if ch else "")
        self.polish_view.setPlainText((draft or {}).get("polished", "") if draft else "")

    def _apply_selected(self):
        store, project = current_project()
        idx = self._selected_draft_chapter()
        if idx is None or not project:
            QMessageBox.warning(self, "提示", "请先在右侧选中一条待定稿。")
            return
        if not busy_guard(self):
            return
        draft = store.load_deai_draft(idx)
        if not draft:
            return
        ret = QMessageBox.question(
            self, "应用润色稿",
            "把第 %d 章的润色稿写回为正式章节？\n写回前会自动备份旧稿到草稿箱，可随时恢复。"
            % idx)
        if ret != QMessageBox.StandardButton.Yes:
            return
        eng = engine_for(APP["project_dir"])
        if not eng.apply_deai(project, idx, draft.get("polished", "")):
            QMessageBox.warning(self, "应用失败", "写入失败：章节缺失或内容为空。")
            return
        store.delete_deai_draft(idx)
        self._refresh_drafts()
        self._refresh_pages()
        log_fn("info", "已把第 %d 章去AI味稿合并回原文。" % idx)

    def _rework_selected(self):
        idx = self._selected_draft_chapter()
        if idx is None:
            return
        store, project = current_project()
        ch = store.load_chapter(idx)
        if not ch:
            return
        if not busy_guard(self):
            return
        mode = self._mode()
        rules = self.rules_edit.toPlainText().strip() or DEAI_DEFAULT_RULES
        directive = self._directive()
        self._queued = [idx]
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.progress_lbl.setText("重新处理第 %d 章…" % idx)
        set_running(True)
        self._worker = _DeaiWorker()
        self._worker.done.connect(self._on_done)
        self._worker.audit.connect(self._on_audit)
        self._worker.finished.connect(self._on_finished)
        _ref = self.style_ref_edit.toPlainText().strip()
        threading.Thread(target=self._worker.run,
                         args=(project, store, [idx], mode, rules, "", directive, True, _ref),
                         daemon=True).start()

    def _discard_selected(self):
        idx = self._selected_draft_chapter()
        if idx is None:
            return
        store, project = current_project()
        if not project:
            return
        ret = QMessageBox.question(self, "丢弃待定稿", "确定丢弃第 %d 章的润色稿？" % idx)
        if ret != QMessageBox.StandardButton.Yes:
            return
        store.delete_deai_draft(idx)
        self._refresh_drafts()
        log_fn("info", "已丢弃第 %d 章的待定稿。" % idx)

    def _merge_all(self):
        store, project = current_project()
        if not project:
            return
        drafts = store.list_deai_drafts()
        if not drafts:
            QMessageBox.information(self, "提示", "没有待定稿。")
            return
        if not busy_guard(self):
            return
        ret = QMessageBox.question(
            self, "全部合并",
            "把全部 %d 章待定稿写回正式章节？每章写回前自动备份旧稿到草稿箱。\n\n%s"
            % (len(drafts), "、".join("第%d章" % d["chapter"] for d in drafts)))
        if ret != QMessageBox.StandardButton.Yes:
            return
        cnt = 0
        for d in drafts:
            idx = d["chapter"]
            draft = store.load_deai_draft(idx)
            if not draft:
                continue
            eng = engine_for(APP["project_dir"])
            if eng.apply_deai(project, idx, draft.get("polished", "")):
                store.delete_deai_draft(idx)
                cnt += 1
        self._refresh_drafts()
        self._refresh_pages()
        log_fn("info", "已把 %d 章去AI味稿合并回原文。" % cnt)
        self.progress_lbl.setText("已合并 %d 章。" % cnt)

    def _export_drafts(self):
        """导出全部待定稿（润色版）为分章 txt 文件夹。"""
        store, project = current_project()
        if not project:
            return
        drafts = store.list_deai_drafts()
        if not drafts:
            QMessageBox.information(self, "提示", "没有待定稿可导出。")
            return
        from PySide6.QtWidgets import QFileDialog
        import os
        import re
        folder = QFileDialog.getExistingDirectory(self, "选择导出目录（每章一个 txt）", "")
        if not folder:
            return
        n = 0
        for d in drafts:
            draft = store.load_deai_draft(d["chapter"])
            if not draft:
                continue
            safe = re.sub(r'[\\/:*?"<>|\n\r]+', "_", d["title"] or "第%d章" % d["chapter"]).strip()
            if not safe:
                safe = "第%d章" % d["chapter"]
            with open(os.path.join(folder, "第%03d章_%s_润色.txt" % (d["chapter"], safe)),
                      "w", encoding="utf-8") as f:
                f.write(draft.get("polished", ""))
            n += 1
        log_fn("info", "已导出 %d 章润色稿到：%s" % (n, folder))
        QMessageBox.information(self, "导出成功",
                                "已导出 %d 章润色稿到：\n%s" % (n, folder))

    def _refresh_pages(self):
        """合并后让其他页面与磁盘一致。"""
        try:
            self.app.page_story.refresh_all()
            self.app.page_generate._update_progress()
        except Exception:
            pass