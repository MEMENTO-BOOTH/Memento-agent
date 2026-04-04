"""Section MISE À JOUR — bandeau style shadcn Alert avec actions."""
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QWidget,
)
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QColor, QPainterPath

from dashboard import T, TEXT_WHITE, LIME_GREEN, TEXT_BLACK
from ..widgets import section_title, label


class _UpdateBanner(QWidget):
    """Bandeau de mise à jour — fond noir, coins arrondis, style alert shadcn."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self._visible = True

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 12, 12)
        p.fillPath(path, QColor("#0F172A"))
        p.end()


def build_mise_a_jour_section():
    from version import VERSION

    # ── Bandeau principal (fond noir) ──
    banner = _UpdateBanner()
    banner.setMinimumHeight(120)
    bl = QHBoxLayout(banner)
    bl.setContentsMargins(20, 18, 16, 18)
    bl.setSpacing(16)

    # Icône cercle info
    icon_lbl = QLabel("ℹ")
    icon_lbl.setFixedSize(24, 24)
    icon_lbl.setAlignment(Qt.AlignCenter)
    icon_lbl.setStyleSheet(
        "color: white; font-size: 16px; font-weight: 700; "
        "background: rgba(255,255,255,0.15); border-radius: 12px;"
    )
    bl.addWidget(icon_lbl, 0, Qt.AlignTop)

    # Colonne texte + boutons
    col = QVBoxLayout()
    col.setSpacing(10)

    # Titre
    lbl_title = QLabel(f"Version actuelle : v{VERSION}")
    lbl_title.setStyleSheet(
        "color: white; font-family: 'Satoshi'; font-size: 14px; "
        "font-weight: 700; background: transparent;"
    )
    col.addWidget(lbl_title)

    # Description (MAJ dispo ou à jour)
    lbl_desc = QLabel("Vérification en cours...")
    lbl_desc.setWordWrap(True)
    lbl_desc.setStyleSheet(
        "color: rgba(255,255,255,0.7); font-family: 'Satoshi'; "
        "font-size: 12px; background: transparent;"
    )
    col.addWidget(lbl_desc)

    # Notes de version (caché par défaut)
    lbl_notes = QLabel("")
    lbl_notes.setWordWrap(True)
    lbl_notes.setStyleSheet(
        "color: rgba(255,255,255,0.6); font-family: 'Satoshi'; "
        "font-size: 11px; background: transparent;"
    )
    lbl_notes.hide()
    col.addWidget(lbl_notes)

    # Boutons
    btn_row = QHBoxLayout()
    btn_row.setSpacing(10)

    btn_check = QPushButton("Vérifier")
    btn_check.setCursor(Qt.PointingHandCursor)
    btn_check.setFixedHeight(28)
    btn_check.setStyleSheet("""
        QPushButton {
            background: rgba(255,255,255,0.1); color: white;
            border: none; border-radius: 6px; padding: 4px 14px;
            font-family: 'Satoshi'; font-size: 12px; font-weight: 500;
        }
        QPushButton:hover { background: rgba(255,255,255,0.2); }
    """)
    btn_row.addWidget(btn_check)

    btn_install = QPushButton("Installer maintenant")
    btn_install.setCursor(Qt.PointingHandCursor)
    btn_install.setFixedHeight(28)
    btn_install.setStyleSheet(f"""
        QPushButton {{
            background: white; color: #0F172A;
            border: none; border-radius: 6px; padding: 4px 14px;
            font-family: 'Satoshi'; font-size: 12px; font-weight: 600;
        }}
        QPushButton:hover {{ background: #E2E8F0; }}
    """)
    btn_install.hide()
    btn_row.addWidget(btn_install)

    btn_row.addStretch()
    col.addLayout(btn_row)

    bl.addLayout(col, 1)

    # Bouton fermer (X)
    btn_close = QPushButton("✕")
    btn_close.setFixedSize(24, 24)
    btn_close.setCursor(Qt.PointingHandCursor)
    btn_close.setStyleSheet("""
        QPushButton {
            background: transparent; color: rgba(255,255,255,0.5);
            border: none; font-size: 14px; font-weight: 600;
        }
        QPushButton:hover { color: white; }
    """)
    btn_close.clicked.connect(lambda: banner.hide())
    bl.addWidget(btn_close, 0, Qt.AlignTop)

    # Badge (caché, utilisé par settings_widget pour le statut)
    badge = QLabel("")
    badge.hide()

    # Compat : lbl_version pointe vers lbl_title pour la mise à jour
    refs = {
        "lbl_version": lbl_title,
        "lbl_latest": lbl_desc,
        "lbl_notes": lbl_notes,
        "badge": badge,
        "btn_check": btn_check,
        "btn_install": btn_install,
        "banner": banner,
    }
    return section_title("MISE À JOUR"), banner, refs
