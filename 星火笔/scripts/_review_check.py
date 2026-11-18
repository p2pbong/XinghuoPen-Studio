# -*- coding: utf-8 -*-
"""v2.44 招式/命名/行为"不尬"审查改动的独立验证（不碰磁盘 config / 不调真实 API）。

验证：正文写作提示词含招式命名与行为约束；主AI审查提示词含新维度且 JSON schema 模板未变；
编辑审稿提示词含招式/行为类别。
运行：env\\python.exe _review_check.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import prompts
import storage
from models import Chapter, NovelProject

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


TMP = tempfile.mkdtemp(prefix="xhb_review_")
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)

project = NovelProject()
project.title = "验证项目"
project.story_brief = "凡人武者宗门世界，主角是外门弟子"
store = storage.ProjectStore("review_proj")
store.save_project(project)
chapter = Chapter(5)
chapter.title = "第5章 试炼"
chapter.content = "他使出一记「九天神雷灭世斩」，瞬间天崩地裂。"
chapter.characters = []

KEY_WRITE = ("化用古代典籍典故", "实力层级相称", "中二堆砌", "不做尬演", "动机",
             "自查总字数", "每幕约", "用词与情景相称", "低于")
KEY_REVIEW = ("招式/技能/法宝/称号等命名是否浮夸违和", "明显到出戏", "实力层级相称",
              "行文与用词是否贴合小说文风", "issues 必须如实列出")
KEY_SCHEMA = ('"approved"', '"issues"', '"rewrite_feedback"', '"brief"',
              '"next_direction"', '"pacing"')
KEY_EDITOR = ("招式/技能/法宝等命名是否浮夸违和", "招式|行为")


def test_write():
    sys_, user = prompts.write_chapter(
        project, store, 5, "试炼场景", "主角迎战对手", {},
        [], 1500, recent_chapters=0)
    for k in KEY_WRITE:
        check("写作-含「%s」" % k, k in user, "")


def test_review():
    sys_, user = prompts.review_chapter(project, store, chapter, "第6章，延续推进")
    for k in KEY_REVIEW:
        check("审查-含「%s」" % k, k in user, "")
    for k in KEY_SCHEMA:
        check("审查-模板字段「%s」未变" % k, k in user, "")
    check("审查-重写门槛措辞", "才 approved=false" in user, "")


def test_editor():
    sys_, user = prompts.editor_review(project, store, chapter)
    for k in KEY_EDITOR:
        check("编辑审稿-含「%s」" % k, k in user or k in sys_, "")


def main():
    try:
        test_write()
        test_review()
        test_editor()
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
