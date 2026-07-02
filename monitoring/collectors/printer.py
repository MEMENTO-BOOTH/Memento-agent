"""Lecture imprimante DNP DS620 via DLL Cx2Stat64.
Extrait de remontee_finale_1.0.0.pyw — fonctionne uniquement sur Windows."""

import os
import platform
from ..alertes.constants import BASE_PRINTER_NAME, STATUS_MAP, is_ds620
from ..dnp_lock import DNP_PORT_LOCK


def lire_imprimante():
    """Lit le statut, feuilles restantes, serial et mode coupe de l'imprimante."""
    result = {
        "nom_imprimante": None,
        "serial_imprimante": None,
        "imprimante_statut": None,
        "imprimante_statut_code": None,
        "feuilles_restantes": None,
        "mode_coupe": None,
    }

    if platform.system() != "Windows":
        result["imprimante_statut"] = "Non disponible (pas Windows)"
        return result

    # Chercher la DLL (dans coupe_2pouces/ ou à la racine monitoring/)
    import sys
    dll_path = None
    monitoring_dir = os.path.dirname(os.path.dirname(__file__))
    candidates = [
        os.path.join(monitoring_dir, "coupe_2pouces", "Cx2Stat64.dll"),
        os.path.join(monitoring_dir, "Cx2Stat64.dll"),
        os.path.join(os.path.dirname(__file__), "Cx2Stat64.dll"),
    ]
    # PyInstaller one-file : DLL dans le dossier temp d'extraction
    if hasattr(sys, '_MEIPASS'):
        candidates.insert(0, os.path.join(sys._MEIPASS, "monitoring", "coupe_2pouces", "Cx2Stat64.dll"))
    for candidate in candidates:
        if os.path.exists(candidate):
            dll_path = candidate
            break

    if not dll_path:
        result["imprimante_statut"] = "DLL introuvable"
        return result

    try:
        import ctypes
        import winreg

        dll = ctypes.WinDLL(dll_path)
        dll.PortInitialize.argtypes = [ctypes.c_wchar_p]
        dll.PortInitialize.restype = ctypes.c_int

        # Trouver l'imprimante dans le registre
        reg = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Print\Printers"
        printer_name = None
        printer_port = None

        # Trouver TOUTES les imprimantes DS620, tester chaque port
        all_printers = []
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg) as key:
            for i in range(100):
                try:
                    name = winreg.EnumKey(key, i)
                    if is_ds620(name):
                        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{reg}\\{name}") as pk:
                            port, _ = winreg.QueryValueEx(pk, "Port")
                            all_printers.append((name, port))
                except OSError:
                    break

        if not all_printers:
            result["imprimante_statut"] = "Imprimante non trouvée"
            return result

        # Tout ce qui touche a la DLL DNP passe par DNP_PORT_LOCK pour ne pas
        # entrer en conflit avec le PrinterCounterWatcher (qui poll toutes
        # les 3s). Sans ce lock : le collecteur echoue PortInitialize quand
        # le port est deja pris -> fausse alerte 'Imprimante deconnectee'.
        with DNP_PORT_LOCK:
            # Tester chaque port — prendre celle qui répond (pas 0x80000000)
            h_port = -1
            for name, port in all_printers:
                h = dll.PortInitialize(port)
                if h >= 0:
                    dll.GetStatus.argtypes = [ctypes.c_int]
                    dll.GetStatus.restype = ctypes.c_uint
                    st = dll.GetStatus(h)
                    if st != 0x80000000:
                        # Cette imprimante répond
                        printer_name = name
                        printer_port = port
                        h_port = h
                        break
                    # Sinon essayer la suivante

            # Si aucune n'a répondu, prendre la première quand même
            if h_port < 0:
                printer_name, printer_port = all_printers[0]
                h_port = dll.PortInitialize(printer_port)

            result["nom_imprimante"] = printer_name

            if h_port < 0:
                result["imprimante_statut"] = "Imprimante déconnectée"
                return result

            # Statut
            dll.GetStatus.argtypes = [ctypes.c_int]
            dll.GetStatus.restype = ctypes.c_uint
            status = dll.GetStatus(h_port)
            result["imprimante_statut_code"] = status
            result["imprimante_statut"] = STATUS_MAP.get(status, f"Inconnu (0x{status:X})")

            # Feuilles restantes
            dll.GetMediaCounter.argtypes = [ctypes.c_int]
            dll.GetMediaCounter.restype = ctypes.c_int
            feuilles = dll.GetMediaCounter(h_port)
            result["feuilles_restantes"] = feuilles if feuilles >= 0 else None

            # Serial
            try:
                buf = ctypes.create_string_buffer(256)
                dll.GetSerialNo.argtypes = [ctypes.c_int, ctypes.c_char_p]
                dll.GetSerialNo.restype = ctypes.c_int
                if dll.GetSerialNo(h_port, buf) >= 0:
                    serial = buf.value.decode("ascii", errors="ignore").strip()
                    if serial:
                        result["serial_imprimante"] = serial
            except Exception:
                pass

            # Libérer
            try:
                dll.PortRelease(h_port)
            except Exception:
                pass

        # Mode coupe — lire le flag fichier (pas le registre HKLM qui ne reflète pas la clé utilisateur)
        # (hors lock : ne touche pas a la DLL DNP)
        from monitoring.coupe_2pouces.coupe import est_coupe_active
        result["mode_coupe"] = "Coupe activée" if est_coupe_active() else "Coupe désactivée"

    except Exception as e:
        result["imprimante_statut"] = f"Erreur: {e}"

    return result
