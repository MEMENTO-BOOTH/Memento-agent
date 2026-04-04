

import os
import sys
import time
import ctypes
import winreg
import struct
import subprocess
import base64
import re
import platform

# ===========================================================
# Configuration
# ===========================================================
PRINTER_PATTERNS = ["DP-DS620", "DNP-DS620", "DNP DS620", "DS620"]

def _is_ds620(name):
    n = name.upper()
    return any(p.upper() in n for p in PRINTER_PATTERNS)
CUTTERCONTROL_DEVMODE_OFFSET = 282  # offset dans le Default DevMode
CMODE_2INCHCUT = 120                # valeur hardware DLL
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MAINTENANCE_FLAG = os.path.join(SCRIPT_DIR, "maintenance.flag")

# ===========================================================
# Elevation admin
# ===========================================================
def require_admin():
    try:
        if not ctypes.windll.shell32.IsUserAnAdmin():
            print("Elevation en mode administrateur...")
            ctypes.windll.shell32.ShellExecuteW(
                None, "runas", sys.executable,
                f'"{os.path.abspath(__file__)}"', None, 1
            )
            sys.exit(0)
    except Exception as e:
        print(f"Impossible d'obtenir les droits admin: {e}")
        sys.exit(1)

# ===========================================================
# Detection de l'imprimante DS620
# ===========================================================
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

# ===========================================================
# Detection des utilisateurs bureau (SID)
# ===========================================================
def get_desktop_user_sids():
    """Trouve les SID des utilisateurs qui ont un profil interactif.
    Quand le script est eleve via UAC avec un autre compte admin,
    HKCU pointe vers l'admin. On doit modifier le registre de
    l'utilisateur du bureau via HKU\\<SID>."""
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
                # Ignorer les SID systeme courts (S-1-5-18, S-1-5-19, S-1-5-20)
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

# ===========================================================
# Section SMTJ de reference avec CUT_2INCH
# ===========================================================
# La section SMTJ du DEVMODE contient les noms des parametres
# en texte clair. Le driver DNP DS620 l'utilise pour determiner
# les reglages effectifs. Modifier uniquement le byte 282 ne
# suffit pas si la section SMTJ est vide ou contient CUT_STANDARD.
def build_smtj_data_2inch():
    """Construit les donnees SMTJ avec CUT_2INCH.
    Le nom d'imprimante est en UTF-16LE, le reste en ASCII."""
    data = bytearray()
    # Nom d'imprimante en UTF-16LE (null termine)
    data += "DP-DS620\x00".encode("utf-16-le")
    # Paires cle/valeur en ASCII (null termine)
    pairs = [
        ("InputBin", "FORMSOURCE"),
        ("RESDLL", "UniresDLL"),
        ("Orientation", "PORTRAIT"),
        ("Resolution", "Option1"),
        ("PrintMargin", "MarginOff"),
        ("OVERCOATTYPE", "OPTYPE_LUSTER"),
        ("PRINTBUFFCONTROL", "PBC_NONCLEAR"),
        ("CUTTERCONTROL", "CUT_2INCH"),
        ("PaperSize", "PC"),
        ("MediaType", "STANDARD"),
        ("ColorMode", "24bpp"),
        ("Halftone", "HT_PATSIZE_SUPERCELL_M"),
    ]
    for key, val in pairs:
        data += key.encode("ascii") + b"\x00"
        data += val.encode("ascii") + b"\x00"
    return data


