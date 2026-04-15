"""Table d'alertes peinte — avec actions Supabase."""
from PyQt5.QtWidgets import QWidget, QMenu, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame
from PyQt5.QtCore import Qt, QRect, QRectF
from PyQt5.QtGui import QPainter, QColor, QPen, QPainterPath, QFont, QPixmap

import os
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtCore import QByteArray

from dashboard import T, DARK_THEME, LIME_GREEN, TEXT_BLACK, TEXT_WHITE, ASSETS_DIR, _utc_to_local
from .data import TYPE_TO_ICON, TYPE_LABELS, resolve_alerte, assign_alerte, delete_alerte

# Types visuellement "warning" (orange) — même si Supabase dit "critique"
_TYPES_WARNING_VISUEL = {"surchauffe", "papier_bas", "disque_bas", "coupe_incoherente", "crash_relance", "borne_hors_ligne", "impression_non_delivree"}

def _gravite_visuelle(alerte):
    """Retourne la gravité visuelle basée sur le type d'alerte."""
    return "warning" if alerte.get("type", "") in _TYPES_WARNING_VISUEL else "critique"


def _load_icon(filename, size=32, resolved=False):
    """Charge un SVG. Si resolved, cercle vert + icône noire."""
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        return pm
    with open(path, "r") as f:
        data = f.read()
    if resolved:
        # Cercle rouge/orange → vert, icône blanche → noire
        data = data.replace('#EF4444', '#22C55E').replace('#ef4444', '#22C55E')
        data = data.replace('#F59E0B', '#22C55E').replace('#f59e0b', '#22C55E')
        data = data.replace('stroke="white"', 'stroke="black"')
        data = data.replace('fill="white"', 'fill="black"')
    renderer = QSvgRenderer(QByteArray(data.encode()))
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(scale)
    return pm


