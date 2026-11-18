"""Chargement des DLL de statut DNP, factorise.

La recherche de chemin etait dupliquee dans collectors/printer.py (liste
`candidates`) et printer_counter.py (`_find_dll()`). v1.0.28.30 la centralise
ici parce qu'il y a desormais deux DLL a charger selon le modele :

    Cx2Stat64.dll -> DS620 series  (DNP Status Monitor API)
    CyStat64.dll  -> DS-RX1 series (Printer Status API v1.4.0.0)

Les handles sont mis en cache : ctypes.WinDLL recharge sinon la meme DLL a
chaque tick du watcher (toutes les 3 s), ce qui est inutile et bruyant.

Note sur PortRelease : cette fonction n'existe dans AUCUNE des deux DLL
(verifie avec pefile le 18/11/2026 : 88 exports pour Cx2Stat64, 72 pour
CyStat64, pas de PortRelease dans l'une ni l'autre). Le code historique
l'appelait quand meme sur Cx2Stat64, l'AttributeError etant avale par un
try/except. Utiliser call_optional() plutot que de supposer qu'une fonction
existe.
"""

import os
import sys
import threading

_lock = threading.Lock()
_cache = {}


def _log(msg):
    """Trace dans alertes.log, pas seulement sur stdout.

    En prod l'agent tourne en fenetre cachee : les print() partent dans le
    vide et sont irrecuperables a distance. Tout ce qui sert au diagnostic
    d'une borne doit passer par activity_logger."""
    print(f"[DNP_DLL] {msg}")
    try:
        import activity_logger as alog
        alog.log_generic("DNP_DLL", msg)
    except Exception:
        pass


# Les echecs de chargement ne sont volontairement PAS mis en cache (voir
# load_dll), donc ils se reproduisent a chaque appel — c'est-a-dire toutes
# les 3 s depuis le watcher. Sans limitation, un incident durable (dossier
# _MEI efface comme en v1.0.28.28, antivirus qui verrouille le fichier au
# boot) ecrirait ~28 800 lignes par jour dans alertes.log. Ce journal tourne
# a 10 Mo avec un seul .old : on effacerait tout l'historique de diagnostic
# au moment precis ou on en a besoin. On journalise donc une fois, puis au
# plus une fois par quart d'heure.
_FAIL_LOG_INTERVAL_S = 900
_last_fail_log = {}


def _log_echec(dll_name, msg):
    import time
    now = time.monotonic()
    if now - _last_fail_log.get(dll_name, float("-inf")) < _FAIL_LOG_INTERVAL_S:
        return
    _last_fail_log[dll_name] = now
    _log(msg)


# Nom de la fonction qui donne le nombre de feuilles REELLEMENT imprimables,
# par DLL. Les deux familles ne comptent pas pareil :
#
#   Cx2Stat64 (DS620)  : GetMediaCounter renvoie directement le restant.
#   CyStat64  (DS-RX1) : GetMediaCounter renvoie un brut dont il faut
#                        retrancher GetMediaCountOffset. GetMediaCounter_R
#                        fait cette soustraction.
#
# Mesure sur MB-50 (parc Ohlain) le 18/11/2026 :
#   GetMediaCounter=480, GetMediaCountOffset=50, GetMediaCounter_R=430,
# et l'outil officiel DNP (RX1-Information.exe) affiche 430 feuilles.
# Prendre GetMediaCounter sur une RX1 publierait donc 50 feuilles de trop :
# l'alerte papier bas (seuil 50) ne serait jamais levee a temps et la borne
# tomberait a court de papier sans prevenir.
MEDIA_COUNTER_FUNC = {
    "Cx2Stat64.dll": "GetMediaCounter",
    "CyStat64.dll": "GetMediaCounter_R",
}
_DEFAULT_MEDIA_COUNTER_FUNC = "GetMediaCounter"


