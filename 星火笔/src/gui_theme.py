# -*- coding: utf-8 -*-
"""可爱 / 二次元主题体系（v1.74 UI 美化，v1.78 增「静谧石墨」低亮护眼，四套配色可切换）。

三条约定：
1. 四套主题共用同一组「语义色槽」(role)，QSS 模板全部用 %(role)s 取色；
2. 界面代码里的历史硬编码色（#8a93a3 / #5b6470 / #d4a44c …）保留为「规范字面量」，
   交给 T() 在**调用时**换算成当前主题色 —— 切换主题后新构造的控件也永远是最新配色；
3. set_theme() 只换当前主题；apply_theme() 再把**已存在**控件的 stylesheet / 只读富文本
   现场重映射一遍，做到免重启即时换肤。

四套风格：
- sakura 樱粉软萌（浅）：薰衣草+樱粉渐变底、白色大圆角卡片、柔粉强调；
- mint   薄荷奶油（浅）：奶油白 + 薄荷绿/天蓝强调，清爽不腻；
- night  二次元夜（深）：深紫夜空底 + 霓虹粉/青强调、发光描边；
- graphite 静谧石墨（深·低亮护眼）：暖中性石墨底 + 哑光金强调，低对比不刺眼，长时间码字用。
"""
import re as _re

