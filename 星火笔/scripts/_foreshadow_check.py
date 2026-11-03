# -*- coding: utf-8 -*-
"""v2.51 伏笔看板（逾期提醒 + 回收率统计 + 一键回收）的独立验证（不碰磁盘 config / 真实 API）。

覆盖：
  [1] prompts._overdue_mark / open_foreshadows_text：逾期标注（埋设后超阈值）、
      未逾期不标、已回收不标、无埋设章不标；阈值参数可调
  [2] 注入检查：decide_characters / consolidate / compress_summary 的伏笔清单含逾期标注；
      review_chapter 有【逾期伏笔提醒】段（有逾期时有、无逾期时无）；update_world 组装
      伏笔 ID 附逾期标注
  [3] 离屏 GUI：StoryPage 伏笔看板构建（stats/按钮/表格列）、_fill_foreshadows 统计文本
      （待回收/已回收/逾期/回收率）、标记已回收流程（选中行→确认→状态变化+统计更新）、
      恢复待回收流程、误选非目标行提示
运行：env\\python.exe _foreshadow_check.py
"""
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # 控制台 GBK 打不出 ⚠ 等字符

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

import prompts
import storage
from models import Foreshadow, NovelProject

RESULTS = []
TMP = tempfile.mkdtemp(prefix="xhb_fs_")
# 与 _lore_check 同款：INDEX_PATH 在 storage 导入时已冻结为真实路径，必须一并 patch
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
storage.INDEX_PATH = os.path.join(storage.PROJECTS_DIR, "index.json")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def make_store(name, with_chapter=25):
    """建一个含伏笔的项目 store。with_chapter=当前已写章节数。"""
    store = storage.ProjectStore(name)
    p = NovelProject()
    p.title = "伏笔看板测试"
    p.story_brief = "测试项目。"
    p.state["next_chapter"] = with_chapter + 1
    store.save_project(p)
    fs = [Foreshadow("主角左手的旧伤会复发", "plant", "主角"),
          Foreshadow("铜钥匙与身世有关", "plant", "主角"),
          Foreshadow("城主府的地下密道", "plant", "")]
    fs[0].planted_chapter = 3
    fs[1].planted_chapter = 10
    fs[2].planted_chapter = 1
    store.save_foreshadows(fs)
    return store, p


def test_overdue_mark():
    fs = [
        Foreshadow("埋得久", "plant", ""),
        Foreshadow("刚埋", "plant", ""),
        Foreshadow("已回收", "plant", ""),
        Foreshadow("无埋设章", "plant", ""),
    ]
    fs[0].planted_chapter = 3
    fs[1].planted_chapter = 20
    fs[2].planted_chapter = 3
    fs[2].status = "resolved"
    fs[2].resolved_chapter = 22
    fs[3].planted_chapter = 0
    # 当前 25 章，阈值 15：3 章埋的 gap=22 > 15 → 逾期；20 章埋的 gap=5 → 不逾期
    check("逾期-埋得久标逾期", prompts._overdue_mark(fs[0], 25) == "⚠逾期22章",
          prompts._overdue_mark(fs[0], 25))
    check("逾期-刚埋不标", prompts._overdue_mark(fs[1], 25) == "", "")
    check("逾期-已回收不标", prompts._overdue_mark(fs[2], 25) == "", "")
    check("逾期-无埋设章不标", prompts._overdue_mark(fs[3], 25) == "", "")
    # 阈值边界：gap == 阈值不逾期（> 才算）
    check("逾期-边界不标", prompts._overdue_mark(fs[0], 18) == "", "gap=15 应不逾期")
    check("逾期-边界超标", prompts._overdue_mark(fs[0], 19) == "⚠逾期16章", "")
    # open_foreshadows_text 输出含/不含标注
    text = prompts.open_foreshadows_text(fs, current_no=25)
    check("清单-含逾期标注", "⚠逾期22章" in text, "")
    check("清单-不含刚埋标注", "⚠逾期5章" not in text, "")
    check("清单-已回收不标", text.count("⚠") == 1, "")


