"""Orchestre l'affichage de l'overlay sur evenement impression."""
from PyQt5.QtCore import QObject, pyqtSlot

from . import config as cfg_mod
from .window import OverlayWindow


class PrintOverlayManager(QObject):
    """Manager singleton a instancier une fois au demarrage.

    Usage :
        mgr = PrintOverlayManager()
        mgr.on_print_started()   # a connecter a monitoring.print_started
        mgr.reload_config()      # apres modif des settings
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._window = None
        self._cfg = cfg_mod.load()

    def reload_config(self):
        self._cfg = cfg_mod.load()

    @pyqtSlot()
    def on_print_started(self):
        if not self._cfg.get("enabled"):
            return
        if self._window is None:
            self._window = OverlayWindow()
        self._window.add_bar(self._cfg, self._cfg.get("duration", 18))

    def trigger_preview(self):
        """Force l'affichage d'une barre (pour test manuel)."""
        if self._window is None:
            self._window = OverlayWindow()
        self._window.add_bar(self._cfg, self._cfg.get("duration", 18))
