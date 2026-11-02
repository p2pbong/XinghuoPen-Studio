# -*- coding: utf-8 -*-
"""v2.43 UI 性能改动的独立回归脚本（不碰磁盘 config / 不调真实 API / 不干扰后台进程）。

覆盖：
  [1] storage.chapter_summaries 索引构建/读取/排序
  [2] 自愈：外部旁路删除章节文件 / 外部改写标题（mtime 变化）→ 自动重建
  [3] save_chapter / delete_chapter 的索引同步
  [4] 千章级性能对比（索引 vs 逐章读全文）
  [5] git_tool 并发提交串行锁
  [6] 离屏 GUI：GeneratePage 日志追加渲染 / 章节管理列表 / 历史下拉走索引

运行方式：在 星火笔 目录执行 python _perf_check.py
"""
import os
import shutil
import sys
import tempfile
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import git_tool
import storage
from models import Chapter, CHAPTER_STATUS_APPROVED, NovelProject

RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


TMP = tempfile.mkdtemp(prefix="xhb_perf_")
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)


def mk_store(name):
    return storage.ProjectStore(name)


def ch(seq, title, content="内容" * 10, status=CHAPTER_STATUS_APPROVED):
    c = Chapter(seq)
    c.title = title
    c.content = content
    c.status = status
    return c


def cleanup():
    shutil.rmtree(TMP, ignore_errors=True)


def test_index():
    store = mk_store("perf_index")
    for s in (3, 1, 2):
        store.save_chapter(ch(s, "标题%d" % s))
    sums = store.chapter_summaries()
    check("索引-构建与排序", [s for s, _ in sums] == [1, 2, 3],
          str([s for s, _ in sums]))
    check("索引-元数据", sums[0][1]["title"] == "标题1"
          and sums[0][1]["status"] == "approved"
          and sums[0][1]["chars"] == len("内容" * 10),
          str(sums[0]))
    # 索引文件已落盘
    ip = store._chapter_index_path()
    check("索引-落盘", os.path.exists(ip) and "chapters" in storage._read_json(ip, {}))
    # save_chapter 更新条目（标题变化后直接反映，无需重建）
    store.save_chapter(ch(2, "新标题2"))
    sums = store.chapter_summaries()
    check("索引-save更新", sums[1][1]["title"] == "新标题2", str(sums[1]))
    # delete_chapter 同步删除条目
    store.delete_chapter(2)
    sums = store.chapter_summaries()
    check("索引-delete同步", [s for s, _ in sums] == [1, 3], str([s for s, _ in sums]))


def test_self_heal():
    store = mk_store("perf_heal")
    for s in (5, 6):
        store.save_chapter(ch(s, "旧%d" % s))
    # 旁路删除（模拟重写/回滚批量删文件，绕过 storage.delete_chapter）
    os.remove(store.chapter_path(5))
    sums = store.chapter_summaries()
    check("自愈-旁路删除", [s for s, _ in sums] == [6], str([s for s, _ in sums]))
    # 旁路改写标题（mtime 变化触发重建）
    p = store.chapter_path(6)
    d = storage._read_json(p)
    d["title"] = "外部改的标题"
    storage._write_json(p, d)
    sums = store.chapter_summaries()
    check("自愈-外部改标题", sums[0][1]["title"] == "外部改的标题", str(sums[0]))
    # 空项目（无 chapters 目录）
    store2 = mk_store("perf_empty")
    sums2 = store2.chapter_summaries()
    check("自愈-空项目", sums2 == [], str(sums2))


def test_perf():
    store = mk_store("perf_1500")
    t0 = time.perf_counter()
    for s in range(1, 1501):
        store.save_chapter(ch(s, "第%d章标题" % s))
    t_write = time.perf_counter() - t0
    t0 = time.perf_counter()
    sums = store.chapter_summaries()
    t_index = time.perf_counter() - t0
    check("性能-1500章索引读取", len(sums) == 1500 and t_index < 0.5,
          "索引读取 %.1fms" % (t_index * 1000))
    t0 = time.perf_counter()
    n = 0
    for s in store.list_chapter_indices():
        c = store.load_chapter(s)
        n += len(c.content or "")
    t_old = time.perf_counter() - t0
    check("性能-旧式逐章读全文", n > 0, "旧式 %.0fms vs 索引 %.1fms（写入 1500 章 %.1fs）"
          % (t_old * 1000, t_index * 1000, t_write))


