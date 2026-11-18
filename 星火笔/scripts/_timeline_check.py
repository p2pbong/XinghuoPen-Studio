# -*- coding: utf-8 -*-
"""v2.53 故事时间线（索引带梗概）+ 生成页剧情点展示 的独立验证（不碰磁盘 config / 真实 API）。

覆盖：
  [1] storage：章节索引新增 brief 字段（save_chapter 写入 → chapter_summaries 带出；
      重建捕获 brief；旧索引无 brief 回退空串）；chapter_brief 回退正文首段截取
  [2] 离屏 GUI·故事页时间线：_fill_timeline 行数/列值（章号/标题/状态/字数/梗概/伏笔埋收标记）、
      缺失梗概后台补载后经 Signal 回填
  [3] 离屏 GUI·生成页剧情点展示：_on_draft 有 beats → beats_label 显示；无 beats → 空
运行：env\\python.exe _timeline_check.py
"""
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import storage
from models import Chapter, Foreshadow, NovelProject

RESULTS = []
TMP = tempfile.mkdtemp(prefix="xhb_tl_")
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
storage.INDEX_PATH = os.path.join(storage.PROJECTS_DIR, "index.json")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def make_store(name, chapters=3):
    store = storage.ProjectStore(name)
    p = NovelProject()
    p.title = "时间线测试"
    p.story_brief = "测试项目。"
    store.save_project(p)
    for i in range(1, chapters + 1):
        ch = Chapter(i)
        ch.title = "第%d章" % i
        ch.content = "第%d章正文内容。" % i
        ch.brief = "第%d章梗概：发生了关键事件。" % i
        ch.status = "approved"
        store.save_chapter(ch)
    return store, p


def test_index_brief():
    store, p = make_store("idx")
    summaries = dict((i, m) for i, m in store.chapter_summaries())
    check("索引-save带出brief", summaries[1]["brief"] == "第1章梗概：发生了关键事件。", "")
    check("索引-状态/字数保留", summaries[1]["status"] == "approved"
          and summaries[1]["chars"] == len("第1章正文内容。"), "")
    # 重建捕获 brief：删索引文件 → chapter_summaries 触发全量重建
    idx_path = os.path.join(store.base, "chapters_index.json")
    os.remove(idx_path)
    summaries2 = dict((i, m) for i, m in store.chapter_summaries())
    check("索引-重建捕获brief", summaries2[1]["brief"] == "第1章梗概：发生了关键事件。", "")
    # 旧索引无 brief：手工写入全量旧格式条目（缺 brief 字段）→ 回退空串
    meta = {"chapters": {}}
    for i in (1, 2, 3):
        meta["chapters"][str(i)] = {"title": "旧章%d" % i, "status": "approved",
                                    "chars": 5,
                                    "mtime": os.path.getmtime(store.chapter_path(i))}
    import json as _json
    with open(idx_path, "w", encoding="utf-8") as f:
        _json.dump(meta, f, ensure_ascii=False)
    s3 = dict((i, m) for i, m in store.chapter_summaries())
    check("索引-旧条目brief回退空", s3[2]["brief"] == "" and s3[2]["title"] == "旧章2",
          str(s3[2]))


def test_chapter_brief_fallback():
    store, p = make_store("fb")
    ch = store.load_chapter(1)
    ch.brief = ""
    ch.content = "首段是关键内容。\n\n第二段。"
    store.save_chapter(ch)
    check("补载-brief优先", store.chapter_brief(1) == "首段是关键内容。", "")
    ch.brief = "有梗概"
    store.save_chapter(ch)
    check("补载-回退首段", store.chapter_brief(1) == "有梗概", "")
    # 超长首段截断 90 字
    ch2 = store.load_chapter(1)
    ch2.brief = ""
    ch2.content = "字" * 150
    store.save_chapter(ch2)
    b = store.chapter_brief(1)
    check("补载-截断90字", len(b) == 91 and b.endswith("…"), "len=%d" % len(b))


def test_gui_timeline():
    import gui_app
    import gui_story
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])
    store, p = make_store("tl_gui", chapters=3)
    # 造两条伏笔：第1章埋、第3章回收
    fs = [Foreshadow("铜钥匙线索", "plant", "主角"), Foreshadow("铜钥匙揭示", "payoff", "主角")]
    fs[0].planted_chapter = 1
    fs[1].planted_chapter = 1
    fs[1].resolved_chapter = 3
    fs[0].status = "resolved"
    fs[0].resolved_chapter = 3
    store.save_foreshadows(fs)
    gui_app.APP["project_dir"] = "tl_gui"
    page = gui_story.StoryPage(None)
    check("GUI-时间线控件存在", hasattr(page, "timeline_table"), "")
    page.refresh_all()
    t = page.timeline_table
    check("GUI-时间线行数", t.rowCount() == 3, "rows=%d" % t.rowCount())
    check("GUI-章号标题梗概", t.item(0, 0).text() == "1"
          and t.item(0, 1).text() == "第1章"
          and "关键事件" in t.item(0, 4).text(), "")
    # 伏笔埋收标记：第1章含「埋:」，第3章含「收:」
    check("GUI-伏笔埋标记", "埋:" in t.item(0, 5).text(), t.item(0, 5).text())
    check("GUI-伏笔收标记", "收:" in t.item(2, 5).text(), t.item(2, 5).text())
    # 缺梗概补载：清掉一章 brief → 刷新 → 后台线程回填
    ch = store.load_chapter(2)
    ch.brief = ""
    store.save_chapter(ch)
    page.refresh_all()
    check("GUI-缺梗概占位", "梗概补载中" in t.item(1, 4).text(), t.item(1, 4).text())
    for _ in range(50):  # 等后台线程 + 信号回填
        qapp.processEvents()
        import time as _time
        _time.sleep(0.02)
    check("GUI-补载回填", "第2章正文内容" in t.item(1, 4).text(), t.item(1, 4).text())
    page.close()
    qapp.processEvents()


def test_gui_beats_label():
    import gui_app
    import gui_generate
    from models import Chapter
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])
    store, p = make_store("beats_gui")
    gui_app.APP["project_dir"] = "beats_gui"
    page = gui_generate.GeneratePage(None)
    check("GUI-beats_edit存在", hasattr(page, "beats_edit"), "")
    ch = Chapter(1)
    ch.content = "正文"
    ch.reasoning = {"beats": ["潜入偷账册", "摊牌"]}
    page._on_draft(ch)
    txt = page.beats_edit.toPlainText()
    check("GUI-beats回填", "潜入偷账册" in txt and "摊牌" in txt, txt)
    page.beats_edit.setPlainText("改成我的剧情点\n\n第二点")   # 含空行
    beats = page._current_beats()
    check("GUI-_current_beats过滤空行", beats == ["改成我的剧情点", "第二点"], str(beats))
    page.beats_edit.setPlainText("   ")
    check("GUI-空输入返回None", page._current_beats() is None, str(page._current_beats()))
    ch2 = Chapter(2)
    ch2.content = "正文2"
    ch2.reasoning = {}
    page._on_draft(ch2)
    check("GUI-无beats清空", page.beats_edit.toPlainText() == "", repr(page.beats_edit.toPlainText()))
    page.close()
    qapp.processEvents()


def main():
    try:
        test_index_brief()
        test_chapter_brief_fallback()
        test_gui_timeline()
        test_gui_beats_label()
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
