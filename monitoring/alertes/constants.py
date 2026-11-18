"""Constantes du monitoring — codes imprimante, seuils, intervalles."""

# Intervalle entre chaque cycle de monitoring (secondes)
HEARTBEAT_INTERVAL = 60
ALERTE_CHECK_INTERVAL = 30

# Seuils d'alertes
SEUIL_PAPIER_BAS = 50        # feuilles
SEUIL_DISQUE_BAS = 5.0       # Go
SEUIL_DISQUE_PLEIN = 1.0     # Go
SEUIL_HORS_LIGNE_MIN = 5     # minutes sans heartbeat

# Imprimantes DNP — gamme complete.
# On matche :
#  - le prefixe DP- (nom standard DNP Windows: "DP-DS620", "DP-DS-RX1"...)
#  - "DNP" dans le nom
#  - Les noms de modeles bruts quand l'utilisateur a renomme l'imprimante
#    sans le prefixe DP- (observe MB-50 : "DS-RX1" tout court).
PRINTER_PATTERNS = ["DP-", "DNP", "DS-RX", "DS620", "DS820", "DS40", "DS80", "QW410"]

# Modeles compatibles avec la DLL Cx2Stat64 (DNP Status Monitor API, DS620 series
# officiellement). Appeler PortInitialize/GetStatus de Cx2Stat64 sur un modele non
# liste ici peut provoquer un segfault natif (ex: observe sur DS-RX1, v1.0.28.9
# -> dashboard blanc + process tue). On protege : si le modele n'est pas dans
# cette liste, lire_imprimante retourne le nom seul sans toucher a la DLL.
CX2STAT_COMPATIBLE_PATTERNS = ["DS620"]

# v1.0.28.30 : chaque famille DNP a sa propre DLL de statut. Utiliser la
# mauvaise provoque un segfault natif qui tue le process (MB-50, v1.0.28.9).
#   Cx2Stat64.dll -> DS620 series   (DNP Status Monitor API)
#   CyStat64.dll  -> DS-RX1 series  (Printer Status API v1.4.0.0)
# Les autres modeles DNP (DS820, DS40, DS80, QW410) n'ont pas de DLL fournie :
# ils restent en fallback "En veille" sans statut ni compteur.
#
# L'ordre compte en cas de nom ambigu : DS-RX est teste AVANT DS620 parce que
# les deux erreurs n'ont pas la meme gravite. Cx2Stat64 sur une RX1 = segfault
# natif qui tue le process agent (MB-50). CyStat64 sur une DS620 = au pire une
# lecture qui echoue. En cas de doute on penche donc du cote qui ne tue pas.
PRINTER_DLL_MAP = [
    (["DS-RX1", "DSRX1", "DS-RX"], "CyStat64.dll"),
    (["DS620"], "Cx2Stat64.dll"),
]

# Modeles dont l'ouverture du port est toleree sur une borne Kapsule.
#
# Regle generale : sur Kapsule l'agent evite d'ouvrir le port DNP, Kapsule le
# tient pour imprimer (MB-50, v1.0.28.13).
#
# Cx2Stat64 (DS620) : exception historique. Le collector heartbeat ouvre ce
# port depuis des mois sans incident sur les bornes Kapsule (lecture breve,
# toutes les 60-90 s, serialisee par DNP_PORT_LOCK) et c'est ce qui alimente
# feuilles_restantes.
#
# CyStat64 (DS-RX1) : ajoute en v1.0.28.30, sur mesure et non par analogie.
# Kapsule 0.1.60 n'embarque QUE Cx2Stat64 (verifie dans ses resources sur
# MB-50) : il est donc incapable de lire une RX1 et ne tient pas ce port.
# Son health.json le confirme -> "printer_media_counter": null. Sans cette
# entree, la seule RX1 du parc resterait aveugle et continuerait de produire
# de fausses alertes "photo non sortie".
# Mesure sur MB-50 le 18/11/2026, Kapsule et l'agent tournant en meme temps :
# PortInitialize("USB003") = 1, 15 lectures consecutives, GetStatus stable a
# 0x00010001, aucun travail d'impression cree (file vide avant/apres chaque
# lecture), aucun incident.
KAPSULE_PORT_ALLOWED_DLLS = {"Cx2Stat64.dll", "CyStat64.dll"}

# Modeles dont Kapsule publie lui-meme le compteur dans health.json. Pour
# ceux-la, le PrinterCounterWatcher lit health.json plutot que le port : c'est
# Kapsule qui imprime, il sait mieux que nous quand le port est libre.
# Les autres modeles (RX1) ne sont pas publies par Kapsule, faute de DLL de
# son cote : l'agent les lit directement.
KAPSULE_HEALTH_JSON_DLLS = {"Cx2Stat64.dll"}

