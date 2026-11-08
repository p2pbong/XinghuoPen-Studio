# -*- coding: utf-8 -*-
"""AI 对话页（v0.91 从综合对话拆分后，本页为纯净对话页，参考 LM Studio / Cherry Studio）。

功能：①测试 API 调用效果（生效配置/模型/耗时/错误即测即见）；
      ②交流小说内容——勾选「读当前项目（不含正文）」注入设定，不勾选完全读不到项目；
      ③联网搜索（勾选后发送前搜 Bing/DDG 注入结果）；
      ④附件：文本文件（内容注入）与图片（路径/尺寸说明）随消息传入并留档；
      ⑤话题存储（data/chats/topics/）+ 文件夹分类 + 导出 md + 话题搜索；
      ⑥消息操作（LM Studio 式，作用于最后一条）：编辑/重生成/继续生成/删除。
线程：后台 threading.Thread（v0.79 冻结教训）；流式 on_chunk 打字机；停止 set_abort。
"""
import os
import threading
import time

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QFrame,
                               QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QListWidget, QMenu, QMessageBox, QPlainTextEdit,
                               QPushButton, QScrollArea, QSplitter, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

import chat_lib
import config
import llm
import web_search
from gui_app import current_project, set_running
from msg_bubbles import BubbleRow, ThinkingBubble, clear_rows
from gui_theme import T

_TEXT_EXT = {".txt", ".md", ".json", ".csv", ".py", ".js", ".html", ".css",
             ".log", ".ini", ".yaml", ".yml", ".xml", ".tsv"}
_IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
ATTACH_TEXT_LIMIT = 6000     # 文本附件注入上限
WEB_RESULTS = 5              # 联网搜索条数


class _ChatWorker(QObject):
    """后台对话线程（v0.91 仅对话/压缩/继续）。"""

    chunk = Signal(str)
    think = Signal(str)      # v1.43 推理思考分片（reasoning_content）
    done = Signal(object)      # {ok,text,elapsed,profile,model,error,stopped,kind}

    def __init__(self):
        super().__init__()
        self._stop = threading.Event()
        self._proc = None

    def stop(self):
        self._stop.set()
        # 立即停止：主动 close 在途流式请求连接（流式读取立刻抛 StopRequested），不再等当前回复生成完
        import llm as _llm_stop
        _llm_stop.abort_active_resps()

    def run_chat(self, messages, profile_name, kind="chat"):
        """kind: chat（追加 assistant）/ compress（压缩摘要）/ continue（续写追加）。"""
        import llm as _llm
        _llm.set_abort(self._stop)
        t0 = time.time()
        try:
            # v0.94 API 归设置页统一管理：对话走「用途分工·AI对话」行（role="chat" + think_role）
            text = _llm.chat(messages, role="chat", profile=None,
                             on_chunk=lambda c: self.chunk.emit(c),
                             on_think=lambda t: self.think.emit(t),
                             think_role="chat")
            prof = config.pick_profile("chat")
            self.done.emit({
                "ok": True, "text": text, "elapsed": time.time() - t0,
                "profile": (prof or {}).get("name", "?"),
                "model": (prof or {}).get("model", "?"),
                "error": None, "stopped": False, "kind": kind})
        except _llm.StopRequested:
            self.done.emit({
                "ok": False, "text": "", "elapsed": time.time() - t0,
                "profile": "AI对话", "model": "?",
                "error": "已停止", "stopped": True, "kind": kind})
        except Exception as e:
            self.done.emit({
                "ok": False, "text": "", "elapsed": time.time() - t0,
                "profile": "AI对话", "model": "?",
                "error": str(e), "stopped": False, "kind": kind})
        finally:
            _llm.set_abort(None)


