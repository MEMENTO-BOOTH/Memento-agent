"""Chargement des alertes depuis Supabase.
Mapping exact entre les codes imprimante DNP DS620, les types d'alertes,
et les icônes Figma."""
import supabase_client as supa

# ─── Codes statut imprimante DNP DS620 (depuis remontee_finale_1.0.0) ───
STATUS_MAP = {
    0x10001: "En veille",
    0x10002: "Impression en cours",
    0x10004: "À l'arrêt",
    0x10008: "Fin de papier",
    0x10010: "Fin de ruban",
    0x10020: "Refroidissement tête",
    0x10040: "Refroidissement moteur",
    0x10080: "Refroidissement",
    0x18000: "Mode veille prolongée",
    0x20001: "Capot ouvert",
    0x20002: "Bourrage papier",
    0x20004: "Erreur ruban",
    0x20008: "Erreur définition papier",
    0x20010: "Erreur données",
    0x20020: "Bac à déchets plein",
    0x40001: "Erreur tension tête",
    0x40002: "Erreur position tête",
    0x40004: "Erreur ventilateur",
    0x40008: "Erreur cutter",
    0x40020: "Température tête anormale",
    0x40040: "Température média anormale",
    0x40100: "Erreur module RFID",
    0x80000000: "Erreur générale",
}

# Codes normaux (pas d'alerte)
CODES_NORMAUX = {0x10001, 0x10002, 0x10080, 0x18000}

# ─── Mapping type alerte → icône Figma ───────────────────────────────────
# Les icônes Figma sont des cercles colorés (rouge/orange) avec icône blanche.
# Elles sont chargées SANS modifier les couleurs (pas de color_override).
TYPE_TO_ICON = {
    # Critiques (cercle rouge #EF4444)
    "bourrage_papier":    "alert_bourrage_papier.svg",
    "fin_papier":         "alert_fin_de_papier.svg",
    "fin_ruban":          "alert_fin_de_papier.svg",
    "capot_ouvert":       "alert_capot_ouvert.svg",
    "bac_chutes_plein":   "alert_disque_plein_new.svg",
    "erreur_mecanique":   "alert_erreur_mecanique.svg",
    "crash_dslrbooth":    "alert_crash_dslrbooth.svg",
    "crash_cashinterface":"alert_crash_dslrbooth.svg",
    "imprimante_deconnectee": "alert_erreur_mecanique.svg",
    "coupe_incoherente": "icon_coupe_incoherente.svg",
    "disque_plein":       "alert_disque_plein_new.svg",
    "camera_deconnectee": "icon_camera_deconnectee.svg",
    "borne_hors_ligne":   "icon_borne_hors_ligne.svg",
    # Warnings (cercle orange #F59E0B)
    "surchauffe":         "icon_surchauffe.svg",
    "papier_bas":         "icon_papier_bas.svg",
    "disque_bas":         "icon_disque_bas.svg",
    "crash_relance":      "icon_crash_relance.svg",
    "impression_non_delivree": "icon_impression_non_delivree.svg",
    "drive_deconnecte": "icon_drive_deconnecte.svg",
}

# ─── Mapping code imprimante → type alerte (depuis twilio_1.0.0) ─────────
CODE_TO_ALERTE = {
    0x20002: {"type": "bourrage_papier",  "gravite": "critique", "message": "Bourrage papier. Intervention nécessaire."},
    0x10008: {"type": "fin_papier",       "gravite": "critique", "message": "Plus de papier. Rouleau à changer."},
    0x10010: {"type": "fin_ruban",        "gravite": "critique", "message": "Ruban épuisé. À remplacer."},
    0x20001: {"type": "capot_ouvert",     "gravite": "critique", "message": "Capot ouvert. Vérifier l'imprimante."},
    0x20020: {"type": "bac_chutes_plein", "gravite": "critique", "message": "Bac à déchets plein. À vider."},
    # Erreurs mécaniques (>= 0x40001)
    0x40001: {"type": "erreur_mecanique", "gravite": "critique", "message": "Erreur tension tête. SAV nécessaire."},
    0x40002: {"type": "erreur_mecanique", "gravite": "critique", "message": "Erreur position tête. SAV nécessaire."},
    0x40004: {"type": "erreur_mecanique", "gravite": "critique", "message": "Erreur ventilateur. SAV nécessaire."},
    0x40008: {"type": "erreur_mecanique", "gravite": "critique", "message": "Erreur cutter. SAV nécessaire."},
    # Warnings
    0x10020: {"type": "surchauffe",       "gravite": "warning",  "message": "Surchauffe tête. Refroidissement en cours."},
    0x10040: {"type": "surchauffe",       "gravite": "warning",  "message": "Surchauffe moteur. Refroidissement en cours."},
}

# ─── Labels français ─────────────────────────────────────────────────────
TYPE_LABELS = {
    "bourrage_papier":    "Bourrage papier",
    "fin_papier":         "Fin de papier",
    "fin_ruban":          "Fin de ruban",
    "capot_ouvert":       "Capot ouvert",
    "bac_chutes_plein":   "Bac à déchets plein",
    "erreur_mecanique":   "Erreur mécanique",
    "surchauffe":         "Surchauffe",
    "papier_bas":         "Papier bas",
    "disque_plein":       "Disque plein",
    "disque_bas":         "Disque bas",
    "camera_deconnectee": "Caméra déconnectée",
    "crash_dslrbooth":    "Crash DSLRBOOTH",
    "crash_cashinterface":"Crash Cash Interface",
    "imprimante_deconnectee": "Imprimante déconnectée",
    "coupe_incoherente": "Coupe 2 pouces désactivée",
    "crash_relance":      "Crash relancé",
    "borne_hors_ligne":   "Borne hors ligne",
    "impression_non_delivree": "Impression non délivrée",
    "drive_deconnecte": "Google Drive déconnecté",
}


def fetch_alertes(borne_id, limit=50):
    """Récupère les alertes depuis Supabase."""
    return supa.get_alertes(borne_id, limit)


def resolve_alerte(alerte_id):
    """Marque une alerte comme résolue."""
    try:
        from datetime import datetime
        import requests
        r = requests.patch(
            f"{supa.SUPABASE_URL}/rest/v1/alertes?id=eq.{alerte_id}",
            headers=supa.HEADERS_MINIMAL,
            json={
                "statut": "resolue",
                "resolue_par": "agent-manuel",
                "resolue_at": datetime.now().isoformat(),
            },
            timeout=10,
        )
        return r.status_code in (200, 204)
    except Exception:
        return False


def assign_alerte(alerte_id, assignee):
    """Assigne une alerte à quelqu'un."""
    try:
        from datetime import datetime
        import requests
        r = requests.patch(
            f"{supa.SUPABASE_URL}/rest/v1/alertes?id=eq.{alerte_id}",
            headers=supa.HEADERS_MINIMAL,
            json={
                "statut": "assignee",
                "assignee_a": assignee,
                "assignee_at": datetime.now().isoformat(),
            },
            timeout=10,
        )
        return r.status_code in (200, 204)
    except Exception:
        return False


def delete_alerte(alerte_id):
    """Supprime une alerte."""
    try:
        import requests
        r = requests.delete(
            f"{supa.SUPABASE_URL}/rest/v1/alertes?id=eq.{alerte_id}",
            headers=supa.HEADERS_MINIMAL,
            timeout=10,
        )
        return r.status_code in (200, 204)
    except Exception:
        return False
