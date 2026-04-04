"""Monitoring système — processus, WiFi, disque, caméra.
Extrait de remontee_finale_1.0.0.pyw — fonctionne uniquement sur Windows."""

import os
import platform
import subprocess
import shutil

CREATE_NO_WINDOW = 0x08000000


def lire_processus():
    """Détecte si DSLRBOOTH et Cash Interface tournent."""
    result = {"dslrbooth_running": False, "cash_interface_running": False}

    if platform.system() != "Windows":
        return result

    try:
        output = subprocess.check_output(
            ["powershell", "-Command", "Get-Process | Select-Object -ExpandProperty ProcessName"],
            encoding="utf-8", errors="ignore", creationflags=CREATE_NO_WINDOW,
        )
        noms = output.lower()
        if "dslrbooth" in noms:
            result["dslrbooth_running"] = True
        ci_noms = ["cash interface", "cashinterface", "ci2"]
        if any(n in noms for n in ci_noms):
            result["cash_interface_running"] = True
    except Exception:
        pass

    return result


def lire_wifi():
    """Retourne le nom du réseau WiFi connecté."""
    if platform.system() != "Windows":
        return None

    try:
        output = subprocess.check_output(
            ["powershell", "-Command",
             "(Get-NetConnectionProfile | Where-Object {$_.InterfaceAlias -like '*Wi-Fi*' -or $_.InterfaceAlias -like '*Wireless*'}).Name"],
            encoding="utf-8", errors="ignore", creationflags=CREATE_NO_WINDOW,
        ).strip()
        if output:
            return output.split("\n")[0].strip()
    except Exception:
        pass

    try:
        output = subprocess.check_output(
            ["powershell", "-Command",
             "(Get-NetConnectionProfile | Where-Object {$_.InterfaceAlias -like '*Ethernet*'}).Name"],
            encoding="utf-8", errors="ignore", creationflags=CREATE_NO_WINDOW,
        ).strip()
        if output:
            return f"Ethernet ({output})"
    except Exception:
        pass

    return None


def lire_wifi_signal():
    """Retourne (vitesse_mbps, qualite_pct) du WiFi via la vitesse de liaison."""
    if platform.system() != "Windows":
        return None, None

    try:
        output = subprocess.check_output(
            ["powershell", "-Command",
             "(Get-NetAdapter | Where-Object {$_.Name -like '*Wi-Fi*' -or $_.Name -like '*Wireless*'} | Where-Object Status -eq 'Up').Speed"],
            encoding="utf-8", errors="ignore", creationflags=CREATE_NO_WINDOW,
        ).strip()
        if output and output.isdigit():
            speed_mbps = int(output) / 1_000_000
            # Qualité basée sur la vitesse de liaison WiFi
            if speed_mbps >= 800:
                qualite = 100
            elif speed_mbps >= 400:
                qualite = 80
            elif speed_mbps >= 100:
                qualite = 60
            elif speed_mbps >= 50:
                qualite = 40
            else:
                qualite = 20
            return round(speed_mbps), qualite
    except Exception:
        pass
    return None, None


def lire_disque():
    """Retourne l'espace libre sur C: en Go."""
    try:
        usage = shutil.disk_usage("C:\\" if platform.system() == "Windows" else "/")
        return round(usage.free / (1024 ** 3), 1)
    except Exception:
        return None


def lire_appareil_photo():
    """Détecte si un appareil photo Canon/Nikon/Sony est réellement connecté (Status=OK)."""
    result = {"serial_appareil_photo": None, "appareil_connecte": False}

    if platform.system() != "Windows":
        return result

    for cmd in [
        "Get-PnpDevice -PresentOnly | Where-Object {$_.Status -eq 'OK' -and ($_.Class -eq 'Camera' -or $_.Class -eq 'Image' -or $_.Class -eq 'WPD') -and ($_.FriendlyName -match 'Canon|Nikon|Sony|Camera|DSLR')} | Select-Object -ExpandProperty FriendlyName",
        "Get-PnpDevice -PresentOnly | Where-Object {$_.Status -eq 'OK' -and $_.InstanceId -match 'USB' -and ($_.FriendlyName -match 'Canon|Nikon|Sony|Camera|DSLR|PTP')} | Select-Object -ExpandProperty FriendlyName",
    ]:
        try:
            output = subprocess.check_output(
                ["powershell", "-Command", cmd],
                encoding="utf-8", errors="ignore", creationflags=CREATE_NO_WINDOW,
            ).strip()
            if output:
                return {"serial_appareil_photo": output.split("\n")[0].strip(), "appareil_connecte": True}
        except Exception:
            pass

    return result


def lire_versions():
    """Lit les versions de l'agent, DSLRBOOTH et Cash Interface."""
    from version import VERSION
    versions = {
        "version_agent": VERSION,
        "version_dslrbooth": None,
        "version_cash_interface": None,
    }

    if platform.system() != "Windows":
        return versions

    # DSLRBOOTH
    for exe in [r"C:\Program Files\dslrBooth\dslrBooth.exe", r"C:\Program Files (x86)\dslrBooth\dslrBooth.exe"]:
        if os.path.exists(exe):
            try:
                ps = subprocess.check_output(
                    ["powershell", "-Command", f"(Get-Item '{exe}').VersionInfo.ProductVersion"],
                    encoding="utf-8", errors="ignore", creationflags=CREATE_NO_WINDOW,
                ).strip()
                if ps:
                    versions["version_dslrbooth"] = ps
                    break
            except Exception:
                pass

    # Cash Interface
    try:
        path = subprocess.check_output(
            ["powershell", "-Command", "Get-Process | Where-Object {$_.ProcessName -match 'cash|ci2'} | Select-Object -ExpandProperty Path"],
            encoding="utf-8", errors="ignore", creationflags=CREATE_NO_WINDOW,
        ).strip()
        if path:
            ver = subprocess.check_output(
                ["powershell", "-Command", f"(Get-Item '{path.split(chr(10))[0].strip()}').VersionInfo.ProductVersion"],
                encoding="utf-8", errors="ignore", creationflags=CREATE_NO_WINDOW,
            ).strip()
            if ver:
                versions["version_cash_interface"] = ver
    except Exception:
        pass

    return versions
