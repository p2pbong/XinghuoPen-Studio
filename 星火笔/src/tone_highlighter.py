# -*- coding: utf-8 -*-
"""正文编辑区实时监测（v0.47/v0.48，借鉴 51mazi「禁词提示」/好好码字「敏感词检测」）。

- ToneHighlighter：AI 八股套话命中画金色波浪下划线（内置 AI_PHRASES + 可追加自定义禁词
  config["tone_words_custom"]，set_extra_words 动态重载）；
- CharacterHighlighter：当前项目角色名着色（亮青色），帮助保持角色名写法一致；
- count_tone_hits(text, extra_words)：独立计数（避免高亮逐块累加的重复问题）。
"""
import re
import weakref

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QColor, QSyntaxHighlighter, QTextCharFormat

from gui_theme import C

# 换肤用：已创建的高亮器实例（弱引用，随控件销毁自动失效）
_LIVE = []


def _register(obj):
    _LIVE.append(weakref.ref(obj))


def retint_all():
    """跟随主题换色（gui_theme.recolor 在换肤后调用）。"""
    for r in list(_LIVE):
        o = r()
        if o is None:
            _LIVE.remove(r)
            continue
        try:
            o.retint()
        except Exception:
            pass

# 网络小说 / AI 生成的高频「套话」短语（词组优先，避免单字误伤；可自行增删）
AI_PHRASES = [
    "眼中闪过一丝", "眼中闪过", "眸中",
    "嘴角勾起一抹", "嘴角微微", "唇角微扬",
    "深吸一口气", "缓缓吸了一口气",
    "心中一动", "心中一惊", "心下一沉", "心头一紧",
    "不自觉地", "下意识地",
    "一种莫名的", "某种莫名的",
    "淡淡道", "冷冷道", "沉声道", "低声道",
    "沉默了片刻", "沉默片刻", "良久",
    "缓缓开口", "缓缓地说道", "缓声道",
    "眸光一闪", "眼神变得", "扯了扯嘴角", "勾了勾嘴角",
    "有些出神", "愣愣地", "怔怔地",
    "就在这时", "说时迟那时快",
]

_TONE_RE = re.compile("(" + "|".join(re.escape(p) for p in AI_PHRASES) + ")")


def _merged_re(extra_words):
    """内置 + 自定义禁词合并正则（去重）。"""
    words = list(AI_PHRASES)
    if extra_words:
        for w in extra_words:
            w = str(w).strip()
            if w and w not in words:
                words.append(w)
    return re.compile("(" + "|".join(re.escape(p) for p in words) + ")")


def count_tone_hits(text, extra_words=None):
    """统计正文中套话命中次数（自定义禁词一并计入）。"""
    if not text:
        return 0
    return len(_merged_re(extra_words).findall(text))


class ToneHighlighter(QSyntaxHighlighter):
    """对命中套话/自定义禁词的位置绘制金色波浪下划线。"""

    def __init__(self, document, extra_words=None):
        super().__init__(document)
        self._fmt = QTextCharFormat()
        self._fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        self.set_extra_words(extra_words or [])
        self.retint()
        _register(self)

    def retint(self):
        """按当前主题重设配色（换肤时由 retint_all 调用）。"""
        self._fmt.setUnderlineColor(QColor(C("accent")))
        self._fmt.setForeground(QColor(C("accent_text")))
        self.rehighlight()

    def set_extra_words(self, extra_words):
        """v0.48：更新自定义禁词并整体重绘（设置页改动后调用）。"""
        self._extra = [str(w).strip() for w in (extra_words or []) if str(w).strip()]
        self._re = QRegularExpression(_merged_re(self._extra).pattern)
        self.rehighlight()

    def highlightBlock(self, text):
        it = self._re.globalMatch(text)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(1), m.capturedLength(1), self._fmt)


class CharacterHighlighter(QSyntaxHighlighter):
    """v0.48：当前项目角色名着色（亮青色前景，无下划线），帮助保持名称一致。"""

    def __init__(self, document, names=None):
        super().__init__(document)
        self._fmt = QTextCharFormat()
        self.set_names(names or [])
        self.retint()
        _register(self)

    def retint(self):
        """按当前主题重设配色（换肤时由 retint_all 调用）。"""
        self._fmt.setForeground(QColor(C("blue")))
        self.rehighlight()

    def set_names(self, names):
        seen = []
        for n in names or []:
            n = str(n).strip()
            if n and n not in seen and 1 < len(n) <= 6:
                seen.append(n)
        self._names = seen
        if seen:
            self._re = QRegularExpression(
                "(" + "|".join(re.escape(n) for n in seen) + ")")
        else:
            self._re = None
        self.rehighlight()

    def highlightBlock(self, text):
        if not self._re:
            return
        it = self._re.globalMatch(text)
        while it.hasNext():
            m = it.next()
            self.setFormat(m.capturedStart(1), m.capturedLength(1), self._fmt)