# -*- coding: utf-8 -*-
"""生成星火笔·安卓版 App 图标（自绘，深底金色火焰+钢笔尖，各密度 PNG + adaptive）。

依赖 PySide6（env 自带 Qt）绘图；输出到 app/src/main/res/mipmap-* 与 anydpi-v26 adaptive。
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QLinearGradient, QPainter, QPainterPath,
                           QPen, QRadialGradient, QBrush)
from PySide6.QtGui import QImage

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "app", "src", "main", "res")


def draw_icon(size):
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    S = size / 512.0

    # 背景圆角方 + 内描边
    bg = QLinearGradient(0, 0, 0, size)
    bg.setColorAt(0.0, QColor("#1c2432"))
    bg.setColorAt(1.0, QColor("#0a0d14"))
    p.setPen(QPen(QColor("#2e3a48"), 3 * S))
    p.setBrush(QBrush(bg))
    p.drawRoundedRect(QRectF(10 * S, 10 * S, size - 20 * S, size - 20 * S),
                      size * 0.22, size * 0.22)

    # 底部微光（星火暖光）
    glow = QRadialGradient(QPointF(256 * S, 330 * S), 200 * S)
    glow.setColorAt(0.0, QColor(212, 164, 76, 60))
    glow.setColorAt(1.0, QColor(212, 164, 76, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(glow))
    p.drawEllipse(QPointF(256 * S, 330 * S), 210 * S, 150 * S)

    # 金色火焰（贝塞尔火焰轮廓 + 径向渐变）
    flame = QPainterPath()
    flame.moveTo(QPointF(256 * S, 432 * S))
    flame.cubicTo(QPointF(336 * S, 392 * S), QPointF(374 * S, 292 * S),
                  QPointF(342 * S, 208 * S))
    flame.cubicTo(QPointF(326 * S, 246 * S), QPointF(306 * S, 258 * S),
                  QPointF(290 * S, 234 * S))
    flame.cubicTo(QPointF(300 * S, 168 * S), QPointF(282 * S, 102 * S),
                  QPointF(256 * S, 64 * S))
    flame.cubicTo(QPointF(230 * S, 102 * S), QPointF(212 * S, 168 * S),
                  QPointF(222 * S, 234 * S))
    flame.cubicTo(QPointF(206 * S, 258 * S), QPointF(186 * S, 246 * S),
                  QPointF(170 * S, 208 * S))
    flame.cubicTo(QPointF(138 * S, 292 * S), QPointF(176 * S, 392 * S),
                  QPointF(256 * S, 432 * S))
    fg = QRadialGradient(QPointF(256 * S, 300 * S), 190 * S)
    fg.setColorAt(0.0, QColor("#ffe9b8"))
    fg.setColorAt(0.45, QColor("#e8b95c"))
    fg.setColorAt(1.0, QColor("#a67c30"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(fg))
    p.drawPath(flame)

    # 钢笔尖（白色米色，叠在火焰中央：笔杆 + 尖头）
    nib = QPainterPath()
    nib.moveTo(QPointF(238 * S, 150 * S))
    nib.lineTo(QPointF(274 * S, 150 * S))
    nib.lineTo(QPointF(288 * S, 250 * S))
    nib.lineTo(QPointF(256 * S, 372 * S))   # 尖
    nib.lineTo(QPointF(224 * S, 250 * S))
    nib.closeSubpath()
    ng = QLinearGradient(0, 140 * S, 0, 380 * S)
    ng.setColorAt(0.0, QColor("#fff6de"))
    ng.setColorAt(1.0, QColor("#e6c27a"))
    p.setPen(QPen(QColor("#8a6a2c"), 4 * S))
    p.setBrush(QBrush(ng))
    p.drawPath(nib)
    # 笔尖中缝
    p.setPen(QPen(QColor("#8a6a2c"), 3 * S))
    p.drawLine(QPointF(256 * S, 152 * S), QPointF(256 * S, 330 * S))
    # 笔尖末端出墨点
    p.setBrush(QBrush(QColor("#d4a44c")))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QPointF(256 * S, 396 * S), 7 * S, 7 * S)

    # 底部文字「星火笔」小字（避免，图标里不放字）
    p.end()
    return img


def save_png(img, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)


def main():
    sizes = {"mipmap-mdpi": 48, "mipmap-hdpi": 72, "mipmap-xhdpi": 96,
             "mipmap-xxhdpi": 144, "mipmap-xxxhdpi": 192}
    for folder, size in sizes.items():
        save_png(draw_icon(size), os.path.join(RES, folder, "ic_launcher.png"))
    # adaptive icon（API 26+）：前景 108dp 安全区 66dp → 画 432 画布上内容 264 区域
    fg = QImage(432, 432, QImage.Format.Format_ARGB32)
    fg.fill(Qt.GlobalColor.transparent)
    p = QPainter(fg)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.drawImage(QRectF(84, 84, 264, 264), draw_icon(512))
    p.end()
    save_png(fg, os.path.join(RES, "mipmap-anydpi-v26", "ic_launcher_foreground.png"))
    os.makedirs(os.path.join(RES, "mipmap-anydpi-v26"), exist_ok=True)
    # background：纯色（与图标底色一致）
    bg = QImage(432, 432, QImage.Format.Format_ARGB32)
    bg.fill(QColor("#0a0d14"))
    save_png(bg, os.path.join(RES, "mipmap-anydpi-v26", "ic_launcher_background.png"))
    # adaptive xml（ic_launcher + ic_launcher_round）
    xml = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
           '    <background android:drawable="@mipmap/ic_launcher_background" />\n'
           '    <foreground android:drawable="@mipmap/ic_launcher_foreground" />\n'
           '</adaptive-icon>\n')
    for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        with open(os.path.join(RES, "mipmap-anydpi-v26", name), "w", encoding="utf-8") as f:
            f.write(xml)
    # 预览图（工程内 docs 用）
    save_png(draw_icon(256), os.path.join(HERE, "_icon_preview.png"))
    print("ICON_DONE ->", RES)


if __name__ == "__main__":
    main()
