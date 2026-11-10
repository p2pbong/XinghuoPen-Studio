# -*- coding: utf-8 -*-
"""情景写作提示词功能页（v1.18 建页，v1.21 总库/项目库分离）：全局总库 + 当前项目主AI可用库。

用户需求（v1.18）：正文AI情景提示词需要一个**专门储存的功能页**——卡库 CRUD（新增/编辑/
删除/任意个数）、AI 一键生成（按「通用情景写作提示词.txt」范例结构：核心定位+分节细则+
写作执行自检清单，字数不限）、导入/导出（单卡 txt 与批量导出可再导入）。

v1.21 起**总库（全局卡库）与「当前项目主AI可用库」（项目库）彻底独立**：
- 总库 = 你提供/制作/提取/导入的全部情景规则卡（config["writer_scene_cards"]）；
- 项目库 = project.scene_cards（[{name,content,source}]，source=user|ai）——主AI每章按正文
  类型**优先选已有卡**，本章类型无匹配卡时主AI会**自行按规则设计一张**（只进本项目库，
  标记「AI 制作」）；你觉得好用的卡点「放入总库」留下来给所有项目用。
- 一键成书 / 项目页都从**总库**勾选要带入本项目的卡。
"""
import threading

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QComboBox, QDialog, QFileDialog, QGroupBox,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QVBoxLayout,
                               QWidget)

import config as app_config
from gui_app import current_project, log_fn, set_running
from prompts import _DEFAULT_EXTRACT_SYS
from gui_theme import T

# 批量导出/导入的卡分隔标记：一行 【卡名】名称 开始一张卡，直到下一个标记/文件尾
CARD_SEP_PREFIX = "【卡名】"


def _all_cards():
    """全局卡库（config["writer_scene_cards"]）。"""
    return list(app_config.load_config().get("writer_scene_cards") or [])


def _save_cards(cards):
    cfg = app_config.load_config()
    cfg["writer_scene_cards"] = cards
    app_config.save_config(cfg)


def _export_text(cards):
    """多卡导出为可再导入的文本：每卡一段，以 【卡名】名称 开头。

    v1.24 有分类的卡在内容前附一行【分类】分类名（无分类则省略，旧版仍可导入）。
    """
    out = []
    for c in cards:
        nm = str(c.get("name") or "").strip() or "未命名"
        ct = str(c.get("content") or "").strip()
        cat = str(c.get("category") or "").strip()
        if ct:
            head = "%s%s" % (CARD_SEP_PREFIX, nm)
            if cat:
                head += "\n【分类】%s" % cat
            out.append("%s\n%s" % (head, ct))
    return "\n\n".join(out)


def _parse_import(text, fallback_name=""):
    """解析导入文本为卡列表。支持【卡名】分隔的多卡文本；无分隔标记时整段作为一张卡
    （卡名取 fallback_name 或「未命名」）。返回 [{"name","content","category"}]。

    v1.24 卡的【分类】行（内容首行）解析为 category，兼容旧文件（无分类行时 category 空）。
    v1.31 细分文件（v1.30 批量导出，文件名 [分类]卡名.txt）兼容：fallback_name 形如
    「[武打]夜战夺镖」时拆分出 category=武打、卡名=夜战夺镖（内容含【分类】行时以内容为准）。
    """
    text = (text or "").strip()
    if not text:
        return []
    cards = []
    parts = []
    cur = None
    for line in text.split("\n"):
        if line.startswith(CARD_SEP_PREFIX):
            if cur:
                parts.append(cur)
            cur = {"name": line[len(CARD_SEP_PREFIX):].strip(), "lines": []}
            continue
        if cur is None:
            cur = {"name": "", "lines": []}
        cur["lines"].append(line)
    if cur:
        parts.append(cur)
    # v1.31 文件名 [分类]卡名 前缀（v1.30 批量导出细分文件格式）
    fb_cat = fb_name = ""
    if fallback_name.startswith("[") and "]" in fallback_name:
        _rb = fallback_name.find("]")
        fb_cat = fallback_name[1:_rb].strip()
        fb_name = fallback_name[_rb + 1:].strip()
    for p in parts:
        lines = list(p["lines"])
        category = ""
        if lines and lines[0].startswith("【分类】"):
            category = lines[0][len("【分类】"):].strip()
            lines = lines[1:]
        content = "\n".join(lines).strip()
        if not content:
            continue
        name = p["name"] or (fb_name or fallback_name) or "未命名"
        if not category:
            category = fb_cat
        cards.append({"name": name, "content": content, "category": category})
    return cards


def _file_safe(name):
    """把卡名/分类转成合法文件名（替换 Windows 非法字符；v1.30 批量导出细分文件用）。"""
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "_")
    return (name or "未命名").strip() or "未命名"


class _CheckListWidget(QListWidget):
    """选卡弹窗列表（v1.28 交互修复）：点行文本 = 切换该行勾选（不用精确点复选框）；
    点左侧复选框区域（x≤28）走 Qt 默认行为。标题行同样点行即整类全选/全不选。"""

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            if pos.x() > 28:  # 避开左侧复选框区
                item = self.itemAt(pos.toPoint())
                if item is not None and (
                        item.flags() & Qt.ItemFlag.ItemIsUserCheckable):
                    self.toggle_row(item)
                    return
        super().mouseReleaseEvent(event)

    @staticmethod
    def toggle_row(item):
        """切换某行勾选状态（卡行=勾/不勾；分类标题行=整类全选/全不选）。"""
        item.setCheckState(Qt.CheckState.Checked
                           if item.checkState() != Qt.CheckState.Checked
                           else Qt.CheckState.Unchecked)