def test_git_lock():
    repo = os.path.join(TMP, "gitrepo")
    os.makedirs(repo)
    if not git_tool.ensure_repo(repo):
        check("git锁-跳过(无git)", True, "git 不可用")
        return
    import subprocess
    # 临时仓库无身份配置时 commit 会失败，先补一份本地身份
    subprocess.run(["git", "config", "user.email", "perf@test"], cwd=repo,
                   capture_output=True)
    subprocess.run(["git", "config", "user.name", "perf"], cwd=repo,
                   capture_output=True)
    ok = []
    msgs = ["c%d" % i for i in range(4)]

    def worker(i):
        with open(os.path.join(repo, "f%d.txt" % i), "w", encoding="utf-8") as f:
            f.write("x" * 100)
        git_tool.commit(repo, msgs[i])
        ok.append(i)

    ts = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    r = subprocess_check(repo)
    tracked = 0
    import subprocess
    ls = subprocess.run(["git", "ls-files"], cwd=repo, capture_output=True,
                        text=True, encoding="utf-8", errors="ignore")
    tracked = len([l for l in ls.stdout.splitlines() if l.strip()])
    # 语义：git add -A 串行提交会把并发期的文件并入第一个提交（无丢失、仓库干净）
    check("git锁-并发4提交", r["clean"] and tracked == 4 and len(ok) == 4,
          "commits=%d tracked=%d clean=%s" % (r["count"], tracked, r["clean"]))


def subprocess_check(repo):
    import subprocess
    out = subprocess.run(["git", "log", "--oneline"], cwd=repo, capture_output=True,
                         text=True, encoding="utf-8", errors="ignore")
    n = len([l for l in out.stdout.splitlines() if l.strip()])
    st = subprocess.run(["git", "status", "--porcelain"], cwd=repo,
                        capture_output=True, text=True, encoding="utf-8",
                        errors="ignore")
    return {"count": n, "clean": not st.stdout.strip()}


def test_gui():
    import gui_app
    from PySide6.QtWidgets import QApplication
    import gui_generate
    qapp = QApplication.instance() or QApplication([])
    # 临时项目载入 APP（需 project.json 才能被 current_project 读到）
    store = mk_store("perf_gui")
    proj = NovelProject()
    proj.title = "性能测试"
    store.save_project(proj)
    for s in (1, 2):
        store.save_chapter(ch(s, "界面章%d" % s))
    gui_app.APP["project_dir"] = "perf_gui"
    page = gui_generate.GeneratePage(None)
    # 日志追加渲染
    page._on_log("info", "测试日志A")
    page._on_log("warn", "带<尖括号>B")
    html_txt = page.log_view.toHtml()
    check("GUI-日志追加", "测试日志A" in html_txt and "带&lt;尖括号&gt;B" in html_txt,
          "len=%d" % len(page._log_items))
    # 超量裁剪重建（原逻辑：超过 600 条裁剪到最近 300，之后继续追加）
    for i in range(700):
        page._on_log("info", "日志%d" % i)
    check("GUI-日志裁剪", len(page._log_items) <= 601,
          "items=%d" % len(page._log_items))
    check("GUI-日志裁剪后仍可读", "日志699" in page.log_view.toHtml())
    # 历史下拉走索引
    store2, project = gui_app.current_project()
    page._refresh_history(store2, project)
    check("GUI-历史下拉", page.hist_combo.count() == 2
          and page.hist_combo.itemText(0).startswith("第1章·界面章1"),
          "count=%d first=%s" % (page.hist_combo.count(),
                                 page.hist_combo.itemText(0) if page.hist_combo.count() else ""))
    # 章节管理对话框列表走索引
    dlg = gui_generate.ChapterManagerDialog(None)
    check("GUI-章节管理列表", dlg.listw.count() == 2
          and "界面章1" in dlg.listw.item(0).text() and "· 20字" in dlg.listw.item(0).text(),
          "count=%d item0=%s" % (dlg.listw.count(),
                                 dlg.listw.item(0).text() if dlg.listw.count() else ""))
    # 后台完成信号处理：按钮恢复可用、列表刷新
    dlg._set_busy(True)
    dlg._on_bg_done(("edit", 1))
    check("GUI-后台完成恢复按钮", dlg._bg_busy is False and dlg.edit_btn.isEnabled(),
          "busy=%s edit_enabled=%s" % (dlg._bg_busy, dlg.edit_btn.isEnabled()))
    dlg.close()
    page._on_log("info", "结束")
    qapp.processEvents()


def main():
    try:
        test_index()
        test_self_heal()
        test_perf()
        test_git_lock()
        test_gui()
    finally:
        cleanup()
    fails = [r for r in RESULTS if not r[1]]
    print("-" * 60)
    if fails:
        print("FAILED %d/%d:" % (len(fails), len(RESULTS)))
        for n, _, d in fails:
            print("  FAIL %s %s" % (n, d))
        sys.exit(1)
    print("ALL_OK (%d checks)" % len(RESULTS))


if __name__ == "__main__":
    main()
