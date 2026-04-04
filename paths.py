"""Chemins centralisés + accès Registre Windows — compatible PyInstaller."""
import os
import sys
import winreg

_REG_PATH = r"Software\MementoAgent"

_DEFAULTS = {
    "setup_done":       (0,           winreg.REG_DWORD),
    "pin":              ("0000",      winreg.REG_SZ),
    "pin_enabled":      (0,           winreg.REG_DWORD),
    "langue":           ("fr",        winreg.REG_SZ),
    "theme":            ("light",     winreg.REG_SZ),
}


def reg_get(name):
    """Lit une valeur dans HKCU\\Software\\MementoAgent. Retourne le défaut si absent."""
    default, _ = _DEFAULTS.get(name, (None, winreg.REG_SZ))
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as k:
            value, _ = winreg.QueryValueEx(k, name)
            return value
    except OSError:
        return default


def reg_set(name, value):
    """Écrit une valeur dans HKCU\\Software\\MementoAgent."""
    _, reg_type = _DEFAULTS.get(name, (None, winreg.REG_SZ))
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_PATH) as k:
        winreg.SetValueEx(k, name, 0, reg_type, value)


def _base_dir():
    """Retourne le dossier racine des assets, compatible PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _base_dir()
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
