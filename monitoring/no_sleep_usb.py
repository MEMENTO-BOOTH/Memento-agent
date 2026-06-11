"""Desactivation de la veille USB pour la DNP DS620.

Pourquoi
--------
Quand Windows coupe le port USB de la DS620 en idle ('selective suspend'),
les jobs envoyes au spooler s'empilent dans la file Windows sans pouvoir
atteindre l'imprimante. Resultat : bouchon, photos non sorties, clients
qui paient sans recevoir leur impression.

On modifie 3 cles registre dans le Device Parameters du peripherique
USB DS620 pour interdire a Windows de mettre le port en veille :
  - AllowIdleIrpInD3 = 0          (pas d'IRP idle en D3 low-power)
  - EnhancedPowerManagementEnabled = 0  (desactive le gestionnaire enhanced)
  - SelectiveSuspendEnabled = 0   (desactive le selective suspend USB)

Aucun impact sur la coupe 2 pouces (DEVMODE distinct), la qualite des
photos, le compteur feuilles ou le status. La seule difference est que
le port USB reste alimente en permanence (~2W de consommation en plus,
imperceptible sur une borne 24/7).

Necessite admin (UAC) car HKLM. Le flag local evite de redeclencher
l'UAC a chaque demarrage. Re-application tous les 30 jours par mesure
de securite (au cas ou une maj Windows reset les Device Parameters).
"""

import os
import sys
import platform
import logging
import time

if hasattr(sys, '_MEIPASS'):
    _DATA_DIR = os.path.join(os.path.expanduser("~"), ".mementoagent")
else:
    _DATA_DIR = os.path.dirname(os.path.abspath(__file__))

os.makedirs(_DATA_DIR, exist_ok=True)
FLAG_PATH = os.path.join(_DATA_DIR, "no_sleep_usb_applied.flag")
LOG_PATH = os.path.join(_DATA_DIR, "no_sleep_usb.log")

# Re-applique si flag plus vieux que ca (au cas ou une maj Windows reset)
FLAG_TTL_DAYS = 30

logging.basicConfig(
    filename=LOG_PATH, level=logging.INFO,
    format="%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
)


def _is_already_applied():
    """True si le fix a deja ete applique recemment (< FLAG_TTL_DAYS)."""
    if not os.path.exists(FLAG_PATH):
        return False
    try:
        age_days = (time.time() - os.path.getmtime(FLAG_PATH)) / 86400
        return age_days < FLAG_TTL_DAYS
    except Exception:
        return False


