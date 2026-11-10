# -*- coding: utf-8 -*-
"""PySide6 应用框架：主窗口、左侧导航、全局状态与跨线程信号总线。"""
import threading

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMainWindow,
                               QPushButton, QScrollArea, QStackedWidget,
                               QVBoxLayout, QWidget)

import config
import storage
from gui_theme import BG, PANEL, build_qss

# ---------- 全局运行状态 ----------
VERSION = "v1.109"

APP = {
    "project_dir": None,
    "draft": None,          # 当前草稿 Chapter
    "draft_seq": 0,
    "running": False,       # 引擎是否在跑
    "stop": False,
    "stop_ev": None,        # v0.55 任务级停止事件（LLM 调用立即中断用；全自动开始时创建）
}


class Bus(QObject):
    """UI 与后台线程之间的信号桥（线程安全）。"""
    log = Signal(str, str)        # kind: info|warn|error|progress
    draft = Signal(object)        # Chapter | None
    running = Signal(bool)
    projectChanged = Signal()
    charactersChanged = Signal()  # 角色卡增删改（后台线程生成完角色后触发，角色页刷新）


bus = Bus()
_lock = threading.Lock()


def log_fn(kind, msg):
    """传给 NovelEngine 的日志回调。"""
    bus.log.emit(kind, str(msg))


def engine_for(project_dir):
    import engine as engine_mod
    store = storage.ProjectStore(project_dir)
    return engine_mod.NovelEngine(store, log_fn)


def current_project():
    if not APP["project_dir"]:
        return None, None
    store = storage.ProjectStore(APP["project_dir"])
    return store, store.load_project()


def set_draft(chapter):
    with _lock:
        APP["draft"] = chapter
        APP["draft_seq"] += 1
    bus.draft.emit(chapter)


def set_running(flag):
    APP["running"] = flag
    bus.running.emit(flag)


class _PageScroll(QScrollArea):
    """带 on_show 转发的内容滚动容器：页面切换时回调内部页面的 on_show。

    用于内容较高的页面（如生成页）：内容超高时滚动查看，控件保持完整尺寸不被压缩。
    """

    def __init__(self, page):
        super().__init__()
        self._inner = page
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidget(page)

    def on_show(self):
        self._inner.on_show()


def project_choices():
    return [(p["title"], p["dir"]) for p in storage.list_projects()]


def busy_guard(parent):
    """后台任务进行中时禁止再次触发新任务。"""
    if APP["running"]:
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(parent, "提示",
                            "有生成任务正在后台运行，请等它完成后再操作。\n"
                            "（遇到 API 报错时会按设置的重试次数与间隔自动重试，期间界面可正常查看/编辑。）")
        return False
    return True


