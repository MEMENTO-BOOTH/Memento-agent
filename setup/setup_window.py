"""Fenêtre setup — affiche uniquement la page de configuration."""
from PyQt5.QtWidgets import QMainWindow
from PyQt5.QtCore import pyqtSignal

from .styles import BG
from .config_page import ConfigPage


class SetupWindow(QMainWindow):
    """Premier lancement : Config → Dashboard."""
    setup_complete = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Memento Agent — Configuration")
        self.setFixedSize(880, 650)

        self._config = ConfigPage(on_finish=self._complete)
        self._config.setStyleSheet(f"background: {BG};")
        self.setCentralWidget(self._config)

    def _complete(self):
        self.setup_complete.emit()
