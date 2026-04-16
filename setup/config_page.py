"""Page 3 : Configuration initiale — design shadcn sobre."""
import os
import socket
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QScrollArea, QFrame
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRectF
from PyQt5.QtGui import QPixmap, QPalette, QColor, QPainter, QPainterPath, QFont, QPen

import supabase_client as supa
from paths import ASSETS_DIR, reg_get, reg_set

JOURS = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

# Couleurs
BG = "#FFFFFF"
TEXT = "#0F172A"
TEXT_MUTED = "#64748B"
BORDER = "#E2E8F0"
GREEN = "#B6FF56"
BLACK = "#000000"


class _FetchWorker(QThread):
    finished = pyqtSignal(object)
    def __init__(self, func, *args):
        super().__init__()
        self._f, self._a = func, args
    def run(self):
        try: self.finished.emit(self._f(*self._a))
        except: self.finished.emit(None)


class _Card(QWidget):
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, 12, 12)
        p.fillPath(path, QColor(BG))
        p.setPen(QPen(QColor(BORDER), 1.7))
        p.drawPath(path)
        p.end()


class _TimeInput(QLineEdit):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setFixedSize(80, 38)
        self.setAlignment(Qt.AlignCenter)
        self.setMaxLength(5)
        self.setPlaceholderText("HH:MM")
        self.setStyleSheet(f"""
            QLineEdit {{
                border: 1.7px solid {BORDER}; border-radius: 8px;
                font-family: 'Satoshi'; font-size: 13px; color: {TEXT};
                background: {BG}; padding: 4px;
            }}
            QLineEdit:focus {{ border: 2px solid {GREEN}; }}
        """)


def _section_title(text):
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {TEXT}; font-family: 'Satoshi'; font-size: 11px; "
        f"font-weight: 700; letter-spacing: 0.1em; background: transparent; "
        f"padding-top: 12px;"
    )
    return lbl


def _separator():
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background-color: {BORDER}; border: none;")
    return sep


def _label(text, bold=False, muted=False, size=13):
    weight = "600" if bold else "400"
    color = TEXT_MUTED if muted else TEXT
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {color}; font-family: 'Satoshi'; font-size: {size}px; "
        f"font-weight: {weight}; background: transparent;"
    )
    return lbl


def _styled_input(placeholder=""):
    inp = QLineEdit()
    inp.setPlaceholderText(placeholder)
    inp.setFixedHeight(40)
    inp.setStyleSheet(f"""
        QLineEdit {{
            border: 1.7px solid {BORDER}; border-radius: 8px;
            padding: 6px 14px; font-family: 'Satoshi'; font-size: 13px;
            color: {TEXT}; background: {BG};
        }}
        QLineEdit:focus {{ border: 2px solid {GREEN}; }}
    """)
    p = inp.palette()
    p.setColor(QPalette.PlaceholderText, QColor(TEXT_MUTED))
    inp.setPalette(p)
    return inp


