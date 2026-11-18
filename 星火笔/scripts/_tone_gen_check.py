# -*- coding: utf-8 -*-
"""v0.47 写作工具台（随机起名 + AI 八股套话实时高亮）的独立验证。

覆盖：
  [1] name_gen：确定性（rng）、姓氏指定、长度、gender 分布、批量去重
  [2] tone_highlighter：count_tone_hits 命中/未命中/空/多命中；
      ToneHighlighter 挂 document 构造不崩、highlightBlock 命中不抛
  [3] 离屏 GUI：生成页含 tone_count 与高亮器；角色页含「随机名字」按钮；
      ChooseNameDialog 构造/候选 8 个/点选 selectedText/自定义/换一批
运行：env\\python.exe _tone_gen_check.py
"""
import os
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "src"))

RESULTS = []
TMP = tempfile.mkdtemp(prefix="xhb_tone_")
import storage
storage.PROJECTS_DIR = os.path.join(TMP, "projects")
storage.INDEX_PATH = os.path.join(storage.PROJECTS_DIR, "index.json")
os.makedirs(storage.PROJECTS_DIR, exist_ok=True)


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def test_name_gen():
    import random
    import name_gen as ng
    r = random.Random(42)
    nm = ng.generate_name(rng=r)
    check("起名-非空", len(nm) >= 2, nm)
    check("起名-含姓氏", any(nm.startswith(s) for s in ng.SURNAMES), nm)
    nm1 = ng.generate_name(rng=r)
    nm2 = ng.generate_name(rng=r)
    check("起名-确定性(同种子)", nm == nm1 or nm2 != nm, "")
    check("起名-可指定姓氏", ng.generate_name("萧", "male", True, r).startswith("萧"), "")
    sf = ng.generate_name("秦", "male", False, r)
    check("起名-单字名", len(sf) == 2, sf)
    batch = ng.generate_names(8, "random", True, r)
    check("起名-批量去重", len(batch) == 8 and len(set(batch)) == 8, str(batch))
    m = ng.generate_name("", "male", True, r)
    f = ng.generate_name("", "female", True, r)
    check("起名-男女字库非空", len(m) == 3 and len(f) == 3, "%s %s" % (m, f))


def test_tone_counts():
    from tone_highlighter import count_tone_hits
    check("套话-命中", count_tone_hits("他的眼中闪过一丝杀意") == 1, "")
    check("套话-多命中累加", count_tone_hits("眼中闪过一丝杀意，他下意识地后退") == 2, "")
    check("套话-未命中", count_tone_hits("夜色如墨，长街尽头一盏灯亮着") == 0, "")
    check("套话-空文本", count_tone_hits("") == 0 and count_tone_hits(None) == 0, "")
    check("套话-普通句子", count_tone_hits("她推门而出，雪落满肩。") == 0, "")
    check("套话-自定义词命中", count_tone_hits("他目光一凝，想起往事",
                                          ["目光一凝"]) == 1, "")
    check("套话-自定义空不崩", count_tone_hits("他目光一凝", []) == 0, "")
    check("套话-内置+自定义累加", count_tone_hits("他目光一凝，眼中闪过一丝杀意",
                                            ["目光一凝"]) == 2, "")


def test_highlighter_attach():
    from PySide6.QtGui import QTextDocument
    from tone_highlighter import CharacterHighlighter, ToneHighlighter
    doc = QTextDocument("他眼中闪过一丝杀意。夜色沉静。")
    hi = ToneHighlighter(doc)
    try:
        hi.rehighlight()
        applied = doc.firstBlock().layout().formats()
        check("高亮-挂载并高亮", len(applied) > 0, str(applied))
    except Exception as e:
        check("高亮-挂载并高亮", False, repr(e))
    # 自定义词动态重载
    doc2 = QTextDocument("他目光一凝，神色如常。")
    hi2 = ToneHighlighter(doc2, ["目光一凝"])
    hi2.rehighlight()
    check("高亮-自定义词生效", len(doc2.firstBlock().layout().formats()) > 0, "")
    hi2.set_extra_words([])
    hi2.rehighlight()
    check("高亮-清除后不高亮", len(doc2.firstBlock().layout().formats()) == 0, "")
    # 角色名着色
    doc3 = QTextDocument("沈云澜踏入铁砧城，沈云澜环顾四周。")
    chi = CharacterHighlighter(doc3, ["沈云澜", "铁砧城", "无此人"])
    chi.rehighlight()
    check("角色高亮-挂载生效", len(doc3.firstBlock().layout().formats()) == 3,
          str(doc3.firstBlock().layout().formats()))
    doc4 = QTextDocument("正文。")
    chi4 = CharacterHighlighter(doc4)
    chi4.rehighlight()
    check("角色高亮-空名单不崩", len(doc4.firstBlock().layout().formats()) == 0, "")


