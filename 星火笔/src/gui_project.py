# -*- coding: utf-8 -*-
"""项目页：项目列表 / 故事设定（剧情/世界观/特殊规则三栏）/ 文风参考 / 新建项目（含AI辅助创建）。"""
import os
import threading

from PySide6.QtCore import Qt, QObject, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFrame,
                               QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem,
                               QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea,
                               QSpinBox, QTabWidget, QVBoxLayout, QWidget)

import main_ai
import config
import storage
from gui_app import APP, bus, busy_guard, current_project, log_fn, set_running
from gui_theme import T


class _Worker(QObject):
    plan_ready = Signal(dict)
    create_ready = Signal(dict)
    failed = Signal(str)


def _legacy_text(project):
    """旧版 opening + volumes 拼接为自然语言（仅加载旧项目时用于迁移显示）。"""
    parts = []
    if (project.opening or "").strip():
        parts.append("【开局设定】%s" % project.opening)
    for v in project.volumes:
        parts.append("【第%d卷（目标%d章）：%s】" % (v.index, v.total_chapters, v.title or "无题"))
        for i, ev in enumerate(v.main_events, 1):
            parts.append("%d. %s" % (i, ev))
        if v.ending:
            parts.append("本卷结尾目标：%s" % v.ending)
        if v.next_hook:
            parts.append("承接下一卷：%s" % v.next_hook)
        if v.notes:
            parts.append("补充约束：%s" % v.notes)
    return "\n".join(parts)


