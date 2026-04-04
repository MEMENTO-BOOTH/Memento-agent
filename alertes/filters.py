"""Filtres pour les alertes."""


def filter_alertes(alertes, gravite=None, statut=None):
    """Filtre la liste d'alertes par gravité et/ou statut."""
    result = alertes
    if gravite:
        result = [a for a in result if a.get("gravite") == gravite]
    if statut:
        result = [a for a in result if a.get("statut") == statut]
    return result
