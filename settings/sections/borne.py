"""Section BORNE — infos de la borne depuis Supabase + avatar initiales."""
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QFileDialog
from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QPainter, QColor, QPainterPath, QFont, QPixmap, QPen
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtCore import QByteArray

from dashboard import T, LIME_GREEN, TEXT_BLACK
from ..widgets import section_title, SectionCard, label, separator

from paths import ASSETS_DIR
import os


def _load_default_avatar(size):
    """Charge l'avatar par défaut shadcn (avatar_default.png)."""
    path = os.path.join(ASSETS_DIR, "avatar_default.png")
    if not os.path.exists(path):
        return None
    pm = QPixmap(path)
    if pm.isNull():
        return None
    return pm.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)


class AvatarInitiales(QWidget):
    """Avatar circulaire style shadcn — photo ou avatar par défaut."""
    def __init__(self, size=48, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self._pixmap = None
        self._default = _load_default_avatar(size)

    def set_nom(self, nom):
        self.update()

    def set_logo(self, pixmap):
        """Affiche un logo/photo au lieu de l'avatar par défaut."""
        self._pixmap = pixmap.scaled(
            self._size, self._size,
            Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation,
        )
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        sz = self._size
        rect = QRectF(0, 0, sz, sz)
        clip = QPainterPath()
        clip.addEllipse(rect)
        p.setClipPath(clip)

        # Photo perso ou avatar shadcn par défaut
        img = self._pixmap if (self._pixmap and not self._pixmap.isNull()) else self._default
        if img and not img.isNull():
            p.drawPixmap(0, 0, img)
        else:
            p.fillPath(clip, QColor("#F1F5F9"))

        p.setClipping(False)
        # Bordure subtile
        p.setPen(QPen(QColor("#E2E8F0"), 1))
        p.drawEllipse(rect.adjusted(0.5, 0.5, -0.5, -0.5))
        p.end()


def build_borne_section():
    """Retourne (title_widget, card_widget, refs)."""
    lbl_nom = label("Chargement...", size=13)
    lbl_ville = label("...", size=13)
    lbl_code = label("...", size=13)
    avatar = AvatarInitiales()

    card = SectionCard()
    vl = QVBoxLayout(card)
    vl.setContentsMargins(20, 20, 20, 20)
    vl.setSpacing(12)

    # Ligne avatar + nom du lieu
    header_row = QHBoxLayout()
    header_row.setSpacing(14)
    header_row.addWidget(avatar)

    name_col = QVBoxLayout()
    name_col.setSpacing(2)
    name_col.addWidget(lbl_nom)
    lbl_sub = label("", muted=True, size=11)
    name_col.addWidget(lbl_sub)
    header_row.addLayout(name_col)
    header_row.addStretch()
    vl.addLayout(header_row)

    # Bouton modifier photo — sur sa propre ligne
    btn_photo = QPushButton("  Modifier la photo du bar  ")
    btn_photo.setCursor(Qt.PointingHandCursor)
    btn_photo.setFixedHeight(34)
    btn_photo.setStyleSheet(f"""
        QPushButton {{
            background: transparent; color: {LIME_GREEN};
            border: 1px solid {LIME_GREEN}; border-radius: 8px;
            padding: 6px 16px; font-family: 'Inter'; font-size: 12px; font-weight: 600;
        }}
        QPushButton:hover {{ background-color: {LIME_GREEN}; color: {TEXT_BLACK}; }}
    """)
    photo_row = QHBoxLayout()
    photo_row.addWidget(btn_photo)
    photo_row.addStretch()
    vl.addLayout(photo_row)

    vl.addWidget(separator())

    for i, (key, val_lbl) in enumerate([
        ("Ville", lbl_ville),
        ("Code borne", lbl_code),
    ]):
        r = QHBoxLayout()
        r.addWidget(label(key, bold=True))
        r.addStretch()
        r.addWidget(val_lbl)
        vl.addLayout(r)
        if i < 1:
            vl.addWidget(separator())

    refs = {
        "lbl_nom": lbl_nom,
        "lbl_ville": lbl_ville,
        "lbl_code": lbl_code,
        "lbl_sub": lbl_sub,
        "avatar": avatar,
        "btn_photo": btn_photo,
    }
    return section_title("BORNE"), card, refs
