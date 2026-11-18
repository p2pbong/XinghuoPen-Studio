# -*- coding: utf-8 -*-
"""v2.57 AI八股文全链路治理（写作预防 + 分级校对 + 报告入库）的独立验证（不碰磁盘 config / 真实 API）。

覆盖：
  [1] prompts.write_chapter 含反「AI八股」写作条款（段落长短随节拍/对话标签低频/情绪直写/
      生活化比喻/留白/排比克制/动作对话收尾/禁用高频套词清单）
  [2] DEFAULT_PROOFREAD_RULES 含【四、AI八股文分级治理】（7 类问题 + 三级判定 + 三条保护规则）
  [3] prompts.proofread_chapter：JSON schema 含 ai_grade/ai_hits；有文风样本时注入
      【参考文风样本…以…为对照】块、无则不注入
  [4] engine._proofread_once：收到 ai_grade/ai_hits → chapter.reasoning["deai_report"] 写入
      与日志输出「AI八股命中 N 处」
  [5] 全链路 mock generate_draft：reasoning 整体重建后 deai_report 不丢（④.3 写入 →
      重建 → 仍在）
  [6] gui_story._chapter_meta_html：有 deai_report → 显示「AI八股治理」行
运行：env\\python.exe _style_check.py
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
TMP = tempfile.mkdtemp(prefix="xhb_style_")
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
storage.INDEX_PATH = os.path.join(storage.PROJECTS_DIR, "index.json")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def make_store(name, with_style=False):
    store = storage.ProjectStore(name)
    p = NovelProject()
    p.title = "文风治理测试"
    p.story_brief = "测试项目。"
    if with_style:
        p.story_style_ref = "文风样本：句子短促有力，动作先行，对话带京腔。"
    store.save_project(p)
    card = CharacterCard("主角", "剑客")
    store.save_character(card, InfoLibrary(card.id))
    return store, p, card.id


def test_write_clause():
    store, p, cid = make_store("w")
    sys_, user = prompts.write_chapter(p, store, 1, "场景", "方向", {}, [],
                                       300, recent_chapters=0)
    for k in ("反「AI八股」", "段落长短随节拍", "对话标签少而自然", "情绪直写且带后果",
              "留白让读者自己脑补", "排比偶尔一两个", "动作或对话收尾",
              "「深吸一口气」", "「眼中闪过一丝」", "「嘴角勾起一抹」", "「不禁」",
              "「缓缓开口」", "「仿佛」"):
        check("写作-含「%s」" % k, k in user, "")


def test_proofread_rules():
    r = prompts.DEFAULT_PROOFREAD_RULES
    for k in ("【四、AI八股文分级治理", "禁用高频套词", "句式套路", "情绪空转",
              "节奏均匀", "对话腔调", "结尾升华", "分级判定与处理",
              "改最少", "删除有上限", "只改怎么说，不改说什么"):
        check("规则-含「%s」" % k, k in r, "")


def test_proofread_prompt():
    store, p, cid = make_store("pr", with_style=True)
    ch = Chapter(1)
    ch.content = "正文。"
    ch.characters = [cid]
    sys_, user = prompts.proofread_chapter(p, store, ch)
    check("校对-含ai_grade字段", '"ai_grade"' in user, "")
    check("校对-含ai_hits字段", '"ai_hits"' in user, "")
    check("校对-有文风样本注入", "参考文风样本" in user and "京腔" in user, "")
    store2, p2, cid2 = make_store("pr2")
    ch2 = Chapter(1)
    ch2.content = "正文。"
    sys_, user2 = prompts.proofread_chapter(p2, store2, ch2)
    check("校对-无样本不注入", "参考文风样本" not in user2, "")
    # v2.58：自定义用户规则时核心八股治理始终追加；默认规则时不重复追加
    sys_, user3 = prompts.proofread_chapter(p, store, ch, rules="用户自定义规则：多用短句。")
    check("v258-自定义规则追加核心段", "AI八股文分级治理（核心治理，始终生效" in user3
          and "用户自定义规则" in user3, "")
    sys_, user4 = prompts.proofread_chapter(p, store, ch, rules="")
    check("v258-默认规则不重复追加", "核心治理，始终生效" not in user4
          and "【四、AI八股文分级治理" in user4, "")


def test_review_degubai():
    store, p, cid = make_store("rev")
    ch = Chapter(1)
    ch.content = "正文。"
    ch.characters = [cid]
    sys_, user = prompts.review_chapter(p, store, ch, "下一章")
    check("审查-含AI八股维度", "AI八股/AI味" in user
          and "重度AI味属明显问题" in user, "")
    check("审查-重写门槛含重度AI味", "重度AI味模板化" in user, "")


def test_proofread_once():
    import config as config_mod
    import engine as engine_mod
    import main_ai as main_ai_mod
    store, p, cid = make_store("po")
    ch = Chapter(1)
    ch.content = "他深吸一口气，眼中闪过一丝寒芒。"
    ch.characters = []
    logs = []
    orig_cfg = config_mod.load_config
    orig_pr = main_ai_mod.proofread_chapter
    try:
        config_mod.load_config = lambda: {"proofread_enabled": True}
        main_ai_mod.proofread_chapter = lambda *a, **k: {
            "content": "他呼出一口气，垂下眼。",
            "notes": ["第一段「深吸一口气」删改", "「眼中闪过一丝」改具体神态"],
            "ai_grade": "中", "ai_hits": 8}
        eng = engine_mod.NovelEngine(store, lambda k, m: logs.append((k, m)))
        notes = eng._proofread_once(p, ch, 300)
    finally:
        config_mod.load_config = orig_cfg
        main_ai_mod.proofread_chapter = orig_pr
    check("校对-notes返回", len(notes) == 2, str(notes))
    check("校对-内容已改", "他呼出一口气" in ch.content and "深吸一口气" not in ch.content, "")
    check("校对-报告入库", ch.reasoning.get("deai_report") == {"grade": "中", "hits": 8},
          str(ch.reasoning.get("deai_report")))
    check("校对-日志含命中", any("AI八股命中 8 处" in m for k, m in logs),
          str([m for k, m in logs if "AI八股" in m]))


def test_pipeline_keep_report():
    """全链路：④.3 写入 deai_report → reasoning 整体重建 → 仍保留。"""
    import config as config_mod
    import engine as engine_mod
    import main_ai as main_ai_mod
    store, p, cid = make_store("pipe")
    logs = []
    orig_cfg = config_mod.load_config
    orig_decide = main_ai_mod.decide_characters
    orig_infer = engine_mod.char_ai.run_inference
    orig_cons = main_ai_mod.consolidate
    orig_write = main_ai_mod.write_chapter
    orig_pr = main_ai_mod.proofread_chapter
    orig_review = main_ai_mod.review_chapter
    try:
        config_mod.load_config = lambda: {
            "reasoning_mode": "sequential", "max_workers": 1,
            "chapter_target_chars": 300, "writer_recent_chapters": 0,
            "web_search_enabled": False, "auto_rewrite": True,
            "proofread_enabled": True}
        main_ai_mod.decide_characters = lambda *a, **k: {
            "scene_focus": "场景", "characters": [{"id": cid}],
            "recall": [], "new_character_hint": ""}
        engine_mod.char_ai.run_inference = lambda *a, **k: {}
        main_ai_mod.consolidate = lambda *a, **k: {
            "verdict": "ok", "approved_direction": "方向",
            "chapter_beats": [], "foreshadows": [], "kb_update": [],
            "need_chapters": [], "search_queries": []}
        main_ai_mod.write_chapter = lambda *a, **k: ("第1章 标题", "正文" * 100)
        main_ai_mod.proofread_chapter = lambda *a, **k: {
            "content": "修正后正文" + "文" * 295, "notes": ["改了一处"],
            "ai_grade": "轻", "ai_hits": 3}
        main_ai_mod.review_chapter = lambda *a, **k: {
            "approved": True, "issues": [], "pacing": "稳"}
        eng = engine_mod.NovelEngine(store, lambda k, m: logs.append((k, m)))
        ch = eng.generate_draft(p)
    finally:
        config_mod.load_config = orig_cfg
        main_ai_mod.decide_characters = orig_decide
        engine_mod.char_ai.run_inference = orig_infer
        main_ai_mod.consolidate = orig_cons
        main_ai_mod.write_chapter = orig_write
        main_ai_mod.proofread_chapter = orig_pr
        main_ai_mod.review_chapter = orig_review
    check("管线-报告保留", (ch.reasoning.get("deai_report") or {}) ==
          {"grade": "轻", "hits": 3}, str(ch.reasoning.get("deai_report")))


def test_meta_html():
    import gui_story
    ch = Chapter(1)
    ch.content = "正文"
    ch.reasoning = {"deai_report": {"grade": "中", "hits": 8}}
    html_text = gui_story._chapter_meta_html(ch, None)
    check("阅读-AI八股治理行", "AI八股治理" in html_text and "命中 8 处" in html_text
          and "等级：中" in html_text, html_text)
    ch2 = Chapter(2)
    ch2.content = "x"
    check("阅读-无报告不显示", "AI八股治理" not in gui_story._chapter_meta_html(ch2, None), "")


def test_style_points():
    """v2.59：风格要点字段往返 + 提炼提示词 + 写作/校对注入 + main_ai 调用。"""
    from models import NovelProject
    p = NovelProject()
    p.story_style_note = "短句推进，动作先行；对话带京腔。"
    d = p.to_dict()
    check("要点-模型往返", NovelProject.from_dict(d).story_style_note ==
          "短句推进，动作先行；对话带京腔。", "")
    d.pop("story_style_note", None)
    check("要点-旧数据回退", NovelProject.from_dict(d).story_style_note == "", "")
    # 提炼提示词：含样本 + 最近章节 + JSON schema；忌空泛条款
    store, p2, cid = make_store("sp", with_style=True)
    from models import Chapter
    ch = Chapter(1)
    ch.content = "夜风卷着雪粒。"
    ch.status = "approved"
    store.save_chapter(ch)
    sys_, user = prompts.extract_style_points(p2, store)
    check("要点-提炼含样本", "参考文风样本" in user and "京腔" in user, "")
    check("要点-提炼含前文", "最近章节正文" in user and "夜风卷着雪粒" in user, "")
    check("要点-提炼含JSON", '"points"' in user and "≤20字" in user, "")
    check("要点-提炼忌空泛", "文笔优美" in user and "行文流畅" in user, "")
    # 写作/校对注入（需先设置 story_style_note）
    p2.story_style_note = "短句推进，动作先行；对话带京腔。"
    store.save_project(p2)
    sys_, user_w = prompts.write_chapter(p2, store, 1, "场景", "方向", {}, [],
                                         300, recent_chapters=0)
    check("要点-写作注入", "【风格要点" in user_w and "对话带京腔" in user_w, "")
    ch2 = Chapter(1)
    ch2.content = "正文。"
    ch2.characters = [cid]
    sys_, user_p = prompts.proofread_chapter(p2, store, ch2)
    check("要点-校对注入", "【风格要点" in user_p and "逐条体现" in user_p, "")
    # 无要点时不注入
    store3, p3, cid3 = make_store("sp3")
    sys_, user_w3 = prompts.write_chapter(p3, store3, 1, "场景", "方向", {}, [],
                                          300, recent_chapters=0)
    check("要点-无要点不注入", "【风格要点" not in user_w3, "")
    # main_ai.extract_style_points 调用链（mock llm）
    import main_ai as main_ai_mod
    orig = main_ai_mod.llm.chat_json
    calls = {}
    main_ai_mod.llm.chat_json = lambda *a, **k: (calls.update(tag=k.get("tag")) or
                                                 {"points": ["短句推进", "动作先行", "京腔对话"]})
    try:
        pts = main_ai_mod.extract_style_points(p2, store)
    finally:
        main_ai_mod.llm.chat_json = orig
    check("要点-main_ai调用", pts == ["短句推进", "动作先行", "京腔对话"]
          and calls.get("tag") == "extract_style", str(pts))
    # 失败返回空列表
    main_ai_mod.llm.chat_json = lambda *a, **k: "bad"
    try:
        pts2 = main_ai_mod.extract_style_points(p2, store)
    finally:
        main_ai_mod.llm.chat_json = orig
    check("要点-失败回退空", pts2 == [], str(pts2))


def main():
    try:
        test_write_clause()
        test_proofread_rules()
        test_proofread_prompt()
        test_review_degubai()
        test_proofread_once()
        test_pipeline_keep_report()
        test_meta_html()
        test_style_points()
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
