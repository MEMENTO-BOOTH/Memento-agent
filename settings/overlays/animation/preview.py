"""Zone d'apercu live : une barre qui reboucle en permanence."""
import time
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPainter

from overlay.renderers import render as render_bar
from overlay.presets import get as get_preset


class AnimationPreview(QWidget):
    def __init__(self, cfg, duration_s=8, parent=None):
        super().__init__(parent)
        self.setFixedSize(340, 50)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self._cfg = dict(cfg)
        self._duration = duration_s
        self._start = time.time()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.update)
        self._timer.start(30)

    def set_cfg(self, cfg):
        self._cfg = dict(cfg)
        self.update()

    def stop(self):
        self._timer.stop()

    def _progress(self):
        cycle = self._duration + 2
        t = (time.time() - self._start) % cycle
        if t >= self._duration:
            return 1.0, True
        return min(1.0, t / self._duration), False

    def paintEvent(self, _event):
        preset = get_preset(self._cfg.get("style", "memento"))
        progress, done = self._progress()
        label = preset["done_label"] if done else preset["label"]
        remaining = max(0, int(self._duration - (progress * self._duration)))
        timer_text = "OK" if done else f"{remaining:02d}s"
        p = QPainter(self)
        render_bar(preset["renderer"], p, self.rect(), self._cfg, progress, label, timer_text, done)
        p.end()