# ============================ 配色表 ============================
_PALETTES = {
    # ---------------- 樱粉软萌（浅色） ----------------
    "sakura": {
        "bg1": "#fff7fa", "bg2": "#f9f0fb", "bg3": "#eef3fd",
        "nav1": "#fffafd", "nav2": "#f7eefa",
        "panel1": "#ffffff", "panel2": "#fdf6fa", "panel_top": "#ffe3ef",
        "card1": "#ffffff", "card2": "#fffafc", "card_top": "#ffe0ee",
        "cardh1": "#fff3f8", "cardh2": "#ffeaf3", "cardh_border": "#f7b9d2",
        "border": "#f3e0e9", "border_active": "#f4bcd4",
        "text": "#4a3a46", "text_soft": "#6d5866", "text_dim": "#9a8695",
        "text_dim2": "#ab96a4", "text_faint": "#bdaab6", "placeholder": "#d3c2cc",
        "accent": "#f4779f", "accent_deep": "#d9437c", "accent_text": "#e0508a",
        "accent_dark": "#ffe6f0", "accent_soft": "#ffeef5", "accent_border": "#f8b3cd",
        "on_accent": "#ffffff",
        "btn1": "#ffffff", "btn2": "#fdf2f7", "btn_border": "#f6cfe0",
        "btnh1": "#fff6fa", "btnh2": "#ffe9f2", "btnh_border": "#f291b8",
        "btn_press": "#ffe1ec", "btn_dis_fg": "#d6c6cf", "btn_dis_bg": "#fdf8fa",
        "input_bg": "#fffdfe", "input_border": "#f2dce7", "input_focus": "#f4779f",
        "sel_bg": "#ffd6e6", "sel_text": "#5a3a4a",
        "row_hover": "#fff2f8", "menu_bg": "#ffffff", "menu_sel_bg": "#ffe3ef",
        "menu_sel_fg": "#4a3a46", "tip_bg": "#fff7fb", "splitter": "#f7e3ec",
        "progress_bg": "#fdeef4",
        "green": "#4fa87a", "red": "#e2686f", "gold": "#d99a3c",
        "blue": "#6aa9dd", "warn": "#d9932b",
        "badge_ok_bg": "#e6f7ee", "badge_ok_fg": "#3f9169",
        "badge_dead_bg": "#fdeced", "badge_dead_fg": "#cf5f68",
        "badge_travel_bg": "#fdf4e0", "badge_travel_fg": "#b98a2a",
        "badge_n_bg": "#fdf1f6", "badge_n_fg": "#a08d9c",
        "title": "#e0508a", "subtitle": "#c6aebc",
        "scroll": "#f8d9e5", "scroll_hover": "#f2b6cd",
        "primary1": "#ffb4d0", "primary2": "#f4779f", "primary_fg": "#ffffff",
        "primary_border": "#f091b9", "primary_h1": "#ffc8dd", "primary_h2": "#f98cb1",
        "danger1": "#fde9ea", "danger_fg": "#cf5f68", "danger_border": "#f3bcc0",
        "danger_h1": "#fbdcdd",
        "ok1": "#e9f8f0", "ok_fg": "#3f9169", "ok_border": "#b6e0c8", "ok_h1": "#dcf3e6",
        "ghost_fg": "#9a8695",
        "tab_sel_bg": "#ffffff", "tab_sel_fg": "#d9437c", "tab_fg": "#a08d9c",
    },
    # ---------------- 薄荷奶油（浅色） ----------------
    "mint": {
        "bg1": "#f5fcf8", "bg2": "#eef9f4", "bg3": "#f0f7fb",
        "nav1": "#fbfffd", "nav2": "#eef9f4",
        "panel1": "#ffffff", "panel2": "#f8fdfa", "panel_top": "#cdeee0",
        "card1": "#ffffff", "card2": "#fbfefc", "card_top": "#d4f0e4",
        "cardh1": "#f2fdf8", "cardh2": "#e8f9f1", "cardh_border": "#a5dcc6",
        "border": "#dcf0e7", "border_active": "#a8dcc8",
        "text": "#33473d", "text_soft": "#556a5f", "text_dim": "#8aa398",
        "text_dim2": "#96ada2", "text_faint": "#b3c7bb", "placeholder": "#cbdbd1",
        "accent": "#3fc09b", "accent_deep": "#1f9c7b", "accent_text": "#1f9c7b",
        "accent_dark": "#e0f7ee", "accent_soft": "#eafaf4", "accent_border": "#9fdfca",
        "on_accent": "#ffffff",
        "btn1": "#ffffff", "btn2": "#f6fdfa", "btn_border": "#cdeade",
        "btnh1": "#f4fefb", "btnh2": "#e6f9f0", "btnh_border": "#6fd0ae",
        "btn_press": "#ddf6eb", "btn_dis_fg": "#c6d4cc", "btn_dis_bg": "#fbfefc",
        "input_bg": "#fcfffe", "input_border": "#dcefe7", "input_focus": "#3fc09b",
        "sel_bg": "#c9f3e2", "sel_text": "#2a4a3e",
        "row_hover": "#f0fcf7", "menu_bg": "#ffffff", "menu_sel_bg": "#ddf7ec",
        "menu_sel_fg": "#33473d", "tip_bg": "#f7fefb", "splitter": "#e4f4ec",
        "progress_bg": "#eefaf4",
        "green": "#2fa878", "red": "#e2686f", "gold": "#d99a3c",
        "blue": "#5aa8d8", "warn": "#d08f28",
        "badge_ok_bg": "#e4f8ef", "badge_ok_fg": "#258a63",
        "badge_dead_bg": "#fdeced", "badge_dead_fg": "#cf5f68",
        "badge_travel_bg": "#fdf4e0", "badge_travel_fg": "#b98a2a",
        "badge_n_bg": "#f2faf6", "badge_n_fg": "#8aa398",
        "title": "#1f9c7b", "subtitle": "#a9c2b6",
        "scroll": "#d5efe4", "scroll_hover": "#a5dcc6",
        "primary1": "#8ee6c9", "primary2": "#3fc09b", "primary_fg": "#ffffff",
        "primary_border": "#5ccfa9", "primary_h1": "#a9efd8", "primary_h2": "#55c9a4",
        "danger1": "#fdeced", "danger_fg": "#cf5f68", "danger_border": "#f3bcc0",
        "danger_h1": "#fbdedf",
        "ok1": "#e7f8f0", "ok_fg": "#258a63", "ok_border": "#a9dfc6", "ok_h1": "#d9f3e7",
        "ghost_fg": "#8aa398",
        "tab_sel_bg": "#ffffff", "tab_sel_fg": "#1f9c7b", "tab_fg": "#96ada2",
    },
    # ---------------- 二次元夜（深色） ----------------
    "night": {
        "bg1": "#12101f", "bg2": "#161129", "bg3": "#1b1533",
        "nav1": "#15122a", "nav2": "#191434",
        "panel1": "#1d1836", "panel2": "#191530", "panel_top": "#35295c",
        "card1": "#221c3f", "card2": "#1c1738", "card_top": "#3a2d64",
        "cardh1": "#2a2350", "cardh2": "#231d44", "cardh_border": "#5b4a92",
        "border": "#2c2554", "border_active": "#4c3f80",
        "text": "#e9e4f7", "text_soft": "#cbc4e8", "text_dim": "#9d94c4",
        "text_dim2": "#9188b8", "text_faint": "#736b96", "placeholder": "#5c5480",
        "accent": "#ff6fb5", "accent_deep": "#ff3f95", "accent_text": "#ff9ecd",
        "accent_dark": "#3a1a3c", "accent_soft": "#331d43", "accent_border": "#82407a",
        "on_accent": "#2b0d1e",
        "btn1": "#2a2350", "btn2": "#241e46", "btn_border": "#463a78",
        "btnh1": "#352c60", "btnh2": "#2d2555", "btnh_border": "#7d6bc0",
        "btn_press": "#1f1a3d", "btn_dis_fg": "#5a5378", "btn_dis_bg": "#1e1a38",
        "input_bg": "#150f28", "input_border": "#332a5e", "input_focus": "#ff6fb5",
        "sel_bg": "#4a2b6e", "sel_text": "#ffe6f5",
        "row_hover": "#241e48", "menu_bg": "#1f1a3c", "menu_sel_bg": "#3b2a63",
        "menu_sel_fg": "#ffe0f0", "tip_bg": "#221c42", "splitter": "#2a2352",
        "progress_bg": "#171232",
        "green": "#5fd6a8", "red": "#ff7a8f", "gold": "#ffd479",
        "blue": "#6fd3ff", "warn": "#ffc766",
        "badge_ok_bg": "#1c3a34", "badge_ok_fg": "#66e0b4",
        "badge_dead_bg": "#3d2030", "badge_dead_fg": "#ff8fa0",
        "badge_travel_bg": "#3a3020", "badge_travel_fg": "#ffd479",
        "badge_n_bg": "#241e44", "badge_n_fg": "#a79dd0",
        "title": "#ff8fc4", "subtitle": "#8d86b3",
        "scroll": "#3b2f66", "scroll_hover": "#6b58a8",
        "primary1": "#ff9ecd", "primary2": "#ff5fa8", "primary_fg": "#2b0d1e",
        "primary_border": "#a8457f", "primary_h1": "#ffb6da", "primary_h2": "#ff78b9",
        "danger1": "#3a1d2a", "danger_fg": "#ff8fa0", "danger_border": "#7a3348",
        "danger_h1": "#4a2434",
        "ok1": "#1a3a30", "ok_fg": "#6be0b6", "ok_border": "#2f6b57", "ok_h1": "#20493d",
        "ghost_fg": "#9d94c4",
        "tab_sel_bg": "#221c3f", "tab_sel_fg": "#ff9ecd", "tab_fg": "#9188b8",
    },
    # ---------------- 静谧石墨（深色·低亮护眼） ----------------
    # 长时间码字用：暖中性石墨底（不用纯黑）、柔化文字（不用纯白）、低饱和哑光金强调（无霓虹/发光）。
    "graphite": {
        "bg1": "#1b1a17", "bg2": "#1f1d19", "bg3": "#232019",
        "nav1": "#1d1b18", "nav2": "#21201b",
        "panel1": "#25231d", "panel2": "#201e19", "panel_top": "#3a3428",
        "card1": "#282620", "card2": "#232119", "card_top": "#3c3628",
        "cardh1": "#302d25", "cardh2": "#292720", "cardh_border": "#544c38",
        "border": "#332f28", "border_active": "#494335",
        "text": "#c9c3b4", "text_soft": "#b2ac9e", "text_dim": "#8f897b",
        "text_dim2": "#857e71", "text_faint": "#706a5e", "placeholder": "#5b554a",
        "accent": "#c2a068", "accent_deep": "#d8b87f", "accent_text": "#d8b87f",
        "accent_dark": "#2c2820", "accent_soft": "#2a2720", "accent_border": "#5c523d",
        "on_accent": "#241d10",
        "btn1": "#2a2720", "btn2": "#252219", "btn_border": "#3f392d",
        "btnh1": "#332f26", "btnh2": "#2c2921", "btnh_border": "#6a5e44",
        "btn_press": "#232019", "btn_dis_fg": "#585245", "btn_dis_bg": "#211f1a",
        "input_bg": "#191714", "input_border": "#342f27", "input_focus": "#c2a068",
        "sel_bg": "#3b3527", "sel_text": "#ece5d3",
        "row_hover": "#252219", "menu_bg": "#252218", "menu_sel_bg": "#393325",
        "menu_sel_fg": "#ece5d3", "tip_bg": "#25221a", "splitter": "#2d2a22",
        "progress_bg": "#1f1d17",
        "green": "#7fac86", "red": "#d68080", "gold": "#d3b074",
        "blue": "#7ea6c6", "warn": "#d3b074",
        "badge_ok_bg": "#253026", "badge_ok_fg": "#8dc194",
        "badge_dead_bg": "#332125", "badge_dead_fg": "#dd93a0",
        "badge_travel_bg": "#332c1d", "badge_travel_fg": "#d8b87f",
        "badge_n_bg": "#252218", "badge_n_fg": "#8f897b",
        "title": "#d8b87f", "subtitle": "#7c7568",
        "scroll": "#393325", "scroll_hover": "#554c37",
        "primary1": "#d2b177", "primary2": "#b58f5a", "primary_fg": "#241d10",
        "primary_border": "#a4844e", "primary_h1": "#dfc48f", "primary_h2": "#c3a066",
        "danger1": "#332125", "danger_fg": "#dd93a0", "danger_border": "#6a3e46",
        "danger_h1": "#3d282e",
        "ok1": "#223026", "ok_fg": "#8dc194", "ok_border": "#3d5947", "ok_h1": "#29392e",
        "ghost_fg": "#8f897b",
        "tab_sel_bg": "#282620", "tab_sel_fg": "#d8b87f", "tab_fg": "#857e71",
    },
}

