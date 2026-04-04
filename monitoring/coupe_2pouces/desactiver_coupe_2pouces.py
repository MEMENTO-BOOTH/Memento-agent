"""
=============================================================
  Desactivation de la coupe 2 pouces (remet en CUT_STANDARD)
  pour imprimante DNP DS620 + dslrBooth
=============================================================

Modifie :
  1. HKLM (Default DevMode systeme)
  2. HKU\\<SID> (DevMode per-user de chaque utilisateur bureau)
  3. printer_settings.xml de dslrBooth (tous les profils)

Doit etre lance en tant qu'administrateur.
Fermer dslrBooth avant de lancer ce script.
"""

import os
import sys
import time
import ctypes
import winreg
import subprocess
import base64
import re
import platform

PRINTER_PATTERNS = ["DP-DS620", "DNP-DS620", "DNP DS620", "DS620"]
CUTTERCONTROL_DEVMODE_OFFSET = 282
CMODE_STANDARD = 0

def _is_ds620(name):
    n = name.upper()
    return any(p.upper() in n for p in PRINTER_PATTERNS)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAINTENANCE_FLAG = os.path.join(SCRIPT_DIR, "maintenance.flag")


def require_admin():
    try:
        if not ctypes.windll.shell32.IsUserAnAdmin():
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable,
                f'"{os.path.abspath(__file__)}"', None, 1
            )
            sys.exit(0)
    except Exception as e:
        print(f"Impossible d'obtenir les droits admin: {e}")
        sys.exit(1)


def find_ds620_printer():
    reg = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Print\Printers"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg) as printers_key:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(printers_key, i)
                except OSError:
                    break
                i += 1
                if not _is_ds620(name):
                    continue
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{reg}\\{name}") as pk:
                    port, _ = winreg.QueryValueEx(pk, "Port")
                return name, port
    except Exception as e:
        print(f"Erreur detection: {e}")
    return None, None


def get_desktop_user_sids():
    """Trouve les SID des utilisateurs qui ont un profil interactif."""
    sids = []
    profiles_reg = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, profiles_reg) as pk:
            i = 0
            while True:
                try:
                    sid = winreg.EnumKey(pk, i)
                except OSError:
                    break
                i += 1
                if len(sid) < 20:
                    continue
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{profiles_reg}\\{sid}") as sk:
                        profile_path, _ = winreg.QueryValueEx(sk, "ProfileImagePath")
                        sids.append((sid, profile_path))
                except Exception:
                    pass
    except Exception as e:
        print(f"  Erreur enumeration profils: {e}")
    return sids


def build_smtj_data_standard():
    """Construit les donnees SMTJ avec CUT_STANDARD.
    Le nom d'imprimante est en UTF-16LE, le reste en ASCII."""
    data = bytearray()
    data += "DP-DS620\x00".encode("utf-16-le")  # Nom de base dans le SMTJ
    pairs = [
        ("InputBin", "FORMSOURCE"),
        ("RESDLL", "UniresDLL"),
        ("Orientation", "PORTRAIT"),
        ("Resolution", "Option1"),
        ("PrintMargin", "MarginOff"),
        ("OVERCOATTYPE", "OPTYPE_LUSTER"),
        ("PRINTBUFFCONTROL", "PBC_NONCLEAR"),
        ("CUTTERCONTROL", "CUT_STANDARD"),
        ("PaperSize", "PC"),
        ("MediaType", "STANDARD"),
        ("ColorMode", "24bpp"),
        ("Halftone", "HT_PATSIZE_SUPERCELL_M"),
    ]
    for key, val in pairs:
        data += key.encode("ascii") + b"\x00"
        data += val.encode("ascii") + b"\x00"
    return data


def fix_smtj_section_standard(dm):
    """Remplace la section SMTJ du DEVMODE avec CUT_STANDARD.
    Retourne (bytearray modifie, True si modifie)."""
    idx_smtj = dm.find(b"SMTJ")
    if idx_smtj < 0:
        return dm, False

    header_size = 12
    text_start = idx_smtj + header_size

    idx_tfsm = dm.find(b"TFSM", text_start)
    if idx_tfsm < 0:
        return dm, False

    current_smtj = dm[text_start:idx_tfsm]
    if b"CUT_STANDARD" in current_smtj and b"CUT_2INCH" not in current_smtj:
        return dm, False

    available = idx_tfsm - text_start
    new_data = bytearray(build_smtj_data_standard())
    if len(new_data) <= available:
        new_data += b"\x00" * (available - len(new_data))
    else:
        new_data = new_data[:available]

    dm[text_start:idx_tfsm] = new_data
    return dm, True


