# -*- coding: utf-8 -*-
"""星火笔 v0.49 语音码字专项检查（无麦克风环境验证组件与 UI 接线，不实际录音）。

运行：env\\python.exe _voice_check.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

PASS = []


def check(name, cond, detail=""):
    PASS.append(bool(cond))
    print("%s %s %s" % ("PASS" if cond else "FAIL", name, detail))


def main():
    # 1) 组件可导入
    try:
        import speech_recognition as sr
        check("组件-speech_recognition", True, getattr(sr, "__version__", "?"))
    except Exception as e:
        check("组件-speech_recognition", False, str(e)[:80])
    try:
        import pyaudio
        check("组件-pyaudio", True, "OK")
    except Exception as e:
        check("组件-pyaudio", False, str(e)[:80])

    # 2) gui_voice 模块可导入 + 对话框无头可构造（QT_QPA_PLATFORM=offscreen）
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from gui_voice import VoiceInputDialog, _SR_OK, _VoiceWorker
    check("语音-gui_voice导入", True, "SR_OK=%s" % _SR_OK)
    dlg = VoiceInputDialog()
    check("语音-对话框构造", dlg.windowTitle() == "语音码字", dlg.windowTitle())
    dlg._worker.done  # Signal 存在
    check("语音-后台worker信号", hasattr(_VoiceWorker, "done"), "")
    check("语音-录音按钮存在", dlg.rec_btn is not None and "录音" in dlg.rec_btn.text(), "")
    check("语音-连续听写开关", dlg.cont_chk is not None
          and "连续听写" in dlg.cont_chk.text(), dlg.cont_chk.text()[:30])
    check("语音-完成插入按钮", dlg.done_btn is not None and "完成并插入" in dlg.done_btn.text(), "")
    dlg.close()

    # 3) 生成页接线：源码含语音按钮与 _voice_input
    gsrc = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "src", "gui_generate.py"), encoding="utf-8").read()
    check("语音-生成页按钮", "self.voice_btn = QPushButton(" in gsrc and "🎤 语音码字" in gsrc, "")
    check("语音-生成页打开对话框", "def _voice_input" in gsrc
          and "VoiceInputDialog" in gsrc and "cur.insertText(text)" in gsrc, "")
    check("语音-版本号v0.50", "v0.50" in open(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "src", "gui_app.py"),
        encoding="utf-8").read(), "")

    fails = [i for i, ok in enumerate(PASS) if not ok]
    print("-" * 50)
    if fails:
        print("FAILED %d/%d" % (len(fails), len(PASS)))
        sys.exit(1)
    print("ALL_OK (%d checks)" % len(PASS))


if __name__ == "__main__":
    main()
