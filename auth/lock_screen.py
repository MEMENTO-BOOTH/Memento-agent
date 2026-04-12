"""Écran de verrouillage PIN — affiché après déconnexion ou au relancement."""
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QPixmap, QColor

from paths import ASSETS_DIR, reg_get

# Couleurs
BG = "#0F172A"
TEXT = "#FFFFFF"
TEXT_SEC = "#94A3B8"
GREEN = "#B6FF56"
BORDER = "#334155"
RED = "#EF4444"


class LockScreen(QWidget):
    """Écran PIN — sobre, fond sombre, lime green."""
    unlocked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pin_inputs = []
        self._error_lbl = None
        self._build()

    def closeEvent(self, event):
        """Se cacher dans le tray au lieu de quitter."""
        event.ignore()
        self.hide()

    def _get_saved_pin(self):
        return reg_get("pin") or "0000"

    def _build(self):
        self.setStyleSheet(f"background: {BG};")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        container = QVBoxLayout()
        container.setSpacing(0)
        container.setAlignment(Qt.AlignCenter)

        # Logo
        logo = QLabel()
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.exists(logo_path):
            logo.setPixmap(QPixmap(logo_path).scaled(70, 70, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        logo.setStyleSheet("background: transparent;")
        container.addWidget(logo)
        container.addSpacing(16)

        title = QLabel("Memento Agent")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {GREEN}; font-family: 'Inter'; font-size: 20px; font-weight: 700; background: transparent;")
        container.addWidget(title)
        container.addSpacing(8)

        subtitle = QLabel("Entrez le code PIN pour accéder au dashboard")
        subtitle.setAlignment(Qt.AlignCenter)
        subtitle.setStyleSheet(f"color: {TEXT_SEC}; font-family: 'Inter'; font-size: 13px; background: transparent;")
        container.addWidget(subtitle)
        container.addSpacing(32)

        # 4 champs PIN
        pin_row = QHBoxLayout()
        pin_row.setSpacing(14)
        pin_row.setAlignment(Qt.AlignCenter)
        for i in range(4):
            inp = QLineEdit()
            inp.setFixedSize(56, 56)
            inp.setMaxLength(1)
            inp.setEchoMode(QLineEdit.Password)
            inp.setAlignment(Qt.AlignCenter)
            inp.setStyleSheet(f"""
                QLineEdit {{
                    border: 2px solid {BORDER}; border-radius: 14px;
                    font-family: 'Inter'; font-size: 22px; font-weight: 700;
                    color: {TEXT}; background: transparent;
                }}
                QLineEdit:focus {{ border: 2px solid {GREEN}; }}
            """)
            inp.textChanged.connect(lambda text, idx=i: self._on_digit(text, idx))
            pin_row.addWidget(inp)
            self._pin_inputs.append(inp)
        container.addLayout(pin_row)
        container.addSpacing(16)

        # Erreur
        self._error_lbl = QLabel("")
        self._error_lbl.setAlignment(Qt.AlignCenter)
        self._error_lbl.setStyleSheet(f"color: {RED}; font-family: 'Inter'; font-size: 12px; background: transparent;")
        container.addWidget(self._error_lbl)
        container.addSpacing(24)

        # Bouton
        btn = QPushButton("Déverrouiller")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedSize(200, 44)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {GREEN}; color: #0F172A;
                border-radius: 8px; font-family: 'Inter'; font-size: 14px; font-weight: 600; border: none;
            }}
            QPushButton:hover {{ background: #A8EE4A; }}
        """)
        btn.clicked.connect(self._check_pin)
        container.addWidget(btn, 0, Qt.AlignCenter)

        layout.addLayout(container)

    def _on_digit(self, text, idx):
        if text and idx < 3:
            self._pin_inputs[idx + 1].setFocus()
        # Auto-check quand 4 digits remplis
        if idx == 3 and text:
            self._check_pin()

    def _check_pin(self):
        entered = "".join(i.text() for i in self._pin_inputs)

        # 1. Vérifier dans Supabase (utilisateurs)
        import supabase_client as supa
        import user_session
        user = supa.verifier_pin(entered)
        if user:
            user_session.set_user(user)
            self._error_lbl.setText("")
            self.unlocked.emit()
            return

        # 2. Fallback : vérifier le PIN local (registre)
        saved = self._get_saved_pin()
        if entered == saved:
            user_session.set_user({"nom": "Local", "role": "admin", "voir_ca": True})
            self._error_lbl.setText("")
            self.unlocked.emit()
            return

        # Échec
        self._error_lbl.setText("Code PIN incorrect")
        for i in self._pin_inputs:
            i.clear()
            i.setStyleSheet(i.styleSheet().replace(f"border: 2px solid {BORDER}", f"border: 2px solid {RED}"))
        self._pin_inputs[0].setFocus()

    def showEvent(self, event):
        super().showEvent(event)
        for i in self._pin_inputs:
            i.clear()
        self._error_lbl.setText("")
        if self._pin_inputs:
            self._pin_inputs[0].setFocus()
