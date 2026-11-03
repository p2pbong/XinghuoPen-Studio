# -*- coding: utf-8 -*-
"""v2.62 用户可控性（生成前剧情点确认）+ 自动化智能性（自适应节奏/黄金三章/承接上章）的独立验证。

覆盖：
  [1] engine._pace_advice：低分项出强化指令 / 合格不出 / 非 dict 回退空串
  [2] prompts.write_chapter：前 3 章含黄金三章条款、后续章不含；第 2+ 章含承接上章条款、第 1 章不含
  [3] engine 全链路 mock·beats_confirm：回调收到剧情点与走向 → 返回覆盖清单 →
      write/review 收到覆盖清单、reasoning 存档覆盖清单、日志「用户确认后」；
      回调返回 None → 沿用主AI规划；回调抛异常 → 不阻断
  [4] engine 自适应节奏：上一章低分 → 写正文方向含「自适应节奏要求」+ 日志；
      无上一章/无评分 → 不注入
  [5] 离屏 GUI：confirm_beats_check 存在；BeatsConfirmDialog 构造与 value()（修改/空输入）
运行：env\\python.exe _ctrl_check.py
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
from models import Chapter, CharacterCard, InfoLibrary, NovelProject

RESULTS = []
TMP = tempfile.mkdtemp(prefix="xhb_ctrl_")
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
storage.INDEX_PATH = os.path.join(storage.PROJECTS_DIR, "index.json")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def make_store(name):
    store = storage.ProjectStore(name)
    p = NovelProject()
    p.title = "可控性测试"
    p.story_brief = "测试项目。"
    store.save_project(p)
    card = CharacterCard("主角", "剑客")
    store.save_character(card, InfoLibrary(card.id))
    return store, p, card.id


def test_pace_advice():
    import engine as engine_mod
    check("节奏-低分出指令", "上章节奏偏平（4分）" in engine_mod._pace_advice(
        {"rhythm": 4, "payout": 8, "immersion": 7, "character": 9}), "")
    a = engine_mod._pace_advice({"rhythm": 9, "payout": 3, "immersion": 2, "character": 9})
    check("节奏-多项低分", "上章情绪输出弱（3分）" in a and "上章沉浸感弱（2分）" in a, a)
    check("节奏-全合格空", engine_mod._pace_advice(
        {"rhythm": 8, "payout": 7, "immersion": 8, "character": 8}) == "", "")
    check("节奏-非dict回退", engine_mod._pace_advice(None) == ""
          and engine_mod._pace_advice("x") == "", "")
    check("节奏-缺失项不崩", engine_mod._pace_advice({"rhythm": 2}) ==
          "上章节奏偏平（2分）：本章结合故事框架自主调整推进结构"
          "（参考：压缩铺垫、加快事件推进、增强节拍变化，以故事需要为准）", "")


def test_write_clauses():
    store, p, cid = make_store("w")
    sys_, user1 = prompts.write_chapter(p, store, 1, "场景", "方向", {}, [],
                                        300, recent_chapters=0)
    check("条款-第1章含黄金三章", "开篇黄金三章" in user1, "")
    check("条款-第1章不含承接", "承接上章结尾" not in user1, "")
    sys_, user2 = prompts.write_chapter(p, store, 2, "场景", "方向", {}, [],
                                        300, recent_chapters=0)
    check("条款-第2章含承接", "承接上章结尾" in user2, "")
    check("条款-第2章含黄金三章", "开篇黄金三章" in user2, "")   # 黄金三章覆盖前 3 章
    sys_, user3 = prompts.write_chapter(p, store, 3, "场景", "方向", {}, [],
                                        300, recent_chapters=0)
    check("条款-第3章仍含黄金三章", "开篇黄金三章" in user3, "")
    sys_, user4 = prompts.write_chapter(p, store, 4, "场景", "方向", {}, [],
                                        300, recent_chapters=0)
    check("条款-第4章不含黄金三章", "开篇黄金三章" not in user4, "")


def run_pipeline(beats_confirm, prev_scores=None):
    """全链路 mock。prev_scores 设置上一章评分（测自适应节奏）。"""
    import config as config_mod
    import engine as engine_mod
    import main_ai as main_ai_mod
    store, p, cid = make_store("e2e")
    logs = []
    got = {"write_beats": None, "direction": None}

    if prev_scores is not None:
        # 上一章 = 第 1 章（自适应节奏只在 ch_no>1 时读取）；本轮生成第 2 章
        prev = Chapter(1)
        prev.title = "第1章"
        prev.content = "上一章正文"
        prev.reasoning = {"review": {"scores": prev_scores}}
        store.save_chapter(prev)
        p.state["next_chapter"] = 2
        store.save_project(p)

    orig_cfg = config_mod.load_config
    orig_decide = main_ai_mod.decide_characters
    orig_infer = engine_mod.char_ai.run_inference
    orig_cons = main_ai_mod.consolidate
    orig_write = main_ai_mod.write_chapter
    orig_review = main_ai_mod.review_chapter
    try:
        config_mod.load_config = lambda: {
            "reasoning_mode": "sequential", "max_workers": 1,
            "chapter_target_chars": 300, "writer_recent_chapters": 0,
            "web_search_enabled": False, "auto_rewrite": True,
            "proofread_enabled": False}
        main_ai_mod.decide_characters = lambda *a, **k: {
            "scene_focus": "场景", "characters": [{"id": cid}],
            "recall": [], "new_character_hint": ""}
        engine_mod.char_ai.run_inference = lambda *a, **k: {}
        main_ai_mod.consolidate = lambda *a, **k: {
            "verdict": "ok", "approved_direction": "深夜潜入城主府",
            "chapter_beats": ["主AI规划点A", "主AI规划点B"],
            "foreshadows": [], "kb_update": [], "need_chapters": [],
            "search_queries": []}

        def fake_write(project, store, ch_no, scene, direction, infer, fs_lines,
                       target, fb="", recent_chapters=3, max_tokens=None,
                       draft="", beats=None, planning_note=None, cliche_watch=None):
            got["write_beats"] = beats
            got["direction"] = direction
            return "第1章 标题", "正文" * 100

        def fake_review(project, store, chapter, target, beats=None):
            return {"approved": True, "issues": [], "pacing": "稳"}

        main_ai_mod.write_chapter = fake_write
        main_ai_mod.review_chapter = fake_review
        eng = engine_mod.NovelEngine(store, lambda k, m: logs.append((k, m)))
        ch = eng.generate_draft(p, beats_confirm=beats_confirm)
    finally:
        config_mod.load_config = orig_cfg
        main_ai_mod.decide_characters = orig_decide
        engine_mod.char_ai.run_inference = orig_infer
        main_ai_mod.consolidate = orig_cons
        main_ai_mod.write_chapter = orig_write
        main_ai_mod.review_chapter = orig_review
    return ch, got, logs


def test_beats_confirm():
    calls = {}

    def confirm(beats, direction):
        calls["beats"] = list(beats)
        calls["direction"] = direction
        return ["用户改的A", "用户改的B"]

    ch, got, logs = run_pipeline(confirm)
    check("确认-回调收到清单", calls.get("beats") == ["主AI规划点A", "主AI规划点B"]
          and "深夜潜入城主府" in calls.get("direction", ""), str(calls))
    check("确认-write收到用户清单", got["write_beats"] == ["用户改的A", "用户改的B"],
          str(got["write_beats"]))
    check("确认-reasoning存档用户清单", (ch.reasoning.get("beats") or []) ==
          ["用户改的A", "用户改的B"], str(ch.reasoning.get("beats")))
    check("确认-日志标用户确认", any("用户确认后" in m for k, m in logs), "")
    # 回调返回 None → 沿用主AI规划
    ch2, got2, logs2 = run_pipeline(lambda b, d: None)
    check("跳过-沿用主AI规划", got2["write_beats"] == ["主AI规划点A", "主AI规划点B"]
          and any("跳过确认" in m for k, m in logs2), "")
    # 回调抛异常 → 不阻断
    ch3, got3, _ = run_pipeline(lambda b, d: 1 / 0)
    check("异常-不阻断沿用规划", got3["write_beats"] == ["主AI规划点A", "主AI规划点B"], "")


def test_adaptive():
    # 上一章低分 → 写正文方向含自适应要求 + 日志
    ch, got, logs = run_pipeline(None, prev_scores={"rhythm": 4, "payout": 8,
                                                    "immersion": 7, "character": 9})
    check("自适应-方向含要求", "自适应节奏要求" in got["direction"]
          and "上章节奏偏平（4分）" in got["direction"], got["direction"][:80])
    check("自适应-日志输出", any("自适应节奏" in m for k, m in logs), "")
    # 无上一章 → 不注入
    ch2, got2, _ = run_pipeline(None)
    check("自适应-无上章不注入", "自适应节奏要求" not in got2["direction"], "")


def test_gui():
    import gui_app
    import gui_generate
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])
    store, p, cid = make_store("gui")
    gui_app.APP["project_dir"] = "gui"
    page = gui_generate.GeneratePage(None)
    check("GUI-确认勾选存在", hasattr(page, "confirm_beats_check"), "")
    dlg = gui_generate.BeatsConfirmDialog(["点A", "点B"], "走向说明", None)
    dlg.edit.setPlainText("改成X\n\n改成Y")
    check("GUI-弹窗取值", dlg.value() == ["改成X", "改成Y"], str(dlg.value()))
    dlg2 = gui_generate.BeatsConfirmDialog(["点A"], "走向", None)
    dlg2.edit.setPlainText("  ")
    check("GUI-空输入返回None", dlg2.value() is None, str(dlg2.value()))
    dlg.close()
    dlg2.close()
    page.close()
    qapp.processEvents()


def main():
    try:
        test_pace_advice()
        test_write_clauses()
        test_beats_confirm()
        test_adaptive()
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
