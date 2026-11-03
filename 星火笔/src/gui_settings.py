# -*- coding: utf-8 -*-
"""设置页：多 API 配置管理（新增/复制/删除/设为当前/分用途）+ 模型参数。"""
import copy
import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox,
                               QFormLayout, QFrame, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMessageBox, QPushButton,
                               QRadioButton, QScrollArea, QSpinBox, QVBoxLayout,
                               QWidget)

import config as app_config
import llm as llm_mod
from gui_app import log_fn
from gui_theme import THEME_LABELS, T, apply_theme, set_theme, theme_label

ROLE_TEXT = {"all": "通用", "decide": "主AI决断", "reason": "角色推理",
             "write": "正文写作", "deai": "去AI味", "review": "审查AI"}

# (键, 标签, 下限, 上限, 类型) —— float 用小数步进（如温度 0.8），int 为整数
API_PARAMS = [
    ("temperature", "温度（temperature）", 0.0, 2.0, "float"),
    ("max_tokens", "max_tokens（单次输出上限）", 1, 1000000, "int"),
    ("chapter_target_chars", "每章目标字数", 800, 20000, "int"),
    # v1.17 正文长度上下限（0=随目标自动：下限×0.8、上限×1.15；上限不设死，用户自决）
    ("chapter_min_chars", "正文下限字数（0=随目标自动）", 0, 999999, "int"),
    ("chapter_max_chars", "正文上限字数（0=随目标自动）", 0, 999999, "int"),
    ("max_workers", "并行推理并发数", 1, 12, "int"),
    ("request_timeout", "单次请求超时（秒）", 30, 999999, "int"),
    ("retry_times", "请求失败重试次数（0=不重试）", 0, 20, "int"),
    ("retry_interval", "重试间隔（秒）", 1, 300, "int"),
    ("rate_limit_min_wait", "429限流最小等待（秒）", 1, 60, "int"),
    ("compress_interval", "主AI压缩管理笔记间隔（章）", 1, 50, "int"),
    ("writer_recent_chapters", "正文AI可读前几章正文", 0, 10, "int"),
    ("foreshadow_overdue_chapters", "伏笔逾期阈值（章）", 1, 99, "int"),
]


def _full_choice(p, is_cur):
    role = ROLE_TEXT.get(p.get("role", "all"), "通用")
    mark = "● 当前　" if is_cur else "　"
    key = "已填 Key" if (p.get("api_key") or "").strip() else "未填 Key"
    return "%s%s（%s）[%s]" % (mark, p.get("name", "?"), role, key)


