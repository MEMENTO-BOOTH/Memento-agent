"""Calcul des statistiques d'alertes."""

# Types visuellement "warning" (orange) — même si Supabase dit "critique"
_TYPES_WARNING_VISUEL = {"surchauffe", "papier_bas", "disque_bas", "coupe_incoherente", "crash_relance", "borne_hors_ligne"}


def compute_stats(alertes):
    """Retourne un dict de stats à partir de la liste d'alertes."""
    total = len(alertes)
    ouvertes = sum(1 for a in alertes if a.get("statut") == "ouverte")
    assignees = sum(1 for a in alertes if a.get("statut") == "assignee")
    resolues = sum(1 for a in alertes if a.get("statut") == "resolue")
    critiques = sum(1 for a in alertes if a.get("type", "") not in _TYPES_WARNING_VISUEL and a.get("statut") != "resolue")
    warnings = sum(1 for a in alertes if a.get("type", "") in _TYPES_WARNING_VISUEL and a.get("statut") != "resolue")

    return {
        "total": total,
        "ouvertes": ouvertes,
        "assignees": assignees,
        "resolues": resolues,
        "critiques": critiques,
        "warnings": warnings,
    }