# DLL dont les codes de statut ont ete valides en production.
# Les tables STATUS_MAP / ALERTES_CRITIQUES / SEUIL_ERREUR_MECANIQUE ont ete
# construites sur la DS620. Sur la RX1, un seul code a ete observe a ce jour :
# 0x00010001 (En veille), identique a la DS620 — l'encodage est donc tres
# probablement partage. Mais "probablement" ne suffit pas pour armer un SMS :
# un code inconnu >= 0x40001 serait range en "erreur mecanique", ce qui
# declenche une alerte critique ET l'ecran de rupture plein ecran qui bloque
# la borne. Tant qu'on n'a pas observe les codes d'erreur reels d'une RX1, on
# journalise son code brut sans appliquer ce fourre-tout.
STATUS_CODES_TRUSTED_DLLS = {"Cx2Stat64.dll"}


def ecarter_ports_ambigus(candidats):
    """Retire les candidats dont le port est revendique par deux familles DNP.

    Retourne (candidats_retenus, ports_ecartes).

    Le registre Windows identifie un PILOTE, jamais le peripherique
    physiquement branche au bout du port. Une entree residuelle "DP-DS620"
    laissee par une imprimante remplacee porte le nom ET le driver d'une
    DS620 : la regle "le driver prime sur le nom" de get_printer_dll ne la
    distingue pas de la vraie. Si une DS-RX1 a ete branchee sur ce meme port
    depuis, on appellerait Cx2Stat64 sur une RX1.

    Quand deux entrees pointent le meme port en resolvant vers deux DLL
    differentes, on ne sait pas ce qu'il y a au bout. On ne touche donc a ce
    port avec AUCUNE des deux : perdre le statut d'une imprimante coute
    infiniment moins cher que de parler a un peripherique avec la
    bibliotheque d'une autre famille.

    candidats : [(nom, port, nom_dll), ...]"""
    par_port = {}
    for _nom, port, dll in candidats:
        par_port.setdefault(port, set()).add(dll)
    ambigus = {p for p, dlls in par_port.items() if len(dlls) > 1}
    if not ambigus:
        return candidats, ambigus
    return [c for c in candidats if c[1] not in ambigus], ambigus


def dll_probe_rank(dll_name):
    """Ordre d'essai des DLL : Cx2Stat64 d'abord.

    Le tri des imprimantes candidates se fait par longueur de nom, qui est
    arbitraire vis-a-vis du modele. Une entree registre courte pointant une
    RX1 passerait donc avant une DS620 au nom plus long, et on sonderait le
    port avec CyStat64 avant d'avoir essaye le chemin eprouve sur les ~28
    bornes DS620 du parc. On force donc Cx2Stat64 en tete : a risque egal,
    le chemin valide depuis des mois passe en premier."""
    return 0 if dll_name == "Cx2Stat64.dll" else 1


def get_printer_dll(name, driver=None):
    """Retourne le nom de la DLL de statut a utiliser, ou None si le modele
    n'a pas de DLL connue ou si l'identification est ambigue.

    Le "Printer Driver" du registre est prioritaire sur le nom affiche :
    le nom est librement editable par l'operateur (vu en prod, des bornes ont
    l'imprimante renommee "DS-RX1" tout court, voire un nom maison), alors que
    le driver reste "DP-DS620" / "DP-DS-RX1". Se fier au nom permettrait a une
    entree fantome "DP-DS620" pointant un port occupe par une RX1 de faire
    charger Cx2Stat64 sur une RX1 -> segfault qui tue le process (MB-50).

    Si le nom et le driver designent deux familles differentes, on renvoie
    None : mieux vaut perdre le statut que risquer la mauvaise DLL."""
    def _match(value):
        v = (value or "").upper()
        for patterns, dll in PRINTER_DLL_MAP:
            if any(p.upper() in v for p in patterns):
                return dll
        return None

    by_driver = _match(driver)
    by_name = _match(name)
    if by_driver and by_name and by_driver != by_name:
        # Identification contradictoire : on refuse de deviner.
        return None
    return by_driver or by_name

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
    mais on ne lit pas leur statut via cette DLL pour eviter un crash natif.

    Conserve pour ne pas casser les imports existants. Le code qui doit choisir
    une DLL utilise get_printer_dll(), qui gere aussi les DS-RX1."""
    n = (name or "").upper()
    return any(p.upper() in n for p in CX2STAT_COMPATIBLE_PATTERNS)


def has_status_dll(name):
    """Vrai si une DLL de statut existe pour ce modele (DS620 ou DS-RX1).
    Les modeles sans DLL restent en fallback 'En veille'."""
    return get_printer_dll(name) is not None


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
    "kapsule_fige",             # kapsule_timestamp (poste par Kapsule Bar) > 2 min = processus Kapsule mort
    "kapsule_mauvaise_borne",   # kapsule_hostname != hostname OS reel = config/token clonee depuis une autre borne
    "capot_ouvert", "bac_chutes_plein", "erreur_mecanique",
    "surchauffe", "papier_bas", "camera_deconnectee",
    "crash_dslrbooth", "disque_bas", "disque_plein",
    "crash_relance", "borne_hors_ligne",
    "impression_non_delivree",  # client a payé, papier jamais sorti (vérif DS620 GetMediaCounter)
    "drive_deconnecte",         # Drive Desktop éteint / lecture-seule / dossier disparu
    "drive_sync_cassee",        # Drive Desktop tourne mais ne sync plus vers le cloud (token expiré, compte déconnecté)
]