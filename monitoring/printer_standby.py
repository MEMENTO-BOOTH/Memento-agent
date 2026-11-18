"""Desactivation de la veille interne de la DNP DS620.

Probleme
--------
La DS620 a sa propre logique de veille (firmware) independante de Windows :
apres N minutes d'inactivite elle eteint la tete thermique. Si Windows
fait planter le reveil au prochain job d'impression (cas observe sur les
bornes en charge), les photos restent bloquees dans la file Windows.

Solution
--------
La DLL Cx2Stat64.dll (SDK officiel DNP v1.31) expose `SetStandbyTime` :
on peut regler le temps de mise en veille de l'imprimante en minutes.
Valeur 0 = veille desactivee (l'imprimante reste toujours en idle, prete).

Pourquoi ce module
------------------
- Pas d'UAC : la DLL parle directement a l'USB de l'imprimante, pas au
  registre Windows -> scalable a 1500 bornes sans clic manuel.
- Source de verite = etat reel de l'imprimante (`GetStandbyTime`). Persiste
  meme apres reinstall/desinstall de l'agent. Aucun flag local necessaire.
- Reappliquable a chaque demarrage de l'agent : idempotent, zero cout.

API publique
------------
  - desactiver_veille_imprimante() : applique SetStandbyTime(0)
  - reactiver_veille_imprimante()  : restaure le defaut (10 minutes)
  - lire_standby_time()            : lit la valeur courante (minutes, ou None
                                     si imprimante injoignable)
  - est_veille_desactivee()        : True si standby = 0 cote imprimante
"""

import os
import sys
import ctypes
import platform
import logging

# Valeur par defaut DNP : 10 minutes
DEFAULT_STANDBY_MIN = 10

# Patterns pour matcher la DS620 dans le registre Windows
# IMPORTANT: ce script appelle PortInitialize/SetStandbyTime sur chaque imprimante
# matchee -> on DOIT rester strictement DS620 (seul modele garanti par Cx2Stat64).
# Un appel sur DS-RX1 peut segfault le process (observe v1.0.28.9 sur MB-50).
PRINTER_PATTERNS = ["DP-DS620", "DNP-DS620", "DNP DS620", "DS620"]


def _find_dll():
    """Localise Cx2Stat64.dll (meme convention que printer_counter)."""
    monitoring_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(monitoring_dir, "coupe_2pouces", "Cx2Stat64.dll"),
        os.path.join(monitoring_dir, "Cx2Stat64.dll"),
    ]
    if hasattr(sys, "_MEIPASS"):
        candidates.insert(
            0,
            os.path.join(sys._MEIPASS, "monitoring", "coupe_2pouces", "Cx2Stat64.dll"),
        )
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def _is_ds620(name):
    n = name.upper()
    return any(p.upper() in n for p in PRINTER_PATTERNS)


def _open_ds620():
    """Initialise la DLL, trouve la DS620 sur un port USB, ouvre le handle.

    Retourne (dll, handle) si succes, sinon (None, None).
    L'appelant est responsable de fermer le handle (pas de PortRelease
    dans cette version de la DLL : on libere via gc + reload si besoin)."""
    if platform.system() != "Windows":
        return None, None
    dll_path = _find_dll()
    if not dll_path:
        logging.warning("printer_standby: Cx2Stat64.dll introuvable")
        return None, None
    try:
        import winreg
        dll = ctypes.WinDLL(dll_path)
        dll.PortInitialize.argtypes = [ctypes.c_wchar_p]
        dll.PortInitialize.restype = ctypes.c_int
        dll.GetStatus.argtypes = [ctypes.c_int]
        dll.GetStatus.restype = ctypes.c_uint
        dll.GetStandbyTime.argtypes = [ctypes.c_int]
        dll.GetStandbyTime.restype = ctypes.c_int
        dll.SetStandbyTime.argtypes = [ctypes.c_int, ctypes.c_int]
        dll.SetStandbyTime.restype = ctypes.c_int

        # Trouver tous les ports DS620 dans le registre
        reg_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Print\Printers"
        candidats = []
        # Ports occupes par une DNP qui n'est PAS une DS620. Le balayage
        # aveugle plus bas ne doit JAMAIS les toucher : y appeler Cx2Stat64
        # revient a parler a une imprimante avec la bibliotheque d'une autre
        # famille, ce qui a tue le process agent en v1.0.28.9 (MB-50).
        ports_interdits = set()
        from .alertes.constants import is_dnp_printer, get_printer_dll
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
            for i in range(100):
                # EnumKey leve OSError quand i depasse le nombre de clefs =
                # fin legitime de l'enumeration -> break. Mais un OSError sur
                # OpenKey/QueryValueEx d'une imprimante au registre atypique
                # ("Microsoft Print to PDF") doit juste faire sauter CETTE
                # entree : sinon la vraie DNP enumeree APRES n'est jamais vue
                # (meme bug que le fix Les Follies du 06/11).
                try:
                    name = winreg.EnumKey(key, i)
                except OSError:
                    break
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE, f"{reg_path}\\{name}"
                    ) as pk:
                        port, _ = winreg.QueryValueEx(pk, "Port")
                        try:
                            driver, _ = winreg.QueryValueEx(pk, "Printer Driver")
                        except OSError:
                            driver = ""
                except OSError:
                    continue
                # Le driver du registre prime sur le nom affiche, librement
                # editable par l'exploitant (MB-50 : imprimante nommee
                # "DS-RX1" tout court).
                if _is_ds620(name) or _is_ds620(driver):
                    candidats.append(port)
                elif is_dnp_printer(name) or is_dnp_printer(driver):
                    if get_printer_dll(name, driver) != "Cx2Stat64.dll":
                        ports_interdits.add(port)

        # Tester chaque port : prendre celui qui repond
        seen = set()
        for port in candidats:
            if port in seen:
                continue
            seen.add(port)
            h = dll.PortInitialize(port)
            if h >= 0:
                status = dll.GetStatus(h)
                if status != 0x80000000:
                    return dll, h
        # Fallback : USB001..USB004 directement, pour les DS620 dont l'entree
        # registre ne matche aucun motif connu (imprimante renommee).
        #
        # v1.0.28.30 : on saute les ports revendiques par une DNP qui n'est
        # PAS une DS620. Sans ce filtre, sur MB-50 (seule entree registre :
        # "DS-RX1" sur USB003), candidats restait vide et ce balayage appelait
        # Cx2Stat64.PortInitialize sur une DS-RX1 a CHAQUE demarrage de
        # l'agent — puis GetStandbyTime/SetStandbyTime, deux fonctions que
        # CyStat64 n'expose meme pas. C'est le seul chemin du genre qui
        # s'execute a coup sur au boot, et il n'etait couvert par aucun garde.
        for port in ("USB001", "USB002", "USB003", "USB004"):
            if port in seen or port in ports_interdits:
                continue
            h = dll.PortInitialize(port)
            if h >= 0:
                status = dll.GetStatus(h)
                if status != 0x80000000:
                    return dll, h
        return None, None
    except Exception as e:
        logging.error(f"printer_standby: erreur ouverture DLL: {e}")
        return None, None


