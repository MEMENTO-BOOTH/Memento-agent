"""Section ECLAIRAGE - calibration de la bande LED Pico.

Toggle on/off, affichage du statut Pico (port COM ou erreur), et deux sliders :
- "Lumiere douce" (1-100%) : niveau permanent entre les photos
- "Boost photo" (1-100%)   : niveau du flash applique sur capture_start

Bouton "Tester boost" pour declencher la sequence sans passer par dslrBooth.
"""
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout

from paths import reg_get
from ..widgets import (
    section_title, SectionCard, label, separator,
    ToggleSwitch, lime_btn, styled_slider,
)


def build_led_section():
    enabled = bool(reg_get("led_enabled"))
    normal_pct = int(reg_get("led_normal_pct") or 5)
    boost_pct = int(reg_get("led_boost_pct") or 30)

    toggle_enabled = ToggleSwitch(on=enabled)
    lbl_status = label("Recherche...", muted=True)
    slider_normal = styled_slider(1, 100, max(1, normal_pct))
    lbl_normal_value = label(f"{normal_pct}%", bold=True)
    slider_boost = styled_slider(1, 100, max(1, boost_pct))
    lbl_boost_value = label(f"{boost_pct}%", bold=True)
    btn_test = lime_btn("Tester boost")

    card = SectionCard()
    cl = QVBoxLayout(card)
    cl.setContentsMargins(20, 16, 20, 16)
    cl.setSpacing(10)

    # Row 1 : toggle activer
    r1 = QHBoxLayout()
    r1.addWidget(label("Activer l'eclairage dynamique", bold=True))
    r1.addStretch()
    r1.addWidget(toggle_enabled)
    cl.addLayout(r1)

    cl.addWidget(separator())

    # Row 2 : statut Pico
    r2 = QHBoxLayout()
    r2.addWidget(label("Statut Pico", bold=True))
    r2.addStretch()
    r2.addWidget(lbl_status)
    cl.addLayout(r2)

    cl.addWidget(separator())

    # Row 3 : lumiere douce (label + valeur sur une ligne, slider sur la suivante)
    r3 = QHBoxLayout()
    r3.addWidget(label("Lumiere douce (entre photos)", bold=True))
    r3.addStretch()
    r3.addWidget(lbl_normal_value)
    cl.addLayout(r3)
    r3b = QHBoxLayout()
    r3b.addWidget(slider_normal)
    cl.addLayout(r3b)

    cl.addWidget(separator())

    # Row 4 : boost photo
    r4 = QHBoxLayout()
    r4.addWidget(label("Boost photo (capture)", bold=True))
    r4.addStretch()
    r4.addWidget(lbl_boost_value)
    cl.addLayout(r4)
    r4b = QHBoxLayout()
    r4b.addWidget(slider_boost)
    cl.addLayout(r4b)

    cl.addWidget(separator())

    # Row 5 : bouton de test
    r5 = QHBoxLayout()
    r5.addWidget(label("Tester l'effet", bold=True))
    r5.addStretch()
    r5.addWidget(btn_test)
    cl.addLayout(r5)

    refs = {
        "toggle_enabled": toggle_enabled,
        "lbl_status": lbl_status,
        "slider_normal": slider_normal,
        "lbl_normal_value": lbl_normal_value,
        "slider_boost": slider_boost,
        "lbl_boost_value": lbl_boost_value,
        "btn_test": btn_test,
    }
    return section_title("ECLAIRAGE"), card, refs