THEMES = ["sakura", "mint", "night", "graphite"]
THEME_LABELS = [
    ("sakura", "🌸 樱粉软萌（浅色）"),
    ("mint", "🌿 薄荷奶油（浅色）"),
    ("night", "🌙 二次元夜（深色）"),
    ("graphite", "🌒 静谧石墨（深色·低亮护眼）"),
]
DEFAULT_THEME = "sakura"


def _top_off():
    """补齐各套配色缺失的色槽（取 sakura 兜底），避免手写表笔误把界面搞崩。"""
    keys = set()
    for p in _PALETTES.values():
        keys |= set(p.keys())
    for p in _PALETTES.values():
        for k in keys:
            p.setdefault(k, _PALETTES[DEFAULT_THEME].get(k, "#000000"))


_top_off()

# ================= 历史硬编码色 → 语义色槽（规范字面量） =================
# 界面代码里散落的历史色值；T() 依此把它们换算成「当前主题」的对应色。
SRC_ROLE = {
    # 次要 / 提示文字
    "#8a93a3": "text_dim2", "#5b6470": "text_faint",
    "#7d8596": "text_dim", "#7d8aa0": "text_dim", "#8791a2": "text_dim",
    "#6a7280": "text_dim", "#7d8b99": "text_dim",
    # 正文 / 强调文字
    "#b9c0cc": "text_soft", "#d5d8de": "text_soft", "#d7dce4": "text_soft",
    "#e8e4da": "text", "#e8e4d8": "text",
    # 强调（旧金色系 → 新主题强调色）
    "#d4a44c": "accent", "#e8c87a": "accent_text", "#e3c87f": "accent_text",
    "#f0c674": "accent_text", "#b08d4a": "accent_deep", "#211c10": "accent_soft",
    "#f0d98c": "accent_text", "#a8842c": "accent", "#4a3a16": "accent_soft",
    "#8f7fc9": "accent_text", "#2b2415": "accent_soft", "#463a1d": "accent_border",
    "#14324f": "sel_bg", "#2f6fae": "blue", "#8ec9f5": "accent_text",
    "#d4af5f": "accent_text", "#e8c88a": "accent_text", "#e0b25a": "accent_text",
    # 语义色
    "#c9a832": "warn", "#c96f6f": "red", "#e06c5a": "red", "#c47070": "red",
    "#7dae7d": "green", "#5f8f6a": "green", "#6a9d7f": "green",
    "#5f8db5": "blue", "#8fc1d9": "blue", "#7fb3d9": "blue",
    # 面板 / 边框 / 输入
    "#1a1d23": "input_bg", "#2a2e35": "input_border", "#262e3a": "border",
    "#1a222e": "card1", "#29384f": "border_active", "#171a26": "card2",
    "#2d2a45": "border_active", "#b9a8d8": "text_soft", "#2c3846": "sel_bg",
    "#2a3341": "card2", "#202b3a": "card1", "#d8dde5": "text",
}

