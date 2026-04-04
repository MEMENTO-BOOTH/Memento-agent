"""Barre de filtres pour la page alertes."""
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QColor, QPainterPath, QFont

from dashboard import T, TEXT_BLACK, TEXT_WHITE


class FilterButton(QWidget):
    """Bouton filtre pill — actif/inactif."""
    def __init__(self, label, count=0, active=False, on_click=None, parent=None):
        super().__init__(parent)
        self._label = label
        self._count = count
        self._active = active
        self._on_click = on_click
        self.setFixedHeight(32)
        self.setFixedWidth(max(70, len(label) * 8 + 40))
        self.setCursor(Qt.PointingHandCursor)

    def set_active(self, active):
        self._active = active
        self.update()

    def set_count(self, count):
        self._count = count
        self.update()

    def mousePressEvent(self, event):
        if self._on_click:
            self._on_click()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 2, self.width(), self.height() - 4)
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)

        text = f"{self._label} {self._count}" if self._count else self._label
        f = QFont("Inter"); f.setPixelSize(11); f.setWeight(QFont.DemiBold); p.setFont(f)

        if self._active:
            p.fillPath(path, QColor(TEXT_BLACK) if T() is not __import__('dashboard').DARK_THEME else QColor("#FFF"))
            p.setPen(QColor(TEXT_WHITE) if T() is not __import__('dashboard').DARK_THEME else QColor(TEXT_BLACK))
        else:
            p.setPen(QColor(T()["card_border"]))
            p.drawPath(path)
            p.setPen(QColor(T().get("donut_sub", "#888")))

        p.drawText(rect, Qt.AlignCenter, text)
        p.end()
