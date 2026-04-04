"""Overlay palette d'erreurs — affiche les icônes et types d'erreur avec leur gravité."""
import os
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QScrollArea
from PyQt5.QtCore import Qt, QRectF, QByteArray
from PyQt5.QtGui import QPainter, QColor, QPixmap, QFont
from PyQt5.QtSvg import QSvgRenderer

from dashboard import T, LIME_GREEN, TEXT_BLACK, TEXT_WHITE

from paths import ASSETS_DIR

# Toutes les alertes avec leur icône Figma et gravité par défaut
ALERTE_TYPES = [
    # ── Critiques (rouges) — déclenchent un SMS ──
    {"type": "bourrage_papier",    "label": "Bourrage papier",      "icon": "alert_bourrage_papier.svg",   "gravite": "critique", "code": "0x20002"},
    {"type": "fin_papier",         "label": "Fin de papier",        "icon": "alert_fin_de_papier.svg",     "gravite": "critique", "code": "0x10008"},
    {"type": "fin_ruban",          "label": "Fin de ruban",         "icon": "alert_fin_de_papier.svg",     "gravite": "critique", "code": "0x10010"},
    {"type": "capot_ouvert",       "label": "Capot ouvert",         "icon": "alert_capot_ouvert.svg",      "gravite": "critique", "code": "0x20001"},
    {"type": "bac_chutes_plein",   "label": "Bac à déchets plein",  "icon": "alert_disque_plein_new.svg",  "gravite": "critique", "code": "0x20020"},
    {"type": "erreur_mecanique",   "label": "Erreur mécanique",     "icon": "alert_erreur_mecanique.svg",  "gravite": "critique", "code": "≥0x40001"},
    {"type": "borne_hors_ligne",   "label": "Borne hors ligne",     "icon": "icon_borne_hors_ligne.svg",   "gravite": "critique", "code": "réseau"},
    {"type": "camera_deconnectee", "label": "Caméra déconnectée",   "icon": "icon_camera_deconnectee.svg", "gravite": "critique", "code": "USB"},
    {"type": "crash_dslrbooth",    "label": "Crash DSLRBOOTH",      "icon": "alert_crash_dslrbooth.svg",   "gravite": "critique", "code": "processus"},
    {"type": "crash_cashinterface","label": "Crash Cash Interface", "icon": "alert_crash_dslrbooth.svg",   "gravite": "critique", "code": "processus"},
    {"type": "imprimante_deconnectee","label": "Imprimante déconnectée", "icon": "alert_erreur_mecanique.svg", "gravite": "critique", "code": "USB"},
    {"type": "coupe_incoherente",    "label": "Coupe 2 pouces","icon": "icon_coupe_incoherente.svg","gravite": "critique", "code": "DEVMODE"},
    {"type": "disque_plein",       "label": "Disque plein",         "icon": "alert_disque_plein_new.svg",  "gravite": "critique", "code": "disque"},
    # ── Warnings (oranges) — affichés sur le dashboard, pas de SMS ──
    {"type": "surchauffe",         "label": "Surchauffe",           "icon": "icon_surchauffe.svg",         "gravite": "warning",  "code": "0x10020/40"},
    {"type": "papier_bas",         "label": "Papier bas",           "icon": "icon_papier_bas.svg",         "gravite": "warning",  "code": "<50 feuilles"},
    {"type": "disque_bas",         "label": "Disque bas",           "icon": "icon_disque_bas.svg",         "gravite": "warning",  "code": "<5 Go"},
    {"type": "crash_relance",      "label": "Crash relancé",        "icon": "icon_crash_relance.svg",      "gravite": "warning",  "code": "auto-restart"},
]

GRAVITE_OPTIONS = ["critique", "warning", "info"]
GRAVITE_COLORS = {"critique": "#EF4444", "warning": "#F59E0B", "info": "#3B82F6"}


def _load_icon_pixmap(filename, size=32):
    """Charge un SVG sans modifier les couleurs."""
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


