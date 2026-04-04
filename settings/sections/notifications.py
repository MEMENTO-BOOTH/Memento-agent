"""Section NOTIFICATIONS — destinataires des alertes SMS.
Les SMS sont envoyés par la Edge Function (send-sms-alerte) via Database Webhook.
Les destinataires sont stockés dans la table alerte_destinataires."""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPalette, QColor

from dashboard import T, LIME_GREEN, TEXT_BLACK
from ..widgets import section_title, SectionCard, label, separator, styled_input, lime_btn


def build_notifications_section():
    btn_add = QPushButton("+")
    btn_add.setFixedSize(30, 30)
    btn_add.setCursor(Qt.PointingHandCursor)
    btn_add.setStyleSheet(f"""
        QPushButton {{
            background-color: {LIME_GREEN}; color: {TEXT_BLACK};
            font-size: 18px; font-weight: 700; font-family: 'Inter';
            border: none; border-radius: 15px;
        }}
        QPushButton:hover {{ background-color: #A8EE4A; }}
    """)

    # Header row
    header = QHBoxLayout()
    header.addWidget(section_title("NOTIFICATIONS"))
    header.addStretch()
    header.addWidget(btn_add, 0, Qt.AlignBottom)

    card = SectionCard()
    notif_layout = QVBoxLayout(card)
    notif_layout.setContentsMargins(20, 16, 20, 16)
    notif_layout.setSpacing(0)

    # Description
    desc = label(
        "Les alertes critiques envoient un SMS via Twilio. "
        "Ajoutez les numéros qui doivent recevoir les alertes.",
        muted=True, size=11,
    )
    desc.setWordWrap(True)
    notif_layout.addWidget(desc)
    notif_layout.addSpacing(10)

    # Bouton Enregistrer
    btn_save = lime_btn("Enregistrer")
    save_row = QHBoxLayout()
    save_row.addStretch()
    save_row.addWidget(btn_save)

    refs = {
        "header_layout": header,
        "card": card,
        "notif_layout": notif_layout,
        "btn_add": btn_add,
        "btn_save": btn_save,
        "save_row": save_row,
        "contact_rows": [],
    }
    return header, card, refs


def create_contact_row(email="", tel="", removable=True, on_remove=None):
    """Crée un widget contact (email + tel)."""
    container = QWidget()
    container.setStyleSheet("background: transparent;")
    cl = QVBoxLayout(container)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(10)

    # Email
    email_row = QHBoxLayout()
    email_row.addWidget(label("Email", bold=True))
    email_row.addStretch()
    inp_email = styled_input(email)
    inp_email.setMinimumWidth(220)
    inp_email.setPlaceholderText("email@exemple.com")
    p = inp_email.palette()
    p.setColor(QPalette.PlaceholderText, QColor("#AAAAAA"))
    inp_email.setPalette(p)
    email_row.addWidget(inp_email)

    if removable:
        del_btn = QPushButton("\u2715")
        del_btn.setFixedSize(28, 28)
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: #CC4444;
                font-size: 14px; font-weight: 700; border: none; border-radius: 14px;
            }}
            QPushButton:hover {{ background-color: #FFEEEE; color: #AA0000; }}
        """)
        if on_remove:
            del_btn.clicked.connect(lambda: on_remove(container))
        email_row.addWidget(del_btn)

    cl.addLayout(email_row)

    # Téléphone
    tel_row = QHBoxLayout()
    tel_row.addWidget(label("Téléphone", bold=True))
    tel_row.addStretch()
    inp_tel = styled_input(tel)
    inp_tel.setMinimumWidth(220)
    inp_tel.setPlaceholderText("+33 6 XX XX XX XX")
    p2 = inp_tel.palette()
    p2.setColor(QPalette.PlaceholderText, QColor("#AAAAAA"))
    inp_tel.setPalette(p2)
    tel_row.addWidget(inp_tel)

    if removable:
        spacer = QWidget()
        spacer.setFixedWidth(28)
        spacer.setStyleSheet("background: transparent;")
        tel_row.addWidget(spacer)

    cl.addLayout(tel_row)

    # Stocker les inputs sur le container pour les récupérer plus tard
    container._inp_email = inp_email
    container._inp_tel = inp_tel

    return container
