# -*- coding: utf-8 -*-
"""星火笔 v0.51 分卷专项检查（storage 归卷/卷合并/索引/导出按卷，UI 接线）。

运行：env\\python.exe _vol_check.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import storage as storage_mod

PASS = []


def check(name, cond, detail=""):
    PASS.append(bool(cond))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def main():
    tmp = tempfile.mkdtemp(prefix="xhb_vol_")
    base = os.path.join(tmp, "projects")
    os.makedirs(base)
    storage_mod.PROJECTS_DIR = base
    store = storage_mod.ProjectStore("分卷验证")
    # 造 3 章
    for seq, title in [(1, "第一章"), (2, "第二章"), (3, "第三章")]:
        from models import Chapter, CHAPTER_STATUS_APPROVED
        ch = Chapter(seq, volume=1)
        ch.title = title
        ch.content = "正文%d" % seq
        ch.status = CHAPTER_STATUS_APPROVED
        store.save_chapter(ch)

    sums = store.chapter_summaries()
    check("分卷-索引默认卷1", all(m.get("vol", 1) == 1 for _i, m in sums)
          and len(sums) == 3, str([m.get("vol") for _i, m in sums]))

    # 归卷：第 2 章 → 卷 2
    ok = store.set_chapter_volume(2, 2)
    sums = store.chapter_summaries()
    check("分卷-单章归卷", ok and
          {i: m.get("vol") for i, m in sums} == {1: 1, 2: 2, 3: 1},
          str({i: m.get("vol") for i, m in sums}))
    ch = store.load_chapter(2)
    check("分卷-章节文件卷同步", int(ch.volume or 1) == 2, str(ch.volume))

    # 非法卷号拒绝
    check("分卷-非法卷号拒绝", store.set_chapter_volume(2, "abc") is False
          and store.set_chapter_volume(99, 3) is False, "")

    # 卷合并：第 2 卷 → 第 3 卷
    n = store.rename_volume(2, 3)
    sums = store.chapter_summaries()
    check("分卷-整卷合并", n == 1 and
          {i: m.get("vol") for i, m in sums} == {1: 1, 2: 3, 3: 1},
          "n=%d %s" % (n, {i: m.get("vol") for i, m in sums}))
    # 合并后索引重建不丢卷
    meta = store._rebuild_chapter_index()
    check("分卷-索引重建保卷", int(meta[2].get("vol", 1)) == 3, str(meta[2]))

    # 导出按卷：EPUB 含卷标题页
    from export_utils import export_novel_epub
    import models as models_mod
    from models import NovelProject
    proj = NovelProject("分卷验证")
    epub = os.path.join(tmp, "分卷验证.epub")
    check("分卷-EPUB导出", export_novel_epub(proj, store, epub) is True, "")
    import zipfile
    with zipfile.ZipFile(epub) as zf:
        names = zf.namelist()
        vol_pages = [n for n in names if n.startswith("OEBPS/vol")]
        # 叙事顺序 1→3→1（合并产生非连续卷）：每个卷变化段插一页
        check("分卷-EPUB卷页存在", len(vol_pages) == 3, str(vol_pages))
        check("分卷-EPUB卷页标签", zf.read(vol_pages[0]).decode("utf-8").find("第1卷") >= 0
              and zf.read(vol_pages[1]).decode("utf-8").find("第3卷") >= 0, "")

    # 版本号
    check("分卷-版本号v0.51", "v0.5" in open(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "src", "gui_app.py"),
        encoding="utf-8").read(), "")

    # 桌面 UI 接线（源码静态断言）
    gsrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "src", "gui_story.py"), encoding="utf-8").read()
    check("分卷-时间线卷头", "第 %d 卷 · %d 章" in gsrc and "setSpan(r, 0, 1, 6)" in gsrc, "")
    check("分卷-分卷管理按钮", "self.vol_btn" in gsrc and "def _manage_volumes" in gsrc, "")
    check("分卷-导出按卷", '"═" * 24' in gsrc and '"第%d卷"' in gsrc and '"第 %d 卷" % vol' in gsrc, "")

    shutil.rmtree(tmp, ignore_errors=True)
    fails = [i for i, ok in enumerate(PASS) if not ok]
    print("-" * 50)
    if fails:
        print("FAILED %d/%d" % (len(fails), len(PASS)))
        sys.exit(1)
    print("ALL_OK (%d checks)" % len(PASS))


if __name__ == "__main__":
    main()
