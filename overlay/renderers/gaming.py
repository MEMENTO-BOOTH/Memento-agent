"""Style Gaming Neon : HUD arcade, cyan fluo, scanlines, coins cassés."""
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QPainterPath, QPen, QFont, QLinearGradient


def render(p, rect, cfg, progress, label, timer_text, done):
    p.setRenderHint(p.Antialiasing, False)

    bg = QColor(cfg["color_bg"])
    main = QColor(cfg["color_main"])
    text = QColor(cfg["color_text"])

    body = QRectF(rect.x(), rect.y(), rect.width(), rect.height())
    p.fillRect(body, bg)
    p.setPen(QPen(main, 2))
    p.drawRect(body.adjusted(1, 1, -1, -1))

    inner = body.adjusted(6, 6, -6, -6)
    fill_w = max(0.0, inner.width() * progress)
    if fill_w > 0:
        grad = QLinearGradient(inner.x(), 0, inner.x() + inner.width(), 0)
        grad.setColorAt(0.0, QColor("#00CCFF"))
        grad.setColorAt(1.0, QColor("#00FFAA"))
        p.fillRect(QRectF(inner.x(), inner.y(), fill_w, inner.height()), grad if not done else QColor("#00FF66"))

        p.setPen(QPen(bg, 1))
        for y in range(int(inner.y()) + 2, int(inner.y() + inner.height()), 4):
            p.drawLine(int(inner.x()), y, int(inner.x() + fill_w), y)

        if cfg.get("glow"):
            p.fillRect(QRectF(inner.x() + fill_w - 4, inner.y(), 4, inner.height()), main)

    corner = 10
    p.setPen(QPen(main, 1))
    p.drawLine(int(body.x()), int(body.y() + corner), int(body.x()), int(body.y() + corner + 8))
    p.drawLine(int(body.right()), int(body.y()), int(body.right()), int(body.y() + 8))

    p.setFont(QFont(cfg["font"], 11, QFont.Bold))
    p.setPen(QColor("#88CCFF") if not done else text)
    p.drawText(body.adjusted(14, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, label)

    p.setFont(QFont(cfg["font"], 15, QFont.Bold))
    p.setPen(main if not done else text)
    p.drawText(body.adjusted(0, 0, -14, 0), Qt.AlignVCenter | Qt.AlignRight, timer_text)