# 反查表：任意主题色值 / 任意规范字面量 → 语义色槽（保证 T() 可反复施加、跨主题幂等）
_VALUE_ROLE = {}
for _p in _PALETTES.values():
    for _r, _v in _p.items():
        if isinstance(_v, str) and _v.startswith("#"):
            _VALUE_ROLE.setdefault(_v.lower(), _r)
for _k, _r in SRC_ROLE.items():
    _VALUE_ROLE.setdefault(_k.lower(), _r)

_SRC_RE = _re.compile(
    "|".join(_re.escape(k) for k in sorted(_VALUE_ROLE, key=len, reverse=True)),
    _re.IGNORECASE)

# ============================ 当前主题状态 ============================
_ACTIVE = {"name": DEFAULT_THEME}


def theme_names():
    return list(THEMES)


def theme_label(name):
    for k, lab in THEME_LABELS:
        if k == name:
            return lab
    return name


def index_of(name):
    """主题在 THEMES 里的下标（下拉框回填用）。"""
    try:
        return THEMES.index(name)
    except ValueError:
        return 0


def get_theme():
    return _ACTIVE["name"]


def set_theme(name):
    """切换当前主题（只改状态；真正刷新界面由 apply_theme 负责）。"""
    if name in _PALETTES:
        _ACTIVE["name"] = name
    return _ACTIVE["name"]


