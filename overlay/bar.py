"""Widget d'une barre d'impression : animation + auto-remove."""
import time
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPainter

from .renderers import render as render_bar
from .presets import get as get_preset


BAR_W = 340
BAR_H = 50
DONE_DISPLAY_S = 3
TICK_MS = 30


class PrintBar(QWidget):
    finished = pyqtSignal(object)

    def __init__(self, cfg, duration_s, parent=None):
        super().__init__(parent)
        self.setFixedSize(BAR_W, BAR_H)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._cfg = cfg
        self._duration = max(1, int(duration_s))
        self._start = time.time()
        self._done_at = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(TICK_MS)

    def progress(self):
        if self._done_at is not None:
            return 1.0
        p = (time.time() - self._start) / self._duration
        return max(0.0, min(1.0, p))

    def _tick(self):
        if self._done_at is None and self.progress() >= 1.0:
            self._done_at = time.time()
        if self._done_at is not None and time.time() - self._done_at >= DONE_DISPLAY_S:
            self._timer.stop()
            self.finished.emit(self)
            return
        self.update()

    def paintEvent(self, _event):
        preset = get_preset(self._cfg.get("style", "memento"))
        done = self._done_at is not None
        label = preset["done_label"] if done else preset["label"]
        remaining = max(0, self._duration - int(time.time() - self._start))
        timer_text = "OK" if done else f"{remaining:02d}s"
        p = QPainter(self)
        render_bar(preset["renderer"], p, self.rect(), self._cfg, self.progress(), label, timer_text, done)
        p.end()
