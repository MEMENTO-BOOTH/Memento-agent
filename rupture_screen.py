"""Écran de rupture — plein écran quand alerte critique.
Bloque l'écran du photobooth. Cadenas pour sortir avec le PIN."""

import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QDialog, QApplication,
)
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QColor, QFont, QPixmap

from paths import ASSETS_DIR


class RuptureScreen(QWidget):
    """Plein écran de rupture — design sombre avec message + QR code."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_DeleteOnClose, False)
        self.setStyleSheet("background: #020617;")
        self._build()

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Cadenas feather en haut à droite
        from PyQt5.QtSvg import QSvgRenderer
        from PyQt5.QtCore import QByteArray
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 16, 24, 0)
        top_bar.addStretch()

        lock_icon_path = os.path.join(ASSETS_DIR, "icon_lock.svg")
        lock_icon = QPixmap(40, 40)
        lock_icon.fill(Qt.transparent)
        if os.path.exists(lock_icon_path):
            with open(lock_icon_path, "r") as f:
                svg_data = f.read()
            renderer = QSvgRenderer(QByteArray(svg_data.encode()))
            p = QPainter(lock_icon)
            renderer.render(p)
            p.end()
        from PyQt5.QtGui import QIcon
        self._lock_btn = QPushButton()
        self._lock_btn.setIcon(QIcon(lock_icon))
        self._lock_btn.setFixedSize(44, 44)
        self._lock_btn.setCursor(Qt.PointingHandCursor)
        self._lock_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.1); border: none; border-radius: 22px;
            }
            QPushButton:hover { background: rgba(255,255,255,0.2); }
        """)
        self._lock_btn.clicked.connect(self._show_pin_dialog)
        top_bar.addWidget(self._lock_btn)
        layout.addLayout(top_bar)

        # Contenu central
        center = QHBoxLayout()
        center.setContentsMargins(60, 0, 60, 60)
        center.setSpacing(48)

        # Gauche — texte
        left = QVBoxLayout()
        left.setSpacing(18)

        brand = QLabel("MEMENTO BOOTH")
        brand.setStyleSheet(
            "color: #6B7280; font-family: 'Satoshi'; font-size: 13px; "
            "letter-spacing: 0.18em; background: transparent;"
        )
        left.addWidget(brand)

        title = QLabel("Victime de son succès,\nil n'y a plus de Mementos en stock 🥲")
        title.setWordWrap(True)
        title.setStyleSheet(
            "color: #F9FAFB; font-family: 'Satoshi'; font-size: 34px; "
            "font-weight: 600; line-height: 1.2; background: transparent;"
        )
        left.addWidget(title)

        text = QLabel(
            "Nous sommes momentanément en rupture sur cette borne.\n"
            "De nouveaux tirages arrivent très bientôt."
        )
        text.setWordWrap(True)
        text.setStyleSheet(
            "color: #D1D5DB; font-family: 'Satoshi'; font-size: 17px; "
            "background: transparent;"
        )
        left.addWidget(text)

        note = QLabel("Merci pour votre passage, et à très vite pour de nouveaux souvenirs 💚")
        note.setWordWrap(True)
        note.setStyleSheet(
            "color: #9CA3AF; font-family: 'Satoshi'; font-size: 14px; "
            "background: transparent;"
        )
        left.addWidget(note)
        left.addStretch()

        center.addLayout(left, 3)

        # Droite — QR code
        right = QVBoxLayout()
        right.setAlignment(Qt.AlignCenter)
        right.setSpacing(12)

        qr_label = QLabel()
        qr_path = os.path.join(ASSETS_DIR, "qr_instagram.png")
        if os.path.exists(qr_path):
            qr_label.setPixmap(QPixmap(qr_path).scaled(190, 190, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            qr_label.setText("QR")
            qr_label.setFixedSize(190, 190)
            qr_label.setAlignment(Qt.AlignCenter)
            qr_label.setStyleSheet(
                "color: #22C55E; font-size: 40px; font-weight: 700; "
                "background: rgba(255,255,255,0.05); border-radius: 12px;"
            )
        qr_label.setStyleSheet(qr_label.styleSheet() + "background: transparent;")
        right.addWidget(qr_label)

        caption = QLabel("Scannez le QR code pour nous écrire\nou suivre nos actualités.")
        caption.setAlignment(Qt.AlignCenter)
        caption.setStyleSheet(
            "color: #9CA3AF; font-family: 'Satoshi'; font-size: 13px; "
            "background: transparent;"
        )
        right.addWidget(caption)

        center.addLayout(right, 2)
        layout.addLayout(center)

    def _show_pin_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Déverrouiller")
        dlg.setFixedSize(340, 420)
        dlg.setStyleSheet("background: #0F172A;")

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(24, 20, 24, 20)
        vl.setSpacing(10)

        title = QLabel("Code PIN")
        title.setStyleSheet(
            "color: white; font-family: 'Satoshi'; font-size: 16px; "
            "font-weight: 700; background: transparent;"
        )
        vl.addWidget(title)

        inp = QLineEdit()
        inp.setEchoMode(QLineEdit.Password)
        inp.setReadOnly(True)
        inp.setPlaceholderText("______")
        inp.setFixedHeight(44)
        inp.setAlignment(Qt.AlignCenter)
        inp.setStyleSheet(
            "border: 1.7px solid #334155; border-radius: 8px; "
            "padding: 6px 14px; font-family: 'Satoshi'; font-size: 22px; "
            "letter-spacing: 12px; color: white; background: transparent;"
        )
        vl.addWidget(inp)

        err = QLabel("")
        err.setAlignment(Qt.AlignCenter)
        err.setStyleSheet("color: #EF4444; font-family: 'Satoshi'; font-size: 12px; background: transparent;")
        vl.addWidget(err)

        # Pavé numérique tactile
        from PyQt5.QtWidgets import QGridLayout
        grid = QGridLayout()
        grid.setSpacing(8)

        btn_style = (
            "QPushButton { background: #1E293B; color: white; border: 1.7px solid #334155; "
            "border-radius: 10px; font-family: 'Satoshi'; font-size: 20px; font-weight: 600; } "
            "QPushButton:pressed { background: #334155; }"
        )

        def _add_digit(d):
            if len(inp.text()) < 6:
                inp.setText(inp.text() + d)

        for i, num in enumerate(["1","2","3","4","5","6","7","8","9"]):
            b = QPushButton(num)
            b.setFixedSize(80, 56)
            b.setCursor(Qt.PointingHandCursor)
            b.setStyleSheet(btn_style)
            b.clicked.connect(lambda _, d=num: _add_digit(d))
            grid.addWidget(b, i // 3, i % 3)

        # Ligne du bas : Effacer, 0, OK
        btn_clear = QPushButton("C")
        btn_clear.setFixedSize(80, 56)
        btn_clear.setCursor(Qt.PointingHandCursor)
        btn_clear.setStyleSheet(
            "QPushButton { background: #7F1D1D; color: white; border: none; "
            "border-radius: 10px; font-family: 'Satoshi'; font-size: 18px; font-weight: 600; } "
            "QPushButton:pressed { background: #991B1B; }"
        )
        btn_clear.clicked.connect(lambda: inp.clear())
        grid.addWidget(btn_clear, 3, 0)

        btn_zero = QPushButton("0")
        btn_zero.setFixedSize(80, 56)
        btn_zero.setCursor(Qt.PointingHandCursor)
        btn_zero.setStyleSheet(btn_style)
        btn_zero.clicked.connect(lambda: _add_digit("0"))
        grid.addWidget(btn_zero, 3, 1)

        def _validate():
            import supabase_client as supa
            from paths import reg_get
            pin = inp.text()
            user = supa.verifier_pin(pin)
            if user:
                # Snooze la page rupture : on cache pour 5 min, elle reviendra
                # automatiquement si l'alerte critique est toujours ouverte
                # (sans nouveau SMS). Ne touche PAS a la row Supabase ni au cache
                # d'alertes : seule la disparition reelle de la cause physique
                # (statut DNP OK, etc.) resout vraiment l'alerte.
                try:
                    from monitoring.alertes.alertes_monitor import snooze_rupture
                    snooze_rupture()
                except Exception:
                    pass
                dlg.accept()
                self.hide()
                return
            err.setText("Code PIN incorrect")
            inp.clear()

        btn_ok = QPushButton("OK")
        btn_ok.setFixedSize(80, 56)
        btn_ok.setCursor(Qt.PointingHandCursor)
        btn_ok.setStyleSheet(
            "QPushButton { background: #B6FF56; color: #0F172A; border: none; "
            "border-radius: 10px; font-family: 'Satoshi'; font-size: 18px; font-weight: 600; } "
            "QPushButton:pressed { background: #A8EE4A; }"
        )
        btn_ok.clicked.connect(_validate)
        grid.addWidget(btn_ok, 3, 2)

        vl.addLayout(grid)
        dlg.exec_()

    def show_fullscreen(self):
        """Affiche en plein écran."""
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.showFullScreen()
        self.raise_()
        self.activateWindow()


# Instance globale
_rupture = None


def show_rupture():
    """Affiche l'écran de rupture."""
    global _rupture
    if _rupture is None:
        _rupture = RuptureScreen()
    if not _rupture.isVisible():
        _rupture.show_fullscreen()


def hide_rupture():
    """Cache l'écran de rupture."""
    global _rupture
    if _rupture and _rupture.isVisible():
        _rupture.hide()


def is_rupture_visible():
    return _rupture is not None and _rupture.isVisible()
