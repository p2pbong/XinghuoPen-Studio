# -*- coding: utf-8 -*-
"""v2.50 设定锚点（项目 Lorebook）+ 审查设定一致性 + EPUB 导出的独立验证（不碰磁盘 config / 真实 API）。

覆盖：
  [1] NovelProject.lore_entries 字段往返 + 旧数据（无该字段）回退 + 脏数据（空内容/非dict）过滤
  [2] prompts.fmt_lore：常驻必注入 / 关键词命中注入 / 未命中不注入 / 空列表返回空 / 上限 10 条 / 内容截断 400 字
  [3] 注入检查：decide_characters / consolidate / write_chapter / review_chapter /
      update_after_chapter / editor_review 六环节含锚点段（有锚点时有、无锚点时无）；
      write_chapter 写作要求含「设定锚点」遵守条款（有条件注入）
  [4] review_chapter 新增「设定一致性」审查维度；editor_review issues 类别含「设定」
  [5] 世界快照 save/rollback 不动 lore_entries（用户内容，不随世界回滚）
  [6] 项目 zip 导出→导入后 lore_entries 完整保留（老包无字段回退 []）
  [7] 离屏 GUI：ProjectPage 设定锚点页签/列表/按钮存在、on_show 刷新列表、LoreEntryDialog 构造与 value()
  [8] EPUB 导出：mimetype 首文件且 STORED、container.xml/content.opf/nav/toc.ncx 结构、
      章节转义（<>&）、标题页含书名与设定、无章节返回 False
运行：env\\python.exe _lore_check.py
"""
import os
import shutil
import sys
import tempfile
import zipfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import export_utils
import prompts
import storage
from models import Chapter, NovelProject

RESULTS = []
TMP = tempfile.mkdtemp(prefix="xhb_lore_")
# 注意：INDEX_PATH 在 storage 导入时已冻结为真实路径，必须一并 patch 到临时目录，
# 否则 import_project 会把条目写进真实 projects/index.json（幻影条目）
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
storage.INDEX_PATH = os.path.join(storage.PROJECTS_DIR, "index.json")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def sample_entries():
    return [
        {"id": "a1", "title": "主角断臂", "keys": [], "content": "主角左臂已断，以符文义肢代替，不能做重活。",
         "always": True},
        {"id": "a2", "title": "铁砧城", "keys": ["铁砧城", "城主府"], "content": "铁砧城垄断符文钢矿脉，城内严禁私斗。",
         "always": False},
        {"id": "a3", "title": "北境", "keys": ["北境"], "content": "北境终年积雪，一年只有三个月能通行商路。",
         "always": False},
    ]


def test_model_roundtrip():
    p = NovelProject()
    p.lore_entries = sample_entries()
    d = p.to_dict()
    p2 = NovelProject.from_dict(d)
    check("模型-往返", p2.lore_entries[0]["title"] == "主角断臂"
          and p2.lore_entries[0]["always"] is True
          and p2.lore_entries[1]["keys"] == ["铁砧城", "城主府"], str(p2.lore_entries))
    check("模型-关键词保留", p2.lore_entries[2]["keys"] == ["北境"], "")
    # 旧数据（无字段）回退
    d.pop("lore_entries", None)
    p3 = NovelProject.from_dict(d)
    check("模型-旧数据回退", p3.lore_entries == [], "")
    # 脏数据过滤：非 dict / 空内容
    d["lore_entries"] = ["bad", {"title": "无内容", "keys": [], "content": "   ", "always": False},
                         {"title": "ok", "keys": [], "content": "有效内容", "always": True}]
    p4 = NovelProject.from_dict(d)
    check("模型-脏数据过滤", len(p4.lore_entries) == 1
          and p4.lore_entries[0]["title"] == "ok", str(p4.lore_entries))


