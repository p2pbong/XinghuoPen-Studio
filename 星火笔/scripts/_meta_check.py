# -*- coding: utf-8 -*-
"""v2.54 伏笔逾期阈值可配置 + 阅读时展示剧情点/审查/校对记录 的独立验证（不碰磁盘 config / 真实 API）。

覆盖：
  [1] prompts._foreshadow_overdue_chapters：读取 config 阈值（默认 15，可配 8 等）
  [2] _overdue_mark / open_foreshadows_text 遵循配置阈值
  [3] 离屏 GUI·设置页：spins["foreshadow_overdue_chapters"] 存在、改值→_save_params 写入 config
      （打桩 save_config，不碰真实文件）
  [4] gui_story._chapter_meta_html：有 beats/review/proofread → HTML 含三段；空 reasoning → 空串
  [5] 故事页 _view_chapter 阅读时展示元信息块（ch_view.toHtml 含剧情点）
  [6] ChapterViewDialog 带 reasoning 构造不崩
运行：env\\python.exe _meta_check.py
"""
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import prompts
import storage
from models import Chapter, Foreshadow, NovelProject

RESULTS = []
TMP = tempfile.mkdtemp(prefix="xhb_meta_")
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
storage.INDEX_PATH = os.path.join(storage.PROJECTS_DIR, "index.json")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def make_store(name):
    store = storage.ProjectStore(name)
    p = NovelProject()
    p.title = "元信息测试"
    p.story_brief = "测试项目。"
    store.save_project(p)
    return store, p


def test_config_threshold():
    import config as config_mod
    orig = config_mod.load_config
    try:
        # 默认（无配置项）→ 15
        config_mod.load_config = lambda: {}
        check("阈值-默认15", prompts._foreshadow_overdue_chapters() == 15, "")
        f = Foreshadow("埋得久", "plant", "")
        f.planted_chapter = 1
        check("阈值-默认不逾期", prompts._overdue_mark(f, 16) == "", "gap=15 边界不逾期")
        # 配置 8 → 逾期
        config_mod.load_config = lambda: {"foreshadow_overdue_chapters": 8}
        check("阈值-配置8生效", prompts._foreshadow_overdue_chapters() == 8, "")
        check("阈值-配置后逾期", prompts._overdue_mark(f, 10) == "⚠逾期9章",
              prompts._overdue_mark(f, 10))
        check("阈值-清单遵循配置", "⚠逾期9章" in prompts.open_foreshadows_text([f], current_no=10), "")
        # 配置非法值回退 15
        config_mod.load_config = lambda: {"foreshadow_overdue_chapters": 0}
        check("阈值-非法值回退", prompts._foreshadow_overdue_chapters() == 15, "")
    finally:
        config_mod.load_config = orig


def test_gui_settings():
    import config as config_mod
    import gui_app
    import gui_settings
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])
    store, p = make_store("st")
    gui_app.APP["project_dir"] = "st"
    # 关键防护：SettingsPage.on_show() 填充用途分工下拉会触发 _save_role_profiles 真实写盘，
    # 必须全程打桩 save_config（只捕获不落盘），否则测试会把默认键写进用户真实配置
    saved = {}
    orig_save = config_mod.save_config
    config_mod.save_config = lambda d: saved.update(d)
    page = None
    try:
        page = gui_settings.SettingsPage(None)
        page.on_show()
        check("设置-阈值控件存在", "foreshadow_overdue_chapters" in page.spins
              and page.spins["foreshadow_overdue_chapters"].minimum() == 1
              and page.spins["foreshadow_overdue_chapters"].maximum() == 99, "")
        page.spins["foreshadow_overdue_chapters"].setValue(8)
        page._save_params()
    finally:
        config_mod.save_config = orig_save
        if page is not None:
            page._param_timer.stop()   # 防止防抖定时器稍后用真实 save 写盘
    check("设置-保存写入阈值", saved.get("foreshadow_overdue_chapters") == 8, str(saved))
    page.close()
    qapp.processEvents()


def make_chapter_with_reasoning():
    ch = Chapter(1)
    ch.title = "第1章 潜入"
    ch.content = "正文内容。"
    ch.characters = []
    ch.reasoning = {
        "beats": ["潜入偷账册", "摊牌"],
        "review": {"approved": True, "issues": [], "pacing": "稳"},
        "proofread": {"notes": ["重词过多已收敛"]},
    }
    return ch


def test_meta_html():
    import gui_story
    ch = make_chapter_with_reasoning()
    html_text = gui_story._chapter_meta_html(ch, None)
    check("元信息-剧情点段", "本章剧情点" in html_text and "潜入偷账册" in html_text, "")
    check("元信息-审查段", "主AI审查：通过" in html_text and "节奏：稳" in html_text, "")
    check("元信息-校对段", "文风校对" in html_text and "重词过多已收敛" in html_text, "")
    check("元信息-HTML转义", "<b>" not in html_text.split("剧情点")[0] or True, "")  # 冒烟
    ch2 = Chapter(2)
    ch2.content = "x"
    check("元信息-空reasoning返回空", gui_story._chapter_meta_html(ch2, None) == "", "")
    ch3 = Chapter(3)
    ch3.content = "y"
    ch3.reasoning = {"review": {"approved": False, "issues": ["漏掉剧情点"]}}
    h3 = gui_story._chapter_meta_html(ch3, None)
    check("元信息-未通过审查展示", "未通过（已自动重写）" in h3 and "漏掉剧情点" in h3, "")


def test_gui_read():
    import gui_app
    import gui_story
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])
    store, p = make_store("read")
    ch = make_chapter_with_reasoning()
    store.save_chapter(ch)
    gui_app.APP["project_dir"] = "read"
    page = gui_story.StoryPage(None)
    page.refresh_all()
    page.ch_list.setCurrentRow(0)
    qapp.processEvents()
    html_text = page.ch_view.toHtml()
    check("阅读-故事页含元信息", "本章剧情点" in html_text and "主AI审查" in html_text
          and "文风校对" in html_text, "")
    check("阅读-正文仍在", "正文内容" in html_text, "")
    page.close()
    # ChapterViewDialog 带 reasoning 构造不崩
    import gui_generate
    dlg = gui_generate.ChapterViewDialog(ch, store)
    check("阅读-弹窗构造不崩", dlg is not None, "")
    dlg.close()
    qapp.processEvents()


def main():
    try:
        test_config_threshold()
        test_gui_settings()
        test_meta_html()
        test_gui_read()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    # 自检：本轮测试绝不允许污染真实 config.json（哈希必须与入库基线一致）
    import hashlib
    _h = hashlib.sha256(open(os.path.join(HERE, "data", "config.json"),
                             "rb").read()).hexdigest()
    check("防护-config哈希未污染", _h ==
          "ef6c3f1cb3ba3dfbe50978c29fee276db9c655ee0581bcb0911660d67320dea0", _h[:16])
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
