"""Page 1 : Choix du dossier d'installation."""
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QCheckBox, QFileDialog
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QPainter, QColor, QPen, QPalette

from .styles import *

from paths import ASSETS_DIR


class CheckBox(QCheckBox):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(f"""
            QCheckBox {{ spacing: 12px; font-family: 'Inter'; font-size: 14px; color: {TEXT}; background: transparent; }}
            QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid {BORDER}; border-radius: 4px; background: {WHITE}; }}
            QCheckBox::indicator:hover {{ border-color: {TEXT_MUTED}; }}
            QCheckBox::indicator:checked {{ background: {GREEN}; border-color: {GREEN}; }}
        """)


class InstallPage(QWidget):
    """Page 1 — choix dossier + options."""

    def __init__(self, on_next=None, parent=None):
        super().__init__(parent)
        self._on_next = on_next
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 40, 80, 40)
        layout.setSpacing(0)

        # Logo
        logo = QLabel()
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.exists(logo_path):
            logo.setPixmap(QPixmap(logo_path).scaled(100, 100, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("background: transparent; margin-bottom: 20px;")
        layout.addWidget(logo)

        title = QLabel("Installation")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {GREEN_DARK}; font-family: 'Inter'; font-size: 32px; font-weight: 700; background: transparent;")
        layout.addWidget(title)
        layout.addSpacing(8)

        subtitle = QLabel("Configurez l'emplacement et les options de votre agent.")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(f"color: {TEXT_SEC}; font-family: 'Inter'; font-size: 15px; background: transparent;")
        layout.addWidget(subtitle)
        layout.addSpacing(48)

        # Dossier
        sec = QLabel("DOSSIER D'INSTALLATION")
        sec.setStyleSheet(f"color: {GREEN_DARK}; font-family: 'Inter'; font-size: 11px; font-weight: 700; letter-spacing: 0.8px; background: transparent;")
        layout.addWidget(sec)
        layout.addSpacing(12)

        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self._path = QLineEdit()
        self._path.setPlaceholderText(r"C:\Program Files\Memento Agent")
        self._path.setFixedHeight(42)
        self._path.setStyleSheet(f"""
            QLineEdit {{ border: 1px solid {BORDER}; border-radius: 6px; padding: 10px 14px; font-family: 'Inter'; font-size: 14px; color: {TEXT}; background: {WHITE}; }}
            QLineEdit:focus {{ border: 2px solid {GREEN}; padding: 9px 13px; }}
        """)
        p = self._path.palette()
        p.setColor(QPalette.PlaceholderText, QColor(TEXT_MUTED))
        self._path.setPalette(p)
        path_row.addWidget(self._path, 1)

        browse = QPushButton("Parcourir")
        browse.setCursor(Qt.PointingHandCursor)
        browse.setFixedHeight(42)
        browse.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 6px; padding: 8px 16px; font-family: 'Inter'; font-size: 14px; font-weight: 500; }}
            QPushButton:hover {{ background: {BG_SEC}; }}
        """)
        browse.clicked.connect(self._browse)
        path_row.addWidget(browse)
        layout.addLayout(path_row)
        layout.addSpacing(40)

        # Options
        sec2 = QLabel("OPTIONS DE CONFIGURATION")
        sec2.setStyleSheet(f"color: {GREEN_DARK}; font-family: 'Inter'; font-size: 11px; font-weight: 700; letter-spacing: 0.8px; background: transparent;")
        layout.addWidget(sec2)
        layout.addSpacing(16)

        self._cb_startup = CheckBox("Lancer au démarrage de Windows")
        self._cb_startup.setChecked(True)
        self._cb_shortcut = CheckBox("Créer un raccourci sur le Bureau")
        self._cb_shortcut.setChecked(True)

        opts = QVBoxLayout()
        opts.setSpacing(16)
        opts.addWidget(self._cb_startup)
        opts.addWidget(self._cb_shortcut)
        layout.addLayout(opts)

        layout.addStretch()

        # Boutons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        cancel = QPushButton("Annuler")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setFixedHeight(44)
        cancel.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT}; border: 1px solid {BORDER}; border-radius: 6px; padding: 8px 16px; font-family: 'Inter'; font-size: 14px; font-weight: 500; }}
            QPushButton:hover {{ background: {BG_SEC}; }}
        """)
        cancel.clicked.connect(lambda: self.window().close())
        btn_row.addWidget(cancel, 1)

        install = QPushButton("Installer")
        install.setCursor(Qt.PointingHandCursor)
        install.setFixedHeight(44)
        install.setStyleSheet(f"""
            QPushButton {{ background: {GREEN}; color: {WHITE}; border-radius: 6px; padding: 8px 16px; font-family: 'Inter'; font-size: 14px; font-weight: 600; border: none; }}
            QPushButton:hover {{ background: {GREEN_HOVER}; }}
        """)
        install.clicked.connect(self._next)
        btn_row.addWidget(install, 1)
        layout.addLayout(btn_row)

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "Choisir le dossier d'installation")
        if folder:
            self._path.setText(folder)

    def _next(self):
        if self._on_next:
            self._on_next({
                "path": self._path.text() or self._path.placeholderText(),
                "startup": self._cb_startup.isChecked(),
                "shortcut": self._cb_shortcut.isChecked(),
            })