def test_fmt_lore():
    p = NovelProject()
    p.lore_entries = sample_entries()
    # 常驻必注入（无扫描文本也注入）
    out = prompts.fmt_lore(p, "")
    check("锚点-常驻无扫描也注入", "主角断臂" in out and "主角左臂已断" in out, "")
    # 关键词命中注入
    out = prompts.fmt_lore(p, "一行人抵达铁砧城，城主府在望。")
    check("锚点-关键词命中注入", "铁砧城" in out and "严禁私斗" in out, "")
    # 未命中不注入（北境条目不带）
    check("锚点-未命中不注入", "北境" not in out, "")
    out = prompts.fmt_lore(p, "北境的雪下了三天三夜。")
    check("锚点-北境命中", "北境" in out and "终年积雪" in out, "")
    # 空列表返回空
    p2 = NovelProject()
    check("锚点-空列表返回空", prompts.fmt_lore(p2, "任意文本") == "", "")
    # 上限 10 条
    p3 = NovelProject()
    p3.lore_entries = [{"id": "x%d" % i, "title": "T%d" % i, "keys": ["k%d" % i],
                        "content": "内容%d" % i, "always": True} for i in range(15)]
    out = prompts.fmt_lore(p3, "k13 k14")
    check("锚点-上限10条", out.count("■") == 10, "count=%d" % out.count("■"))
    # 内容截断 400 字
    p4 = NovelProject()
    p4.lore_entries = [{"id": "c1", "title": "长文", "keys": [], "content": "字" * 600, "always": True}]
    out = prompts.fmt_lore(p4, "")
    check("锚点-内容截断400字", out.count("字") == 400, "count=%d" % out.count("字"))


def make_store(name, with_lore=True, with_chapters=2):
    """建一个含锚点（可选）+ 章节（可选）的临时项目 store。"""
    store = storage.ProjectStore(name)
    p = NovelProject()
    p.title = "锚点测试"
    p.story_brief = "一本测试用的架空小说。"
    if with_lore:
        p.lore_entries = sample_entries()
    store.save_project(p)
    for i in range(1, with_chapters + 1):
        ch = Chapter(i)
        ch.title = "第%d章" % i
        ch.content = "第%d章正文：主角在铁砧城城主府调查账册。" % i
        ch.status = "approved"
        store.save_chapter(ch)
    return store, p


def test_injection():
    store, p = make_store("inj")
    # 六环节有锚点时均含锚点段
    sys_, user = prompts.decide_characters(p, store, 3, 1, 3)
    check("注入-决断含锚点", "【项目设定锚点" in user, "")
    sys_, user = prompts.consolidate(p, store, 3, "主角到铁砧城", {"c": {}})
    check("注入-校验含锚点", "【项目设定锚点" in user, "")
    sys_, user = prompts.write_chapter(p, store, 3, "主角到铁砧城", "推进调查", {}, [],
                                       2500, recent_chapters=0)
    check("注入-写作含锚点", "【项目设定锚点" in user and "主角左臂已断" in user, "")
    check("注入-写作含锚点遵守条款", "严格遵循【项目设定锚点】" in user, "")
    ch = store.load_chapter(1)
    sys_, user = prompts.review_chapter(p, store, ch, "下一章")
    check("注入-审查含锚点", "【项目设定锚点" in user, "")
    sys_, user = prompts.update_after_chapter(p, store, ch, [])
    check("注入-战后含锚点", "【项目设定锚点" in user, "")
    sys_, user = prompts.editor_review(p, store, ch)
    check("注入-编辑审稿含锚点", "【项目设定锚点" in user, "")
    # 无锚点时各环节不含锚点段
    store2, p2 = make_store("inj2", with_lore=False)
    sys_, user = prompts.write_chapter(p2, store2, 3, "主角到铁砧城", "推进调查", {}, [],
                                       2500, recent_chapters=0)
    check("注入-无锚点不注入", "【项目设定锚点" not in user
          and "严格遵循【项目设定锚点】" not in user, "")
    sys_, user = prompts.review_chapter(p2, store2, store2.load_chapter(1), "下一章")
    check("注入-无锚点审查不注入", "严禁私斗" not in user and "左臂已断" not in user, "")