def palette(name=None):
    return _PALETTES[name or _ACTIVE["name"]]


def C(role, theme=None):
    """取当前主题的语义色。role 也接受规范字面量（如 C("#8a93a3")）。"""
    if role and role.startswith("#"):
        role = _VALUE_ROLE.get(role.lower(), "text")
    p = _PALETTES[theme or _ACTIVE["name"]]
    return p.get(role, p.get("text", "#000000"))


def T(s):
    """把字符串里的历史硬编码色换算成当前主题色（对已换算过的串幂等）。"""
    if not isinstance(s, str) or "#" not in s:
        return s
    p = _PALETTES[_ACTIVE["name"]]
    return _SRC_RE.sub(
        lambda m: p.get(_VALUE_ROLE.get(m.group(0).lower(), "text"), m.group(0)), s)


def q(hexcolor):
    """单色换算（给 QColor / QBrush 用）。"""
    return T(hexcolor) if isinstance(hexcolor, str) else hexcolor


# ============================ QSS 模板 ============================
FONT_FAMILY = '"Microsoft YaHei", "PingFang SC", "Segoe UI", sans-serif'

_QSS_TEMPLATE = """
* { font-family: %(font)s; outline: none; }

/* ---------- 窗口底：柔和渐变 ---------- */
QMainWindow, QDialog {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 %(bg1)s, stop:0.5 %(bg2)s, stop:1 %(bg3)s);
}
QWidget { color: %(text)s; font-size: 13px; }

/* ---------- 面板与分组：大圆角 + 顶部柔光 ---------- */
QFrame#panel, QGroupBox {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 %(panel1)s, stop:1 %(panel2)s);
    border: 1px solid %(border)s;
    border-top-color: %(panel_top)s;
    border-radius: 18px;
}
QGroupBox {
    margin-top: 16px; padding: 15px 12px 12px 12px;
    font-weight: 600; color: %(text)s; font-size: 14px;
}
QGroupBox::title {
    subcontrol-origin: margin; left: 14px; padding: 2px 9px;
    color: %(accent_deep)s; font-weight: 700;
    background: %(accent_soft)s; border-radius: 9px;
}
QFrame#card, QFrame#charCard {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 %(card1)s, stop:1 %(card2)s);
    border: 1px solid %(border)s;
    border-top-color: %(card_top)s;
    border-radius: 18px;
}
QFrame#charCard:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 %(cardh1)s, stop:1 %(cardh2)s);
    border-color: %(cardh_border)s;
}

/* ---------- 按钮：圆角胶囊 + 渐变 ---------- */
QPushButton {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 %(btn1)s, stop:1 %(btn2)s);
    color: %(text)s;
    border: 1px solid %(btn_border)s; border-radius: 12px;
    padding: 7px 16px; font-weight: 600;
}
QPushButton:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 %(btnh1)s, stop:1 %(btnh2)s);
    border-color: %(btnh_border)s;
}
QPushButton:pressed { background: %(btn_press)s; }
QPushButton:disabled { color: %(btn_dis_fg)s; border-color: %(border)s; background: %(btn_dis_bg)s; }
QPushButton#primary {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 %(primary1)s, stop:1 %(primary2)s);
    color: %(primary_fg)s; border: 1px solid %(primary_border)s; font-weight: 700;
}
QPushButton#primary:hover {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop:0 %(primary_h1)s, stop:1 %(primary_h2)s);
}
QPushButton#danger { background: %(danger1)s; color: %(danger_fg)s; border-color: %(danger_border)s; }
QPushButton#danger:hover { background: %(danger_h1)s; }
QPushButton#ghost { background: transparent; border: 1px solid transparent; color: %(ghost_fg)s; }
QPushButton#ghost:hover { color: %(accent_deep)s; border-color: %(border)s; background: %(accent_soft)s; }
QPushButton#accent { background: %(ok1)s; color: %(ok_fg)s; border-color: %(ok_border)s; }
QPushButton#accent:hover { background: %(ok_h1)s; }
/* 角色页分类合集行（文件夹式） */
QPushButton#catFolder {
    background: %(card2)s; border: 1px solid %(border)s; border-radius: 14px;
    text-align: left; padding: 4px 8px;
}
QPushButton#catFolder:hover { background: %(cardh1)s; border-color: %(cardh_border)s; }

/* ---------- 左侧导航 ---------- */
QFrame#nav {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 %(nav1)s, stop:1 %(nav2)s);
    border-right: 1px solid %(border)s;
}
QPushButton#navBtn {
    text-align: left; padding: 11px 14px; border: none; border-radius: 14px;
    background: transparent; color: %(text_dim)s; font-size: 14px; font-weight: 600;
}
QPushButton#navBtn:hover { background: %(cardh1)s; color: %(text)s; }
QPushButton#navBtn:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 %(accent_soft)s, stop:1 %(panel1)s);
    color: %(accent_deep)s;
    border-left: 4px solid %(accent)s;
}

/* ---------- 输入 ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QTextBrowser, QComboBox, QSpinBox, QDoubleSpinBox {
    background: %(input_bg)s; color: %(text)s;
    border: 1px solid %(input_border)s; border-radius: 12px;
    padding: 7px 10px;
    selection-background-color: %(sel_bg)s;
    selection-color: %(sel_text)s;
}
QLineEdit, QPlainTextEdit, QTextEdit { placeholder-text-color: %(placeholder)s; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus,
QSpinBox:focus, QDoubleSpinBox:focus { border-color: %(input_focus)s; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView {
    background: %(menu_bg)s; border: 1px solid %(border_active)s;
    border-radius: 12px; padding: 4px;
    selection-background-color: %(menu_sel_bg)s; selection-color: %(menu_sel_fg)s;
}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    background: %(card2)s; border: none; width: 18px; border-radius: 0 8px 8px 0;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background: %(accent_soft)s;
}

/* ---------- 列表 / 表格 ---------- */
QListWidget, QTableWidget, QTreeWidget {
    background: %(input_bg)s; border: 1px solid %(input_border)s;
    border-radius: 14px; padding: 5px;
    alternate-background-color: %(card2)s;
}
QListWidget::item { padding: 8px 10px; border-radius: 10px; }
QListWidget::item:hover { background: %(row_hover)s; }
QListWidget::item:selected { background: %(sel_bg)s; color: %(sel_text)s; }
QTreeWidget::item { padding: 5px 8px; border-radius: 8px; }
QTreeWidget::item:hover { background: %(row_hover)s; }
QTreeWidget::item:selected { background: %(sel_bg)s; color: %(sel_text)s; }
QTableWidget { gridline-color: %(border)s; }
QTableWidget::item { padding: 4px 8px; }
QTableWidget::item:hover { background: %(row_hover)s; }
QTableWidget::item:selected { background: %(sel_bg)s; color: %(sel_text)s; }
QHeaderView::section {
    background: %(card2)s; color: %(text_dim)s; border: none;
    border-bottom: 1px solid %(border)s; padding: 7px 8px; font-weight: 700;
}
QHeaderView::section:hover { color: %(accent_deep)s; }

/* ---------- 滚动条 ---------- */
QScrollBar:vertical { background: transparent; width: 11px; margin: 2px; }
QScrollBar::handle:vertical { background: %(scroll)s; border-radius: 5px; min-height: 32px; }
QScrollBar::handle:vertical:hover { background: %(scroll_hover)s; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 11px; margin: 2px; }
QScrollBar::handle:horizontal { background: %(scroll)s; border-radius: 5px; min-width: 32px; }
QScrollBar::handle:horizontal:hover { background: %(scroll_hover)s; }

/* ---------- 菜单 / 勾选 ---------- */
QMenu {
    background: %(menu_bg)s; border: 1px solid %(border_active)s;
    border-radius: 14px; padding: 6px;
}
QMenu::item { padding: 7px 24px; border-radius: 10px; }
QMenu::item:selected { background: %(menu_sel_bg)s; color: %(menu_sel_fg)s; }
QMenu::separator { height: 1px; background: %(border)s; margin: 5px 10px; }
QCheckBox { spacing: 6px; }
QCheckBox:checked { color: %(accent_deep)s; font-weight: bold; }
QCheckBox::indicator {
    width: 17px; height: 17px; border: 1px solid %(border_active)s;
    border-radius: 6px; background: %(input_bg)s;
}
QCheckBox::indicator:hover { border-color: %(accent)s; }
QCheckBox::indicator:checked {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 %(accent)s, stop:1 %(accent_deep)s);
    border-color: %(accent_deep)s;
}
QRadioButton { spacing: 6px; }
QRadioButton:checked { color: %(accent_deep)s; font-weight: bold; }
QRadioButton::indicator {
    width: 16px; height: 16px; border: 1px solid %(border_active)s;
    border-radius: 9px; background: %(input_bg)s;
}
QRadioButton::indicator:hover { border-color: %(accent)s; }
QRadioButton::indicator:checked { background: %(accent)s; border-color: %(accent_deep)s; }

/* ---------- 文字 / 徽章 ---------- */
QLabel#title { color: %(title)s; font-size: 21px; font-weight: 800; letter-spacing: 5px; }
QLabel#subtitle { color: %(subtitle)s; font-size: 11px; letter-spacing: 2px; }
QLabel#projName {
    color: %(text)s; font-size: 13px; font-weight: 600;
    background: %(card1)s; border: 1px solid %(border)s; border-radius: 14px; padding: 7px 12px;
}
QLabel#statusBusy { color: %(accent_deep)s; font-weight: 700; }
QLabel#statusIdle { color: %(green)s; font-weight: 600; }
QLabel#zoomLabel, QLabel#verLabel { color: %(text_faint)s; font-size: 11px; padding: 2px 0; }
QLabel#zoomLabel:hover, QLabel#verLabel:hover { color: %(accent_deep)s; }
QLabel.badge { border-radius: 12px; padding: 2px 10px; font-size: 11px; font-weight: 600; }
QLabel#badgeActive { background: %(badge_ok_bg)s; color: %(badge_ok_fg)s; }
QLabel#badgeDead { background: %(badge_dead_bg)s; color: %(badge_dead_fg)s; }
QLabel#badgeTravel { background: %(badge_travel_bg)s; color: %(badge_travel_fg)s; }
QToolTip {
    background: %(tip_bg)s; color: %(text)s;
    border: 1px solid %(border_active)s; border-radius: 10px; padding: 6px 9px;
}
QSplitter::handle { background: %(splitter)s; width: 3px; }

/* ---------- 标签页 / 进度条 ---------- */
QTabWidget::pane {
    border: 1px solid %(border)s; border-radius: 14px; background: %(input_bg)s;
}
QTabBar::tab {
    background: transparent; color: %(tab_fg)s; padding: 8px 18px; margin-right: 3px;
    border-top-left-radius: 12px; border-top-right-radius: 12px; font-weight: 600;
}
QTabBar::tab:hover { color: %(accent_deep)s; background: %(accent_soft)s; }
QTabBar::tab:selected {
    background: %(tab_sel_bg)s; color: %(tab_sel_fg)s;
    border: 1px solid %(border)s; border-bottom: none;
}
QProgressBar {
    background: %(progress_bg)s; border: 1px solid %(border)s; border-radius: 8px;
    height: 16px; text-align: center; color: %(text)s; font-weight: 600;
}
QProgressBar::chunk {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 %(accent)s, stop:1 %(accent_deep)s);
    border-radius: 7px;
}
QScrollArea { background: transparent; border: none; }
QScrollArea > QWidget > QWidget { background: transparent; }
"""


