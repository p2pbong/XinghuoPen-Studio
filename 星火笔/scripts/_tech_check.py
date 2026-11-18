# -*- coding: utf-8 -*-
"""v2.61 写作技巧库（爆款拆解注入）+ 审查量化打分 + 情绪高点节奏条款 的独立验证（不碰磁盘 config / 真实 API）。

覆盖：
  [1] NovelProject 字段往返：story_tech_source / story_techniques（旧数据回退空串）
  [2] prompts.extract_writing_techniques：含素材、JSON schema、忌空泛条款
  [3] main_ai.extract_writing_techniques 调用链与失败回退
  [4] write_chapter：有技巧库注入【写作技巧库…】；无则不注入；写作要求含「情绪高点/爽点」条款
  [5] review_chapter：有技巧库注入；JSON schema 含 scores 四维字段；说明在 JSON 模板外
  [6] engine 全链路 mock：review 带 scores → 日志输出「本章评分：沉浸…/节奏…/爽点…/人设…」、
      reasoning["review"]["scores"] 存档
  [7] gui_story._chapter_meta_html：审查行含评分
运行：env\\python.exe _tech_check.py
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
TMP = tempfile.mkdtemp(prefix="xhb_tech_")
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
storage.INDEX_PATH = os.path.join(storage.PROJECTS_DIR, "index.json")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def make_store(name, with_tech=False):
    store = storage.ProjectStore(name)
    p = NovelProject()
    p.title = "技巧库测试"
    p.story_brief = "测试项目。"
    if with_tech:
        p.story_techniques = "每幕开头抛新信息勾住读者；爽点放在章节 1/3 处；大段描写后接反转短句。"
    store.save_project(p)
    card = CharacterCard("主角", "剑客")
    store.save_character(card, InfoLibrary(card.id))
    return store, p, card.id


def test_model():
    p = NovelProject()
    p.story_tech_source = "素材段落"
    p.story_techniques = "技巧一；技巧二"
    d = p.to_dict()
    p2 = NovelProject.from_dict(d)
    check("模型-字段往返", p2.story_tech_source == "素材段落"
          and p2.story_techniques == "技巧一；技巧二", "")
    d.pop("story_techniques", None)
    d.pop("story_tech_source", None)
    check("模型-旧数据回退", NovelProject.from_dict(d).story_techniques == ""
          and NovelProject.from_dict(d).story_tech_source == "", "")


def test_extract_prompt():
    source = "夜风卷着雪粒。他踏入城门，把怀里的密信攥得更紧。守卫拦下他，他笑了：'替城主送信。'" * 3
    sys_, user = prompts.extract_writing_techniques(source)
    check("拆解-含素材", "爆款章节片段" in user and "密信" in user, "")
    check("拆解-含JSON", '"techniques"' in user and "5-8 条" in user, "")
    check("拆解-忌空泛", "节奏好" in user and "悬念强" in user, "")
    # main_ai 调用链
    import main_ai as main_ai_mod
    orig = main_ai_mod.llm.chat_json
    calls = {}
    main_ai_mod.llm.chat_json = lambda *a, **k: (calls.update(tag=k.get("tag")) or
                                                 {"techniques": ["幕幕抛新信息", "爽点放1/3"]})
    try:
        ts = main_ai_mod.extract_writing_techniques(source)
    finally:
        main_ai_mod.llm.chat_json = orig
    check("拆解-main_ai调用", ts == ["幕幕抛新信息", "爽点放1/3"]
          and calls.get("tag") == "extract_techniques", str(ts))
    main_ai_mod.llm.chat_json = lambda *a, **k: "bad"
    try:
        ts2 = main_ai_mod.extract_writing_techniques(source)
    finally:
        main_ai_mod.llm.chat_json = orig
    check("拆解-失败回退空", ts2 == [], "")


def test_write_injection():
    store, p, cid = make_store("w", with_tech=True)
    sys_, user = prompts.write_chapter(p, store, 1, "场景", "方向", {}, [],
                                       300, recent_chapters=0)
    check("写作-注入技巧库", "【写作技巧库" in user and "爽点放在章节 1/3 处" in user, "")
    check("写作-情绪支点条款", "情绪节奏" in user and "情绪支点" in user
          and "结尾留强烈钩子" in user, "")
    store2, p2, cid2 = make_store("w2")
    sys_, user2 = prompts.write_chapter(p2, store2, 1, "场景", "方向", {}, [],
                                        300, recent_chapters=0)
    check("写作-无技巧库不注入", "【写作技巧库" not in user2, "")


def test_review_injection_scores():
    store, p, cid = make_store("r", with_tech=True)
    ch = Chapter(1)
    ch.content = "正文。"
    ch.characters = [cid]
    sys_, user = prompts.review_chapter(p, store, ch, "下一章")
    check("审查-注入技巧库", "【写作技巧库" in user and "爽点放在章节 1/3 处" in user, "")
    check("审查-scores字段", '"scores"' in user and '"immersion"' in user
          and '"rhythm"' in user and '"payout"' in user and '"character"' in user, "")
    # JSON 模板外有打分说明（说明文字在 JSON 字符串之后）
    idx = user.find('"scores"')
    note = user.find("量化打分")
    check("审查-说明在模板外", idx > 0 and note > idx, "idx=%d note=%d" % (idx, note))
    store2, p2, cid2 = make_store("r2")
    sys_, user2 = prompts.review_chapter(p2, store2, ch, "下一章")
    check("审查-无技巧库不注入", "【写作技巧库" not in user2, "")


def test_engine_scores_log():
    """全链路 mock：review 带 scores → 日志输出评分 + reasoning 存档。"""
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
            "verdict": "ok", "approved_direction": "方向",
            "chapter_beats": [], "foreshadows": [], "kb_update": [],
            "need_chapters": [], "search_queries": []}
        main_ai_mod.write_chapter = lambda *a, **k: ("第1章 标题", "正文" * 100)
        main_ai_mod.review_chapter = lambda *a, **k: {
            "approved": True, "issues": [], "pacing": "稳",
            "scores": {"immersion": 7, "rhythm": 8, "payout": 6, "character": 9}}
        eng = engine_mod.NovelEngine(store, lambda k, m: logs.append((k, m)))
        ch = eng.generate_draft(p)
    finally:
        config_mod.load_config = orig_cfg
        main_ai_mod.decide_characters = orig_decide
        engine_mod.char_ai.run_inference = orig_infer
        main_ai_mod.consolidate = orig_cons
        main_ai_mod.write_chapter = orig_write
        main_ai_mod.review_chapter = orig_review
    check("管线-评分日志", any("本章评分：沉浸7 / 节奏8 / 爽点6 / 人设9" in m for k, m in logs),
          str([m for k, m in logs if "评分" in m]))
    check("管线-评分存档", (ch.reasoning.get("review") or {}).get("scores") ==
          {"immersion": 7, "rhythm": 8, "payout": 6, "character": 9},
          str((ch.reasoning.get("review") or {}).get("scores")))


def test_meta_html():
    import gui_story
    ch = Chapter(1)
    ch.content = "正文"
    ch.reasoning = {"review": {"approved": True, "issues": [], "pacing": "稳",
                               "scores": {"immersion": 7, "rhythm": 8, "payout": 6, "character": 9}}}
    html_text = gui_story._chapter_meta_html(ch, None)
    check("阅读-含评分", "评分：沉浸7/节奏8/爽点6/人设9" in html_text, html_text)


def main():
    try:
        test_model()
        test_extract_prompt()
        test_write_injection()
        test_review_injection_scores()
        test_engine_scores_log()
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
