"""Style Memento Lime : barre lime sur fond sombre, police Satoshi."""
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QPainterPath, QPen, QFont


def render(p, rect, cfg, progress, label, timer_text, done):
    p.setRenderHint(p.Antialiasing)

    bg = QColor(cfg["color_bg"])
    main = QColor(cfg["color_main"])
    text = QColor(cfg["color_text"])

    body = QRectF(rect.x(), rect.y(), rect.width(), rect.height())
    path = QPainterPath()
    path.addRoundedRect(body, 10, 10)
    p.fillPath(path, bg)
    p.setPen(QPen(main, 1.5))
    p.drawPath(path)

    inner = body.adjusted(4, 4, -4, -4)
    fill_w = max(0.0, inner.width() * progress)
    fill_rect = QRectF(inner.x(), inner.y(), fill_w, inner.height())
    fill_path = QPainterPath()
    fill_path.addRoundedRect(fill_rect, 7, 7)
    p.fillPath(fill_path, main)

    if cfg.get("glow") and not done and fill_w > 6:
        glow = QColor(main)
        glow.setAlpha(60)
        halo = QRectF(inner.x() + fill_w - 3, inner.y() - 3, 6, inner.height() + 6)
        p.fillRect(halo, glow)

    p.setFont(QFont(cfg["font"], 11, QFont.DemiBold))
    p.setPen(text)
    p.drawText(body.adjusted(16, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, label)

    p.setFont(QFont(cfg["font"], 13, QFont.Bold))
    p.setPen(main if not done else text)
    p.drawText(body.adjusted(0, 0, -16, 0), Qt.AlignVCenter | Qt.AlignRight, timer_text)