def _qss(theme=None):
    d = dict(_PALETTES[theme or _ACTIVE["name"]])
    d["font"] = FONT_FAMILY
    return _QSS_TEMPLATE % d


def build_qss(scale=1.0, theme=None):
    """按缩放系数 + 指定主题生成整套 QSS：所有 px 尺寸等比缩放（界面整体缩放）。"""
    s = _qss(theme)
    if abs(scale - 1.0) < 0.001:
        return s

    def _scale_px(m):
        try:
            return "%.0fpx" % (float(m.group(1)) * scale)
        except Exception:
            return m.group(0)

    return _re.sub(r"(\d+(?:\.\d+)?)px", _scale_px, s)


# ============================ 换肤 ============================
def recolor(app):
    """把已存在控件的内联 stylesheet / 只读富文本现场重映射到当前主题。

    - 控件内联 stylesheet：逐个 T() 重写（内联样式优先级高于全局 QSS，必须处理）；
    - 只读富文本（日志/预览/审稿意见等 QTextBrowser、只读 QTextEdit）：
      toHtml → T() → setHtml 往返；**可编辑**文本框不动，避免重置光标/滚动/撤销栈。
    """
    from PySide6.QtWidgets import QTextBrowser, QTextEdit
    try:
        widgets = app.allWidgets()
    except Exception:
        return
    for w in widgets:
        try:
            ss = w.styleSheet()
            if ss and "#" in ss:
                new = T(ss)
                if new != ss:
                    w.setStyleSheet(new)
        except Exception:
            pass
        try:
            if isinstance(w, QTextBrowser) or (isinstance(w, QTextEdit) and w.isReadOnly()):
                doc = w.document()
                html = doc.toHtml()
                if "#" in html:
                    new = T(html)
                    if new != html:
                        w.setHtml(new)
        except Exception:
            pass
    try:
        import tone_highlighter as _th
        _th.retint_all()
    except Exception:
        pass


