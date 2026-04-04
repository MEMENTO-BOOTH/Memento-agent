"""Tableau d'activité — logs + alertes mélangés, style shadcn."""
import os
from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import Qt, QRectF, QRect, QByteArray, QTimer
from PyQt5.QtGui import QPainter, QColor, QPen, QPainterPath, QFont, QPixmap
from PyQt5.QtSvg import QSvgRenderer

from dashboard import T, ASSETS_DIR


def _load_icon(filename, size=28):
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        return pm
    with open(path, "r") as f:
        data = f.read()
    renderer = QSvgRenderer(QByteArray(data.encode()))
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


def _load_resolved_icon(filename, size=28):
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        return pm
    with open(path, "r") as f:
        data = f.read()
    data = data.replace('#EF4444', '#22C55E').replace('#ef4444', '#22C55E')
    data = data.replace('#F59E0B', '#22C55E').replace('#f59e0b', '#22C55E')
    data = data.replace('stroke="white"', 'stroke="black"')
    data = data.replace('fill="white"', 'fill="black"')
    renderer = QSvgRenderer(QByteArray(data.encode()))
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


class ActivityTable(QWidget):
    """Tableau d'activité — logs sans icône, alertes avec icône."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries = []
        self._icons_cache = {}
        self._header_h = 48
        self._log_row_h = 36
        self._alert_row_h = 50
        self._update_height()

        # Auto-refresh toutes les 5 secondes
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh)
        self._timer.start(5000)

    def _refresh(self):
        import activity_logger as alog
        new_entries = alog.get_ui_entries()
        if len(new_entries) != len(self._entries):
            self._entries = new_entries
            self._update_height()
            self.update()

    def _update_height(self):
        h = self._header_h + 8
        for e in self._entries:
            if e["type"] == "alerte":
                h += self._alert_row_h + 10
            else:
                h += self._log_row_h
        self.setFixedHeight(max(h + 16, 120))

    def _get_icon(self, fname, resolved):
        key = fname + ("_r" if resolved else "_o")
        if key not in self._icons_cache:
            if resolved:
                self._icons_cache[key] = _load_resolved_icon(fname, 28)
            else:
                self._icons_cache[key] = _load_icon(fname, 28)
        return self._icons_cache[key]

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.TextAntialiasing)

        w = self.width()
        total_h = self.height()
        r = 12.0

        # Fond + bordure
        outer = QPainterPath()
        outer.addRoundedRect(QRectF(0.5, 0.5, w - 1, total_h - 1), r, r)
        p.fillPath(outer, QColor(T()["card_bg"]))
        p.setPen(QPen(QColor(T()["card_border"]), 1.7))
        p.drawPath(outer)

        # Header
        hdr = QPainterPath()
        hdr.moveTo(1, self._header_h)
        hdr.lineTo(1, r + 1)
        hdr.arcTo(QRectF(1, 1, r * 2, r * 2), 180, -90)
        hdr.lineTo(w - r - 1, 1)
        hdr.arcTo(QRectF(w - r * 2 - 1, 1, r * 2, r * 2), 90, -90)
        hdr.lineTo(w - 1, self._header_h)
        hdr.closeSubpath()
        p.fillPath(hdr, QColor(T()["table_header_bg"]))
        p.setPen(QPen(QColor(T()["card_border"]), 1.7))
        p.drawLine(0, self._header_h, w, self._header_h)

        # Header text
        font_header = QFont("Satoshi")
        font_header.setPixelSize(12)
        font_header.setWeight(QFont.DemiBold)
        p.setFont(font_header)
        p.setPen(QColor(T()["text"]))
        p.drawText(QRect(20, 0, w, self._header_h), Qt.AlignVCenter | Qt.AlignLeft, "ACTIVITÉ")

        if not self._entries:
            font_empty = QFont("Satoshi")
            font_empty.setPixelSize(12)
            p.setFont(font_empty)
            p.setPen(QColor(T()["text"]))
            p.drawText(QRect(20, self._header_h, w - 40, 60), Qt.AlignVCenter | Qt.AlignLeft,
                       "En attente d'activité...")
            p.end()
            return

        # Lignes
        y = self._header_h + 8
        for i, entry in enumerate(self._entries):
            is_alert = entry["type"] == "alerte"

            if is_alert:
                y += 5
                row_h = self._alert_row_h
                cy = y + row_h // 2

                # Icône
                fname = entry.get("icon", "")
                resolved = entry.get("resolved", False)
                if fname:
                    icon = self._get_icon(fname, resolved)
                    if not icon.isNull():
                        isz = int(icon.width() / icon.devicePixelRatio())
                        p.drawPixmap(20, cy - isz // 2, icon)

                # Heure — bold
                font_time = QFont("Satoshi")
                font_time.setPixelSize(12)
                font_time.setWeight(QFont.DemiBold)
                p.setFont(font_time)
                p.setPen(QColor(T()["text"]))
                p.drawText(QRect(56, y, 70, row_h), Qt.AlignVCenter | Qt.AlignLeft, entry["time"])

                # Message — bold
                font_msg = QFont("Satoshi")
                font_msg.setPixelSize(13)
                font_msg.setWeight(QFont.DemiBold)
                p.setFont(font_msg)
                p.drawText(QRect(130, y, w - 150, row_h), Qt.AlignVCenter | Qt.AlignLeft, entry["text"])

                y += row_h + 5
            else:
                row_h = self._log_row_h

                # Séparateur
                if i > 0 and self._entries[i - 1]["type"] == "log":
                    p.setPen(QPen(QColor(T()["row_sep"]), 1))
                    p.drawLine(20, y, w - 20, y)

                # Heure
                font_time = QFont("Satoshi")
                font_time.setPixelSize(12)
                p.setFont(font_time)
                p.setPen(QColor(T()["text"]))
                p.drawText(QRect(20, y, 70, row_h), Qt.AlignVCenter | Qt.AlignLeft, entry["time"])

                # Message
                font_msg = QFont("Satoshi")
                font_msg.setPixelSize(12)
                p.setFont(font_msg)
                p.drawText(QRect(100, y, w - 120, row_h), Qt.AlignVCenter | Qt.AlignLeft, entry["text"])

                y += row_h

        p.end()
