"""Overlay modification des horaires d'ouverture."""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QColor, QPalette

from dashboard import T, LIME_GREEN, TEXT_BLACK
from ..widgets import ToggleSwitch


class _TimeInput(QLineEdit):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setFixedSize(72, 36)
        self.setAlignment(Qt.AlignCenter)
        self.setMaxLength(5)
        self.setPlaceholderText("HH:MM")
        p = self.palette()
        p.setColor(QPalette.PlaceholderText, QColor("#AAAAAA"))
        self.setPalette(p)
        self.setStyleSheet(f"""
            QLineEdit {{
                border: 1.5px solid {T()['card_border']}; border-radius: 8px;
                font-family: 'Inter'; font-size: 13px; font-weight: 500;
                color: {T()['text']}; background-color: {T()['content_bg']};
            }}
            QLineEdit:focus {{ border: 2px solid {LIME_GREEN}; }}
            QLineEdit:disabled {{ background-color: {T()['table_header_bg']}; color: #AAAAAA; }}
        """)


class HorairesOverlay(QWidget):
    def __init__(self, horaires_data, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._day_widgets = []
        self._horaires_data = horaires_data
        self._on_confirm_cb = None
        self._build()

    def set_on_confirm(self, cb):
        self._on_confirm_cb = cb

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        card = QWidget()
        card.setFixedSize(480, 480)
        card.setObjectName("hor_card")
        card.setStyleSheet(f"""
            QWidget#hor_card {{
                background-color: {T()['card_bg']};
                border: 1px solid {T()['card_border']};
                border-radius: 16px;
            }}
        """)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(28, 24, 28, 24)
        cl.setSpacing(0)

        header = QHBoxLayout()
        title = QLabel("Modifier les horaires")
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
        cl.addSpacing(6)

        subtitle = QLabel("Définissez les plages horaires pour chaque jour")
        subtitle.setStyleSheet(f"color: #888888; font-family: 'Inter'; font-size: 12px; background: transparent;")
        cl.addWidget(subtitle)
        cl.addSpacing(16)

        # En-tête colonnes
        col_hdr = QHBoxLayout()
        col_hdr.setSpacing(0)
        for txt, w in [("Jour", 90), ("Statut", 60)]:
            lbl = QLabel(txt)
            lbl.setFixedWidth(w)
            lbl.setStyleSheet(f"color: #888888; font-family: 'Inter'; font-size: 11px; font-weight: 600; background: transparent;")
            col_hdr.addWidget(lbl)
        col_hdr.addStretch()
        for txt in ["Ouverture", "Fermeture"]:
            lbl = QLabel(txt)
            lbl.setFixedWidth(80)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(f"color: #888888; font-family: 'Inter'; font-size: 11px; font-weight: 600; background: transparent;")
            col_hdr.addWidget(lbl)
            if txt == "Ouverture":
                col_hdr.addSpacing(16)
        cl.addLayout(col_hdr)
        cl.addSpacing(6)

        # 7 jours
        jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        for i, jour in enumerate(jours):
            _, heures = self._horaires_data[i]
            is_open = heures != "Fermé"

            row = QHBoxLayout()
            row.setSpacing(0)
            lbl_day = QLabel(jour)
            lbl_day.setFixedWidth(90)
            lbl_day.setStyleSheet(f"color: {T()['text']}; font-family: 'Inter'; font-size: 13px; font-weight: 500; background: transparent;")
            row.addWidget(lbl_day)

            toggle = ToggleSwitch(on=is_open)
            toggle.setFixedSize(40, 22)
            row.addWidget(toggle)
            row.addStretch()

            h_open, h_close = "", ""
            if is_open and " – " in heures:
                parts = heures.split(" – ")
                h_open, h_close = parts[0], parts[1]

            inp_open = _TimeInput(h_open)
            inp_open.setEnabled(is_open)
            row.addWidget(inp_open)

            tiret = QLabel("–")
            tiret.setFixedWidth(16)
            tiret.setAlignment(Qt.AlignCenter)
            tiret.setStyleSheet(f"color: {T()['text']}; font-family: 'Inter'; font-size: 14px; background: transparent;")
            row.addWidget(tiret)

            inp_close = _TimeInput(h_close)
            inp_close.setEnabled(is_open)
            row.addWidget(inp_close)

            # Toggle handler
            toggle.mousePressEvent_orig = toggle.mousePressEvent
            def _make_toggle_handler(tg, io, ic):
                def handler(event):
                    tg.mousePressEvent_orig(event)
                    io.setEnabled(tg.is_on())
                    ic.setEnabled(tg.is_on())
                    if not tg.is_on():
                        io.clear()
                        ic.clear()
                return handler
            toggle.mousePressEvent = _make_toggle_handler(toggle, inp_open, inp_close)

            self._day_widgets.append((toggle, inp_open, inp_close))
            cl.addLayout(row)
            cl.addSpacing(4)

        cl.addStretch()

        # Boutons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        cancel_btn = QPushButton("Annuler")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setFixedHeight(38)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{ background-color: transparent; color: {T()['text']}; border: 1px solid {T()['card_border']}; border-radius: 8px; padding: 6px 20px; font-family: 'Inter'; font-size: 13px; font-weight: 500; }}
            QPushButton:hover {{ background-color: {T()['row_sep']}; }}
        """)
        cancel_btn.clicked.connect(self._close)
        btn_row.addWidget(cancel_btn, 1)

        confirm_btn = QPushButton("Confirmer")
        confirm_btn.setCursor(Qt.PointingHandCursor)
        confirm_btn.setFixedHeight(38)
        confirm_btn.setStyleSheet(f"""
            QPushButton {{ background-color: {LIME_GREEN}; color: {TEXT_BLACK}; border-radius: 8px; padding: 6px 20px; font-family: 'Inter'; font-size: 13px; font-weight: 600; border: none; }}
            QPushButton:hover {{ background-color: #A8EE4A; }}
        """)
        confirm_btn.clicked.connect(self._confirm)
        btn_row.addWidget(confirm_btn, 1)
        cl.addLayout(btn_row)
        layout.addWidget(card)

    def _close(self):
        self.hide()

    def _confirm(self):
        jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        new_data = []
        for i, (toggle, inp_open, inp_close) in enumerate(self._day_widgets):
            if toggle.is_on() and inp_open.text().strip() and inp_close.text().strip():
                heures = f"{inp_open.text().strip()} – {inp_close.text().strip()}"
            else:
                heures = "Fermé"
            new_data.append((jours[i], heures))
        if self._on_confirm_cb:
            self._on_confirm_cb(new_data)
        self._close()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 120))
        p.end()

    def mousePressEvent(self, event):
        if self.childAt(event.pos()) is None:
            self._close()