def test_injection():
    store, p = make_store("inj", with_chapter=25)
    # 决断/校验的伏笔清单含逾期标注
    sys_, user = prompts.decide_characters(p, store, 26, 1, 26)
    check("注入-决断含逾期标注", "⚠逾期" in user, "")
    sys_, user = prompts.consolidate(p, store, 26, "场景", {})
    check("注入-校验含逾期标注", "⚠逾期" in user, "")
    # 压缩环节：逾期伏笔被标注并提示优先回收
    sys_, user = prompts.compress_summary(p, store, recent=3)
    check("注入-压缩含逾期标注", "⚠逾期" in user and "优先安排回收" in user, "")
    # 审查环节：有逾期 → 出现【逾期伏笔提醒】；无逾期 → 不出现
    store2, p2 = make_store("inj2", with_chapter=5)
    ch = store2.load_chapter  # 不存在章节也没关系，review 只读 content 字段
    from models import Chapter
    ch = Chapter(5)
    ch.content = "正文。"
    ch.characters = []
    sys_, user = prompts.review_chapter(p2, store2, ch, "下一章")
    check("注入-无逾期审查无提醒", "优先考虑回收其中一条" not in user, "")
    sys_, user = prompts.review_chapter(p, store, ch, "下一章")
    check("注入-有逾期审查有提醒", "【逾期伏笔提醒" in user
          and "优先考虑回收其中一条" in user, "")
    check("注入-审查要求含逾期说明条款", "逾期伏笔：若上方给出" in user, "")
    # 战后更新：伏笔 ID 附逾期标注
    import main_ai as main_ai_mod
    orig = main_ai_mod.llm.chat_json
    calls = {}
    main_ai_mod.llm.chat_json = lambda *a, **k: (calls.update(user=a[1]) or {})
    try:
        main_ai_mod.update_world(p, store, ch)
    finally:
        main_ai_mod.llm.chat_json = orig
    check("注入-战后ID含逾期标注", "⚠逾期" in calls.get("user", ""), "")


def test_gui():
    import gui_app
    import gui_story
    from PySide6.QtWidgets import QApplication, QMessageBox
    qapp = QApplication.instance() or QApplication([])
    store, p = make_store("gui_fs", with_chapter=25)
    gui_app.APP["project_dir"] = "gui_fs"
    page = gui_story.StoryPage(None)
    check("GUI-看板控件存在", hasattr(page, "fore_stats")
          and hasattr(page, "fore_resolve_btn") and hasattr(page, "fore_reopen_btn")
          and hasattr(page, "fore_table"), "")
    page.refresh_all()
    stats = page.fore_stats.text()
    # 埋设章 3→gap22、10→gap15(边界不逾期)、1→gap24：待回收3、已回收0、逾期2、回收率0%
    check("GUI-统计文本", "待回收 3" in stats and "已回收 0" in stats
          and "⚠逾期 2" in stats and "回收率 0%（0/3）" in stats, stats)
    # 逾期行状态列显示 ⚠ 逾期
    check("GUI-逾期行标红", page.fore_table.item(0, 0).text() == "⚠ 逾期", "")
    # 全程打桩确认/提示弹窗（离屏环境不能等人工点击）
    orig_q = QMessageBox.question
    orig_i = QMessageBox.information
    QMessageBox.question = lambda *a, **k: QMessageBox.StandardButton.Yes
    QMessageBox.information = lambda *a, **k: QMessageBox.StandardButton.Ok
    try:
        # 选中第一行（逾期待回收）→ 标记已回收
        page.fore_table.selectRow(0)
        page._fore_resolve()
        stats2 = page.fore_stats.text()
        check("GUI-标记后统计", "待回收 2" in stats2 and "已回收 1" in stats2
              and "回收率 33%" in stats2, stats2)
        fs = store.load_foreshadows()
        check("GUI-标记落盘", fs[0].status == "resolved" and fs[0].resolved_chapter == 25,
              "status=%s rc=%s" % (fs[0].status, fs[0].resolved_chapter))
        # 误选：行 0 已回收，再点「标记已回收」→ 无待回收可选，提示且状态不变
        page.fore_table.selectRow(0)
        page._fore_resolve()
        fs = store.load_foreshadows()
        check("GUI-误选不崩溃且不变", fs[0].status == "resolved", "")
        # 恢复待回收：选中已回收行 → 恢复
        page.fore_table.selectRow(0)
        page._fore_reopen()
        fs = store.load_foreshadows()
        check("GUI-恢复待回收", fs[0].status == "open" and fs[0].resolved_chapter == 0, "")
        # 无选中行点按钮 → 提示不崩溃
        page.fore_table.clearSelection()
        page._fore_resolve()
        check("GUI-无选中不崩溃", True, "")
    finally:
        QMessageBox.question = orig_q
        QMessageBox.information = orig_i
    page.close()
    qapp.processEvents()


def main():
    try:
        test_overdue_mark()
        test_injection()
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