def test_review_dimension():
    store, p = make_store("rev")
    ch = store.load_chapter(1)
    sys_, user = prompts.review_chapter(p, store, ch, "下一章")
    check("审查-设定一致性维度", "设定一致性" in user and "对照【项目设定锚点】" in user, "")
    check("审查-重写门槛含锚点冲突", "与锚点明显冲突" in user, "")
    sys_, user = prompts.editor_review(p, store, ch)
    check("审稿-设定类别", "|设定|" in user, "")
    check("审稿-设定一致性提及", "设定一致性" in (sys_ + user), "")


def test_snapshot_keeps_lore():
    store, p = make_store("snap")
    # 存档快照（v2.50 起：锚点是用户内容，不随世界快照回滚）
    store.save_world_snapshot(2)
    snap = store.load_world_snapshot(2)
    check("快照-不含锚点字段", "lore_entries" not in snap, "")
    # 改动锚点后回滚，锚点保持现状（不被世界回滚动）
    p.lore_entries = [{"id": "z1", "title": "后来加的", "keys": [], "content": "后来新增的锚点", "always": True}]
    store.save_project(p)
    store.rollback_world(snap)
    p2 = store.load_project()
    check("快照-回滚不动锚点", len(p2.lore_entries) == 1
          and p2.lore_entries[0]["title"] == "后来加的", str(p2.lore_entries))


def test_project_zip_roundtrip():
    store, p = make_store("zipproj")
    zip_path = os.path.join(TMP, "proj_export.zip")
    ok = storage.export_project("zipproj", zip_path)
    check("项目包-导出", ok, "")
    # 改名导入（避免重名后缀干扰断言）
    import shutil as _sh
    zip2 = os.path.join(TMP, "proj_import.zip")
    _sh.copyfile(zip_path, zip2)
    ret = storage.import_project(zip2)
    check("项目包-导入", ret is not None, str(ret))
    dir_name = ret[0]
    store2 = storage.ProjectStore(dir_name)
    p2 = store2.load_project()
    check("项目包-锚点保留", len(p2.lore_entries) == 3
          and p2.lore_entries[0]["title"] == "主角断臂", str(p2.lore_entries))
    # 老包（无锚点字段）导入回退 []
    p3 = NovelProject()
    d = p3.to_dict()
    d.pop("lore_entries", None)
    old_dir = "oldproj"
    os.makedirs(os.path.join(storage.PROJECTS_DIR, old_dir), exist_ok=True)
    import json as _json
    with open(os.path.join(storage.PROJECTS_DIR, old_dir, "project.json"), "w",
              encoding="utf-8") as f:
        _json.dump(d, f, ensure_ascii=False)
    store3 = storage.ProjectStore(old_dir)
    p4 = store3.load_project()
    check("项目包-老数据回退", p4.lore_entries == [], "")