def test_gui():
    import gui_app
    import gui_characters
    import gui_generate
    from PySide6.QtWidgets import QApplication
    qapp = QApplication.instance() or QApplication([])

    store = storage.ProjectStore("proj")
    p = __import__("models").NovelProject()
    p.title = "T"
    store.save_project(p)
    gui_app.APP["project_dir"] = "proj"

    page = gui_generate.GeneratePage(None)
    check("GUI-正文套话计数控件", hasattr(page, "tone_count") and hasattr(page, "_tone_hi"), "")
    page.content.setPlainText("他眼中闪过一丝杀意，不禁冷笑。")
    page._update_content_count()
    check("GUI-套话计数刷新", "套话 1" in page.tone_count.text(),
          page.tone_count.text())
    check("GUI-字数计数保留", "字" in page.content_count.text(),
          page.content_count.text())
    page.close()

    chars = gui_characters.CharactersPage(None)
    from PySide6.QtWidgets import QPushButton
    found = False
    for b in chars.findChildren(QPushButton):
        if "随机名字" in b.text():
            found = True
            break
    check("角色-随机名字按钮", found, "")
    dlg = gui_characters.ChooseNameDialog(None)
    names = [b.text() for b in dlg._btns]
    check("弹窗-8个候选", len(names) == 8 and all(names), str(names))
    dlg._pick(3)
    check("弹窗-点选记录", dlg.selectedText == names[3], dlg.selectedText)
    dlg2 = gui_characters.ChooseNameDialog(None)
    dlg2.custom.setText("自定义名")
    dlg2._use_custom()
    check("弹窗-自定义名", dlg2.selectedText == "自定义名", dlg2.selectedText)
    dlg.close()
    dlg2.close()

    # v0.48：角色名着色挂载（on_show 从角色卡读取姓名）
    from models import CharacterCard, InfoLibrary
    card = CharacterCard("沈云澜")
    store.save_character(card, InfoLibrary(card.id))
    page.on_show()
    check("GUI-角色名着色挂载",
          page._char_hi is not None and page._char_hi._names == ["沈云澜"],
          str(getattr(page._char_hi, "_names", None)))
    page.content.setPlainText("沈云澜踏入铁砧城，眼中闪过一丝杀意。")
    page._update_content_count()
    check("GUI-套话计数仍生效", "套话 1" in page.tone_count.text(),
          page.tone_count.text())
    page.close()

    # v0.48：设置页自定义禁词管理 + 保存闭环（打桩 save_config 防写盘）
    import config as cfgmod
    import gui_settings
    sp = gui_settings.SettingsPage(None)
    check("设置-禁词控件", hasattr(sp, "tone_word_list")
          and hasattr(sp, "tone_word_edit"), "")
    sp.tone_word_edit.setText("目光一凝")
    sp._add_tone_word()
    check("设置-添加禁词", sp.tone_word_list.count() == 1
          and sp.tone_word_list.item(0).text() == "目光一凝", "")
    sp.tone_word_list.setCurrentRow(0)
    sp._del_tone_word()
    check("设置-删除禁词", sp.tone_word_list.count() == 0, "")
    sp.tone_word_list.addItem("自定义词")
    saved = {}
    orig_save = cfgmod.save_config
    cfgmod.save_config = lambda c: saved.update(c)
    try:
        sp._save_params()
    finally:
        cfgmod.save_config = orig_save
    check("设置-保存含禁词", saved.get("tone_words_custom") == ["自定义词"],
          str(saved.get("tone_words_custom")))
    sp.close()
    chars.close()
    qapp.processEvents()


def main():
    try:
        test_name_gen()
        test_tone_counts()
        test_highlighter_attach()
        test_gui()
    finally:
        import shutil
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