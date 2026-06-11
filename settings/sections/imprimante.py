"""Section IMPRIMANTE — nom, serial, statut, coupe, veille USB."""
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout
from ..widgets import section_title, SectionCard, label, separator, ToggleSwitch


def build_imprimante_section():
    lbl_nom = label("...", size=13)
    lbl_serial = label("...", size=13)
    lbl_statut = label("...", size=13)
    toggle_coupe = ToggleSwitch(on=True)
    toggle_no_sleep = ToggleSwitch(on=False)

    card = SectionCard()
    cl = QVBoxLayout(card)
    cl.setContentsMargins(20, 16, 20, 16)
    cl.setSpacing(10)

    for key, val_w in [("Nom", lbl_nom), ("Numéro de série", lbl_serial), ("Statut", lbl_statut)]:
        r = QHBoxLayout()
        r.addWidget(label(key, bold=True))
        r.addStretch()
        r.addWidget(val_w)
        cl.addLayout(r)
        cl.addWidget(separator())

    coupe_row = QHBoxLayout()
    coupe_row.addWidget(label("Coupe 2 pouces", bold=True))
    coupe_row.addStretch()
    coupe_row.addWidget(toggle_coupe)
    cl.addLayout(coupe_row)
    cl.addWidget(separator())

    # Empêcher la veille USB de la DS620 (fix bouchon file impression Windows).
    # Le réglage est stocké directement dans le registre Windows et persiste
    # indéfiniment, même après désinstallation/réinstallation de l'agent.
    no_sleep_row = QHBoxLayout()
    no_sleep_row.addWidget(label("Empêcher veille USB", bold=True))
    no_sleep_row.addStretch()
    no_sleep_row.addWidget(toggle_no_sleep)
    cl.addLayout(no_sleep_row)

    refs = {
        "lbl_nom": lbl_nom,
        "lbl_serial": lbl_serial,
        "lbl_statut": lbl_statut,
        "toggle_coupe": toggle_coupe,
        "toggle_no_sleep": toggle_no_sleep,
    }
    return section_title("IMPRIMANTE"), card, refs
