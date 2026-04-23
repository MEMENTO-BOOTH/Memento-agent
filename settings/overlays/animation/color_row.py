"""Ligne 'Couleur X : [swatch] #HEX [Changer]' reutilisable."""
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel, QPushButton
from PyQt5.QtCore import Qt, pyqtSignal

from dashboard import T
from .color_picker_dialog import ColorPickerDialog


class ColorRow(QWidget):
    changed = pyqtSignal(str)

    def __init__(self, title, initial_hex, parent=None):
        super().__init__(parent)
        self._value = initial_hex
        self._title = title
        self._build()

    def value(self):
        return self._value

    def set_value(self, hex_value):
        self._value = hex_value
        self._swatch.setStyleSheet(f"background: {hex_value}; border: 1px solid {T()['card_border']}; border-radius: 4px;")
        self._hex_lbl.setText(hex_value)

    def _build(self):
        hl = QHBoxLayout(self)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(10)

        title_lbl = QLabel(self._title)
        title_lbl.setStyleSheet(f"color: {T()['text']}; font-family: 'Inter'; font-size: 13px; font-weight: 600; background: transparent;")
        hl.addWidget(title_lbl)
        hl.addStretch()

        self._swatch = QLabel()
        self._swatch.setFixedSize(22, 22)
        self._swatch.setStyleSheet(f"background: {self._value}; border: 1px solid {T()['card_border']}; border-radius: 4px;")
        hl.addWidget(self._swatch)

        self._hex_lbl = QLabel(self._value)
        self._hex_lbl.setStyleSheet(f"color: {T()['text']}; font-family: 'Inter'; font-size: 12px; background: transparent;")
        self._hex_lbl.setFixedWidth(72)
        hl.addWidget(self._hex_lbl)

        btn = QPushButton("Changer")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(30)
        btn.setStyleSheet(f"background: transparent; color: {T()['text']}; border: 1px solid {T()['card_border']}; border-radius: 6px; padding: 4px 12px; font-family: 'Inter'; font-size: 12px;")
        btn.clicked.connect(self._open)
        hl.addWidget(btn)

    def _open(self):
        dlg = ColorPickerDialog(self._value, self)
        if dlg.exec_() == dlg.Accepted:
            self.set_value(dlg.value())
            self.changed.emit(self._value)