def desactiver_veille_usb_ds620(force=False):
    """Desactive la veille USB pour toutes les DS620 detectees.

    Idempotent : si le fix a deja ete applique recemment (flag valide),
    retourne True sans rien faire. Sinon lance un PowerShell admin (UAC)
    qui modifie le registre.

    force=True : ignore le flag, force la re-application (pour debug ou
                 verification manuelle).

    Retourne True si on a lance (ou si deja applique), False si le
    systeme n'est pas Windows ou si l'UAC a echoue.
    """
    if platform.system() != "Windows":
        return False
    if not force and _is_already_applied():
        logging.info("Veille USB DS620 deja desactivee (flag valide)")
        return True

    logging.info("=== Desactivation veille USB DS620 ===")

    flag_for_ps = FLAG_PATH.replace(os.sep, '/')
    log_for_ps = LOG_PATH.replace(os.sep, '/')

    # PowerShell admin : enumere les peripheriques USBPRINT, matche ceux qui
    # contiennent DS620 / DP-DS620 / DNP dans leur nom, et patche les 3 cles
    # registre dans Device Parameters.
    ps_script = f'''
$ErrorActionPreference = "SilentlyContinue"
$logFile = "{log_for_ps}"
$flagFile = "{flag_for_ps}"

function Log($msg) {{
    Add-Content -Path $logFile -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') [PS-ADMIN] $msg"
}}

Log "Demarrage desactivation veille USB DS620"

$root = "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\USBPRINT"
$found = 0

if (Test-Path $root) {{
    Get-ChildItem $root | ForEach-Object {{
        $deviceName = $_.PSChildName
        # Matche DS620 dans le hardware id (ex: 'DAI_NIPPON_PRINTINGDP-DS620_PRINTER')
        if ($deviceName -match "DS620|DP-DS620|DNP") {{
            Log "Peripherique trouve: $deviceName"
            $devicePath = $_.PSPath
            # Iterer sur les instances de ce peripherique
            Get-ChildItem $devicePath | ForEach-Object {{
                $instanceId = $_.PSChildName
                $paramsPath = "$($_.PSPath)\\Device Parameters"
                if (Test-Path $paramsPath) {{
                    try {{
                        Set-ItemProperty -Path $paramsPath -Name "AllowIdleIrpInD3" -Value 0 -Type DWord
                        Set-ItemProperty -Path $paramsPath -Name "EnhancedPowerManagementEnabled" -Value 0 -Type DWord
                        Set-ItemProperty -Path $paramsPath -Name "SelectiveSuspendEnabled" -Value 0 -Type DWord
                        Log "Applique sur instance $instanceId"
                        $found++
                    }} catch {{
                        Log "Erreur sur instance $instanceId : $_"
                    }}
                }} else {{
                    Log "Device Parameters absent pour $instanceId"
                }}
            }}
        }}
    }}
}} else {{
    Log "USBPRINT root introuvable - imprimante USB non installee?"
}}

# Aussi traiter les peripheriques sous USB\\ (au cas ou la DS620 apparait pas en USBPRINT)
$usbRoot = "HKLM:\\SYSTEM\\CurrentControlSet\\Enum\\USB"
if (Test-Path $usbRoot) {{
    Get-ChildItem $usbRoot | ForEach-Object {{
        $vidPid = $_.PSChildName
        Get-ChildItem $_.PSPath | ForEach-Object {{
            $instanceId = $_.PSChildName
            $paramsPath = "$($_.PSPath)\\Device Parameters"
            if (Test-Path $paramsPath) {{
                # Lire le FriendlyName ou DeviceDesc pour matcher la DS620
                $friendly = (Get-ItemProperty -Path $_.PSPath -Name "FriendlyName" -ErrorAction SilentlyContinue).FriendlyName
                $desc = (Get-ItemProperty -Path $_.PSPath -Name "DeviceDesc" -ErrorAction SilentlyContinue).DeviceDesc
                if ($friendly -match "DS620|DP-DS620|DNP" -or $desc -match "DS620|DP-DS620|DNP") {{
                    Log "Peripherique USB trouve: $vidPid / $instanceId ($friendly / $desc)"
                    try {{
                        Set-ItemProperty -Path $paramsPath -Name "AllowIdleIrpInD3" -Value 0 -Type DWord
                        Set-ItemProperty -Path $paramsPath -Name "EnhancedPowerManagementEnabled" -Value 0 -Type DWord
                        Set-ItemProperty -Path $paramsPath -Name "SelectiveSuspendEnabled" -Value 0 -Type DWord
                        Log "Applique sur USB $vidPid / $instanceId"
                        $found++
                    }} catch {{
                        Log "Erreur sur USB $instanceId : $_"
                    }}
                }}
            }}
        }}
    }}
}}

Log "Termine. Peripheriques traites: $found"

# Marquer comme applique seulement si on a traite au moins 1 peripherique.
# Sinon (imprimante debranchee ou non installee), on n'ecrit pas le flag
# pour reessayer au prochain demarrage.
if ($found -gt 0) {{
    Set-Content -Path $flagFile -Value "applied $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" -Force
    Log "Flag ecrit. Re-verification dans {FLAG_TTL_DAYS} jours."
}} else {{
    Log "Aucun peripherique traite, flag non ecrit (reessai au prochain demarrage)"
}}
'''

    try:
        import ctypes
        ps_path = os.path.join(_DATA_DIR, "no_sleep_usb_admin.ps1")
        with open(ps_path, "w", encoding="utf-8") as f:
            f.write(ps_script)

        # Lancer en admin via UAC popup
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", "powershell.exe",
            f'-ExecutionPolicy Bypass -WindowStyle Hidden -File "{ps_path}"',
            None, 0  # SW_HIDE
        )
        if ret > 32:
            logging.info("Script admin lance (UAC) - resultat dans no_sleep_usb.log")
            return True
        else:
            logging.warning(f"ShellExecuteW retourne {ret} (UAC refuse?)")
            return False
    except Exception as e:
        logging.error(f"Erreur lancement admin: {e}")
        return False


def est_veille_usb_desactivee():
    """True si le flag de fix applique existe et est valide."""
    return _is_already_applied()


# Permet de tester en standalone : `python -m monitoring.no_sleep_usb`
if __name__ == "__main__":
    print(f"=== Test desactivation veille USB DS620 ===")
    print(f"Deja applique recemment ? {_is_already_applied()}")
    print(f"Lancement... (popup UAC va apparaitre)")
    result = desactiver_veille_usb_ds620(force=True)
    print(f"Lance avec succes ? {result}")
    print(f"Verifier le log: {LOG_PATH}")
    print(f"Verifier le flag: {FLAG_PATH}")
