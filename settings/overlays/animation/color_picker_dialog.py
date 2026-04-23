"""Dialogue color picker : palette + saisie HEX."""
import re
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton, QLineEdit
from PyQt5.QtCore import Qt

from dashboard import T, LIME_GREEN, TEXT_BLACK


PALETTE = [
    "#B6FF56", "#22C55E", "#10B981", "#06B6D4", "#00FFFF",
    "#3B82F6", "#6366F1", "#8B5CF6", "#EC4899", "#EF4444",
    "#F59E0B", "#FBBF24", "#EAB308", "#FFFFFF", "#E5E7EB",
    "#9CA3AF", "#6B7280", "#374151", "#111827", "#000000",
]


class ColorPickerDialog(QDialog):
    def __init__(self, initial_hex, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Couleur")
        self.setFixedSize(320, 300)
        self.setStyleSheet(f"background: {T()['card_bg']};")
        self._value = initial_hex
        self._build()

    def value(self):
        return self._value

    def _build(self):
        vl = QVBoxLayout(self)
        vl.setContentsMargins(20, 18, 20, 18)
        vl.setSpacing(12)

        grid = QGridLayout()
        grid.setSpacing(6)
        for i, color in enumerate(PALETTE):
            btn = QPushButton()
            btn.setFixedSize(42, 32)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(f"background: {color}; border: 1px solid {T()['card_border']}; border-radius: 6px;")
            btn.clicked.connect(lambda _, c=color: self._pick(c))
            grid.addWidget(btn, i // 5, i % 5)
        vl.addLayout(grid)

        self._input = QLineEdit(self._value)
        self._input.setMaxLength(7)
        self._input.setFixedHeight(34)
        self._input.setAlignment(Qt.AlignCenter)
        self._input.setStyleSheet(f"border: 1.5px solid {T()['card_border']}; border-radius: 6px; font-family: 'Inter'; font-size: 13px; color: {T()['text']};")
        vl.addWidget(self._input)

        row = QHBoxLayout()
        cancel = QPushButton("Annuler")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.setFixedHeight(34)
        cancel.setStyleSheet(f"background: transparent; color: {T()['text']}; border: 1px solid {T()['card_border']}; border-radius: 6px; padding: 0 14px;")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("Valider")
        ok.setCursor(Qt.PointingHandCursor)
        ok.setFixedHeight(34)
        ok.setStyleSheet(f"background: {LIME_GREEN}; color: {TEXT_BLACK}; border: none; border-radius: 6px; font-weight: 600; padding: 0 14px;")
        ok.clicked.connect(self._accept)
        row.addWidget(cancel, 1)
        row.addWidget(ok, 1)
        vl.addLayout(row)

    def _pick(self, c):
        self._value = c
        self._input.setText(c)

    def _accept(self):
        v = self._input.text().strip().upper()
        if not v.startswith("#"):
            v = "#" + v
        if re.fullmatch(r"#[0-9A-F]{6}", v):
            self._value = v
            self.accept()
