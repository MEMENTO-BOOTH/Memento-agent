"""Style Rétro Pixel : barre en blocs 8-bit, palette Game Boy."""
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QPen, QFont


BLOCKS = 14


def render(p, rect, cfg, progress, label, timer_text, done):
    p.setRenderHint(p.Antialiasing, False)

    bg = QColor(cfg["color_bg"])
    main = QColor(cfg["color_main"])
    text = QColor(cfg["color_text"])

    body = QRectF(rect.x(), rect.y(), rect.width(), rect.height())
    p.fillRect(body, bg)
    p.setPen(QPen(main, 2))
    p.drawRect(body.adjusted(1, 1, -1, -1))
    p.drawRect(body.adjusted(4, 4, -4, -4))

    inner = body.adjusted(10, 18, -10, -8)
    block_w = inner.width() / BLOCKS
    filled_count = int(progress * BLOCKS + 0.0001)
    for i in range(BLOCKS):
        x = inner.x() + i * block_w + 1
        w = block_w - 2
        if i < filled_count:
            p.fillRect(QRectF(x, inner.y(), w, inner.height()), main)
        else:
            p.fillRect(QRectF(x, inner.y(), w, inner.height()), QColor(main.red() // 4, main.green() // 4, main.blue() // 4))

    p.setFont(QFont(cfg["font"], 9, QFont.Bold))
    p.setPen(text)
    p.drawText(body.adjusted(10, 2, 0, 0), Qt.AlignTop | Qt.AlignLeft, label)

    p.setPen(main if not done else text)
    p.drawText(body.adjusted(0, 2, -10, 0), Qt.AlignTop | Qt.AlignRight, timer_text)