class PaletteOverlay(QWidget):
    """Modal affichant la palette d'erreurs avec icônes Figma + combo gravité."""

    def __init__(self, on_save=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._on_save = on_save
        self._combos = []
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        card = QWidget()
        card.setFixedSize(500, 520)
        card.setObjectName("palette_card")
        card.setStyleSheet(f"""
            QWidget#palette_card {{
                background-color: {T()['card_bg']};
                border: 1px solid {T()['card_border']};
                border-radius: 16px;
            }}
        """)

        cl = QVBoxLayout(card)
        cl.setContentsMargins(28, 24, 28, 24)
        cl.setSpacing(0)

        # Header
        header = QHBoxLayout()
        title = QLabel("Palette d'erreurs")
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
        cl.addSpacing(4)

        subtitle = QLabel("Modifiez la gravité de chaque type d'erreur. Les alertes critiques déclenchent un SMS.")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: #888888; font-family: 'Inter'; font-size: 11px; background: transparent;")
        cl.addWidget(subtitle)
        cl.addSpacing(16)

        # Scroll pour les lignes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: transparent; }}
            QScrollBar:vertical {{ width: 4px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {T()['scroll_handle']}; border-radius: 2px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        rows_layout = QVBoxLayout(inner)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(10)

        for item in ALERTE_TYPES:
            row = QHBoxLayout()
            row.setSpacing(12)

            # Icône
            icon_lbl = QLabel()
            pm = _load_icon_pixmap(item["icon"], 32)
            icon_lbl.setPixmap(pm)
            icon_lbl.setFixedSize(32, 32)
            icon_lbl.setStyleSheet("background: transparent;")
            row.addWidget(icon_lbl)

            # Label
            name_lbl = QLabel(item["label"])
            name_lbl.setFixedWidth(180)
            name_lbl.setStyleSheet(f"color: {T()['text']}; font-family: 'Inter'; font-size: 13px; background: transparent;")
            row.addWidget(name_lbl)

            row.addStretch()

            # Combo gravité
            combo = QComboBox()
            combo.addItems(GRAVITE_OPTIONS)
            idx = GRAVITE_OPTIONS.index(item["gravite"]) if item["gravite"] in GRAVITE_OPTIONS else 0
            combo.setCurrentIndex(idx)
            combo.setFixedWidth(110)
            combo.setFixedHeight(30)
            combo.setCursor(Qt.PointingHandCursor)
            combo.setStyleSheet(f"""
                QComboBox {{
                    border: 1px solid {T()['card_border']}; border-radius: 6px;
                    padding: 4px 8px; font-family: 'Inter'; font-size: 12px;
                    color: {T()['text']}; background-color: {T()['card_bg']};
                }}
                QComboBox::drop-down {{ border: none; width: 20px; }}
                QComboBox QAbstractItemView {{
                    background-color: {T()['card_bg']}; color: {T()['text']};
                    selection-background-color: {LIME_GREEN}; selection-color: {TEXT_BLACK};
                    border: 1px solid {T()['card_border']};
                }}
            """)
            row.addWidget(combo)

            self._combos.append((item["type"], combo))
            rows_layout.addLayout(row)

        rows_layout.addStretch()
        scroll.setWidget(inner)
        cl.addWidget(scroll, 1)
        cl.addSpacing(12)

        # Bouton Enregistrer
        save_btn = QPushButton("Enregistrer")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setFixedHeight(38)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {LIME_GREEN}; color: {TEXT_BLACK};
                border-radius: 8px; padding: 6px 20px; font-family: 'Inter';
                font-size: 13px; font-weight: 600; border: none;
            }}
            QPushButton:hover {{ background-color: #A8EE4A; }}
        """)
        save_btn.clicked.connect(self._save)
        cl.addWidget(save_btn)

        layout.addWidget(card)

    def _close(self):
        self.hide()

    def _save(self):
        result = {}
        for alert_type, combo in self._combos:
            result[alert_type] = combo.currentText()
        if self._on_save:
            self._on_save(result)
        self._close()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        p.end()

    def mousePressEvent(self, event):
        if self.childAt(event.pos()) is None:
            self._close()
