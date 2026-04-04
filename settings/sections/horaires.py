"""Section HORAIRES — lecture/écriture depuis Supabase."""
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout
from ..widgets import section_title, SectionCard, label, lime_btn


DEFAULT_HORAIRES = [
    ("Lundi", "Fermé"),
    ("Mardi", "17:00 – 02:00"),
    ("Mercredi", "17:00 – 02:00"),
    ("Jeudi", "17:00 – 02:00"),
    ("Vendredi", "17:00 – 04:00"),
    ("Samedi", "14:00 – 04:00"),
    ("Dimanche", "Fermé"),
]


def build_horaires_section(horaires_data=None):
    data = horaires_data or list(DEFAULT_HORAIRES)

    card = SectionCard()
    hl = QVBoxLayout(card)
    hl.setContentsMargins(20, 16, 20, 16)
    hl.setSpacing(6)

    desc = label("L'agent envoie une alerte Borne hors ligne uniquement pendant ces horaires.", muted=True, size=11)
    desc.setWordWrap(True)
    hl.addWidget(desc)
    hl.addSpacing(6)

    horaires_labels = []
    for jour, heures in data:
        r = QHBoxLayout()
        r.addWidget(label(jour, size=12))
        r.addStretch()
        is_ferme = heures == "Fermé"
        lbl_h = label(heures, muted=is_ferme, size=12)
        horaires_labels.append(lbl_h)
        r.addWidget(lbl_h)
        hl.addLayout(r)

    hl.addSpacing(8)
    btn_modifier = lime_btn("Modifier les horaires")
    btn_row = QHBoxLayout()
    btn_row.addStretch()
    btn_row.addWidget(btn_modifier)
    hl.addLayout(btn_row)

    refs = {
        "horaires_data": data,
        "horaires_labels": horaires_labels,
        "btn_modifier": btn_modifier,
    }
    return section_title("HORAIRES D'OUVERTURE"), card, refs