class _PickCardsDialog(QDialog):
    """从总库多选卡（勾选列表）。

    v1.25 按分类分组：每组一个加粗标题行（带复选框——勾选 = 整类全选，取消 = 整类全不选），
    组内卡可单独勾选；卡名存 data(UserRole) 防前缀/标题干扰取值。
    exist_names：已存在的卡名（默认不勾，用于「从总库加入本项目」语义）；
    checked：显式指定默认勾选名单（一键成书「＋ 加入」用：原已加入的默认勾选，
    取消勾选 = 不带）；未传时用 exist_names 语义。
    """

    def __init__(self, cards, exist_names, parent=None, checked=None):
        super().__init__(parent)
        self.setWindowTitle("从总库选择情景卡")
        self.setMinimumWidth(480)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(
            "勾选要加入的卡（✔ 分类标题 = 整类全选/全不选；组内卡可单独勾选）："
            if checked is not None else
            "勾选要复制进本项目主AI可用库的卡（✔ 分类标题 = 整类全选/全不选）："))
        self.list = _CheckListWidget()
        self.list.setMinimumHeight(280)
        default_checked = set(checked) if checked is not None else set()
        groups = {}
        for c in cards:
            nm = str(c.get("name") or "").strip()
            if not nm:
                continue
            cat = str(c.get("category") or "").strip() or "未分类"
            groups.setdefault(cat, []).append(c)
        for cat, clist in groups.items():
            all_checked = all(
                (str(c.get("name") or "").strip() in default_checked)
                if checked is not None else
                (str(c.get("name") or "").strip() not in exist_names)
                for c in clist if str(c.get("name") or "").strip())
            title = QListWidgetItem("▾ %s（%d 张）" % (cat, len(clist)))
            title.setData(Qt.ItemDataRole.UserRole, "__CAT__")
            title.setData(Qt.ItemDataRole.UserRole + 1, cat)
            title.setFlags(title.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            title.setCheckState(Qt.CheckState.Checked if all_checked
                                else Qt.CheckState.Unchecked)
            f = title.font()
            f.setBold(True)
            title.setFont(f)
            self.list.addItem(title)
            for c in clist:
                nm = str(c.get("name") or "").strip()
                cat2 = str(c.get("category") or "").strip()
                label = ("[%s] %s（%d 字）" % (cat2, nm, len(str(c.get("content") or "")))
                         if cat2 else "%s（%d 字）" % (nm, len(str(c.get("content") or ""))))
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, nm)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                if checked is not None:
                    item.setCheckState(Qt.CheckState.Checked if nm in default_checked
                                       else Qt.CheckState.Unchecked)
                else:
                    item.setCheckState(Qt.CheckState.Checked if nm not in exist_names
                                       else Qt.CheckState.Unchecked)
                self.list.addItem(item)
        self.list.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self.list)
        brow = QHBoxLayout()
        cc = QPushButton("取消")
        cc.clicked.connect(self.reject)
        ok = QPushButton("确定")
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        brow.addStretch(1)
        brow.addWidget(cc)
        brow.addWidget(ok)
        lay.addLayout(brow)

    def _on_item_changed(self, item):
        """分类标题复选框 → 整类全选/全不选（组内卡单独勾选不反向影响标题）。"""
        if item.data(Qt.ItemDataRole.UserRole) != "__CAT__":
            return
        want = item.checkState() == Qt.CheckState.Checked
        start = self.list.row(item)
        for i in range(start + 1, self.list.count()):
            it = self.list.item(i)
            if it.data(Qt.ItemDataRole.UserRole) == "__CAT__":
                break
            it.setCheckState(Qt.CheckState.Checked if want
                             else Qt.CheckState.Unchecked)

    def picked(self):
        out = []
        for i in range(self.list.count()):
            it = self.list.item(i)
            if it.checkState() == Qt.CheckState.Checked:
                nm = it.data(Qt.ItemDataRole.UserRole)
                if nm and nm != "__CAT__":
                    out.append(str(nm))
        return out