class AlerteTable(QWidget):
    """Table d'alertes connectée à Supabase."""

    def __init__(self, on_refresh=None, parent=None):
        super().__init__(parent)
        self._alertes = []
        self._icons_cache = {}
        from dashboard import load_svg
        self._dots = load_svg("icon_dots.svg", 18, "#000000")
        self._on_refresh = on_refresh
        self._header_h = 48
        self._row_h = 56

    def set_alertes(self, alertes):
        self._alertes = alertes
        h = self._header_h + len(alertes) * self._row_h
        self.setFixedHeight(max(h, 100))
        self.update()

    def _get_icon(self, alert_type, resolved=False):
        cache_key = f"{alert_type}_{'r' if resolved else 'o'}"
        if cache_key not in self._icons_cache:
            svg = TYPE_TO_ICON.get(alert_type, "icon_borne_hors_ligne.svg")
            self._icons_cache[cache_key] = _load_icon(svg, 32, resolved=resolved)
        return self._icons_cache[cache_key]

    def _row_at(self, y):
        if y < self._header_h:
            return -1
        idx = int((y - self._header_h) / self._row_h)
        return idx if idx < len(self._alertes) else -1

    def mousePressEvent(self, event):
        row = self._row_at(event.pos().y())
        if row < 0:
            return
        w = self.width()
        if event.pos().x() >= int(0.94 * w) - 10:
            self._show_menu(row, event.globalPos())

    def _show_menu(self, row, global_pos):
        alerte = self._alertes[row]
        alerte_id = alerte.get("id")
        statut = alerte.get("statut", "ouverte")

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {T()['card_bg']}; border: 1.7px solid {T()['card_border']};
                border-radius: 8px; padding: 4px 0; font-family: 'Satoshi'; font-size: 13px; color: {T()['text']};
            }}
            QMenu::item {{ padding: 8px 24px; }}
            QMenu::item:selected {{ background-color: {LIME_GREEN}; color: {TEXT_BLACK}; }}
        """)

        act_detail = menu.addAction("Voir les détails")
        act_assign = None
        if statut == "ouverte":
            act_assign = menu.addAction("Assigner")
        act_resolve = None
        if statut != "resolue":
            act_resolve = menu.addAction("Marquer résolu")
        menu.addSeparator()
        act_delete = menu.addAction("Supprimer")

        chosen = menu.exec_(global_pos)
        if chosen == act_detail:
            self._show_detail(alerte)
        elif chosen == act_assign and act_assign:
            if assign_alerte(alerte_id, "agent"):
                alerte["statut"] = "assignee"
                alerte["assignee_a"] = "agent"
                self.update()
        elif chosen == act_resolve and act_resolve:
            if resolve_alerte(alerte_id):
                alerte["statut"] = "resolue"
                alerte["resolue_par"] = "agent-manuel"
                self.update()
                from ui_components import toast
                toast("Alerte marquée comme résolue", "success")
        elif chosen == act_delete:
            if delete_alerte(alerte_id):
                self._alertes.pop(row)
                h = self._header_h + len(self._alertes) * self._row_h
                self.setFixedHeight(max(h, 100))
                self.update()
                if self._on_refresh:
                    self._on_refresh()

    def _show_detail(self, alerte):
        """Overlay sobre style shadcn pour les détails d'une alerte."""
        alert_type = alerte.get("type", "")
        label = TYPE_LABELS.get(alert_type, alert_type)
        statut = alerte.get("statut", "ouverte")

        dlg = QDialog(self.window())
        dlg.setWindowTitle("Détails")
        dlg.setFixedSize(440, 340)
        dlg.setStyleSheet(f"background: {T()['card_bg']};")

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(28, 24, 28, 24)
        vl.setSpacing(0)

        # Titre
        title = QLabel(label)
        title.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 18px; font-weight: 700; background: transparent;")
        vl.addWidget(title)
        vl.addSpacing(16)

        # Lignes de détails
        def _row(key, value):
            r = QHBoxLayout()
            r.setSpacing(0)
            k = QLabel(key)
            k.setFixedWidth(120)
            k.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 12px; font-weight: 600; background: transparent;")
            v = QLabel(value)
            v.setWordWrap(True)
            v.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 12px; background: transparent;")
            r.addWidget(k)
            r.addWidget(v, 1)
            return r

        vl.addLayout(_row("Statut", statut.capitalize()))
        vl.addSpacing(8)
        vl.addLayout(_row("Gravité", _gravite_visuelle(alerte).capitalize()))
        vl.addSpacing(8)
        vl.addLayout(_row("Heure", _utc_to_local(alerte.get("timestamp", ""))))
        vl.addSpacing(8)
        vl.addLayout(_row("Source", alerte.get("source", "—")))
        vl.addSpacing(8)
        vl.addLayout(_row("Assignée à", alerte.get("assignee_a") or "—"))
        vl.addSpacing(8)

        if statut == "resolue":
            vl.addLayout(_row("Résolu par", "Agent"))
            vl.addSpacing(8)
            vl.addLayout(_row("Résolu le", _utc_to_local(alerte.get("resolue_at", ""))))
            vl.addSpacing(8)

        # Message
        msg = alerte.get("message", "")
        if msg:
            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setFixedHeight(1)
            sep.setStyleSheet(f"background-color: {T()['row_sep']}; border: none;")
            vl.addWidget(sep)
            vl.addSpacing(10)
            msg_lbl = QLabel(msg)
            msg_lbl.setWordWrap(True)
            msg_lbl.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 12px; background: transparent;")
            vl.addWidget(msg_lbl)

        vl.addStretch()

        # Bouton fermer
        btn = QPushButton("Fermer")
        btn.setFixedHeight(36)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {T()['text']}; color: {T()['card_bg']};
                border-radius: 8px; font-family: 'Satoshi'; font-size: 12px;
                font-weight: 600; border: none;
            }}
            QPushButton:hover {{ opacity: 0.9; }}
        """)
        btn.clicked.connect(dlg.close)
        vl.addWidget(btn)

        dlg.exec_()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        total_h = self.height()
        r = 16.0

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

        # Colonnes
        col_x = [int(0.067 * w), int(0.22 * w), int(0.38 * w), int(0.56 * w), int(0.72 * w), int(0.85 * w), int(0.94 * w)]
        headers = ["Type", "Gravité", "Heure", "Source", "Assignée à", "Statut", ""]
        icon_x = int(0.02 * w)

        # En-tête — noir
        p.setPen(QColor(T()["text"]))
        hdr_font = QFont("Satoshi")
        hdr_font.setPixelSize(12)
        hdr_font.setWeight(QFont.DemiBold)
        p.setFont(hdr_font)
        for i, (x, txt) in enumerate(zip(col_x, headers)):
            if txt:
                cw = (col_x[i + 1] if i + 1 < len(col_x) else w) - x
                p.drawText(QRect(x, 0, cw, self._header_h), Qt.AlignVCenter | Qt.AlignLeft, txt)

        # Lignes
        for row_idx, alerte in enumerate(self._alertes):
            y = self._header_h + row_idx * self._row_h
            if row_idx > 0:
                p.setPen(QPen(QColor(T()["row_sep"]), 1))
                p.drawLine(24, y, w - 24, y)

            cy = y + self._row_h // 2
            alert_type = alerte.get("type", "")
            statut = alerte.get("statut", "ouverte")
            is_resolved = (statut == "resolue")

            # Icône — vert + noir si résolu, rouge + blanc sinon
            icon = self._get_icon(alert_type, resolved=is_resolved)
            if not icon.isNull():
                p.drawPixmap(icon_x, cy - 16, icon)

            # Type — noir
            p.setPen(QColor(T()["text"]))
            type_font = QFont("Satoshi")
            type_font.setPixelSize(12)
            type_font.setWeight(QFont.DemiBold)
            p.setFont(type_font)
            label = TYPE_LABELS.get(alert_type, alert_type)
            p.drawText(QRect(col_x[0], y, col_x[1] - col_x[0], self._row_h), Qt.AlignVCenter | Qt.AlignLeft, label)

            # Gravité — noir, pas de badge coloré
            body_font = QFont("Satoshi")
            body_font.setPixelSize(12)
            p.setFont(body_font)
            p.setPen(QColor(T()["text"]))
            gravite = _gravite_visuelle(alerte)
            p.drawText(QRect(col_x[1], y, col_x[2] - col_x[1], self._row_h), Qt.AlignVCenter | Qt.AlignLeft, gravite.capitalize())

            # Heure — noir
            p.setPen(QColor(T()["text"]))
            ts = _utc_to_local(alerte.get("timestamp", ""))
            p.drawText(QRect(col_x[2], y, col_x[3] - col_x[2], self._row_h), Qt.AlignVCenter | Qt.AlignLeft, ts)

            # Source — noir
            p.drawText(QRect(col_x[3], y, col_x[4] - col_x[3], self._row_h), Qt.AlignVCenter | Qt.AlignLeft,
                       alerte.get("source", "—"))

            # Assignée à — si résolu, afficher qui a résolu
            assignee = alerte.get("assignee_a") or "—"
            if is_resolved:
                assignee = "Agent"
            p.drawText(QRect(col_x[4], y, col_x[5] - col_x[4], self._row_h), Qt.AlignVCenter | Qt.AlignLeft, assignee)

            # Statut badge — sobre
            stat_label = {"ouverte": "Ouverte", "assignee": "Assignée", "resolue": "Résolue"}.get(statut, statut)
            badge_font = QFont("Satoshi")
            badge_font.setPixelSize(11)
            badge_font.setWeight(QFont.DemiBold)
            p.setFont(badge_font)
            tw = p.fontMetrics().horizontalAdvance(stat_label) + 18
            bx = col_x[5]
            by = cy - 11
            badge = QPainterPath()
            badge.addRoundedRect(QRectF(bx, by, tw, 22), 11, 11)
            if is_resolved:
                p.fillPath(badge, QColor("#F0FDF4"))
                p.setPen(QColor("#16A34A"))
            else:
                p.fillPath(badge, QColor("#F1F5F9"))
                p.setPen(QColor(T()["text"]))
            p.drawText(QRect(int(bx), int(by), int(tw), 22), Qt.AlignCenter, stat_label)

            # Dots menu
            if not self._dots.isNull():
                p.drawPixmap(col_x[6], cy - 9, self._dots)

        p.end()