def apply_theme(app, scale=1.0):
    """应用当前主题：重设全局 QSS + 现场重映射既有控件。"""
    app.setStyleSheet(build_qss(scale))
    recolor(app)


# 兼容旧引用（旧代码 / _smoke 直接 import 这些名字）
QSS_BASE = _qss(DEFAULT_THEME)
QSS = build_qss(1.0)
_D = _PALETTES[DEFAULT_THEME]
BG = _D["bg1"]
PANEL = _D["panel1"]
CARD = _D["card1"]
CARD_HOVER = _D["cardh1"]
BORDER = _D["border"]
BORDER_ACTIVE = _D["border_active"]
TEXT = _D["text"]
TEXT_DIM = _D["text_dim"]
ACCENT = _D["accent"]
ACCENT_DARK = _D["accent_dark"]
ACCENT_HOVER = _D["accent_soft"]
INPUT_BG = _D["input_bg"]
GREEN = _D["green"]
RED = _D["red"]
GOLD = _D["gold"]
BLUE = _D["blue"]


def icon(name, size=16):
    """从 assets/icons 加载 SVG 图标（Bootstrap Icons，MIT；随主题色渲染为单色）。

    Qt 经 QtSvg 插件读取 SVG；文件缺失时返回空 QIcon（UI 不崩）。
    """
    import os as _os
    from PySide6.QtGui import QIcon
    p = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
                      "assets", "icons", name + ".svg")
    return QIcon(p) if _os.path.exists(p) else QIcon()
