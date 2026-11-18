# -*- coding: utf-8 -*-
"""v2.60 草稿箱性能优化（文件名解析零读取）+ 去AI味页统一八股核心段的独立验证（不碰磁盘 config / 真实 API）。

覆盖：
  [1] storage.list_chapter_drafts：备份文件名直接解析 章号/tag/时间（标题空串）——
      顺序倒序、字段正确；同秒防覆盖的 -2 后缀文件名也能解析
  [2] 回退路径：异常文件名（非标准格式）回退读 JSON，标题正确带出
  [3] 性能冒烟：200 份备份列表秒出（仅统计行数与时间量级）
  [4] 离屏 GUI·DraftsDialog：列表项显示「第N章（重写前 · 时间）」
  [5] prompts.deai_chapter：默认规则与自定义规则都注入八股核心治理段
运行：env\\python.exe _draft_check.py
"""
import os
import shutil
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import prompts
import storage
from models import Chapter, NovelProject

RESULTS = []
TMP = tempfile.mkdtemp(prefix="xhb_draft_")
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
storage.INDEX_PATH = os.path.join(storage.PROJECTS_DIR, "index.json")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def make_store(name):
    store = storage.ProjectStore(name)
    p = NovelProject()
    p.title = "草稿箱测试"
    p.story_brief = "测试项目。"
    store.save_project(p)
    return store, p


def test_fast_list():
    store, p = make_store("fast")
    ch = Chapter(3)
    ch.title = "第3章 夜探"
    ch.content = "正文" * 50
    store.backup_chapter_draft(ch, "rewrite")
    ch2 = Chapter(1)
    ch2.title = "第1章 开头"
    ch2.content = "正文2" * 50
    store.backup_chapter_draft(ch2, "edit")
    ch3 = Chapter(7)
    ch3.title = "第7章 决战"
    ch3.content = "正文3" * 50
    store.backup_chapter_draft(ch3, "delete")
    drafts = store.list_chapter_drafts()
    check("快路径-数量", len(drafts) == 3, "n=%d" % len(drafts))
    check("快路径-字段正确", {d["index"] for d in drafts} == {7, 3, 1}
          and {d["tag"] for d in drafts} == {"rewrite", "edit", "delete"}, str(drafts))
    # 按时间倒序：最新备份（第7章 delete）在最前
    check("快路径-倒序", drafts[0]["index"] == 7 and drafts[0]["tag"] == "delete",
          str(drafts[0]))
    check("快路径-时间格式", "20" in drafts[0]["saved_at"]
          and len(drafts[0]["saved_at"]) == 19, drafts[0]["saved_at"])
    check("快路径-标题留空", drafts[0]["title"] == "", "")
    # 同秒防覆盖 -2 后缀文件名可解析
    d = os.path.join(store.base, "drafts")
    extra = "draft_ch_003_2026-09-29_134527_rewrite-2.json"
    open(os.path.join(d, extra), "w", encoding="utf-8").write("{}")
    drafts2 = store.list_chapter_drafts()
    check("快路径-序号后缀解析", any(x["fname"] == extra and x["index"] == 3
          and x["tag"] == "rewrite" for x in drafts2), "")


def test_fallback():
    store, p = make_store("fb")
    d = os.path.join(store.base, "drafts")
    os.makedirs(d, exist_ok=True)
    # 非标准文件名 → 回退读 JSON（标题带出）
    ch = Chapter(5)
    ch.title = "旧版备份"
    ch.content = "内容"
    import json as _json
    from models import now as _now
    data = {"chapter": ch.to_dict(), "tag": "rewrite", "saved_at": _now(),
            "kind": "chapter_draft"}
    with open(os.path.join(d, "old_style_backup.json"), "w", encoding="utf-8") as f:
        _json.dump(data, f, ensure_ascii=False)
    drafts = store.list_chapter_drafts()
    hit = [x for x in drafts if x["fname"] == "old_style_backup.json"]
    check("回退-读JSON带标题", hit and hit[0]["title"] == "旧版备份"
          and hit[0]["index"] == 5, str(hit))


def test_perf():
    store, p = make_store("perf")
    ch = Chapter(1)
    ch.content = "正文" * 200
    for i in range(200):
        ch.index = (i % 200) + 1
        ch.title = "第%d章" % ch.index
        store.backup_chapter_draft(ch, "rewrite")
    t0 = time.time()
    drafts = store.list_chapter_drafts()
    el = time.time() - t0
    check("性能-200份列表秒出", len(drafts) == 200 and el < 1.0,
          "n=%d elapsed=%.3fs" % (len(drafts), el))


def test_gui():
    import gui_app
    import gui_generate
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])
    store, p = make_store("gui")
    ch = Chapter(2)
    ch.title = "第2章 入城"
    ch.content = "正文" * 20
    store.backup_chapter_draft(ch, "rewrite")
    gui_app.APP["project_dir"] = "gui"
    # DraftsDialog 构造需要 engine_for(project_dir) → 用真实 store 目录
    dlg = gui_generate.DraftsDialog(None)
    check("GUI-列表项显示", dlg.listw.count() == 1
          and "第2章" in dlg.listw.item(0).text()
          and "重写前" in dlg.listw.item(0).text(), dlg.listw.item(0).text())
    dlg.close()
    qapp.processEvents()


def test_deai_core():
    store, p = make_store("deai")
    ch = Chapter(1)
    ch.content = "他深吸一口气，眼中闪过一丝寒芒。"
    # 默认规则
    sys_, user = prompts.deai_chapter(p, ch, mode="clean")
    check("去AI味-默认含核心段", "AI八股文分级治理（核心治理" in user, "")
    # 自定义规则
    sys_, user2 = prompts.deai_chapter(p, ch, mode="clean", rules="自定义：多用短句。")
    check("去AI味-自定义含核心段", "AI八股文分级治理（核心治理" in user2
          and "自定义：多用短句" in user2, "")


def main():
    try:
        test_fast_list()
        test_fallback()
        test_perf()
        test_gui()
        test_deai_core()
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
