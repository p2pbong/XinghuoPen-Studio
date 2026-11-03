# -*- coding: utf-8 -*-
"""角色页：卡片式网格管理 + 编辑对话框（酒馆 Persona 风格角色卡 / 信息库 分栏编辑）。

设计原则（对齐酒馆 SillyTavern 角色卡）：
- 角色卡 = 人设（这个角色是怎么样）：name + description（自然语言大字段）+ 可选高级字段
- 信息库 = 外在信息（影响该角色判断的内容）：当前场景/处境、经历事件、已知信息、隐秘
"""
import re
import threading

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QGridLayout,
                               QGroupBox, QHBoxLayout, QHeaderView,
                               QInputDialog, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton,
                               QScrollArea, QTabWidget, QTableWidget,
                               QTableWidgetItem, QVBoxLayout, QWidget, QFrame)

import llm
import main_ai
import name_gen
import storage
from gui_app import APP, bus, busy_guard, current_project, log_fn, set_running
from models import CharacterCard, InfoLibrary
from gui_theme import T

STATUS_TEXT = {"active": "在世", "dead": "阵亡", "traveling": "游历",
               "archived": "已归档", "discarded": "已废弃"}
STATUS_COLOR = {"active": "#5f8f6a", "dead": "#c96f6f", "traveling": "#c9a832",
                "archived": "#6a7280", "discarded": "#8a6f5c"}
# 状态下拉选项（顺序固定）与「中文 → 内部值」反查（各对话框共用，避免多处手写漏项）
STATUS_OPTIONS = ["在世", "阵亡", "游历", "已归档", "已废弃"]
STATUS_KEY = {v: k for k, v in STATUS_TEXT.items()}


def _spec_desc_fallback(card):
    """酒馆卡 description 回退拼装（v0.99）：老卡/手动卡无 description 时，
    用分离字段拼出综合人设，保证导出的卡到酒馆里能直接玩。"""
    parts = []
    if (card.age or "").strip() or (card.gender or "").strip():
        parts.append("%s%s" % (("年龄%s" % card.age) if (card.age or "").strip() else "",
                               ("·%s" % card.gender) if (card.gender or "").strip() else ""))
    if (card.appearance or "").strip():
        parts.append("外貌：%s" % card.appearance)
    if (card.personality or "").strip():
        parts.append("性格：%s" % card.personality)
    if (card.backstory or "").strip():
        parts.append("背景：%s" % card.backstory)
    for label, key in (("价值观", "values"), ("目标", "goals"), ("弱点", "fears"),
                       ("说话风格", "speech_style"), ("关系", "relationships")):
        v = str(getattr(card, key) or "").strip()
        if v:
            parts.append("%s：%s" % (label, v))
    return "\n".join(parts)


def export_character_json(card, lib):
    """导出为酒馆（SillyTavern）chara_card_v2 格式 JSON dict（信息库→character_book）。

    严格对齐酒馆 spec_v2 顶层（spec/spec_version/data{...}）与 data 字段（含
    creator/extensions/avatar/tags/character_version…），角色分类 category 以一条
    「分类：…」entry 写入 character_book（SillyTavern 视为普通知识条目，星火笔导入时
    解析回 category——保证导出→导入后分类不丢、不必重新分类）。
    """
    entries = []

    def entry(keys, content):
        entries.append({"keys": keys, "content": content, "insertion_order": len(entries),
                        "enabled": True, "extensions": {}})

    if (card.category or "").strip():
        entry(["category"], "分类：%s" % card.category)
    if (lib.scenario or "").strip():
        entry(["scenario"], "当前场景/处境：%s" % lib.scenario)
    for i, e in enumerate(lib.events):
        entry(["event%d" % i], "【事件·第%s章】%s（影响：%s）"
              % (e.get("chapter", "?"), e.get("event", ""), e.get("impact", "无")))
    for i, k in enumerate(lib.knowledge):
        entry(["know%d" % i], "【情报·第%s章】%s" % (k.get("chapter", "?"), k.get("info", "")))
    for i, s in enumerate(lib.secrets):
        entry(["secret%d" % i], "【隐秘】%s" % s)
    if (lib.notes or "").strip():
        entry(["notes"], "备注：%s" % lib.notes)
    desc = (card.description or "").strip() or (card.personality or "").strip() \
        or _spec_desc_fallback(card)
    data = {
        "name": card.name,
        "description": desc,
        "personality": card.personality,
        "scenario": lib.scenario,
        "first_mes": card.first_mes,
        "mes_example": card.mes_example,
        "system_prompt": card.system_prompt,
        "post_history_instructions": card.post_history_instructions,
        "creator_notes": card.creator_notes,
        "tags": list(card.tags),
        "creator": "星火笔",
        "character_version": card.character_version or "main",
        "alternate_greetings": [],
        "extensions": {},
        "avatar": "",
        "character_book": {
            "name": "%s-信息库" % card.name,
            "description": "该角色信息库（外在信息：经历/情报/隐秘）",
            "entries": entries,
        },
    }
    return {"spec": "chara_card_v2", "spec_version": "2.0", "data": data}


def import_character_json(data):
    """从酒馆 chara_card_v2 JSON 解析角色卡 + 信息库（export_character_json 的逆操作）。

    兼容裸卡（无 spec 包装）；信息库 character_book.entries 的 content 前缀解析回结构化字段。
    返回 (card, lib)；缺 name 时抛 ValueError。
    """
    if isinstance(data, dict) and isinstance(data.get("data"), dict):
        d = data["data"]
    elif isinstance(data, dict):
        d = data
    else:
        d = {}
    name = str(d.get("name") or "").strip()
    if not name:
        raise ValueError("缺少角色名 name")
    card = CharacterCard(name, "")
    card.description = str(d.get("description") or "")
    card.personality = str(d.get("personality") or "")
    card.first_mes = str(d.get("first_mes") or "")
    card.mes_example = str(d.get("mes_example") or "")
    card.system_prompt = str(d.get("system_prompt") or "")
    card.post_history_instructions = str(d.get("post_history_instructions") or "")
    card.creator_notes = str(d.get("creator_notes") or "")
    _rt = d.get("tags") or []
    if isinstance(_rt, str):
        _rt = re.split(r"[，,、;；\s]+", _rt)
    card.tags = [str(t).strip() for t in _rt if str(t).strip()]
    card.character_version = str(d.get("character_version") or "")
    lib = InfoLibrary(card.id)
    lib.scenario = str(d.get("scenario") or "")
    book = d.get("character_book") or {}
    for e in book.get("entries") or []:
        if not isinstance(e, dict):
            continue
        content = str(e.get("content") or "").strip()
        if not content:
            continue
        keys = e.get("keys") or []
        k = str(keys[0]) if keys else ""
        if k == "scenario" or content.startswith("当前场景/处境"):
            lib.scenario = content.split("：", 1)[-1].strip()
        elif k == "category" or content.startswith("分类："):
            card.category = content.split("：", 1)[-1].strip()
        elif content.startswith("【事件·"):
            m = re.match(r"【事件·第(\d+)章】(.+?)(?:（影响：(.+?)）)?$", content)
            lib.events.append({
                "chapter": int(m.group(1)) if m and m.group(1) else "?",
                "event": (m.group(2) or content).strip() if m else content,
                "impact": (m.group(3) or "").strip() if m else "",
            })
        elif content.startswith("【情报·"):
            m = re.match(r"【情报·第(\d+)章】(.+)$", content)
            lib.knowledge.append({
                "chapter": int(m.group(1)) if m and m.group(1) else "?",
                "info": (m.group(2) or content).strip() if m else content,
            })
        elif content.startswith("【隐秘】"):
            lib.secrets.append(content.replace("【隐秘】", "").strip())
        elif content.startswith("备注："):
            lib.notes = content.replace("备注：", "").strip()
        elif k.startswith("event"):
            lib.events.append({"chapter": "?", "event": content, "impact": ""})
        elif k.startswith("know"):
            lib.knowledge.append({"chapter": "?", "info": content})
        elif k.startswith("secret"):
            lib.secrets.append(content)
        else:
            lib.notes = ((lib.notes + "\n" + content) if lib.notes else content).strip()
    return card, lib

