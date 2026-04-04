"""Section CODE E-MEMENTO — config apparence du code court."""
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QWidget
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QColor
from ..widgets import section_title, SectionCard, label, separator, styled_input
from dashboard import T, LIME_GREEN, TEXT_BLACK

from paths import reg_get, reg_set


POLICES = ["arial.ttf", "verdana.ttf", "tahoma.ttf", "calibri.ttf", "consola.ttf"]
COULEURS_TEXTE = ["white", "black", "#B6FF56", "#F7DB2C", "#EF4444"]
COULEURS_FOND = ["transparent", "black", "white", "#1A1A1A", "#333333"]
COULEURS_LABELS = {
    "white": "Blanc", "black": "Noir", "transparent": "Transparent",
    "#B6FF56": "Vert", "#F7DB2C": "Jaune", "#EF4444": "Rouge",
    "#1A1A1A": "Noir foncé", "#333333": "Gris foncé",
}


def _combo(items, current_val):
    cb = QComboBox()
    cb.setCursor(Qt.PointingHandCursor)
    cb.setFixedHeight(32)
    cb.setStyleSheet(f"""
        QComboBox {{
            border: 1px solid {T()['card_border']}; border-radius: 6px;
            padding: 4px 10px; font-family: 'Inter'; font-size: 12px;
            color: {T()['text']}; background: {T()['content_bg']};
        }}
        QComboBox::drop-down {{ border: none; width: 24px; }}
        QComboBox QAbstractItemView {{ background: {T()['card_bg']}; color: {T()['text']}; }}
    """)
    for item in items:
        display = COULEURS_LABELS.get(item, item.replace(".ttf", "").capitalize())
        cb.addItem(display, item)
    for i in range(cb.count()):
        if cb.itemData(i) == current_val:
            cb.setCurrentIndex(i)
            break
    return cb


class _PreviewWidget(QWidget):
    """Aperçu du code avec fond damier (transparence) ou couleur pleine."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self._text = "K7MPNXR"
        self._text_color = "white"
        self._bg_color = "transparent"
        self._font_size = 32

    def set_config(self, text_color, bg_color, font_size):
        self._text_color = text_color
        self._bg_color = bg_color
        self._font_size = min(font_size, 40)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # Fond : damier si transparent, couleur sinon
        if self._bg_color == "transparent":
            cell = 8
            for row in range(self.height() // cell + 1):
                for col in range(self.width() // cell + 1):
                    c = QColor("#E0E0E0") if (row + col) % 2 == 0 else QColor("#F5F5F5")
                    p.fillRect(col * cell, row * cell, cell, cell, c)
        else:
            p.fillRect(self.rect(), QColor(self._bg_color))

        # Bordure arrondie
        from PyQt5.QtGui import QPen, QPainterPath
        from PyQt5.QtCore import QRectF
        border = QPainterPath()
        border.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 8, 8)
        p.setPen(QPen(QColor(T()["card_border"]), 1))
        p.drawPath(border)

        # Texte
        from PyQt5.QtGui import QFont
        font = QFont("Inter")
        font.setPixelSize(self._font_size)
        font.setWeight(75)
        p.setFont(font)
        p.setPen(QColor(self._text_color))
        p.drawText(self.rect(), Qt.AlignCenter, self._text)

        p.end()


def build_emmento_section():
    # Lire la config actuelle depuis le registre
    taille = reg_get("emmento_taille_police")
    try:
        taille = int(taille) if taille else 50
    except (ValueError, TypeError):
        taille = 50
    couleur_texte = reg_get("emmento_couleur_texte") or "white"
    couleur_fond = reg_get("emmento_couleur_fond") or "transparent"
    police = reg_get("emmento_police") or "arial.ttf"

    inp_taille = styled_input(str(taille))
    inp_taille.setFixedWidth(60)

    combo_texte = _combo(COULEURS_TEXTE, couleur_texte)
    combo_fond = _combo(COULEURS_FOND, couleur_fond)
    combo_police = _combo(POLICES, police)

    # Aperçu peint (pas de QLabel — tout peint pour un rendu fidèle)
    preview = _PreviewWidget()
    preview.set_config(couleur_texte, couleur_fond, taille)

    def _update_preview():
        t_size = inp_taille.text().strip()
        try:
            sz = int(t_size) if t_size else 50
        except ValueError:
            sz = 50
        c_texte = combo_texte.currentData() or "white"
        c_fond = combo_fond.currentData() or "transparent"
        preview.set_config(c_texte, c_fond, sz)

    def _save():
        t_size = inp_taille.text().strip()
        try:
            sz = int(t_size) if t_size else 50
        except ValueError:
            sz = 50
        reg_set("emmento_taille_police", str(sz))
        reg_set("emmento_couleur_texte", combo_texte.currentData() or "white")
        reg_set("emmento_couleur_fond", combo_fond.currentData() or "transparent")
        reg_set("emmento_police", combo_police.currentData() or "arial.ttf")
        _update_preview()

    combo_texte.currentIndexChanged.connect(_save)
    combo_fond.currentIndexChanged.connect(_save)
    combo_police.currentIndexChanged.connect(_save)
    inp_taille.editingFinished.connect(_save)

    # Construction de la carte
    card = SectionCard()
    cl = QVBoxLayout(card)
    cl.setContentsMargins(20, 16, 20, 16)
    cl.setSpacing(10)

    for key, val_w in [
        ("Taille du texte", inp_taille),
        ("Couleur du texte", combo_texte),
        ("Couleur du fond", combo_fond),
        ("Police", combo_police),
    ]:
        r = QHBoxLayout()
        r.addWidget(label(key, bold=True))
        r.addStretch()
        r.addWidget(val_w)
        cl.addLayout(r)
        cl.addWidget(separator())

    # Aperçu
    r_apercu = QHBoxLayout()
    r_apercu.addWidget(label("Aperçu", bold=True))
    r_apercu.addSpacing(16)
    r_apercu.addWidget(preview, 1)
    cl.addLayout(r_apercu)

    refs = {
        "inp_taille": inp_taille,
        "combo_texte": combo_texte,
        "combo_fond": combo_fond,
        "combo_police": combo_police,
        "preview": preview,
    }
    return section_title("CODE E-MEMENTO"), card, refs
