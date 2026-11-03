# -*- coding: utf-8 -*-
"""语音码字（v0.49）：说一段话→免费语音识别为中文→插入正文光标处。
v0.50：连续听写模式——说一段识别一段、自动续听，最后整段插入。

依赖：speech_recognition（3.x）+ pyaudio（Windows wheel）。组件缺失时按钮提示而不崩溃。
"""
import threading

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout)

from gui_app import log_fn
from gui_theme import T

try:
    import speech_recognition as sr
    _SR_OK = True
except Exception:
    sr = None
    _SR_OK = False


class _VoiceWorker(QObject):
    """后台线程：环境噪声校准 → 录音（说完静音自动结束，最长 20 秒）→ 中文识别。

    done 信号跨线程回传（queued connection），与 gui_generate._ReviewWorker 同模式。
    """

    done = Signal(object)

    def run(self):
        if not _SR_OK:
            self.done.emit({"error": "语音组件未安装（speech_recognition / pyaudio，见 README）"})
            return
        try:
            r = sr.Recognizer()
            with sr.Microphone() as mic:
                r.adjust_for_ambient_noise(mic, duration=0.6)
                audio = r.listen(mic, timeout=8, phrase_time_limit=20)
            text = r.recognize_google(audio, language="zh-CN")
            self.done.emit({"text": text.strip()})
        except sr.WaitTimeoutError:
            self.done.emit({"error": "8 秒没听到声音，已超时（可再试一次）"})
        except sr.UnknownValueError:
            self.done.emit({"error": "没听清内容，请再试一次"})
        except sr.RequestError as e:
            self.done.emit({"error": "语音识别服务请求失败：%s（识别需要联网）" % e})
        except Exception as e:
            self.done.emit({"error": "录音/识别失败：%s" % e})


class VoiceInputDialog(QDialog):
    """语音码字对话框：单次（说一段插入）或连续听写（多段累积后整段插入）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("语音码字")
        self.setMinimumWidth(460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(12)
        self.state = QLabel("点击「开始录音」后直接说话；说完停顿几秒自动识别，最长 20 秒。"
                            if _SR_OK else "语音组件未安装（需要 speech_recognition + pyaudio，见 README 安装说明）。")
        self.state.setWordWrap(True)
        lay.addWidget(self.state)
        # v0.50 连续听写
        self.cont_chk = QCheckBox("连续听写：说一段识别一段、自动续听，说完全部后点「完成并插入」")
        self.cont_chk.setToolTip("适合边想边说整段情节：每段说完自动开始下一轮，直到点「完成并插入」整段进正文。")
        lay.addWidget(self.cont_chk)
        self.rec_btn = QPushButton("开始录音")
        self.rec_btn.setObjectName("primary")
        self.rec_btn.clicked.connect(self._start)
        lay.addWidget(self.rec_btn)
        self.status = QLabel("")
        self.status.setStyleSheet(T("color:#5b6470;"))
        self.status.setWordWrap(True)
        lay.addWidget(self.status)
        row = QHBoxLayout()
        self.done_btn = QPushButton("完成并插入")
        self.done_btn.setToolTip("把已识别内容一次性插入正文光标处（连续听写时使用）")
        self.done_btn.setEnabled(False)
        self.done_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(self.done_btn)
        row.addWidget(cancel_btn)
        lay.addLayout(row)
        self._worker = _VoiceWorker()
        self._worker.done.connect(self._on_done)
        self._thread = None
        self._parts = []
        self._text = None

    def value(self):
        """识别出的文本（未识别返回 None）；连续听写时返回多段拼接（每段一行）。"""
        if self._parts:
            return "\n".join(self._parts)
        return self._text

    def _start(self):
        if not _SR_OK:
            return
        self.rec_btn.setEnabled(False)
        if self._parts:
            self.state.setText("🎤 第 %d 段录音中…继续说（说完停顿几秒自动识别）" % (len(self._parts) + 1))
        else:
            self.state.setText("🎤 录音中…请说话（说完停顿几秒自动识别；也可以直接关闭窗口放弃）")
        self._thread = threading.Thread(target=self._worker.run, daemon=True)
        self._thread.start()

    def _on_done(self, res):
        self.rec_btn.setEnabled(True)
        if "text" in res and res["text"]:
            self._parts.append(res["text"])
            if self.cont_chk.isChecked():
                self.done_btn.setEnabled(True)
                self.status.setText("已识别 %d 段。继续说（自动续听下一段），或点「完成并插入」。"
                                    % len(self._parts))
                # 自动开始下一轮（间隔 600ms，避免麦克风刚释放就被重开）
                QTimer.singleShot(600, self._start)
                return
            self._text = res["text"]
            self.status.setText("识别完成：%s" % res["text"][:40])
            self.accept()
        else:
            msg = res.get("error", "识别失败")
            self.status.setText(msg)
            self.state.setText("可点「开始录音」重试，或「完成/取消」关闭。")
            log_fn("warn", "语音识别失败：%s" % msg)