# ---------- 主窗口 ----------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("星火笔 · AI小说写作室")
        self.resize(1440, 900)
        self.setMinimumSize(1120, 700)
        self._ui_scale = 1.0

        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 左侧导航 ----
        nav = QFrame()
        nav.setObjectName("nav")
        nav.setFixedWidth(208)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(14, 22, 14, 16)
        nav_layout.setSpacing(6)

        title = QLabel("星火笔")
        title.setObjectName("title")
        subtitle = QLabel("AI 小说写作室 · RP 自推理引擎")
        subtitle.setObjectName("subtitle")
        nav_layout.addWidget(title)
        nav_layout.addWidget(subtitle)
        nav_layout.addSpacing(18)

        self.proj_label = QLabel("未载入项目")
        self.proj_label.setObjectName("projName")
        self.proj_label.setWordWrap(True)
        nav_layout.addWidget(self.proj_label)
        nav_layout.addSpacing(12)

        self.pages = QStackedWidget()
        self.nav_buttons = []

        # v0.52 图标化导航：Bootstrap Icons（MIT）SVG，Qt 经 QtSvg 插件加载
        import os as _os
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QIcon
        _ICON_DIR = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
            "assets", "icons")

        def _nav_icon(name):
            p = _os.path.join(_ICON_DIR, name + ".svg")
            return QIcon(p) if _os.path.exists(p) else QIcon()

        def make_nav(text, page, icon=""):
            btn = QPushButton(text)
            btn.setObjectName("navBtn")
            if icon:
                btn.setIcon(_nav_icon(icon))
                btn.setIconSize(QSize(18, 18))
            btn.setCheckable(True)
            btn.clicked.connect(lambda _=False, b=btn, p=page: self._switch(page, b))
            nav_layout.addWidget(btn)
            self.nav_buttons.append(btn)
            return btn

        # 延迟导入避免循环
        from gui_project import ProjectPage
        from gui_characters import CharactersPage
        from gui_generate import GeneratePage
        from gui_story import StoryPage
        from gui_settings import SettingsPage
        from gui_deai import DeaiPage
        from gui_break import BreakPage
        from gui_style_extract import StyleExtractPage
        from gui_tutorial import TutorialPage
        from gui_chat import ChatPage
        from gui_write import WritePage
        from gui_scene_cards import SceneCardsPage

        self.page_project = ProjectPage(self)
        self.page_write = WritePage(self)
        self.page_characters = CharactersPage(self)
        self.page_generate = GeneratePage(self)
        self.page_deai = DeaiPage(self)
        self.page_style_extract = StyleExtractPage(self)
        self.page_story = StoryPage(self)
        self.page_settings = SettingsPage(self)
        self.page_break = BreakPage(self)
        self.page_tutorial = TutorialPage(self)
        self.page_chat = ChatPage(self)
        # v1.18 情景写作提示词功能页：全局卡库独立管理（不再藏在设置页）
        self.page_scene_cards = SceneCardsPage(self)
        sc_scroll = _PageScroll(self.page_scene_cards)
        self.page_scene_cards_scroll = sc_scroll

        # 生成页内容高（情节设置/主AI提示词/草稿/日志/正文编辑区等），包一层滚动容器，
        # 防止页面内容被窗口高度压缩导致输入栏挤在一起；超高时滚动查看
        gen_scroll = _PageScroll(self.page_generate)
        self.page_generate_scroll = gen_scroll

        # v0.64.1 文风校对/拆书工坊页内容同样高（输入/结果/多节点状态/设置/风格库），
        # 包滚动容器防输入栏被窗口高度压扁成一条线（同类问题，与生成页同一方案）
        se_scroll = _PageScroll(self.page_style_extract)
        self.page_style_extract_scroll = se_scroll
        br_scroll = _PageScroll(self.page_break)
        self.page_break_scroll = br_scroll

        nav_layout.addSpacing(10)
        make_nav("项　　目", self.page_project, "folder2-open")
        make_nav("码　　字", self.page_write, "pen")
        make_nav("角色管理", self.page_characters, "people")
        make_nav("小说生成", gen_scroll, "pencil")
        make_nav("去AI味", self.page_deai, "stars")
        make_nav("文风校对", se_scroll, "pencil-square")
        make_nav("拆书工坊", br_scroll, "journal-text")
        make_nav("AI 对话", self.page_chat, "chat-left-quote")
        make_nav("故事档案", self.page_story, "book")
        make_nav("设　　置", self.page_settings, "gear")
        make_nav("情景提示词", sc_scroll, "magic")
        make_nav("📖 教程", self.page_tutorial, "book")
        nav_layout.addStretch(1)

        self.status_label = QLabel("● 空闲")
        self.status_label.setObjectName("statusIdle")
        nav_layout.addWidget(self.status_label)

        self.ver_label = QLabel(VERSION)
        self.ver_label.setObjectName("verLabel")
        self.ver_label.setToolTip("软件版本（开发日志见 README）")
        nav_layout.addWidget(self.ver_label)

        self.zoom_label = QLabel("界面缩放 100%")
        self.zoom_label.setObjectName("zoomLabel")
        self.zoom_label.setToolTip("Ctrl + 鼠标滚轮 调整界面缩放（50%~160%，适配高DPI/横长界面）；点击恢复 100%")
        self.zoom_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.zoom_label.mousePressEvent = lambda _e: self._set_ui_scale(1.0)
        nav_layout.addWidget(self.zoom_label)

        # 页面顺序（switch_page 按此 index 切换）：项目0 码字1 角色2 生成3 去AI味4 文风校对5 拆书6
        # AI对话7 故事8 设置9 教程10 情景提示词11（v1.66 新增码字页插第二位，旧 index 整体 +1）
        for page in (self.page_project, self.page_write, self.page_characters):
            self.pages.addWidget(page)
        self.pages.addWidget(gen_scroll)   # 生成页滚动容器占原 index=3
        for page in (self.page_deai, se_scroll, br_scroll,
                     self.page_chat, self.page_story,
                     self.page_settings, self.page_tutorial, sc_scroll):
            self.pages.addWidget(page)

        root.addWidget(nav)
        root.addWidget(self.pages, 1)
        self.setCentralWidget(central)

        bus.running.connect(self._on_running)
        bus.projectChanged.connect(self._on_project_changed)

        if not APP["project_dir"]:
            projects = storage.list_projects()
            if projects:
                APP["project_dir"] = projects[0]["dir"]

        self.nav_buttons[0].setChecked(True)
        self._refresh_project_label()
        self.page_project.on_show()

    # ---------- 内部 ----------
    def _set_ui_scale(self, scale):
        """界面整体缩放：重设 app 级样式表（QSS 全部 px 尺寸等比缩放）。"""
        # v0.64 缩放下限 80%→50%：高 DPI（如 200% 显示缩放）下横长界面可再缩小看全
        scale = round(max(0.5, min(1.6, scale)), 2)
        if abs(scale - self._ui_scale) < 0.001:
            return
        self._ui_scale = scale
        from PySide6.QtWidgets import QApplication
        QApplication.instance().setStyleSheet(build_qss(scale))
        self.zoom_label.setText("界面缩放 %d%%" % int(scale * 100))

    def wheelEvent(self, event):
        """Ctrl + 滚轮 = 界面缩放；普通滚轮交给页面自身滚动。"""
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = event.angleDelta().y()
            if delta:
                self._set_ui_scale(self._ui_scale + (0.05 if delta > 0 else -0.05))
                event.accept()
                return
        super().wheelEvent(event)

    def _switch(self, page, btn):
        self.pages.setCurrentWidget(page)
        for b in self.nav_buttons:
            b.setChecked(b is btn)
        page.on_show()

    def _on_running(self, flag):
        if flag:
            self.status_label.setText("● 生成中…")
            self.status_label.setObjectName("statusBusy")
        else:
            self.status_label.setText("● 空闲")
            self.status_label.setObjectName("statusIdle")
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)

    def _on_project_changed(self):
        self._refresh_project_label()
        self.status_label.setText("项目已切换")

    def _refresh_project_label(self):
        _, project = current_project()
        self.proj_label.setText(project.title if project else "未载入项目")

    def select_project(self, dir_name):
        APP["project_dir"] = dir_name
        bus.projectChanged.emit()

    def switch_page(self, index):
        self.nav_buttons[index].setChecked(True)
        self._switch(self.pages.widget(index), self.nav_buttons[index])

    def refresh_project_label(self):
        self._refresh_project_label()


def run():
    import sys
    from PySide6.QtWidgets import QApplication
    app = QApplication(sys.argv)
    app.setApplicationName("星火笔")
    from gui_theme import DEFAULT_THEME, apply_theme, set_theme, theme_names
    _name = config.load_config().get("ui_theme")
    set_theme(_name if _name in theme_names() else DEFAULT_THEME)
    apply_theme(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())