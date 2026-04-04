"""Widgets partagés et helpers de style pour toutes les sections."""
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QComboBox, QLineEdit
)
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QColor, QPen, QPainterPath, QFont, QPalette

from dashboard import T, LIME_GREEN, TEXT_BLACK, TEXT_WHITE, SIDEBAR_BG, load_svg

from paths import ASSETS_DIR


class ToggleSwitch(QWidget):
    """Toggle ON/OFF style néobrutalist."""
    def __init__(self, on=False, parent=None):
        super().__init__(parent)
        self._on = on
        self.setFixedSize(48, 26)
        self.setCursor(Qt.PointingHandCursor)

    def is_on(self):
        return self._on

    def set_on(self, on):
        self._on = on
        self.update()

    def mousePressEvent(self, event):
        self._on = not self._on
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        track = QPainterPath()
        track.addRoundedRect(QRectF(0, 0, w, h), h / 2, h / 2)
        p.fillPath(track, QColor(LIME_GREEN) if self._on else QColor("#DCDADA"))
        knob_r = h - 6
        knob_x = w - knob_r - 3 if self._on else 3
        knob = QPainterPath()
        knob.addEllipse(QRectF(knob_x, 3, knob_r, knob_r))
        p.fillPath(knob, QColor("#FFFFFF"))
        p.setPen(QPen(QColor(0, 0, 0, 30), 1.7))
        p.drawEllipse(QRectF(knob_x, 3, knob_r, knob_r))
        p.end()


class SectionCard(QWidget):
    """Carte de section avec bordure peinte."""
    def __init__(self, parent=None):
        super().__init__(parent)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        p.fillPath(path, QColor(T()["card_bg"]))
        p.setPen(QPen(QColor(T()["card_border"]), 1.7))
        p.drawPath(path)
        p.end()


# ─── Helpers de style ────────────────────────────

def section_title(text):
    lbl = QLabel(text)
    lbl.setStyleSheet(f"""
        color: {T()['text']}; font-family: 'Inter'; font-size: 11px;
        font-weight: 700; letter-spacing: 0.08em; background: transparent; padding-top: 8px;
    """)
    return lbl


def separator():
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background-color: {T()['row_sep']}; border: none;")
    return sep


def label(text, bold=False, muted=False, size=13):
    lbl = QLabel(text)
    weight = "600" if bold else "400"
    color = "#888888" if muted else T()["text"]
    lbl.setStyleSheet(f"""
        color: {color}; font-family: 'Inter'; font-size: {size}px;
        font-weight: {weight}; background: transparent;
    """)
    return lbl


def styled_combo(items, current=0):
    combo = QComboBox()
    combo.addItems(items)
    combo.setCurrentIndex(current)
    combo.setFixedHeight(36)
    combo.setMinimumWidth(180)
    combo.setCursor(Qt.PointingHandCursor)
    combo.setStyleSheet(f"""
        QComboBox {{
            border: 1.7px solid {T()['card_border']}; border-radius: 6px;
            padding: 6px 12px; font-family: 'Inter'; font-size: 13px;
            color: {T()['text']}; background-color: {T()['card_bg']};
        }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox QAbstractItemView {{
            background-color: {T()['card_bg']}; color: {T()['text']};
            selection-background-color: {LIME_GREEN}; selection-color: {TEXT_BLACK};
            border: 1.7px solid {T()['card_border']};
        }}
    """)
    return combo


def styled_input(text="", readonly=False):
    inp = QLineEdit(text)
    inp.setReadOnly(readonly)
    inp.setFixedHeight(36)
    bg = T()['card_bg'] if not readonly else T()['table_header_bg']
    inp.setStyleSheet(f"""
        QLineEdit {{
            border: 1.7px solid {T()['card_border']}; border-radius: 6px;
            padding: 6px 12px; font-family: 'Inter'; font-size: 13px;
            color: {T()['text']}; background-color: {bg};
        }}
        QLineEdit:focus {{ border: 2px solid {LIME_GREEN}; padding: 5px 11px; }}
    """)
    return inp


def green_btn(text):
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFixedHeight(34)
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {TEXT_BLACK}; color: {TEXT_WHITE}; border-radius: 6px;
            padding: 6px 16px; font-family: 'Inter'; font-size: 12px; font-weight: 600; border: none;
        }}
        QPushButton:hover {{ background-color: #333333; }}
    """)
    return btn


def lime_btn(text):
    btn = QPushButton(text)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFixedHeight(34)
    btn.setStyleSheet(f"""
        QPushButton {{
            background-color: {LIME_GREEN}; color: {TEXT_BLACK}; border-radius: 6px;
            padding: 6px 16px; font-family: 'Inter'; font-size: 12px; font-weight: 600; border: none;
        }}
        QPushButton:hover {{ background-color: #A8EE4A; }}
    """)
    return btn