def test_epub():
    store, p = make_store("epub", with_chapters=2)
    # 章节正文带特殊字符（验证转义）
    ch = store.load_chapter(1)
    ch.content = "正文含 <标记> 与 & 符号，以及\"引号\"。\n\n第二段。"
    ch.title = "第1章 开局<测试>"
    store.save_chapter(ch)
    out = os.path.join(TMP, "test.epub")
    ok = export_utils.export_novel_epub(p, store, out)
    check("EPUB-导出成功", ok, "")
    with zipfile.ZipFile(out) as zf:
        names = zf.namelist()
        check("EPUB-mimetype首文件", names[0] == "mimetype", names[0] if names else "empty")
        info = zf.getinfo("mimetype")
        check("EPUB-mimetype无压缩", info.compress_type == zipfile.ZIP_STORED, "")
        check("EPUB-mimetype内容", zf.read("mimetype").decode() == "application/epub+zip", "")
        check("EPUB-container存在", "META-INF/container.xml" in names, "")
        opf = zf.read("OEBPS/content.opf").decode("utf-8")
        check("EPUB-opf含章节", "chap0001.xhtml" in opf and "chap0002.xhtml" in opf
              and "nav.xhtml" in opf and "toc.ncx" in opf, "")
        nav = zf.read("OEBPS/nav.xhtml").decode("utf-8")
        check("EPUB-nav含章节标题", "第1章" in nav and "第2章" in nav, "")
        ncx = zf.read("OEBPS/toc.ncx").decode("utf-8")
        check("EPUB-ncx含章节", "chap0001.xhtml" in ncx and "chap0002.xhtml" in ncx, "")
        chap1 = zf.read("OEBPS/chap0001.xhtml").decode("utf-8")
        check("EPUB-章节转义", "&lt;标记&gt;" in chap1 and "&amp;" in chap1
              and "&quot;" in chap1, "")
        check("EPUB-章节标题转义", "第1章 开局&lt;测试&gt;" in chap1, "")
        title_pg = zf.read("OEBPS/title.xhtml").decode("utf-8")
        check("EPUB-封面含书名与设定", "锚点测试" in title_pg and "一本测试用的架空小说" in title_pg, "")
    # 无章节 → False
    store2 = storage.ProjectStore("epub_empty")
    p2 = NovelProject()
    p2.title = "空书"
    store2.save_project(p2)
    check("EPUB-无章节返回False", not export_utils.export_novel_epub(p2, store2,
          os.path.join(TMP, "empty.epub")), "")


def test_gui():
    import gui_app
    import gui_project
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])
    store, p = make_store("gui_lore")
    gui_app.APP["project_dir"] = "gui_lore"
    page = gui_project.ProjectPage(None)
    check("GUI-锚点控件存在", hasattr(page, "lore_list")
          and hasattr(page, "lore_add_btn") and hasattr(page, "lore_edit_btn")
          and hasattr(page, "lore_del_btn"), "")
    page.on_show()
    check("GUI-锚点列表刷新", page.lore_list.count() == 3
          and "主角断臂" in page.lore_list.item(0).text(), "count=%d" % page.lore_list.count())
    # 编辑弹窗构造与取值
    dlg = gui_project.LoreEntryDialog(None, p.lore_entries[0])
    dlg.keys.setText("铁砧城,城主府")
    dlg.always.setChecked(False)
    v = dlg.value()
    check("GUI-弹窗取值", v["title"] == "主角断臂" and v["keys"] == ["铁砧城", "城主府"]
          and v["always"] is False and v["content"], str(v))
    # 新增一条件入并刷新（走 _lore_save_entries 主流程）
    dlg2 = gui_project.LoreEntryDialog(None)
    dlg2.title.setText("新条目")
    dlg2.content.setPlainText("新内容")
    dlg2.always.setChecked(True)
    page._lore_save_entries((p.lore_entries or []) + [dlg2.value()])
    check("GUI-新增后列表", page.lore_list.count() == 4, "")
    # 删除流程（确认弹窗打桩为「是」，离屏环境不能等人工点击）
    from PySide6.QtWidgets import QMessageBox
    orig_question = gui_project.QMessageBox.question
    gui_project.QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.Yes
    try:
        page.lore_list.setCurrentRow(0)
        page._lore_del()
    finally:
        gui_project.QMessageBox.question = orig_question
    check("GUI-删除后列表", page.lore_list.count() == 3, "")
    page.close()
    qapp.processEvents()


def main():
    try:
        test_model_roundtrip()
        test_fmt_lore()
        test_injection()
        test_review_dimension()
        test_snapshot_keeps_lore()
        test_project_zip_roundtrip()
        test_epub()
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
