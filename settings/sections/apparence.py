"""Section APPARENCE — thème + langue."""
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel
from ..widgets import section_title, SectionCard, label, separator, styled_combo


def build_apparence_section(theme_index=0, lang_index=0):
    combo_theme = styled_combo(["Clair", "Sombre"], theme_index)
    combo_lang = styled_combo(["Français", "English"], lang_index)
    combo_lang.setEnabled(False)  # Pas encore implémenté

    card = SectionCard()
    al = QVBoxLayout(card)
    al.setContentsMargins(20, 16, 20, 16)
    al.setSpacing(10)

    theme_row = QHBoxLayout()
    theme_row.addWidget(label("Thème", bold=True))
    theme_row.addStretch()
    theme_row.addWidget(combo_theme)
    al.addLayout(theme_row)

    al.addWidget(separator())

    lang_row = QHBoxLayout()
    lang_row.addWidget(label("Langue", bold=True))
    lang_row.addStretch()
    lang_row.addWidget(combo_lang)
    soon = label("Bientôt disponible", muted=True, size=10)
    lang_row.addWidget(soon)
    al.addLayout(lang_row)

    refs = {"combo_theme": combo_theme, "combo_lang": combo_lang}
    return section_title("APPARENCE"), card, refs
