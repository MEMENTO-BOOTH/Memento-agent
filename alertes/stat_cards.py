"""Cartes statistiques style shadcn — sobre, noir, pas de couleurs."""
import os
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QRectF, QRect, QByteArray
from PyQt5.QtGui import QPainter, QColor, QPen, QPainterPath, QFont, QPixmap
from PyQt5.QtSvg import QSvgRenderer

from dashboard import T
from paths import ASSETS_DIR


def _load_icon(filename, size):
    """Charge un SVG feather en noir."""
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        return pm
    with open(path, "r") as f:
        data = f.read()
    data = data.replace('stroke="currentColor"', 'stroke="#0F172A"')
    renderer = QSvgRenderer(QByteArray(data.encode()))
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


class AlerteStatCard(QWidget):
    """Stat card sobre — icône noire, texte noir, fond blanc."""
    def __init__(self, title="", value="0", color="#888", icon_file="", parent=None):
        super().__init__(parent)
        self._title = title
        self._value = str(value)
        self._icon_file = icon_file
        self._badge_text = ""
        self.setFixedHeight(150)

    def set_data(self, value, badge_text=""):
        self._value = str(value)
        self._badge_text = badge_text
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)
        w = self.width()
        h = self.height()
        pad = 16

        # Fond carte + bordure fine
        rect = QRectF(0.5, 0.5, w - 1, h - 1)
        card = QPainterPath()
        card.addRoundedRect(rect, 12, 12)
        p.fillPath(card, QColor(T()["card_bg"]))
        p.setPen(QPen(QColor(T()["card_border"]), 1.7))
        p.drawPath(card)

        # Icône carrée arrondie — fond gris très clair
        icon_sz = 38
        icon_rect = QRectF(pad, pad, icon_sz, icon_sz)
        icon_bg = QPainterPath()
        icon_bg.addRoundedRect(icon_rect, 8, 8)
        p.fillPath(icon_bg, QColor("#F1F5F9"))

        # Icône SVG noire
        if self._icon_file:
            icon = _load_icon(self._icon_file, 18)
            if not icon.isNull():
                isz = int(icon.width() / icon.devicePixelRatio())
                p.drawPixmap(
                    int(pad + (icon_sz - isz) / 2),
                    int(pad + (icon_sz - isz) / 2),
                    icon,
                )

        # Valeur — noir, gros
        y_val = pad + icon_sz + 14
        font_val = QFont("Satoshi")
        font_val.setPixelSize(22)
        font_val.setWeight(QFont.Bold)
        p.setFont(font_val)
        p.setPen(QColor(T()["text"]))
        p.drawText(QRect(pad, y_val, w - pad * 2, 28), Qt.AlignLeft | Qt.AlignVCenter, self._value)

        # Titre — noir
        font_title = QFont("Satoshi")
        font_title.setPixelSize(12)
        p.setFont(font_title)
        p.setPen(QColor(T()["text"]))
        p.drawText(QRect(pad, y_val + 28, w - pad * 2, 18), Qt.AlignLeft | Qt.AlignVCenter, self._title)

        # Badge en bas — fond gris clair, texte noir
        if self._badge_text:
            font_badge = QFont("Satoshi")
            font_badge.setPixelSize(10)
            font_badge.setWeight(QFont.DemiBold)
            p.setFont(font_badge)
            badge_w = p.fontMetrics().horizontalAdvance(self._badge_text) + 16
            bx = pad
            by = h - pad - 22
            badge_path = QPainterPath()
            badge_path.addRoundedRect(QRectF(bx, by, badge_w, 22), 6, 6)
            p.fillPath(badge_path, QColor("#F1F5F9"))
            p.setPen(QColor(T()["text"]))
            p.drawText(QRect(int(bx), int(by), int(badge_w), 22), Qt.AlignCenter, self._badge_text)

        p.end()