class SceneCardsPage(QWidget):
    """情景写作提示词功能页（v1.18 独立页，包 _PageScroll 后进 QStackedWidget）。"""

    _card_generated = Signal(object)   # ("ok", name, content) | ("err", name, msg)

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._current = None    # 列表当前卡名（用于「保存修改」定位）
        self._generating = False
        self._card_generated.connect(self._on_card_generated)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(10)

        title = QLabel("情景写作提示词 · 正文AI情景规则卡（总库 + 当前项目主AI可用库）")
        title.setStyleSheet(T("font-size:16px;color:#d4a44c;font-weight:bold;"))
        lay.addWidget(title)

        hint = QLabel(
            "每张卡给一类「正文情景」定写作规则（如武打/文斗/见父母装傻充愣）。\n"
            "上半区是**总库**：你提供/制作/提取/导入的全部卡（新增、AI 一键生成、从文本提取、导入导出都在这里）。\n"
            "下半区是**当前项目主AI可用库**（与总库独立）：主AI每章按正文类型优先从这里选已有卡；"
            "本章类型没有匹配卡时，主AI会按规则**自行设计一张**（只进本项目库、标记「AI 制作」），"
            "你觉得好用的卡点「📥 放入总库」就能留下来给所有项目用。\n"
            "一键成书与项目页都是从总库勾选要带入本项目的卡。文风（语感/句式）仍由文风参考统一管，卡只约束情景怎么写才有起伏。")
        hint.setWordWrap(True)
        hint.setStyleSheet(T("color:#5b6470;font-size:12px;"))
        lay.addWidget(hint)

        # ---------- 卡库列表 + 操作 ----------
        list_box = QGroupBox("总库·卡库列表（全局，你提供的卡，任意个数）")
        llay = QVBoxLayout(list_box)
        catrow = QHBoxLayout()
        catrow.addWidget(QLabel("分类筛选："))
        self.category_combo = QComboBox()
        self.category_combo.setEditable(True)
        self.category_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.category_combo.setToolTip("只显示该分类的卡（选「全部」显示所有卡）。\n"
                                       "可直接输入新分类名后回车——筛选到该分类，方便连续新增同分类卡；\n"
                                       "卡的分类在下方编辑区的「分类」框里设置。")
        self.category_combo.currentTextChanged.connect(self._on_category_changed)
        catrow.addWidget(self.category_combo, 1)
        catrow.addStretch(2)
        llay.addLayout(catrow)
        row = QHBoxLayout()
        self.card_list = QListWidget()
        self.card_list.setMinimumHeight(180)
        self.card_list.currentRowChanged.connect(self._on_row)
        row.addWidget(self.card_list, 3)
        ops = QVBoxLayout()
        add_btn = QPushButton("＋ 新增")
        add_btn.clicked.connect(self._card_new)
        self.save_btn = QPushButton("💾 保存当前卡")
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self._card_save)
        del_btn = QPushButton("🗑 删除当前卡")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._card_delete)
        self.gen_btn = QPushButton("✨ AI 一键生成")
        self.gen_btn.setObjectName("accent")
        self.gen_btn.clicked.connect(self._card_ai_gen)
        self.extract_btn = QPushButton("📄 从文本提取")
        self.extract_btn.setObjectName("accent")
        self.extract_btn.setToolTip("粘贴一段参考文本（如你喜欢的一类情景的写法范例），"
                                    "AI 从中提炼该类情景的规则卡草稿（不照抄原文），可编辑后保存")
        self.extract_btn.clicked.connect(self._card_extract)
        ops.addWidget(add_btn)
        ops.addWidget(self.save_btn)
        ops.addWidget(del_btn)
        ops.addWidget(self.gen_btn)
        ops.addWidget(self.extract_btn)
        ops.addStretch(1)
        row.addLayout(ops, 1)
        llay.addLayout(row)

        # ---------- 当前卡编辑区 ----------
        edit_box = QGroupBox("当前卡（类型名 + 分类 + 规则内容）")
        elay = QVBoxLayout(edit_box)
        elay.addWidget(QLabel("类型名（主AI据此按本章正文类型选用）："))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例：武打 / 文斗 / 见父母装傻充愣 / 情感对峙")
        elay.addWidget(self.name_edit)
        catr = QHBoxLayout()
        catr.addWidget(QLabel("分类（可选，卡多时方便管理；下拉选已有的不怕忘，也可直接输新分类）："))
        self.category_edit = QComboBox()
        self.category_edit.setEditable(True)
        self.category_edit.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.category_edit.setToolTip("从已有分类下拉选择（不用记分类名）；也可直接输入新分类名"
                                      "（保存后成为新分类并出现在上方的分类筛选中）。\n「未分类」= 不设分类")
        catr.addWidget(self.category_edit, 1)
        elay.addLayout(catr)
        elay.addWidget(QLabel("规则内容（正文AI写作时必须逐条遵守；按范例结构：核心定位+分节细则+自检清单）："))
        self.content_edit = QPlainTextEdit()
        self.content_edit.setMinimumHeight(260)
        self.content_edit.setPlaceholderText(
            "例：\n你是一位擅长写实的网文作者，专精武打场景……\n\n**核心定位：**……\n\n**一、动作与对抗：**\n- ……\n\n**写作执行与自检清单：**\n1. ……")
        elay.addWidget(self.content_edit)
        lay.addWidget(list_box)
        lay.addWidget(edit_box)

        # ---------- 导入 / 导出 ----------
        io_box = QGroupBox("导入 / 导出")
        ilay = QHBoxLayout(io_box)
        imp_btn = QPushButton("📥 导入 txt")
        imp_btn.setToolTip("导入情景提示词文本：支持【卡名】开头分隔的多卡文件（本页批量导出格式），"
                           "也支持无分隔的单卡文本（卡名取文件名）")
        imp_btn.clicked.connect(self._import_txt)
        imp_batch = QPushButton("📂 批量导入 txt")
        imp_batch.setToolTip("一次选择多个 txt 导入（v1.30：支持汇总文件与「_细分」文件夹里的单卡文件；"
                             "同名自动跳过，不会覆盖已有卡）")
        imp_batch.clicked.connect(self._import_batch)
        self.exp_btn = QPushButton("📤 导出当前卡 txt")
        self.exp_btn.setToolTip("把当前编辑区的卡导出为 .txt（文件名=类型名）")
        self.exp_btn.clicked.connect(self._export_one)
        exp_all_btn = QPushButton("📤📤 批量导出（txt + 细分文件夹）")
        exp_all_btn.setToolTip("v1.30 选一个文件夹：① 生成汇总 txt（每卡以【卡名】分隔，可整批再导入）；"
                               "② 同时生成「_细分」子文件夹，每张卡一个文件（文件名带分类前缀）——"
                               "下次只想导入其中一张，直接选那个文件就行")
        exp_all_btn.clicked.connect(self._export_batch)
        ilay.addWidget(imp_btn)
        ilay.addWidget(imp_batch)
        ilay.addWidget(self.exp_btn)
        ilay.addWidget(exp_all_btn)
        ilay.addStretch(1)
        lay.addWidget(io_box)

        # ---------- 提取提示词（v1.20 可编辑：保存到 config / 恢复初始） ----------
        ep_box = QGroupBox("从文本提取·提取提示词（可改；保存后生效，改坏了可恢复初始）")
        eplay = QVBoxLayout(ep_box)
        self.extract_prompt_edit = QPlainTextEdit()
        self.extract_prompt_edit.setMinimumHeight(180)
        self.extract_prompt_edit.setToolTip("「📄 从文本提取」环节用的提取提示词（角色定位+分析要求）。\n"
                                            "改完点「保存提取提示词」生效；想回到出厂版本点「恢复初始」。")
        eplay.addWidget(self.extract_prompt_edit)
        eprow = QHBoxLayout()
        save_ep = QPushButton("💾 保存提取提示词")
        save_ep.setObjectName("primary")
        save_ep.clicked.connect(self._save_extract_prompt)
        reset_ep = QPushButton("↩ 恢复初始")
        reset_ep.setObjectName("danger")
        reset_ep.clicked.connect(self._reset_extract_prompt)
        eprow.addWidget(save_ep)
        eprow.addWidget(reset_ep)
        eprow.addStretch(1)
        eplay.addLayout(eprow)
        lay.addWidget(ep_box)

        # ---------- 当前项目主AI可选的情景提示词卡（v1.20 显示框 → v1.21 可操作项目库） ----------
        cur_box = QGroupBox("当前项目主AI可选的情景提示词卡（本项目库，与总库独立；"
                            "主AI每章按正文类型优先从这里选已有卡，本章类型没匹配卡时自做一张只进本库）")
        clay2 = QVBoxLayout(cur_box)
        self.project_cards_view = QListWidget()
        self.project_cards_view.setMinimumHeight(120)
        self.project_cards_view.setToolTip("当前项目主AI可选的情景规则卡（本项目库，与总库独立）。\n"
                                           "主AI每章按正文类型优先从已有卡里选；没匹配类型时会自做一张"
                                           "（标记「AI 制作」，只进本库）。\n"
                                           "「＋ 从总库加入」把总库卡复制进本项目；「🗑 移出本项目」解除可用；"
                                           "「📥 放入总库」把本项目卡留进总库（所有项目可用）。")
        self.project_cards_view.currentRowChanged.connect(self._on_project_row)
        clay2.addWidget(self.project_cards_view)
        prows = QHBoxLayout()
        proj_add = QPushButton("＋ 从总库加入")
        proj_add.setObjectName("primary")
        proj_add.setToolTip("从总库勾选卡，复制进本项目主AI可用库（用户提供）")
        proj_add.clicked.connect(self._project_add_from_lib)
        self.proj_del_btn = QPushButton("🗑 移出本项目")
        self.proj_del_btn.setObjectName("danger")
        self.proj_del_btn.clicked.connect(self._project_remove)
        self.proj_lib_btn = QPushButton("📥 放入总库")
        self.proj_lib_btn.setObjectName("accent")
        self.proj_lib_btn.setToolTip("把选中的本项目卡复制进总库（所有项目都能从总库加入它）。"
                                     "同名已存在时询问是否覆盖")
        self.proj_lib_btn.clicked.connect(self._project_to_lib)
        prows.addWidget(proj_add)
        prows.addWidget(self.proj_del_btn)
        prows.addWidget(self.proj_lib_btn)
        prows.addStretch(1)
        clay2.addLayout(prows)
        self.project_cards_detail = QPlainTextEdit()
        self.project_cards_detail.setReadOnly(True)
        self.project_cards_detail.setMaximumHeight(120)
        self.project_cards_detail.setPlaceholderText("点选上面的一张卡，这里显示它的完整规则内容…")
        clay2.addWidget(self.project_cards_detail)
        lay.addWidget(cur_box)

        lay.addStretch(1)

    # ---------- 提取提示词（v1.20 可编辑/恢复初始） ----------
    def _refresh_extract_prompt(self):
        """回填提取提示词：config 有自定义用之，否则内置初始。"""
        cfg = app_config.load_config()
        custom = (cfg.get("extract_scene_card_prompt") or "").strip()
        self.extract_prompt_edit.setPlainText(custom or _DEFAULT_EXTRACT_SYS)

    def _save_extract_prompt(self):
        """保存提取提示词到 config（全局，影响「从文本提取」环节）。"""
        text = self.extract_prompt_edit.toPlainText().strip()
        cfg = app_config.load_config()
        cfg["extract_scene_card_prompt"] = text or None
        app_config.save_config(cfg)
        log_fn("info", "提取提示词已保存（%d 字，从文本提取环节生效）。" % len(text))
        QMessageBox.information(self, "已保存", "提取提示词已保存（%d 字），「从文本提取」将按此执行。"
                                 % len(text))

    def _reset_extract_prompt(self):
        """恢复初始提取提示词（清空 config 自定义，回内置初始）。"""
        ret = QMessageBox.question(self, "恢复初始",
                                   "确定恢复为初始提取提示词吗？当前自定义内容会丢失。")
        if ret != QMessageBox.StandardButton.Yes:
            return
        cfg = app_config.load_config()
        cfg["extract_scene_card_prompt"] = None
        app_config.save_config(cfg)
        self.extract_prompt_edit.setPlainText(_DEFAULT_EXTRACT_SYS)
        log_fn("info", "提取提示词已恢复初始。")
        QMessageBox.information(self, "已恢复", "已恢复初始提取提示词。")

    # ---------- 当前项目主AI可用情景卡库（v1.20 显示框 → v1.21 可操作项目库） ----------
    def _refresh_project_cards(self):
        """显示当前项目主AI可选情景卡库（project.scene_cards，与总库独立）。"""
        self.project_cards_view.blockSignals(True)
        self.project_cards_view.clear()
        self.project_cards_detail.clear()
        self.project_cards_view.blockSignals(False)
        try:
            _, project = current_project()
        except Exception:
            project = None
        if project is None:
            self.project_cards_view.addItem("（未载入项目——载入项目后这里显示主AI可选的情景卡）")
            return
        cards = [c for c in (getattr(project, "scene_cards", None) or [])
                 if isinstance(c, dict) and str(c.get("name") or "").strip()
                 and str(c.get("content") or "").strip()]
        if not cards:
            self.project_cards_view.addItem(
                "（本项目库为空——点「＋ 从总库加入」把总库卡带进来；"
                "主AI在缺匹配类型时也会自做一张只进本库）")
            return
        for c in cards:
            nm = str(c.get("name") or "").strip()
            ct = str(c.get("content") or "").strip()
            src = "我提供" if str(c.get("source") or "").strip() != "ai" else "AI 制作"
            cat = str(c.get("category") or "").strip()
            prefix = "[%s] " % cat if cat else ""
            preview = ct[:60] + ("…" if len(ct) > 60 else "")
            self.project_cards_view.addItem("■ [%s] %s%s（%d 字）：%s" % (src, prefix, nm, len(ct), preview))

    def _on_project_row(self, row):
        """点选项目库卡 → 显示完整规则内容。"""
        try:
            _, project = current_project()
        except Exception:
            project = None
        cards = []
        if project is not None:
            cards = [c for c in (getattr(project, "scene_cards", None) or [])
                     if isinstance(c, dict) and str(c.get("name") or "").strip()
                     and str(c.get("content") or "").strip()]
        if 0 <= row < len(cards):
            self.project_cards_detail.setPlainText(
                "【%s】%s\n\n%s" % (
                    "我提供" if str(cards[row].get("source") or "").strip() != "ai" else "AI 制作",
                    str(cards[row].get("name") or "").strip(),
                    str(cards[row].get("content") or "").strip()))
        else:
            self.project_cards_detail.clear()

    def _project_add_from_lib(self):
        """从总库勾选卡，复制进本项目主AI可用库（source="user"）。"""
        try:
            store, project = current_project()
        except Exception:
            store = project = None
        if project is None:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        lib = self._cards()
        if not lib:
            QMessageBox.warning(self, "提示", "总库为空——先在上方「总库·卡库列表」新增/生成/导入几张卡。")
            return
        exist = {str(c.get("name") or "").strip() for c in
                 (getattr(project, "scene_cards", None) or [])}
        dlg = _PickCardsDialog(lib, exist, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        picked = dlg.picked()
        if not picked:
            return
        project.scene_cards = list(getattr(project, "scene_cards", None) or [])
        added = 0
        for nm in picked:
            if nm in exist:
                continue
            hit = next((c for c in lib if str(c.get("name") or "").strip() == nm), None)
            if hit and str(hit.get("content") or "").strip():
                project.scene_cards.append({"name": nm,
                                            "content": str(hit.get("content") or ""),
                                            "source": "user",
                                            "category": str(hit.get("category") or "")})
                exist.add(nm)
                added += 1
        store.save_project(project)
        self._refresh_project_cards()
        log_fn("info", "从总库加入本项目情景卡 %d 张（本项目库现有 %d 张）。"
               % (added, len(project.scene_cards)))
        QMessageBox.information(self, "已加入",
                                "已把 %d 张总库卡复制进本项目主AI可用库（本项目库共 %d 张）。"
                                % (added, len(project.scene_cards)))

    def _project_remove(self):
        """把选中的本项目库卡移出（只解除本项目可用，不影响总库）。"""
        try:
            store, project = current_project()
        except Exception:
            store = project = None
        if project is None:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        row = self.project_cards_view.currentRow()
        cards = [c for c in (getattr(project, "scene_cards", None) or [])
                 if isinstance(c, dict) and str(c.get("name") or "").strip()]
        if row < 0 or row >= len(cards):
            QMessageBox.warning(self, "提示", "请先选中要移出的一张卡。")
            return
        nm = str(cards[row].get("name") or "").strip()
        ret = QMessageBox.question(self, "移出本项目",
                                   "把「%s」移出本项目主AI可用库吗？\n（不影响总库，可随时再加回来）" % nm)
        if ret != QMessageBox.StandardButton.Yes:
            return
        project.scene_cards = [c for c in cards if str(c.get("name") or "").strip() != nm]
        store.save_project(project)
        self._refresh_project_cards()
        log_fn("info", "已把「%s」移出本项目主AI可用库。" % nm)

    def _project_to_lib(self):
        """把选中的本项目库卡复制进总库（同名已存在 → 询问覆盖；否则新增）。"""
        try:
            store, project = current_project()
        except Exception:
            store = project = None
        if project is None:
            QMessageBox.warning(self, "提示", "请先载入项目。")
            return
        row = self.project_cards_view.currentRow()
        cards = [c for c in (getattr(project, "scene_cards", None) or [])
                 if isinstance(c, dict) and str(c.get("name") or "").strip()
                 and str(c.get("content") or "").strip()]
        if row < 0 or row >= len(cards):
            QMessageBox.warning(self, "提示", "请先选中要放入总库的一张卡。")
            return
        c = cards[row]
        nm = str(c.get("name") or "").strip()
        ct = str(c.get("content") or "").strip()
        lib = self._cards()
        hit = next((x for x in lib if str(x.get("name") or "").strip() == nm), None)
        if hit is not None:
            ret = QMessageBox.question(self, "总库已有同名卡",
                                       "总库已有卡「%s」。要用本项目的这版内容覆盖它吗？（否=跳过）" % nm)
            if ret != QMessageBox.StandardButton.Yes:
                return
            hit["content"] = ct
            hit["category"] = str(c.get("category") or "")
        else:
            lib = lib + [{"name": nm, "content": ct,
                          "category": str(c.get("category") or "")}]
        self._persist(lib)
        self._refresh_list(keep_sel=True)
        log_fn("info", "已把本项目卡「%s」放入总库（全局可用）。" % nm)
        QMessageBox.information(self, "已放入总库",
                                "「%s」已放入总库，所有项目都能从总库加入它。" % nm)

    # ---------- 数据 ----------
    def on_show(self):
        self._refresh_categories(keep_selection=True)
        self._refresh_extract_prompt()
        self._refresh_project_cards()

    def _cards(self):
        return _all_cards()

    def _persist(self, cards):
        _save_cards(cards)
        self._refresh_categories(keep_selection=True)
        log_fn("info", "情景规则卡已保存（%d 张）。" % len(cards))

    # ---------- 分类（v1.24） ----------
    def _category_filter(self, c):
        """当前分类筛选是否命中该卡（card 项 dict）。"""
        cur = self.category_combo.currentText().strip()
        if not cur or cur == "全部":
            return True
        cat = str(c.get("category") or "").strip() or "未分类"
        return cat == cur

    def _category_options(self):
        cats = ["全部", "未分类"]
        seen = set(cats)
        for c in self._cards():
            cat = str(c.get("category") or "").strip() or "未分类"
            if cat not in seen:
                seen.add(cat)
                cats.append(cat)
        return cats

    def _refresh_categories(self, keep_selection=False):
        """重建分类下拉（保留当前选择；自定义新分类名若无卡不保留），
        并同步刷新编辑区「分类」下拉（「未分类」+ 已有分类，v1.25 下拉选不怕忘）。"""
        cur = self.category_combo.currentText().strip()
        cats = self._category_options()
        self.category_combo.blockSignals(True)
        self.category_combo.clear()
        self.category_combo.addItems(cats)
        self.category_combo.setCurrentText(cur if cur in cats else "全部")
        self.category_combo.blockSignals(False)
        cur_edit = self.category_edit.currentText().strip() or "未分类"
        self.category_edit.blockSignals(True)
        self.category_edit.clear()
        self.category_edit.addItem("未分类", "")
        for c in cats[1:]:
            if c != "未分类":
                self.category_edit.addItem(c, c)
        # editable：已有分类精确恢复；输入中的新分类名保持编辑文本不丢
        self.category_edit.setCurrentText(cur_edit)
        self.category_edit.blockSignals(False)
        self._refresh_list(keep_sel=keep_selection)

    def _on_category_changed(self, _text):
        self._refresh_list(keep_sel=True)

    def _refresh_list(self, keep_sel=False):
        sel_name = self._current if keep_sel else None
        self.card_list.blockSignals(True)
        self.card_list.clear()
        cards = [c for c in self._cards() if self._category_filter(c)]
        for c in cards:
            nm = str(c.get("name") or "").strip() or "未命名"
            ct = str(c.get("content") or "").strip()
            cat = str(c.get("category") or "").strip()
            prefix = "[%s] " % cat if cat else ""
            self.card_list.addItem("%s%s（%d 字）" % (prefix, nm, len(ct)))
        self.card_list.blockSignals(False)
        idx = -1
        if sel_name:
            for i, c in enumerate(cards):
                if str(c.get("name") or "").strip() == sel_name:
                    idx = i
                    break
        self.card_list.setCurrentRow(idx if idx >= 0 else (0 if self.card_list.count() else -1))
        self._on_row(self.card_list.currentRow())

    def _on_row(self, row):
        cards = [c for c in self._cards() if self._category_filter(c)]
        if row < 0 or row >= len(cards):
            self._current = None
            self.name_edit.clear()
            self.category_edit.clear()
            self.content_edit.clear()
            self.save_btn.setEnabled(False)
            self.exp_btn.setEnabled(False)
            return
        c = cards[row]
        self._current = str(c.get("name") or "").strip()
        self.name_edit.setText(self._current)
        cat = str(c.get("category") or "").strip()
        self.category_edit.setCurrentText(cat if cat else "未分类")
        self.content_edit.setPlainText(str(c.get("content") or ""))
        self.save_btn.setEnabled(True)
        self.exp_btn.setEnabled(True)

    # ---------- 操作 ----------
    def _card_new(self):
        self._current = None
        self.card_list.setCurrentRow(-1)
        self.name_edit.clear()
        self.content_edit.clear()
        cur_cat = self.category_combo.currentText().strip()
        self.category_edit.setCurrentText(
            cur_cat if cur_cat not in ("", "全部", "未分类") else "未分类")
        self.save_btn.setEnabled(True)
        self.name_edit.setFocus()

    def _card_save(self):
        name = self.name_edit.text().strip() or "未命名"
        content = self.content_edit.toPlainText().strip()
        category = self.category_edit.currentText().strip()
        if category == "未分类":
            category = ""
        if not content:
            QMessageBox.warning(self, "提示", "卡内容不能为空。")
            return
        cards = self._cards()
        if self._current:
            for c in cards:
                if str(c.get("name") or "").strip() == self._current:
                    c["name"] = name
                    c["content"] = content
                    c["category"] = category
                    break
        else:
            cards.append({"name": name, "content": content, "category": category})
        self._persist(cards)
        self._current = name

    def _card_delete(self):
        if not self._current:
            QMessageBox.warning(self, "提示", "请先选中一张卡。")
            return
        ret = QMessageBox.question(self, "删除情景卡", "确定删除「%s」？" % self._current)
        if ret != QMessageBox.StandardButton.Yes:
            return
        cards = [c for c in self._cards()
                 if str(c.get("name") or "").strip() != self._current]
        self._persist(cards)

    def _card_ai_gen(self):
        name, ok = QInputDialog.getText(
            self, "AI 一键生成情景卡",
            "输入情景类型名（主AI据此按本章正文类型选用）：\n"
            "例：武打 / 文斗 / 见父母装傻充愣 / 情感对峙 / 群像宴会")
        if not ok or not (name or "").strip():
            return
        name = name.strip()
        detail, ok2 = QInputDialog.getMultiLineText(
            self, "AI 一键生成情景卡",
            "细节方向（可选，控制这张卡的写法侧重；留空则 AI 按该类情景通用思路设计）：\n"
            "例：偏兵刃近身、狠辣致命、不留活口 / 大开大合、江湖切磋、点到即止 /\n"
            "高手过招、无声无息、一击定胜负",
            "")
        if not ok2:
            return
        detail = detail.strip()
        self.gen_btn.setEnabled(False)
        self.gen_btn.setText("生成中…")
        self._generating = True
        set_running(True)
        threading.Thread(target=self._card_ai_gen_worker,
                         args=(name, detail), daemon=True).start()

    def _card_ai_gen_worker(self, name, detail=""):
        try:
            import main_ai as _mai118
            content = _mai118.generate_scene_card(name, detail=detail)
            if not (content or "").strip():
                raise ValueError("AI 未返回有效内容")
            self._card_generated.emit(("ok", name, content))
        except Exception as e:
            self._card_generated.emit(("err", name, str(e)))

    # ---------- 从文本提取（v1.19） ----------
    def _card_extract(self):
        """根据用户提供的参考文本，提取某类型情景的规则卡草稿。"""
        name, ok = QInputDialog.getText(
            self, "从文本提取情景卡",
            "输入情景类型名（主AI据此按本章正文类型选用）：\n"
            "例：武打 / 文斗 / 见父母装傻充愣 / 情感对峙")
        if not ok or not (name or "").strip():
            return
        name = name.strip()
        sample, ok2 = QInputDialog.getMultiLineText(
            self, "从文本提取情景卡",
            "粘贴参考文本（你喜欢的一类情景的写法范例；AI 从中提炼可迁移的规则，"
            "不照抄原文）：",
            "")
        if not ok2 or not (sample or "").strip():
            return
        sample = sample.strip()
        self.gen_btn.setEnabled(False)
        self.gen_btn.setText("提取中…")
        self.extract_btn.setEnabled(False)
        self._generating = True
        set_running(True)
        threading.Thread(target=self._card_extract_worker,
                         args=(name, sample), daemon=True).start()

    def _card_extract_worker(self, name, sample):
        try:
            import main_ai as _mai119
            content = _mai119.extract_scene_card(name, sample)
            if not (content or "").strip():
                raise ValueError("AI 未返回有效内容")
            self._card_generated.emit(("ok", name, content))
        except Exception as e:
            self._card_generated.emit(("err", name, str(e)))

    def _on_card_generated(self, payload):
        self.gen_btn.setEnabled(True)
        self.gen_btn.setText("✨ AI 一键生成")
        self.extract_btn.setEnabled(True)
        self._generating = False
        set_running(False)
        if payload[0] != "ok":
            QMessageBox.warning(self, "生成失败",
                                "AI 生成情景卡失败：%s" % payload[2])
            return
        _, name, content = payload
        # 若类型名已存在，先切到该卡（覆盖式编辑由用户点保存）
        cards = self._cards()
        idx = -1
        for i, c in enumerate(cards):
            if str(c.get("name") or "").strip() == name:
                idx = i
                break
        if idx >= 0:
            self.card_list.setCurrentRow(idx)
        else:
            self._card_new()
            self.name_edit.setText(name)
        self.content_edit.setPlainText(content)
        QMessageBox.information(self, "生成完成",
                                "已按范例结构生成「%s」卡的规则草稿，请检查修改后点「保存当前卡」。"
                                % name)

    # ---------- 导入 / 导出 ----------
    def _import_txt(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入情景提示词 txt", "",
            "文本文件 (*.txt);;所有文件 (*.*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception as e:
            QMessageBox.warning(self, "导入失败", "读取文件失败：%s" % e)
            return
        import os as _os
        fname = _os.path.splitext(_os.path.basename(path))[0]
        cards = _parse_import(text, fallback_name=fname)
        if not cards:
            QMessageBox.warning(self, "导入失败", "文件里没有可导入的内容。")
            return
        cur = self._cards()
        names = {str(c.get("name") or "").strip() for c in cur}
        added = 0
        for c in cards:
            nm = c["name"]
            if nm in names:
                ret = QMessageBox.question(
                    self, "卡已存在",
                    "卡「%s」已存在，要覆盖它吗？（否=跳过）" % nm)
                if ret != QMessageBox.StandardButton.Yes:
                    continue
                for x in cur:
                    if str(x.get("name") or "").strip() == nm:
                        x["content"] = c["content"]
                        break
            else:
                cur.append(c)
                names.add(nm)
            added += 1
        self._persist(cur)
        QMessageBox.information(self, "导入完成", "成功导入/覆盖 %d 张卡（库内共 %d 张）。"
                                 % (added, len(cur)))

    def _import_batch(self):
        """v1.30 批量导入：多选 txt（汇总文件 /「_细分」文件夹里的单卡文件都行），
        逐文件解析合并进总库；同名自动跳过（不逐个弹窗打断，不覆盖已有卡）。"""
        import os as _os
        paths, _ = QFileDialog.getOpenFileNames(
            self, "批量导入情景卡（多选 txt；支持汇总文件与「_细分」单卡文件）", "",
            "文本文件 (*.txt);;所有文件 (*.*)")
        if not paths:
            return
        cards = []
        for p in paths:
            try:
                with open(p, "r", encoding="utf-8") as f:
                    text = f.read()
            except Exception as e:
                QMessageBox.warning(self, "读取失败",
                                    "无法读取 %s：%s" % (_os.path.basename(p), e))
                continue
            fname = _os.path.splitext(_os.path.basename(p))[0]
            cards.extend(_parse_import(text, fallback_name=fname))
        if not cards:
            QMessageBox.warning(self, "导入失败", "选择的文件里没有可导入的内容。")
            return
        cur = self._cards()
        names = {str(c.get("name") or "").strip() for c in cur}
        added = 0
        for c in cards:
            nm = str(c.get("name") or "").strip()
            if not nm or nm in names:
                continue  # 批量导入同名自动跳过
            cur.append(c)
            names.add(nm)
            added += 1
        self._persist(cur)
        log_fn("info", "批量导入情景卡 %d 张（同名跳过 %d 张）。"
               % (added, len(cards) - added))
        QMessageBox.information(
            self, "导入完成",
            "成功导入 %d 张情景卡（同名自动跳过 %d 张，不覆盖已有卡），库内共 %d 张。"
            % (added, len(cards) - added, len(cur)))

    def _export_one(self):
        name = self.name_edit.text().strip() or self._current or "未命名"
        content = self.content_edit.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "提示", "当前卡内容为空，没有可导出的。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出当前卡", "%s.txt" % name, "文本文件 (*.txt)")
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            QMessageBox.warning(self, "导出失败", "%s" % e)
            return
        QMessageBox.information(self, "导出完成", "已导出到：\n%s" % path)

    def _export_batch(self):
        """v1.30 批量导出：选一个文件夹 → ① 汇总 txt（每卡【卡名】分隔，可整批再导入）
        + ②「_细分」子文件夹每张卡一个文件（文件名带分类前缀）——下次只想导入其中
        一张，直接选细分文件夹里那个文件即可。"""
        import os as _os
        import datetime as _dt
        cards = [c for c in self._cards() if str(c.get("content") or "").strip()]
        if not cards:
            QMessageBox.warning(self, "提示", "卡库为空，没有可导出的。")
            return
        directory = QFileDialog.getExistingDirectory(
            self, "选择导出文件夹（将生成汇总 txt + _细分 子文件夹）", "")
        if not directory:
            return
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        base = _os.path.join(directory, "星火笔情景卡_导出_%s" % stamp)
        try:
            with open(base + ".txt", "w", encoding="utf-8") as f:
                f.write(_export_text(cards))
            sub = base + "_细分"
            _os.makedirs(sub, exist_ok=True)
            for c in cards:
                nm = str(c.get("name") or "").strip() or "未命名"
                cat = str(c.get("category") or "").strip()
                fname = ("[%s]%s.txt" % (cat, nm) if cat else "%s.txt" % nm)
                # v1.31 细分文件内容带【分类】行（与汇总一致）：直接导入该文件分类也不丢
                body = str(c.get("content") or "").strip()
                if cat:
                    body = "【分类】%s\n%s" % (cat, body)
                with open(_os.path.join(sub, _file_safe(fname)),
                          "w", encoding="utf-8") as f:
                    f.write(body)
        except Exception as e:
            QMessageBox.warning(self, "导出失败", "%s" % e)
            return
        log_fn("info", "批量导出情景卡 %d 张（汇总 txt + 细分文件夹）。" % len(cards))
        QMessageBox.information(
            self, "导出完成",
            "已批量导出 %d 张卡：\n"
            "① 汇总：%s.txt（每卡以【卡名】分隔，可整批再导入）\n"
            "② 细分文件夹：%s\\\n"
            "　每张卡一个文件（文件名带分类前缀，如 [武打]夜战夺镖.txt）——"
            "下次只想导入其中一张，直接选那个文件导入即可。"
            % (len(cards), base, sub))
