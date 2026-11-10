# -*- coding: utf-8 -*-
"""生成页：推理过程（浏览器面板）+ 正文编辑 + 逐章/全自动两种模式 + 前文阅读 + 章节管理。"""
import html
import threading

from PySide6.QtCore import QSize, Qt, QObject, QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox,
                               QComboBox, QDialog, QFrame, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMessageBox, QPlainTextEdit, QProgressBar,
                               QPushButton, QRadioButton, QSpinBox,
                               QTableWidget, QTableWidgetItem, QTextBrowser,
                               QVBoxLayout, QWidget)

import config
import llm
import main_ai
from gui_app import APP, bus, busy_guard, current_project, engine_for, set_draft, set_running
from gui_theme import icon, T
from tone_highlighter import CharacterHighlighter, ToneHighlighter, count_tone_hits


class _PromptEdit(QPlainTextEdit):
    """带失焦信号的提示词输入框：失焦即保存，避免用户忘记点保存。"""

    focusOutSignal = Signal()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.focusOutSignal.emit()


class _ReviewWorker(QObject):
    """AI 编辑审稿的后台线程载体（信号跨线程回传结果）。"""

    done = Signal(object)

    def run(self, project, store, chapter):
        try:
            data = main_ai.editor_review_chapter(project, store, chapter)
            if not isinstance(data, dict):
                data = {"error": "审稿结果不是有效 JSON。"}
        except llm.LLMError as e:
            data = {"error": "审稿调用失败：%s" % e}
        except Exception as e:
            data = {"error": "审稿失败：%s" % e}
        self.done.emit(data)