def modify_registry_devmode(printer_name):
    print("\n[1/3] Desactivation dans le registre Windows...")
    reg_path = rf"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Print\Printers\{printer_name}"

    subprocess.run(["net", "stop", "spooler"], capture_output=True, text=True)
    time.sleep(1)

    # --- A) HKLM (Default DevMode systeme) ---
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path,
                            0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            dm, typ = winreg.QueryValueEx(k, "Default DevMode")
            dm = bytearray(dm)
            modified = False

            if dm[CUTTERCONTROL_DEVMODE_OFFSET] != 0:
                dm[CUTTERCONTROL_DEVMODE_OFFSET] = 0
                print("  HKLM: Byte 282 -> 0 (CUT_STANDARD)")
                modified = True

            dm, smtj_changed = fix_smtj_section_standard(dm)
            if smtj_changed:
                print("  HKLM: Section SMTJ -> CUTTERCONTROL=CUT_STANDARD")
                modified = True

            if modified:
                winreg.SetValueEx(k, "Default DevMode", 0, typ, bytes(dm))
                print("  HKLM: DEVMODE sauvegarde.")
            else:
                print("  HKLM: Deja en CUT_STANDARD.")
    except Exception as e:
        print(f"  ERREUR HKLM: {e}")

    # --- B) HKU\<SID> (DevMode per-user de chaque utilisateur) ---
    user_sids = get_desktop_user_sids()
    for sid, profile_path in user_sids:
        hku_path = rf"{sid}\Printers\DevModePerUser"
        try:
            with winreg.OpenKey(winreg.HKEY_USERS, hku_path,
                                0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
                dm_user, typ_user = winreg.QueryValueEx(k, printer_name)
                dm_user = bytearray(dm_user)
                user_name = os.path.basename(profile_path)
                modified = False

                if dm_user[CUTTERCONTROL_DEVMODE_OFFSET] != 0:
                    dm_user[CUTTERCONTROL_DEVMODE_OFFSET] = 0
                    print(f"  HKU ({user_name}): Byte 282 -> 0")
                    modified = True

                dm_user, smtj_changed = fix_smtj_section_standard(dm_user)
                if smtj_changed:
                    print(f"  HKU ({user_name}): Section SMTJ -> CUT_STANDARD")
                    modified = True

                if modified:
                    winreg.SetValueEx(k, printer_name, 0, typ_user, bytes(dm_user))
                    print(f"  HKU ({user_name}): DEVMODE sauvegarde.")
                else:
                    print(f"  HKU ({user_name}): Deja en CUT_STANDARD.")
        except FileNotFoundError:
            pass
        except Exception as e:
            user_name = os.path.basename(profile_path)
            print(f"  HKU ({user_name}): {e}")

    subprocess.run(["net", "start", "spooler"], capture_output=True, text=True)
    time.sleep(1)


def find_dslrbooth_settings():
    """Cherche le fichier printer_settings.xml de dslrBooth
    dans le profil de tous les utilisateurs."""
    candidates = []

    users_dir = r"C:\Users"
    if os.path.isdir(users_dir):
        for user_folder in os.listdir(users_dir):
            settings_path = os.path.join(
                users_dir, user_folder, "AppData", "Roaming", "dslrBooth", "printer_settings.xml"
            )
            if os.path.exists(settings_path):
                candidates.append(settings_path)

    direct = os.path.join(os.environ.get("APPDATA", ""), "dslrBooth", "printer_settings.xml")
    if os.path.exists(direct) and direct not in candidates:
        candidates.append(direct)

    return candidates


def deactivate_hardware(printer_port):
    print(f"\n[3/3] Desactivation hardware via DLL...")

    arch = platform.architecture()[0]
    dll_name = "Cx2Stat64.dll" if arch == "64bit" else "Cx2Stat.dll"
    dll_path = os.path.join(SCRIPT_DIR, dll_name)

    if not os.path.exists(dll_path):
        print(f"  DLL introuvable: {dll_path}")
        print("  Etape ignoree.")
        return

    try:
        printer_api = ctypes.WinDLL(dll_path)

        f_init = printer_api.PortInitialize
        f_init.argtypes = [ctypes.c_wchar_p]
        f_init.restype = ctypes.c_int
        handle = f_init(printer_port)

        if handle < 0:
            print(f"  Impossible d'ouvrir le port {printer_port} (imprimante eteinte?)")
            print("  Etape ignoree.")
            return

        f_cut = printer_api.SetCutterMode
        f_cut.argtypes = [ctypes.c_int, ctypes.c_int]
        f_cut.restype = ctypes.c_int
        result = f_cut(handle, CMODE_STANDARD)

        if result >= 0:
            print(f"  Hardware: SetCutterMode({CMODE_STANDARD}) -> {result} (succes)")
        else:
            print(f"  Hardware: SetCutterMode({CMODE_STANDARD}) -> {result} (echec)")
    except Exception as e:
        print(f"  ERREUR DLL: {e}")
        print("  Etape ignoree.")


def modify_dslrbooth(file_path):
    print(f"\n[2/3] Desactivation dans dslrBooth...")
    print(f"  Fichier: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        print(f"  ERREUR lecture: {e}")
        return

    if "CUT_STANDARD" in content and "CUT_2INCH" not in content:
        print("  Deja en CUT_STANDARD.")
        return

    # XML
    content = content.replace("ns0000:CUT_2INCH", "ns0000:CUT_STANDARD")
    print("  XML: CUT_2INCH -> CUT_STANDARD")

    # DEVMODE blob
    flat = content.replace("\n", "").replace("\r", "")
    m = re.search(r'PageDevmodeSnapshot.*?xsd:string[^>]*>([A-Za-z0-9+/=]+)<', flat)
    if m:
        old_b64 = m.group(1)
        dm = bytearray(base64.b64decode(old_b64))

        dm[CUTTERCONTROL_DEVMODE_OFFSET] = 0

        old_str = b"CUT_2INCH\x00"
        new_str = b"CUT_STANDARD\x00"
        idx = dm.find(old_str)
        if idx >= 0:
            # Expand: shift data right
            dm = dm[:idx] + new_str + dm[idx + len(old_str):]
            # Trim or pad to original size
            original_len = len(base64.b64decode(old_b64))
            if len(dm) > original_len:
                dm = dm[:original_len]
            elif len(dm) < original_len:
                dm += b'\x00' * (original_len - len(dm))
            print("  SMTJ: CUT_2INCH -> CUT_STANDARD")

        new_b64 = base64.b64encode(bytes(dm)).decode("ascii")
        content = content.replace(old_b64, new_b64)
        print("  DEVMODE byte 282 -> 0")

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("  Fichier sauvegarde.")


if __name__ == "__main__":
    require_admin()

    print("=" * 50)
    print("  DESACTIVATION coupe 2 pouces - DNP DS620")
    print("=" * 50)

    printer_name, printer_port = find_ds620_printer()
    if not printer_name:
        print("\nERREUR: Aucune imprimante DS620 trouvee!")
        input("\nAppuie sur Entree pour fermer...")
        sys.exit(1)

    print(f"\nImprimante: {printer_name}")

    # Creer le drapeau de maintenance pour empecher le monitor
    # d'afficher l'alerte pendant l'arret du spooler
    try:
        with open(MAINTENANCE_FLAG, "w") as f:
            f.write("maintenance")
        print("\n[FLAG] Drapeau de maintenance cree.")
    except Exception:
        pass

    try:
        modify_registry_devmode(printer_name)

        dslr_files = find_dslrbooth_settings()
        if dslr_files:
            for dslr_path in dslr_files:
                modify_dslrbooth(dslr_path)
        else:
            print("\n[2/3] dslrBooth non detecte. Etape ignoree.")

        # Etape 3: Remettre le hardware en mode standard via la DLL
        deactivate_hardware(printer_port)

        # Supprimer le fichier flag pour que le script de startup
        # ne reactive pas le hardware au prochain redemarrage
        flag_path = os.path.join(SCRIPT_DIR, "coupe_2pouces_active.flag")
        try:
            os.remove(flag_path)
            print("  Flag de startup supprime.")
        except FileNotFoundError:
            pass

        print("\n" + "=" * 50)
        print("  Coupe 2 pouces DESACTIVEE.")
        print("=" * 50)
    finally:
        # Supprimer le drapeau de maintenance dans tous les cas
        try:
            os.remove(MAINTENANCE_FLAG)
            print("[FLAG] Drapeau de maintenance supprime.")
        except Exception:
            pass

    input("\nAppuie sur Entree pour fermer...")
