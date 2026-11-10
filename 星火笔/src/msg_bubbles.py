# -*- coding: utf-8 -*-
"""对话页消息气泡渲染（v0.96 新增头像框 + 左右对齐 + 气泡）。

此前两页用 QTextBrowser 的 HTML 画气泡（div + display:inline-block 的 span）——
Qt 富文本（QTextDocument）不支持 inline-block，背景/边框/圆角全部不生效，
用户看到的就是左右两段裸文字，且容易误判为全部右对齐。

改为真实控件：头像框 QLabel + 气泡 QLabel（wordWrap、鼠标可选中复制、
PlainText 直显不解析 HTML）。user 靠右（气泡+头像在右），assistant 靠左（头像+气泡在左）。
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget)
from gui_theme import T

AVATAR_SIZE = 34          # 头像框直径（px）

# 气泡样式：user 暖棕（输入），assistant 冷蓝（AI 输出）
_USER_BUBBLE_QSS = ("background:#2b2415;border:1px solid #463a1d;"
                    "border-radius:10px;padding:8px 12px;color:#e8e4d8;font-size:13px;")
_AI_BUBBLE_QSS = ("background:#1a222e;border:1px solid #29384f;"
                  "border-radius:10px;padding:8px 12px;color:#d8dde5;font-size:13px;")
# v1.43 思考气泡：深灰紫（区别于正文蓝），标题按钮可折叠
_THINK_BUBBLE_QSS = ("background:#171a26;border:1px solid #2d2a45;"
                     "border-radius:10px;padding:8px 12px;color:#b9a8d8;font-size:13px;")
_THINK_TITLE_QSS = ("background:transparent;border:none;color:#8f7fc9;"
                    "font-size:12px;font-weight:bold;padding:2px 0;")

# 头像框样式：圆形 + 描边，user 金、assistant 蓝
_USER_AVATAR_QSS = ("background:#4a3a16;border:1px solid #a8842c;color:#f0d98c;"
                    "border-radius:%dpx;font-weight:bold;font-size:12px;" % (AVATAR_SIZE // 2))
_AI_AVATAR_QSS = ("background:#14324f;border:1px solid #2f6fae;color:#8ec9f5;"
                  "border-radius:%dpx;font-weight:bold;font-size:12px;" % (AVATAR_SIZE // 2))


class BubbleRow(QWidget):
    """一条消息行：头像框 + 气泡。user 靠右显示，assistant 靠左显示。"""

    def __init__(self, role, text=""):
        super().__init__()
        self._role = role
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(8)

        self.avatar = QLabel("我" if role == "user" else "AI")
        self.avatar.setFixedSize(AVATAR_SIZE, AVATAR_SIZE)
        self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.avatar.setStyleSheet(T(_USER_AVATAR_QSS if role == "user" else _AI_AVATAR_QSS))

        self.bubble = QLabel()
        self.bubble.setWordWrap(True)
        self.bubble.setTextFormat(Qt.TextFormat.PlainText)   # 直显原文，不解析富文本
        self.bubble.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)    # 鼠标可选中/复制
        self.bubble.setStyleSheet(T(_USER_BUBBLE_QSS if role == "user" else _AI_BUBBLE_QSS))
        self.bubble.setText(text)

        if role == "user":
            lay.addStretch(1)
            lay.addWidget(self.bubble)
            lay.addWidget(self.avatar)
        else:
            lay.addWidget(self.avatar)
            lay.addWidget(self.bubble)
            lay.addStretch(1)

    def append_text(self, piece):
        self.bubble.setText(self.bubble.text() + piece)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # 气泡宽度随容器收缩换行（留出头像 + 间距 + 边距）
        w = self.width() - AVATAR_SIZE - 8 - 48
        self.bubble.setMaximumWidth(max(200, int(w * 0.94)))


def clear_rows(layout):
    """清空消息容器里全部行（保留容器本身，调用方再补 addStretch）。"""
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()


class ThinkingBubble(QWidget):
    """思考过程气泡（v1.43）：标题按钮可折叠 + 内容区实时追加。

    AI 对话/Agent 流式输出时，若模型先输出推理思考（reasoning_content），
    用本组件独立展示（深灰紫，区别于正文蓝），标题「🧠 思考中…」点击可
    展开/收起——避免长篇思考占据整个对话空间；模型没有思考时根本不创建。
    """

    def __init__(self, text=""):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        lay.setSpacing(2)

        self.toggle_btn = QPushButton("🧠 思考中…")
        self.toggle_btn.setStyleSheet(T(_THINK_TITLE_QSS))
        self.toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.setChecked(True)
        self.toggle_btn.clicked.connect(self._on_toggle)

        self.bubble = QLabel()
        self.bubble.setWordWrap(True)
        self.bubble.setTextFormat(Qt.TextFormat.PlainText)
        self.bubble.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.bubble.setStyleSheet(T(_THINK_BUBBLE_QSS))
        self.bubble.setText(text)
        self.bubble.setMaximumWidth(900)

        lay.addWidget(self.toggle_btn)
        lay.addWidget(self.bubble)

    def append_text(self, piece):
        self.bubble.setText(self.bubble.text() + piece)

    def _on_toggle(self, checked):
        self.bubble.setVisible(checked)
        if checked:
            self.toggle_btn.setText("🧠 思考中…")
        else:
            self.toggle_btn.setText("🧠 思考（点击展开）")

    def finish(self):
        """思考结束（正文开始/请求完成）：自动收起，保留标题可点开回顾。"""
        if self.toggle_btn.isChecked():
            self.toggle_btn.setChecked(False)   # 触发 _on_toggle 收起
            self.toggle_btn.setText("🧠 思考（点击展开）")