# 角色卡高级字段（酒馆 Persona 标准字段，默认折叠不打扰）
ADVANCED_FIELDS = [
    ("personality", "性格摘要（可选）", 60),
    ("first_mes", "首次登场台词/动作 first_mes（可选）", 60),
    ("mes_example", "示例对话 mes_example（教模型模仿语气，可选）", 100),
    ("system_prompt", "附加扮演规则 system_prompt（可选）", 60),
]


class CharCard(QFrame):
    """一张角色卡片（点击整卡编辑）。"""

    def __init__(self, page, card, lib=None):
        super().__init__()
        self.page = page
        self.char_id = card.id
        self.setObjectName("charCard")
        self.setFixedHeight(224)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        if not card:
            return

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 10)
        lay.setSpacing(5)

        top = QHBoxLayout()
        name = QLabel(card.name or "无名")
        name.setStyleSheet(T("font-size:16px;font-weight:700;color:#e8e4da;"))
        badge = QLabel(STATUS_TEXT.get(card.status, card.status))
        badge.setStyleSheet(T("border-radius:9px;padding:2px 10px;font-size:11px;font-weight:600;"
                            "background:#211c10;color:%s;") % T(STATUS_COLOR.get(card.status, "#5f8f6a")))
        top.addWidget(name)
        top.addStretch(1)
        top.addWidget(badge)
        lay.addLayout(top)

        meta = []
        if card.role:
            meta.append(card.role)
        if card.age:
            meta.append(card.age + "岁")
        if card.gender:
            meta.append(card.gender)
        m = QLabel(" · ".join(meta) if meta else "（身份未设定）")
        m.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lay.addWidget(m)

        desc_src = (card.description or card.personality or "").strip()
        p = ("%s" % desc_src) if desc_src else "（无描述，点击卡片编辑补充）"
        desc = QLabel(p)
        desc.setWordWrap(True)
        desc.setMaximumHeight(40)
        desc.setStyleSheet(T("color:#b9c0cc;font-size:12px;"))
        lay.addWidget(desc, 1)

        # 分类行：下拉可改分类（可输入自定义分类名，改动即保存并刷新分组）
        cat_row = QHBoxLayout()
        cat_lab = QLabel("分类")
        cat_lab.setStyleSheet(T("color:#7d8596;font-size:11px;"))
        cat_row.addWidget(cat_lab)
        cat_combo = QComboBox()
        cat_combo.setEditable(True)
        cat_combo.setFixedWidth(150)
        cat_combo.setStyleSheet("font-size:11px;")
        for c in getattr(page, "_categories", []) or []:
            cat_combo.addItem(c)
        cur_cat = (card.category or "").strip()
        cat_combo.setCurrentText(cur_cat)
        cat_combo.setToolTip("角色分类（文件夹式分组）：下拉选择或直接输入新分类名，改动即时生效")
        # 下拉选择（索引变化）或编辑框完成输入（回车/失焦）时保存；
        # 不用 currentTextChanged——打字过程中逐字触发会导致每次刷新重建卡片丢焦点
        cat_combo.currentIndexChanged.connect(
            lambda _i: self._set_category(cat_combo.currentText()))
        if cat_combo.lineEdit():
            cat_combo.lineEdit().editingFinished.connect(
                lambda: self._set_category(cat_combo.currentText()))
        cat_row.addWidget(cat_combo)
        cat_row.addStretch(1)
        lay.addLayout(cat_row)

        tags = QHBoxLayout()
        for t in card.traits[:2]:
            tag = QLabel("#" + t)
            tag.setStyleSheet(T("color:#b08d4a;background:#211c10;border-radius:8px;"
                              "padding:1px 8px;font-size:11px;"))
            tags.addWidget(tag)
        tags.addStretch(1)
        lay.addLayout(tags)

        # 信息库角标：事件/已知信息/隐秘 计数
        ev_n = len(lib.events) if lib else 0
        kn_n = len(lib.knowledge) if lib else 0
        sc_n = len(lib.secrets) if lib else 0
        lib_label = QLabel("📖 事件 %d · 情报 %d · 隐秘 %d" % (ev_n, kn_n, sc_n))
        lib_label.setStyleSheet(T("color:#7d8596;font-size:11px;"))
        lay.addWidget(lib_label)

        btns = QHBoxLayout()
        btns.addStretch(1)
        edit_btn = QPushButton("✎ 编辑卡片与信息库")
        edit_btn.setObjectName("primary")
        edit_btn.setFixedHeight(26)
        edit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        edit_btn.clicked.connect(self._edit)
        del_btn = QPushButton("删除")
        del_btn.setObjectName("ghost")
        del_btn.setFixedHeight(26)
        del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        del_btn.clicked.connect(self._delete)
        btns.addWidget(edit_btn)
        btns.addWidget(del_btn)
        lay.addLayout(btns)

        # 让卡片内部文字不拦截鼠标，点击任意位置都能打开编辑（分类下拉除外）
        for w in self.findChildren(QLabel):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def _set_category(self, text):
        """分类下拉改动即保存；分类变化后刷新分组视图。"""
        cat = (text or "").strip()
        store, _ = current_project()
        card, lib = store.load_character(self.char_id)
        if not card or (card.category or "") == cat:
            return
        card.category = cat
        card.version += 1
        store.save_character(card, lib)
        log_fn("info", "角色「%s」已归类：%s" % (card.name, cat or "未分类"))
        self.page.refresh()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self._edit()
        super().mouseReleaseEvent(ev)

    def _edit(self):
        CharEditDialog(self.char_id, self.page).exec()

    def _delete(self):
        store, _ = current_project()
        card, _ = store.load_character(self.char_id)
        name = card.name if card else self.char_id
        ret = QMessageBox.question(self, "删除角色",
                                   "确定删除角色「%s」？其信息库也会一并删除。" % name)
        if ret != QMessageBox.StandardButton.Yes:
            return
        store.delete_character(self.char_id)
        log_fn("info", "已删除角色：%s" % name)
        self.page.refresh()


