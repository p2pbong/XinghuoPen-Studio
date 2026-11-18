# -*- coding: utf-8 -*-
"""诊断：角色卡编辑流程（offscreen 模拟真实交互）。"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import storage
from models import CharacterCard, InfoLibrary
from PySide6.QtWidgets import QApplication

storage.ensure_example_project()
st = storage.ProjectStore("示例项目_星海孤城")
test = CharacterCard("诊断角色")
lib = InfoLibrary(test.id)
lib.scenario = "初始处境：在铁砧城"
st.save_character(test, lib)

app = QApplication(sys.argv)
from gui_theme import QSS
app.setStyleSheet(QSS)
from gui_app import MainWindow, APP

APP["project_dir"] = "示例项目_星海孤城"
win = MainWindow()
win.switch_page(1)
app.processEvents()

card_w = None
for c in win.page_characters.cards:
    if c.char_id == test.id:
        card_w = c
        break
print("卡片找到:", card_w is not None)

# 直接构造对话框（exec 模态会阻塞无头测试，故不 exec）
from gui_characters import CharEditDialog
d = None
try:
    d = CharEditDialog(test.id)
    print("CharEditDialog 构造 OK")
    print("  当前处境载入:", d.scenario_edit.toPlainText())
except Exception as e:
    import traceback
    traceback.print_exc()
    print("CharEditDialog 构造失败:", e)

if d is not None:
    d.desc_edit.setPlainText("诊断：综合人设描述写入")
    d.scenario_edit.setPlainText("诊断：处境更新")
    d.name_edit.setText("诊断角色2")
    try:
        d._save()
        card2, lib2 = st.load_character(test.id)
        print("保存后 description =", repr(card2.description))
        print("保存后 scenario(信息库) =", repr(lib2.scenario))
        print("保存后 name =", card2.name)
        assert lib2.scenario == "诊断：处境更新"
        assert card2.description == "诊断：综合人设描述写入"
    except Exception as e:
        import traceback
        traceback.print_exc()
        print("_save 异常:", e)

st.delete_character(test.id)
print("DONE")