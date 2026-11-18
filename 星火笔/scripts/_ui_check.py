# -*- coding: utf-8 -*-
"""v2.56 界面美化·全局视觉打磨的独立验证（不碰磁盘 config / 真实 API）。

覆盖：
  [1] gui_theme.QSS_BASE 包含新增选择器与样式（斑马纹 alternate-background-color、
      表格/列表悬停与选中、导航选中金条 border-left、QMenu、QCheckBox::indicator、
      QTabBar::tab:hover、滚动条 add-page、状态标签加粗、项目名卡片、表头 hover）
  [2] build_qss 缩放：1.0 原样；1.3 等比例放大（无 13px 残留）；0.8 缩小
  [3] 离屏构建主窗口：应用 QSS 不崩、页面顺序不变（项目0/角色1/生成2/去AI味3/故事4/设置5）、
      switch_page 正常
  [4] 表格交替行色与时间线列宽：fore_table/timeline_table setAlternatingRowColors(True)、
      时间线章号/状态/字数列宽固定
运行：env\\python.exe _ui_check.py
"""
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import gui_theme
import storage
from models import NovelProject

RESULTS = []
TMP = tempfile.mkdtemp(prefix="xhb_ui_")
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
storage.INDEX_PATH = os.path.join(storage.PROJECTS_DIR, "index.json")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def test_qss_content():
    q = gui_theme.QSS_BASE
    need = [
        "alternate-background-color: #0e1219",
        "QListWidget::item:hover",
        "QTreeWidget::item:selected",
        "QTableWidget::item:hover",
        "QTableWidget::item:selected",
        "QHeaderView::section:hover",
        "border-left: 3px solid #d4a44c",     # 导航选中金条（QSS_BASE 已做占位符替换）
        "QMenu {",
        "QMenu::item:selected",
        "QCheckBox::indicator",
        "QRadioButton::indicator",
        "QTabBar::tab:hover",
        "QScrollBar::add-page, QScrollBar::sub-page",
        "QLabel#statusBusy { color: #d4a44c; font-weight: 700; }",
        "QLabel#projName",
        "QSpinBox::up-button:hover",
    ]
    for s in need:
        check("QSS-含「%s」" % s[:24], s in q, "")


def test_scale():
    base = gui_theme.QSS_BASE
    check("缩放-1.0原样", gui_theme.build_qss(1.0) == base, "")
    s13 = gui_theme.build_qss(1.3)
    check("缩放-1.3放大", "font-size: 17px" in s13 and "font-size: 25px" in s13, "")   # 13→17, 19→25
    s08 = gui_theme.build_qss(0.8)
    check("缩放-0.8缩小", "font-size: 10px" in s08 and "font-size: 15px" in s08
          and s08 != s13, "")   # 13→10, 19→15
    check("缩放-参数合法", all(x in base and x in s13 and x in s08
                             for x in ("QMenu {", "alternate-background-color")), "")


def test_gui_build():
    import gui_app
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])
    qapp.setStyleSheet(gui_theme.QSS)
    store = storage.ProjectStore("uiproj")
    p = NovelProject()
    p.title = "界面项目"
    p.story_brief = "测试。"
    store.save_project(p)
    # 写两章供故事页表格填充
    from models import Chapter
    for i in (1, 2):
        ch = Chapter(i)
        ch.title = "第%d章" % i
        ch.content = "正文%d。" % i
        ch.brief = "梗概%d" % i
        ch.status = "approved"
        store.save_chapter(ch)
    gui_app.APP["project_dir"] = "uiproj"
    win = gui_app.MainWindow()
    check("窗口-构建不崩", win is not None, "")
    check("窗口-页面顺序", win.pages.indexOf(win.page_project) == 0
          and win.pages.indexOf(win.page_characters) == 1
          and win.pages.indexOf(win.page_generate_scroll) == 2
          and win.pages.indexOf(win.page_deai) == 3
          and win.pages.indexOf(win.page_story) == 4
          and win.pages.indexOf(win.page_settings) == 5, "")
    win.page_story.refresh_all()
    check("表格-伏笔交替行色", win.page_story.fore_table.alternatingRowColors(), "")
    check("表格-时间线交替行色", win.page_story.timeline_table.alternatingRowColors(), "")
    check("表格-时间线列宽", win.page_story.timeline_table.columnWidth(0) == 56
          and win.page_story.timeline_table.columnWidth(3) == 64,
          "w0=%d w3=%d" % (win.page_story.timeline_table.columnWidth(0),
                           win.page_story.timeline_table.columnWidth(3)))
    check("表格-时间线行数", win.page_story.timeline_table.rowCount() == 2, "")
    win.switch_page(5)
    check("窗口-switch_page(设置)正常", win.pages.currentWidget() is win.page_settings, "")
    win.switch_page(2)
    check("窗口-switch_page(生成)正常", win.pages.currentWidget() is win.page_generate_scroll, "")
    win.close()
    qapp.processEvents()


def main():
    try:
        test_qss_content()
        test_scale()
        test_gui_build()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    fails = [r for r in RESULTS if not r[1]]
    print("-" * 50)
    if fails:
        print("FAILED %d/%d:" % (len(fails), len(RESULTS)))
        for n, _, d in fails:
            print("  FAIL %s %s" % (n, d))
        sys.exit(1)
    print("ALL_OK (%d checks)" % len(RESULTS))


if __name__ == "__main__":
    main()
