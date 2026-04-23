"""Style Minimal : une ligne fine, pas de bordure, ultra épuré."""
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QPen, QFont


def render(p, rect, cfg, progress, label, timer_text, done):
    p.setRenderHint(p.Antialiasing)

    main = QColor(cfg["color_main"])
    text = QColor(cfg["color_text"])
    track = QColor(cfg["color_bg"])
    track.setAlpha(110)

    body = QRectF(rect.x(), rect.y(), rect.width(), rect.height())
    bar_h = 2.0
    bar_y = body.y() + body.height() - bar_h - 6
    bar_x = body.x() + 4
    bar_w = body.width() - 8
    p.fillRect(QRectF(bar_x, bar_y, bar_w, bar_h), track)
    p.fillRect(QRectF(bar_x, bar_y, bar_w * progress, bar_h), main)

    p.setFont(QFont(cfg["font"], 10))
    p.setPen(text)
    p.drawText(QRectF(bar_x, body.y(), bar_w, bar_h + 20), Qt.AlignVCenter | Qt.AlignLeft, label)
    p.drawText(QRectF(bar_x, body.y(), bar_w, bar_h + 20), Qt.AlignVCenter | Qt.AlignRight, timer_text)