def read_media_counter(dll, dll_name, h_port):
    """Lit le nombre de feuilles restantes avec la fonction propre au modele.

    Retourne l'entier brut, ou None si la lecture echoue. Le filtrage
    metier (compteur <= 0 = imprimante en veille) reste a la charge des
    appelants, qui n'en font pas le meme usage."""
    if dll is None or h_port < 0:
        return None
    import ctypes
    names = [MEDIA_COUNTER_FUNC.get(dll_name, _DEFAULT_MEDIA_COUNTER_FUNC)]
    # Repli sur la fonction generique si le modele expose un nom different de
    # celui attendu : mieux vaut un compteur approximatif que pas de compteur.
    if _DEFAULT_MEDIA_COUNTER_FUNC not in names:
        names.append(_DEFAULT_MEDIA_COUNTER_FUNC)
    attendue = names[0]
    for fn_name in names:
        fn = getattr(dll, fn_name, None)
        if fn is None:
            continue
        try:
            fn.argtypes = [ctypes.c_int]
            fn.restype = ctypes.c_int
            val = fn(h_port)
        except Exception:
            continue
        if fn_name != attendue:
            # Le repli vaut mieux que pas de compteur du tout, mais sur une
            # RX1 il publie 480 au lieu de 430 : l'alerte papier bas (seuil
            # 50) partirait 50 tirages trop tard. Ca ne doit pas se produire
            # en silence.
            _log_echec(
                f"{dll_name}:{attendue}",
                f"{attendue} indisponible sur {dll_name}, repli sur {fn_name} "
                f"-> compteur potentiellement errone ({val})",
            )
        return val
    return None


def find_dll_path(dll_name):
    """Cherche une DLL DNP dans les emplacements connus. Retourne le chemin
    ou None. Gere le mode PyInstaller (sys._MEIPASS)."""
    monitoring_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(monitoring_dir, "coupe_2pouces", dll_name),
        os.path.join(monitoring_dir, dll_name),
    ]
    # PyInstaller one-file : les datas sont extraites dans le dossier temporaire
    if hasattr(sys, "_MEIPASS"):
        candidates.insert(
            0, os.path.join(sys._MEIPASS, "monitoring", "coupe_2pouces", dll_name)
        )
        candidates.insert(1, os.path.join(sys._MEIPASS, dll_name))
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def load_dll(dll_name):
    """Charge (et met en cache) une DLL DNP. Retourne l'objet WinDLL ou None.

    Ne leve jamais : une DLL manquante ou illisible doit degrader vers
    'pas de statut', jamais casser le tick du monitoring."""
    with _lock:
        if dll_name in _cache:
            return _cache[dll_name]
    path = find_dll_path(dll_name)
    dll = None
    if not path:
        _log_echec(dll_name, f"{dll_name} introuvable sur le disque")
    else:
        try:
            import ctypes
            dll = ctypes.WinDLL(path)
        except Exception as e:
            # Cas connu : CyStat64 a besoin de CSJCYLM.DLL, depose par le
            # pilote DP-DS-RX1. Sur une machine sans ce pilote, le chargement
            # echoue avec WinError 1114 (echec du DllMain). C'est attendu et
            # sans gravite : l'imprimante n'est de toute facon pas la.
            _log_echec(dll_name, f"chargement {dll_name} echoue: {e}")
            dll = None
    # On ne met en cache QUE les succes. Mettre un echec en cache le figerait
    # pour toute la vie du process : un probleme transitoire (DLL pas encore
    # extraite du _MEI, fichier verrouille par l'antivirus au boot) condamnerait
    # l'agent a remonter "DLL introuvable" pour toujours. Or alertes_monitor
    # range cette valeur avec "Imprimante deconnectee" -> alerte critique + SMS
    # jamais resolue. Avant la factorisation, chaque appel rechargeait la DLL
    # et un echec transitoire se reparait tout seul : on garde ce comportement.
    if dll is not None:
        with _lock:
            _cache[dll_name] = dll
    return dll


def call_optional(dll, func_name, *args):
    """Appelle une fonction de la DLL si elle existe. Retourne (True, resultat)
    ou (False, None) si la fonction est absente ou a leve.

    Necessaire parce que les deux DLL n'exposent pas le meme jeu de fonctions
    (19 fonctions de Cx2Stat64 manquent dans CyStat64, surtout cote coupe)."""
    if dll is None:
        return False, None
    fn = getattr(dll, func_name, None)
    if fn is None:
        return False, None
    try:
        return True, fn(*args)
    except Exception:
        return False, None