class ChatPage(QWidget):
    """AI 对话页（index 6，纯净对话）。"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self._worker = None
        self._thread = None
        self._tid = None
        self._msgs = []
        self._running = False
        self._stream_row = None   # v0.96 流式输出中的气泡行
        self._attachments = []   # [{name, path, kind: text|image}]

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---------- 左：话题列表（LM Studio / Cherry Studio 式侧栏） ----------
        left = QWidget()
        left.setFixedWidth(280)
        llay = QVBoxLayout(left)
        llay.setContentsMargins(12, 12, 12, 12)
        llay.setSpacing(8)
        bar = QHBoxLayout()
        new_btn = QPushButton("➕ 新话题")
        new_btn.setObjectName("primary")
        new_btn.clicked.connect(self._new_topic)
        bar.addWidget(new_btn)
        folder_btn = QPushButton("📁 文件夹")
        folder_btn.clicked.connect(self._new_folder)
        bar.addWidget(folder_btn)
        llay.addLayout(bar)
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("🔍 搜索话题…")
        self.search_edit.textChanged.connect(lambda _t: self._refresh_tree(keep_selected=True))
        llay.addWidget(self.search_edit)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._tree_menu)
        self.tree.itemClicked.connect(self._tree_click)
        # v1.08 双击话题直接改名（文件夹双击无动作）
        self.tree.itemDoubleClicked.connect(self._tree_double)
        llay.addWidget(self.tree, 1)
        hint = QLabel("新建话题可直接起名；双击/右键话题可重命名、导出、移动、删除；单击打开。")
        hint.setStyleSheet(T("color:#5b6470;font-size:11px;"))
        hint.setWordWrap(True)
        llay.addWidget(hint)
        root.addWidget(left)

        # ---------- 右：对话区 ----------
        right = QWidget()
        rlay = QVBoxLayout(right)
        rlay.setContentsMargins(16, 12, 16, 12)
        rlay.setSpacing(8)
        head = QHBoxLayout()
        self.title_lbl = QLabel("未选择话题")
        self.title_lbl.setStyleSheet(T("font-size:16px;color:#d4a44c;font-weight:bold;"))
        head.addWidget(self.title_lbl)
        # v1.08 话题可命名：标题栏直接「重命名」按钮（新建时也会先弹命名框，双击/右键话题也可改名）
        self.rename_btn = QPushButton("✏️ 重命名")
        self.rename_btn.setToolTip("给当前话题改名字（新建话题时也会先让你起名；树中双击/右键话题同样可改）")
        self.rename_btn.setEnabled(False)
        self.rename_btn.clicked.connect(self._rename_current)
        head.addWidget(self.rename_btn)
        head.addSpacing(8)
        head.addWidget(QLabel("API"))
        self.cur_api_lbl = QLabel("（未指定）")
        self.cur_api_lbl.setToolTip("当前生效配置：设置页「用途分工·AI对话」行选择（含独立思考强度）；"
                                    "换配置请到设置页")
        head.addWidget(self.cur_api_lbl)
        head.addSpacing(10)
        self.ctx_chk = QCheckBox("读当前项目（不含正文）")
        self.ctx_chk.setToolTip(
            "勾选后把项目设定（故事设定/角色表/伏笔台账/知识库/设定锚点等，**不含章节正文**）"
            "注入对话上下文；不勾选 AI 完全读不到项目。")
        head.addWidget(self.ctx_chk)
        self.web_chk = QCheckBox("🌐 联网搜索")
        self.web_chk.setToolTip("发送前用 Bing/DDG 搜索问题关键词，把结果注入上下文（v0.91）")
        head.addWidget(self.web_chk)
        head.addStretch(1)
        rlay.addLayout(head)   # v0.95 头部拆行：第一行=标题/API/开关（200% 缩放下不再挤）

        # 第二行：导出/停止 + 消息操作（LM Studio 式，作用于最后一条）+ 上下文用量
        tools = QHBoxLayout()
        export_btn = QPushButton("📤 导出话题")
        export_btn.clicked.connect(self._export_topic)
        tools.addWidget(export_btn)
        self.stop_btn = QPushButton("⏹ 停止")
        self.stop_btn.setObjectName("danger")
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        tools.addWidget(self.stop_btn)
        tools.addSpacing(10)
        self.edit_btn = QPushButton("✏️ 编辑")
        self.edit_btn.setToolTip("编辑最后一条消息（用户输入或 AI 输出均可改；改用户消息后自动重新生成）")
        self.edit_btn.clicked.connect(self._edit_last)
        tools.addWidget(self.edit_btn)
        self.reg_btn = QPushButton("🔄 重生成")
        self.reg_btn.setToolTip("重新生成最后一条 AI 回复（删除该条，用其前一条用户消息重新请求）")
        self.reg_btn.clicked.connect(self._regenerate_last)
        tools.addWidget(self.reg_btn)
        self.cont_btn = QPushButton("▶ 继续")
        self.cont_btn.setToolTip("让 AI 从最后一条回复末尾继续写（不重复已有内容）")
        self.cont_btn.clicked.connect(self._continue_last)
        tools.addWidget(self.cont_btn)
        self.del_btn = QPushButton("🗑 删除")
        self.del_btn.setToolTip("删除最后一条消息")
        self.del_btn.clicked.connect(self._delete_last)
        tools.addWidget(self.del_btn)
        tools.addStretch(1)
        self.ctx_lbl = QLabel("")
        self.ctx_lbl.setStyleSheet(T("color:#7d8aa0;font-size:11px;"))
        self.ctx_lbl.setToolTip("发送给模型的上下文估算（含系统提示/项目设定/历史/摘要）；"
                                "窗口来自设置页「拉取模型」记录或手填")
        tools.addWidget(self.ctx_lbl)
        rlay.addLayout(tools)

        # v0.95 状态独立一行（长文本不再挤压 ctx 标签）
        self.status_lbl = QLabel("就绪。输入问题开始对话（可作 API 连通性测试）。")
        self.status_lbl.setStyleSheet(T("color:#8791a2;font-size:12px;"))
        self.status_lbl.setWordWrap(True)
        rlay.addWidget(self.status_lbl)

        # v0.96 消息区改为控件渲染（气泡 + 头像框 + 左右对齐），替代 QTextBrowser HTML
        self.msg_scroll = QScrollArea()
        self.msg_scroll.setWidgetResizable(True)
        self.msg_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.msg_list = QWidget()
        self.msg_vbox = QVBoxLayout(self.msg_list)
        self.msg_vbox.setContentsMargins(8, 8, 8, 8)
        self.msg_vbox.setSpacing(4)
        self.msg_scroll.setWidget(self.msg_list)
        rlay.addWidget(self.msg_scroll, 1)

        # 附件栏（v0.91 文件/图片传入）
        att_row = QHBoxLayout()
        att_row.addWidget(QLabel("📎 附件"))
        att_add_txt = QPushButton("➕ 文本文件")
        att_add_txt.setToolTip("选择文本/代码文件，发送时内容注入（≤6000 字）")
        att_add_txt.clicked.connect(lambda: self._add_attachment("text"))
        att_row.addWidget(att_add_txt)
        att_add_img = QPushButton("🖼 图片")
        att_add_img.setToolTip("选择图片，发送时以附件说明注入（模型支持视觉时可描述图片）")
        att_add_img.clicked.connect(lambda: self._add_attachment("image"))
        att_row.addWidget(att_add_img)
        att_del = QPushButton("✕ 移除选中")
        att_del.clicked.connect(self._del_attachment)
        att_row.addWidget(att_del)
        self.att_list = QListWidget()
        self.att_list.setFixedHeight(64)
        att_row.addWidget(self.att_list, 1)
        rlay.addLayout(att_row)

        inrow = QHBoxLayout()
        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText(
            "输入问题…（Enter 发送，Shift+Enter 换行；可先添加附件再发送）")
        self.input_edit.setMinimumHeight(72)
        self.input_edit.setMaximumHeight(140)
        inrow.addWidget(self.input_edit, 1)
        send_btn = QPushButton("🚀 发送")
        send_btn.setObjectName("primary")
        send_btn.clicked.connect(self._send)
        inrow.addWidget(send_btn)
        rlay.addLayout(inrow)
        root.addWidget(right, 1)

        self._tid = None
        self._last_sys_len = 120   # 固定系统提示长度估算（字符）

    # ---------- 生命周期 ----------
    def on_show(self):
        self._refresh_cur_api()
        self._refresh_tree(keep_selected=True)
        if not self._tid:
            self._new_topic(prompt=False)   # v1.08 自动兜底创建不弹命名框
        self._update_ctx()

    def _refresh_cur_api(self):
        """v0.94 API 归设置页统一管理：只读显示对话用途行生效的配置。"""
        try:
            prof = config.pick_profile("chat")
            self.cur_api_lbl.setText(
                "%s（%s）" % ((prof or {}).get("name", "?"),
                              (prof or {}).get("model", "?")))
        except Exception:
            self.cur_api_lbl.setText("（未指定）")

    # ---------- 话题树 ----------
    def _refresh_tree(self, keep_selected=False):
        cur_tid = self._tid if keep_selected else None
        kw = (self.search_edit.text() or "").strip().lower()
        self.tree.blockSignals(True)
        self.tree.clear()
        topics = chat_lib.list_topics()
        folders = chat_lib.list_folders()
        roots = [("未分类", "")]
        for f in folders:
            roots.append((f["name"], f["id"]))
        for fname, fid in roots:
            item = QTreeWidgetItem([fname])
            item.setData(0, Qt.ItemDataRole.UserRole, ("folder", fid))
            self.tree.addTopLevelItem(item)
            for t in topics:
                if t["folder"] != fid:
                    continue
                if kw and kw not in (t["title"] or "").lower():
                    continue
                ti = QTreeWidgetItem(["%s　（%d）" % (t["title"], t["msg_count"])])
                ti.setData(0, Qt.ItemDataRole.UserRole, ("topic", t["id"]))
                if t["id"] == cur_tid:
                    self.tree.setCurrentItem(ti)
                item.addChild(ti)
        self.tree.expandAll()
        self.tree.blockSignals(False)

    def _tree_click(self, item, _col):
        kind, val = item.data(0, Qt.ItemDataRole.UserRole)
        if kind == "topic":
            self._open_topic(val)

    def _tree_double(self, item, _col):
        """v1.08 双击话题直接重命名（文件夹无动作）。"""
        kind, val = item.data(0, Qt.ItemDataRole.UserRole)
        if kind == "topic":
            self._rename_topic(val)

    def _open_topic(self, tid):
        t = chat_lib.load_topic(tid)
        if not t:
            return
        self._tid = tid
        self._msgs = [dict(m) for m in (t.get("messages") or [])]
        self.title_lbl.setText(t.get("title") or "未命名")
        self.rename_btn.setEnabled(True)
        self._render_all()
        self.status_lbl.setText("话题「%s」· 共 %d 条消息。" % (t.get("title"), len(self._msgs)))

    def _tree_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        kind, val = item.data(0, Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        if kind == "topic":
            menu.addAction("重命名", lambda: self._rename_topic(val))
            menu.addAction("导出为 md", lambda: self._export_topic(tid=val))
            sub = menu.addMenu("移动到文件夹")
            sub.addAction("未分类", lambda: self._move_topic(val, ""))
            for f in chat_lib.list_folders():
                sub.addAction(f["name"], lambda fid=f["id"]: self._move_topic(val, fid))
            menu.addSeparator()
            menu.addAction("删除话题", lambda: self._delete_topic(val))
        elif kind == "folder" and val:
            menu.addAction("重命名文件夹", lambda: self._rename_folder(val))
            menu.addAction("删除文件夹（话题移回未分类）", lambda: self._delete_folder(val))
        elif kind == "folder" and not val:
            menu.addAction("新建文件夹", self._new_folder)
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _new_topic(self, prompt=True):
        # v1.08 新建话题可直接起名：按钮触发时先弹命名框（默认名可改）；
        # on_show/发送等自动兜底创建传 prompt=False（直接用默认名，不打扰）
        default_name = "新话题 %d" % (len(chat_lib.list_topics()) + 1)
        title = default_name
        if prompt:
            name, ok = QInputDialog.getText(self, "新建话题", "话题名称：", text=default_name)
            if ok and (name or "").strip():
                title = name.strip()
        tid = chat_lib.create_topic(title)
        self._tid = tid
        self._msgs = []
        self._attachments = []
        self.title_lbl.setText(title)
        self.rename_btn.setEnabled(True)
        clear_rows(self.msg_vbox)
        self.msg_vbox.addStretch(1)
        self.att_list.clear()
        self.status_lbl.setText("新话题已创建。")
        self._update_ctx()
        self._refresh_tree()
        self.input_edit.setFocus()

    def _rename_current(self):
        """标题栏「重命名」按钮：改当前话题名。"""
        if not self._tid:
            return
        self._rename_topic(self._tid)

    def _rename_topic(self, tid):
        t = chat_lib.load_topic(tid)
        if not t:
            return
        name, ok = QInputDialog.getText(self, "重命名话题", "名称：", text=t.get("title", ""))
        if ok and name.strip():
            chat_lib.rename_topic(tid, name.strip())
            if tid == self._tid:
                self.title_lbl.setText(name.strip())
            self._refresh_tree(keep_selected=True)

    def _move_topic(self, tid, folder):
        chat_lib.move_topic(tid, folder)
        self._refresh_tree(keep_selected=True)

    def _delete_topic(self, tid):
        if QMessageBox.question(self, "删除话题", "删除该话题及其全部消息？") \
                != QMessageBox.StandardButton.Yes:
            return
        chat_lib.delete_topic(tid)
        if tid == self._tid:
            self._tid = None
            self._msgs = []
            self.title_lbl.setText("未选择话题")
            clear_rows(self.msg_vbox)
            self.msg_vbox.addStretch(1)
        self._refresh_tree()

    def _new_folder(self):
        name, ok = QInputDialog.getText(self, "新建文件夹", "文件夹名称：")
        if ok and name.strip():
            chat_lib.create_folder(name.strip())
            self._refresh_tree(keep_selected=True)

    def _rename_folder(self, fid):
        for f in chat_lib.list_folders():
            if f["id"] == fid:
                name, ok = QInputDialog.getText(self, "重命名文件夹", "名称：", text=f["name"])
                if ok and name.strip():
                    chat_lib.rename_folder(fid, name.strip())
                    self._refresh_tree(keep_selected=True)
                return

    def _delete_folder(self, fid):
        if QMessageBox.question(self, "删除文件夹",
                                "删除该文件夹？其中话题会移回「未分类」（不删话题）。") \
                != QMessageBox.StandardButton.Yes:
            return
        chat_lib.delete_folder(fid)
        self._refresh_tree(keep_selected=True)

    def _export_topic(self, tid=None):
        tid = tid or self._tid
        if not tid or not chat_lib.load_topic(tid):
            QMessageBox.warning(self, "提示", "没有可导出的话题。")
            return
        default = "星火笔-对话-%s-%s.md" % (
            time.strftime("%Y%m%d_%H%M%S"),
            (chat_lib.load_topic(tid).get("title") or "话题").strip())
        path, _ = QFileDialog.getSaveFileName(self, "导出话题", default,
                                              "Markdown (*.md);;文本 (*.txt)")
        if not path:
            return
        if chat_lib.export_topic_md(tid, path):
            QMessageBox.information(self, "导出成功", "已导出到：\n%s" % path)
        else:
            QMessageBox.warning(self, "导出失败", "话题不存在或写入失败。")

    # ---------- 附件（v0.91 文件/图片传入） ----------
    def _add_attachment(self, kind):
        if kind == "image":
            path, _ = QFileDialog.getOpenFileName(self, "选择图片", "",
                                                  "图片 (*.png *.jpg *.jpeg *.gif *.bmp *.webp)")
            ext = os.path.splitext(path)[1].lower() if path else ""
            if path and ext in _IMG_EXT:
                self._attachments.append({"name": os.path.basename(path), "path": path,
                                          "kind": "image"})
        else:
            path, _ = QFileDialog.getOpenFileName(self, "选择文本/代码文件", "",
                                                  "文本/代码 (*.txt *.md *.json *.csv *.py *.js *.html *.css *.log)")
            ext = os.path.splitext(path)[1].lower() if path else ""
            if path and ext in _TEXT_EXT:
                self._attachments.append({"name": os.path.basename(path), "path": path,
                                          "kind": "text"})
        self._refresh_attachments()

    def _refresh_attachments(self):
        self.att_list.clear()
        for a in self._attachments:
            self.att_list.addItem("%s [%s]" % (a["name"], "图片" if a["kind"] == "image" else "文本"))

    def _del_attachment(self):
        row = self.att_list.currentRow()
        if row < 0:
            return
        self._attachments.pop(row)
        self._refresh_attachments()

    def _attachments_to_text(self):
        """把附件转成注入文本；图片以说明形式（模型支持视觉时可读图，否则至少可见文件名）。"""
        if not self._attachments:
            return ""
        parts = []
        for a in self._attachments:
            if a["kind"] == "image":
                parts.append("[图片附件：%s（%s）]" % (a["name"], a["path"]))
            else:
                try:
                    with open(a["path"], "r", encoding="utf-8", errors="replace") as f:
                        content = f.read(ATTACH_TEXT_LIMIT)
                    parts.append("【附件文件：%s】\n%s" % (a["name"], content))
                except Exception as e:
                    parts.append("【附件文件：%s】（读取失败：%s）" % (a["name"], e))
        return "\n\n".join(parts)

    # ---------- 渲染（v0.96 气泡 + 头像框 + 左右对齐） ----------
    def _scroll_bottom(self):
        sb = self.msg_scroll.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _render_all(self):
        clear_rows(self.msg_vbox)
        for m in self._msgs:
            role = "user" if m.get("role") == "user" else "assistant"
            body = str(m.get("content", ""))
            att = m.get("attachments") or []
            if att:
                att_line = "\n".join("📎 %s" % str(a.get("name", "")) for a in att[:6])
                body = att_line + "\n\n" + body if body else att_line
            # v1.47 思考内容持久化：assistant 消息带 think 时，先渲染可折叠思考气泡
            # （重绘/重启后仍可展开回顾，不再随流式结束消失）
            if role == "assistant" and m.get("think"):
                tb = ThinkingBubble(str(m["think"]))
                tb.finish()     # 渲染为折叠态（点标题展开看完整思考）
                self.msg_vbox.addWidget(tb)
            self.msg_vbox.addWidget(BubbleRow(role, body))
        self.msg_vbox.addStretch(1)
        self._scroll_bottom()
        self._update_ctx()

    def _begin_stream(self):
        """请求开始时插入一个空的 AI 气泡行，流式文字实时写入。"""
        row = BubbleRow("assistant", "")
        self.msg_vbox.insertWidget(self.msg_vbox.count() - 1, row)
        self._stream_row = row
        self._think_row = None   # v1.43 流式思考气泡（推理模型思考分片独立展示，可折叠）
        self._think_text = ""    # v1.47 本次思考全文（完成时随消息落库，重绘可回顾）
        self._body_started = False
        self._scroll_bottom()

    def _stream_piece(self, piece):
        if self._stream_row is not None:
            self._stream_row.append_text(piece)
            self._scroll_bottom()

    def _on_think(self, piece):
        """v1.43 推理思考分片：在正文气泡前插入可折叠思考气泡并实时写入。

        模型没有思考（reasoning_content 从未出现）时永远不回调 → 不创建思考气泡，
        直接走正文气泡——「模型没思考就直接显示输出内容」。
        """
        if self._stream_row is None:
            return
        if self._think_row is None:
            tb = ThinkingBubble("")
            # 插在正文气泡之前（正文气泡位于 stretch 前一个）
            self.msg_vbox.insertWidget(max(0, self.msg_vbox.count() - 2), tb)
            self._think_row = tb
        self._think_row.append_text(piece)
        self._think_text += piece   # v1.47 累积全文，完成时随消息落库（重绘可回顾）
        self._scroll_bottom()

    def _stream_finish(self):
        """流式结束/正文开始时：折叠思考气泡（保留标题可点开回顾）。"""
        if self._think_row is not None:
            self._think_row.finish()

    # ---------- v0.93 上下文用量显示 ----------
    def _update_ctx(self):
        win = chat_lib.context_window(role="chat")
        chars = self._last_sys_len
        summary = ""
        t = chat_lib.load_topic(self._tid)
        if t:
            summary = t.get("summary") or ""
        for m in self._msgs:
            chars += len(str(m.get("content") or ""))
        est = chat_lib.estimate_tokens(chars)
        if summary:
            est += chat_lib.estimate_tokens(summary)
        def _fmt(n):
            if n >= 1000000:
                return "%.1fM" % (n / 1000000)
            if n >= 1000:
                return "%.1fK" % (n / 1000)
            return str(int(n))
        if win <= 0:
            self.ctx_lbl.setText("上下文 ≈ %s token（窗口未记录，设置页「拉取模型」后显示比例）" % _fmt(est))
        else:
            ratio = est * 100.0 / win
            self.ctx_lbl.setText("上下文 ≈ %s / %s（%.1f%%）" % (_fmt(est), _fmt(win), ratio))

    # ---------- 发送 / 停止 ----------
    def _send(self):
        if self._running:
            return
        text = self.input_edit.toPlainText().strip()
        if not text:
            return
        self.input_edit.clear()
        self._send_text(text, append_user=True)

    def _send_text(self, text, append_user=True):
        if self._running:
            return
        if not self._tid:
            self._new_topic(prompt=False)   # v1.08 发送时自动兜底创建不弹命名框（避免打断输入）
        tid = self._tid

        # 附件注入 + 留档
        att_text = self._attachments_to_text()
        att_meta = [dict(a) for a in self._attachments]
        if att_text:
            text = text + "\n\n" + att_text
        if append_user:
            chat_lib.append_message(tid, "user", text)
            t = chat_lib.load_topic(tid)
            if att_meta:
                t["messages"][-1]["attachments"] = att_meta
                chat_lib.save_topic(t)
            self._msgs = [dict(m) for m in (chat_lib.load_topic(tid).get("messages") or [])]
            self._attachments = []
            self._refresh_attachments()
            self._render_all()

        self._running = True
        self._streaming = False
        self.stop_btn.setEnabled(True)
        self.status_lbl.setText("⏳ 正在请求…（测试 API：查看下方生效配置/耗时）")
        set_running(True)

        system = ("你是星火笔内嵌的 AI 对话助手。当前会话用于测试 API 调用效果与交流小说内容。"
                  "回答用中文，简洁准确。")
        if self.ctx_chk.isChecked():
            store, project = current_project()
            ctx = chat_lib.build_project_context(store, project)
            if ctx:
                system += "\n\n以下是当前项目设定参考（不含正文）：\n" + ctx
        if self.web_chk.isChecked():
            hits = web_search.search(text[:120], max_results=WEB_RESULTS)
            if hits:
                lines = ["%d. %s（%s）\n%s" % (i + 1, h.get("title", ""),
                                               h.get("url", ""), h.get("snippet", ""))
                         for i, h in enumerate(hits)]
                system += "\n\n【联网搜索结果（仅供参考，引用需注明来源）】\n" + "\n".join(lines)
        self._last_sys_len = len(system)
        t = chat_lib.load_topic(tid)
        if (t or {}).get("summary"):
            system += "\n\n【此前对话摘要（已压缩，回答相关问题时参考）】\n" + t["summary"]
        history = chat_lib.recent_messages(tid)
        messages = [{"role": "system", "content": system}] + [
            {"role": m.get("role"), "content": m.get("content")}
            for m in history]

        self._worker = _ChatWorker()
        self._worker.chunk.connect(self._on_chunk)
        self._worker.think.connect(self._on_think)
        self._worker.done.connect(self._on_done)
        self._begin_stream()
        self._thread = threading.Thread(
            target=self._worker.run_chat,
            args=(messages, None, "chat"), daemon=True)
        self._thread.start()

    def _stop(self):
        if self._worker is not None:
            self._worker.stop()
            self.stop_btn.setEnabled(False)
            self.status_lbl.setText("⏹ 正在停止…")

    # ---------- v0.90 消息操作（LM Studio 式，作用于最后一条） ----------
    def _edit_last(self):
        if self._running or not self._msgs:
            return
        last = self._msgs[-1]
        cur = str(last.get("content", ""))
        new, ok = QInputDialog.getMultiLineText(
            self, "编辑最后一条消息", "修改内容（编辑用户消息后自动重新生成回复）：", cur)
        if not ok or new.strip() == cur.strip():
            return
        new = new.strip()
        last["content"] = new
        chat_lib.update_last_message(self._tid, new)
        self._render_all()
        if last.get("role") == "user":
            self._send_text(new, append_user=False)
        else:
            self.status_lbl.setText("已编辑 AI 回复文本（如需重写，点「🔄 重生成」）。")

    def _regenerate_last(self):
        if self._running or not self._tid or not self._msgs:
            return
        last = self._msgs[-1]
        if last.get("role") == "user":
            self._send_text(last.get("content", ""), append_user=False)
            return
        chat_lib.pop_last_messages(self._tid, 1)
        self._msgs.pop()
        self._render_all()
        if self._msgs and self._msgs[-1].get("role") == "user":
            self._send_text(self._msgs[-1].get("content", ""), append_user=False)
        else:
            self.status_lbl.setText("没有用户消息可用于重新生成。")

    def _continue_last(self):
        if self._running or not self._tid or not self._msgs:
            return
        if self._msgs[-1].get("role") != "assistant":
            self.status_lbl.setText("最后一条不是 AI 回复，无法继续生成。")
            return
        tid = self._tid
        system = ("你是星火笔内嵌的 AI 对话助手。请从用户给出的最后一段内容末尾继续往下写，"
                  "不要重复已有内容，直接续写。回答用中文。")
        if self.ctx_chk.isChecked():
            store, project = current_project()
            ctx = chat_lib.build_project_context(store, project)
            if ctx:
                system += "\n\n项目设定参考（不含正文）：\n" + ctx
        self._last_sys_len = len(system)
        t = chat_lib.load_topic(tid)
        if (t or {}).get("summary"):
            system += "\n\n【此前对话摘要】\n" + t["summary"]
        history = chat_lib.recent_messages(tid)
        messages = [{"role": "system", "content": system}] + [
            {"role": m.get("role"), "content": m.get("content")} for m in history]
        messages.append({"role": "user",
                         "content": "请从上面最后一条 AI 回复的末尾继续写（不重复已有内容，直接续写）。"})
        self._running = True
        self._streaming = False
        self.stop_btn.setEnabled(True)
        self.status_lbl.setText("⏳ 正在继续生成…")
        set_running(True)
        self._worker = _ChatWorker()
        self._worker.chunk.connect(self._on_chunk)
        self._worker.think.connect(self._on_think)
        self._worker.done.connect(self._on_done)
        self._begin_stream()
        self._thread = threading.Thread(
            target=self._worker.run_chat,
            args=(messages, None, "continue"), daemon=True)
        self._thread.start()

    def _delete_last(self):
        if self._running or not self._tid or not self._msgs:
            return
        chat_lib.pop_last_messages(self._tid, 1)
        self._msgs.pop()
        self._render_all()
        self.status_lbl.setText("已删除最后一条消息（剩 %d 条）。" % len(self._msgs))

    def _on_chunk(self, piece):
        self._streaming = True
        if not self._body_started:
            self._body_started = True
            self._stream_finish()   # 正文开始：折叠思考气泡（保留标题可点开回顾）
        self._stream_piece(piece)

    def _on_done(self, result):
        ok = result.get("ok")
        text = result.get("text") or ""
        elapsed = result.get("elapsed", 0)
        prof = result.get("profile") or "?"
        model = result.get("model") or "?"
        err = result.get("error")
        stopped = result.get("stopped")
        kind = result.get("kind", "chat")

        if kind == "continue":
            if ok and text.strip():
                if self._msgs:
                    self._msgs[-1]["content"] += text
                    # v1.47 续写思考：追加到既有 think（若有）
                    if self._think_text:
                        self._msgs[-1]["think"] = (self._msgs[-1].get("think") or "") + self._think_text
                if self._tid:
                    chat_lib.append_to_last_message(self._tid, text,
                                                    think=self._think_text or None)
                self._render_all()
                self.status_lbl.setText(
                    "✅ 已续写 %d 字 · 配置：%s（%s）· 耗时 %.1fs" % (len(text), prof, model, elapsed))
            else:
                self.status_lbl.setText(
                    "❌ %s%s · 配置：%s（%s）· 耗时 %.1fs"
                    % ("已停止" if stopped else "续写失败：", err if not stopped else "",
                       prof, model, elapsed))
        elif ok and text.strip():
            think = self._think_text or None   # v1.47 思考内容随消息落库（重绘可回顾）
            if self._tid:
                chat_lib.append_message(self._tid, "assistant", text, think=think)
            self._msgs.append({"role": "assistant", "content": text, "think": think})
            self._render_all()
            self.status_lbl.setText(
                "✅ 完成 · 配置：%s（%s）· 耗时 %.1fs · %d 字。"
                % (prof, model, elapsed, len(text)))
        elif err:
            self.status_lbl.setText(
                "❌ %s%s · 配置：%s（%s）· 耗时 %.1fs"
                % ("已停止" if stopped else "失败：", err if not stopped else "",
                   prof, model, elapsed))
        self._running = False
        self._streaming = False
        self._stream_finish()      # v1.43 完成时折叠思考气泡（保留标题可点开回顾）
        self._stream_row = None    # 流式气泡已由 _render_all 重建
        self.stop_btn.setEnabled(False)
        set_running(False)
        self._refresh_tree(keep_selected=True)