class CharactersPage(QWidget):
    def __init__(self, app):
        super().__init__()
        self.app = app
        self.cards = []
        self._view = "groups"      # 视图：groups（分类合集列表）/ 某分类名 / search
        self._cards_cache = {}     # cid -> (CharacterCard, InfoLibrary)：refresh 时批量读一次
        self._categories = []      # 全部已用分类名列表

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)

        # 工具栏第一行：搜索 + 新建/AI生成/核心团
        tool = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜索角色…")
        self.search.setFixedWidth(200)
        self.search.textChanged.connect(lambda _: self.refresh())
        new_btn = QPushButton("＋ 新建空白卡")
        new_btn.setObjectName("primary")
        new_btn.clicked.connect(self._new_blank)
        ai_btn = QPushButton("AI 生成角色")
        ai_btn.clicked.connect(self._gen_ai)
        core_btn = QPushButton("一键核心角色团")
        core_btn.clicked.connect(self._gen_core)
        rnd_btn = QPushButton("🎲 随机名字")
        rnd_btn.setToolTip("随机生成中文角色名（本地字库，无网络）")
        rnd_btn.clicked.connect(self._random_name)
        tool.addWidget(QLabel("角色管理"))
        tool.addStretch(1)
        tool.addWidget(self.search)
        tool.addWidget(new_btn)
        tool.addWidget(ai_btn)
        tool.addWidget(core_btn)
        tool.addWidget(rnd_btn)
        lay.addLayout(tool)

        # 工具栏第二行：批量生成/导出/导入/批量管理/刷新/AI自动分类
        tool2 = QHBoxLayout()
        batch_btn = QPushButton("批量生成配角")
        batch_btn.clicked.connect(self._gen_batch)
        export_btn = QPushButton("导出角色卡")
        export_btn.clicked.connect(self._export_all)
        import_btn = QPushButton("导入角色卡")
        import_btn.setToolTip("从酒馆 chara_card_v2 JSON 导入（可多选，支持本软件导出的角色卡或其他工具的卡）")
        import_btn.clicked.connect(self._import_cards)
        batch_mgr_btn = QPushButton("批量管理")
        batch_mgr_btn.setObjectName("primary")
        batch_mgr_btn.setToolTip("批量删除 / 批量改状态（在世/阵亡/游历/已归档/已废弃）")
        batch_mgr_btn.clicked.connect(self._batch_manage)
        refresh_btn = QPushButton("刷新")
        refresh_btn.clicked.connect(self.refresh)
        lib_btn = QPushButton("🗂 角色卡库")
        lib_btn.setObjectName("accent")
        lib_btn.setToolTip("查看全部已归档角色（主AI清理/手动归档的角色都保留在这里，可随时恢复在籍）")
        lib_btn.clicked.connect(lambda: self._open_library())
        discard_btn = QPushButton("♻ 废弃角色库")
        discard_btn.setObjectName("accent")
        discard_btn.setToolTip("查看全部已废弃角色（删除章节/回滚世界后移出当前剧情的角色都保留在这里，"
                              "附废弃原因，可随时恢复在籍）")
        discard_btn.clicked.connect(lambda: self._open_discard())
        classify_btn = QPushButton("AI 自动分类")
        classify_btn.setObjectName("accent")
        classify_btn.setToolTip("让 AI 通读全部角色卡，按剧情定位自动分类（主要角色/配角/NPC/反派…），"
                                "分类后在界面按分组显示，类似文件夹管理")
        classify_btn.clicked.connect(self._classify_ai)
        tool2.addStretch(1)
        tool2.addWidget(batch_btn)
        tool2.addWidget(export_btn)
        tool2.addWidget(import_btn)
        tool2.addWidget(batch_mgr_btn)
        tool2.addWidget(lib_btn)
        tool2.addWidget(discard_btn)
        tool2.addWidget(classify_btn)
        tool2.addWidget(refresh_btn)
        lay.addLayout(tool2)

        hint = QLabel("点击任意卡片即可编辑角色卡 + 信息库（事件/情报/隐秘）。「AI 自动分类」让 AI 按剧情定位把角色分到"
                      "「主要角色/配角/NPC/反派…」各组（也可在卡片下拉或编辑对话框里手动改分类，界面按组显示）。\n"
                      "角色卡不会被直接删除：「🗂 角色卡库」存主AI清理/手动归档的角色，"
                      "「♻ 废弃角色库」存删除章节或回滚世界后移出当前剧情的角色，两处都可恢复在籍。")
        hint.setWordWrap(True)
        hint.setStyleSheet(T("color:#5b6470;"))
        lay.addWidget(hint)

        # 角色生成进度（显示在本页，而不是小说生成页）
        self.gen_status = QLabel("")
        self.gen_status.setWordWrap(True)
        self.gen_status.setStyleSheet(T("color:#d4a44c;font-size:12px;"))
        lay.addWidget(self.gen_status)
        from gui_app import bus
        bus.log.connect(self._on_gen_log)
        bus.charactersChanged.connect(self.refresh)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.grid_host = QWidget()
        # 分组容器：每个分类一组（标题 + 卡片网格），自上而下排列
        self.groups = QVBoxLayout(self.grid_host)
        self.groups.setContentsMargins(2, 2, 2, 2)
        self.groups.setSpacing(16)
        self.groups.addStretch(1)
        self.scroll.setWidget(self.grid_host)
        lay.addWidget(self.scroll, 1)

    def on_show(self):
        self.refresh()

    def refresh(self):
        for c in self.cards:
            c.deleteLater()
        self.cards = []
        while self.groups.count():
            item = self.groups.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        store, project = current_project()
        if not project:
            return
        # 批量读取全部角色卡（一次遍历磁盘），后续渲染全部走内存缓存，不再逐张读盘
        self._cards_cache = {}
        self._categories = []
        for card, lib in store.list_character_cards():
            self._cards_cache[card.id] = (card, lib)
            if (card.category or "").strip() and card.category not in self._categories:
                self._categories.append(card.category)

        kw = self.search.text().strip()
        if kw:
            self._render_search(kw)
        elif self._view == "groups":
            self._render_groups()
        elif self._view == "library":
            self._render_library()
        elif self._view == "discard":
            self._render_discard()
        else:
            self._render_group(self._view)

    # ---------- 视图渲染 ----------
    @staticmethod
    def _cat_key(cat):
        """分类排序：未分类最后；主要/主角 → 配角 → NPC/路人/日常 → 其他，再按名称。"""
        name = cat
        if "主要" in name or "主角" in name:
            return (0, name)
        if "配角" in name:
            return (1, name)
        if "NPC" in name.upper() or "路人" in name or "日常" in name:
            return (2, name)
        return (3, name)

    def _render_groups(self):
        """分类合集视图：每个分类一个可点击的「文件夹」行（不渲染卡片，避免数百张卡卡顿）。

        只统计**在籍**角色（active/dead/traveling）；已归档的在「🗂 角色卡库」、
        已废弃的在「♻ 废弃角色库」查看。
        """
        groups = {}
        for cid, (card, _lib) in self._cards_cache.items():
            if card.status in ("archived", "discarded"):
                continue
            cat = (card.category or "").strip() or "未分类"
            groups.setdefault(cat, []).append(card)
        if not groups:
            empty = QLabel("角色池为空。点上方「AI 生成角色」「一键核心角色团」或「＋ 新建空白卡」创建角色。")
            empty.setStyleSheet(T("color:#8a93a3;"))
            self.groups.addWidget(empty)
            return
        ordered = sorted(groups.keys(), key=self._cat_key)
        for cat in ordered:
            cards = groups[cat]
            names = "、".join(c.name for c in cards[:4])
            if len(cards) > 4:
                names += " 等…"
            row = QPushButton()
            row.setObjectName("catFolder")
            row.setCursor(Qt.CursorShape.PointingHandCursor)
            row.setMinimumHeight(56)
            row.setToolTip("点击查看该分类下全部 %d 个角色" % len(cards))
            rl = QHBoxLayout(row)
            rl.setContentsMargins(16, 8, 16, 8)
            folder = QLabel("📁")
            folder.setStyleSheet("font-size:17px;")
            t = QLabel(cat)
            t.setStyleSheet(T("font-size:15px;font-weight:700;color:#e8e4da;"))
            cnt = QLabel("%d 个角色" % len(cards))
            cnt.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
            preview = QLabel(names)
            preview.setStyleSheet(T("color:#5b6470;font-size:12px;"))
            arrow = QLabel("›")
            arrow.setStyleSheet(T("color:#8a93a3;font-size:20px;"))
            rl.addWidget(folder)
            rl.addWidget(t)
            rl.addWidget(cnt)
            rl.addSpacing(14)
            rl.addWidget(preview, 1)
            rl.addWidget(arrow)
            row.clicked.connect(lambda _=False, c=cat: self._open_group(c))
            self.groups.addWidget(row)

    def _render_group(self, cat):
        """分类内视图：返回按钮 + 该分类下全部在籍角色卡片（网格；已归档/已废弃进各自的库）。"""
        self._render_back_bar()
        cards = [card for cid, (card, _l) in self._cards_cache.items()
                 if ((card.category or "").strip() or "未分类") == cat
                 and card.status not in ("archived", "discarded")]
        if not cards:
            empty = QLabel("该分类下暂无角色。可在其他分类的卡片上下拉改分类，或点「AI 自动分类」重新归类。")
            empty.setStyleSheet(T("color:#8a93a3;"))
            self.groups.addWidget(empty)
            return
        head = QLabel("📁 %s　·　%d 个角色" % (cat, len(cards)))
        head.setStyleSheet(T("font-size:14px;font-weight:700;color:#b9c0cc;"))
        self.groups.addWidget(head)
        self._render_cards_grid(cards)

    def _render_search(self, kw):
        """搜索结果视图：直接网格显示匹配角色（带返回）。"""
        self._render_back_bar()
        cards = [card for cid, (card, _l) in self._cards_cache.items()
                 if kw in (card.name or "")]
        head = QLabel("搜索「%s」：找到 %d 个角色" % (kw, len(cards)))
        head.setStyleSheet(T("font-size:14px;font-weight:700;color:#b9c0cc;"))
        self.groups.addWidget(head)
        if cards:
            self._render_cards_grid(cards)

    def _render_back_bar(self):
        back = QPushButton("← 返回分类合集")
        back.setObjectName("ghost")
        back.setCursor(Qt.CursorShape.PointingHandCursor)
        back.clicked.connect(lambda: self._back_to_groups())
        self.groups.addWidget(back)

    def _render_cards_grid(self, cards):
        cols = 3
        grid = QGridLayout()
        grid.setContentsMargins(4, 2, 4, 2)
        grid.setSpacing(14)
        r = c = 0
        for card in cards:
            card_w = CharCard(self, card, self._cards_cache[card.id][1])
            self.cards.append(card_w)
            grid.addWidget(card_w, r, c)
            c += 1
            if c >= cols:
                c = 0
                r += 1
        grid.setRowStretch(r + 1, 1)
        gw = QWidget()
        gw.setLayout(grid)
        self.groups.addWidget(gw)

    def _open_group(self, cat):
        self._view = cat
        self.refresh()

    # ---------- 角色卡库（v0.98：全部已归档角色保留处，可恢复在籍）；
    #           废弃角色库（v1.79：删除章节/回滚世界移出的角色保留处，附原因） ----------
    def _open_library(self):
        self._view = "library"
        self.search.clear()
        self.refresh()

    def _open_discard(self):
        self._view = "discard"
        self.search.clear()
        self.refresh()

    def _render_library(self):
        """角色卡库视图：已归档 + 已废弃两类都不删除，分区列出，可一键恢复。"""
        self._render_back_bar()
        archived = [card for cid, (card, _l) in self._cards_cache.items()
                    if card.status == "archived"]
        discarded = [card for cid, (card, _l) in self._cards_cache.items()
                     if card.status == "discarded"]
        archived.sort(key=lambda c: (c.updated_chapter or 0), reverse=True)
        discarded.sort(key=lambda c: (c.discarded_chapter or 0, c.name or ""), reverse=True)
        active_n = sum(1 for cid, (c, _l) in self._cards_cache.items()
                       if c.status not in ("archived", "discarded"))
        head = QLabel("🗂 角色卡库　·　已归档 %d 个 · 已废弃 %d 个 · 在籍 %d 个"
                      % (len(archived), len(discarded), active_n))
        head.setStyleSheet(T("font-size:14px;font-weight:700;color:#b9c0cc;"))
        self.groups.addWidget(head)
        tip = QLabel("归档与废弃的角色**都不删除**：主AI清理/手动归档的进「已归档」，"
                     "删除章节或回滚世界后移出当前剧情的进「已废弃」（附原因）；"
                     "需要时点「恢复在籍」即可重新出场。")
        tip.setWordWrap(True)
        tip.setStyleSheet(T("color:#6a7280;font-size:12px;"))
        self.groups.addWidget(tip)

        self._render_shelf("📁 已归档（主AI清理 / 手动归档）", archived,
                           "卡库为空——主AI归档或你手动「已归档」的角色会出现在这里。")
        self._render_shelf("♻ 已废弃（删除章节 / 回滚世界后移出剧情）", discarded,
                           "暂无废弃角色——删除章节或从某章重写时，"
                           "不再属于当前剧情的角色会移到这里（不再直接删除）。")

    def _render_discard(self):
        """废弃角色库视图：只列已废弃角色及其废弃原因/章节。"""
        self._render_back_bar()
        discarded = [card for cid, (card, _l) in self._cards_cache.items()
                     if card.status == "discarded"]
        discarded.sort(key=lambda c: (c.discarded_chapter or 0, c.name or ""), reverse=True)
        head = QLabel("♻ 废弃角色库　·　已废弃 %d 个" % len(discarded))
        head.setStyleSheet(T("font-size:14px;font-weight:700;color:#b9c0cc;"))
        self.groups.addWidget(head)
        tip = QLabel("这些角色因**删除章节或回滚世界**而移出当前剧情（之前是直接删除，v1.79 起改为保留在此），"
                     "档案与信息库完整保留、附上废弃原因；想让它重新出场点「恢复在籍」即可。")
        tip.setWordWrap(True)
        tip.setStyleSheet(T("color:#6a7280;font-size:12px;"))
        self.groups.addWidget(tip)
        self._render_shelf(None, discarded,
                           "废弃角色库为空——删除章节或重写某章后，"
                           "移出当前剧情的角色会出现在这里。")

    def _render_shelf(self, title, cards, empty_text):
        """渲染一整组卡库条目（title 为空则不画小标题，用于独立视图）。"""
        if title:
            sub = QLabel(title)
            sub.setStyleSheet(T("font-size:13px;font-weight:700;color:#9aa3b0;margin-top:6px;"))
            self.groups.addWidget(sub)
        if not cards:
            empty = QLabel(empty_text)
            empty.setWordWrap(True)
            empty.setStyleSheet(T("color:#8a93a3;"))
            self.groups.addWidget(empty)
            return
        for card in cards:
            self.groups.addWidget(self._library_row(card))

    def _library_row(self, card):
        """卡库单行：角色名/定位/简介 + 废弃信息 + 「恢复在籍」按钮。"""
        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(10, 6, 10, 6)
        rl.setSpacing(10)
        name = QLabel("♻ %s" % card.name if card.status == "discarded"
                      else "📁 %s" % card.name)
        name.setStyleSheet(T("font-size:14px;font-weight:700;color:#e8e4da;"))
        desc = (card.description or card.personality or "").strip()
        brief = QLabel(("%s（%s）" % (desc[:40], card.role or "身份未知"))
                       if desc else ("（%s 无描述）" % (card.role or "身份未知")))
        brief.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        brief.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rl.addWidget(name)
        if card.status == "discarded":
            why = (card.discarded_reason or "").strip() or "（无原因记录）"
            if card.discarded_chapter:
                why = "废弃于第 %d 章 · %s" % (card.discarded_chapter, why)
            reason = QLabel(why)
            reason.setWordWrap(True)
            reason.setStyleSheet(T("color:#a08a72;font-size:12px;"))
            reason.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            rl.addWidget(reason, 1)
        else:
            rl.addWidget(brief, 1)
        restore = QPushButton("恢复在籍")
        restore.setObjectName("primary")
        restore.setCursor(Qt.CursorShape.PointingHandCursor)
        restore.clicked.connect(lambda _=False, cid=card.id: self._restore_from_library(cid))
        rl.addWidget(restore)
        if card.status == "discarded":
            purge = QPushButton("彻底删除")
            purge.setObjectName("danger")
            purge.setCursor(Qt.CursorShape.PointingHandCursor)
            purge.setToolTip("从废弃角色库移除该档案（不可恢复；一般不必——留在这里不影响剧情）")
            purge.clicked.connect(lambda _=False, cid=card.id, nm=card.name:
                                  self._purge_discarded(cid, nm))
            rl.addWidget(purge)
        return row

    def _restore_from_library(self, cid):
        store, _p = current_project()
        card, lib = store.load_character(cid)
        if not card:
            return
        was = card.status
        card.status = "active"
        card.version += 1
        store.save_character(card, lib)   # save_character 会清空废弃标记
        log_fn("info", "角色「%s」已从%s恢复在籍。" % (
            card.name, "废弃角色库" if was == "discarded" else "角色卡库"))
        self.refresh()

    def _purge_discarded(self, cid, name):
        """从废弃角色库彻底删除（用户明确操作，二次确认）。"""
        ret = QMessageBox.question(
            self, "彻底删除角色",
            "确定把「%s」从废弃角色库彻底删除？\n档案与信息库将一并删除，不可恢复。"
            "（留在库里不影响剧情，一般不需要删除。）" % name)
        if ret != QMessageBox.StandardButton.Yes:
            return
        store, _p = current_project()
        store.delete_character(cid)
        log_fn("info", "已从废弃角色库彻底删除角色：%s" % name)
        self.refresh()

    def _back_to_groups(self):
        self._view = "groups"
        self.search.clear()
        self.refresh()

    def _classify_ai(self):
        """AI 自动分类：让 AI 通读全部角色卡，按剧情定位归类（主要角色/配角/NPC/反派…），写回 category。"""
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        if not busy_guard(self):
            return
        chars = store.list_characters()
        if not chars:
            QMessageBox.warning(self, "提示", "角色池为空，无角色可分类。")
            return
        log_fn("info", "AI 正在为 %d 个角色分类…" % len(chars))
        set_running(True)

        def work():
            try:
                roles = main_ai.classify_characters(project, store)
                if not roles:
                    log_fn("error", "AI 没有解析出分类结果，请重试（可先在项目页确认故事设定已填写）。")
                    return
                ok_n = 0
                for cid, name, _ in store.list_characters():
                    cat = roles.get(name)
                    if not cat:
                        continue
                    card, lib = store.load_character(cid)
                    if card and card.category != cat:
                        card.category = cat
                        card.version += 1
                        store.save_character(card, lib)
                    ok_n += 1
                cats = sorted(set(roles.values()))
                log_fn("info", "AI 分类完成：%d 个角色已归类，共 %d 组（%s）。"
                       % (ok_n, len(cats), " / ".join(cats)))
            except llm.LLMError as e:
                log_fn("error", "AI 分类失败：%s" % e)
            except Exception as e:
                log_fn("error", "AI 分类失败：%s" % e)
            finally:
                bus.charactersChanged.emit()
                set_running(False)

        threading.Thread(target=work, daemon=True).start()

    def _new_blank(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        # v0.47：新建弹窗默认预填一个随机名（不满意可直接改）
        name, ok = QInputDialog.getText(self, "新建角色卡", "角色姓名：",
                                        text=name_gen.generate_name())
        if not ok or not name.strip():
            return
        card = CharacterCard(name.strip())
        store.save_character(card, InfoLibrary(card.id))
        log_fn("info", "已创建角色卡：%s（点击卡片补充设定与信息库）" % card.name)
        self.refresh()

    def _random_name(self):
        """🎲 随机名字：弹候选窗，选一个立刻建卡（v0.47，本地字库无网络）。"""
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        dlg = ChooseNameDialog(self)
        if not dlg.exec():
            return
        name = (dlg.selectedText or "").strip()
        if not name:
            return
        card = CharacterCard(name)
        store.save_character(card, InfoLibrary(card.id))
        self.refresh()
        log_fn("info", "已用随机名字创建角色卡：%s（点击卡片补全设定与信息）" % name)

    def _gen_ai(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        if not busy_guard(self):
            return
        text, ok = QInputDialog.getMultiLineText(
            self, "AI 生成角色",
            "简单描述想要的角色（例：铁砧城酒吧老板娘，三十出头，风尘气但眼神锐利，与城主府有旧怨…）：")
        if not ok or not text.strip():
            return
        self._spawn_ai_gen([text.strip()])

    def _gen_core(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        if not busy_guard(self):
            return
        descriptions = [
            "故事核心主角（第一视角重点刻画，性格要有缺陷与成长空间，写清综合描述与说话风格）",
            "与主角关系最紧密的第一配角（分担冲突与对话，性格与主角互补或对立）",
            "一名推动本卷主线的关键配角（掌握关键线索或权力，埋有秘密）",
        ]
        log_fn("info", "开始一键生成核心角色团（主角 + 第一配角 + 关键配角）…")
        self._spawn_ai_gen(descriptions)

    def _gen_batch(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        if not busy_guard(self):
            return
        dlg = BatchGenDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        desc = dlg.desc.toPlainText().strip()
        if not desc:
            QMessageBox.warning(self, "提示", "请先描述想要的角色。")
            return
        log_fn("info", "开始按需求批量生成角色：%s" % desc[:40])
        set_running(True)

        def work():
            try:
                cards_data = main_ai.generate_batch_roles(desc, project, store)
                if not cards_data:
                    log_fn("error", "AI 没有解析出角色，请换一种描述方式重试。")
                    return
                ok_n = fail_n = 0
                for i, data in enumerate(cards_data):
                    log_fn("info", "AI 正在生成角色 %d/%d：%s"
                           % (i + 1, len(cards_data), data.get("name") or "?"))
                    try:
                        card = main_ai.character_from_data(data, created_by="ai")
                        lib = InfoLibrary(card.id)
                        if data.get("scenario"):
                            lib.scenario = str(data.get("scenario", "")).strip()
                        store.save_character(card, lib)
                        ok_n += 1
                        log_fn("info", "已生成角色卡：%s（%s）" % (card.name, card.role))
                    except Exception as e:
                        fail_n += 1
                        log_fn("error", "角色「%s」建档失败：%s"
                               % (data.get("name") or "?", e))
                log_fn("info", "批量生成结束：成功 %d 个，失败 %d 个。" % (ok_n, fail_n))
            except llm.LLMError as e:
                log_fn("error", "批量生成失败：%s" % e)
            except Exception as e:
                log_fn("error", "批量生成失败：%s" % e)
            finally:
                bus.charactersChanged.emit()
                set_running(False)

        threading.Thread(target=work, daemon=True).start()

    def _export_all(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        chars = store.list_characters()
        if not chars:
            QMessageBox.warning(self, "提示", "角色池为空，无角色可导出。")
            return
        from PySide6.QtWidgets import QFileDialog
        import json
        import export_utils
        folder = QFileDialog.getExistingDirectory(
            self, "选择导出目录", export_utils.default_cards_dir(project.title))
        if not folder:
            return
        written = 0
        for cid, name, _ in chars:
            card, lib = store.load_character(cid)
            if not card:
                continue
            data = export_character_json(card, lib)
            fname = "".join(c for c in (card.name or cid) if c not in '\\/:*?"<>|') or cid
            with open(__import__("os").path.join(folder, fname + ".json"),
                      "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            written += 1
        log_fn("info", "已导出 %d 张角色卡（酒馆 chara_card_v2 格式）到：%s" % (written, folder))

    def _import_cards(self):
        """从酒馆 chara_card_v2 JSON 导入角色卡（可多选文件），导入后刷新。"""
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        from PySide6.QtWidgets import QFileDialog
        import json
        import os
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择角色卡 JSON（可多选）", "", "角色卡 (*.json)")
        if not paths:
            return
        ok_n, fail_n, fails = 0, 0, []
        for p in paths:
            try:
                with open(p, encoding="utf-8") as f:
                    data = json.load(f)
                card, lib = import_character_json(data)
                store.save_character(card, lib)
                ok_n += 1
            except Exception as e:
                fail_n += 1
                fails.append("%s（%s）" % (os.path.basename(p), e))
        if ok_n:
            bus.charactersChanged.emit()
            self.refresh()
            log_fn("info", "已导入 %d 张角色卡，失败 %d 张。" % (ok_n, fail_n))
        msg = "导入成功 %d 张角色卡。" % ok_n
        if fail_n:
            msg += "\n失败 %d 张：\n%s" % (fail_n, "\n".join(fails[:5]))
        QMessageBox.information(self, "导入角色卡", msg)

    def _batch_manage(self):
        store, project = current_project()
        if not project:
            QMessageBox.warning(self, "提示", "请先在「项目」页载入项目。")
            return
        dlg = BatchManageDialog(self)
        dlg.exec()

    def _on_gen_log(self, kind, msg):
        keys = ("AI 正在生成角色", "已生成角色卡", "AI 生成角色失败",
                "开始一键生成", "批量生成", "角色生成结束", "建档失败",
                "分类", "AI 正在为")
        if not any(k in msg for k in keys):
            return
        self._gen_msgs = getattr(self, "_gen_msgs", []) + [(kind, msg)]
        self._gen_msgs = self._gen_msgs[-4:]
        color = {"info": T("#d4a44c"), "warn": T("#c9a832"), "error": T("#c96f6f")}.get(kind, T("#d4a44c"))
        html = "<br>".join(
            "<span style='color:%s;'>%s</span>" % (color, m.replace("<", "&lt;"))
            for k, m in self._gen_msgs)
        self.gen_status.setText(html)

    def _spawn_ai_gen(self, descriptions, batch=False):
        store, project = current_project()
        set_running(True)

        def work():
            ok_n = fail_n = 0
            total = len(descriptions)
            try:
                for i, desc in enumerate(descriptions):
                    log_fn("info", "AI 正在生成角色 %d/%d：%s" % (i + 1, total, desc[:30]))
                    try:
                        data = main_ai.generate_character_ai(desc, project, store)
                        # v0.98 防重复：同名角色已存在则复用旧卡（补齐空缺字段），不重复建档
                        card, lib, created = main_ai.save_generated_character(store, data)
                        if not created:
                            log_fn("info", "角色池已有同名角色「%s」，复用旧卡，不重复建档。" % card.name)
                        else:
                            log_fn("info", "已生成角色卡：%s（%s）" % (card.name, card.role))
                        ok_n += 1
                    except llm.LLMError as e:
                        fail_n += 1
                        log_fn("error", "AI 生成角色失败（第%d/%d个）：%s" % (i + 1, total, e))
                    except Exception as e:
                        fail_n += 1
                        log_fn("error", "AI 生成角色失败（第%d/%d个）：%s" % (i + 1, total, e))
            finally:
                log_fn("info", "角色生成结束：成功 %d 个，失败 %d 个。" % (ok_n, fail_n))
                bus.charactersChanged.emit()
                set_running(False)

        threading.Thread(target=work, daemon=True).start()


class ChooseNameDialog(QDialog):
    """🎲 随机角色名候选窗（v0.47）：性别倾向 + 候选网格（点选即用）+ 自定义输入。

    纯本地字库（name_gen），无网络、无 AI 调用；selectedText 存选中名。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🎲 随机角色名")
        self.resize(460, 360)
        self.selectedText = ""
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        top.addWidget(QLabel("性别倾向"))
        self.gender = QComboBox()
        self.gender.addItems(["随机", "男", "女"])
        self.gender.currentIndexChanged.connect(self._refresh)
        top.addWidget(self.gender)
        more = QPushButton("换一批")
        more.clicked.connect(self._refresh)
        top.addWidget(more)
        top.addStretch(1)
        lay.addLayout(top)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(8)
        self._btns = []
        for i in range(8):
            b = QPushButton()
            b.clicked.connect(lambda _=False, i=i: self._pick(i))
            grid.addWidget(b, i // 2, i % 2)
            self._btns.append(b)
        lay.addLayout(grid)

        cus = QHBoxLayout()
        cus.addWidget(QLabel("自定义"))
        self.custom = QLineEdit()
        self.custom.setPlaceholderText("也可直接输入想要的角色名")
        cus.addWidget(self.custom, 1)
        use = QPushButton("使用")
        use.setObjectName("primary")
        use.clicked.connect(self._use_custom)
        cus.addWidget(use)
        lay.addLayout(cus)

        self._refresh()

    def _gender(self):
        t = self.gender.currentText()
        return "random" if t == "随机" else ("male" if t == "男" else "female")

    def _refresh(self):
        for b, nm in zip(self._btns, name_gen.generate_names(8, self._gender())):
            b.setText(nm)

    def _pick(self, i):
        self.selectedText = self._btns[i].text()
        self.accept()

    def _use_custom(self):
        t = self.custom.text().strip()
        if t:
            self.selectedText = t
            self.accept()


class BatchGenDialog(QDialog):
    """批量生成角色：直接自然语言告诉 AI 要哪些角色，数量由 AI 自行拆解。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批量生成角色")
        self.resize(580, 330)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)
        lab = QLabel("直接告诉 AI 你想要哪些角色（可指定姓名/身份/性格/数量，AI 自动拆解逐个生成；"
                     "只立形象——外貌/气质/性格/说话风格，身世与秘密留给主 AI 在剧情中设计）：")
        lab.setWordWrap(True)
        lab.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lay.addWidget(lab)
        self.desc = QPlainTextEdit()
        self.desc.setPlaceholderText(
            "例：给我生成一个城主管家（老成持重、忠心耿耿但心里有小九九）、"
            "一个商会女掌柜（八面玲珑、唯利是图）和一个矿工头目（粗豪直爽、重义气），"
            "性格各不相同，方便后文安排剧情。")
        self.desc.setMinimumHeight(130)
        lay.addWidget(self.desc)
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("开始生成")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        row.addWidget(ok)
        row.addWidget(cancel)
        lay.addLayout(row)


class BatchManageDialog(QDialog):
    """批量管理：勾选多个角色 → 一次确认批量删除 / 批量改状态（在世/阵亡/游历/已归档/已废弃）。

    表格列出全部角色（支持按名字搜索），勾选列用复选框；底部显示选中数，
    删除只弹一次确认（显示名单），状态修改即时生效。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.page = parent if hasattr(parent, "refresh") else None
        self.setWindowTitle("批量管理角色")
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(10)

        # 搜索 + 全选/清空
        top = QHBoxLayout()
        top.addWidget(QLabel("搜索"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("按姓名过滤…")
        self.search_edit.setFixedWidth(220)
        self.search_edit.textChanged.connect(lambda _: self._reload())
        top.addWidget(self.search_edit)
        top.addStretch(1)
        self.check_all_btn = QPushButton("全选")
        self.check_all_btn.clicked.connect(lambda: self._set_all(True))
        self.uncheck_all_btn = QPushButton("清空")
        self.uncheck_all_btn.clicked.connect(lambda: self._set_all(False))
        top.addWidget(self.check_all_btn)
        top.addWidget(self.uncheck_all_btn)
        lay.addLayout(top)

        # 表格：勾选 | 姓名 | 身份 | 状态 | 创建方式
        self.table = QTableWidget(0, 5)
        self.table.setAlternatingRowColors(True)
        self.table.setHorizontalHeaderLabels(["✓", "姓名", "身份/职业", "状态", "创建方式"])
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        lay.addWidget(self.table, 1)

        # 底部操作条
        ops = QHBoxLayout()
        ops.addWidget(QLabel("批量改状态"))
        self.status_combo = QComboBox()
        self.status_combo.addItems(STATUS_OPTIONS)
        ops.addWidget(self.status_combo)
        apply_btn = QPushButton("应用到选中")
        apply_btn.setObjectName("primary")
        apply_btn.clicked.connect(self._apply_status)
        ops.addWidget(apply_btn)
        ops.addStretch(1)
        self.count_lbl = QLabel("已选 0 个")
        self.count_lbl.setStyleSheet(T("color:#8a93a3;"))
        ops.addWidget(self.count_lbl)
        del_btn = QPushButton("删除选中")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._delete_selected)
        ops.addWidget(del_btn)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        ops.addWidget(close_btn)
        lay.addLayout(ops)

        # 行数据: [(cid, name, role, status_key)]
        self._rows = []
        self._reload()

    # ---------- 数据 ----------
    def _all_characters(self):
        store, _ = current_project()
        if not store:
            return []
        kw = self.search_edit.text().strip()
        out = []
        for cid, name, status in store.list_characters():
            if kw and kw not in name:
                continue
            card, _ = store.load_character(cid)
            if not card:
                continue
            out.append((cid, card.name, card.role, card.status))
        return out

    def _reload(self):
        self._rows = self._all_characters()
        self.table.setRowCount(len(self._rows))
        store, _ = current_project()
        for r, (cid, name, role, status) in enumerate(self._rows):
            chk = QCheckBox()
            chk.setProperty("row", r)
            self.table.setCellWidget(r, 0, chk)
            self.table.setItem(r, 1, QTableWidgetItem(name))
            self.table.setItem(r, 2, QTableWidgetItem(role or ""))
            self.table.setItem(r, 3, QTableWidgetItem(STATUS_TEXT.get(status, status)))
            card, _ = store.load_character(cid)
            by = "AI" if card and card.created_by == "ai" else "手动"
            self.table.setItem(r, 4, QTableWidgetItem(by))
        self._update_count()

    def _selected_rows(self):
        return [r for r in range(self.table.rowCount())
                if self.table.cellWidget(r, 0) and self.table.cellWidget(r, 0).isChecked()]

    def _update_count(self):
        n = len(self._selected_rows())
        self.count_lbl.setText("已选 %d 个" % n)
        self.check_all_btn.setEnabled(bool(self._rows))
        self.uncheck_all_btn.setEnabled(bool(self._rows))

    def _set_all(self, flag):
        for r in range(self.table.rowCount()):
            w = self.table.cellWidget(r, 0)
            if w:
                w.setChecked(flag)
        self._update_count()

    # ---------- 操作 ----------
    def _apply_status(self):
        rows = self._selected_rows()
        if not rows:
            QMessageBox.information(self, "提示", "请先勾选要修改的角色。")
            return
        st = STATUS_KEY
        target = st.get(self.status_combo.currentText(), "active")
        store, _ = current_project()
        names = []
        for r in rows:
            cid, name, role, status = self._rows[r]
            card, lib = store.load_character(cid)
            if not card:
                continue
            card.status = target
            card.version += 1
            store.save_character(card, lib)
            names.append(name)
            self.table.setItem(r, 3, QTableWidgetItem(STATUS_TEXT.get(target, target)))
        log_fn("info", "已将 %d 个角色状态改为「%s」：%s"
               % (len(names), self.status_combo.currentText(), "、".join(names)))
        self._update_count()
        if self.page:
            self.page.refresh()

    def _delete_selected(self):
        rows = self._selected_rows()
        if not rows:
            QMessageBox.information(self, "提示", "请先勾选要删除的角色。")
            return
        names = [self._rows[r][1] for r in rows]
        ret = QMessageBox.question(
            self, "批量删除角色",
            "确定删除选中的 %d 个角色？\n%s\n\n其信息库（事件/情报/隐秘）会一并删除，"
            "已归档章节中引用的角色将显示为「已删除」。" % (len(rows), "、".join(names)))
        if ret != QMessageBox.StandardButton.Yes:
            return
        store, _ = current_project()
        for r in rows:
            store.delete_character(self._rows[r][0])
        log_fn("info", "已批量删除 %d 个角色：%s" % (len(rows), "、".join(names)))
        self._reload()
        if self.page:
            self.page.refresh()


class CharEditDialog(QDialog):
    """角色卡（人设）+ 信息库（外在）编辑。左右两栏均可滚动缩放。"""

    def __init__(self, char_id, parent_page=None):
        super().__init__(parent_page)
        self.char_id = char_id
        store, _ = current_project()
        self.card, self.lib = store.load_character(char_id)
        # 旧数据迁移：角色卡上的 scenario 属外在信息 → 迁入信息库
        if self.card and (self.card.scenario or "") and not (self.lib.scenario or ""):
            self.lib.scenario = self.card.scenario
            self.card.scenario = ""
        self.setWindowTitle("编辑角色 · %s" % (self.card.name if self.card else char_id))
        self.resize(1080, 720)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        body = QHBoxLayout()
        body.setSpacing(14)

        # ---------- 左栏：角色卡（人设，可滚动） ----------
        left_box = QGroupBox("角色卡 · 人设（这个角色是怎么样）")
        left_in = QVBoxLayout(left_box)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_host = QWidget()
        lf = QVBoxLayout(left_host)
        lf.setContentsMargins(6, 4, 10, 6)
        lf.setSpacing(8)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("姓名"))
        self.name_edit = QLineEdit()
        name_row.addWidget(self.name_edit, 1)
        name_row.addWidget(QLabel("分类"))
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.setMinimumWidth(130)
        # 已有分类列表（来自角色页缓存；对话框单独打开时即时收集）
        cats = list(getattr(parent_page, "_categories", []) or [])
        if not cats and store:
            seen = set()
            for cid2, _n, _s in store.list_characters():
                c2, _ = store.load_character(cid2)
                if c2 and c2.category and c2.category not in seen:
                    seen.add(c2.category)
                    cats.append(c2.category)
        for c in cats:
            self.category_combo.addItem(c)
        name_row.addWidget(self.category_combo)
        name_row.addWidget(QLabel("世界状态"))
        self.status_combo = QComboBox()
        self.status_combo.addItems(STATUS_OPTIONS)
        name_row.addWidget(self.status_combo)
        lf.addLayout(name_row)

        desc_lbl = QLabel("角色描述：用自然语言写清外貌、性格、背景、言行习惯等（对应酒馆的 description 字段）")
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        lf.addWidget(desc_lbl)
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setPlaceholderText(
            "例：\n铁砧城酒吧老板娘，三十二岁，风尘气但眼神锐利。寡言，笑起来不动声色，"
            "右手无名指常年戴着一枚旧银戒。与城主府有旧怨，掌握城中大半情报，"
            "对陌生人习惯先试探再给好脸色，关键时刻比谁都靠得住。")
        self.desc_edit.setMinimumHeight(220)
        lf.addWidget(self.desc_edit)

        adv = QGroupBox("高级字段（可选 · 酒馆 Persona 标准字段）")
        adv.setCheckable(True)
        adv.setChecked(False)
        adv_layout = QVBoxLayout(adv)
        self.adv_editors = {}
        for attr, label, h in ADVANCED_FIELDS:
            l = QLabel(label)
            l.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
            adv_layout.addWidget(l)
            w = QPlainTextEdit()
            w.setFixedHeight(h)
            self.adv_editors[attr] = w
            adv_layout.addWidget(w)
        lf.addWidget(adv)
        lf.addStretch(1)

        left_scroll.setWidget(left_host)
        left_in.addWidget(left_scroll)
        body.addWidget(left_box, 5)

        # ---------- 右栏：信息库（外在，可滚动） ----------
        right_box = QGroupBox("信息库 · 外在信息（影响该角色判断的内容）")
        right_in = QVBoxLayout(right_box)
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setFrameShape(QFrame.Shape.NoFrame)
        right_host = QWidget()
        rf = QVBoxLayout(right_host)
        rf.setContentsMargins(6, 4, 10, 6)
        rf.setSpacing(8)

        scen_lbl = QLabel("当前场景/处境（该角色身处何地、处境如何，随剧情由主 AI 更新）")
        scen_lbl.setWordWrap(True)
        scen_lbl.setStyleSheet(T("color:#8a93a3;font-size:12px;"))
        rf.addWidget(scen_lbl)
        self.scenario_edit = QPlainTextEdit()
        self.scenario_edit.setPlaceholderText("例：本卷前中期，她仍在铁砧城经营酒吧，暗中替主角收集城主府情报。")
        self.scenario_edit.setFixedHeight(64)
        rf.addWidget(self.scenario_edit)

        tabs = QTabWidget()
        self.ev_table = self._make_table(["章节", "经历的事件", "产生的影响"])
        self.kn_table = self._make_table(["章节", "已知信息"])
        self.sec_edit = QPlainTextEdit()
        self.sec_edit.setPlaceholderText("每行一条隐秘…")
        self.note_edit = QPlainTextEdit()
        self.note_edit.setPlaceholderText("其他备注…")
        tabs.addTab(self._table_group(self.ev_table), "经历的事件")
        tabs.addTab(self._table_group(self.kn_table), "已知信息")
        tabs.addTab(self.sec_edit, "掌握的隐秘")
        tabs.addTab(self.note_edit, "备注")
        rf.addWidget(tabs, 1)

        right_scroll.setWidget(right_host)
        right_in.addWidget(right_scroll)
        body.addWidget(right_box, 6)

        root.addLayout(body, 1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        save_btn = QPushButton("保存")
        save_btn.setObjectName("primary")
        save_btn.clicked.connect(self._save)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        btns.addWidget(save_btn)
        btns.addWidget(cancel_btn)
        root.addLayout(btns)

        self._load()

    def _make_table(self, headers):
        t = QTableWidget(0, len(headers))
        t.setAlternatingRowColors(True)
        t.setHorizontalHeaderLabels(headers)
        t.horizontalHeader().setStretchLastSection(True)
        t.verticalHeader().setVisible(False)
        return t

    def _table_group(self, table):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(table)
        row = QHBoxLayout()
        add = QPushButton("＋ 添加行")
        add.clicked.connect(lambda: table.insertRow(table.rowCount()))
        rm = QPushButton("－ 删除选中行")
        rm.clicked.connect(lambda: table.removeRow(table.currentRow())
                           if table.currentRow() >= 0 else None)
        row.addWidget(add)
        row.addWidget(rm)
        row.addStretch(1)
        lay.addLayout(row)
        return w

    # ---------- 载入 ----------
    def _load(self):
        if not self.card:
            return
        card, lib = self.card, self.lib
        self.name_edit.setText(card.name)
        self.category_combo.setCurrentText(card.category or "")
        # 状态回填（含「已废弃」，避免打开废弃卡保存时被当成在世）
        self.status_combo.setCurrentText(STATUS_TEXT.get(card.status, "在世"))
        self.desc_edit.setPlainText(card.description)
        for attr, _, _ in ADVANCED_FIELDS:
            self.adv_editors[attr].setPlainText(getattr(card, attr, "") or "")
        self.scenario_edit.setPlainText(lib.scenario)
        for e in lib.events:
            r = self.ev_table.rowCount()
            self.ev_table.insertRow(r)
            self.ev_table.setItem(r, 0, QTableWidgetItem(str(e.get("chapter", ""))))
            self.ev_table.setItem(r, 1, QTableWidgetItem(e.get("event", "")))
            self.ev_table.setItem(r, 2, QTableWidgetItem(e.get("impact", "")))
        for k in lib.knowledge:
            r = self.kn_table.rowCount()
            self.kn_table.insertRow(r)
            self.kn_table.setItem(r, 0, QTableWidgetItem(str(k.get("chapter", ""))))
            self.kn_table.setItem(r, 1, QTableWidgetItem(k.get("info", "")))
        self.sec_edit.setPlainText("\n".join(lib.secrets))
        self.note_edit.setPlainText(lib.notes)

    # ---------- 保存 ----------
    def _save(self):
        store, _ = current_project()
        card, lib = self.card, self.lib
        if not card:
            self.reject()
            return
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "姓名不能为空。")
            return
        card.name = name
        card.description = self.desc_edit.toPlainText().strip()
        for attr, _, _ in ADVANCED_FIELDS:
            setattr(card, attr, self.adv_editors[attr].toPlainText().strip())
        st = STATUS_KEY
        card.status = st.get(self.status_combo.currentText(), card.status)
        card.category = (self.category_combo.currentText() or "").strip()
        card.version += 1

        lib.scenario = self.scenario_edit.toPlainText().strip()
        lib.events = []
        for r in range(self.ev_table.rowCount()):
            ch = self.ev_table.item(r, 0)
            ev = self.ev_table.item(r, 1)
            im = self.ev_table.item(r, 2)
            if ev and ev.text().strip():
                lib.events.append({
                    "chapter": (ch.text().strip() if ch else "").replace("第", "").replace("章", ""),
                    "event": ev.text().strip(),
                    "impact": (im.text().strip() if im else ""),
                })
        lib.knowledge = []
        for r in range(self.kn_table.rowCount()):
            ch = self.kn_table.item(r, 0)
            k = self.kn_table.item(r, 1)
            if k and k.text().strip():
                lib.knowledge.append({
                    "chapter": (ch.text().strip() if ch else "").replace("第", "").replace("章", ""),
                    "info": k.text().strip(),
                })
        lib.secrets = [s.strip() for s in self.sec_edit.toPlainText().splitlines()
                       if s.strip()]
        lib.notes = self.note_edit.toPlainText().strip()

        store.save_character(card, lib)
        log_fn("info", "角色卡与信息库已保存：%s" % card.name)
        page = self.parent()
        if page and hasattr(page, "refresh"):
            page.refresh()
        self.accept()
