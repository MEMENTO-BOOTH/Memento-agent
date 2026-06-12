"""Desactivation / reactivation de la veille USB pour la DNP DS620.

Pourquoi
--------
Quand Windows coupe le port USB de la DS620 en idle ('selective suspend'),
les jobs envoyes au spooler s'empilent dans la file Windows sans pouvoir
atteindre l'imprimante. Bouchon -> photos non sorties.

On modifie 3 cles registre dans Device Parameters du peripherique USB
DS620 pour interdire a Windows de mettre le port en veille :
  - AllowIdleIrpInD3 = 0
  - EnhancedPowerManagementEnabled = 0
  - SelectiveSuspendEnabled = 0

API publique
------------
  - desactiver_veille_usb_ds620() : applique le fix (UAC popup)
  - reactiver_veille_usb_ds620()  : remet les valeurs par defaut (UAC popup)
  - est_veille_usb_desactivee()   : lit l'etat reel depuis le registre.
                                     Ne necessite PAS admin (lecture seule).
                                     Persiste meme si l'agent est desinstalle.

Aucun impact sur la coupe 2 pouces (DEVMODE distinct), la qualite des
photos, le compteur feuilles ou le status.
"""

import os
import sys
import platform
import logging

if hasattr(sys, '_MEIPASS'):
    _DATA_DIR = os.path.join(os.path.expanduser("~"), ".mementoagent")
else:
    _DATA_DIR = os.path.dirname(os.path.abspath(__file__))

os.makedirs(_DATA_DIR, exist_ok=True)
LOG_PATH = os.path.join(_DATA_DIR, "no_sleep_usb.log")

logging.basicConfig(
    filename=LOG_PATH, level=logging.INFO,
    format="%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
)


def _iter_ds620_device_param_keys():
    """Itere sur les chemins registre 'Device Parameters' de toutes les
    instances DS620 trouvees, sous USBPRINT\\ ET USB\\.

    Yield des tuples (hive, sous_cle) qu'on peut ouvrir en lecture sans admin.
    Yields rien si win32 absent ou aucun peripherique trouve.
    """
    if platform.system() != "Windows":
        return
    try:
        import winreg
    except ImportError:
        return

    PATTERNS = ("DS620", "DP-DS620", "DNP")

    # 1) USBPRINT\<device_name>\<instance>\Device Parameters
    usbprint = r"SYSTEM\CurrentControlSet\Enum\USBPRINT"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, usbprint) as root:
            i = 0
            while True:
                try:
                    device_name = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                if not any(p in device_name.upper() for p in PATTERNS):
                    continue
                device_path = f"{usbprint}\\{device_name}"
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, device_path) as dev:
                        j = 0
                        while True:
                            try:
                                instance = winreg.EnumKey(dev, j)
                            except OSError:
                                break
                            j += 1
                            yield (winreg.HKEY_LOCAL_MACHINE,
                                   f"{device_path}\\{instance}\\Device Parameters")
                except OSError:
                    pass
    except OSError:
        pass

    # 2) USB\VID_xxxx&PID_xxxx\<instance>\Device Parameters, filtre par
    #    FriendlyName / DeviceDesc contenant DS620 / DNP
    usb_root = r"SYSTEM\CurrentControlSet\Enum\USB"
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, usb_root) as root:
            i = 0
            while True:
                try:
                    vid_pid = winreg.EnumKey(root, i)
                except OSError:
                    break
                i += 1
                vid_pid_path = f"{usb_root}\\{vid_pid}"
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, vid_pid_path) as vk:
                        j = 0
                        while True:
                            try:
                                instance = winreg.EnumKey(vk, j)
                            except OSError:
                                break
                            j += 1
                            inst_path = f"{vid_pid_path}\\{instance}"
                            # Match sur FriendlyName ou DeviceDesc
                            matched = False
                            try:
                                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, inst_path) as ik:
                                    for prop in ("FriendlyName", "DeviceDesc"):
                                        try:
                                            val, _ = winreg.QueryValueEx(ik, prop)
                                            if any(p in val.upper() for p in PATTERNS):
                                                matched = True
                                                break
                                        except OSError:
                                            pass
                            except OSError:
                                pass
                            if matched:
                                yield (winreg.HKEY_LOCAL_MACHINE,
                                       f"{inst_path}\\Device Parameters")
                except OSError:
                    pass
    except OSError:
        pass