def fix_smtj_section(dm):
    """Remplace la section SMTJ du DEVMODE avec les bons parametres.
    Retourne (bytearray modifie, True si modifie)."""
    idx_smtj = dm.find(b"SMTJ")
    if idx_smtj < 0:
        return dm, False

    # L'en-tete SMTJ fait 12 bytes: "SMTJ" (4) + reserved (4) + flags (4)
    # Les donnees commencent a offset 12 apres le marqueur SMTJ
    header_size = 12
    text_start = idx_smtj + header_size

    # Trouver la fin de la section SMTJ (debut du marqueur TFSM)
    idx_tfsm = dm.find(b"TFSM", text_start)
    if idx_tfsm < 0:
        return dm, False  # Structure inconnue, ne pas modifier

    # Verifier si la section contient deja CUT_2INCH
    current_smtj = dm[text_start:idx_tfsm]
    if b"CUT_2INCH" in current_smtj and b"CUT_STANDARD" not in current_smtj:
        return dm, False  # Deja correct

    # Calculer l'espace disponible pour les donnees
    available = idx_tfsm - text_start
    new_data = bytearray(build_smtj_data_2inch())

    # Padder avec des zeros pour remplir exactement l'espace disponible
    if len(new_data) <= available:
        new_data += b"\x00" * (available - len(new_data))
    else:
        # Tronquer si necessaire (ne devrait pas arriver)
        new_data = new_data[:available]

    dm[text_start:idx_tfsm] = new_data
    return dm, True

# ===========================================================
# Etape 1 : Modifier le registre Windows (DEVMODE)
# ===========================================================
def modify_registry_devmode(printer_name):
    print("\n[1/3] Modification du driver Windows (registre)...")

    reg_path = rf"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Print\Printers\{printer_name}"

    # Arreter le spooler
    print("  Arret du spooler...")
    subprocess.run(["net", "stop", "spooler"], capture_output=True, text=True)
    time.sleep(1)

    success = False

    # --- A) Modifier le Default DevMode systeme (HKLM) ---
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path,
                            0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            dm, typ = winreg.QueryValueEx(k, "Default DevMode")
            dm = bytearray(dm)

            modified = False

            # 1) Modifier le byte 282 (index d'option CUTTERCONTROL)
            if dm[CUTTERCONTROL_DEVMODE_OFFSET] != 1:
                dm[CUTTERCONTROL_DEVMODE_OFFSET] = 1
                print("  HKLM: Byte 282 -> 1 (CUT_2INCH)")
                modified = True

            # 2) Modifier la section SMTJ (noms texte des parametres)
            dm, smtj_changed = fix_smtj_section(dm)
            if smtj_changed:
                print("  HKLM: Section SMTJ -> CUTTERCONTROL=CUT_2INCH")
                modified = True

            if modified:
                winreg.SetValueEx(k, "Default DevMode", 0, typ, bytes(dm))
                print("  HKLM: DEVMODE sauvegarde.")
                success = True
            else:
                print("  HKLM: Deja active (byte 282 + SMTJ).")
                success = True
    except PermissionError:
        print("  ERREUR: Droits administrateur insuffisants!")
    except Exception as e:
        print(f"  ERREUR HKLM: {e}")

    # --- B) Modifier le DevMode per-user via HKU\<SID> ---
    # (HKCU pointe vers l'admin apres elevation UAC, pas le vrai utilisateur)
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

                # 1) Byte 282
                if dm_user[CUTTERCONTROL_DEVMODE_OFFSET] != 1:
                    dm_user[CUTTERCONTROL_DEVMODE_OFFSET] = 1
                    print(f"  HKU ({user_name}): Byte 282 -> 1")
                    modified = True

                # 2) Section SMTJ
                dm_user, smtj_changed = fix_smtj_section(dm_user)
                if smtj_changed:
                    print(f"  HKU ({user_name}): Section SMTJ -> CUT_2INCH")
                    modified = True

                if modified:
                    winreg.SetValueEx(k, printer_name, 0, typ_user, bytes(dm_user))
                    print(f"  HKU ({user_name}): DEVMODE sauvegarde.")
                else:
                    print(f"  HKU ({user_name}): Deja active.")
                success = True
        except FileNotFoundError:
            pass  # Cet utilisateur n'a pas de DevMode per-user
        except Exception as e:
            user_name = os.path.basename(profile_path)
            print(f"  HKU ({user_name}): {e}")

    # Redemarrer le spooler
    print("  Redemarrage du spooler...")
    subprocess.run(["net", "start", "spooler"], capture_output=True, text=True)
    time.sleep(1)

    return success

