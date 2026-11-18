# -*- coding: utf-8 -*-
"""v2.44 全量回归补充：旧版本项目 zip 导入兼容专项（不碰磁盘 config / 真实 projects / API）。

模拟 v2.42 之前导出的老版本项目包（project.json 无新字段、角色卡无 category、无快照目录）：
  [A] 老版 zip 导入成功，新字段 from_dict 回退、设定/角色/章节完整还原
  [B] 新版 zip 往返（export→import）新字段完整保留
  [C] 重名项目自动加 _2 后缀、不覆盖
  [D] 非法包（无 project.json）拒绝
  [E] zip-slip 越界包拒绝
运行：env\\python.exe _legacy_check.py
"""
import json
import os
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import storage
from models import CharacterCard, Chapter, InfoLibrary, NovelProject

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


TMP = tempfile.mkdtemp(prefix="xhb_legacy_")
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)
ZIPDIR = os.path.join(TMP, "zips")
os.makedirs(ZIPDIR, exist_ok=True)


def make_legacy_package(name="旧版项目", with_title=True):
    """构造老版本项目磁盘结构（无新字段/无 category/无快照），返回其目录。"""
    base = os.path.join(TMP, "src_" + name)
    if os.path.exists(base):
        shutil.rmtree(base, ignore_errors=True)
    os.makedirs(os.path.join(base, "characters"))
    os.makedirs(os.path.join(base, "chapters"))
    # 老版 project.json：只含旧字段
    proj = NovelProject()
    proj.title = name
    proj.story_brief = "老版设定-剧情"
    proj.story_world = "老版设定-世界观"
    proj.story_rules = "老版设定-规则"
    proj.story_style = "老版文风"
    proj.volume_target = 10
    d = proj.to_dict()
    for k in ("story_characters", "story_ideas", "story_knowledge"):
        d.pop(k, None)
    if not with_title:
        d.pop("title", None)
    with open(os.path.join(base, "project.json"), "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=2)
    # 老版角色卡：无 category
    card = CharacterCard("老角色", "", card_id="old_char_1")
    card.description = "老版角色描述"
    cd = card.to_dict()
    cd.pop("category", None)
    lib = InfoLibrary(card.id)
    lib.events = [{"chapter": 1, "event": "老事件", "impact": "老影响"}]
    with open(os.path.join(base, "characters", "old_char_1.json"), "w",
              encoding="utf-8") as f:
        json.dump({"card": cd, "library": lib.to_dict()}, f, ensure_ascii=False, indent=2)
    # 老版章节
    ch = Chapter(1)
    ch.title = "第1章 旧章"
    ch.content = "旧章节正文内容。"
    ch.status = "approved"
    with open(os.path.join(base, "chapters", "ch_001.json"), "w",
              encoding="utf-8") as f:
        json.dump(ch.to_dict(), f, ensure_ascii=False, indent=2)
    return base


def zip_dir(src, zip_path, arc_root=None):
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(src):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, src)
                arc = ((arc_root + "/") if arc_root else "") + rel.replace("\\", "/")
                zf.write(full, arc)


def test_legacy_import():
    base = make_legacy_package()
    zpath = os.path.join(ZIPDIR, "legacy.zip")
    zip_dir(base, zpath, arc_root="任意顶层目录名")
    ret = storage.import_project(zpath)
    check("旧版导入-成功返回", ret is not None and ret[1] == "旧版项目", str(ret))
    if not ret:
        return
    dir_name = ret[0]
    store = storage.ProjectStore(dir_name)
    p = store.load_project()
    check("旧版导入-设定完整", p is not None and p.title == "旧版项目"
          and p.story_brief == "老版设定-剧情" and p.story_world == "老版设定-世界观"
          and p.story_rules == "老版设定-规则" and p.story_style == "老版文风"
          and p.volume_target == 10, "")
    check("旧版导入-新字段回退", p.story_characters == [] and p.story_ideas == []
          and p.story_knowledge == "", "chars=%r ideas=%r kb=%r"
          % (p.story_characters, p.story_ideas, p.story_knowledge))
    card, lib = store.load_character("old_char_1")
    check("旧版导入-角色回退", card is not None and card.category == ""
          and card.description == "老版角色描述"
          and lib.events[0]["event"] == "老事件", "category=%r" % (card.category if card else None))
    ch = store.load_chapter(1)
    check("旧版导入-章节完整", ch is not None and ch.title == "第1章 旧章"
          and ch.content == "旧章节正文内容。" and ch.status == "approved", "")


def test_new_roundtrip():
    # 新版导出→导入：新字段完整保留
    store = storage.ProjectStore("新版项目")
    proj = NovelProject()
    proj.title = "新版项目"
    proj.story_characters = [{"name": "主角", "info": "动向"}]
    proj.story_ideas = ["伏笔展开"]
    store.save_project(proj)
    ch = Chapter(1)
    ch.title = "第一章"
    ch.content = "正文"
    store.save_chapter(ch)
    card = CharacterCard("新角色", "", card_id="nc1")
    card.category = "主要角色"
    store.save_character(card)
    zpath = os.path.join(ZIPDIR, "new.zip")
    check("新版导出-成功", storage.export_project("新版项目", zpath), "")
    ret = storage.import_project(zpath)
    check("新版导入-成功", ret is not None and ret[1] == "新版项目", str(ret))
    if not ret:
        return
    p = storage.ProjectStore(ret[0]).load_project()
    check("新版往返-新字段保留", p.story_characters == [{"name": "主角", "info": "动向"}]
          and p.story_ideas == ["伏笔展开"], "chars=%r" % p.story_characters)
    c2, _ = storage.ProjectStore(ret[0]).load_character("nc1")
    check("新版往返-角色分类保留", c2 is not None and c2.category == "主要角色", "")


def test_duplicate_and_bad():
    # 重名：先导入一次，再导入同名包 → 加 _2 后缀且不覆盖
    base = make_legacy_package("重名项目")
    zpath = os.path.join(ZIPDIR, "dup.zip")
    zip_dir(base, zpath)
    r1 = storage.import_project(zpath)
    r2 = storage.import_project(zpath)
    check("重名-后缀不覆盖", r1 is not None and r2 is not None
          and r1[0] != r2[0] and r2[0].endswith("_2")
          and os.path.exists(os.path.join(storage.PROJECTS_DIR, r1[0], "project.json"))
          and os.path.exists(os.path.join(storage.PROJECTS_DIR, r2[0], "project.json")),
          "%s vs %s" % (r1[0], r2[0]))
    # 非法包：无 project.json
    bad = os.path.join(TMP, "bad")
    os.makedirs(bad, exist_ok=True)
    with open(os.path.join(bad, "readme.txt"), "w", encoding="utf-8") as f:
        f.write("x")
    bz = os.path.join(ZIPDIR, "bad.zip")
    zip_dir(bad, bz)
    check("非法包-拒绝", storage.import_project(bz) is None, "")
    # zip-slip 越界
    sz = os.path.join(ZIPDIR, "slip.zip")
    with zipfile.ZipFile(sz, "w") as zf:
        zf.writestr("../../escape/project.json",
                    json.dumps({"title": "越界项目"}, ensure_ascii=False))
    check("zip-slip-拒绝", storage.import_project(sz) is None, "")


def main():
    try:
        test_legacy_import()
        test_new_roundtrip()
        test_duplicate_and_bad()
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