def est_veille_usb_desactivee():
    """Lit directement dans le registre Windows si la veille USB est
    desactivee pour la DS620. Source de verite absolue : persiste apres
    desinstallation/reinstallation de l'agent.

    Returns True si AU MOINS UNE instance DS620 a les 3 cles a 0.
    Returns False si aucune instance trouvee OU au moins une instance
    n'a pas les cles configurees correctement.

    Necessite seulement la lecture HKLM (pas d'admin requis pour read).
    """
    if platform.system() != "Windows":
        return False
    try:
        import winreg
    except ImportError:
        return False

    found_any = False
    found_ok = False
    for hive, path in _iter_ds620_device_param_keys():
        found_any = True
        try:
            with winreg.OpenKey(hive, path, 0, winreg.KEY_READ) as k:
                vals = {}
                for prop in ("AllowIdleIrpInD3",
                             "EnhancedPowerManagementEnabled",
                             "SelectiveSuspendEnabled"):
                    try:
                        v, _ = winreg.QueryValueEx(k, prop)
                        vals[prop] = v
                    except OSError:
                        vals[prop] = None
                if all(vals.get(p) == 0 for p in vals):
                    found_ok = True
                    break  # une instance OK suffit
        except OSError:
            pass

    return found_any and found_ok


def _wait_ps1_done(start_pos, timeout=15):
    """Attend que le marqueur de fin '[PS-ADMIN-DONE]' apparaisse dans le log.
    ShellExecuteW est asynchrone : sans attente, on lit l'etat registre
    AVANT que le script ait fini de patcher -> toggle qui semble annule."""
    import time
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(start_pos)
                if "[PS-ADMIN-DONE]" in f.read():
                    return True
        except Exception:
            pass
        time.sleep(0.3)
    logging.warning("Timeout attente PS1 admin (peut-etre UAC refuse)")
    return False