class ProjectPage(QWidget):

    _style_done = Signal(object)   # AI 风格要点提炼完成（要点列表 / ("__err__", 信息)）

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._style_done.connect(self._on_style_done)
        self.worker = _Worker()
        self.worker.plan_ready.connect(self._on_plan_ready)
        self.worker.create_ready.connect(self._on_create_ready)
        self.worker.failed.connect(self._on_plan_failed)

        # 整页滚动：窗口矮时整体可滚，文本框不再被压成一小点
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

        # ---------- 顶部：项目选择 + 进度 ----------
        box = QFrame()
        box.setObjectName("panel")
        blay = QVBoxLayout(box)
        blay.setContentsMargins(14, 12, 14, 12)
        blay.setSpacing(8)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("当前项目"))
        self.proj_combo = QComboBox()
        self.proj_combo.setMinimumWidth(300)
        row1.addWidget(self.proj_combo, 1)
        # v0.55 起项目页顶部不再放「一键成书/小说导入成项目」按钮（子 UI 页面里已有功能按键，
        # 顶部重复多余）；入口在各自 tab 页内（与「新建项目」平级）。
        self.new_btn = QPushButton("新建项目")
        self.new_btn.setObjectName("primary")
        self.new_btn.clicked.connect(self._new_dialog)
        self.load_btn = QPushButton("载入")
        self.load_btn.clicked.connect(self._load_selected)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh_projects)
        self.example_btn = QPushButton("载入示例项目")
        self.example_btn.clicked.connect(self._load_example)
        self.del_btn = QPushButton("删除所选项目")
        self.del_btn.setObjectName("danger")
        self.del_btn.clicked.connect(self._delete_selected)
        row1.addWidget(self.new_btn)
        row1.addWidget(self.load_btn)
        row1.addWidget(self.refresh_btn)
        row1.addWidget(self.example_btn)
        row1.addWidget(self.del_btn)
        blay.addLayout(row1)
        # 项目整体导入导出（zip 包：设定/角色卡/章节/快照/日志全带走，换电脑继续写）
        row2 = QHBoxLayout()
        self.export_btn = QPushButton("导出项目")
        self.export_btn.setToolTip("把当前项目的完整状态（设定/文风/角色卡与信息库/全部章节/伏笔/主AI笔记/知识库/世界快照/日志）打包为 zip")
        self.export_btn.clicked.connect(self._export_project)
        self.import_btn = QPushButton("导入项目")
        self.import_btn.setToolTip("从 zip 包导入项目（自动规避重名，绝不覆盖已有项目）")
        self.import_btn.clicked.connect(self._import_project)
        io_hint = QLabel("导入/导出即整个项目打包，换电脑接手写作直接导出→导入，无需单篇搬运。")
        io_hint.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        row2.addWidget(self.export_btn)
        row2.addWidget(self.import_btn)
        row2.addWidget(io_hint)
        row2.addStretch(1)
        blay.addLayout(row2)
        self.progress_lbl = QLabel("")
        self.progress_lbl.setStyleSheet(T("color:#8a93a3;"))
        blay.addWidget(self.progress_lbl)
        lay.addWidget(box)

        # ---------- 中部：Tab 管理 ----------
        tabs = QTabWidget()
        self.tabs = tabs

        # ===== Tab 1：故事设定（剧情/世界观/特殊规则 三栏合一） =====
        t1 = QWidget()
        t1lay = QVBoxLayout(t1)
        t1lay.setContentsMargins(0, 0, 0, 0)
        # v0.83「故事设定」Tab 包滚动容器：设定三栏 + AI 辅助 + 文风校对（正文生成后/主AI验收前）
        _t1_scr = QScrollArea()
        _t1_scr.setWidgetResizable(True)
        _t1_inner = QWidget()
        l1 = QVBoxLayout(_t1_inner)
        l1.setContentsMargins(6, 8, 6, 6)
        l1.setSpacing(10)

        # 顶部：标题 + 目标章数
        top_box = QFrame()
        top_box.setObjectName("panel")
        top_lay = QGridLayout(top_box)
        top_lay.setContentsMargins(12, 10, 12, 10)
        top_lay.addWidget(QLabel("小说标题"), 0, 0)
        self.p_title = QLineEdit()
        top_lay.addWidget(self.p_title, 0, 1)
        top_lay.addWidget(QLabel("本卷目标章数（0 = 由主 AI 把控节奏）"), 1, 0)
        self.target_spin = QSpinBox()
        self.target_spin.setRange(0, 9999)
        self.target_spin.setValue(0)
        self.target_spin.setFixedWidth(110)
        top_lay.addWidget(self.target_spin, 1, 1)
        self.save_btn = QPushButton("保存故事设定")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self._save)
        top_lay.addWidget(self.save_btn, 1, 2, alignment=Qt.AlignmentFlag.AlignLeft)
        l1.addWidget(top_box)

        # 剧情发展
        sbox = QGroupBox("剧情发展（开局/主线/关键事件/结尾方向/下一卷）")
        sgrid = QVBoxLayout(sbox)
        self.p_story = QPlainTextEdit()
        self.p_story.setMinimumHeight(150)
        self.p_story.setPlaceholderText(
            "示例：\n"
            "【开局】主角在风沙夜抵达边境孤城…\n"
            "【本卷主线】…（按你定的节奏推进）\n"
            "【结尾方向】…\n"
            "【下一卷】…\n"
            "写多写少、怎么分段都行。")
        sgrid.addWidget(self.p_story)
        l1.addWidget(sbox, 2)

        # 世界观
        wbox = QGroupBox("世界观（世界背景、势力格局、地理/大概念地图、力量体系、种族文明等；剧情必须服从）")
        wlay = QVBoxLayout(wbox)
        self.p_world = QPlainTextEdit()
        self.p_world.setMinimumHeight(110)
        self.p_world.setPlaceholderText(
            "示例：\n"
            "【时代背景】铁与火的后启示录纪元，旧文明毁灭后三百年…\n"
            "【地理】大陆分九域：中央王域、北境冻原、西漠诸邦、东陆群岛…\n"
            "【势力格局】城主府鹰派 / 秘术隐修会 / 南方佣兵公会三方角力…\n"
            "【力量体系】斗气九阶 + 上古符文秘术，禁忌：灵魂契约…\n"
            "留空则忽略。")
        wlay.addWidget(self.p_world)
        l1.addWidget(wbox, 1)

        # 特殊规则
        rbox = QGroupBox("特殊规则 / 其他设定（金手指、禁忌、叙事偏好等杂项硬约束）")
        rlay = QVBoxLayout(rbox)
        self.p_rules = QPlainTextEdit()
        self.p_rules.setMinimumHeight(110)
        self.p_rules.setPlaceholderText(
            "示例：\n"
            "- 主角金手指：每次生死危机后觉醒一种旧日符文之力，但会付出代价；\n"
            "- 禁忌：禁止主角开挂秒杀 BOSS，禁止圣母心泛滥，禁止降智情节；\n"
            "- 叙事：重要配角死亡必须有铺垫，不得突然退场…\n"
            "留空则忽略。")
        rlay.addWidget(self.p_rules)
        l1.addWidget(rbox, 1)

        # AI 辅助完善本项目的三栏（可勾选生成哪些）
        aibox = QGroupBox("AI 辅助（按你的想法起草/完善下列勾选的内容，填入对应栏，检查后点「保存故事设定」）")
        ailay = QHBoxLayout(aibox)
        self.plan_notes = QLineEdit()
        self.plan_notes.setPlaceholderText("你的故事想法（例：古代架空+悬疑+权谋，从孤城悬案入手…留空则由 AI 顺着现有栏目的基调发挥）")
        ailay.addWidget(self.plan_notes, 1)
        self.plan_constraint = QLineEdit()
        self.plan_constraint.setPlaceholderText("章数约束（可留空）")
        self.plan_constraint.setFixedWidth(150)
        ailay.addWidget(self.plan_constraint)
        self.plan_chk_story = QCheckBox("剧情")
        self.plan_chk_world = QCheckBox("世界观")
        self.plan_chk_rules = QCheckBox("规则")
        self.plan_chk_story.setChecked(True)
        self.plan_chk_world.setChecked(True)
        self.plan_chk_rules.setChecked(True)
        ailay.addWidget(self.plan_chk_story)
        ailay.addWidget(self.plan_chk_world)
        ailay.addWidget(self.plan_chk_rules)
        self.plan_btn = QPushButton("AI 生成所选")
        self.plan_btn.setObjectName("primary")
        self.plan_btn.clicked.connect(self._plan_ai)
        ailay.addWidget(self.plan_btn)
        l1.addWidget(aibox)
        _t1_scr.setWidget(_t1_inner)
        t1lay.addWidget(_t1_scr)

        tabs.addTab(t1, "故事设定")

        # ===== Tab 2：文风参考（自然语言描述 / 正文AI角色提示词 / 范例文本 / 主AI全局提示词 / 文风校对） =====
        t2 = QWidget()
        t2lay = QVBoxLayout(t2)
        t2lay.setContentsMargins(0, 0, 0, 0)
        # v0.82 包滚动容器：①~⑤ 内容很高，直放会把底部（⑤ 文风校对）裁掉滚不到
        _t2_scr = QScrollArea()
        _t2_scr.setWidgetResizable(True)
        _t2_inner = QWidget()
        l2 = QVBoxLayout(_t2_inner)
        l2.setContentsMargins(6, 8, 6, 6)
        l2.setSpacing(10)
        _t2_scr.setWidget(_t2_inner)
        t2lay.addWidget(_t2_scr)

        # ① 主AI风格设定（自然语言描述文风）
        gbox = QGroupBox("① 文风描述（自然语言告诉主 AI：文风/基调/视角/节奏；主 AI 决断与写作都会遵循）")
        glay = QVBoxLayout(gbox)
        self.p_style = QPlainTextEdit()
        self.p_style.setMinimumHeight(120)
        self.p_style.setPlaceholderText(
            "示例：\n"
            "- 文风：冷峻克制、画面感强，少抒情多白描；对话简短有力；\n"
            "- 基调：悬疑 + 权谋 + 轻克苏鲁，黑暗但不绝望；\n"
            "- 视角：第三人称限知，跟随主角视角；\n"
            "- 节奏：开篇慢热铺陈，每 2-3 章一个小高潮，卷末大高潮；\n"
            "写什么都行，主 AI 会照做。留空则不启用。")
        glay.addWidget(self.p_style)
        save_style = QPushButton("保存文风描述")
        save_style.setObjectName("primary")
        save_style.clicked.connect(self._save_style)
        glay.addWidget(save_style, alignment=Qt.AlignmentFlag.AlignLeft)
        l2.addWidget(gbox, 2)

        # ② 正文AI角色提示词（"你是一个…"式）
        wbox = QGroupBox("② 正文AI角色提示词（只给正文AI：限定它的身份/风格，例如「你是一个擅长冷峻写实的网文作者…」）")
        wlay = QVBoxLayout(wbox)
        self.p_writer_prompt = QPlainTextEdit()
        self.p_writer_prompt.setMinimumHeight(90)
        self.p_writer_prompt.setPlaceholderText(
            "示例：\n"
            "你是一个擅长古风权谋的网文作者，描写克制、伏笔绵密，惯用短句营造张力，"
            "写对话时字字机锋，极少直抒胸臆。\n"
            "也可以是任何自然语言要求（如：正文里减少心理独白，多用动作与细节呈现）。留空则不启用。")
        wlay.addWidget(self.p_writer_prompt)
        save_writer = QPushButton("保存正文AI角色提示词")
        save_writer.setObjectName("primary")
        save_writer.clicked.connect(self._save_writer_prompt)
        wlay.addWidget(save_writer, alignment=Qt.AlignmentFlag.AlignLeft)
        l2.addWidget(wbox, 1)

        # ③ 参考文风样本（范例文本）
        rbox = QGroupBox("③ 参考文风样本（粘贴一段你觉得文风对味的文字，正文AI会模仿它来写）")
        rlay = QVBoxLayout(rbox)
        self.p_style_ref = QPlainTextEdit()
        self.p_style_ref.setMinimumHeight(120)
        self.p_style_ref.setPlaceholderText(
            "示例：粘贴一段你喜欢的网文/小说片段（100-1000字都行）：\n"
            "\n"
            "夜风卷着雪粒扑在城墙上，他拢了拢斗篷，靴底碾过一层薄霜……\n"
            "\n"
            "正文AI会学习它的句式、语感、节奏与描写手法来写你的章节；"
            "只模仿风格，不会照抄内容。留空则不启用。")
        rlay.addWidget(self.p_style_ref)
        save_ref = QPushButton("保存参考文风样本")
        save_ref.setObjectName("primary")
        save_ref.clicked.connect(self._save_style_ref)
        rlay.addWidget(save_ref, alignment=Qt.AlignmentFlag.AlignLeft)
        l2.addWidget(rbox, 2)

        # ③.5 风格要点（AI 从文风样本/前文提炼的可执行要点，写作与校对逐条体现）
        sbox = QGroupBox("③.5 风格要点（可编辑；点「AI 提炼」自动从文风样本+前文归纳，"
                         "正文写作与文风校对会逐条检查体现）")
        slay = QVBoxLayout(sbox)
        self.p_style_note = QPlainTextEdit()
        self.p_style_note.setMinimumHeight(80)
        self.p_style_note.setPlaceholderText(
            "示例（每行一条）：\n短句推进，动作先行；\n对话带京腔，字字机锋；\n"
            "少心理独白，多用细节呈现。\n\n留空则不启用。")
        slay.addWidget(self.p_style_note)
        srow = QHBoxLayout()
        self.style_extract_btn = QPushButton("AI 提炼风格要点")
        self.style_extract_btn.setObjectName("primary")
        self.style_extract_btn.clicked.connect(self._extract_style_points)
        save_note = QPushButton("保存风格要点")
        save_note.clicked.connect(self._save_style_note)
        srow.addWidget(self.style_extract_btn)
        srow.addWidget(save_note)
        srow.addStretch(1)
        slay.addLayout(srow)
        l2.addWidget(sbox, 1)

        # ④ 主AI全局提示词
        mbox = QGroupBox("④ 主AI全局提示词（只给主AI：控制它如何把控剧情走向/节奏/角色管理，"
                         "支持「你是一个…」式或自然语言要求）")
        mlay = QVBoxLayout(mbox)
        self.p_main_prompt = QPlainTextEdit()
        self.p_main_prompt.setMinimumHeight(90)
        self.p_main_prompt.setPlaceholderText(
            "示例：\n"
            "你是一个擅长长线布局的剧情总监：每个重大转折至少提前 3 章埋下暗示；"
            "每章结尾必须有钩子；保持主角有成长弧光；支线不超过两条并行。\n"
            "或自然语言：主 AI 把控剧情时注意节奏起伏，避免连续平淡，关键情节给足铺垫。"
            "留空则不启用。")
        mlay.addWidget(self.p_main_prompt)
        save_main = QPushButton("保存主AI全局提示词")
        save_main.setObjectName("primary")
        save_main.clicked.connect(self._save_main_prompt)
        mlay.addWidget(save_main, alignment=Qt.AlignmentFlag.AlignLeft)
        l2.addWidget(mbox, 1)

        # ⑤ 情景写作提示词（v1.18 勾选 → v1.21 只读显示项目主AI可用库；管理移到「情景提示词」功能页）
        scbox = QGroupBox("⑤ 情景写作提示词（本项目主AI可用库，与总库独立：主AI每章按正文类型"
                          "优先从这里选卡；本章类型没匹配卡时主AI会自做一张只进本库）")
        sclay = QVBoxLayout(scbox)
        self.scene_cards_list = QListWidget()
        self.scene_cards_list.setMinimumHeight(130)
        self.scene_cards_list.setToolTip("本项目主AI可选的情景规则卡（与总库独立）。\n"
                                         "管理（从总库加入 / 移出本项目 / 放入总库）在「情景提示词」功能页。")
        sclay.addWidget(self.scene_cards_list)
        scrow = QHBoxLayout()
        adapt_btn = QPushButton("主AI按本文风适配本项目卡")
        adapt_btn.setObjectName("primary")
        adapt_btn.setToolTip("让主AI按本项目的「正文AI角色提示词」文风，逐张改写本项目库情景卡——"
                             "保持每张卡的情景内核/卡名/分类不变，只把写法表述调整到契合本项目文风；"
                             "只改本项目库、不动总库。\n"
                             "（v1.42 新增：跨项目/拆书得来的通用卡按当前项目文风适配后再用）")
        adapt_btn.clicked.connect(self._adapt_scene_cards)
        scrow.addWidget(adapt_btn)
        goto_sc = QPushButton("打开「情景提示词」页管理")
        goto_sc.setToolTip("跳转到「情景提示词」功能页：从总库加入本项目 / 移出本项目 / 放入总库")
        goto_sc.clicked.connect(self._goto_scene_cards)
        scrow.addWidget(goto_sc)
        scrow.addStretch(1)
        sclay.addLayout(scrow)
        l2.addWidget(scbox, 1)

        tabs.addTab(t2, "文风参考")

        # ===== Tab：写后校对（v0.85 独立子页面；v0.86 定名「写后校对」——正文生成后、主AI验收前的校对） =====
        t_pr = QWidget()
        tpr_lay = QVBoxLayout(t_pr)
        tpr_lay.setContentsMargins(6, 8, 6, 6)
        tpr_lay.setSpacing(10)
        prov_box = QGroupBox("写后校对（正文AI完稿后、主AI验收前，只改文本不改剧情；"
                             "不想每章校对时关掉，每章省一次调用生成更快；失败自动重试 3 次）")
        prov_lay = QVBoxLayout(prov_box)
        prov_lay.setContentsMargins(10, 8, 10, 8)
        prov_lay.setSpacing(6)
        prov_row = QHBoxLayout()
        self.proofread_chk = QCheckBox("启用写后校对环节")
        self.proofread_chk.setChecked(True)
        self.proofread_chk.toggled.connect(self._proofread_dirty)
        self.proofread_chk.toggled.connect(self._proofread_group_enable)
        prov_row.addWidget(self.proofread_chk)
        self.pr_status = QLabel("改动自动保存，无需另按保存按钮")
        self.pr_status.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        prov_row.addWidget(self.pr_status)
        prov_row.addStretch(1)
        prov_lay.addLayout(prov_row)
        self.pr_hint = QLabel(
            "写后校对规则（可自由编辑，留空恢复内置默认；不需要校对时直接关掉上方开关）：\n"
            "负责检查描写逻辑错误（物品/人物位置姿态前后矛盾、时间数量错乱），"
            "以及语句、字词、修辞是否合理（「砸/砍/撕裂/狠狠」等重词要少用、"
            "「像被撕碎/指尖泛白」等套话修辞要克制）。校对只修改文本，绝不改剧情。")
        self.pr_hint.setWordWrap(True)
        self.pr_hint.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        prov_lay.addWidget(self.pr_hint)
        self.proofread_edit = QPlainTextEdit()
        self.proofread_edit.setPlaceholderText("留空 = 使用内置默认校对规则")
        self.proofread_edit.setMinimumHeight(90)
        self.proofread_edit.setMaximumHeight(160)
        self.proofread_edit.setStyleSheet("font-family:Consolas,'Microsoft YaHei';")
        self.proofread_edit.textChanged.connect(self._proofread_dirty)
        prov_lay.addWidget(self.proofread_edit)
        # v1.07 写后校对照前后章节参考（与去AI味页共用 deai_nearby_chapters；0=只看本章）
        prov_near = QHBoxLayout()
        prov_near.addWidget(QLabel("前后章节参考："))
        self.proof_near_spin = QSpinBox()
        self.proof_near_spin.setRange(0, 20)
        self.proof_near_spin.setSuffix(" 章")
        self.proof_near_spin.setValue(2)
        self.proof_near_spin.setToolTip("校对时看前后各几章的衔接参考（人物状态/地点/时间线/已发生事件"
                                        "必须与前后文一致，防剧情偏移）；与去AI味页设置共用，0=只看本章")
        self.proof_near_spin.valueChanged.connect(self._proofread_dirty)
        prov_near.addWidget(self.proof_near_spin)
        prov_near.addWidget(QLabel("（AI 对照前后文核对剧情衔接，防止偏移；与去AI味页共用，0=只看本章）"))
        prov_near.addStretch(1)
        prov_lay.addLayout(prov_near)
        self._proofread_timer = QTimer(self)
        self._proofread_timer.setSingleShot(True)
        self._proofread_timer.setInterval(600)
        self._proofread_timer.timeout.connect(self._save_proofread)
        tpr_lay.addWidget(prov_box)
        tpr_lay.addStretch(1)
        tabs.addTab(t_pr, "写后校对")

        # ===== Tab 3：设定锚点（项目 Lorebook） =====
        t4 = QWidget()
        l4 = QVBoxLayout(t4)
        l4.setContentsMargins(6, 8, 6, 6)
        l4.setSpacing(10)
        hint = QLabel(
            "设定锚点是**用户维护的硬性设定**（与故事设定同级，正文/决断/审查都不得与锚点冲突）。\n"
            "· 「常驻」条目：每章生成时必定注入主AI与正文AI（如主角断臂、关键势力铁律等绝不能被压缩笔记遗忘的设定）；\n"
            "· 「关键词」条目：剧情文本（最近章节/本章指示/草稿等）命中关键词时自动注入（如「铁砧城」一出现就把该城设定带上）。\n"
            "适合存放世界观细节、地名/势力/组织设定、力量体系细则等——避免长篇小说里设定被遗忘或被模型自由发挥改掉。")
        hint.setWordWrap(True)
        hint.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        l4.addWidget(hint)
        row_lore = QHBoxLayout()
        row_lore.addWidget(QLabel("锚点/知识条目"))
        row_lore.addStretch(1)
        self.lore_add_btn = QPushButton("＋ 新增")
        self.lore_add_btn.setObjectName("primary")
        self.lore_add_btn.clicked.connect(self._lore_add)
        self.lore_edit_btn = QPushButton("编辑")
        self.lore_edit_btn.clicked.connect(self._lore_edit)
        self.lore_del_btn = QPushButton("删除")
        self.lore_del_btn.setObjectName("danger")
        self.lore_del_btn.clicked.connect(self._lore_del)
        row_lore.addWidget(self.lore_add_btn)
        row_lore.addWidget(self.lore_edit_btn)
        row_lore.addWidget(self.lore_del_btn)
        l4.addLayout(row_lore)
        self.lore_list = QListWidget()
        self.lore_list.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        l4.addWidget(self.lore_list, 1)
        tabs.addTab(t4, "设定锚点")

        # v0.83 撤销「写作技巧库」功能页（主AI可直接联网搜索/用锚点与提示词控制，用户明确不需要）

        # ===== Tab 5：新建项目 =====
        nbox = QGroupBox("创建新小说")
        nlay = QGridLayout(nbox)
        self.new_title = QLineEdit()
        self.new_title.setPlaceholderText("例：星海孤城")
        self.new_story = QPlainTextEdit()
        self.new_story.setPlaceholderText(
            "用自然语言写下你想让主 AI 知道的故事：世界观、开局、剧情走向、关键事件、结尾方向…（可留空，创建后再写）")
        self.new_story.setFixedHeight(100)
        nlay.addWidget(QLabel("小说标题"), 0, 0)
        nlay.addWidget(self.new_title, 0, 1)
        nlay.addWidget(QLabel("故事描述"), 1, 0)
        nlay.addWidget(self.new_story, 1, 1)

        # AI 辅助创建：可勾选让 AI 生成哪几块，直接创建时填写
        ailine = QHBoxLayout()
        ailine.addWidget(QLabel("AI 帮我起草："))
        self.new_chk_story = QCheckBox("剧情")
        self.new_chk_world = QCheckBox("世界观")
        self.new_chk_rules = QCheckBox("规则")
        self.new_chk_story.setChecked(True)
        self.new_chk_world.setChecked(True)
        self.new_chk_rules.setChecked(True)
        ailine.addWidget(self.new_chk_story)
        ailine.addWidget(self.new_chk_world)
        ailine.addWidget(self.new_chk_rules)
        ailine.addStretch(1)
        nlay.addLayout(ailine, 2, 1)

        # 两个创建按钮同行右对齐（v0.52 对齐修正）
        btnline = QHBoxLayout()
        btnline.addStretch(1)
        self.new_ai_btn = QPushButton("AI 生成并创建")
        self.new_ai_btn.setObjectName("primary")
        self.new_ai_btn.setToolTip("按上方故事描述/想法让 AI 起草勾选的内容，然后创建项目")
        self.new_ai_btn.clicked.connect(self._create_with_ai)
        btnline.addWidget(self.new_ai_btn)
        self.create_btn = QPushButton("直接创建项目")
        self.create_btn.clicked.connect(self._create)
        btnline.addWidget(self.create_btn)
        nlay.addLayout(btnline, 3, 1)
        hint = QLabel("「AI 生成并创建」：按你的想法让 AI 起草勾选的部分（不勾选的栏留空），再创建项目；"
                      "「直接创建项目」：什么都不生成，先建空项目后到「故事设定」页自己填。")
        hint.setWordWrap(True)
        hint.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        nlay.addWidget(hint, 4, 1)
        t3 = QWidget()
        l3 = QVBoxLayout(t3)
        l3.setContentsMargins(6, 8, 6, 6)
        l3.addWidget(nbox)
        l3.addStretch(1)
        tabs.addTab(t3, "新建项目")

        # ===== Tab 6：一键成书（与「新建项目」平级的独立 UI 界面，v0.53） =====
        from gui_book import BookPanel
        self._book_panel = BookPanel(self, show_title=False)
        tabs.addTab(self._book_panel, "✨ 一键成书")

        # ===== Tab 7：小说导入成项目（与「新建项目」「一键成书」平级，v0.54） =====
        from gui_import import ImportPanel
        t7 = ImportPanel(self, show_title=False)
        tabs.addTab(t7, "📥 小说导入成项目")

        lay.addWidget(tabs, 1)

    # ---------- 刷新 ----------
    def refresh_projects(self):
        self.proj_combo.clear()
        for item in storage.list_projects():
            self.proj_combo.addItem(item["title"], item["dir"])
        if APP["project_dir"]:
            idx = self.proj_combo.findData(APP["project_dir"])
            if idx >= 0:
                self.proj_combo.setCurrentIndex(idx)

    def on_show(self):
        self.refresh_projects()
        store, project = current_project()
        if not project:
            self.progress_lbl.setText("尚未载入项目。")
            return
        idx = self.proj_combo.findData(APP["project_dir"])
        if idx >= 0:
            self.proj_combo.setCurrentIndex(idx)
        self.p_title.setText(project.title)
        if (project.story_brief or "").strip():
            self.p_story.setPlainText(project.story_brief)
        else:
            self.p_story.setPlainText(_legacy_text(project))
        self.p_style.setPlainText(project.story_style or "")
        self.p_style_ref.setPlainText(project.story_style_ref or "")
        self.p_style_note.setPlainText(project.story_style_note or "")
        self.p_writer_prompt.setPlainText(project.story_writer_prompt or "")
        self.p_main_prompt.setPlainText(project.story_main_prompt or "")
        # v1.18 本项目启用的情景写作提示词回填（全局卡库勾选子集）
        try:
            self._refresh_scene_cards(project)
        except Exception:
            pass
        # v0.100 一键成书面板的拆书风格下拉跟随风格库刷新（拆书工坊保存/删除后进项目页即更新）
        try:
            if hasattr(self, "_book_panel") and hasattr(self._book_panel, "_refresh_breaks"):
                self._book_panel._refresh_breaks()
        except Exception:
            pass
        self.p_world.setPlainText(project.story_world or "")
        self.p_rules.setPlainText(project.story_rules or "")
        self.target_spin.setValue(int(project.volume_target or 0))
        # v0.81 写后校对设置回填（全局 config：开关 + 提示词）
        _cfg = config.load_config()
        self.proofread_chk.blockSignals(True)
        self.proofread_chk.setChecked(bool(_cfg.get("proofread_enabled", True)))
        self.proofread_chk.blockSignals(False)
        self.proofread_edit.blockSignals(True)
        self.proofread_edit.setPlainText(_cfg.get("proofread_rules") or "")
        self.proofread_edit.blockSignals(False)
        # v1.07 写后校对照前后章节参考（与去AI味页共用 deai_nearby_chapters；0=只看本章）
        self.proof_near_spin.blockSignals(True)
        try:
            _pn = int(_cfg.get("deai_nearby_chapters", 2) or 2)
        except (TypeError, ValueError):
            _pn = 2
        self.proof_near_spin.setValue(max(0, min(20, _pn)))
        self.proof_near_spin.blockSignals(False)
        self._proofread_group_enable(bool(_cfg.get("proofread_enabled", True)))
        self._lore_refresh()
        self._update_progress(project)

    def _update_progress(self, project=None):
        if project is None:
            _, project = current_project()
        if not project:
            return
        written = project.written_chapters()
        target = project.chapter_target()
        if target > 0:
            self.progress_lbl.setText("%s　|　进度：本卷目标 %d 章 · 已写 %d 章"
                                      % (project.title, target, written))
        else:
            self.progress_lbl.setText("%s　|　进度：已写 %d 章 · 无硬性章数目标（主 AI 把控节奏）"
                                      % (project.title, written))

    # ---------- 动作 ----------
    def _load_selected(self):
        dir_name = self.proj_combo.currentData()
        if not dir_name:
            return
        self.app.select_project(dir_name)
        self.on_show()
        log_fn("info", "已载入项目：%s" % dir_name)

    def _load_example(self):
        storage.ensure_example_project()
        projects = storage.list_projects()
        if projects:
            self.app.select_project(projects[0]["dir"])
            self.on_show()
            log_fn("info", "示例项目已载入。")
        else:
            QMessageBox.warning(self, "提示", "示例项目创建失败。")

    def _export_project(self):
        """把当前项目整体打包为 zip（含设定/角色卡/章节/快照/日志），可拷走换电脑继续写。"""
        from PySide6.QtWidgets import QFileDialog
        import export_utils
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        if not busy_guard(self):
            return
        default_path = export_utils.default_project_zip_path(project.title)
        path, _ = QFileDialog.getSaveFileName(
            self, "导出项目（整个项目打包）", default_path, "星火笔项目包 (*.zip)")
        if not path:
            return
        if storage.export_project(project.dir_name, path):
            log_fn("info", "项目已导出：%s" % path)
            QMessageBox.information(
                self, "导出成功",
                "项目已打包导出到：\n%s\n\n包含：故事设定/文风/角色卡与信息库/全部章节/伏笔台账/"
                "主AI笔记/知识库/世界快照/生成日志。\n拷到其他电脑用「导入项目」即可继续写（需同一版本的星火笔）。"
                % path)
        else:
            QMessageBox.warning(self, "导出失败", "导出失败，请检查目标路径是否可写。")

    def _import_project(self):
        """从 zip 包导入项目（重名自动加后缀，不覆盖已有项目），导入后自动载入。

        老版本项目（角色卡无分类）导入后自动触发一次 AI 分类（后台线程，不阻塞界面）。
        """
        from PySide6.QtWidgets import QFileDialog
        path, _ = QFileDialog.getOpenFileName(
            self, "导入项目（星火笔项目包）", "", "星火笔项目包 (*.zip)")
        if not path:
            return
        if not busy_guard(self):
            return
        ret = storage.import_project(path)
        if ret is None:
            QMessageBox.warning(
                self, "导入失败",
                "不是有效的星火笔项目包：未找到 project.json，或文件已损坏/受版本限制。")
            return
        dir_name, title, warn = ret
        self.app.select_project(dir_name)
        self.on_show()
        log_fn("info", "已导入项目：《%s》" % title)
        auto_n = self._auto_classify_after_import()
        st = storage.ProjectStore(dir_name)
        n_ch = len(st.list_chapter_indices())
        n_ca = len(st.list_characters())
        n_sn = len(st.list_snapshot_indices())
        msg = ("已导入《%s》并自动载入。\n\n章节 %d 章 · 角色卡 %d 个 · 世界快照 %d 个。"
               "\n若本机已有同名项目，导入的副本自动追加了后缀，原项目不受影响。"
               % (title, n_ch, n_ca, n_sn))
        if warn:
            msg = ("⚠️ 导入可能不完整：%s。\n请回到原版本重新「导出项目」并确认传输完整后再导入。\n\n"
                   % warn) + msg
        if auto_n > 0:
            msg += "\n\n检测到 %d 个角色未分类（老版本项目），已自动开始 AI 分类，完成后在「角色管理」查看。" % auto_n
        QMessageBox.information(self, "导入成功", msg)

    def _auto_classify_after_import(self):
        """老版本项目导入后：存在未分类角色时自动 AI 分类（后台线程）。

        返回未分类角色数（0 表示无需分类）。分类失败不阻断使用，可稍后在角色页手动「AI 自动分类」。
        """
        store, project = current_project()
        if not project or not store:
            return 0
        uncat = [c for c, _l in store.list_character_cards()
                 if not (c.category or "").strip() and c.status != "archived"]
        if not uncat:
            return 0
        log_fn("info", "导入项目检测到 %d 个角色未分类，自动 AI 分类中…" % len(uncat))

        def work():
            try:
                roles = main_ai.classify_characters(project, store)
                if not roles:
                    log_fn("warn", "自动分类未返回结果（可稍后在角色页点「AI 自动分类」重试）。")
                    return
                ok_n = 0
                for cid, name, _st in store.list_characters():
                    cat = roles.get(name)
                    if not cat:
                        continue
                    card, lib = store.load_character(cid)
                    if card and card.category != cat:
                        card.category = cat
                        card.version += 1
                        store.save_character(card, lib)
                    ok_n += 1
                log_fn("info", "导入项目自动分类完成：%d 个角色已归类。" % ok_n)
            except Exception as e:
                log_fn("warn", "导入项目自动分类失败：%s（可稍后在角色页手动「AI 自动分类」）" % e)
            finally:
                bus.charactersChanged.emit()

        threading.Thread(target=work, daemon=True).start()
        return len(uncat)

    def _create(self):
        title = self.new_title.text().strip()
        if not title:
            QMessageBox.warning(self, "提示", "请填写小说标题。")
            return
        story = self.new_story.toPlainText().strip()
        self.new_title.clear()
        self.new_story.clear()
        self._do_create(title, story)

    def _new_dialog(self):
        """顶部「新建项目」入口：弹窗填标题+故事，创建并载入。"""
        dlg = NewProjectDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        title = dlg.title.text().strip()
        if not title:
            QMessageBox.warning(self, "提示", "请填写小说标题。")
            return
        story = dlg.story.toPlainText().strip()
        self._do_create(title, story)

    def _book_start(self):
        """一键成书（v0.53）：切到项目页「✨ 一键成书」独立界面（与新建项目平级）。"""
        self._switch_tab("一键成书")

    def _import_start(self):
        """小说导入成项目（v0.54）：切到项目页「📥 小说导入成项目」独立界面。"""
        self._switch_tab("小说导入成项目")

    def _switch_tab(self, keyword):
        for i in range(self.tabs.count()):
            if keyword in self.tabs.tabText(i):
                self.tabs.setCurrentIndex(i)
                return

    def _do_create(self, title, story, world="", rules=""):
        project = storage.create_project(title)
        project.story_brief = story
        project.story_world = world
        project.story_rules = rules
        store = storage.ProjectStore(project.dir_name)
        store.save_project(project)
        self.app.select_project(project.dir_name)
        self.on_show()
        log_fn("info", "已创建项目：%s" % project.title)

    def _save(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        project.title = self.p_title.text().strip() or project.title
        project.story_brief = self.p_story.toPlainText().strip()
        project.story_world = self.p_world.toPlainText().strip()
        project.story_rules = self.p_rules.toPlainText().strip()
        project.volume_target = self.target_spin.value()
        store.save_project(project)
        self._update_progress(project)
        log_fn("info", "故事设定已保存（本卷目标 %d 章）。" % project.volume_target)

    def _save_style(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        project.story_style = self.p_style.toPlainText().strip()
        store.save_project(project)
        log_fn("info", "主AI风格设定已保存。")

    def _save_style_ref(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        project.story_style_ref = self.p_style_ref.toPlainText().strip()
        store.save_project(project)
        log_fn("info", "参考文风样本已保存（%d 字，正文AI写作时将模仿）。"
               % len(project.story_style_ref))

    # ---------- 风格要点（AI 提炼 / 手动编辑） ----------
    def _save_style_note(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        project.story_style_note = self.p_style_note.toPlainText().strip()
        store.save_project(project)
        log_fn("info", "风格要点已保存（正文写作与写后校对会逐条检查体现）。")

    def _extract_style_points(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        if not (project.story_style_ref or "").strip() and not store.list_chapter_indices():
            QMessageBox.warning(self, "提示",
                                "请先填写参考文风样本（或在故事页先写几章），AI 才有依据提炼风格。")
            return
        if not busy_guard(self):
            return
        self.style_extract_btn.setEnabled(False)
        self.style_extract_btn.setText("提炼中…")
        set_running(True)

        def work():
            try:
                pts = main_ai.extract_style_points(project, store)
                self._style_done.emit(pts)
            except Exception as e:
                self._style_done.emit(("__err__", str(e)))
            finally:
                set_running(False)

        threading.Thread(target=work, daemon=True).start()

    def _on_style_done(self, result):
        self.style_extract_btn.setEnabled(True)
        self.style_extract_btn.setText("AI 提炼风格要点")
        if isinstance(result, tuple) and result and result[0] == "__err__":
            log_fn("warn", "风格要点提炼失败：%s" % result[1])
            QMessageBox.warning(self, "提示", "风格要点提炼失败：%s" % result[1])
            return
        pts = [str(x).strip() for x in result if str(x).strip()]
        if not pts:
            log_fn("warn", "风格要点提炼结果为空。")
            QMessageBox.warning(self, "提示", "提炼结果为空，请确认文风样本有效后重试。")
            return
        self.p_style_note.setPlainText("\n".join(pts))
        store, project = current_project()
        if project:
            project.story_style_note = "\n".join(pts)
            store.save_project(project)
        log_fn("info", "已提炼风格要点 %d 条（可手动编辑后保存）。" % len(pts))

    def _save_writer_prompt(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        project.story_writer_prompt = self.p_writer_prompt.toPlainText().strip()
        store.save_project(project)
        log_fn("info", "正文AI角色提示词已保存（%d 字，仅正文AI生效）。"
               % len(project.story_writer_prompt))

    def _save_main_prompt(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        project.story_main_prompt = self.p_main_prompt.toPlainText().strip()
        store.save_project(project)
        log_fn("info", "主AI全局提示词已保存（%d 字，仅主AI生效）。"
               % len(project.story_main_prompt))

    # ---------- 情景写作提示词：本项目主AI可用库（v1.18 勾选 → v1.21 只读显示；管理在「情景提示词」页） ----------
    def _refresh_scene_cards(self, project):
        """渲染本项目主AI可用情景卡库（project.scene_cards，只读；管理在「情景提示词」功能页）。"""
        self.scene_cards_list.blockSignals(True)
        self.scene_cards_list.clear()
        cards = [c for c in (getattr(project, "scene_cards", None) or [])
                 if isinstance(c, dict) and str(c.get("name") or "").strip()
                 and str(c.get("content") or "").strip()]
        if not cards:
            self.scene_cards_list.addItem(
                "（本项目主AI可用库为空——到「情景提示词」页从总库加入，"
                "或让主AI在缺匹配类型时自做一张只进本库）")
        else:
            for c in cards:
                nm = str(c.get("name") or "").strip()
                ct = str(c.get("content") or "").strip()
                src = "我提供" if str(c.get("source") or "").strip() != "ai" else "AI 制作"
                preview = ct[:50] + ("…" if len(ct) > 50 else "")
                self.scene_cards_list.addItem("■ [%s] %s（%d 字）：%s" % (src, nm, len(ct), preview))
        self.scene_cards_list.blockSignals(False)

    def _goto_scene_cards(self):
        """跳转到「情景提示词」功能页管理本项目情景卡。"""
        try:
            self.app.switch_page(11)
        except Exception:
            log_fn("info", "请在左侧导航点「情景提示词」页管理本项目情景卡。")

    def _adapt_scene_cards(self):
        """v1.42 主AI按本项目正文AI基础文风适配项目库情景卡（只改项目库、不动总库）。"""
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        if not busy_guard(self):
            return
        cards = [c for c in (getattr(project, "scene_cards", None) or [])
                 if isinstance(c, dict) and str(c.get("name") or "").strip()
                 and str(c.get("content") or "").strip()]
        if not cards:
            QMessageBox.warning(self, "提示", "本项目情景卡库为空——先到「情景提示词」页把卡加入本项目再适配。")
            return
        if not (project.story_writer_prompt or "").strip():
            QMessageBox.warning(self, "提示", "尚未设置正文AI角色提示词（文风参考②）——适配以它为文风基准，先填写保存。")
            return
        if QMessageBox.question(self, "按本文风适配情景卡",
                "将让主AI按本项目的「正文AI角色提示词」文风，逐张改写本项目库 %d 张情景卡"
                "（%s…）。\n\n保持各卡情景内核/卡名/分类不变，只调整写法表述契合文风；"
                "只改本项目库、不动总库。\n\n继续？"
                % (len(cards), "、".join(str(c.get("name") or "") for c in cards[:3]))) \
                != QMessageBox.StandardButton.Yes:
            return
        set_running(True)
        log_fn("info", "开始按项目正文文风适配 %d 张项目库情景卡…" % len(cards))

        def work():
            try:
                from engine import NovelEngine
                eng = NovelEngine(store)
                r = eng.adapt_project_scene_cards(project)
                ok_n = r.get("ok", 0) if isinstance(r, dict) else 0
                failed = (r.get("failed") or []) if isinstance(r, dict) else []
                log_fn("info", "情景卡适配完成：%d 张成功%s" % (
                    ok_n, ("，%d 张失败：%s" % (len(failed), "、".join(failed))) if failed else "。"))
                QTimer.singleShot(0, lambda: (self._refresh_scene_cards(project),
                                              QMessageBox.information(
                                                  self, "适配完成",
                                                  "已按本文风适配 %d 张情景卡%s。"
                                                  % (ok_n, ("；%d 张失败：%s"
                                                            % (len(failed), "、".join(failed)))
                                                     if failed else ""))))
            except Exception as e:
                log_fn("error", "情景卡适配失败：%s" % e)
                QTimer.singleShot(0, lambda: QMessageBox.warning(self, "适配失败", str(e)))
            finally:
                set_running(False)

        threading.Thread(target=work, daemon=True).start()

    # ---------- 写后校对（v0.81：开关 + 提示词，改动防抖自动保存） ----------
    def _proofread_dirty(self, _val=None):
        self._proofread_timer.start()

    def _proofread_group_enable(self, checked):
        self.pr_hint.setEnabled(checked)
        self.proofread_edit.setEnabled(checked)

    def _save_proofread(self):
        cfg = config.load_config()
        cfg["proofread_enabled"] = self.proofread_chk.isChecked()
        rules = self.proofread_edit.toPlainText().strip()
        cfg["proofread_rules"] = rules if rules else None
        cfg["deai_nearby_chapters"] = self.proof_near_spin.value()   # v1.07 前后章节参考
        config.save_config(cfg)
        config._cache = None
        self.pr_status.setText("✓ 已自动保存：校对%s，规则 %d 字，前后参考 %d 章"
                               % ("开" if cfg["proofread_enabled"] else "关",
                                  len(rules), self.proof_near_spin.value()))
        log_fn("info", "写后校对设置已保存（启用=%s，前后参考=%d 章）"
               % ("开" if cfg["proofread_enabled"] else "关", self.proof_near_spin.value()))

    def _save_world(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        project.story_world = self.p_world.toPlainText().strip()
        store.save_project(project)
        log_fn("info", "世界观已保存（%d 字）。" % len(project.story_world))

    def _save_rules(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        project.story_rules = self.p_rules.toPlainText().strip()
        store.save_project(project)
        log_fn("info", "特殊规则已保存（%d 字）。" % len(project.story_rules))

    # ---------- 设定锚点（项目 Lorebook） ----------
    def _lore_entry_item_text(self, e):
        tag = "常驻" if e.get("always") else ("关键词：" + "、".join(e.get("keys") or []))
        title = (e.get("title") or "").strip() or "（无标题）"
        content = (e.get("content") or "").strip().replace("\n", " ")
        return "【%s】%s — %s" % (tag, title, content[:48] + ("…" if len(content) > 48 else ""))

    def _lore_refresh(self):
        store, project = current_project()
        if not project:
            self.lore_list.clear()
            return
        self.lore_list.blockSignals(True)
        self.lore_list.clear()
        for e in project.lore_entries or []:
            self.lore_list.addItem(self._lore_entry_item_text(e))
        self.lore_list.blockSignals(False)

    def _lore_save_entries(self, entries):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        project.lore_entries = entries
        store.save_project(project)
        self._lore_refresh()
        log_fn("info", "设定锚点已保存（%d 条）。" % len(entries))

    def _lore_add(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        dlg = LoreEntryDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        entry = dlg.value()
        if not (entry.get("content") or "").strip():
            QMessageBox.warning(self, "提示", "内容不能为空。")
            return
        self._lore_save_entries((project.lore_entries or []) + [entry])

    def _lore_edit(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        row = self.lore_list.currentRow()
        entries = list(project.lore_entries or [])
        if row < 0 or row >= len(entries):
            QMessageBox.warning(self, "提示", "请先选中一条锚点。")
            return
        dlg = LoreEntryDialog(self, entries[row])
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        entries[row] = dlg.value()
        self._lore_save_entries(entries)

    def _lore_del(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        row = self.lore_list.currentRow()
        entries = list(project.lore_entries or [])
        if row < 0 or row >= len(entries):
            QMessageBox.warning(self, "提示", "请先选中一条锚点。")
            return
        if QMessageBox.question(self, "确认删除", "删除锚点「%s」？" % (entries[row].get("title") or "无标题")) \
                != QMessageBox.StandardButton.Yes:
            return
        entries.pop(row)
        self._lore_save_entries(entries)

    def _plan_targets(self):
        """收集勾选的三栏目标（用于 AI 辅助/创建）。"""
        targets = []
        if self.plan_chk_story.isChecked():
            targets.append("story")
        if self.plan_chk_world.isChecked():
            targets.append("world")
        if self.plan_chk_rules.isChecked():
            targets.append("rules")
        return targets

    def _plan_ai(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        targets = self._plan_targets()
        if not targets:
            QMessageBox.warning(self, "提示", "请至少勾选一个要生成的部分。")
            return
        if not busy_guard(self):
            return
        # 主线程先取好全部 UI 值，后台线程只读这些快照（Qt 控件禁跨线程访问）
        opening = "\n\n".join([
            (self.p_story.toPlainText().strip() or ""),
            (self.p_world.toPlainText().strip() or ""),
            (self.p_rules.toPlainText().strip() or ""),
        ]).strip()
        notes = self.plan_notes.text().strip()
        constraint = self.plan_constraint.text().strip()
        self.plan_btn.setEnabled(False)
        self.plan_btn.setText("AI 生成中…")
        set_running(True)

        def work():
            try:
                # 把现有栏内容作为草稿基础传给 AI（顺着已有设定完善）
                data = main_ai.plan_story_ai(opening, notes, constraint, targets)
                self.worker.plan_ready.emit(data if isinstance(data, dict) else {})
            except Exception as e:
                self.worker.failed.emit(str(e))
            finally:
                set_running(False)

        threading.Thread(target=work, daemon=True).start()

    def _on_plan_ready(self, data):
        self.plan_btn.setEnabled(True)
        self.plan_btn.setText("AI 生成所选")
        if data.get("story"):
            self.p_story.setPlainText(str(data["story"]).strip())
        if data.get("world"):
            self.p_world.setPlainText(str(data["world"]).strip())
        if data.get("rules"):
            self.p_rules.setPlainText(str(data["rules"]).strip())
        log_fn("info", "AI 已生成所选部分，检查后点「保存故事设定」生效。")

    def _create_with_ai(self):
        """新建项目：按想法让 AI 起草勾选的三栏，然后创建。"""
        title = self.new_title.text().strip()
        if not title:
            QMessageBox.warning(self, "提示", "请填写小说标题。")
            return
        targets = []
        if self.new_chk_story.isChecked():
            targets.append("story")
        if self.new_chk_world.isChecked():
            targets.append("world")
        if self.new_chk_rules.isChecked():
            targets.append("rules")
        if not targets:
            QMessageBox.warning(self, "提示", "请至少勾选一个让 AI 生成的部分（或点「直接创建项目」）。")
            return
        if not busy_guard(self):
            return
        # 主线程取 UI 快照；新项目没有已有设定草稿，只把想法传一次给 AI
        idea = self.new_story.toPlainText().strip()
        self.new_ai_btn.setEnabled(False)
        self.new_ai_btn.setText("AI 生成中…")
        set_running(True)

        def work():
            try:
                data = main_ai.plan_story_ai("", idea, "", targets)
                self.worker.create_ready.emit({
                    "title": title,
                    "data": data if isinstance(data, dict) else {},
                })
            except Exception as e:
                self.worker.failed.emit(str(e))
            finally:
                set_running(False)

        threading.Thread(target=work, daemon=True).start()

    def _on_create_ready(self, payload):
        self.new_ai_btn.setEnabled(True)
        self.new_ai_btn.setText("AI 生成并创建")
        title = payload.get("title", "")
        data = payload.get("data") or {}
        story = str(data.get("story") or "").strip()
        world = str(data.get("world") or "").strip()
        rules = str(data.get("rules") or "").strip()
        if not (story or world or rules):
            QMessageBox.warning(self, "提示", "AI 没有生成出内容，请换个想法或改勾选后重试。")
            return
        self.new_title.clear()
        self.new_story.clear()
        self._do_create(title, story, world, rules)
        log_fn("info", "已用 AI 生成的故事设定创建项目：%s" % title)

    def _on_plan_failed(self, msg):
        self.plan_btn.setEnabled(True)
        self.plan_btn.setText("AI 生成所选")
        self.new_ai_btn.setEnabled(True)
        self.new_ai_btn.setText("AI 生成并创建")
        QMessageBox.warning(self, "生成失败", msg)

    def _delete_selected(self):
        """删除项目下拉中选中的任意项目（无需先载入）。"""
        dir_name = self.proj_combo.currentData()
        if not dir_name:
            QMessageBox.warning(self, "提示", "请先在顶部选择要删除的项目。")
            return
        title = self.proj_combo.currentText()
        ret = QMessageBox.question(self, "确认删除",
                                   "确定删除项目「%s」？所有章节与角色数据将不可恢复。" % title)
        if ret != QMessageBox.StandardButton.Yes:
            return
        storage.delete_project(dir_name)
        if APP["project_dir"] == dir_name:
            self.app.select_project(None)
            projects = storage.list_projects()
            if projects:
                self.app.select_project(projects[0]["dir"])
        self.on_show()
        log_fn("info", "已删除项目：%s" % title)


class NewProjectDialog(QDialog):
    """顶部「新建项目」弹窗：标题 + 故事描述（可留空）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("新建项目")
        self.resize(540, 320)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)
        lay.addWidget(QLabel("小说标题"))
        self.title = QLineEdit()
        self.title.setPlaceholderText("例：星海孤城")
        lay.addWidget(self.title)
        lay.addWidget(QLabel("故事描述（可留空，创建后到「故事设定」页再写）"))
        self.story = QPlainTextEdit()
        self.story.setPlaceholderText(
            "用自然语言写下你想让主 AI 知道的故事：世界观、开局、剧情走向、关键事件、结尾方向…")
        self.story.setMinimumHeight(130)
        lay.addWidget(self.story)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("创建")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)


class LoreEntryDialog(QDialog):
    """设定锚点条目编辑弹窗：标题 / 关键词（逗号分隔）/ 内容 / 是否常驻。"""

    def __init__(self, parent=None, entry=None):
        super().__init__(parent)
        self.setWindowTitle("设定锚点条目" if entry else "新增设定锚点")
        self.resize(560, 380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)
        lay.addWidget(QLabel("标题（可空；如「铁砧城」「主角的断臂」）"))
        self.title = QLineEdit()
        lay.addWidget(self.title)
        lay.addWidget(QLabel("关键词（逗号分隔；剧情文本命中任一关键词时本条自动注入；「常驻」条目不需要填）"))
        self.keys = QLineEdit()
        self.keys.setPlaceholderText("例：铁砧城, 城主府, 北境")
        lay.addWidget(self.keys)
        lay.addWidget(QLabel("内容（设定的具体描述，写入正文/决断/审查的上下文）"))
        self.content = QPlainTextEdit()
        self.content.setPlaceholderText(
            "例：铁砧城是北境唯一能锻造符文钢的城邦，城主府垄断矿脉，城内严禁私斗。")
        self.content.setMinimumHeight(120)
        lay.addWidget(self.content)
        self.always = QCheckBox("常驻注入（每章必带，不依赖关键词）")
        lay.addWidget(self.always)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("保存")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)

        if entry:
            self.title.setText(entry.get("title") or "")
            self.keys.setText("、".join(entry.get("keys") or []))
            self.content.setPlainText(entry.get("content") or "")
            self.always.setChecked(bool(entry.get("always")))

    def value(self):
        import uuid as _uuid
        keys = [k.strip() for k in self.keys.text().replace("，", ",").split(",")
                if k.strip()]
        return {
            "id": _uuid.uuid4().hex[:12],
            "title": self.title.text().strip(),
            "keys": keys,
            "content": self.content.toPlainText().strip(),
            "always": self.always.isChecked(),
        }