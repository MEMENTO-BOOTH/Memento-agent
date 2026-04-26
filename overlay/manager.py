"""Orchestre l'affichage de l'overlay sur evenement impression."""
import time
from PyQt5.QtCore import QObject, pyqtSlot

from . import config as cfg_mod
from .window import OverlayWindow
from .detector import PrintStartDetector


# Deux signaux start rapproches sont ignores (spool + status DNP de la meme impression).
DEDUP_START_S = 25


class PrintOverlayManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._window = None
        self._cfg = cfg_mod.load()
        self._last_start = 0.0
        self._detector = None
        if self._cfg.get("enabled"):
            self._ensure_detector()

    def _ensure_detector(self):
        if self._detector is not None:
            return
        self._detector = PrintStartDetector(
            on_print_started=self._on_start_signal,
            on_print_completed=self._on_done_signal,
            parent=self,
        )
        self._detector.start()

    def reload_config(self):
        self._cfg = cfg_mod.load()
        if self._cfg.get("enabled"):
            self._ensure_detector()

    def _on_start_signal(self):
        self.on_print_started()

    def _on_done_signal(self):
        """Compteur DNP a baisse = papier sorti. Marquer la barre active comme terminee."""
        if self._window is None:
            return
        self._window.mark_current_done()

    @pyqtSlot()
    def on_print_started(self):
        if not self._cfg.get("enabled"):
            return
        now = time.time()
        if now - self._last_start < DEDUP_START_S:
            return
        self._last_start = now
        if self._window is None:
            self._window = OverlayWindow()
        self._window.add_bar(self._cfg, self._cfg.get("duration", 18))

    def trigger_preview(self):
        self._last_start = time.time()
        if self._window is None:
            self._window = OverlayWindow()
        self._window.add_bar(self._cfg, self._cfg.get("duration", 18))
