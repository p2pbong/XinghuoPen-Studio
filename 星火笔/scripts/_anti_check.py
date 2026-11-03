# -*- coding: utf-8 -*-
"""v0.45 框架驱动与反套路治理 的独立验证（不碰磁盘 config / 真实 API）。

覆盖：
  [1] prompts.consolidate：JSON 模板含 planning_note/cliche_watch 字段 + 框架驱动任务说明
  [2] prompts.write_chapter：有规划卡 → 注入【本章意图…】+【本章套路陷阱预警…】；
      无 → 不注入；写作要求含反套路条款（巧合推进/反派主动解释/打脸循环）、
      情绪节奏软化（「不必硬造爽点」）、黄金三章软化（开场方式由故事框架决定）且仅前 3 章
  [3] prompts.review_chapter：含套路化/情节尴尬检查；JSON 含 cliches 字段 + scores 含 natural；
      approved=false 条件含「明显套路化/情节尴尬」
  [4] engine._pace_advice：natural 低分出「上章情节自然度低」；payout 低分软化为「情绪输出弱…
      不必硬造爽点」；旧硬性文字（务必保证一个清晰的情绪高点）已不存在
  [5] engine 全链路 mock：规划卡传入 write + reasoning 存档 + 日志；
      review 带 natural scores → 评分日志含「自然」；篇幅自适应（上章超目标 25% → 本章
      target 上调 10%）
  [6] gui_story._chapter_meta_html：意图/套路检测/自然评分展示；无记录返回空串
运行：env\\python.exe _anti_check.py
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
TMP = tempfile.mkdtemp(prefix="xhb_anti_")
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
storage.INDEX_PATH = os.path.join(storage.PROJECTS_DIR, "index.json")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)
_RUN_SEQ = [0]


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def make_store(name):
    store = storage.ProjectStore(name)
    p = NovelProject()
    p.title = "反套路测试"
    p.story_brief = "测试项目。"
    store.save_project(p)
    card = CharacterCard("主角", "剑客")
    store.save_character(card, InfoLibrary(card.id))
    return store, p, card.id


def test_consolidate_template():
    store, p, cid = make_store("c")
    sys_, user = prompts.consolidate(p, store, 1, "场景", {}, "")
    check("校验-框架驱动任务", "7. 生成本章规划卡" in user and "不预设爽点" in user, "")
    check("校验-意图字段", '"planning_note"' in user, "")
    check("校验-陷阱字段", '"cliche_watch"' in user, "")


def test_write_injection():
    store, p, cid = make_store("w")
    sys_, user = prompts.write_chapter(
        p, store, 2, "场景", "方向", {}, [], 300, recent_chapters=0,
        planning_note="以陈管家之死引主角深挖身世，奠定阴谋基调",
        cliche_watch=["不要让主角靠巧合获知密道位置", "反派不要主动解释阴谋"])
    check("写作-注入意图", "【本章意图（主AI基于故事框架裁定" in user
          and "奠定阴谋基调" in user, "")
    check("写作-注入预警", "【本章套路陷阱预警" in user
          and "- 规避：不要让主角靠巧合获知密道位置" in user
          and "- 规避：反派不要主动解释阴谋" in user, "")
    sys2, user2 = prompts.write_chapter(p, store, 2, "场景", "方向", {}, [],
                                        300, recent_chapters=0)
    check("写作-无卡不注入", "【本章意图" not in user2 and "【本章套路陷阱预警" not in user2, "")
    check("写作-反套路条款", "反套路（负面约束，宁可慢不可套" in user2
          and "『巧合推进』" in user2 and "『反派主动解释计划或临死全盘托出』" in user2
          and "『每章固定受辱-打脸循环』" in user2, "")
    check("写作-情绪节奏软化", "不必硬造爽点" in user2
          and "情绪支点" in user2, "")
    check("写作-黄金三章软化", "开场方式由故事框架决定" in user2, "")
    sys3, user3 = prompts.write_chapter(p, store, 1, "场景", "方向", {}, [],
                                        300, recent_chapters=0)
    check("写作-第1章含黄金三章", "开篇黄金三章" in user3, "")
    sys4, user4 = prompts.write_chapter(p, store, 4, "场景", "方向", {}, [],
                                        300, recent_chapters=0)
    check("写作-第4章不含黄金三章", "开篇黄金三章" not in user4, "")


def test_review_template():
    store, p, cid = make_store("r")
    ch = Chapter(1)
    ch.title = "第1章"
    ch.content = "正文。"
    sys_, user = prompts.review_chapter(p, store, ch, "下一章目标")
    check("审查-反套路检查", "套路化/情节尴尬" in user
          and "巧合推进" in user and "打脸循环" in user and "生硬转折" in user, "")
    check("审查-cliches字段", '"cliches"' in user, "")
    check("审查-natural维度", '"natural"' in user, "")
    check("审查-重写条件含套路", "明显套路化/情节尴尬" in user, "")


def test_pace_advice_soft():
    import engine as engine_mod
    a = engine_mod._pace_advice({"natural": 3, "rhythm": 8, "payout": 8,
                                 "immersion": 8, "character": 8})
    check("节奏-natural低分", "上章情节自然度低（3分）" in a
          and "避免巧合堆砌与生硬推进" in a, a)
    b = engine_mod._pace_advice({"payout": 3, "rhythm": 8, "immersion": 8,
                                 "character": 8, "natural": 8})
    check("节奏-payout软化", "上章情绪输出弱（3分）" in b and "不必硬造爽点" in b, b)
    check("节奏-旧硬性文字移除",
          "务必保证一个清晰的情绪高点/爽点" not in b and "上章爽点不足" not in b, "")


def run_pipeline(consolidation, prev=None, prev_len=None, prev_scores=None):
    """全链路 mock。consolidation：consolidate 返回 dict；prev：是否构造上一章。

    prev_len 上一章正文长度（测篇幅自适应）；prev_scores 上一章评分（测自适应节奏）。
    """
    import config as config_mod
    import engine as engine_mod
    import main_ai as main_ai_mod
    _RUN_SEQ[0] += 1
    store, p, cid = make_store("e2e_%d" % _RUN_SEQ[0])
    logs = []
    got = {"beats": None, "planning": None, "cliche": None, "target": None}

    if prev is not None:
        prevch = Chapter(1)
        prevch.title = "第1章"
        prevch.content = "字" * (prev_len or 300)
        prevch.reasoning = {"review": {"scores": prev_scores or {}}}
        store.save_chapter(prevch)
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
            "chapter_target_chars": 2000, "writer_recent_chapters": 0,
            "web_search_enabled": False, "auto_rewrite": True,
            "proofread_enabled": False}
        main_ai_mod.decide_characters = lambda *a, **k: {
            "scene_focus": "场景", "characters": [{"id": cid}],
            "recall": [], "new_character_hint": ""}
        engine_mod.char_ai.run_inference = lambda *a, **k: {}
        main_ai_mod.consolidate = lambda *a, **k: dict(consolidation)

        def fake_write(project, store, ch_no, scene, direction, infer, fs_lines,
                       target, fb="", recent_chapters=3, max_tokens=None,
                       draft="", beats=None, planning_note=None, cliche_watch=None):
            got["beats"] = beats
            got["planning"] = planning_note
            got["cliche"] = cliche_watch
            got["target"] = target
            return "第2章 标题", "字" * target

        def fake_review(project, store, chapter, target, beats=None):
            return {"approved": True, "issues": [], "pacing": "稳",
                    "scores": {"immersion": 7, "rhythm": 8, "payout": 6,
                               "character": 9, "natural": 8},
                    "cliches": [], "brief": "测试", "next_direction": "继续"}

        main_ai_mod.write_chapter = fake_write
        main_ai_mod.review_chapter = fake_review
        eng = engine_mod.NovelEngine(store, lambda k, m: logs.append((k, m)))
        ch = eng.generate_draft(p)
    finally:
        config_mod.load_config = orig_cfg
        main_ai_mod.decide_characters = orig_decide
        engine_mod.char_ai.run_inference = orig_infer
        main_ai_mod.consolidate = orig_cons
        main_ai_mod.write_chapter = orig_write
        main_ai_mod.review_chapter = orig_review
    return ch, got, logs


def test_engine_pipeline():
    cons = {
        "verdict": "ok", "approved_direction": "深夜潜入城主府",
        "chapter_beats": ["主AI规划点A", "主AI规划点B"],
        "planning_note": "以陈管家之死引主角深挖身世，奠定阴谋基调",
        "cliche_watch": ["不要让主角靠巧合获知密道位置"],
        "foreshadows": [], "kb_update": [], "need_chapters": [],
        "search_queries": []}
    ch, got, logs = run_pipeline(cons, prev=True, prev_len=2000)
    check("管线-意图传入write", got["planning"] == "以陈管家之死引主角深挖身世，奠定阴谋基调",
          str(got["planning"]))
    check("管线-预警传入write", got["cliche"] == ["不要让主角靠巧合获知密道位置"],
          str(got["cliche"]))
    check("管线-意图存档", (ch.reasoning.get("consolidation") or {}).get("planning_note")
          == "以陈管家之死引主角深挖身世，奠定阴谋基调", "")
    check("管线-意图日志", any("本章意图（框架裁定）" in m for k, m in logs), "")
    check("管线-预警日志", any("本章套路陷阱预警" in m for k, m in logs), "")
    check("管线-评分日志含自然", any("本章评分：沉浸7 / 节奏8 / 爽点6 / 人设9 / 自然8"
                                 in m for k, m in logs), "")
    check("管线-评分存档natural", (ch.reasoning.get("review") or {}).get("scores", {})
          .get("natural") == 8, "")
    # 篇幅自适应：上一章 2000 字 = 目标 2000，无调整
    check("篇幅-无偏差不变", got["target"] == 2000, str(got["target"]))
    # 上一章超目标 25%：2600 字 → 本章 2200 字
    ch2, got2, logs2 = run_pipeline(cons, prev=True, prev_len=2600)
    check("篇幅-超限上调", got2["target"] == 2200, str(got2["target"]))
    check("篇幅-日志输出", any("篇幅自适应" in m for k, m in logs2), "")
    # 上一章低于目标 25%：1400 字 → 本章 1800 字
    ch3, got3, _ = run_pipeline(cons, prev=True, prev_len=1400)
    check("篇幅-不足下调", got3["target"] == 1800, str(got3["target"]))
    # 无上一章 → 不调整
    ch4, got4, _ = run_pipeline(cons)
    check("篇幅-无上章不变", got4["target"] == 2000, str(got4["target"]))


def test_meta_html():
    import gui_story
    store, p, cid = make_store("m")
    ch = Chapter(1)
    ch.title = "第1章"
    ch.content = "正文。"
    ch.reasoning = {
        "consolidation": {"planning_note": "以陈管家之死引主角深挖身世，奠定阴谋基调"},
        "review": {"approved": True, "pacing": "稳", "cliches": ["巧合推进"],
                   "scores": {"immersion": 7, "rhythm": 8, "payout": 6,
                              "character": 9, "natural": 8}}}
    html = gui_story._chapter_meta_html(ch, store)
    check("阅读-意图展示", "本章意图（框架裁定）" in html
          and "奠定阴谋基调" in html, "")
    check("阅读-套路检测", "套路检测：巧合推进" in html, "")
    check("阅读-自然评分", "评分：沉浸7/节奏8/爽点6/人设9/自然8" in html, html)
    ch2 = Chapter(2)
    ch2.title = "第2章"
    ch2.content = "正文。"
    check("阅读-无记录空串", gui_story._chapter_meta_html(ch2, store) == "", "")


def main():
    try:
        test_consolidate_template()
        test_write_injection()
        test_review_template()
        test_pace_advice_soft()
        test_engine_pipeline()
        test_meta_html()
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