def lire_standby_time():
    """Retourne la valeur actuelle du standby time (minutes) ou None si
    l'imprimante n'est pas joignable. Source de verite absolue : la valeur
    stockee dans le firmware de l'imprimante elle-meme."""
    dll, h = _open_ds620()
    if dll is None or h is None:
        return None
    try:
        return dll.GetStandbyTime(h)
    except Exception as e:
        logging.error(f"printer_standby: erreur GetStandbyTime: {e}")
        return None


def est_veille_desactivee():
    """True si la veille de la DS620 est desactivee (SetStandbyTime=0).
    False si veille active ou si l'imprimante est injoignable."""
    val = lire_standby_time()
    return val == 0


def desactiver_veille_imprimante():
    """Desactive la veille de la DS620 (SetStandbyTime=0).
    Retourne True si applique avec succes, False sinon.
    Pas d'UAC : appel DLL direct via USB."""
    dll, h = _open_ds620()
    if dll is None or h is None:
        logging.warning("printer_standby: imprimante injoignable")
        return False
    try:
        ret = dll.SetStandbyTime(h, 0)
        if ret > 0:
            logging.info("printer_standby: veille desactivee (SetStandbyTime=0)")
            return True
        logging.warning(f"printer_standby: SetStandbyTime(0) a retourne {ret}")
        return False
    except Exception as e:
        logging.error(f"printer_standby: erreur SetStandbyTime: {e}")
        return False


def reactiver_veille_imprimante(minutes=DEFAULT_STANDBY_MIN):
    """Restaure la veille au defaut DNP (10 minutes).
    Retourne True si applique avec succes."""
    if minutes <= 0:
        minutes = DEFAULT_STANDBY_MIN
    dll, h = _open_ds620()
    if dll is None or h is None:
        return False
    try:
        ret = dll.SetStandbyTime(h, int(minutes))
        if ret > 0:
            logging.info(f"printer_standby: veille reactivee ({minutes} min)")
            return True
        return False
    except Exception as e:
        logging.error(f"printer_standby: erreur SetStandbyTime: {e}")
        return False


def desactiver_au_demarrage():
    """Appele au demarrage de l'agent : applique SetStandbyTime(0) de maniere
    inconditionnelle. Idempotent (si deja a 0, ne change rien). Zero cout.

    Pourquoi inconditionnel : la veille DS620 ne doit JAMAIS etre active sur
    les bornes Memento. Si l'imprimante a perdu son reglage (firmware update,
    debranche/rebranche), on le restaure transparently au prochain demarrage
    de l'agent."""
    try:
        current = lire_standby_time()
        if current is None:
            logging.info("printer_standby: imprimante injoignable au demarrage, skip")
            return
        if current == 0:
            logging.info("printer_standby: deja desactivee (rien a faire)")
            return
        logging.info(f"printer_standby: veille etait {current}min, application 0")
        desactiver_veille_imprimante()
    except Exception as e:
        logging.error(f"printer_standby: erreur desactiver_au_demarrage: {e}")


# Test standalone : `python -m monitoring.printer_standby`
if __name__ == "__main__":
    print(f"=== Test printer_standby ===")
    val = lire_standby_time()
    print(f"GetStandbyTime actuel : {val} (None = injoignable)")
    if val is not None:
        print(f"Veille desactivee ? {est_veille_desactivee()}")
