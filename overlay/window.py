"""Fenêtre overlay sans bord, toujours au-dessus, transparente.
Empile les barres d'impression dans le coin choisi."""
from PyQt5.QtWidgets import QWidget, QApplication
from PyQt5.QtCore import Qt

from .bar import PrintBar, BAR_W, BAR_H


MARGIN_X = 30
MARGIN_Y = 40
SPACING = 8


class OverlayWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
            | Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._bars = []

    def add_bar(self, cfg, duration_s):
        bar = PrintBar(cfg, duration_s, parent=self)
        bar.finished.connect(self._remove_bar)
        self._bars.append(bar)
        bar.show()
        self._relayout(cfg.get("position", "bottom_right"))

    def mark_current_done(self):
        """Marque la barre non-terminee la plus ancienne comme finie (papier sorti)."""
        for bar in self._bars:
            if bar._done_at is None:
                bar.mark_done()
                return

    def _remove_bar(self, bar):
        if bar in self._bars:
            self._bars.remove(bar)
        bar.deleteLater()
        if not self._bars:
            self.hide()
        else:
            self._relayout(self._bars[-1]._cfg.get("position", "bottom_right"))

    def _relayout(self, position):
        if not self._bars:
            return
        screen = QApplication.primaryScreen().availableGeometry()
        count = len(self._bars)
        total_h = count * BAR_H + (count - 1) * SPACING
        total_w = BAR_W

        if position == "bottom_center":
            x = screen.x() + (screen.width() - total_w) // 2
            y = screen.bottom() - total_h - MARGIN_Y
        elif position == "top_right":
            x = screen.right() - total_w - MARGIN_X
            y = screen.y() + MARGIN_Y
        else:
            x = screen.right() - total_w - MARGIN_X
            y = screen.bottom() - total_h - MARGIN_Y

        self.setGeometry(x, y, total_w, total_h)
        for i, bar in enumerate(self._bars):
            bar.move(0, i * (BAR_H + SPACING))
        if not self.isVisible():
            self.show()