class ConfigPage(QWidget):
    def __init__(self, on_finish=None, parent=None):
        super().__init__(parent)
        self._on_finish = on_finish
        self._borne_id = None
        self._workers = []
        self._build()
        self._detect_borne()

    def _run(self, func, cb, *args):
        w = _FetchWorker(func, *args)
        w.finished.connect(cb)
        self._workers.append(w)
        w.start()

    def _build(self):
        self.setStyleSheet(f"background: #F8FAFC;")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        from touch_scroll import enable_touch_scroll
        enable_touch_scroll(scroll)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: #F8FAFC; }}
            QScrollBar:vertical {{ width: 6px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: #CBD5E1; border-radius: 3px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        inner = QWidget()
        inner.setStyleSheet(f"background: #F8FAFC;")
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(60, 30, 60, 30)
        vl.setSpacing(14)

        # ── HEADER ──
        header = QHBoxLayout()
        logo = QLabel()
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.exists(logo_path):
            logo.setPixmap(QPixmap(logo_path).scaled(40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setStyleSheet("background: transparent;")
        header.addWidget(logo)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Configuration")
        title.setStyleSheet(
            f"color: {TEXT}; font-family: 'Satoshi'; font-size: 24px; "
            f"font-weight: 700; background: transparent;"
        )
        title_col.addWidget(title)
        subtitle = QLabel("Configurez votre borne pour commencer")
        subtitle.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: 'Satoshi'; font-size: 13px; "
            f"background: transparent;"
        )
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()
        vl.addLayout(header)
        vl.addSpacing(8)

        # ── BORNE ──
        vl.addWidget(_section_title("BORNE"))
        card_borne = _Card()
        bl = QVBoxLayout(card_borne)
        bl.setContentsMargins(20, 16, 20, 16)
        bl.setSpacing(12)

        r1 = QHBoxLayout()
        r1.addWidget(_label("Hostname", bold=True))
        r1.addStretch()
        hostname_lbl = _label(socket.gethostname())
        hostname_lbl.setStyleSheet(
            f"color: {TEXT}; font-family: 'Satoshi'; font-size: 13px; "
            f"background: #F1F5F9; border-radius: 6px; padding: 4px 12px;"
        )
        r1.addWidget(hostname_lbl)
        bl.addLayout(r1)
        bl.addWidget(_separator())

        r2 = QHBoxLayout()
        r2.addWidget(_label("Nom du lieu", bold=True))
        r2.addStretch()
        self._inp_nom_lieu = _styled_input("Ex: Latina Café")
        self._inp_nom_lieu.setMinimumWidth(240)
        r2.addWidget(self._inp_nom_lieu)
        bl.addLayout(r2)
        vl.addWidget(card_borne)

        # ── HORAIRES ──
        vl.addWidget(_section_title("HORAIRES D'OUVERTURE"))
        card_hor = _Card()
        hl = QVBoxLayout(card_hor)
        hl.setContentsMargins(20, 16, 20, 16)
        hl.setSpacing(8)

        desc = _label(
            "L'agent envoie les alertes uniquement pendant ces horaires.",
            muted=True, size=12
        )
        desc.setWordWrap(True)
        hl.addWidget(desc)
        hl.addSpacing(4)

        col_hdr = QHBoxLayout()
        col_hdr.setSpacing(0)
        for txt, w in [("Jour", 100), ("Ouverture", 90), ("", 20), ("Fermeture", 90)]:
            lbl = QLabel(txt)
            lbl.setFixedWidth(w)
            if txt:
                lbl.setStyleSheet(
                    f"color: {TEXT_MUTED}; font-family: 'Satoshi'; font-size: 11px; "
                    f"font-weight: 600; background: transparent;"
                )
            if txt in ("Ouverture", "Fermeture"):
                lbl.setAlignment(Qt.AlignCenter)
            col_hdr.addWidget(lbl)
        col_hdr.addStretch()
        hl.addLayout(col_hdr)

        self._horaires = []
        for jour in JOURS:
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl_day = _label(jour, size=13)
            lbl_day.setFixedWidth(100)
            row.addWidget(lbl_day)
            inp_o = _TimeInput("00:00")
            row.addWidget(inp_o)
            tiret = QLabel("—")
            tiret.setFixedWidth(20)
            tiret.setAlignment(Qt.AlignCenter)
            tiret.setStyleSheet(f"color: {TEXT}; font-size: 14px; background: transparent;")
            row.addWidget(tiret)
            inp_f = _TimeInput("23:59")
            row.addWidget(inp_f)
            row.addStretch()
            hl.addLayout(row)
            self._horaires.append((inp_o, inp_f))
        vl.addWidget(card_hor)

        # ── CONTACTS ──
        vl.addWidget(_section_title("CONTACTS ALERTES SMS"))
        card_contacts = _Card()
        cl = QVBoxLayout(card_contacts)
        cl.setContentsMargins(20, 16, 20, 16)
        cl.setSpacing(12)

        desc2 = _label(
            "Ces personnes recevront un SMS en cas d'alerte critique.",
            muted=True, size=12
        )
        desc2.setWordWrap(True)
        cl.addWidget(desc2)
        cl.addSpacing(4)

        self._contacts = []
        for i in range(2):
            if i > 0:
                cl.addWidget(_separator())
                cl.addSpacing(4)

            e_row = QHBoxLayout()
            e_row.addWidget(_label("Email", bold=True))
            e_row.addStretch()
            inp_email = _styled_input("email@exemple.com")
            inp_email.setMinimumWidth(240)
            e_row.addWidget(inp_email)
            cl.addLayout(e_row)

            t_row = QHBoxLayout()
            t_row.addWidget(_label("Téléphone", bold=True))
            t_row.addStretch()
            inp_tel = _styled_input("+33 6 XX XX XX XX")
            inp_tel.setMinimumWidth(240)
            t_row.addWidget(inp_tel)
            cl.addLayout(t_row)

            self._contacts.append({"email": inp_email, "tel": inp_tel})
        vl.addWidget(card_contacts)

        # ── CODE PIN ──
        vl.addWidget(_section_title("CODE PIN"))
        card_pin = _Card()
        pl = QVBoxLayout(card_pin)
        pl.setContentsMargins(20, 20, 20, 20)
        pl.setSpacing(14)

        pin_desc = _label(
            "Ce code protège l'accès à l'agent après déconnexion.",
            muted=True, size=12
        )
        pl.addWidget(pin_desc)

        pin_row = QHBoxLayout()
        pin_row.setAlignment(Qt.AlignCenter)
        pin_row.setSpacing(14)
        self._pin_inputs = []
        for _ in range(4):
            inp = QLineEdit()
            inp.setFixedSize(56, 56)
            inp.setMaxLength(1)
            inp.setAlignment(Qt.AlignCenter)
            inp.setStyleSheet(f"""
                QLineEdit {{
                    border: 1.7px solid {BORDER}; border-radius: 12px;
                    font-family: 'Satoshi'; font-size: 24px; font-weight: 700;
                    color: {TEXT}; background: {BG};
                }}
                QLineEdit:focus {{ border: 2px solid {GREEN}; }}
            """)
            inp.textChanged.connect(lambda text, idx=len(self._pin_inputs): self._pin_advance(text, idx))
            pin_row.addWidget(inp)
            self._pin_inputs.append(inp)
        pl.addLayout(pin_row)
        vl.addWidget(card_pin)

        vl.addSpacing(12)

        # Bouton Continuer
        btn = QPushButton("Continuer")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setFixedHeight(46)
        btn.setStyleSheet(f"""
            QPushButton {{
                background: {BLACK}; color: {BG};
                border-radius: 10px; font-family: 'Satoshi';
                font-size: 14px; font-weight: 600; border: none;
            }}
            QPushButton:hover {{ background: #1E293B; }}
        """)
        btn.clicked.connect(self._finish)
        vl.addWidget(btn)

        vl.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)

    def _pin_advance(self, text, idx):
        if text and idx < 3:
            self._pin_inputs[idx + 1].setFocus()

    def _detect_borne(self):
        self._run(supa.get_or_create_borne, self._on_borne)

    def _on_borne(self, data):
        if data:
            self._borne_id = data["id"]
            nom = data.get("nom_lieu", "")
            if nom and not nom.startswith("Borne "):
                self._inp_nom_lieu.setText(nom)

    def _finish(self):
        pin = "".join(i.text() for i in self._pin_inputs)
        if len(pin) < 4:
            pin = "0000"

        reg_set("pin", pin)
        reg_set("setup_done", 1)

        # Collecter toutes les données à envoyer
        nom_lieu = self._inp_nom_lieu.text().strip()
        rows = []
        for i, (inp_o, inp_f) in enumerate(self._horaires):
            o, fv = inp_o.text().strip(), inp_f.text().strip()
            rows.append({"jour": i, "ouverture": o or "00:00", "fermeture": fv or "00:00", "ferme": not o or not fv})
        contacts = []
        for c in self._contacts:
            tel = c["tel"].text().strip()
            email = c["email"].text().strip()
            if tel or email:
                contacts.append({"email": email, "telephone": tel})

        borne_id = self._borne_id
        on_finish = self._on_finish

        # Envoyer tout dans un seul thread, puis passer au dashboard
        def _save_all():
            nonlocal borne_id
            if not borne_id:
                borne = supa.get_or_create_borne()
                if borne:
                    borne_id = borne["id"]
                else:
                    return
            try:
                supa.patch_borne(borne_id, {"setup_done": True})
            except Exception:
                pass
            if nom_lieu:
                try:
                    supa.patch_borne(borne_id, {"nom_lieu": nom_lieu})
                except Exception:
                    pass
            try:
                supa.save_horaires(borne_id, rows)
            except Exception:
                pass
            if contacts:
                try:
                    supa.save_alerte_destinataires(borne_id, contacts)
                except Exception:
                    pass

        def _on_saved(result):
            if on_finish:
                on_finish()

        self._run(_save_all, _on_saved)
