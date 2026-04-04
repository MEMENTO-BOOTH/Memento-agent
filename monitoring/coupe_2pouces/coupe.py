"""Gestion de la coupe 2 pouces — DNP DS620.
Intègre : activation/désactivation complète (registre + dslrBooth XML + DLL hardware).
Fonctionne en mode PyInstaller (pas de sous-processus Python).
Les opérations admin (HKLM, spooler) sont tentées et échouent gracieusement."""

import os
import sys
import platform
import logging

if hasattr(sys, '_MEIPASS'):
    _DATA_DIR = os.path.join(os.path.expanduser("~"), ".mementoagent")
    SCRIPT_DIR = os.path.join(sys._MEIPASS, "monitoring", "coupe_2pouces")
else:
    _DATA_DIR = os.path.dirname(os.path.abspath(__file__))
    SCRIPT_DIR = _DATA_DIR

os.makedirs(_DATA_DIR, exist_ok=True)
FLAG_PATH = os.path.join(_DATA_DIR, "coupe_2pouces_active.flag")
LOG_PATH = os.path.join(_DATA_DIR, "coupe.log")

logging.basicConfig(
    filename=LOG_PATH, level=logging.INFO,
    format="%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
)

PRINTER_PATTERNS = ["DP-DS620", "DNP-DS620", "DNP DS620", "DS620"]
CUTTERCONTROL_DEVMODE_OFFSET = 282
CMODE_2INCHCUT = 120
CMODE_STANDARD = 0


def _is_ds620(name):
    n = name.upper()
    return any(p.upper() in n for p in PRINTER_PATTERNS)


# ═══════════════════════════════════════════════════════════════
#  Utilitaires partagés
# ═══════════════════════════════════════════════════════════════

def _find_ds620():
    """Retourne (printer_name, printer_port) ou (None, None).
    Cherche toutes les variantes: DP-DS620, DNP-DS620, Copie 1..10."""
    if platform.system() != "Windows":
        return None, None
    import winreg, ctypes
    reg = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Print\Printers"
    all_printers = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg) as key:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(key, i)
                except OSError:
                    break
                i += 1
                if _is_ds620(name):
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{reg}\\{name}") as pk:
                        port, _ = winreg.QueryValueEx(pk, "Port")
                    all_printers.append((name, port))
    except Exception as e:
        logging.error(f"Détection imprimante: {e}")

    if not all_printers:
        return None, None

    # Tester chaque port — prendre celle qui répond
    dll_path = os.path.join(os.path.dirname(__file__), "Cx2Stat64.dll")
    if os.path.exists(dll_path):
        try:
            dll = ctypes.WinDLL(dll_path)
            dll.PortInitialize.argtypes = [ctypes.c_wchar_p]
            dll.PortInitialize.restype = ctypes.c_int
            dll.GetStatus.argtypes = [ctypes.c_int]
            dll.GetStatus.restype = ctypes.c_uint
            for name, port in all_printers:
                h = dll.PortInitialize(port)
                if h >= 0:
                    st = dll.GetStatus(h)
                    if st != 0x80000000:
                        return name, port
        except Exception:
            pass

    # Fallback : première trouvée
    return all_printers[0]


def _get_dll_path():
    """Retourne le chemin de la DLL Cx2Stat64 ou None."""
    dll_path = os.path.join(SCRIPT_DIR, "Cx2Stat64.dll")
    if os.path.exists(dll_path):
        return dll_path
    # Fallback dans _DATA_DIR
    dll_path2 = os.path.join(_DATA_DIR, "Cx2Stat64.dll")
    if os.path.exists(dll_path2):
        return dll_path2
    return None


def _get_desktop_user_sids():
    """Trouve les SID des utilisateurs bureau."""
    import winreg
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
    except Exception:
        pass
    return sids


# ═══════════════════════════════════════════════════════════════
#  SMTJ builders
# ═══════════════════════════════════════════════════════════════

def _build_smtj_data(cut_mode="CUT_2INCH", printer_name="DP-DS620"):
    """Construit les données SMTJ."""
    data = bytearray()
    base_name = printer_name.split(" (")[0] if " (" in printer_name else printer_name
    data += (base_name + "\x00").encode("utf-16-le")
    pairs = [
        ("InputBin", "FORMSOURCE"), ("RESDLL", "UniresDLL"),
        ("Orientation", "PORTRAIT"), ("Resolution", "Option1"),
        ("PrintMargin", "MarginOff"), ("OVERCOATTYPE", "OPTYPE_LUSTER"),
        ("PRINTBUFFCONTROL", "PBC_NONCLEAR"), ("CUTTERCONTROL", cut_mode),
        ("PaperSize", "PC"), ("MediaType", "STANDARD"),
        ("ColorMode", "24bpp"), ("Halftone", "HT_PATSIZE_SUPERCELL_M"),
    ]
    for key, val in pairs:
        data += key.encode("ascii") + b"\x00"
        data += val.encode("ascii") + b"\x00"
    return data


