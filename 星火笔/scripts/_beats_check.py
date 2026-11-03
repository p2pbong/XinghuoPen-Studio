# -*- coding: utf-8 -*-
"""v2.52 章节剧情点规划卡的独立验证（不碰磁盘 config / 真实 API）。

覆盖：
  [1] engine._clean_beats：非列表回退 [] / 空串过滤 / 上限 4 条 / 每条截断 40 字
  [2] prompts.consolidate：任务文本含「规划本章剧情点」+ JSON schema 含 chapter_beats 字段
  [3] prompts.write_chapter：有 beats 注入【本章剧情点…必须逐条在正文中完成】；无 beats 不注入
  [4] prompts.review_chapter：有 beats 注入核对块 + 审查要求含「剧情点完成度」；无 beats 不注入核对块
  [5] engine.generate_draft 全链路 mock：beats 从 consolidate 流向 write/review 调用、
      随章节 reasoning 存档、日志输出剧情点
运行：env\\python.exe _beats_check.py
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
from models import CharacterCard, InfoLibrary, NovelProject

RESULTS = []
TMP = tempfile.mkdtemp(prefix="xhb_beats_")
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
storage.INDEX_PATH = os.path.join(storage.PROJECTS_DIR, "index.json")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def make_store(name):
    store = storage.ProjectStore(name)
    p = NovelProject()
    p.title = "剧情点测试"
    p.story_brief = "测试项目。"
    store.save_project(p)
    card = CharacterCard("主角", "剑客")
    lib = InfoLibrary(card.id)
    store.save_character(card, lib)
    return store, p, card.id


def test_clean_beats():
    import engine as engine_mod
    check("清洗-非列表回退", engine_mod._clean_beats("不是列表") == [], "")
    check("清洗-空串过滤", engine_mod._clean_beats(["a", "", "  ", "b"]) == ["a", "b"], "")
    check("清洗-上限4条", len(engine_mod._clean_beats(["1", "2", "3", "4", "5"])) == 4, "")
    long_b = "长" * 60
    out = engine_mod._clean_beats([long_b])
    check("清洗-截断40字", len(out) == 1 and len(out[0]) == 40, "len=%d" % len(out[0]))


def test_consolidate_schema():
    store, p, cid = make_store("cons")
    sys_, user = prompts.consolidate(p, store, 1, "场景", {})
    check("校验-任务文本含规划剧情点", "规划本章剧情点" in user, "")
    check("校验-schema含chapter_beats", '"chapter_beats"' in user, "")


def test_write_review_injection():
    store, p, cid = make_store("inj")
    beats = ["主角潜入城主府偷到账册", "与陈管家摊牌获知身世线索"]
    sys_, user = prompts.write_chapter(p, store, 1, "场景", "方向", {}, [],
                                       300, recent_chapters=0, beats=beats)
    check("写作-注入剧情点块", "【本章剧情点" in user and "必须逐条在正文中完成" in user, "")
    check("写作-剧情点内容", "潜入城主府偷到账册" in user and "与陈管家摊牌" in user, "")
    sys_, user = prompts.write_chapter(p, store, 1, "场景", "方向", {}, [],
                                       300, recent_chapters=0)
    check("写作-无beats不注入", "【本章剧情点" not in user, "")
    from models import Chapter
    ch = Chapter(1)
    ch.content = "正文。"
    ch.characters = []
    sys_, user = prompts.review_chapter(p, store, ch, "下一章", beats=beats)
    check("审查-注入核对块", "【本章剧情点" in user and "逐条核对是否在正文中完成" in user, "")
    check("审查-含完成度要求", "剧情点完成度" in user, "")
    sys_, user = prompts.review_chapter(p, store, ch, "下一章")
    check("审查-无beats不注入核对块", "逐条核对是否在正文中完成" not in user, "")


def test_engine_pipeline():
    """全链路 mock：beats 从 consolidate 流向 write/review、随 reasoning 存档、日志输出。"""
    import config as config_mod
    import engine as engine_mod
    import main_ai as main_ai_mod
    store, p, cid = make_store("e2e")
    logs = []

    orig_cfg = config_mod.load_config
    orig_decide = main_ai_mod.decide_characters
    orig_infer = engine_mod.char_ai.run_inference
    orig_cons = main_ai_mod.consolidate
    orig_write = main_ai_mod.write_chapter
    orig_review = main_ai_mod.review_chapter
    got = {"write_beats": None, "review_beats": None}

    try:
        config_mod.load_config = lambda: {
            "reasoning_mode": "sequential", "max_workers": 1,
            "chapter_target_chars": 300, "writer_recent_chapters": 0,
            "web_search_enabled": False, "auto_rewrite": True}
        main_ai_mod.decide_characters = lambda *a, **k: {
            "scene_focus": "潜入城主府", "characters": [{"id": cid}],
            "recall": [], "new_character_hint": ""}
        engine_mod.char_ai.run_inference = lambda *a, **k: {}
        main_ai_mod.consolidate = lambda *a, **k: {
            "verdict": "ok", "approved_direction": "深夜潜入城主府",
            "chapter_beats": ["主角潜入城主府偷到账册", "与陈管家摊牌"],
            "foreshadows": [], "kb_update": [], "need_chapters": [],
            "search_queries": []}

        def fake_write(project, store, ch_no, scene, direction, infer, fs_lines,
                       target, fb="", recent_chapters=3, max_tokens=None,
                       draft="", beats=None, planning_note=None, cliche_watch=None):
            got["write_beats"] = beats
            return "第1章 潜入", "正" * 300

        def fake_review(project, store, chapter, target, beats=None):
            got["review_beats"] = beats
            return {"approved": True, "issues": [], "pacing": "稳",
                    "brief": "主角潜入城主府偷到账册", "next_direction": "追查"}

        main_ai_mod.write_chapter = fake_write
        main_ai_mod.review_chapter = fake_review

        eng = engine_mod.NovelEngine(store, lambda k, m: logs.append((k, m)))
        chapter = eng.generate_draft(p)
    finally:
        config_mod.load_config = orig_cfg
        main_ai_mod.decide_characters = orig_decide
        engine_mod.char_ai.run_inference = orig_infer
        main_ai_mod.consolidate = orig_cons
        main_ai_mod.write_chapter = orig_write
        main_ai_mod.review_chapter = orig_review

    check("管线-生成成功", chapter is not None and chapter.title == "第1章 潜入", "")
    check("管线-write收到beats", got["write_beats"] == ["主角潜入城主府偷到账册", "与陈管家摊牌"],
          str(got["write_beats"]))
    check("管线-review收到beats", got["review_beats"] == ["主角潜入城主府偷到账册", "与陈管家摊牌"],
          str(got["review_beats"]))
    check("管线-reasoning存档beats", (chapter.reasoning.get("beats") or []) ==
          ["主角潜入城主府偷到账册", "与陈管家摊牌"], str(chapter.reasoning.get("beats")))
    check("管线-日志输出剧情点", any("本章剧情点" in m for k, m in logs), str(logs[:3]))


def main():
    try:
        test_clean_beats()
        test_consolidate_schema()
        test_write_review_injection()
        test_engine_pipeline()
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
