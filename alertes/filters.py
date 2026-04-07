"""Filtres pour les alertes."""

# Types visuellement "warning" (orange) — même si Supabase dit "critique"
_TYPES_WARNING_VISUEL = {"surchauffe", "papier_bas", "disque_bas", "coupe_incoherente", "crash_relance"}


def _gravite_visuelle(alerte):
    return "warning" if alerte.get("type", "") in _TYPES_WARNING_VISUEL else "critique"


def filter_alertes(alertes, gravite=None, statut=None):
    """Filtre la liste d'alertes par gravité visuelle et/ou statut."""
    result = alertes
    if gravite:
        result = [a for a in result if _gravite_visuelle(a) == gravite]
    if statut:
        result = [a for a in result if a.get("statut") == statut]
    return result
