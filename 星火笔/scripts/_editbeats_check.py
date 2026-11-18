# -*- coding: utf-8 -*-
"""v2.55 剧情点可编辑（beats_override 接管 + 生成页编辑框）的独立验证（不碰磁盘 config / 真实 API）。

覆盖：
  [1] engine.generate_draft 全链路 mock：consolidate 规划 beatsA，beats_override=B →
      write/review 收到 B、reasoning["beats"]==B、日志标「用户指定」；
      override 为空 → 沿用主AI规划 A
  [2] 离屏 GUI·生成页：beats_edit 存在；_on_draft 回填剧情点；_current_beats 过滤空行、
      空输入返回 None；无 beats 清空
  [3] 引擎 override 清洗：超 4 条截断（走 _clean_beats）
运行：env\\python.exe _editbeats_check.py
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
from models import CharacterCard, InfoLibrary, NovelProject

RESULTS = []
TMP = tempfile.mkdtemp(prefix="xhb_eb_")
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
storage.INDEX_PATH = os.path.join(storage.PROJECTS_DIR, "index.json")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def make_store(name):
    store = storage.ProjectStore(name)
    p = NovelProject()
    p.title = "剧情点编辑测试"
    p.story_brief = "测试项目。"
    store.save_project(p)
    card = CharacterCard("主角", "剑客")
    store.save_character(card, InfoLibrary(card.id))
    return store, p, card.id


def run_pipeline(beats_override):
    """全链路 mock：consolidate 规划 beatsA；可选 beats_override。返回 (chapter, got, logs)。"""
    import config as config_mod
    import engine as engine_mod
    import main_ai as main_ai_mod
    store, p, cid = make_store("e2e")
    logs = []
    got = {"write_beats": None, "review_beats": None}

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
            "web_search_enabled": False, "auto_rewrite": True}
        main_ai_mod.decide_characters = lambda *a, **k: {
            "scene_focus": "潜入城主府", "characters": [{"id": cid}],
            "recall": [], "new_character_hint": ""}
        engine_mod.char_ai.run_inference = lambda *a, **k: {}
        main_ai_mod.consolidate = lambda *a, **k: {
            "verdict": "ok", "approved_direction": "深夜潜入城主府",
            "chapter_beats": ["主AI规划点一", "主AI规划点二"],
            "foreshadows": [], "kb_update": [], "need_chapters": [],
            "search_queries": []}

        def fake_write(project, store, ch_no, scene, direction, infer, fs_lines,
                       target, fb="", recent_chapters=3, max_tokens=None,
                       draft="", beats=None, planning_note=None, cliche_watch=None):
            got["write_beats"] = beats
            return "第1章 潜入", "正" * 300

        def fake_review(project, store, chapter, target, beats=None):
            got["review_beats"] = beats
            return {"approved": True, "issues": [], "pacing": "稳"}

        main_ai_mod.write_chapter = fake_write
        main_ai_mod.review_chapter = fake_review

        eng = engine_mod.NovelEngine(store, lambda k, m: logs.append((k, m)))
        chapter = eng.generate_draft(p, beats_override=beats_override)
    finally:
        config_mod.load_config = orig_cfg
        main_ai_mod.decide_characters = orig_decide
        engine_mod.char_ai.run_inference = orig_infer
        main_ai_mod.consolidate = orig_cons
        main_ai_mod.write_chapter = orig_write
        main_ai_mod.review_chapter = orig_review
    return chapter, got, logs


def test_override():
    # 用户指定 → 接管主AI规划
    chapter, got, logs = run_pipeline(["用户点一", "用户点二"])
    check("接管-write收到用户点", got["write_beats"] == ["用户点一", "用户点二"],
          str(got["write_beats"]))
    check("接管-review收到用户点", got["review_beats"] == ["用户点一", "用户点二"], "")
    check("接管-reasoning存档用户点", (chapter.reasoning.get("beats") or []) ==
          ["用户点一", "用户点二"], str(chapter.reasoning.get("beats")))
    check("接管-日志标用户指定", any("用户指定" in m for k, m in logs), "")
    # 留空 → 沿用主AI规划
    chapter2, got2, logs2 = run_pipeline(None)
    check("默认-沿用主AI规划", got2["write_beats"] == ["主AI规划点一", "主AI规划点二"],
          str(got2["write_beats"]))
    check("默认-reasoning存主AI规划", (chapter2.reasoning.get("beats") or []) ==
          ["主AI规划点一", "主AI规划点二"], "")
    check("默认-日志不标用户指定", not any("用户指定" in m for k, m in logs2), "")
    # 空列表同留空
    chapter3, got3, _ = run_pipeline([])
    check("默认-空列表同留空", got3["write_beats"] == ["主AI规划点一", "主AI规划点二"], "")


def test_gui():
    import gui_app
    import gui_generate
    from models import Chapter
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])
    store, p, cid = make_store("gui")
    gui_app.APP["project_dir"] = "gui"
    page = gui_generate.GeneratePage(None)
    check("GUI-beats_edit存在", hasattr(page, "beats_edit"), "")
    ch = Chapter(1)
    ch.content = "正文"
    ch.reasoning = {"beats": ["潜入偷账册", "摊牌"]}
    page._on_draft(ch)
    txt = page.beats_edit.toPlainText()
    check("GUI-回填剧情点", "潜入偷账册" in txt and "摊牌" in txt, txt)
    page.beats_edit.setPlainText("改成我的剧情点\n\n第二点")
    beats = page._current_beats()
    check("GUI-过滤空行", beats == ["改成我的剧情点", "第二点"], str(beats))
    page.beats_edit.setPlainText("  \n  ")
    check("GUI-空输入None", page._current_beats() is None, str(page._current_beats()))
    page.beats_edit.setPlainText("点A\n点B\n点C\n点D\n点E")
    beats5 = page._current_beats()
    import engine as engine_mod
    check("GUI-超4条走清洗", len(engine_mod._clean_beats(beats5)) == 4, str(beats5))
    ch2 = Chapter(2)
    ch2.reasoning = {}
    page._on_draft(ch2)
    check("GUI-无beats清空", page.beats_edit.toPlainText() == "", "")
    page.close()
    qapp.processEvents()


def main():
    try:
        test_override()
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