class GeneratePage(QWidget):

    _beats_confirm_req = Signal(object, object, object, object)  # (beats, direction, event, holder)
    _retitle_done = Signal(int, int, int, int)   # v1.03 (ok, fail, start, end)：重设计完成，回主线程弹框

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._beats_confirm_req.connect(self._on_beats_confirm_req)
        self._retitle_done.connect(self._on_retitle_done)
        self._log_items = []   # ("kind", "msg")
        self._main_prompt_synced = None   # (dir_name, text) 主AI提示词最后一次同步值
        self._title_rules_synced = None  # v1.90 (dir_name, rules) 章节标题命名规则最后一次同步值
        self._progress_timer = QTimer(self)   # 进度/列表刷新防抖（草稿与进度日志高频触发时合并成一次）
        self._progress_timer.setSingleShot(True)
        self._progress_timer.setInterval(250)
        self._progress_timer.timeout.connect(self._update_progress)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        # ---------- 进度 ----------
        self.progress_label = QLabel("")
        self.progress_label.setWordWrap(True)
        self.progress_label.setTextFormat(Qt.TextFormat.RichText)
        lay.addWidget(self.progress_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMaximum(0)
        self.progress_bar.setVisible(False)
        lay.addWidget(self.progress_bar)

        # ---------- 本章情节设置（临场指示 + 第 N~M 章写作计划，最显眼位置） ----------
        plan_box = QGroupBox("本章情节设置 — 写作计划按「从第 N 章 到 第 M 章」自动生效，写完对应章节自动移除；"
                             "下方临时指示仅本次生成生效")
        play = QVBoxLayout(plan_box)
        play.setContentsMargins(12, 10, 12, 10)
        play.setSpacing(8)
        # 写作计划：页内直接编辑「从第 N 章 到 第 M 章」+ 内容
        span = QHBoxLayout()
        span.setSpacing(8)
        span.addWidget(QLabel("写作计划：从第"))
        self.plan_start_spin = QSpinBox()
        self.plan_start_spin.setRange(1, 99999)
        self.plan_start_spin.setFixedWidth(90)
        self.plan_start_spin.setMinimumHeight(30)
        self.plan_start_spin.setValue(1)
        span.addWidget(self.plan_start_spin)
        span.addWidget(QLabel("章 到 第"))
        self.plan_end_spin = QSpinBox()
        self.plan_end_spin.setRange(1, 99999)
        self.plan_end_spin.setFixedWidth(90)
        self.plan_end_spin.setMinimumHeight(30)
        self.plan_end_spin.setValue(10)
        span.addWidget(self.plan_end_spin)
        span.addWidget(QLabel("章生效"))
        span.addStretch(1)
        play.addLayout(span)
        self.plan_note_edit = QPlainTextEdit()
        self.plan_note_edit.setMinimumHeight(90)
        self.plan_note_edit.setMaximumHeight(150)
        self.plan_note_edit.setPlaceholderText(
            "这几章的情节怎么写、有什么注意的地方（可写多行）：例：第3~8章推进主角复仇线，"
            "每章结尾留悬念，别让反派提前暴露身份…")
        play.addWidget(self.plan_note_edit)
        plan_row = QHBoxLayout()
        plan_row.setSpacing(8)
        add_plan_btn = QPushButton("＋ 添加到计划")
        add_plan_btn.setObjectName("primary")
        add_plan_btn.setToolTip("把上面的区间与内容加进写作计划；生成到这些章时自动生效")
        add_plan_btn.clicked.connect(self._add_plan)
        del_plan_btn = QPushButton("删除选中")
        del_plan_btn.setToolTip("删除选中的写作计划（不影响已生成的章节）")
        del_plan_btn.clicked.connect(self._del_plan)
        plan_row.addWidget(add_plan_btn)
        plan_row.addWidget(del_plan_btn)
        plan_row.addWidget(QLabel("已生效计划"))
        self.plan_list = QListWidget()
        self.plan_list.setMaximumHeight(110)
        plan_row.addWidget(self.plan_list, 1)
        play.addLayout(plan_row)
        # 本次临时指示
        self.directive = QLineEdit()
        self.directive.setMinimumHeight(38)
        self.directive.setPlaceholderText("本次生成临时指示（可选，仅本次生效）：例：本章让老板娘察觉主角腰间的旧剑，"
                                          "并借对话点出旧剑来历…")
        play.addWidget(self.directive)
        lay.addWidget(plan_box)

        # ---------- 操作行 ----------
        tool = QHBoxLayout()
        gen_btn = QPushButton("生成下一章")
        gen_btn.setObjectName("primary")
        gen_btn.setIcon(icon("pencil", 15))
        gen_btn.setIconSize(QSize(15, 15))
        gen_btn.clicked.connect(self._gen_draft)
        auto_btn = QPushButton("启动全自动连写")
        auto_btn.setIcon(icon("rocket-takeoff", 15))
        auto_btn.setIconSize(QSize(15, 15))
        auto_btn.clicked.connect(self._auto_start)
        stop_btn = QPushButton("停止")
        stop_btn.setObjectName("danger")
        stop_btn.setIcon(icon("stop-circle", 14))
        stop_btn.setIconSize(QSize(14, 14))
        stop_btn.clicked.connect(self._auto_stop)
        tool.addWidget(gen_btn)
        tool.addWidget(auto_btn)
        tool.addWidget(stop_btn)
        tool.addStretch(1)
        lay.addLayout(tool)

        # ---------- 章节标题重设计（v1.01）：按本书类型与书名风格批量重取标题，只改标题不碰正文 ----------
        trow = QHBoxLayout()
        trow.setSpacing(8)
        trow.addWidget(QLabel("章节标题重设计：从第"))
        self.retitle_start_spin = QSpinBox()
        self.retitle_start_spin.setRange(1, 99999)
        self.retitle_start_spin.setFixedWidth(90)
        self.retitle_start_spin.setMinimumHeight(30)
        self.retitle_start_spin.setValue(1)
        trow.addWidget(self.retitle_start_spin)
        trow.addWidget(QLabel("章 到 第"))
        self.retitle_end_spin = QSpinBox()
        self.retitle_end_spin.setRange(1, 99999)
        self.retitle_end_spin.setFixedWidth(90)
        self.retitle_end_spin.setMinimumHeight(30)
        self.retitle_end_spin.setValue(10)
        trow.addWidget(self.retitle_end_spin)
        trow.addWidget(QLabel("章"))
        # v1.81 让 AI 读该章正文再取题（v1.82 改为读完整一章，避免只读开头被铺垫带偏）；取消勾选=只看梗概省 token
        self.retitle_content_chk = QCheckBox("让 AI 阅读章节正文后命名")
        self.retitle_content_chk.setChecked(True)
        self.retitle_content_chk.setToolTip("勾选：AI 会读到每章完整正文（开头铺垫+中间冲突+结尾钩子"
                                            "全看到），依据实际内容取题（默认，取题更准，稍费 token）；"
                                            "取消勾选：只看梗概与原标题取题（省 token，取题精度下降）")
        trow.addWidget(self.retitle_content_chk)
        retitle_btn = QPushButton("重新设计章节名")
        retitle_btn.setObjectName("accent")
        retitle_btn.setToolTip("AI 按本书类型与书名气质重新设计区间内章节的标题：勾选「让 AI 阅读"
                               "章节正文后命名」时每章依据正文实际内容取题（只改标题，不碰正文与"
                               "章节顺序）。取题的风格规则在「项目页 → 文风参考 → ③.8 章节标题"
                               "命名规则」设置，填了就按你的来（最高优先）")
        retitle_btn.clicked.connect(self._retitle_chapters)
        trow.addWidget(retitle_btn)
        trow.addStretch(1)
        lay.addLayout(trow)
        # v1.90 章节标题命名规则：直接放在「重新设计章节名」旁边（与项目页「文风参考」③.8 同一字段，
        # 两处修改互通；失焦自动保存）——用户要求入口就在按钮旁，不去别处翻
        trbox = QGroupBox("章节标题命名规则（可留空=内置通用；填写后 AI 起名/重命名按你的来，最高优先）")
        trlay = QVBoxLayout(trbox)
        trlay.setContentsMargins(8, 6, 8, 6)
        trlay.setSpacing(6)
        self.title_rules_edit = _PromptEdit()
        self.title_rules_edit.setMaximumHeight(76)
        self.title_rules_edit.setPlaceholderText(
            "例：标题要浓缩本章发生的事；文学向含蓄、可用对仗；可用『xx与xx』（两项须是本章"
            "真正并列/对照的要素）；长度 2~8 字；不许连续两章同一种句式。失焦即自动保存；"
            "留空=内置通用规则（按本书类型与书名气质取名）。")
        self.title_rules_edit.focusOutSignal.connect(self._save_title_rules)
        trlay.addWidget(self.title_rules_edit)
        save_tr = QPushButton("保存标题命名规则")
        save_tr.setObjectName("primary")
        save_tr.clicked.connect(self._save_title_rules)
        trlay.addWidget(save_tr, alignment=Qt.AlignmentFlag.AlignLeft)
        reset_tr = QPushButton("重置为默认规则")
        reset_tr.setToolTip("恢复内置默认命名规则（依据网文/文学标题命名经验写就的默认文案）")
        reset_tr.clicked.connect(self._reset_title_rules)
        trlay.addWidget(reset_tr, alignment=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(trbox)

        # 前文速查：已归档章节下拉 + 章节管理/重写 + 主AI管理笔记
        hist = QHBoxLayout()
        hist.addWidget(QLabel("已写章节"))
        self.hist_combo = QComboBox()
        self.hist_combo.setMinimumWidth(260)
        self.hist_combo.setMaxVisibleItems(30)   # 千章级项目时限制下拉弹出渲染项数
        self.hist_combo.setToolTip("查看前面已归档的章节，回忆剧情走向")
        manage_btn = QPushButton("章节管理")
        manage_btn.setIcon(icon("pencil-square", 14))
        manage_btn.setIconSize(QSize(14, 14))
        manage_btn.setToolTip("阅读 / 编辑 / 删除 / 批量操作已归档章节")
        manage_btn.clicked.connect(self._manage_chapters)
        rewrite_btn = QPushButton("重写此章")
        rewrite_btn.setObjectName("danger")
        rewrite_btn.setToolTip("回滚世界状态到该章之前，删除该章及之后章节，重新生成")
        rewrite_btn.clicked.connect(self._rewrite_chapter)
        summary_btn = QPushButton("主AI管理笔记")
        summary_btn.setToolTip("查看主AI压缩的卷信息管理笔记")
        summary_btn.clicked.connect(self._view_summary)
        hist.addWidget(self.hist_combo)
        hist.addWidget(manage_btn)
        hist.addWidget(rewrite_btn)
        hist.addWidget(summary_btn)
        hist.addStretch(1)
        lay.addLayout(hist)

        # 主AI提示词（行动逻辑）：与项目页「文风参考」④主AI全局提示词同一字段，失焦自动保存
        mbox = QGroupBox("主AI提示词（行动逻辑）— 只给主AI，决断/校验/审查/战后更新/压缩全部环节生效；"
                         "与项目页「文风参考」④ 为同一内容，两处修改互通")
        mlay = QVBoxLayout(mbox)
        mlay.setContentsMargins(8, 6, 8, 6)
        mlay.setSpacing(6)
        self.main_prompt = _PromptEdit()
        self.main_prompt.setMaximumHeight(104)
        self.main_prompt.setPlaceholderText(
            "用提示词控制主AI的行动逻辑。例如：「你是一个擅长长线布局的剧情总监：重大转折至少提前3章"
            "埋下暗示，每章结尾留钩子，主线与支线并行但支线不超过两条……」。失焦即自动保存；留空则不启用。")
        self.main_prompt.focusOutSignal.connect(self._save_main_prompt)
        mlay.addWidget(self.main_prompt)
        mrow = QHBoxLayout()
        save_main_btn = QPushButton("保存主AI提示词")
        save_main_btn.setObjectName("primary")
        save_main_btn.clicked.connect(self._save_main_prompt)
        mrow.addWidget(save_main_btn)
        # v2.62 生成前剧情点确认关卡（用户参与可控性：先看主AI规划的本章剧情点，可修改再写正文）
        # v0.63 修复断链：持久化（config 键）+ 全自动连写/凭意见重新生成同样生效（此前只有「生成下一章」生效）
        self.confirm_beats_check = QCheckBox("生成前确认剧情点（校验后弹出，可修改再写正文）")
        self.confirm_beats_check.setToolTip(
            "勾选后：主AI校验完会先弹出本章剧情点清单与走向，你可修改/确认后再开始写正文；"
            "「生成下一章」「凭意见重新生成」「全自动连写」都会弹（一键成书不弹，避免打断全程自动）；"
            "嫌烦可不勾。选择会自动保存，重启软件仍记忆。")
        self.confirm_beats_check.toggled.connect(self._save_confirm_beats)
        mrow.addWidget(self.confirm_beats_check)
        mrow.addStretch(1)
        mlay.addLayout(mrow)
        lay.addWidget(mbox)

        # ---------- 本章草稿（可选）：AI 在草稿基础上扩写润色，禁止改变剧情 ----------
        draft_box = QGroupBox("本章草稿（可选）— AI 以你的草稿为底扩写润色：补足描写、修复与前文文风不一致、"
                              "丰富修辞，可调整叙事结构优化叙事，但禁止改变剧情走向与人物决定")
        dlay = QVBoxLayout(draft_box)
        dlay.setContentsMargins(10, 8, 10, 8)
        dlay.setSpacing(6)
        self.draft_edit = QPlainTextEdit()
        self.draft_edit.setMaximumHeight(130)
        self.draft_edit.setPlaceholderText(
            "把你写的本章草稿粘贴到这里（可详细可粗略，大致情节 + 人物处理细节即可）。\n"
            "生成时 AI 会在此基础上扩写润色成正式正文；留空则完全由 AI 自己写。\n"
            "（草稿只在逐章生成/凭意见重新生成时生效，全自动连写时忽略）")
        dlay.addWidget(self.draft_edit)
        lay.addWidget(draft_box)

        # 操作提示行
        self.hint_label = QLabel("逐章模式：生成后主AI先审查，不满意会自动请正文AI按意见重写（最多2轮）；"
                                 "最终草稿显示在下方，满意点「通过并完成本章」，不满意点「凭意见重新生成」。")
        self.hint_label.setStyleSheet(T("color:#5b6470;"))
        lay.addWidget(self.hint_label)

        # ---------- 推理过程 ----------
        self.log_view = QTextBrowser()
        self.log_view.setOpenExternalLinks(False)
        self.log_view.setHtml(T("<div style='color:#5b6470;font-size:12px;'>推理过程将在此展示……</div>"))
        lay.addWidget(self.log_view, 5)

        # ---------- 本章剧情点（可编辑，v2.55） ----------
        beats_box = QGroupBox("本章剧情点（每行一条，可编辑；改后点「凭意见重新生成」按你的清单写，留空=让主AI规划）")
        blay = QVBoxLayout(beats_box)
        blay.setContentsMargins(10, 8, 10, 8)
        blay.setSpacing(4)
        self.beats_edit = QPlainTextEdit()
        self.beats_edit.setMaximumHeight(70)
        self.beats_edit.setPlaceholderText(
            "例如：\n主角潜入城主府偷到账册\n与陈管家摊牌获知身世线索\n\n"
            "生成后这里会显示主AI规划的剧情点；你可以改成自己的清单再重新生成。")
        blay.addWidget(self.beats_edit)
        lay.addWidget(beats_box)

        # ---------- 正文 ----------
        self.content = QPlainTextEdit()
        self.content.setPlaceholderText("生成草稿后，可在此修改正文再归档，或点击「凭意见重新生成」。")
        lay.addWidget(self.content, 6)
        # v0.47/v0.48 AI 八股套话实时高亮 + 角色名着色（金色波浪线标记 AI 味措辞）
        self._tone_hi = ToneHighlighter(self.content.document())
        self._tone_words = []
        self._char_hi = None
        ctr = QHBoxLayout()
        ctr.addStretch(1)
        # v0.53 AI 段落工具：选中正文任意文本 → 润色/扩写/缩写/去AI味 → 就地替换
        self.polish_btn = QPushButton("AI 段落工具")
        self.polish_btn.setObjectName("zoomLabel")
        self.polish_btn.setIcon(icon("magic", 14))
        self.polish_btn.setIconSize(QSize(14, 14))
        self.polish_btn.setToolTip("选中正文中的一段文字，交给 AI 润色/扩写/缩写/去AI味，结果可预览后替换")
        self.polish_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.polish_btn.clicked.connect(self._polish_selected)
        ctr.addWidget(self.polish_btn)
        # v0.49 语音码字：说一段话自动识别中文，插入光标处（需联网 + 麦克风）
        self.voice_btn = QPushButton("语音码字")
        self.voice_btn.setObjectName("zoomLabel")
        self.voice_btn.setIcon(icon("mic", 14))
        self.voice_btn.setIconSize(QSize(14, 14))
        self.voice_btn.setToolTip("用语音输入正文：说一段话自动识别为中文，插入到光标处。\n"
                                  "点击后在弹窗里直接说话，说完停顿几秒自动结束；需要联网（免费识别服务）与麦克风。")
        self.voice_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.voice_btn.clicked.connect(self._voice_input)
        ctr.addWidget(self.voice_btn)
        self.tone_count = QLabel("套话 0")
        self.tone_count.setObjectName("zoomLabel")
        self.tone_count.setToolTip("正文中疑似 AI 八股套话的命中数（可据此手动润色，或交给「去 AI 味」）")
        ctr.addWidget(self.tone_count)
        self.content_count = QLabel("0 字")
        self.content_count.setObjectName("zoomLabel")
        self.content_count.setToolTip("本章正文当前字数")
        ctr.addWidget(self.content_count)
        lay.addLayout(ctr)
        self.content.textChanged.connect(self._update_content_count)

        # ---------- 审查按钮 ----------
        btns = QHBoxLayout()
        self.final_btn = QPushButton("通过并完成本章")
        self.final_btn.setObjectName("primary")
        self.final_btn.setIcon(icon("check-circle", 15))
        self.final_btn.setIconSize(QSize(15, 15))
        self.final_btn.clicked.connect(self._finalize)
        self.regen_btn = QPushButton("凭意见重新生成")
        self.regen_btn.setIcon(icon("arrow-clockwise", 14))
        self.regen_btn.setIconSize(QSize(14, 14))
        self.regen_btn.clicked.connect(self._regenerate)
        btns.addWidget(self.final_btn)
        btns.addWidget(self.regen_btn)
        btns.addStretch(1)
        lay.addLayout(btns)

        bus.log.connect(self._on_log)
        bus.draft.connect(self._on_draft)
        bus.running.connect(self._on_running)

    # ---------- 刷新 ----------
    def on_show(self):
        self._update_progress()
        self._refresh_plans()
        # v0.48 编辑器实时监测刷新：自定义禁词 + 角色名着色（名称一致性）
        cfg = config.load_config()
        self._tone_words = cfg.get("tone_words_custom") or []
        self._tone_hi.set_extra_words(self._tone_words)
        # v0.63 剧情点确认开关回填（持久化）
        self.confirm_beats_check.blockSignals(True)
        self.confirm_beats_check.setChecked(bool(cfg.get("confirm_beats_enabled", False)))
        self.confirm_beats_check.blockSignals(False)
        store, project = current_project()
        if store:
            names = [n for _i, n, _s in store.list_characters()]
            if self._char_hi is None:
                self._char_hi = CharacterHighlighter(self.content.document(), names)
            else:
                self._char_hi.set_names(names)
        self._update_content_count()

    # ---------- 剧情点确认开关（v0.63：勾选即保存，重启记忆） ----------
    def _save_confirm_beats(self, _val=None):
        from gui_app import log_fn
        cfg = config.load_config()
        cfg["confirm_beats_enabled"] = self.confirm_beats_check.isChecked()
        config.save_config(cfg)
        config._cache = None
        log_fn("info", "剧情点确认开关已保存（勾选=%s）"
               % ("开" if cfg["confirm_beats_enabled"] else "关"))

    # ---------- 正文实时字数 / AI 套话计数（v0.46/v0.47） ----------
    def _update_content_count(self):
        text = self.content.toPlainText()
        self.content_count.setText("%d 字" % len(text))
        self.tone_count.setText("套话 %d" % count_tone_hits(
            text, getattr(self, "_tone_words", None)))

    # ---------- 语音码字（v0.49） ----------
    def _voice_input(self):
        """打开语音输入对话框：识别结果插入正文光标处。"""
        from gui_voice import VoiceInputDialog
        dlg = VoiceInputDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.value():
            text = dlg.value()
            cur = self.content.textCursor()
            cur.insertText(text)
            self.content.setTextCursor(cur)
            self.content.setFocus()
            log_fn("info", "语音输入 %d 字" % len(text))

    # ---------- AI 段落工具（v0.53） ----------
    def _polish_selected(self):
        """把正文选中的一段交给 AI 处理（润色/扩写/缩写/去AI味），结果可替换选中。"""
        cur = self.content.textCursor()
        text = cur.selectedText().replace("\u2029", "\n").strip()
        if not text:
            QMessageBox.information(self, "提示", "请先在正文中选中要处理的一段文字。")
            return
        dlg = PolishParagraphDialog(text, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_text = dlg.result_text()
            if not new_text:
                return
            cur.beginEditBlock()
            cur.removeSelectedText()
            cur.insertText(new_text)
            cur.endEditBlock()
            self.content.setTextCursor(cur)
            self.content.setFocus()
            log_fn("info", "AI 段落工具：%d 字 → %d 字" % (len(text), len(new_text)))

    # ---------- 章节写作计划（第 N~M 章自动生效） ----------
    def _refresh_plans(self):
        store, project = current_project()
        self.plan_list.blockSignals(True)
        self.plan_list.clear()
        if project:
            for p in project.chapter_plans or []:
                if not isinstance(p, dict):
                    continue
                s, e = int(p.get("start", 0) or 0), int(p.get("end", 0) or 0)
                note = str(p.get("note") or "").replace("\n", " ")
                self.plan_list.addItem("第%d~%d章：%s" % (s, e, note[:42]))
        self.plan_list.blockSignals(False)

    def _add_plan(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        s = self.plan_start_spin.value()
        e = self.plan_end_spin.value()
        if e < s:
            e = s
        note = self.plan_note_edit.toPlainText().strip()
        if not note:
            QMessageBox.warning(self, "提示", "计划内容不能为空。")
            return
        plan = {"start": s, "end": e, "note": note}
        # 同区间已有计划则覆盖，避免重复
        project.chapter_plans = [p for p in (project.chapter_plans or [])
                                 if not (isinstance(p, dict)
                                         and int(p.get("start", 0) or 0) == s
                                         and int(p.get("end", 0) or 0) == e)]
        project.chapter_plans.append(plan)
        store.save_project(project)
        self.plan_note_edit.clear()
        self._refresh_plans()
        from gui_app import log_fn
        log_fn("info", "已添加写作计划：第 %d~%d 章（%s）" % (s, e, note[:30]))

    def _del_plan(self):
        store, project = current_project()
        row = self.plan_list.currentRow()
        if not project or row < 0:
            QMessageBox.warning(self, "提示", "请先选中一条写作计划。")
            return
        plans = project.chapter_plans or []
        if 0 <= row < len(plans):
            ret = QMessageBox.question(self, "删除写作计划",
                                       "确定删除这条写作计划？\n%s" % (
                                           "第%d~%d章：%s" % (
                                               int(plans[row].get("start", 0)),
                                               int(plans[row].get("end", 0)),
                                               str(plans[row].get("note", ""))[:60])))
            if ret != QMessageBox.StandardButton.Yes:
                return
            plans.pop(row)
            store.save_project(project)
        self._refresh_plans()

    def _update_progress(self):
        store, project = current_project()
        self._refresh_history(store, project)
        # 主AI提示词同步（切换项目、或项目页修改后回到生成页时刷新输入框；输入框聚焦时不打扰）
        if project:
            cur = (project.dir_name, project.story_main_prompt or "")
            if cur != self._main_prompt_synced and not self.main_prompt.hasFocus():
                self.main_prompt.setPlainText(cur[1])
                self._main_prompt_synced = cur
        elif self._main_prompt_synced is not None:
            self._main_prompt_synced = None
        # 章节标题命名规则同步（与项目页文风参考 ③.8 同字段；聚焦时不打扰）
        if project:
            from prompts import DEFAULT_TITLE_RULES as _DTR
            cur2 = (project.dir_name, project.story_title_rules or _DTR)
            if cur2 != self._title_rules_synced and not self.title_rules_edit.hasFocus():
                self.title_rules_edit.setPlainText(cur2[1])
                self._title_rules_synced = cur2
        elif self._title_rules_synced is not None:
            self._title_rules_synced = None
        if not project:
            self.progress_label.setText("<b>尚未载入项目。</b>")
            return
        state = project.state
        written = int(state.get("next_chapter", 1)) - 1
        target = project.chapter_target()
        if target > 0:
            rank = min(written, target)
            vol_text = "本卷目标：已完成 <b>%d/%d</b> 章" % (rank, target)
            self.progress_bar.setMaximum(target)
            self.progress_bar.setValue(rank)
        else:
            vol_text = "本卷：已写 %d 章（无硬性章数目标，主AI把控节奏）" % written
            self.progress_bar.setMaximum(0)
            self.progress_bar.setValue(0)
        st = "完结" if state.get("story_complete") else ("生成中…" if APP["running"] else "空闲")
        self.progress_label.setText(
            T("<span style='color:#d4a44c;'>当前项目：%s</span>　|　状态：%s<br>%s")
            % (project.title, st, vol_text))

    # ---------- 前文阅读 ----------
    def _refresh_history(self, store, project):
        """刷新「已写章节」下拉列表（含全部已归档章节；走轻量索引，不逐章读全文）。"""
        self.hist_combo.blockSignals(True)
        cur = self.hist_combo.currentData()
        self.hist_combo.clear()
        if project:
            for i, m in store.chapter_summaries():
                self.hist_combo.addItem("第%d章·%s" % (i, m["title"]), i)
            if cur is not None:
                idx = self.hist_combo.findData(cur)
                if idx >= 0:
                    self.hist_combo.setCurrentIndex(idx)
        self.hist_combo.blockSignals(False)

    def _rewrite_chapter(self):
        """从选中的章节起重写：回滚世界状态 + 删后续章节 + 重新生成该章。"""
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        idx = self.hist_combo.currentData()
        if idx is None:
            QMessageBox.information(self, "提示", "还没有已归档章节可重写。")
            return
        ret = QMessageBox.question(
            self, "重写章节",
            "将从第 %d 章开始重写：\n"
            "1. 世界状态（全部角色卡 / 信息库 / 伏笔 / 主AI管理笔记）回滚到第 %d 章开始前；\n"
            "2. 删除第 %d 章及之后的所有章节；\n"
            "3. 立即重新生成第 %d 章。\n\n"
            "此操作不可撤销，确定继续？" % (idx, idx, idx, idx))
        if ret != QMessageBox.StandardButton.Yes:
            return
        if not self._stop_if_busy():
            return
        set_running(True)

        def work():
            try:
                eng = engine_for(APP["project_dir"])
                ok = eng.rewrite_from(project, int(idx))
                if not ok:
                    return
                # 重新载入项目（回滚后进度已更新），清掉旧草稿再生成
                store2, project2 = current_project()
                set_draft(None)
                log_fn("info", "世界状态已回滚，正在重新生成第 %d 章…" % idx)
                chapter = eng.generate_draft(project2, user_directive="")
                if chapter:
                    set_draft(chapter)
            except llm.LLMError as e:
                self._log_err("重写失败：%s" % e)
            except Exception as e:
                self._log_err("重写失败：%s" % e)
            finally:
                set_running(False)

        threading.Thread(target=work, daemon=True).start()

    def _view_summary(self):
        """查看主AI管理笔记（压缩卷信息）。"""
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        SummaryViewDialog(project.story_summary or "", self).exec()

    def _retitle_chapters(self):
        """v1.01 章节标题重设计：AI 按本书类型与书名风格，批量重取第 start~end 章标题。
        只改标题，不碰正文与章节顺序；后台线程跑 LLM，完成提示成功/失败数。"""
        if not self._stop_if_busy():
            return
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        start = self.retitle_start_spin.value()
        end = self.retitle_end_spin.value()
        if start > end:
            start, end = end, start
        if store.load_chapter(start) is None:
            QMessageBox.warning(self, "提示", "第 %d 章还不存在，无法重设计章节名。"
                                % start)
            return
        set_running(True)
        self._save_title_rules()   # v1.90 重命名前先用输入框里的规则（失焦可能未触发自动保存）
        self._on_log("info", "开始重设计第 %d~%d 章章节名（按本书类型与书名气质）…" % (start, end))

        def work():
            try:
                import main_ai as _mai_rt
                ok, fail = _mai_rt.retitle_chapters(
                    project, store, start, end,
                    with_content=self.retitle_content_chk.isChecked())
                self._on_log("info", "章节标题重设计完成：成功 %d 章，未处理 %d 章（原标题保留）。"
                             % (ok, fail))
                # v1.03 修复：QMessageBox 必须在主线程弹——后台线程只发信号，主线程槽里弹框/刷新
                self._retitle_done.emit(ok, fail, start, end)
            except llm.LLMError as e:
                self._log_err("章节标题重设计失败：%s" % e)
            except ValueError as e:
                self._log_err("章节标题重设计失败：%s" % e)
            except Exception as e:
                self._log_err("章节标题重设计失败：%s" % e)
            finally:
                set_running(False)

        threading.Thread(target=work, daemon=True).start()

    def _on_retitle_done(self, ok, fail, start, end):
        """v1.03 主线程槽：重设计完成后的弹框与章节列表刷新（后台线程不得直接弹 QMessageBox）。"""
        if ok:
            QMessageBox.information(
                self, "完成",
                "已按本书类型与书名风格重新设计 %d 章标题（第 %d~%d 章）。\n"
                "只改了标题，正文与章节顺序未动。\n\n未处理 %d 章保留原标题。"
                % (ok, start, end, fail))
            self._update_progress()   # 内部刷新「已写章节」下拉

    def _save_title_rules(self):
        """v1.90 章节标题命名规则保存（生成页；与项目页「文风参考」③.8 同一字段，失焦/点按钮均触发）。"""
        store, project = current_project()
        if not project:
            return
        text = self.title_rules_edit.toPlainText().strip()
        if text == (project.story_title_rules or ""):
            self._title_rules_synced = (project.dir_name, text)
            return  # 无变化不落盘
        project.story_title_rules = text
        store.save_project(project)
        self._title_rules_synced = (project.dir_name, text)
        from gui_app import log_fn
        log_fn("info", "章节标题命名规则已保存（AI 起名/重命名时执行）。" if text
               else "已清空章节标题命名规则（恢复内置通用规则）。")

    def _reset_title_rules(self):
        """v1.91 重置为内置默认命名规则（与提示词内置默认同一文本，DEFAULT_TITLE_RULES）。"""
        from prompts import DEFAULT_TITLE_RULES
        self.title_rules_edit.setPlainText(DEFAULT_TITLE_RULES)
        self._save_title_rules()

    def _save_main_prompt(self):
        """保存主AI提示词到项目（与项目页「文风参考」④同一字段，失焦/点按钮均触发）。"""
        store, project = current_project()
        if not project:
            return
        text = self.main_prompt.toPlainText().strip()
        if text == (project.story_main_prompt or ""):
            self._main_prompt_synced = (project.dir_name, text)
            return  # 无变化不落盘
        project.story_main_prompt = text
        store.save_project(project)
        self._main_prompt_synced = (project.dir_name, text)
        from gui_app import log_fn
        log_fn("info", "主AI提示词已保存（%d 字，仅主AI生效）。" % len(text))

    def _manage_chapters(self):
        """打开章节管理（阅读/编辑/删除）。"""
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        ChapterManagerDialog(self.app).exec()

    # ---------- 日志渲染（追加式，避免每来一行全量 setHtml 重排） ----------
    def _on_log(self, kind, msg):
        if kind == "progress":
            self._schedule_progress()
            return
        icon = {"warn": "▲ ", "error": "✖ "}.get(kind, "")
        self._log_items.append((kind, icon + msg))
        colors = {"info": T("#d7dce4"), "warn": T("#c9a832"), "error": T("#c96f6f")}
        div = "<div style='color:%s;margin:3px 0;font-size:13px;'>%s</div>" % (
            colors.get(kind, T("#d7dce4")), (icon + msg).replace("<", "&lt;"))
        cursor = self.log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(div)
        bar = self.log_view.verticalScrollBar()
        bar.setValue(bar.maximum())
        if len(self._log_items) > 600:
            self._log_items = self._log_items[-300:]
            self._rebuild_log_view()

    def _rebuild_log_view(self):
        """日志超量裁剪后全量重建一次（600 行内保持追加式渲染）。"""
        colors = {"info": T("#d7dce4"), "warn": T("#c9a832"), "error": T("#c96f6f")}
        divs = ["<div style='color:%s;margin:3px 0;font-size:13px;'>%s</div>"
                % (colors.get(k, T("#d7dce4")), m.replace("<", "&lt;"))
                for k, m in self._log_items]
        self.log_view.setHtml("".join(divs))
        bar = self.log_view.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _schedule_progress(self):
        """进度/列表刷新防抖：高频事件合并为一次（250ms），避免生成时反复全量刷新。"""
        if not self._progress_timer.isActive():
            self._progress_timer.start()

    # ---------- 草稿 ----------
    def _ask_beats(self, beats, direction):
        """生成前剧情点确认回调（后台线程调用）：把清单交给主线程弹窗，等用户结果后继续。"""
        import threading as _th
        ev = _th.Event()
        holder = {}
        self._beats_confirm_req.emit(beats, direction, ev, holder)
        ev.wait()
        return holder.get("result")

    def _on_beats_confirm_req(self, beats, direction, ev, holder):
        dlg = BeatsConfirmDialog(beats, direction, self)
        try:
            if dlg.exec() == QDialog.DialogCode.Accepted:
                holder["result"] = dlg.value()
        finally:
            ev.set()

    def _current_beats(self):
        """生成页剧情点：非空行列表；无输入返回 None（=让主AI规划，v2.55）。"""
        lines = [ln.strip() for ln in self.beats_edit.toPlainText().splitlines() if ln.strip()]
        return lines or None

    def _on_draft(self, chapter):
        if chapter is None:
            self.content.setPlainText("")
            self.beats_edit.setPlainText("")
        else:
            self.content.setPlainText(chapter.content)
            # 展示主AI规划的本章剧情点（v2.52，随草稿携带），用户可改后重新生成（v2.55）
            beats = (chapter.reasoning or {}).get("beats") or []
            self.beats_edit.setPlainText("\n".join(beats))
        self._schedule_progress()

    def _on_running(self, flag):
        self.progress_bar.setVisible(flag)
        if not flag:
            self._update_progress()

    # ---------- 动作 ----------
    def _check_project(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return None
        return store, project

    def _stop_if_busy(self):
        from gui_app import busy_guard
        return busy_guard(self)

    def _gen_draft(self):
        store, project = self._check_project()
        if not project or not self._stop_if_busy():
            return
        directive = self.directive.text().strip()
        draft = self.draft_edit.toPlainText().strip()
        set_running(True)

        def work():
            try:
                eng = engine_for(APP["project_dir"])
                eng.ensure_world(project)
                beats_confirm = (self._ask_beats if self.confirm_beats_check.isChecked()
                                 else None)
                chapter = eng.generate_draft(project, user_directive=directive,
                                             user_draft=draft,
                                             beats_confirm=beats_confirm)
                if chapter:
                    set_draft(chapter)
            except llm.LLMError as e:
                self._log_err("生成失败：%s" % e)
            except Exception as e:
                self._log_err("生成失败：%s" % e)
            finally:
                set_running(False)

        threading.Thread(target=work, daemon=True).start()

    def _finalize(self):
        store, project = self._check_project()
        chapter = APP["draft"]
        if not chapter:
            QMessageBox.warning(self, "提示", "暂无可完成章节，请先生成草稿。")
            return
        if not self._stop_if_busy():
            return
        chapter.content = self.content.toPlainText().strip()
        if not chapter.content:
            QMessageBox.warning(self, "提示", "正文为空，无法完成本章。")
            return
        set_running(True)

        def work():
            try:
                eng = engine_for(APP["project_dir"])
                eng.finalize_chapter(project, chapter)
                set_draft(None)
            except Exception as e:
                self._log_err("归档失败：%s" % e)
            finally:
                set_running(False)

        threading.Thread(target=work, daemon=True).start()

    def _regenerate(self):
        store, project = self._check_project()
        if not APP["draft"]:
            QMessageBox.warning(self, "提示", "请先生成草稿。")
            return
        if not self._stop_if_busy():
            return
        feedback = self.content.toPlainText().strip()
        draft = self.draft_edit.toPlainText().strip()
        set_running(True)

        def work():
            try:
                eng = engine_for(APP["project_dir"])
                beats_confirm = (self._ask_beats
                                 if self.confirm_beats_check.isChecked() else None)
                new_ch = eng.generate_draft(project,
                                            user_feedback=feedback[:2000] if feedback else "整体重写，保持主线",
                                            user_draft=draft,
                                            beats_override=self._current_beats(),
                                            beats_confirm=beats_confirm)
                if new_ch:
                    set_draft(new_ch)
            except Exception as e:
                self._log_err("重新生成失败：%s" % e)
            finally:
                set_running(False)

        threading.Thread(target=work, daemon=True).start()

    def _auto_start(self):
        store, project = self._check_project()
        if not project or not self._stop_if_busy():
            return
        import threading as _th
        import llm as _llm
        APP["stop"] = False
        if APP["stop_ev"] is None:
            APP["stop_ev"] = _th.Event()
        else:
            APP["stop_ev"].clear()
        set_running(True)

        def work():
            _llm.set_abort(APP["stop_ev"])
            try:
                eng = engine_for(APP["project_dir"])
                eng.ensure_world(project)
                beats_confirm = (self._ask_beats
                                 if self.confirm_beats_check.isChecked() else None)
                eng.auto_run(project, stop_check=lambda: APP["stop"],
                             beats_confirm=beats_confirm)
            except _llm.StopRequested:
                self._log_err("已停止：立即中断当前章节写作（已归档章节保留，可继续）。")
            except Exception as e:
                self._log_err("自动生成中断：%s" % e)
            finally:
                _llm.set_abort(None)
                set_running(False)

        threading.Thread(target=work, daemon=True).start()

    def _auto_stop(self):
        APP["stop"] = True
        if APP.get("stop_ev") is not None:
            APP["stop_ev"].set()   # 立即中断当前 LLM 请求（不再等本章写完）
        # v1.103 与其它页面（对话/拆书/导入/一键成书等）对齐：主动 close 在途流式连接，
        # 阻塞读取立刻抛异常转 StopRequested——避免停止滞后一个数据块、或卡在流中段。
        import llm as _llm
        _llm.abort_active_resps()

    # ---------- 一键成书（v0.54） ----------
    def _book_start(self):
        """打开一键成书对话框：描述 + 章数 → AI 自动立项连写（可停止）。"""
        from gui_app import APP, busy_guard
        if busy_guard(self):
            return
        from gui_book import AutoBookDialog
        dlg = AutoBookDialog(self.app)
        dlg.exec()

    def _log_err(self, msg):
        from gui_app import log_fn
        log_fn("error", msg)


class ChapterViewDialog(QDialog):
    """只读阅读弹窗：查看已归档章节全文（标题/卷/出场角色/正文）。"""

    def __init__(self, chapter, store, parent=None):
        super().__init__(parent)
        self.setWindowTitle("已写章节 · %s" % (chapter.title or "第%d章" % chapter.index))
        self.resize(780, 680)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        viewer = QTextBrowser()
        viewer.setOpenExternalLinks(False)
        from gui_story import _chapter_meta_html
        md = T("<h2 style='color:#e8c87a;'>%s</h2>") % html.escape(chapter.title or "第%d章" % chapter.index)
        names = []
        for cid in chapter.characters or []:
            card, _ = store.load_character(cid)
            names.append(card.name if card else cid)
        md += T("<p style='color:#8a93a3;'>第%d卷 · 出场角色：%s</p>") % (
            chapter.volume, html.escape("、".join(names) or "无"))
        md += _chapter_meta_html(chapter, store)
        md += T("<hr style='border-color:#262e3a;'>")
        md += "<div style='line-height:1.8;'>" + html.escape(chapter.content or "").replace("\n", "<br>") + "</div>"
        viewer.setHtml(md)
        lay.addWidget(viewer, 1)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


class SummaryViewDialog(QDialog):
    """只读弹窗：查看主AI管理笔记（压缩卷信息）。"""

    def __init__(self, summary, parent=None):
        super().__init__(parent)
        self.setWindowTitle("主AI管理笔记")
        self.resize(680, 520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)
        tip = QLabel("这是主AI每隔若干章把前文剧情与各项信息归纳概括成的「管理笔记」，"
                     "用于全局把控剧情、回顾前文发生了什么。生成页/故事页均可查看。")
        tip.setWordWrap(True)
        tip.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lay.addWidget(tip)
        view = QTextBrowser()
        view.setPlainText(summary if summary.strip() else
                          "（还没有管理笔记——每 5 章或卷末主AI会自动压缩生成。）")
        lay.addWidget(view, 1)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)


class ChapterManagerDialog(QDialog):
    """章节管理：列出全部已归档章节，单选操作 / 多选批量阅读与批量删除。"""

    _bg_done = Signal(object)   # (label, result)：后台落盘/git 归档完成后回主线程刷新

    def __init__(self, win=None):
        """win: MainWindow（用于操作后刷新生成页与故事页）。"""
        super().__init__(win)
        self.win = win
        self._bg_busy = False
        self.setWindowTitle("章节管理")
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)
        self._bg_done.connect(self._on_bg_done)

        tip = QLabel("单击选中一章做单章操作；Ctrl/Shift 多选后可「连续阅读」或「批量删除」（一次确认）。\n"
                     "「删除本章及之后」会回滚世界状态（角色卡/信息库/伏笔/管理笔记）到本章开始前；"
                     "「仅删除本章」保留后续章节。所有删除前都会自动备份到草稿箱。")
        tip.setWordWrap(True)
        tip.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lay.addWidget(tip)

        self.listw = QListWidget()
        self.listw.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.listw.itemSelectionChanged.connect(self._update_btn_state)
        lay.addWidget(self.listw, 1)

        # 行1：单章操作 / 批量操作
        b1 = QHBoxLayout()
        self.view_btn = QPushButton("阅读")
        self.view_btn.setToolTip("只读查看本章全文")
        self.view_btn.clicked.connect(self._view)
        self.edit_btn = QPushButton("编辑…")
        self.edit_btn.setObjectName("primary")
        self.edit_btn.setToolTip("修改本章标题与正文")
        self.edit_btn.clicked.connect(self._edit)
        self.review_btn = QPushButton("编辑审稿")
        self.review_btn.setToolTip("让 AI 以资深编辑视角通读本章，给情节/人设/文风/节奏/伏笔等全面修改意见")
        self.review_btn.clicked.connect(self._editor_review)
        self.del_btn = QPushButton("删除…")
        self.del_btn.setObjectName("danger")
        self.del_btn.setToolTip("删除本章（可选：仅本章 / 本章及之后并回滚世界状态）")
        self.del_btn.clicked.connect(self._delete)
        self.read_multi_btn = QPushButton("连续阅读")
        self.read_multi_btn.setToolTip("把选中的多章按顺序拼接，一口气读完")
        self.read_multi_btn.clicked.connect(self._read_selected)
        self.del_multi_btn = QPushButton("删除选中…")
        self.del_multi_btn.setObjectName("danger")
        self.del_multi_btn.setToolTip("批量删除选中的章节（一次确认，删除前自动备份到草稿箱）")
        self.del_multi_btn.clicked.connect(self._delete_selected)
        b1.addWidget(self.view_btn)
        b1.addWidget(self.edit_btn)
        b1.addWidget(self.review_btn)
        b1.addWidget(self.del_btn)
        b1.addWidget(self.read_multi_btn)
        b1.addWidget(self.del_multi_btn)
        lay.addLayout(b1)

        # 行2：排序/查找/统计 + 草稿箱 + 导出
        b2 = QHBoxLayout()
        swap_btn = QPushButton("交换章节…")
        swap_btn.setIcon(icon("arrows-move", 14))
        swap_btn.setIconSize(QSize(14, 14))
        swap_btn.setToolTip("交换两章内容（互换标题/正文/出场角色等，用于调整章节顺序）。\n"
                            "交换前自动把两章旧版备份到草稿箱")
        swap_btn.clicked.connect(self._swap)
        search_btn = QPushButton("全文搜索")
        search_btn.setIcon(icon("search", 14))
        search_btn.setIconSize(QSize(14, 14))
        search_btn.setToolTip("在当前项目全部章节的标题/梗概/正文中查找关键词，点击结果直接阅读")
        search_btn.clicked.connect(self._search)
        stats_btn = QPushButton("写作统计")
        stats_btn.setIcon(icon("journal-text", 14))
        stats_btn.setIconSize(QSize(14, 14))
        stats_btn.setToolTip("总字数/各卷分布/当前卷进度一览")
        stats_btn.clicked.connect(self._stats)
        drafts_btn = QPushButton("草稿箱")
        drafts_btn.setIcon(icon("clock-history", 14))
        drafts_btn.setIconSize(QSize(14, 14))
        drafts_btn.setToolTip("重写/删除/编辑章节前自动备份的旧版，可查看/恢复找回")
        drafts_btn.clicked.connect(self._drafts)
        export_btn = QPushButton("导出小说（txt+分章）")
        export_btn.setObjectName("primary")
        export_btn.setIcon(icon("download", 15))
        export_btn.setIconSize(QSize(15, 15))
        export_btn.setToolTip("把全部已写章节导出为完整拼接 txt + 分章文件夹（每章一个 txt）")
        export_btn.clicked.connect(self._export)
        epub_btn = QPushButton("导出 EPUB")
        epub_btn.setIcon(icon("book-half", 14))
        epub_btn.setIconSize(QSize(14, 14))
        epub_btn.setToolTip("导出为 EPUB3 电子书（手机/阅读器可直接打开阅读）")
        epub_btn.clicked.connect(self._export_epub)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        b2.addWidget(swap_btn)
        b2.addWidget(search_btn)
        b2.addWidget(stats_btn)
        b2.addWidget(drafts_btn)
        b2.addWidget(export_btn)
        b2.addWidget(epub_btn)
        b2.addStretch(1)
        b2.addWidget(close_btn)
        lay.addLayout(b2)

        for b in (self.view_btn, self.edit_btn, self.review_btn, self.del_btn,
                  self.read_multi_btn, self.del_multi_btn,
                  swap_btn, search_btn, stats_btn, drafts_btn, export_btn, epub_btn):
            b.setCursor(Qt.CursorShape.PointingHandCursor)

        self._refresh()

    # ---------- 内部 ----------
    def _selected(self):
        """返回当前选中的章节号列表（按章节号排序），无选中返回空列表。"""
        store, project = current_project()
        if not project:
            return []
        indices = store.list_chapter_indices()
        rows = sorted(r.row() for r in self.listw.selectedIndexes())
        return [indices[r] for r in rows if 0 <= r < len(indices)]

    def _first_selected(self):
        sel = self._selected()
        return sel[0] if sel else None

    def _update_btn_state(self):
        n = len(self._selected())
        for b in (self.view_btn, self.edit_btn, self.review_btn, self.del_btn):
            b.setEnabled(n == 1)
        for b in (self.read_multi_btn, self.del_multi_btn):
            b.setEnabled(n >= 2)

    def _refresh(self):
        store, project = current_project()
        self.listw.blockSignals(True)
        self.listw.clear()
        if project:
            for i, m in store.chapter_summaries():
                st = {"approved": "已归档", "draft": "草稿"}.get(m["status"], m["status"])
                self.listw.addItem("第%d章 · %s（%s · %d字）"
                                   % (i, m["title"], st, m["chars"]))
        self.listw.blockSignals(False)
        if self.listw.count():
            self.listw.setCurrentRow(0)
        self._update_btn_state()

    # ---------- 后台落盘 / git 归档（避免主线程 git add -A 全仓库扫描卡界面） ----------
    def _set_busy(self, flag):
        self._bg_busy = flag
        for b in (self.view_btn, self.edit_btn, self.review_btn, self.del_btn,
                  self.read_multi_btn, self.del_multi_btn, ):
            b.setEnabled(not flag)
        if not flag:
            self._update_btn_state()

    def _bg(self, label, fn):
        """后台线程执行 fn()（含引擎操作与 git 归档），完成后经信号回主线程刷新。

        fn 应返回结果；异常会记日志并以 None 收尾（界面照常恢复，不弹错）。
        """
        self._set_busy(True)

        def work():
            try:
                result = fn()
            except Exception as e:
                from gui_app import log_fn
                log_fn("warn", "%s失败：%s" % (label, e))
                result = None
            self._bg_done.emit((label, result))

        threading.Thread(target=work, daemon=True).start()

    def _on_bg_done(self, payload):
        label, result = payload
        self._set_busy(False)
        from gui_app import log_fn
        if label == "编辑保存":
            if result:
                self._refresh()
                self._refresh_pages()
                log_fn("info", "第 %d 章已编辑保存。" % result)
        elif label == "交换章节":
            if result:
                a, b = result
                self._refresh()
                self._refresh_pages()
                log_fn("info", "第 %d 章与第 %d 章已交换（旧版备份在草稿箱）。" % (a, b))
            else:
                QMessageBox.warning(self, "提示",
                                    "交换失败：章节不存在或章号非法/相同（未做任何修改）。")
        elif label == "删除":
            if result is not None:
                self._refresh()
                self._refresh_pages()
                log_fn("info", "第 %d 章已删除。" % result)
            else:
                QMessageBox.warning(self, "提示",
                                    "回滚失败（该章之前没有世界状态快照），未删除任何章节。")
        elif label == "批量删除":
            if result:   # 删除章数 > 0
                self._refresh()
                self._refresh_pages()
                log_fn("info", "已批量删除 %d 章。" % result)

    def closeEvent(self, event):
        if self._bg_busy:
            QMessageBox.information(
                self, "提示", "正在后台处理（保存/删除/归档）…请稍候，完成后即可关闭。")
            event.ignore()
            return
        super().closeEvent(event)

    def _refresh_pages(self):
        """操作后让生成页/故事页与磁盘一致。"""
        if not self.win:
            return
        try:
            self.win.page_generate._update_progress()
            self.win.page_story.refresh_all()
        except Exception:
            pass

    # ---------- 动作 ----------
    def _view(self):
        idx = self._first_selected()
        store, project = current_project()
        if idx is None or not project:
            return
        ch = store.load_chapter(idx)
        if not ch:
            QMessageBox.warning(self, "提示", "章节数据缺失。")
            return
        ChapterViewDialog(ch, store, self).exec()

    def _read_selected(self):
        """连续阅读：把选中的多章按顺序拼接弹窗。"""
        sel = self._selected()
        store, project = current_project()
        if len(sel) < 2 or not project:
            return
        MultiChapterDialog(store, sel, self).exec()

    def _edit(self):
        idx = self._first_selected()
        store, project = current_project()
        if idx is None or not project:
            return
        ch = store.load_chapter(idx)
        if not ch:
            QMessageBox.warning(self, "提示", "章节数据缺失。")
            return
        dlg = ChapterEditDialog(ch, store, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._bg("编辑保存", lambda: self._do_edit(dlg.chapter, idx))

    def _do_edit(self, ch, idx):
        """后台：编辑章节（含旧稿备份与 git 归档）。返回章节号。"""
        eng = engine_for(APP["project_dir"])
        eng.edit_chapter(ch)
        return idx

    def _delete(self):
        idx = self._first_selected()
        store, project = current_project()
        if idx is None or not project:
            return
        ch = store.load_chapter(idx)
        if not ch:
            QMessageBox.warning(self, "提示", "章节数据缺失。")
            return
        dlg = DeleteChapterDialog(idx, ch.title or "第%d章" % idx, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        self._bg("删除", lambda: self._do_delete(project, idx, dlg.rollback_mode))

    def _do_delete(self, project, idx, rollback_mode):
        """后台：删除章节（含世界回滚/git 归档）。回滚失败返回 None。"""
        eng = engine_for(APP["project_dir"])
        if rollback_mode:
            ok = eng.rollback_delete_from(project, idx)
            return idx if ok else None
        eng.delete_chapter_only(project, idx)
        return idx

    def _delete_selected(self):
        """批量删除选中的多章（一次确认，删除前逐章备份到草稿箱）。"""
        sel = self._selected()
        store, project = current_project()
        if len(sel) < 2 or not project:
            return
        names = []
        for i in sel:
            ch = store.load_chapter(i)
            names.append("第%d章《%s》" % (i, ch.title if ch else "未命名"))
        preview = "\n".join(names[:8]) + ("\n…共 %d 章" % len(names) if len(names) > 8 else "")
        ret = QMessageBox.question(
            self, "批量删除章节",
            "将一次删除选中的 %d 章：\n%s\n\n"
            "删除前会自动备份到草稿箱（可找回）；不回滚世界状态；"
            "若删除了最新章节，进度自动回退。\n确定删除？" % (len(names), preview))
        if ret != QMessageBox.StandardButton.Yes:
            return
        self._bg("批量删除", lambda: self._do_delete_selected(project, sel))

    def _do_delete_selected(self, project, sel):
        """后台：批量删除（含逐章备份与 git 归档）。返回实际删除章数。"""
        eng = engine_for(APP["project_dir"])
        return eng.delete_chapters_bulk(project, sel)

    def _editor_review(self):
        """AI 编辑审稿：后台调用，完成后弹窗展示结构化意见。"""
        idx = self._first_selected()
        store, project = current_project()
        if idx is None or not project:
            return
        ch = store.load_chapter(idx)
        if not ch:
            QMessageBox.warning(self, "提示", "章节数据缺失。")
            return
        if not busy_guard(self):
            return
        self.review_btn.setEnabled(False)
        self.review_btn.setText("审稿中…")
        worker = _ReviewWorker()
        worker.done.connect(self._on_review_ready)
        self._worker = worker  # 防 GC
        threading.Thread(target=worker.run, args=(project, store, ch), daemon=True).start()

    # ---------- 交换章节 / 全文搜索 / 写作统计（v0.53 写作工作台） ----------
    def _swap(self):
        """交换两章内容（排序）：选中的一章 + 手动输入另一章号。"""
        sel = self._first_selected()
        store, project = current_project()
        if sel is None or not project:
            QMessageBox.information(self, "提示", "请先在列表选中一章，作为交换的第一章。")
            return
        ch = store.load_chapter(sel)
        a_title = ch.title if ch else "第%d章" % sel
        dlg = QDialog(self)
        dlg.setWindowTitle("交换章节")
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        lay.addWidget(QLabel("把「第%d章《%s》」与哪一章交换？" % (sel, a_title)))
        row = QHBoxLayout()
        row.addWidget(QLabel("目标章号"))
        b_spin = QSpinBox()
        b_spin.setRange(1, 99999)
        b_spin.setValue(sel + 1 if sel < 99999 else 1)
        row.addWidget(b_spin)
        row.addStretch(1)
        lay.addLayout(row)
        hint = QLabel("交换 = 两章的标题/正文/出场角色/场景/卷归属互换（章号不变，便于调整叙事顺序）。\n"
                      "交换前自动把两章旧版备份到草稿箱；交换完成后会 git 存档，可在草稿箱找回。")
        hint.setWordWrap(True)
        hint.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lay.addWidget(hint)
        br = QHBoxLayout()
        ok_btn = QPushButton("交换")
        ok_btn.setObjectName("primary")
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(dlg.reject)
        br.addStretch(1)
        br.addWidget(ok_btn)
        br.addWidget(cancel_btn)
        lay.addLayout(br)

        def _do():
            b = b_spin.value()
            if b == sel:
                QMessageBox.warning(dlg, "提示", "两章不能相同。")
                return
            dlg.accept()
            self._bg("交换章节", lambda: self._do_swap(sel, b))

        ok_btn.clicked.connect(_do)
        dlg.exec()

    def _do_swap(self, a, b):
        """后台：交换两章内容（含旧稿备份与 git 归档）。返回 (a, b) 或 None。"""
        eng = engine_for(APP["project_dir"])
        return (a, b) if eng.swap_chapters(a, b) else None

    def _search(self):
        """全文搜索：全部章节标题/梗概/正文关键词，结果可双击阅读。"""
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        dlg = SearchDialog(self)
        dlg.exec()

    def _stats(self):
        """写作统计：总字数/各卷分布/当前卷进度。"""
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        StatsDialog(store, self).exec()

    def _on_review_ready(self, data):
        self.review_btn.setEnabled(True)
        self.review_btn.setText("编辑审稿")
        if not isinstance(data, dict) or data.get("error"):
            QMessageBox.warning(self, "审稿失败", str(data.get("error", "未知错误")))
            return
        ReviewResultDialog(data, self).exec()

    def _drafts(self):
        """打开草稿箱（重写/删除/编辑前自动备份的旧章节，可查看/恢复）。"""
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        DraftsDialog(self.win).exec()

    def _export(self):
        """导出全部已写章节（完整 txt + 分章文件夹），与故事页导出同一实现。"""
        from gui_story import export_novel
        export_novel(self)

    def _export_epub(self):
        """导出 EPUB3 电子书，与故事页导出同一实现。"""
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        indices = store.list_chapter_indices()
        if not indices:
            QMessageBox.warning(self, "提示", "还没有已写章节可导出。")
            return
        from PySide6.QtWidgets import QFileDialog
        from gui_app import log_fn
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


class ChapterEditDialog(QDialog):
    """编辑已归档章节：标题 + 正文，保存即落盘并 git 存档。"""

    def __init__(self, chapter, store, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑章节 · 第%d章《%s》" % (chapter.index, chapter.title or "未命名"))
        self.resize(780, 620)
        self.chapter = chapter
        self.store = store
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)
        lay.addWidget(QLabel("标题"))
        self.title_edit = QLineEdit(chapter.title or "第%d章" % chapter.index)
        lay.addWidget(self.title_edit)
        lay.addWidget(QLabel("正文（保存后写入章节文件并 git 存档）"))
        self.content_edit = QPlainTextEdit()
        self.content_edit.setPlainText(chapter.content or "")
        lay.addWidget(self.content_edit, 1)
        btns = QHBoxLayout()
        save_btn = QPushButton("保存修改")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(save_btn)
        btns.addWidget(cancel_btn)
        lay.addLayout(btns)

    def _save(self):
        title = self.title_edit.text().strip()
        content = self.content_edit.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "提示", "正文不能为空。")
            return
        ch = self.chapter
        ch.title = title if title else "第%d章" % ch.index
        ch.content = content
        # 落盘与 git 归档由章节管理对话框在后台线程执行（避免主线程 git add -A 卡界面）
        self.accept()


class DeleteChapterDialog(QDialog):
    """删除章节确认：选择「仅删本章」或「删本章及之后（世界回滚）」。"""

    def __init__(self, ch_no, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle("删除第 %d 章" % ch_no)
        self.rollback_mode = True
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(12)
        head = QLabel("确定要删除「第 %d 章 · %s」吗？此操作不可撤销。" % (ch_no, title))
        head.setWordWrap(True)
        lay.addWidget(head)
        self.rb_rollback = QRadioButton("删除本章及之后所有章节（世界状态回滚到本章开始前 · 推荐）")
        self.rb_rollback.setChecked(True)
        self.rb_rollback.setToolTip("角色卡/信息库/伏笔/管理笔记回到本章开始前；本章与之后章节全部删除，"
                                    "进度回到本章，可直接继续生成补写。")
        self.rb_single = QRadioButton("仅删除本章（保留之后的章节，编号不变，不回滚世界状态）")
        rb_hint = QLabel("提示：若只是某章写崩了想重写，也可用生成页的「重写此章」（回滚后自动重新生成）。")
        rb_hint.setWordWrap(True)
        rb_hint.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        lay.addWidget(self.rb_rollback)
        lay.addWidget(self.rb_single)
        lay.addWidget(rb_hint)
        btns = QHBoxLayout()
        del_btn = QPushButton("删除")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._ok)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(del_btn)
        btns.addWidget(cancel_btn)
        lay.addLayout(btns)

    def _ok(self):
        self.rollback_mode = self.rb_rollback.isChecked()
        self.accept()


class ReviewResultDialog(QDialog):
    """显示 AI 编辑审稿结果（结构化意见），可复制全文。"""

    def __init__(self, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑审稿意见")
        self.resize(760, 620)
        self.data = data
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        html_out = T("<h2 style='color:#e8c87a;'>审稿意见：%s</h2>") % html.escape(str(data.get("verdict") or "—"))
        strengths = data.get("strengths") or []
        if strengths:
            html_out += T("<p style='color:#7dae7d;'><b>优点：</b>%s</p>") % "；".join(
                html.escape(str(s)) for s in strengths)
        issues = data.get("issues") or []
        if issues:
            html_out += T("<p style='color:#c96f6f;'><b>问题：</b></p><ul>")
            for it in issues:
                if isinstance(it, dict):
                    html_out += "<li><b>[%s]</b> %s</li>" % (html.escape(str(it.get("category", "其他"))),
                                                              html.escape(str(it.get("detail", ""))))
                else:
                    html_out += "<li>%s</li>" % html.escape(str(it))
            html_out += "</ul>"
        sugs = data.get("suggestions") or []
        if sugs:
            html_out += T("<p style='color:#d4a44c;'><b>修改建议：</b></p><ul>")
            for s in sugs:
                html_out += "<li>%s</li>" % html.escape(str(s))
            html_out += "</ul>"
        html_out += T("<hr style='border-color:#262e3a;'><div style='line-height:1.7;'>%s</div>") % (
            html.escape(str(data.get("overall") or "")))
        view = QTextBrowser()
        view.setHtml(html_out)
        lay.addWidget(view, 1)

        btns = QHBoxLayout()
        copy_btn = QPushButton("复制全文")
        copy_btn.clicked.connect(self._copy)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btns.addStretch(1)
        btns.addWidget(copy_btn)
        btns.addWidget(close_btn)
        lay.addLayout(btns)

    def _copy(self):
        d = self.data
        issues = "\n".join(
            "- [%s] %s" % (i.get("category", "其他"), i.get("detail", ""))
            if isinstance(i, dict) else "- %s" % i for i in (d.get("issues") or []))
        sugs = "\n".join("- %s" % s for s in (d.get("suggestions") or []))
        txt = "审稿意见：%s\n\n优点：%s\n\n问题：\n%s\n\n修改建议：\n%s\n\n总评：%s" % (
            d.get("verdict", ""), "；".join(str(s) for s in (d.get("strengths") or [])),
            issues, sugs, d.get("overall", ""))
        QApplication.clipboard().setText(txt)


class SearchDialog(QDialog):
    """全文搜索（v0.53）：在当前项目全部章节的标题/梗概/正文中查找关键词。"""

    def __init__(self, win=None):
        super().__init__(win)
        self.setWindowTitle("全文搜索")
        self.resize(720, 520)
        self.win = win
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        row = QHBoxLayout()
        row.addWidget(QLabel("关键词"))
        self.kw = QLineEdit()
        self.kw.setPlaceholderText("输入要查找的词（标题/梗概/正文全文）")
        self.kw.returnPressed.connect(self._go)
        row.addWidget(self.kw, 1)
        go_btn = QPushButton("搜索")
        go_btn.setObjectName("primary")
        go_btn.clicked.connect(self._go)
        row.addWidget(go_btn)
        lay.addLayout(row)

        self.listw = QListWidget()
        self.listw.setWordWrap(True)
        self.listw.itemDoubleClicked.connect(self._open)
        lay.addWidget(self.listw, 1)
        self.hint = QLabel("结果双击可直接阅读对应章节。")
        self.hint.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lay.addWidget(self.hint)
        ok_btn = QPushButton("关闭")
        ok_btn.clicked.connect(self.accept)
        lay.addWidget(ok_btn, 0, Qt.AlignmentFlag.AlignRight)

    def _go(self):
        kw = self.kw.text().strip()
        if not kw:
            return
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        self.listw.clear()
        self.hint.setText("搜索中…")
        QApplication.processEvents()

        def work():
            try:
                return store.search_chapters(kw)
            except Exception:
                return []

        import queue
        q = queue.Queue()

        def _put():
            q.put(work())

        t = threading.Thread(target=_put, daemon=True)
        t.start()
        t.join(timeout=8)
        results = q.get() if not q.empty() else []
        self.hint.setText("共 %d 条结果" % len(results))
        if not results:
            self.listw.addItem("（未找到包含「%s」的章节）" % kw)
            return
        where_t = {"title": "标题", "brief": "梗概", "content": "正文"}
        for r in results:
            self.listw.addItem(
                "第%d章《%s》· %s\n%s"
                % (r["seq"], r["title"], where_t.get(r["where"], "正文"),
                   r["snippet"] or "（无预览）"))
            self.listw.item(self.listw.count() - 1).setData(
                Qt.ItemDataRole.UserRole, r["seq"])

    def _open(self, item):
        seq = item.data(Qt.ItemDataRole.UserRole)
        if not seq:
            return
        store, project = current_project()
        ch = store.load_chapter(int(seq))
        if ch:
            ChapterViewDialog(ch, store, self).exec()


class StatsDialog(QDialog):
    """写作统计（v0.53）：总字数/各卷分布/当前卷进度。"""

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.setWindowTitle("写作统计")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(12)
        stats = store.project_stats()
        total = stats.get("total_chars", 0)
        title = QLabel("<h2 style='margin:0;'>写作统计</h2>")
        lay.addWidget(title)
        target = stats.get("target") or 0
        prog_txt = ("%.1f%%（%d / %d 章）" % (stats.get("progress") or 0,
                                              stats.get("chapters", 0), target)
                    if target else "%d 章" % stats.get("chapters", 0))
        head = QLabel(T("总字数 <b style='font-size:22px;color:#e8c87a;'>%s</b> 字 · 已完成 %s")
                      % (format(total, ","), prog_txt))
        head.setWordWrap(True)
        lay.addWidget(head)
        if target:
            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(int(stats.get("progress") or 0))
            bar.setFormat("当前卷进度 %p%")
            lay.addWidget(bar)
        vols = stats.get("volume_chars") or []
        if vols:
            tbl = QTableWidget(len(vols), 3)
            tbl.setHorizontalHeaderLabels(["卷号", "章节数", "字数"])
            tbl.verticalHeader().setVisible(False)
            tbl.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            tbl.horizontalHeader().setStretchLastSection(True)
            total_chars = 0
            for r, v in enumerate(vols):
                tbl.setItem(r, 0, QTableWidgetItem("第 %d 卷" % v["vol"]))
                tbl.setItem(r, 1, QTableWidgetItem(str(v["count"])))
                tbl.setItem(r, 2, QTableWidgetItem(format(v["chars"], ",")))
                total_chars += v["chars"]
            lay.addWidget(tbl)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        lay.addWidget(close_btn, 0, Qt.AlignmentFlag.AlignRight)


class PolishParagraphDialog(QDialog):
    """AI 段落工具（v0.53）：把选中的一段文字交给 AI 润色/扩写/缩写/去AI味。

    结果可反复换模式处理；「替换选中文本」把结果写回编辑器并关闭。
    """

    _done = Signal(object)   # 段落处理结果（文本）

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI 段落工具")
        self.setMinimumWidth(640)
        self.resize(720, 560)
        self._text = text
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        head = QLabel("把选中的这段文字交给 AI 处理（原段 %d 字）：" % len(text.strip()))
        head.setWordWrap(True)
        lay.addWidget(head)

        row = QHBoxLayout()
        row.addWidget(QLabel("处理方式"))
        self.mode = QComboBox()
        self.mode.addItem("文笔润色（polish）", "polish")
        self.mode.addItem("扩写补足（expand）", "expand")
        self.mode.addItem("精简浓缩（shorten）", "shorten")
        self.mode.addItem("去AI味（deai）", "deai")
        row.addWidget(self.mode)
        # v1.67 附加要求输入：缩写成一半 / 保留所有对白 / 去AI味但保留口语等，优先级最高
        self.directive_edit = QLineEdit()
        self.directive_edit.setPlaceholderText("附加要求（可选）：如 缩写成一半 / 保留全部对白 / 去AI味但口语自然…")
        self.directive_edit.setClearButtonEnabled(True)
        row.addWidget(self.directive_edit, 1)
        self.run_btn = QPushButton("开始处理")
        self.run_btn.setObjectName("primary")
        self.run_btn.clicked.connect(self._run)
        row.addWidget(self.run_btn)
        row.addStretch(1)
        lay.addLayout(row)

        # 原文（只读，供对照）
        orig_box = QGroupBox("原文")
        olay = QVBoxLayout(orig_box)
        self.orig_view = QPlainTextEdit()
        self.orig_view.setPlainText(text)
        self.orig_view.setReadOnly(True)
        self.orig_view.setMaximumHeight(170)
        olay.addWidget(self.orig_view)
        lay.addWidget(orig_box)

        res_box = QGroupBox("AI 处理结果（可手动微调后替换）")
        rlay = QVBoxLayout(res_box)
        self.res_view = QPlainTextEdit()
        rlay.addWidget(self.res_view)
        lay.addWidget(res_box, 1)

        self.hint = QLabel("")
        self.hint.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lay.addWidget(self.hint)
        # v1.68 段落工具上下文开关（与设置页/码字页同键 tool_ctx_*，改动即存 config，下次调用生效）
        ctx_row = QHBoxLayout()
        ctx_row.setSpacing(8)
        ctx_lab = QLabel("任务上下文")
        ctx_lab.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        ctx_row.addWidget(ctx_lab)
        self.ctx_style_chk = QCheckBox("正文AI文风")
        self.ctx_notes_chk = QCheckBox("故事设定+笔记")
        self.ctx_rp_chk = QCheckBox("人物读取推理")
        ctx_tip = ("控制本次处理附带多少上下文（与码字页/设置页是同一组开关）：\n"
                   "· 正文AI文风：正文AI提示词 + 文风参考/风格要点；\n"
                   "· 故事设定+笔记：剧情发展/世界观/特殊规则 + 管理笔记/重要角色档案/灵感/知识库；\n"
                   "· 人物读取推理：按近几章出场 + 笔记点名的角色卡读取并推理其言行。\n"
                   "默认全开保证效果；省 token 时可关。")
        for chk in (self.ctx_style_chk, self.ctx_notes_chk, self.ctx_rp_chk):
            chk.setToolTip(ctx_tip)
            chk.toggled.connect(self._save_ctx_switches)
            ctx_row.addWidget(chk)
        ctx_row.addStretch(1)
        lay.addLayout(ctx_row)
        self._done.connect(self._on_done)
        # 打开对话框时回填当前 config 的上下文开关（toggled 已连 _save_ctx_switches 自动保存）
        try:
            import config as _cfg168
            _c168 = _cfg168.load_config()
            self.ctx_style_chk.setChecked(bool(_c168.get("tool_ctx_style", True)))
            self.ctx_notes_chk.setChecked(bool(_c168.get("tool_ctx_notes", True)))
            self.ctx_rp_chk.setChecked(bool(_c168.get("tool_ctx_rp", True)))
        except Exception:
            pass

        btns = QHBoxLayout()
        copy_btn = QPushButton("复制结果")
        copy_btn.clicked.connect(self._copy)
        replace_btn = QPushButton("替换选中文本")
        replace_btn.setObjectName("primary")
        replace_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btns.addStretch(1)
        btns.addWidget(copy_btn)
        btns.addWidget(replace_btn)
        btns.addWidget(cancel_btn)
        lay.addLayout(btns)

    def _run(self):
        text = self._text.strip()
        if not text:
            QMessageBox.warning(self, "提示", "没有可处理的文本。")
            return
        if len(text) > 6000:
            QMessageBox.warning(self, "提示", "选中文本过长（最多 6000 字），请分段处理。")
            return
        project = current_project()[1]
        if project is None:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        self.run_btn.setEnabled(False)
        self.run_btn.setText("处理中…")
        self.hint.setText("正在调用模型处理…")
        mode = str(self.mode.currentData() or "polish")
        directive = self.directive_edit.text().strip()
        store = current_project()[0]
        worker = _PolishWorker()
        worker.done.connect(self._on_done)
        self._worker = worker   # 防 GC
        threading.Thread(target=worker.run,
                         args=(project, text, mode, directive),
                         kwargs={"store": store}, daemon=True).start()

    # v1.68 段落工具上下文开关：对话框打开回填 config，改动即存（与码字页/设置页同键）
    def _save_ctx_switches(self, _chk=None):
        import config as _cfg168
        cfg = _cfg168.load_config()
        cfg["tool_ctx_style"] = self.ctx_style_chk.isChecked()
        cfg["tool_ctx_notes"] = self.ctx_notes_chk.isChecked()
        cfg["tool_ctx_rp"] = self.ctx_rp_chk.isChecked()
        _cfg168.save_config(cfg)

    def _on_done(self, payload):
        self.run_btn.setEnabled(True)
        self.run_btn.setText("开始处理")
        if isinstance(payload, dict) and payload.get("error"):
            self.hint.setText("")
            QMessageBox.warning(self, "处理失败", str(payload["error"]))
            return
        out = payload if isinstance(payload, str) else ""
        self.res_view.setPlainText(out)
        self.hint.setText("处理完成（%d 字），可微调后「替换选中文本」。" % len(out.strip()))

    def _copy(self):
        QApplication.clipboard().setText(self.res_view.toPlainText())
        self.hint.setText("已复制。")

    def result_text(self):
        return self.res_view.toPlainText().strip()


class _PolishWorker(QObject):
    """AI 段落处理的后台线程载体。"""

    done = Signal(object)

    def run(self, project, text, mode, directive="", store=None):
        try:
            # v1.02 段落工具沿用全局「去AI味参考文风样本」（模仿语感，不抄内容）
            import config as _cfg_mod
            _ref = (_cfg_mod.load_config().get("deai_style_ref") or "")
            # v1.67 附加要求（优先级最高，如缩写成一半/保留全部对白）直接透传；
            # v1.68 store 传入时启用涉及人物读取推理（ctx 开关由设置页 tool_ctx_* 控制）
            out = main_ai.polish_paragraph(project, text, mode, style_ref=_ref,
                                           directive=directive, store=store)
            if not out:
                out = {"error": "模型返回为空，请重试。"}
        except Exception as e:
            out = {"error": "%s" % e}
        self.done.emit(out)


class DraftsDialog(QDialog):
    """草稿箱：重写/删除/编辑章节前自动备份的旧版，可查看/恢复为正式章节/删除备份。"""

    def __init__(self, win=None):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("草稿箱（旧章节备份）")
        self.resize(760, 520)
        self.eng = engine_for(APP["project_dir"])
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)
        tip = QLabel("「重写此章」「删除章节」「编辑章节」前会自动把旧版备份到这里。\n"
                     "可查看备份内容、恢复为正式章节（写回章节文件，覆盖同章号现有内容）、删除备份。\n"
                     "恢复只写回章节本身，不自动回滚世界状态（角色卡/伏笔等）。")
        tip.setWordWrap(True)
        tip.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lay.addWidget(tip)

        self.listw = QListWidget()
        lay.addWidget(self.listw, 1)

        btns = QHBoxLayout()
        view_btn = QPushButton("查看")
        view_btn.clicked.connect(self._view)
        restore_btn = QPushButton("恢复为正式章节")
        restore_btn.setObjectName("primary")
        restore_btn.clicked.connect(self._restore)
        del_btn = QPushButton("删除此备份")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._delete)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btns.addWidget(view_btn)
        btns.addWidget(restore_btn)
        btns.addWidget(del_btn)
        btns.addStretch(1)
        btns.addWidget(close_btn)
        lay.addLayout(btns)
        self._refresh()

    def _refresh(self):
        self.listw.clear()
        tag_txt = {"rewrite": "重写前", "delete": "删除前", "edit": "编辑前"}
        for d in self.eng.store.list_chapter_drafts():
            item = "%s（%s · %s）" % (d["title"] or "第%d章" % d["index"],
                                      tag_txt.get(d["tag"], d["tag"]), d["saved_at"])
            self.listw.addItem(item)
            self.listw.item(self.listw.count() - 1).setData(Qt.ItemDataRole.UserRole, d["fname"])
        if self.listw.count():
            self.listw.setCurrentRow(0)

    def _selected_fname(self):
        row = self.listw.currentRow()
        if row < 0:
            return None
        return self.listw.item(row).data(Qt.ItemDataRole.UserRole)

    def _view(self):
        fname = self._selected_fname()
        if not fname:
            return
        ch = self.eng.store.load_chapter_draft(fname)
        if not ch:
            QMessageBox.warning(self, "提示", "备份数据缺失或已损坏。")
            return
        ChapterViewDialog(ch, self.eng.store, self).exec()

    def _restore(self):
        fname = self._selected_fname()
        if not fname:
            return
        if not busy_guard(self):
            return
        ret = QMessageBox.question(
            self, "恢复草稿",
            "将把这份备份写回为正式章节（若该章号当前有内容会被覆盖）。\n"
            "确定恢复？")
        if ret != QMessageBox.StandardButton.Yes:
            return
        ch = self.eng.store.restore_chapter_draft(fname)
        if not ch:
            QMessageBox.warning(self, "提示", "恢复失败：备份数据缺失或已损坏。")
            return
        self._refresh()
        if self.win:
            try:
                self.win.page_generate._update_progress()
                self.win.page_story.refresh_all()
            except Exception:
                pass
        from gui_app import log_fn
        log_fn("info", "已从草稿箱恢复第 %d 章《%s》为正式章节。" % (ch.index, ch.title))

    def _delete(self):
        fname = self._selected_fname()
        if not fname:
            return
        ret = QMessageBox.question(self, "删除备份", "确定删除这份备份？删除后不可恢复。")
        if ret != QMessageBox.StandardButton.Yes:
            return
        self.eng.store.delete_chapter_draft(fname)
        self._refresh()


class MultiChapterDialog(QDialog):
    """连续阅读多章：把选中的章节按顺序拼接显示，可复制全文。"""

    def __init__(self, store, indices, parent=None):
        super().__init__(parent)
        idxs = sorted(int(i) for i in indices)
        self.setWindowTitle("连续阅读 · 第 %d-%d 章（共 %d 章）"
                            % (idxs[0], idxs[-1], len(idxs)))
        self.resize(800, 720)
        self.idxs = idxs
        self.store = store
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)

        chunks = []
        for i in idxs:
            ch = store.load_chapter(i)
            if not ch:
                continue
            chunks.append(T("<h2 style='color:#e8c87a;margin-top:18px;'>%s</h2>")
                          % html.escape(ch.title or "第%d章" % i))
            names = []
            for cid in ch.characters or []:
                card, _ = store.load_character(cid)
                names.append(card.name if card else cid)
            chunks.append(T("<p style='color:#8a93a3;'>第%d卷 · 出场角色：%s</p>")
                          % (ch.volume, html.escape("、".join(names) or "无")))
            chunks.append(T("<hr style='border-color:#262e3a;'>"))
            chunks.append("<div style='line-height:1.8;'>%s</div>"
                          % html.escape(ch.content or "").replace("\n", "<br>"))
        view = QTextBrowser()
        view.setHtml("".join(chunks))
        lay.addWidget(view, 1)

        btns = QHBoxLayout()
        copy_btn = QPushButton("复制全部")
        copy_btn.clicked.connect(self._copy_all)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        btns.addStretch(1)
        btns.addWidget(copy_btn)
        btns.addWidget(close_btn)
        lay.addLayout(btns)

    def _copy_all(self):
        parts = []
        for i in self.idxs:
            ch = self.store.load_chapter(i)
            if not ch:
                continue
            parts.append("%s\n%s\n\n%s" % (ch.title or "第%d章" % i, "-" * 30, ch.content))
        QApplication.clipboard().setText("\n\n".join(parts))


class BeatsConfirmDialog(QDialog):
    """生成前剧情点确认弹窗（v2.62）：展示主AI规划的本章剧情点与走向，用户可修改/跳过。

    value() 返回：修改后的剧情点列表（非空）或 None（跳过确认，沿用主AI规划）。
    """

    def __init__(self, beats, direction, parent=None):
        super().__init__(parent)
        self.setWindowTitle("确认本章剧情点")
        self.resize(560, 460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)
        tip = QLabel("主AI已规划本章剧情点（每行一条，可增删改；正文将逐条完成）：")
        tip.setWordWrap(True)
        tip.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lay.addWidget(tip)
        self.edit = QPlainTextEdit()
        self.edit.setPlainText("\n".join(beats or []))
        self.edit.setMinimumHeight(150)
        lay.addWidget(self.edit)
        lay.addWidget(QLabel("本章走向（主AI裁定）："))
        dirlbl = QLabel(str(direction or "")[:200])
        dirlbl.setWordWrap(True)
        dirlbl.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        lay.addWidget(dirlbl)
        row = QHBoxLayout()
        use_btn = QPushButton("用我的剧情点")
        use_btn.setObjectName("primary")
        use_btn.clicked.connect(self.accept)
        skip_btn = QPushButton("跳过（沿用主AI规划）")
        skip_btn.clicked.connect(self.reject)
        row.addWidget(use_btn)
        row.addWidget(skip_btn)
        row.addStretch(1)
        lay.addLayout(row)

    def value(self):
        lines = [ln.strip() for ln in self.edit.toPlainText().splitlines() if ln.strip()]
        return lines or None