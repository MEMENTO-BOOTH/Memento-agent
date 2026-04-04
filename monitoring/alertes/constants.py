"""Constantes du monitoring — codes imprimante, seuils, intervalles."""

# Intervalle entre chaque cycle de monitoring (secondes)
HEARTBEAT_INTERVAL = 60
ALERTE_CHECK_INTERVAL = 30

# Seuils d'alertes
SEUIL_PAPIER_BAS = 50        # feuilles
SEUIL_DISQUE_BAS = 5.0       # Go
SEUIL_DISQUE_PLEIN = 1.0     # Go
SEUIL_HORS_LIGNE_MIN = 5     # minutes sans heartbeat

# Imprimante DNP DS620 — tous les noms possibles
PRINTER_PATTERNS = ["DP-DS620", "DNP-DS620", "DNP DS620", "DS620"]

def is_ds620(name):
    """Vérifie si le nom correspond à une DS620 (y compris Copie 1, Copie 2...)."""
    n = name.upper()
    return any(p.upper() in n for p in PRINTER_PATTERNS)

# Compatibilité ancienne
BASE_PRINTER_NAME = "DP-DS620"

# Codes statut imprimante → label humain
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

# Code imprimante → type alerte + gravité
ALERTES_CRITIQUES = {
    0x20002: {"type": "bourrage_papier",    "message": "Bourrage papier. Intervention nécessaire."},
    0x10008: {"type": "fin_papier",         "message": "Plus de papier. Rouleau à changer."},
    0x10010: {"type": "fin_ruban",          "message": "Ruban épuisé. À remplacer."},
    0x20001: {"type": "capot_ouvert",       "message": "Capot ouvert. Vérifier l'imprimante."},
    0x20020: {"type": "bac_chutes_plein",   "message": "Bac à déchets plein. À vider."},
}

SEUIL_ERREUR_MECANIQUE = 0x40001

ALERTES_WARNING = {
    0x10020: {"type": "surchauffe", "message": "Surchauffe tête. Refroidissement en cours."},
    0x10040: {"type": "surchauffe", "message": "Surchauffe moteur. Refroidissement en cours."},
}

# Tous les types d'alertes gérés
TOUS_TYPES_ALERTES = [
    "bourrage_papier", "fin_papier", "fin_ruban", "crash_cashinterface",
    "capot_ouvert", "bac_chutes_plein", "erreur_mecanique",
    "surchauffe", "papier_bas", "camera_deconnectee",
    "crash_dslrbooth", "disque_bas", "disque_plein",
    "crash_relance", "borne_hors_ligne",
]
