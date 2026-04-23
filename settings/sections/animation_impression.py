"""Section ANIMATION IMPRESSION — toggle + bouton 'Configurer'."""
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout
from ..widgets import section_title, SectionCard, label, separator, ToggleSwitch, lime_btn

from overlay import config as cfg_mod
from overlay.presets import get as get_preset


def build_animation_section():
    cfg = cfg_mod.load()
    toggle = ToggleSwitch(on=cfg.get("enabled", False))
    btn_config = lime_btn("Configurer")
    style_name = get_preset(cfg.get("style", "memento"))["name"]
    lbl_style = label(style_name, size=13)
    lbl_duration = label(f"{cfg.get('duration', 18)}s", size=13)

    card = SectionCard()
    cl = QVBoxLayout(card)
    cl.setContentsMargins(20, 16, 20, 16)
    cl.setSpacing(10)

    r1 = QHBoxLayout()
    r1.addWidget(label("Activer l'animation", bold=True))
    r1.addStretch()
    r1.addWidget(toggle)
    cl.addLayout(r1)

    cl.addWidget(separator())

    r2 = QHBoxLayout()
    r2.addWidget(label("Style actuel", bold=True))
    r2.addStretch()
    r2.addWidget(lbl_style)
    cl.addLayout(r2)

    cl.addWidget(separator())

    r3 = QHBoxLayout()
    r3.addWidget(label("Duree", bold=True))
    r3.addStretch()
    r3.addWidget(lbl_duration)
    cl.addLayout(r3)

    cl.addWidget(separator())

    r4 = QHBoxLayout()
    r4.addWidget(label("Personnaliser", bold=True))
    r4.addStretch()
    r4.addWidget(btn_config)
    cl.addLayout(r4)

    refs = {
        "toggle": toggle,
        "btn_config": btn_config,
        "lbl_style": lbl_style,
        "lbl_duration": lbl_duration,
    }
    return section_title("ANIMATION IMPRESSION"), card, refs