def _run_admin_ps(activate):
    """Lance un PS1 admin (UAC popup) qui patche les cles registre.
    activate=True  -> veille desactivee (les 3 cles = 0)
    activate=False -> retour au defaut Windows (les 3 cles = 1)

    Bloque jusqu'a ce que le script PS ait ecrit son marqueur de fin (max 15s),
    pour que l'appelant puisse lire l'etat registre apres modification."""
    if platform.system() != "Windows":
        return False

    target_byte = 0 if activate else 1
    log_for_ps = LOG_PATH.replace(os.sep, '/')
    action = "DESACTIVATION" if activate else "REACTIVATION"

    ps_script = f'''
$ErrorActionPreference = "SilentlyContinue"
$logFile = "{log_for_ps}"
$target = {target_byte}

function Log($msg) {{
    Add-Content -Path $logFile -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [PS-ADMIN] $msg"
}}

Log "Demarrage {action} veille USB DS620 (target=$target)"

$root = "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\USBPRINT"
$found = 0

if (Test-Path $root) {{
    Get-ChildItem $root | ForEach-Object {{
        $deviceName = $_.PSChildName
        if ($deviceName -match "DS620|DP-DS620|DNP") {{
            Log "Peripherique USBPRINT: $deviceName"
            $devicePath = $_.PSPath
            Get-ChildItem $devicePath | ForEach-Object {{
                $instanceId = $_.PSChildName
                $paramsPath = "$($_.PSPath)\\Device Parameters"
                if (Test-Path $paramsPath) {{
                    try {{
                        Set-ItemProperty -Path $paramsPath -Name "AllowIdleIrpInD3" -Value $target -Type DWord
                        Set-ItemProperty -Path $paramsPath -Name "EnhancedPowerManagementEnabled" -Value $target -Type DWord
                        Set-ItemProperty -Path $paramsPath -Name "SelectiveSuspendEnabled" -Value $target -Type DWord
                        Log "Applique sur instance $instanceId"
                        $found++
                    }} catch {{
                        Log "Erreur sur $instanceId : $_"
                    }}
                }}
            }}
        }}
    }}
}}

$usbRoot = "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\USB"
if (Test-Path $usbRoot) {{
    Get-ChildItem $usbRoot | ForEach-Object {{
        $vidPid = $_.PSChildName
        Get-ChildItem $_.PSPath | ForEach-Object {{
            $instanceId = $_.PSChildName
            $paramsPath = "$($_.PSPath)\\Device Parameters"
            if (Test-Path $paramsPath) {{
                $friendly = (Get-ItemProperty -Path $_.PSPath -Name "FriendlyName" -ErrorAction SilentlyContinue).FriendlyName
                $desc = (Get-ItemProperty -Path $_.PSPath -Name "DeviceDesc" -ErrorAction SilentlyContinue).DeviceDesc
                if ($friendly -match "DS620|DP-DS620|DNP" -or $desc -match "DS620|DP-DS620|DNP") {{
                    Log "Peripherique USB: $vidPid / $instanceId"
                    try {{
                        Set-ItemProperty -Path $paramsPath -Name "AllowIdleIrpInD3" -Value $target -Type DWord
                        Set-ItemProperty -Path $paramsPath -Name "EnhancedPowerManagementEnabled" -Value $target -Type DWord
                        Set-ItemProperty -Path $paramsPath -Name "SelectiveSuspendEnabled" -Value $target -Type DWord
                        Log "Applique sur USB $vidPid / $instanceId"
                        $found++
                    }} catch {{
                        Log "Erreur USB $instanceId : $_"
                    }}
                }}
            }}
        }}
    }}
}}

Log "{action} terminee. Peripheriques traites: $found"
Log "[PS-ADMIN-DONE]"
'''

    try:
        import ctypes
        ps_path = os.path.join(_DATA_DIR, "no_sleep_usb_admin.ps1")
        with open(ps_path, "w", encoding="utf-8") as f:
            f.write(ps_script)

        # Memoriser la taille du log AVANT le lancement pour ne chercher le
        # marqueur DONE que dans les nouvelles lignes (evite de matcher un
        # DONE d'une operation precedente).
        try:
            start_pos = os.path.getsize(LOG_PATH)
        except OSError:
            start_pos = 0

        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "powershell.exe",
            f'-ExecutionPolicy Bypass -WindowStyle Hidden -File "{ps_path}"',
            None, 0  # SW_HIDE
        )
        if ret <= 32:
            logging.warning(f"ShellExecuteW retourne {ret} ({action}) - UAC refuse?")
            return False

        # Bloquer jusqu'a ce que le script ait fini d'ecrire dans le registre.
        # Sans ca, l'appelant lit l'etat AVANT modification -> toggle qui
        # semble annule alors qu'il a marche.
        done = _wait_ps1_done(start_pos, timeout=15)
        if done:
            logging.info(f"{action} terminee avec succes")
        else:
            logging.warning(f"{action} : timeout - le script n'a pas fini dans les 15s")
        return done
    except Exception as e:
        logging.error(f"Erreur lancement {action}: {e}")
        return False


def desactiver_veille_usb_ds620():
    """Empeche Windows de mettre le port USB de la DS620 en veille.
    Popup UAC. Persiste indefiniment dans le registre Windows."""
    logging.info("=== Desactivation veille USB DS620 ===")
    return _run_admin_ps(activate=True)


def reactiver_veille_usb_ds620():
    """Retabli le comportement par defaut Windows (veille USB autorisee).
    Popup UAC. Persiste indefiniment dans le registre Windows."""
    logging.info("=== Reactivation veille USB DS620 (defaut Windows) ===")
    return _run_admin_ps(activate=False)


# Test standalone : `python -m monitoring.no_sleep_usb`
if __name__ == "__main__":
    print(f"=== Test no_sleep_usb ===")
    print(f"Etat actuel (registre) : {'DESACTIVEE' if est_veille_usb_desactivee() else 'ACTIVEE (defaut)'}")
    print(f"Log: {LOG_PATH}")
