# -*- coding: utf-8 -*-
"""v2.47 章节写作计划 + 本章草稿的独立验证（不碰磁盘 config / 真实 API）。

覆盖：
  [1] NovelProject.chapter_plans 字段往返 + 旧数据（无该字段）回退
  [2] 世界快照 save/rollback 同步 chapter_plans（含旧快照无字段兼容）
  [3] engine._match_chapter_plan：区间命中 / 区间外不命中 / 重叠取 start 大者 / end<start 容错
  [4] prompts.write_chapter 注入草稿段与草稿模式要求（扩写/禁止改剧情/文风一致）
  [5] 离屏 GUI：GeneratePage 构建（plan_list/draft_edit 存在）、on_show 刷新计划列表
运行：env\\python.exe _plan_check.py
"""
import os
import shutil
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import engine as engine_mod
import prompts
import storage
from models import NovelProject

RESULTS = []
TMP = tempfile.mkdtemp(prefix="xhb_plan_")
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def test_model_roundtrip():
    p = NovelProject()
    p.chapter_plans = [{"start": 3, "end": 8, "note": "这段推进主角复仇线，注意别写太急"},
                       {"start": 10, "end": 5, "note": "end<start 应容错为 10"}]
    d = p.to_dict()
    p2 = NovelProject.from_dict(d)
    check("模型-往返", p2.chapter_plans[0] == {"start": 3, "end": 8,
          "note": "这段推进主角复仇线，注意别写太急"}, str(p2.chapter_plans))
    check("模型-end<start容错", p2.chapter_plans[1]["start"] == 10
          and p2.chapter_plans[1]["end"] == 10, str(p2.chapter_plans[1]))
    # 旧数据（无 chapter_plans 字段）回退
    d.pop("chapter_plans", None)
    p3 = NovelProject.from_dict(d)
    check("模型-旧数据回退", p3.chapter_plans == [], "")


def test_snapshot_sync():
    store = storage.ProjectStore("plan_proj")
    proj = NovelProject()
    proj.title = "计划项目"
    proj.chapter_plans = [{"start": 1, "end": 2, "note": "快照里的计划"}]
    store.save_project(proj)
    store.save_world_snapshot(2)
    # 改动计划后再回滚，应恢复快照里的计划
    proj.chapter_plans = [{"start": 99, "end": 99, "note": "后来改的"}]
    store.save_project(proj)
    snap = store.load_world_snapshot(2)
    store.rollback_world(snap)
    p = store.load_project()
    check("快照-回滚恢复计划", p.chapter_plans == [{"start": 1, "end": 2, "note": "快照里的计划"}],
          str(p.chapter_plans))
    # 旧快照（无 chapter_plans 字段）回滚不崩、计划不变
    snap.pop("chapter_plans", None)
    p.chapter_plans = [{"start": 5, "end": 6, "note": "旧"}]
    store.save_project(p)
    store.rollback_world(snap)
    p2 = store.load_project()
    check("快照-旧快照兼容", p2.chapter_plans == [{"start": 5, "end": 6, "note": "旧"}],
          str(p2.chapter_plans))


def test_match_plan():
    store = storage.ProjectStore("plan_proj2")
    eng = engine_mod.NovelEngine(store, lambda k, m: None)
    p = NovelProject()
    p.chapter_plans = [
        {"start": 3, "end": 8, "note": "计划A"},
        {"start": 5, "end": 10, "note": "计划B"},
        {"start": 20, "end": 30, "note": "计划C"},
    ]
    check("计划-区间内命中", eng._match_chapter_plan(p, 4) == "计划A",
          eng._match_chapter_plan(p, 4))
    check("计划-重叠取start大者", eng._match_chapter_plan(p, 6) == "计划B",
          eng._match_chapter_plan(p, 6))
    check("计划-区间外不命中", eng._match_chapter_plan(p, 15) == "",
          eng._match_chapter_plan(p, 15))
    check("计划-末章命中", eng._match_chapter_plan(p, 30) == "计划C", "")
    p.chapter_plans = []
    check("计划-无计划返回空", eng._match_chapter_plan(p, 4) == "", "")


