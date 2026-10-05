"""Constantes du monitoring — codes imprimante, seuils, intervalles."""

# Intervalle entre chaque cycle de monitoring (secondes)
HEARTBEAT_INTERVAL = 60
ALERTE_CHECK_INTERVAL = 30

# Seuils d'alertes
SEUIL_PAPIER_BAS = 50        # feuilles
SEUIL_DISQUE_BAS = 5.0       # Go
SEUIL_DISQUE_PLEIN = 1.0     # Go
SEUIL_HORS_LIGNE_MIN = 5     # minutes sans heartbeat

# Imprimantes DNP — gamme complete (DS620, DS820, DS-RX1, DS40, DS80, QW410...).
# La DLL Cx2Stat64 (DNP Status Monitor API) est generique DNP, elle fonctionne
# sur tous ces modeles -> on filtre les imprimantes Windows uniquement sur leur
# origine DNP ("DP-" prefixe commun, ou "DNP" dans le nom), pas sur le modele.
PRINTER_PATTERNS = ["DP-", "DNP"]

# Modeles compatibles avec la DLL Cx2Stat64 (DNP Status Monitor API, DS620 series
# officiellement). Appeler PortInitialize/GetStatus de Cx2Stat64 sur un modele non
# liste ici peut provoquer un segfault natif (ex: observe sur DS-RX1, v1.0.28.9
# -> dashboard blanc + process tue). On protege : si le modele n'est pas dans
# cette liste, lire_imprimante retourne le nom seul sans toucher a la DLL.
CX2STAT_COMPATIBLE_PATTERNS = ["DS620"]

# Capacite media (feuilles 4x6 par defaut) par modele DNP. Utilise pour
# afficher le compteur / donut cote dashboard quand le modele n'est pas
# interrogeable via la DLL (ex: DS-RX1 fournit son propre compteur par Kapsule
# ou on affiche juste la capacite nominale).
MEDIA_CAPACITY = {
    "DS620":  400,
    "DS-RX1": 700,
    "DSRX1":  700,
    "DS820":  230,
    "DS40":   400,
    "DS80":   260,
    "QW410":  230,
}


def get_media_capacity(name, default=400):
    """Retourne la capacite media (feuilles) d'une imprimante DNP par nom."""
    if not name:
        return default
    n = name.upper()
    for model, cap in MEDIA_CAPACITY.items():
        if model.upper() in n:
            return cap
    return default


def is_dnp_printer(name):
    """Vrai si le nom d'imprimante Windows correspond a une DNP (gamme entiere)."""
    n = name.upper()
    return any(p.upper() in n for p in PRINTER_PATTERNS)


def is_cx2stat_compatible(name):
    """Vrai si cette imprimante accepte sans risque les appels de Cx2Stat64.dll
    (DS620 series). Les autres modeles DNP sont detectes (voir is_dnp_printer)
    mais on ne lit pas leur statut via cette DLL pour eviter un crash natif."""
    n = (name or "").upper()
    return any(p.upper() in n for p in CX2STAT_COMPATIBLE_PATTERNS)


# Alias de compat : les anciens imports is_ds620 continuent de fonctionner,
# mais la fonction accepte maintenant tous les modeles DNP.
is_ds620 = is_dnp_printer

# Compatibilite ancienne
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
    0x20004: {"type": "erreur_ruban",       "message": "Erreur ruban. Vérifier l'insertion du média."},
    0x20010: {"type": "erreur_donnees",     "message": "Problème de transmission de données de photo dans l'imprimante. Redémarrer l'imprimante."},
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
    "bourrage_papier", "fin_papier", "fin_ruban", "erreur_ruban", "erreur_donnees", "crash_cashinterface",
    "kapsule_crash", "kapsule_ferme", "kapsule_exe_absent", "kapsule_health_illisible",
    "capot_ouvert", "bac_chutes_plein", "erreur_mecanique",
    "surchauffe", "papier_bas", "camera_deconnectee",
    "crash_dslrbooth", "disque_bas", "disque_plein",
    "crash_relance", "borne_hors_ligne",
    "impression_non_delivree",  # client a payé, papier jamais sorti (vérif DS620 GetMediaCounter)
    "drive_deconnecte",         # Drive Desktop éteint / lecture-seule / dossier disparu
    "drive_sync_cassee",        # Drive Desktop tourne mais ne sync plus vers le cloud (token expiré, compte déconnecté)
]