class SettingsPage(QWidget):

    _models_fetched = Signal(object)   # ("ok", [models]) | ("err", msg)：模型列表拉取完成回主线程

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._loading = True   # on_show 加载值期间不触发自动保存
        self._fetching = False
        self._models_fetched.connect(self._on_models_fetched)
        # 参数改动自动保存（600ms 防抖）：改完即存，不再依赖手动点「保存参数」
        self._param_timer = QTimer(self)
        self._param_timer.setSingleShot(True)
        self._param_timer.setInterval(600)
        self._param_timer.timeout.connect(self._save_params)

        # 整页滚动：内容超出窗口高度时用页面滚动条，不再被压缩成一小点
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        host = QWidget()
        lay = QVBoxLayout(host)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)
        self.scroll.setWidget(host)
        outer.addWidget(self.scroll)

        # ================= 界面风格（v1.74：只换配色，不动任何功能） =================
        theme_box = QGroupBox("界面风格（配色可随时切换，只换皮肤不改功能）")
        tlay = QHBoxLayout(theme_box)
        tlay.setSpacing(18)
        self.theme_radios = []
        for _tname, _tlabel in THEME_LABELS:
            rb = QRadioButton(_tlabel)
            rb.toggled.connect(lambda on, n=_tname: self._pick_theme(n) if on else None)
            tlay.addWidget(rb)
            self.theme_radios.append((_tname, rb))
        tlay.addStretch(1)
        theme_tip = QLabel("切换后立即生效并记住，下次打开还是这套配色。")
        theme_tip.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        tlay.addWidget(theme_tip)
        lay.addWidget(theme_box)

        # ================= API 配置 =================
        api_box = QGroupBox("API 配置（可保存多套密钥/模型，随时切换；还能让主AI决断、角色推理、正文写作各用不同模型）")
        alay = QHBoxLayout(api_box)
        alay.setSpacing(12)

        # 左：列表 + 操作
        left = QVBoxLayout()
        self.list = QListWidget()
        self.list.setMinimumHeight(360)
        self.list.currentRowChanged.connect(self._load_row_to_form)
        left.addWidget(self.list, 1)
        ops = QHBoxLayout()
        new_btn = QPushButton("新增")
        new_btn.clicked.connect(self._add)
        dup_btn = QPushButton("复制")
        dup_btn.clicked.connect(self._dup)
        cur_btn = QPushButton("设为当前")
        cur_btn.setObjectName("primary")
        cur_btn.clicked.connect(self._set_current)
        del_btn = QPushButton("删除")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._delete)
        ops.addWidget(new_btn)
        ops.addWidget(dup_btn)
        ops.addWidget(cur_btn)
        ops.addWidget(del_btn)
        left.addLayout(ops)
        alay.addLayout(left, 3)

        # 右：表单
        form_w = QWidget()
        form = QFormLayout(form_w)
        form.setSpacing(10)
        self.e_name = QLineEdit()
        self.e_name.setPlaceholderText("配置名（用于区分与切换）")
        self.e_url = QLineEdit()
        self.e_url.setPlaceholderText("例：https://api.deepseek.com/v1")
        self.e_key = QLineEdit()
        self.e_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_key.setPlaceholderText("sk-…（仅存本地 data/config.json，不入 git）")
        self.e_model = QComboBox()
        self.e_model.setEditable(True)
        self.e_model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.e_model.setPlaceholderText("例：deepseek-chat / gpt-4o / qwen-plus")
        form.addRow("配置名", self.e_name)
        form.addRow("API 地址 base_url", self.e_url)
        form.addRow("API Key", self.e_key)
        model_row = QHBoxLayout()
        model_row.addWidget(self.e_model, 1)
        self.fetch_btn = QPushButton("拉取模型")
        self.fetch_btn.setToolTip("从该 API 网关自动拉取可用模型列表（GET /models）供下拉选择，"
                                  "也可继续手动输入")
        self.fetch_btn.clicked.connect(self._fetch_models_clicked)
        model_row.addWidget(self.fetch_btn)
        form.addRow("模型名", model_row)
        save_api = QPushButton("保存当前配置")
        save_api.setObjectName("primary")
        save_api.clicked.connect(self._save_current)
        form.addRow("", save_api)
        tip = QLabel("切换：点下方列表选中 → 点「设为当前」。当前配置作为「通用」兜底，"
                     "三个环节想用不同模型请用下方「用途分工」各选一个配置。")
        tip.setWordWrap(True)
        tip.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        form.addRow("", tip)
        alay.addWidget(form_w, 4)

        lay.addWidget(api_box)

        # ================= 用途分工（各环节各用哪个 API + 思考强度） =================
        role_box = QGroupBox("用途分工（各环节选 API 配置 + 独立思考强度；"
                             "「思考」跟随全局=用上方全局思考强度设置）")
        rlay = QVBoxLayout(role_box)
        rlay.setSpacing(6)
        self.role_combos = {}
        self.think_combos = {}
        _roles = [("decide", "主AI决断与校验", "剧情走向 / 出场决断 / 战后更新 / 压缩笔记"),
                  ("write", "正文写作", "每章正文的执笔模型"),
                  ("reason", "角色推理", "代入角色卡推理各角色行为"),
                  ("deai", "去AI味润色", "洗稿 / 润色去AI味（可另用便宜或更有文学味的模型）"),
                  ("review", "审查AI", "正文与主AI验收之间的审查（招式/命名/行为/文风把关，"
                   "可另用更严格的模型；未指定时跟随主AI决断配置）"),
                  ("write_tool", "码字AI（续写/段落工具）", "码字页 AI 续写 + AI 段落工具（润色/扩写/"
                   "缩写/去AI味）；可另选便宜的模型，未指定时跟随正文写作"),
                  ("break", "拆书工坊", "拆书四阶段 + 逐块人物抽取/角色卡/管理笔记（调用量很大，"
                   "可另选便宜/快的模型）"),
                  ("import", "小说导入成项目", "导入专属环节（默认跟随拆书工坊配置；"
                   "未完成小说还原成项目时可单独选更好的模型）"),
                  ("scene_card", "情景提示词制作", "情景提示词页·AI 一键生成 / 从文本提取情景规则卡"
                   "（可另选便宜/快的模型；未指定时跟随通用）"),
                  ("style_a", "文风校对·节点A", "提取文风特征（原文 → 文风提示词）"),
                  ("style_b", "文风校对·节点B", "按文风提示词生成文章（调用量大，可另选便宜/快的）"),
                  ("style_c", "文风校对·节点C", "评分对比（生成文 vs 原文，回复 0-100）"),
                  ("style_d", "文风校对·节点D", "优化文风提示词（多轮迭代核心）"),
                  ("chat", "AI对话", "对话页（话题/联网/附件/编辑；接口测试与小说内容交流）")]
        for key, label, desc in _roles:
            row = QHBoxLayout()
            lab = QLabel(label)
            lab.setFixedWidth(150)
            row.addWidget(lab)
            combo = QComboBox()
            combo.setMinimumWidth(200)
            combo.currentIndexChanged.connect(self._save_role_profiles)
            row.addWidget(combo, 1)
            tlab = QLabel("思考")
            tlab.setStyleSheet(T("color:#5b6470;font-size:12px;"))
            row.addWidget(tlab)
            tcombo = QComboBox()
            tcombo.addItem("跟随全局", "")
            tcombo.addItem("关闭思考（最快）", "off")
            tcombo.addItem("低（low）", "low")
            tcombo.addItem("中（medium）", "medium")
            tcombo.addItem("高（high）", "high")
            tcombo.addItem("最大（max）", "max")
            tcombo.setToolTip("该功能自己的 thinking 强度（reasoning_effort）；"
                              "「跟随全局」= 用上方全局思考强度设置；\n"
                              "JSON 环节（决断/推理/校验等）设「关闭/低」可显著提速，正文写作留默认或「高」保质量")
            tcombo.setMinimumWidth(110)
            tcombo.currentIndexChanged.connect(self._save_role_profiles)
            row.addWidget(tcombo)
            d = QLabel(desc)
            d.setStyleSheet(T("color:#5b6470;font-size:12px;"))
            row.addWidget(d)
            rlay.addLayout(row)
            self.role_combos[key] = combo
            self.think_combos[key] = tcombo
        role_tip = QLabel("给各环节各选一个已保存的 API 配置（下拉里即上面的配置名）；"
                          "选「（不指定）」则该环节用「通用/当前」配置。改动即自动保存。")
        role_tip.setWordWrap(True)
        role_tip.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        rlay.addWidget(role_tip)
        lay.addWidget(role_box)

        # ================= 生成参数（常用 / 高级 两组） =================
        pbox = QGroupBox("生成参数（常用即可，高级一般保持默认；悬停有说明）")
        play = QVBoxLayout(pbox)
        play.setSpacing(10)

        self.spins = {}
        _spin_tips = {
            "max_tokens": "单次输出上限（兜底）。软件已按环节自动取合理值（决断/推理等 8000、写作=目标字数×3、"
                           "去AI味 16000），此项只需保证不小于自动值即可，一般不用改",
            "request_timeout": "单次请求的最长等待（秒）。官方 API 正常几秒返回，建议 300-600；"
                               "设太大时若 API 卡住不返回，软件会一直干等",
            "retry_times": "请求失败（429/5xx/超时/网络错误）自动重试的次数；0 = 失败即报错",
            "retry_interval": "每次重试前等待的秒数（固定间隔，429 限流额外不低于下方「最小等待」）",
            "rate_limit_min_wait": "429 限流时的最小等待（秒）：限流窗口按分钟计，实际等待取它与重试间隔的较大值",
            "max_workers": "并行推理并发数：同时推理的角色数，越大越快但越容易触发限流",
            "compress_interval": "每多少章让主AI压缩一次管理笔记（额外一次调用；章数越小压缩越勤、越慢）",
            "foreshadow_overdue_chapters": "伏笔埋设后超过多少章未回收 → 标记「⚠逾期N章」，"
                                           "并在主AI决断/校验/压缩/审查里强提醒优先回收。"
                                           "慢节奏文可调大，快节奏/强悬念文可调小",
        }

        def _make_cell(key, label, lo, hi, kind):
            col = QVBoxLayout()
            col.setSpacing(4)
            col.addWidget(QLabel(label))
            if kind == "float":
                sp = QDoubleSpinBox()
                sp.setRange(lo, hi)
                sp.setDecimals(2)
                sp.setSingleStep(0.1)
                sp.setValue(1.0)
            else:
                sp = QSpinBox()
                sp.setRange(int(lo), int(hi))
                sp.setValue(2000 if key == "chapter_target_chars" else
                            (0 if key in ("chapter_min_chars", "chapter_max_chars") else 100))
            sp.setMinimumWidth(140)
            tip = _spin_tips.get(key)
            if tip:
                sp.setToolTip(tip)
                col.itemAt(0).widget().setToolTip(tip)
            self.spins[key] = sp
            sp.valueChanged.connect(self._on_param_dirty)
            col.addWidget(sp)
            return col

        _by_key = {k: (k, lbl, lo, hi, kind) for k, lbl, lo, hi, kind in API_PARAMS}

        # ---- 常用 ----
        cbox = QGroupBox("常用")
        clay = QGridLayout(cbox)
        clay.setHorizontalSpacing(24)
        clay.setVerticalSpacing(10)
        common_keys = ["chapter_target_chars", "chapter_min_chars", "chapter_max_chars",
                       "temperature", "request_timeout", "max_workers"]
        for i, key in enumerate(common_keys):
            r, c = divmod(i, 2)
            clay.addLayout(_make_cell(*_by_key[key]), r, c)
        # 推理方式（常用）
        mc = QVBoxLayout()
        mc.setSpacing(4)
        mc.addWidget(QLabel("角色推理方式"))
        self.mode_seq = QRadioButton("分步串行（省额度、稳限速）")
        self.mode_par = QRadioButton("并行推理（更快，注意限速）")
        mode_tip = "每章出场的多个角色逐个推理（串行）还是同时推理（并行）。\n" \
                   "并行更快（并发数见「并行推理并发数」），但并发请求更容易触发 429 限流。"
        self.mode_seq.setToolTip(mode_tip)
        self.mode_par.setToolTip(mode_tip)
        mc.addWidget(self.mode_seq)
        mc.addWidget(self.mode_par)
        clay.addLayout(mc, 0, 2)
        # v1.68 码字 AI 任务上下文（续写/段落工具共用；省 token 可关）
        ctx_tip = ("控制「码字」页 AI 续写与「AI 段落工具」在提示词中附带多少上下文：\n"
                   "· 正文AI文风要求：正文AI提示词 + 文风参考/风格要点，让任务贴合小说的既定文风；\n"
                   "· 主AI笔记+故事设定：剧情发展/世界观/特殊规则 + 管理笔记/重要角色档案/灵感/知识库，"
                   "让任务贴合世界主线与人设；\n"
                   "· 涉及人物读取推理：按项目角色卡（近几章出场 + 笔记点名）读取并推理人物的"
                   "行为/语言/情绪。\n"
                   "默认全开保证效果；需要省 token 时按任务关掉对应项（关掉该项则不注入对应内容）。")
        ctx_lbl = QVBoxLayout()
        ctx_lbl.setSpacing(4)
        cl = QLabel("码字 AI 任务上下文")
        cl.setToolTip(ctx_tip)
        ctx_lbl.addWidget(cl)
        clay.addLayout(ctx_lbl, 3, 0)
        self.ctx_style_chk = QCheckBox("正文AI文风要求")
        self.ctx_notes_chk = QCheckBox("故事设定+主AI笔记")
        self.ctx_rp_chk = QCheckBox("涉及人物读取推理")
        for chk in (self.ctx_style_chk, self.ctx_notes_chk, self.ctx_rp_chk):
            chk.setToolTip(ctx_tip)
            chk.toggled.connect(self._on_param_dirty)
        clay.addWidget(self.ctx_style_chk, 3, 1)
        clay.addWidget(self.ctx_notes_chk, 3, 2)
        clay.addWidget(self.ctx_rp_chk, 3, 3)
        play.addWidget(cbox)

        # ---- 高级 ----
        abox = QGroupBox("高级设置（一般保持默认即可）")
        alay = QGridLayout(abox)
        alay.setHorizontalSpacing(24)
        alay.setVerticalSpacing(10)
        adv_keys = ["max_tokens", "retry_times", "retry_interval",
                    "rate_limit_min_wait", "compress_interval", "writer_recent_chapters",
                    "foreshadow_overdue_chapters"]
        for i, key in enumerate(adv_keys):
            r, c = divmod(i, 3)
            alay.addLayout(_make_cell(*_by_key[key]), r, c)
        # 行为选项：审查策略 / 灵感来源（v0.60 修复：此前「伏笔逾期阈值」占 (2,0)，
        # 「审查策略」也放 (2,0) → 两功能在网格同一格重叠，看不到；全部顺延到第 3 行起）
        rc = QVBoxLayout()
        rc.setSpacing(4)
        rc.addWidget(QLabel("审查策略"))
        self.rewrite_chk = QRadioButton("生成后由主AI审查，不满意自动请正文AI重写（最多2轮）")
        self.rewrite_chk.setChecked(True)
        rc.addWidget(self.rewrite_chk)
        alay.addLayout(rc, 3, 0)
        sc = QVBoxLayout()
        sc.setSpacing(4)
        sc.addWidget(QLabel("灵感来源"))
        self.search_chk = QCheckBox("主AI联网搜索灵感")
        self.search_chk.setToolTip("开启后，主AI在不确知后续剧情走向时会联网搜索同类题材的写法做参考"
                                   "（Bing 中国搜索，无需 Key）。\n"
                                   "注意：每章最多触发 2 轮搜索（每轮最多 3 个查询）+ 每轮重判一次，"
                                   "会明显拖慢每章生成；不需要灵感时建议关闭。")
        sc.addWidget(self.search_chk)
        alay.addLayout(sc, 3, 1)
        # 推理思考强度（参考 deepseek-harness 的 reasoning_effort；不传=跟随 API 默认）
        ec = QVBoxLayout()
        ec.setSpacing(4)
        ec.addWidget(QLabel("推理思考强度"))
        self.effort_combo = QComboBox()
        self.effort_combo.addItem("跟随 API 默认（不传）", "")
        self.effort_combo.addItem("关闭思考（最快）", "off")
        self.effort_combo.addItem("低（low）", "low")
        self.effort_combo.addItem("高（high）", "high")
        self.effort_combo.addItem("最大（max）", "max")
        self.effort_combo.setToolTip("推理模型的思考强度（reasoning_effort，参考 dsh）。\n"
                                     "推理模型（如商汤 deepseek-v4-flash）不控制思考时每个请求先想很久，"
                                     "拖慢全流程。\n"
                                     "JSON 环节（决断/推理/校验）通常不需要深度思考，设「关闭/低」可显著提速；\n"
                                     "正文写作保留默认或「高」保质量。网关不认该参数时会忽略或报错，可随时改回。")
        ec.addWidget(self.effort_combo)
        alay.addLayout(ec, 3, 2)
        play.addWidget(abox)

        # 保存 / 重置（重置为参考 dsh 校准的默认值）
        pbtns = QHBoxLayout()
        pbtns.setSpacing(10)
        save_params = QPushButton("保存参数")
        save_params.setObjectName("primary")
        save_params.clicked.connect(self._save_params)
        reset_params = QPushButton("重置为默认")
        reset_params.setToolTip("把所有生成参数恢复为默认值（参考 deepseek-harness 校准：\n"
                                "max_tokens 兜底、重试 3 次、思考强度跟随 API 等）。\n"
                                "设置错了想恢复出厂时点它。")
        reset_params.clicked.connect(self._reset_params)
        pbtns.addWidget(save_params)
        pbtns.addWidget(reset_params)
        pbtns.addStretch(1)
        play.addLayout(pbtns)
        lay.addWidget(pbox)

        self.status = QLabel("")
        self.status.setStyleSheet(T("color:#d4a44c;"))
        lay.addWidget(self.status)
        lay.addStretch(1)

    # ---------- 数据操作 ----------
    def _cfg(self):
        return app_config.load_config()

    def refresh_all(self):
        cfg = self._cfg()
        cur = cfg.get("current_profile")
        self.list.blockSignals(True)
        self.list.clear()
        for p in cfg.get("api_profiles", []):
            self.list.addItem(_full_choice(p, p.get("name") == cur))
        self.list.blockSignals(False)
        if self.list.count():
            self.list.setCurrentRow(0)
            self._load_row_to_form(0)
        else:
            self._clear_form()
        self._refresh_role_combos()

    def on_show(self):
        self._loading = True
        cfg = self._cfg()
        self.refresh_all()
        _theme = cfg.get("ui_theme")
        for _tname, _rb in self.theme_radios:
            _rb.setChecked(_tname == _theme)
        self.spins["temperature"].setValue(float(cfg.get("temperature", 1.0)))
        self.spins["max_tokens"].setValue(int(cfg.get("max_tokens", 32000)))
        self.spins["chapter_target_chars"].setValue(int(cfg.get("chapter_target_chars", 2500)))
        self.spins["chapter_min_chars"].setValue(int(cfg.get("chapter_min_chars", 0)))
        self.spins["chapter_max_chars"].setValue(int(cfg.get("chapter_max_chars", 0)))
        self.spins["max_workers"].setValue(int(cfg.get("max_workers", 5)))
        self.spins["request_timeout"].setValue(int(cfg.get("request_timeout", 300)))
        self.spins["retry_times"].setValue(int(cfg.get("retry_times", 3)))
        self.spins["retry_interval"].setValue(int(cfg.get("retry_interval", 3)))
        self.spins["rate_limit_min_wait"].setValue(int(cfg.get("rate_limit_min_wait", 5)))
        self.spins["compress_interval"].setValue(int(cfg.get("compress_interval", 5)))
        self.spins["writer_recent_chapters"].setValue(int(cfg.get("writer_recent_chapters", 3)))
        self.spins["foreshadow_overdue_chapters"].setValue(
            int(cfg.get("foreshadow_overdue_chapters", 15)))
        # v1.68 码字 AI 任务上下文开关（回填）
        self.ctx_style_chk.setChecked(bool(cfg.get("tool_ctx_style", True)))
        self.ctx_notes_chk.setChecked(bool(cfg.get("tool_ctx_notes", True)))
        self.ctx_rp_chk.setChecked(bool(cfg.get("tool_ctx_rp", True)))
        self.search_chk.setChecked(bool(cfg.get("web_search_enabled", False)))
        if cfg.get("reasoning_mode") == "parallel":
            self.mode_par.setChecked(True)
        else:
            self.mode_seq.setChecked(True)
        self.rewrite_chk.setChecked(bool(cfg.get("auto_rewrite", True)))
        effort = cfg.get("reasoning_effort") or ""
        ei = self.effort_combo.findData(effort)
        self.effort_combo.setCurrentIndex(ei if ei >= 0 else 0)
        # v0.58 拆书参数不再混在设置页：模式/token/重叠/并行/提示词/L3 全在「拆书工坊」功能页
        # （文风校对的启用与规则在「项目」页·文风参考；v0.81 起撤销设置页「自定义禁词」栏；
        #  v1.18 情景规则卡移出设置页 → 独立「情景提示词」功能页 + 项目页/一键成书勾选启用）
        self._loading = False

    def _pick_theme(self, name):
        """界面风格切换（v1.74）：只换配色，立即生效并持久化，下次启动沿用。"""
        if self._loading:
            return
        from PySide6.QtWidgets import QApplication
        set_theme(name)
        _app = QApplication.instance()
        if _app is not None:
            apply_theme(_app, getattr(self.app, "_ui_scale", 1.0))
        cfg = self._cfg()
        cfg["ui_theme"] = name
        app_config.save_config(cfg)
        self.status.setText("界面风格已切换：%s" % theme_label(name))

    def _selected_index(self):
        row = self.list.currentRow()
        if row < 0:
            return -1
        cfg = self._cfg()
        if row >= len(cfg.get("api_profiles", [])):
            return -1
        return row

    def _load_row_to_form(self, row):
        if row < 0:
            return
        cfg = self._cfg()
        profs = cfg.get("api_profiles", [])
        if row >= len(profs):
            return
        p = profs[row]
        self.e_name.setText(p.get("name", ""))
        self.e_url.setText(p.get("base_url", ""))
        self.e_key.setText(p.get("api_key", ""))
        # v0.67 不再 clear() 抹掉已拉取的模型列表：拉取一次，各配置行都能从下拉选；
        # 只改当前文本（仍可手输任意模型 id）
        self.e_model.setEditText(p.get("model", ""))

    def _clear_form(self):
        for w in (self.e_name, self.e_url, self.e_key):
            w.clear()
        self.e_model.setEditText("")   # 保留已拉取模型列表（v0.67）

    def _add(self):
        cfg = self._cfg()
        profs = cfg.get("api_profiles", [])
        n = 1
        while any(p.get("name") == "新配置%d" % n for p in profs):
            n += 1
        profs.append({"name": "新配置%d" % n,
                      "base_url": "https://api.deepseek.com/v1",
                      "api_key": "", "model": "", "role": "all"})
        if not cfg.get("current_profile"):
            cfg["current_profile"] = profs[0]["name"]
        app_config.save_config(cfg)
        self.refresh_all()
        self.list.setCurrentRow(len(profs) - 1)
        log_fn("info", "已新增 API 配置。")

    def _dup(self):
        idx = self._selected_index()
        if idx < 0:
            QMessageBox.warning(self, "提示", "请先选中一个配置。")
            return
        cfg = self._cfg()
        profs = cfg.get("api_profiles", [])
        src = profs[idx]
        newp = copy.deepcopy(src)
        base = src.get("name", "配置") + " 副本"
        name = base
        n = 1
        while any(p.get("name") == name for p in profs):
            n += 1
            name = "%s %d" % (base, n)
        newp["name"] = name
        profs.append(newp)
        app_config.save_config(cfg)
        self.refresh_all()
        self.list.setCurrentRow(len(profs) - 1)
        log_fn("info", "已复制配置：%s" % name)

    def _set_current(self):
        idx = self._selected_index()
        if idx < 0:
            QMessageBox.warning(self, "提示", "请先选中一个配置。")
            return
        cfg = self._cfg()
        profs = cfg.get("api_profiles", [])
        cfg["current_profile"] = profs[idx]["name"]
        app_config.save_config(cfg)
        self.refresh_all()
        log_fn("info", "当前已切换为：%s" % profs[idx]["name"])
        self.status.setText("已切换为「%s」" % profs[idx]["name"])

    def _delete(self):
        idx = self._selected_index()
        if idx < 0:
            return
        cfg = self._cfg()
        profs = cfg.get("api_profiles", [])
        name = profs[idx]["name"]
        if len(profs) <= 1:
            QMessageBox.warning(self, "提示", "至少要保留一个配置。")
            return
        ret = QMessageBox.question(self, "删除配置", "确定删除配置「%s」？" % name)
        if ret != QMessageBox.StandardButton.Yes:
            return
        profs.pop(idx)
        if cfg.get("current_profile") == name:
            cfg["current_profile"] = profs[0]["name"]
        # 清理用途分工里对该配置的引用（避免指向已删除的配置）
        rp = cfg.get("role_profiles") or {}
        for k, v in list(rp.items()):
            if v == name:
                rp.pop(k, None)
        app_config.save_config(cfg)
        self.refresh_all()
        log_fn("info", "已删除配置：%s" % name)

    def _save_current(self):
        idx = self._selected_index()
        if idx < 0:
            QMessageBox.warning(self, "提示", "请先选中一个配置。")
            return
        name = self.e_name.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "配置名不能为空。")
            return
        cfg = self._cfg()
        profs = cfg.get("api_profiles", [])
        old_name = profs[idx]["name"]
        if name != old_name and any(p.get("name") == name for p in profs):
            QMessageBox.warning(self, "提示", "配置名「%s」已存在。" % name)
            return
        profs[idx]["name"] = name
        profs[idx]["base_url"] = self.e_url.text().strip().rstrip("/")
        profs[idx]["api_key"] = self.e_key.text().strip()
        profs[idx]["model"] = self.e_model.currentText().strip()
        if cfg.get("current_profile") == old_name:
            cfg["current_profile"] = name
        # 用途分工里引用了旧配置名的，跟随改名
        for role_key, pname in (cfg.get("role_profiles") or {}).items():
            if pname == old_name:
                cfg["role_profiles"][role_key] = name
        app_config.save_config(cfg)
        self.refresh_all()
        log_fn("info", "配置「%s」已保存。" % name)
        self.status.setText("「%s」已保存" % name)

    def _refresh_role_combos(self):
        """刷新用途分工：各行使下拉回填 role_profiles 指定配置，思考强度回填 role_thinking。"""
        cfg = self._cfg()
        rp = cfg.get("role_profiles") or {}
        rt = cfg.get("role_thinking") or {}
        profs = cfg.get("api_profiles", [])
        for key, combo in self.role_combos.items():
            combo.blockSignals(True)
            combo.clear()
            combo.addItem("（不指定 → 用通用/当前配置）", "")
            for p in profs:
                combo.addItem(p.get("name", "?"), p.get("name"))
            sel = rp.get(key)
            idx = combo.findData(sel) if sel else -1
            combo.setCurrentIndex(idx if idx >= 0 else 0)
            combo.blockSignals(False)
        for key, tcombo in self.think_combos.items():
            tcombo.blockSignals(True)
            val = rt.get(key) or ""
            idx = tcombo.findData(val)
            tcombo.setCurrentIndex(idx if idx >= 0 else 0)
            tcombo.blockSignals(False)

    def _save_role_profiles(self, _idx=None):
        """用途分工改动即保存：API 配置名写入 role_profiles，思考强度写入 role_thinking；
        拆书工坊/导入行同步 break_profile / import_profile（引擎读取键）；
        文风校对四节点行同步 style_profiles dict（引擎读取键；node_a 兼写旧单键 style_profile 兼容）。"""
        if self._loading:
            return
        cfg = self._cfg()
        rp = {}
        rt = {}
        for key, combo in self.role_combos.items():
            name = combo.currentData()
            if name:
                rp[key] = name
            tk = self.think_combos[key].currentData() or ""
            if tk:
                rt[key] = tk
        cfg["role_profiles"] = rp
        cfg["role_thinking"] = rt
        cfg["break_profile"] = str(rp.get("break") or "").strip()
        cfg["import_profile"] = str(rp.get("import") or "").strip()
        cfg["style_profiles"] = {
            "node_a": str(rp.get("style_a") or "").strip() or None,
            "node_b": str(rp.get("style_b") or "").strip() or None,
            "node_c": str(rp.get("style_c") or "").strip() or None,
            "node_d": str(rp.get("style_d") or "").strip() or None}
        cfg["style_profile"] = str(rp.get("style_a") or "").strip()
        app_config.save_config(cfg)
        parts = []
        label_of = {"decide": "主AI决断", "write": "正文写作", "reason": "角色推理",
                    "deai": "去AI味", "review": "审查", "break": "拆书工坊",
                    "write_tool": "码字AI", "import": "小说导入成项目", "scene_card": "情景提示词制作",
                    "style_a": "文风校对A",
                    "style_b": "文风校对B", "style_c": "文风校对C", "style_d": "文风校对D",
                    "chat": "AI对话"}
        for key, combo in self.role_combos.items():
            parts.append("%s=%s" % (label_of.get(key, key), rp.get(key, "不指定")))
        for key, tcombo in self.think_combos.items():
            tk = tcombo.currentData() or ""
            if tk:
                parts.append("%s-思考%s" % (label_of.get(key, key), tk))
        log_fn("info", "用途分工已保存：%s" % " ".join(parts))
        self.status.setText("用途分工已保存（改动即自动保存）")

    # ---------- 拉取模型列表（GET /models，后台线程避免卡设置页） ----------
    def _fetch_models_clicked(self):
        if self._fetching:
            return
        base_url = self.e_url.text().strip()
        api_key = self.e_key.text().strip()
        if not base_url or not api_key:
            QMessageBox.warning(self, "提示",
                                "请先填写 API 地址和 API Key，再拉取模型列表。")
            return
        self._fetching = True
        self.fetch_btn.setEnabled(False)
        self.fetch_btn.setText("拉取中…")
        threading.Thread(target=self._fetch_models_worker,
                         args=(base_url, api_key), daemon=True).start()

    def _fetch_models_worker(self, base_url, api_key):
        try:
            det = llm_mod.fetch_models_detailed(base_url, api_key)
            self._models_fetched.emit(("ok", det.get("models") or [],
                                       det.get("contexts") or {}))
        except Exception as e:
            self._models_fetched.emit(("err", str(e), {}))

    def _on_models_fetched(self, payload):
        self._fetching = False
        self.fetch_btn.setEnabled(True)
        self.fetch_btn.setText("拉取模型")
        status, data = payload[0], payload[1]
        contexts = payload[2] if len(payload) > 2 else {}
        if status == "err":
            QMessageBox.warning(self, "拉取失败",
                                "无法获取模型列表，请检查地址/Key 或网络后重试。\n%s" % data)
            return
        cur = self.e_model.currentText().strip()
        self.e_model.clear()
        for m in data:
            self.e_model.addItem(m)
        if cur:
            self.e_model.setEditText(cur)
        # v0.69 拉取后不再自动选中第一个模型：用户没选就不改编辑文本，
        # 避免「新建配置后拉取，模型名被莫名改成列表第一个」
        # v0.68 拉取后自动展开下拉：模型列表直接弹出可见（此前藏在 popup 里，
        # 编辑框只显示一个 id，用户不点箭头就看不到列表、误以为拉取失败）
        if self.e_model.count():
            self.e_model.showPopup()
        # v0.59：把网关返回的模型上下文长度记入当前配置（智能拆书按此自动定每部分大小）
        ctx = int(contexts.get(cur) or 0) if cur else 0
        cfg = self._cfg()
        idx = self._selected_index()
        if idx >= 0 and len(cfg.get("api_profiles", [])) > idx:
            cfg["api_profiles"][idx]["context_window"] = ctx
            app_config.save_config(cfg)
        log_fn("info", "已从网关拉取 %d 个可用模型%s。"
               % (len(data), "（%s 上下文 %d token）" % (cur, ctx) if ctx else "（网关未返回上下文长度）"))
        self.status.setText("已拉取 %d 个模型（可直接选，也可手动输入）%s"
                            % (len(data), "；%s 上下文 %d token" % (cur, ctx) if ctx else ""))

    # ---------- 参数改动防抖保存 ----------
    def _on_param_dirty(self, _val=None):
        """参数改动防抖：停止输入 0.6 秒后自动保存（用户无需手动点「保存参数」）。"""
        if self._loading:
            return
        self.status.setText("参数已修改，自动保存中…")
        self._param_timer.start()

    def _save_params(self, auto=False):
        cfg = self._cfg()
        cfg["temperature"] = self.spins["temperature"].value()
        cfg["max_tokens"] = self.spins["max_tokens"].value()
        cfg["chapter_target_chars"] = self.spins["chapter_target_chars"].value()
        cfg["chapter_min_chars"] = self.spins["chapter_min_chars"].value()
        cfg["chapter_max_chars"] = self.spins["chapter_max_chars"].value()
        cfg["max_workers"] = self.spins["max_workers"].value()
        cfg["request_timeout"] = self.spins["request_timeout"].value()
        cfg["retry_times"] = self.spins["retry_times"].value()
        cfg["retry_interval"] = self.spins["retry_interval"].value()
        cfg["rate_limit_min_wait"] = self.spins["rate_limit_min_wait"].value()
        cfg["compress_interval"] = self.spins["compress_interval"].value()
        cfg["writer_recent_chapters"] = self.spins["writer_recent_chapters"].value()
        cfg["foreshadow_overdue_chapters"] = self.spins["foreshadow_overdue_chapters"].value()
        cfg["web_search_enabled"] = self.search_chk.isChecked()
        cfg["reasoning_mode"] = "parallel" if self.mode_par.isChecked() else "sequential"
        cfg["auto_rewrite"] = self.rewrite_chk.isChecked()
        # v1.68 码字 AI 任务上下文开关（写入）
        cfg["tool_ctx_style"] = self.ctx_style_chk.isChecked()
        cfg["tool_ctx_notes"] = self.ctx_notes_chk.isChecked()
        cfg["tool_ctx_rp"] = self.ctx_rp_chk.isChecked()
        effort = self.effort_combo.currentData() or None
        cfg["reasoning_effort"] = effort
        # v0.81 撤销设置页「自定义禁词」栏：tone_words_custom 维持 config 已有值
        # （引擎正文编辑区波浪线标记仍可用，只是不再从这里维护）
        app_config.save_config(cfg)
        log_fn("info", "生成参数已保存。")
        self.status.setText("生成参数已保存（改动即自动保存）")

    def _reset_params(self):
        """重置生成参数为默认值（参考 deepseek-harness 校准），立即保存。

        默认值以 config.DEFAULT_CONFIG 为准：max_tokens 兜底语义、重试 3 次、
        reasoning_effort 跟随 API（不传）等。设置错了想恢复出厂时点它。
        """
        ret = QMessageBox.question(
            self, "重置参数",
            "确定把所有生成参数恢复为默认值吗？\n"
            "（默认值参考 deepseek-harness 校准：max_tokens 兜底、重试 3 次、"
            "推理思考强度跟随 API 默认等）")
        if ret != QMessageBox.StandardButton.Yes:
            return
        d = app_config.DEFAULT_CONFIG
        self.spins["temperature"].setValue(float(d.get("temperature", 1.0)))
        self.spins["max_tokens"].setValue(int(d.get("max_tokens", 32000)))
        self.spins["chapter_target_chars"].setValue(int(d.get("chapter_target_chars", 2500)))
        self.spins["chapter_min_chars"].setValue(int(d.get("chapter_min_chars", 0)))
        self.spins["chapter_max_chars"].setValue(int(d.get("chapter_max_chars", 0)))
        self.spins["max_workers"].setValue(int(d.get("max_workers", 5)))
        self.spins["request_timeout"].setValue(int(d.get("request_timeout", 300)))
        self.spins["retry_times"].setValue(int(d.get("retry_times", 3)))
        self.spins["retry_interval"].setValue(int(d.get("retry_interval", 3)))
        self.spins["rate_limit_min_wait"].setValue(int(d.get("rate_limit_min_wait", 5)))
        self.spins["compress_interval"].setValue(int(d.get("compress_interval", 5)))
        self.spins["writer_recent_chapters"].setValue(int(d.get("writer_recent_chapters", 3)))
        self.spins["foreshadow_overdue_chapters"].setValue(
            int(d.get("foreshadow_overdue_chapters", 15)))
        self.search_chk.setChecked(bool(d.get("web_search_enabled", False)))
        self.mode_seq.setChecked(True)
        self.rewrite_chk.setChecked(bool(d.get("auto_rewrite", True)))
        self.effort_combo.setCurrentIndex(0)
        self._save_params()
        self.status.setText("已重置为默认参数（参考 dsh 校准）")