def test_draft_prompt():
    store = storage.ProjectStore("plan_proj3")
    proj = NovelProject()
    proj.title = "草稿项目"
    store.save_project(proj)
    sys_, user = prompts.write_chapter(
        proj, store, 5, "焦点", "方向", {}, [], 1500, recent_chapters=0,
        draft="草稿内容：主角发现井底有密道，决定深夜潜入。")
    check("草稿-注入草稿段", "【本章草稿" in user and "草稿内容：主角发现井底有密道" in user, "")
    for k in ("以其情节为底", "扩写润色", "禁止改变剧情走向", "修复与前文文风不一致",
              "调整叙事结构", "行文语感与前面已写章节保持一致"):
        check("草稿-含「%s」" % k, k in user, "")
    # 无草稿时不注入草稿内容段（「【本章草稿】」字样会出现在写作要求条款里，属正常）
    sys_, user = prompts.write_chapter(proj, store, 5, "焦点", "方向", {}, [],
                                       1500, recent_chapters=0)
    check("草稿-空草稿不注入内容", "草稿内容：主角发现井底有密道" not in user, "")


def test_gui():
    import gui_app
    import gui_generate
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])
    store = storage.ProjectStore("plan_proj4")
    proj = NovelProject()
    proj.title = "界面计划项目"
    proj.chapter_plans = [{"start": 2, "end": 4, "note": "界面计划"}]
    store.save_project(proj)
    gui_app.APP["project_dir"] = "plan_proj4"
    page = gui_generate.GeneratePage(None)
    check("GUI-计划表单存在", hasattr(page, "plan_list")
          and hasattr(page, "plan_start_spin") and hasattr(page, "plan_end_spin")
          and hasattr(page, "plan_note_edit") and hasattr(page, "draft_edit"), "")
    page.on_show()
    check("GUI-计划列表刷新", page.plan_list.count() == 1
          and "第2~4章" in page.plan_list.item(0).text(),
          "count=%d item=%s" % (page.plan_list.count(),
                                page.plan_list.item(0).text() if page.plan_list.count() else ""))
    # 页内直接添加（同区间覆盖）
    page.plan_start_spin.setValue(2)
    page.plan_end_spin.setValue(4)
    page.plan_note_edit.setPlainText("页内新计划")
    page._add_plan()
    check("GUI-页内添加同区间覆盖", page.plan_list.count() == 1
          and "页内新计划" in page.plan_list.item(0).text(),
          "count=%d item=%s" % (page.plan_list.count(),
                                page.plan_list.item(0).text() if page.plan_list.count() else ""))
    page.close()
    qapp.processEvents()


def test_auto_cleanup():
    """写完区间最后一章（next_chapter 越过 end）自动移除计划。"""
    import git_tool as git_tool_mod
    import main_ai as main_ai_mod
    from models import Chapter
    store = storage.ProjectStore("plan_cleanup")
    p = NovelProject()
    p.title = "清理测试"
    p.chapter_plans = [{"start": 1, "end": 2, "note": "前两章"},
                       {"start": 5, "end": 8, "note": "中段"},
                       {"start": 1, "end": 99, "note": "长段"}]
    store.save_project(p)
    ch = Chapter(2)
    ch.title = "第2章"
    ch.content = "正文内容" * 30
    ch.status = "approved"
    ch.characters = []
    store.save_chapter(ch)
    orig_uw, orig_cs = main_ai_mod.update_world, main_ai_mod.compress_summary
    orig_gt = git_tool_mod.commit
    main_ai_mod.update_world = lambda *a, **k: {}
    main_ai_mod.compress_summary = lambda *a, **k: {}
    git_tool_mod.commit = lambda *a, **k: None   # 禁止真实 git 归档（避免 git add -A 卷入工作树改动）
    try:
        eng = engine_mod.NovelEngine(store, lambda k, m: None)
        eng.finalize_chapter(p, ch)
    finally:
        git_tool_mod.commit = orig_gt
        main_ai_mod.update_world, main_ai_mod.compress_summary = orig_uw, orig_cs
    p2 = store.load_project()
    check("清理-写完end章自动移除",
          p2.chapter_plans == [{"start": 5, "end": 8, "note": "中段"},
                               {"start": 1, "end": 99, "note": "长段"}],
          str(p2.chapter_plans))
    check("清理-next_chapter推进", p2.state.get("next_chapter") == 3, "")


def main():
    try:
        test_model_roundtrip()
        test_snapshot_sync()
        test_match_plan()
        test_draft_prompt()
        test_auto_cleanup()
        test_gui()
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
