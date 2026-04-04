"""Section SYSTÈME — mode maintenance uniquement."""
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout

from dashboard import T
from ..widgets import section_title, SectionCard, label, separator, ToggleSwitch


def build_systeme_section():
    toggle_maint = ToggleSwitch(on=False)

    card = SectionCard()
    sl = QVBoxLayout(card)
    sl.setContentsMargins(20, 16, 20, 16)
    sl.setSpacing(10)

    # Mode maintenance
    maint_row = QHBoxLayout()
    maint_row.addWidget(label("Mode maintenance", bold=True))
    maint_row.addStretch()
    maint_row.addWidget(toggle_maint)
    sl.addLayout(maint_row)

    desc = label("Suspend les alertes pendant la maintenance.", muted=True, size=11)
    sl.addWidget(desc)

    refs = {
        "toggle_maint": toggle_maint,
    }
    return section_title("SYSTÈME"), card, refs
