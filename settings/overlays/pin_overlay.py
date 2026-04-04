"""Overlay modification du code PIN."""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QColor

from dashboard import T, LIME_GREEN, TEXT_BLACK
from ..config import load as load_config, save as save_config


class PinOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._pin_inputs = []
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        card = QWidget()
        card.setFixedSize(380, 280)
        card.setObjectName("pin_card")
        card.setStyleSheet(f"""
            QWidget#pin_card {{
                background-color: {T()['card_bg']};
                border: 1px solid {T()['card_border']};
                border-radius: 16px;
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(32, 28, 32, 28)
        cl.setSpacing(0)

        # Header
        header = QHBoxLayout()
        title = QLabel("Modifier le code PIN")
        title.setStyleSheet(f"color: {T()['text']}; font-family: 'Inter'; font-size: 17px; font-weight: 700; background: transparent;")
        header.addWidget(title)
        header.addStretch()

        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(30, 30)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {T()['text']}; font-size: 16px; font-weight: 600; border: none; border-radius: 15px; }}
            QPushButton:hover {{ background-color: {T()['row_sep']}; }}
        """)
        close_btn.clicked.connect(self._close)
        header.addWidget(close_btn)
        cl.addLayout(header)
        cl.addSpacing(8)

        subtitle = QLabel("Entrez votre nouveau code à 4 chiffres")
        subtitle.setStyleSheet(f"color: #888888; font-family: 'Inter'; font-size: 12px; background: transparent;")
        cl.addWidget(subtitle)
        cl.addSpacing(24)

        # 4 champs PIN
        pin_row = QHBoxLayout()
        pin_row.setSpacing(14)
        pin_row.addStretch()
        for i in range(4):
            inp = QLineEdit()
            inp.setFixedSize(56, 56)
            inp.setMaxLength(1)
            inp.setAlignment(Qt.AlignCenter)
            inp.setStyleSheet(f"""
                QLineEdit {{
                    border: 2px solid {T()['card_border']}; border-radius: 12px;
                    font-family: 'Inter'; font-size: 22px; font-weight: 700;
                    color: {T()['text']}; background-color: {T()['content_bg']};
                }}
                QLineEdit:focus {{ border: 2px solid {LIME_GREEN}; }}
            """)
            inp.textChanged.connect(lambda text, idx=i: self._on_digit(text, idx))
            pin_row.addWidget(inp)
            self._pin_inputs.append(inp)
        pin_row.addStretch()
        cl.addLayout(pin_row)
        cl.addStretch()

        # Boutons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        cancel_btn = QPushButton("Annuler")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedHeight(38)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: transparent; color: {T()['text']};
                border: 1px solid {T()['card_border']}; border-radius: 8px;
                padding: 6px 20px; font-family: 'Inter'; font-size: 13px; font-weight: 500;
            }}
            QPushButton:hover {{ background-color: {T()['row_sep']}; }}
        """)
        cancel_btn.clicked.connect(self._close)
        btn_row.addWidget(cancel_btn, 1)

        confirm_btn = QPushButton("Confirmer")
        confirm_btn.setCursor(Qt.PointingHandCursor)
        confirm_btn.setFixedHeight(38)
        confirm_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {LIME_GREEN}; color: {TEXT_BLACK};
                border-radius: 8px; padding: 6px 20px; font-family: 'Inter';
                font-size: 13px; font-weight: 600; border: none;
            }}
            QPushButton:hover {{ background-color: #A8EE4A; }}
        """)
        confirm_btn.clicked.connect(self._confirm)
        btn_row.addWidget(confirm_btn, 1)
        cl.addLayout(btn_row)
        layout.addWidget(card)

    def _on_digit(self, text, idx):
        if text and idx < 3:
            self._pin_inputs[idx + 1].setFocus()

    def _close(self):
        for inp in self._pin_inputs:
            inp.clear()
        self.hide()

    def _confirm(self):
        pin = "".join(inp.text() for inp in self._pin_inputs)
        if len(pin) == 4:
            cfg = load_config()
            cfg["pin"] = pin
            save_config(cfg)
            self._close()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        p.end()

    def showEvent(self, event):
        super().showEvent(event)
        if self._pin_inputs:
            self._pin_inputs[0].setFocus()

    def mousePressEvent(self, event):
        if self.childAt(event.pos()) is None:
            self._close()