def _fix_smtj_section(dm, target="CUT_2INCH"):
    """Remplace la section SMTJ du DEVMODE. Retourne (dm, modified)."""
    other = "CUT_STANDARD" if target == "CUT_2INCH" else "CUT_2INCH"
    idx_smtj = dm.find(b"SMTJ")
    if idx_smtj < 0:
        return dm, False
    text_start = idx_smtj + 12
    idx_tfsm = dm.find(b"TFSM", text_start)
    if idx_tfsm < 0:
        return dm, False
    current = dm[text_start:idx_tfsm]
    if target.encode() in current and other.encode() not in current:
        return dm, False
    available = idx_tfsm - text_start
    new_data = bytearray(_build_smtj_data(target))
    if len(new_data) <= available:
        new_data += b"\x00" * (available - len(new_data))
    else:
        new_data = new_data[:available]
    dm[text_start:idx_tfsm] = new_data
    return dm, True


# ═══════════════════════════════════════════════════════════════
#  Étape 1 : Registre Windows (DEVMODE) — via PowerShell admin
# ═══════════════════════════════════════════════════════════════

def _modify_registry(printer_name, activate=True):
    """Modifie le DEVMODE via un script PowerShell lancé en admin (UAC).
    Génère un .ps1 temporaire, le lance avec Start-Process -Verb RunAs."""
    import tempfile
    import ctypes

    target_byte = 1 if activate else 0
    target_smtj = "CUT_2INCH" if activate else "CUT_STANDARD"
    other_smtj = "CUT_STANDARD" if activate else "CUT_2INCH"

    # Script PowerShell qui modifie le registre en admin
    ps_script = f'''
$ErrorActionPreference = "SilentlyContinue"
$printerName = "{printer_name}"
$regPath = "HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Print\\Printers\\$printerName"
$targetByte = {target_byte}
$logFile = "{LOG_PATH.replace(os.sep, '/')}"

function Log($msg) {{ Add-Content -Path $logFile -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [PS-ADMIN] $msg" }}

# Arreter le spooler
Log "Arret spooler..."
Stop-Service -Name Spooler -Force
Start-Sleep -Seconds 1

# Modifier HKLM Default DevMode
try {{
    $dm = (Get-ItemProperty -Path $regPath -Name "Default DevMode")."Default DevMode"
    if ($dm -and $dm.Length -gt 282) {{
        $dm[282] = $targetByte
        # Modifier section SMTJ si presente
        $smtjText = [System.Text.Encoding]::ASCII.GetString($dm)
        if ($smtjText -match "{other_smtj}") {{
            $oldBytes = [System.Text.Encoding]::ASCII.GetBytes("{other_smtj}")
            $newBytes = [System.Text.Encoding]::ASCII.GetBytes("{target_smtj}")
            $str = [System.Text.Encoding]::ASCII.GetString($dm)
            $idx = $str.IndexOf("{other_smtj}")
            if ($idx -ge 0) {{
                # Remplacer les bytes directement
                for ($i = 0; $i -lt $newBytes.Length; $i++) {{
                    $dm[$idx + $i] = $newBytes[$i]
                }}
                # Si le nouveau est plus court, remplir avec des zeros
                for ($i = $newBytes.Length; $i -lt $oldBytes.Length; $i++) {{
                    $dm[$idx + $i] = 0
                }}
            }}
        }}
        Set-ItemProperty -Path $regPath -Name "Default DevMode" -Value $dm -Type Binary
        Log "HKLM: byte 282 = $targetByte, SMTJ = {target_smtj}"
    }} else {{
        Log "HKLM: DEVMODE trop court ou introuvable"
    }}
}} catch {{
    Log "HKLM erreur: $_"
}}

# Modifier HKU (per-user DevMode)
$profilesReg = "HKLM:\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\ProfileList"
Get-ChildItem $profilesReg | ForEach-Object {{
    $sid = $_.PSChildName
    if ($sid.Length -lt 20) {{ return }}
    $hkuPath = "Registry::HKEY_USERS\\$sid\\Printers\\DevModePerUser"
    try {{
        $dmUser = (Get-ItemProperty -Path $hkuPath -Name $printerName -ErrorAction Stop).$printerName
        if ($dmUser -and $dmUser.Length -gt 282) {{
            $dmUser[282] = $targetByte
            $str = [System.Text.Encoding]::ASCII.GetString($dmUser)
            $idx = $str.IndexOf("{other_smtj}")
            if ($idx -ge 0) {{
                $newBytes = [System.Text.Encoding]::ASCII.GetBytes("{target_smtj}")
                $oldBytes = [System.Text.Encoding]::ASCII.GetBytes("{other_smtj}")
                for ($i = 0; $i -lt $newBytes.Length; $i++) {{
                    $dmUser[$idx + $i] = $newBytes[$i]
                }}
                for ($i = $newBytes.Length; $i -lt $oldBytes.Length; $i++) {{
                    $dmUser[$idx + $i] = 0
                }}
            }}
            Set-ItemProperty -Path $hkuPath -Name $printerName -Value $dmUser -Type Binary
            Log "HKU ($sid): byte 282 = $targetByte"
        }}
    }} catch {{ }}
}}

# Redemarrer le spooler
Log "Redemarrage spooler..."
Start-Service -Name Spooler
Start-Sleep -Seconds 1
Log "Termine."
'''

    # Écrire le script dans un fichier temporaire
    try:
        ps_path = os.path.join(_DATA_DIR, "coupe_admin.ps1")
        with open(ps_path, "w", encoding="utf-8") as f:
            f.write(ps_script)

        # Lancer en admin via ShellExecuteW (UAC popup)
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "powershell.exe",
            f'-ExecutionPolicy Bypass -WindowStyle Hidden -File "{ps_path}"',
            None, 0  # 0 = SW_HIDE
        )
        if ret > 32:
            logging.info("Script admin lancé (UAC)")
            return True
        else:
            logging.warning(f"ShellExecuteW retourne {ret} (UAC refusé?)")
            return False
    except Exception as e:
        logging.error(f"Erreur lancement admin: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
#  Étape 2 : dslrBooth XML
# ═══════════════════════════════════════════════════════════════

def _modify_dslrbooth(activate=True):
    """Modifie les fichiers printer_settings.xml de dslrBooth."""
    import re
    import base64

    old_mode = "CUT_STANDARD" if activate else "CUT_2INCH"
    new_mode = "CUT_2INCH" if activate else "CUT_STANDARD"
    target_byte = 1 if activate else 0

    candidates = []
    users_dir = r"C:\Users"
    if os.path.isdir(users_dir):
        for user_folder in os.listdir(users_dir):
            path = os.path.join(users_dir, user_folder, "AppData", "Roaming", "dslrBooth", "printer_settings.xml")
            if os.path.exists(path):
                candidates.append(path)
    direct = os.path.join(os.environ.get("APPDATA", ""), "dslrBooth", "printer_settings.xml")
    if os.path.exists(direct) and direct not in candidates:
        candidates.append(direct)

    if not candidates:
        logging.info("dslrBooth non détecté, étape ignorée")
        return True

    for file_path in candidates:
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()

            if new_mode in content and old_mode not in content:
                continue  # déjà correct

            modified = False

            # A. Feature XML
            if old_mode in content:
                content = content.replace(f"ns0000:{old_mode}", f"ns0000:{new_mode}")
                modified = True

            # B. Blob DEVMODE base64
            flat = content.replace("\n", "").replace("\r", "")
            m = re.search(r'PageDevmodeSnapshot.*?xsd:string[^>]*>([A-Za-z0-9+/=]+)<', flat)
            if m:
                old_b64 = m.group(1)
                try:
                    dm = bytearray(base64.b64decode(old_b64))
                    dm[CUTTERCONTROL_DEVMODE_OFFSET] = target_byte

                    old_str = old_mode.encode() + b"\x00"
                    new_str = new_mode.encode() + b"\x00"
                    idx = dm.find(old_str)
                    if idx >= 0:
                        original_len = len(dm)
                        dm = dm[:idx] + new_str + dm[idx + len(old_str):]
                        if len(dm) > original_len:
                            dm = dm[:original_len]
                        elif len(dm) < original_len:
                            dm += b'\x00' * (original_len - len(dm))

                    new_b64 = base64.b64encode(bytes(dm)).decode("ascii")
                    content = content.replace(old_b64, new_b64)
                    modified = True
                except Exception as e:
                    logging.warning(f"dslrBooth DEVMODE: {e}")

            if modified:
                import shutil
                backup = file_path + ".backup"
                if not os.path.exists(backup):
                    try:
                        shutil.copy2(file_path, backup)
                    except Exception:
                        pass
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(content)
                logging.info(f"dslrBooth: {file_path} → {new_mode}")

        except Exception as e:
            logging.warning(f"dslrBooth {file_path}: {e}")

    return True


# ═══════════════════════════════════════════════════════════════
#  Étape 3 : Hardware DLL (SetCutterMode)
# ═══════════════════════════════════════════════════════════════

def _set_hardware_cutter(printer_port, mode):
    """Appelle SetCutterMode via la DLL. Ne nécessite pas admin."""
    dll_path = _get_dll_path()
    if not dll_path:
        logging.warning("DLL introuvable pour SetCutterMode")
        return False

    try:
        import ctypes
        dll = ctypes.WinDLL(dll_path)
        dll.PortInitialize.argtypes = [ctypes.c_wchar_p]
        dll.PortInitialize.restype = ctypes.c_int
        handle = dll.PortInitialize(printer_port)

        if handle < 0:
            logging.warning(f"Imprimante pas prête (port {printer_port})")
            return False

        dll.SetCutterMode.argtypes = [ctypes.c_int, ctypes.c_int]
        dll.SetCutterMode.restype = ctypes.c_int
        result = dll.SetCutterMode(handle, mode)

        if result >= 0:
            logging.info(f"SetCutterMode({mode}) → {result} (succès)")
            return True
        else:
            logging.error(f"SetCutterMode({mode}) → {result} (échec)")
            return False
    except Exception as e:
        logging.error(f"Erreur DLL: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
#  API publique
# ═══════════════════════════════════════════════════════════════

def _restart_dslrbooth():
    """Ferme dslrBooth, attend qu'il sauve, puis le relance."""
    import subprocess, time
    # Fermer
    ret = subprocess.run(["taskkill", "/F", "/IM", "dslrBooth.exe"],
                         capture_output=True, text=True, timeout=10)
    was_running = ret.returncode == 0
    if was_running:
        logging.info("dslrBooth fermé")
        time.sleep(3)
    return was_running


def _launch_dslrbooth():
    """Relance dslrBooth."""
    import subprocess
    for path in [
        r"C:\Program Files\dslrBooth\dslrBooth.exe",
        r"C:\Program Files (x86)\dslrBooth\dslrBooth.exe",
    ]:
        if os.path.exists(path):
            subprocess.Popen([path])
            logging.info("dslrBooth relancé")
            return


def activer_coupe():
    """Active la coupe 2 pouces (ferme dslrBooth → registre → XML → DLL → relance)."""
    if platform.system() != "Windows":
        return False

    logging.info("=== Activation coupe 2 pouces ===")

    printer_name, printer_port = _find_ds620()
    if not printer_name:
        logging.warning("Imprimante DS620 non trouvée")
        return False

    # 0. Fermer dslrBooth AVANT
    was_running = _restart_dslrbooth()

    # 1. Registre
    _modify_registry(printer_name, activate=True)

    # 2. dslrBooth XML
    _modify_dslrbooth(activate=True)

    # 3. Hardware DLL
    _set_hardware_cutter(printer_port, CMODE_2INCHCUT)

    # 4. Relancer dslrBooth
    if was_running:
        _launch_dslrbooth()

    _set_flag(True)
    logging.info("Activation coupe terminée")
    return True


def desactiver_coupe():
    """Désactive la coupe 2 pouces (ferme dslrBooth → registre → XML → DLL → relance)."""
    if platform.system() != "Windows":
        return False

    logging.info("=== Désactivation coupe 2 pouces ===")

    printer_name, printer_port = _find_ds620()
    if not printer_name:
        logging.warning("Imprimante DS620 non trouvée")
        return False

    # 0. Fermer dslrBooth AVANT
    was_running = _restart_dslrbooth()

    # 1. Registre
    _modify_registry(printer_name, activate=False)

    # 2. dslrBooth XML
    _modify_dslrbooth(activate=False)

    # 3. Hardware DLL
    _set_hardware_cutter(printer_port, CMODE_STANDARD)

    # 4. Relancer dslrBooth
    if was_running:
        _launch_dslrbooth()

    _set_flag(False)
    logging.info("Désactivation coupe terminée")
    return True


def startup_hardware():
    """Réactive le hardware au démarrage si le flag est actif."""
    if platform.system() != "Windows":
        return False
    if not os.path.exists(FLAG_PATH):
        return False

    logging.info("=== Startup coupe 2 pouces ===")
    printer_name, printer_port = _find_ds620()
    if not printer_port:
        logging.warning("Imprimante non trouvée au startup")
        return False

    return _set_hardware_cutter(printer_port, CMODE_2INCHCUT)


def est_coupe_active():
    """Vérifie si le flag de coupe est actif."""
    return os.path.exists(FLAG_PATH)


def _set_flag(active):
    if active:
        with open(FLAG_PATH, "w") as f:
            f.write("active")
    else:
        if os.path.exists(FLAG_PATH):
            os.remove(FLAG_PATH)