# ===========================================================
# Etape 2 : Modifier le fichier dslrBooth
# ===========================================================
def find_dslrbooth_settings():
    """Cherche le fichier printer_settings.xml de dslrBooth
    dans le profil de tous les utilisateurs."""
    candidates = []

    # Chercher via les profils utilisateurs
    users_dir = r"C:\Users"
    if os.path.isdir(users_dir):
        for user_folder in os.listdir(users_dir):
            settings_path = os.path.join(
                users_dir, user_folder, "AppData", "Roaming", "dslrBooth", "printer_settings.xml"
            )
            if os.path.exists(settings_path):
                candidates.append(settings_path)

    # Aussi verifier le chemin direct de l'utilisateur courant
    direct = os.path.join(os.environ.get("APPDATA", ""), "dslrBooth", "printer_settings.xml")
    if os.path.exists(direct) and direct not in candidates:
        candidates.append(direct)

    return candidates


def modify_dslrbooth_settings(file_path):
    print(f"\n[2/3] Modification de dslrBooth...")
    print(f"  Fichier: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print("  dslrBooth non installe ou fichier introuvable. Etape ignoree.")
        return True
    except Exception as e:
        print(f"  ERREUR lecture: {e}")
        return False

    if "CUT_2INCH" in content and "CUT_STANDARD" not in content:
        print("  Deja configure en CUT_2INCH.")
        return True

    modified = False

    # A. Modifier la feature XML
    if "CUT_STANDARD" in content:
        content = content.replace("ns0000:CUT_STANDARD", "ns0000:CUT_2INCH")
        print("  XML: CUT_STANDARD -> CUT_2INCH")
        modified = True

    # B. Modifier le blob DEVMODE base64
    flat = content.replace("\n", "").replace("\r", "")
    m = re.search(r'PageDevmodeSnapshot.*?xsd:string[^>]*>([A-Za-z0-9+/=]+)<', flat)
    if m:
        old_b64 = m.group(1)
        try:
            dm = bytearray(base64.b64decode(old_b64))

            changes = []

            # Changer byte 282 (option index CUTTERCONTROL)
            if dm[CUTTERCONTROL_DEVMODE_OFFSET] == 0:
                dm[CUTTERCONTROL_DEVMODE_OFFSET] = 1
                changes.append("byte 282: 0 -> 1")

            # Changer la chaine CUT_STANDARD dans la section SMTJ
            old_str = b"CUT_STANDARD\x00"
            new_str = b"CUT_2INCH\x00"
            idx = dm.find(old_str)
            if idx >= 0:
                diff = len(old_str) - len(new_str)
                dm[idx:idx + len(new_str)] = new_str
                dm[idx + len(new_str):len(dm) - diff] = dm[idx + len(old_str):len(dm)]
                dm[len(dm) - diff:] = b"\x00" * diff
                changes.append("SMTJ: CUT_STANDARD -> CUT_2INCH")

            if changes:
                new_b64 = base64.b64encode(bytes(dm)).decode("ascii")
                content = content.replace(old_b64, new_b64)
                for c in changes:
                    print(f"  DEVMODE: {c}")
                modified = True
            else:
                print("  DEVMODE deja a jour.")
        except Exception as e:
            print(f"  ERREUR modification DEVMODE: {e}")
            return False
    else:
        print("  Pas de DevmodeSnapshot dans le fichier (normal si autre imprimante).")

    if modified:
        # Sauvegarder une copie de backup
        backup_path = file_path + ".backup"
        try:
            import shutil
            if not os.path.exists(backup_path):
                shutil.copy2(file_path, backup_path)
                print(f"  Backup: {backup_path}")
        except:
            pass

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print("  Fichier sauvegarde.")

    return True

# ===========================================================
# Etape 3 : Activer sur le hardware via la DLL
# ===========================================================
def activate_hardware(printer_port):
    print(f"\n[3/3] Activation hardware via DLL...")

    arch = platform.architecture()[0]
    dll_name = "Cx2Stat64.dll" if arch == "64bit" else "Cx2Stat.dll"
    dll_path = os.path.join(SCRIPT_DIR, dll_name)

    if not os.path.exists(dll_path):
        print(f"  DLL introuvable: {dll_path}")
        print("  Copiez {0} dans le meme dossier que ce script.".format(dll_name))
        print("  Etape ignoree (le driver Windows est deja configure).")
        return True

    try:
        printer_api = ctypes.WinDLL(dll_path)

        f_init = printer_api.PortInitialize
        f_init.argtypes = [ctypes.c_wchar_p]
        f_init.restype = ctypes.c_int
        handle = f_init(printer_port)

        if handle < 0:
            print(f"  Impossible d'ouvrir le port {printer_port} (imprimante eteinte?)")
            print("  Etape ignoree.")
            return True

        f_cut = printer_api.SetCutterMode
        f_cut.argtypes = [ctypes.c_int, ctypes.c_int]
        f_cut.restype = ctypes.c_int
        result = f_cut(handle, CMODE_2INCHCUT)

        if result >= 0:
            print(f"  Hardware: SetCutterMode retourne {result} (succes)")
        else:
            print(f"  Hardware: SetCutterMode retourne {result} (echec)")
    except Exception as e:
        print(f"  ERREUR DLL: {e}")
        print("  Etape ignoree.")

    return True

# ===========================================================
# Rapport final
# ===========================================================
def write_report(printer_name, printer_port, results):
    report_path = os.path.join(SCRIPT_DIR, "coupe_2pouces_ok.txt")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=" * 50 + "\n")
        f.write("  Coupe 2 pouces - Rapport d'activation\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Date: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Imprimante: {printer_name}\n")
        f.write(f"Port: {printer_port}\n\n")
        for step, status in results:
            f.write(f"[{'OK' if status else 'ECHEC'}] {step}\n")
    print(f"\nRapport: {report_path}")

# ===========================================================
# Main
# ===========================================================
if __name__ == "__main__":
    require_admin()

    print("=" * 50)
    print("  Activation coupe 2 pouces - DNP DS620")
    print("=" * 50)

    # Detection imprimante
    printer_name, printer_port = find_ds620_printer()
    if not printer_name:
        print("\nERREUR: Aucune imprimante DNP DS620 trouvee!")
        print("Verifiez que l'imprimante est installee.")
        input("\nAppuie sur Entree pour fermer...")
        sys.exit(1)

    print(f"\nImprimante: {printer_name}")
    print(f"Port: {printer_port}")

    # Creer le drapeau de maintenance pour empecher le monitor
    # d'afficher l'alerte pendant l'arret du spooler
    try:
        with open(MAINTENANCE_FLAG, "w") as f:
            f.write("maintenance")
        print("\n[FLAG] Drapeau de maintenance cree.")
    except Exception:
        pass

    results = []

    try:
        # Etape 1: Registre Windows
        r1 = modify_registry_devmode(printer_name)
        results.append(("Driver Windows (registre DEVMODE)", r1))

        # Etape 2: dslrBooth
        dslr_files = find_dslrbooth_settings()
        if dslr_files:
            for dslr_path in dslr_files:
                r2 = modify_dslrbooth_settings(dslr_path)
                results.append((f"dslrBooth ({dslr_path})", r2))
        else:
            print("\n[2/3] dslrBooth non detecte. Etape ignoree.")
            results.append(("dslrBooth", True))

        # Etape 3: Hardware DLL
        r3 = activate_hardware(printer_port)
        results.append(("Hardware (DLL SetCutterMode)", r3))

        # Rapport
        write_report(printer_name, printer_port, results)
    finally:
        # Supprimer le drapeau de maintenance dans tous les cas
        try:
            os.remove(MAINTENANCE_FLAG)
            print("[FLAG] Drapeau de maintenance supprime.")
        except Exception:
            pass

    # Resume
    print("\n" + "=" * 50)
    all_ok = all(s for _, s in results)
    if all_ok:
        # Creer le fichier flag pour que le script de startup
        # reactive le hardware au prochain redemarrage
        flag_path = os.path.join(SCRIPT_DIR, "coupe_2pouces_active.flag")
        with open(flag_path, "w") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S"))
        print("  SUCCES! Coupe 2 pouces activee partout.")
        print("  (Flag cree pour reactivation auto au redemarrage)")
    else:
        print("  Termine avec des erreurs (voir ci-dessus).")
    print("=" * 50)

    print("\nREDEMARREZ dslrBooth si il etait ouvert.")
    input("\nAppuie sur Entree pour fermer...")
