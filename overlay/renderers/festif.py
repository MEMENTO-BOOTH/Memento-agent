"""Style Festif : degrade base sur color_main avec variations de teinte."""
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QPainterPath, QFont, QLinearGradient


def _shift_hue(color, delta):
    h = (color.hue() + delta) % 360
    return QColor.fromHsv(h, color.saturation(), color.value())


def render(p, rect, cfg, progress, label, timer_text, done):
    p.setRenderHint(p.Antialiasing)

    bg = QColor(cfg["color_bg"])
    main = QColor(cfg["color_main"])
    text = QColor(cfg["color_text"])

    body = QRectF(rect.x(), rect.y(), rect.width(), rect.height())
    path = QPainterPath()
    path.addRoundedRect(body, 12, 12)
    p.fillPath(path, bg)

    inner = body.adjusted(5, 5, -5, -5)
    fill_w = max(0.0, inner.width() * progress)
    if fill_w > 0:
        grad = QLinearGradient(inner.x(), 0, inner.x() + inner.width(), 0)
        if done:
            grad.setColorAt(0.0, main)
            grad.setColorAt(1.0, _shift_hue(main, 30))
        else:
            grad.setColorAt(0.00, _shift_hue(main, -40))
            grad.setColorAt(0.40, main)
            grad.setColorAt(0.75, _shift_hue(main, 40))
            grad.setColorAt(1.00, _shift_hue(main, 80))
        fill_path = QPainterPath()
        fill_path.addRoundedRect(QRectF(inner.x(), inner.y(), fill_w, inner.height()), 8, 8)
        p.fillPath(fill_path, grad)

    p.setFont(QFont(cfg["font"], 12, QFont.DemiBold))
    p.setPen(text)
    p.drawText(body.adjusted(16, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, label)

    p.setFont(QFont(cfg["font"], 13, QFont.Bold))
    p.drawText(body.adjusted(0, 0, -16, 0), Qt.AlignVCenter | Qt.AlignRight, timer_text)
