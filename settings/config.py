"""Config locale persistée dans le Registre Windows (HKCU\\Software\\MementoAgent)."""
from paths import reg_get, reg_set

DEFAULTS = {
    "pin":              "0000",
    "pin_enabled":      0,
    "langue":           "fr",
    "theme":            "light",
}

def load():
    data = {}
    for k, default in DEFAULTS.items():
        val = reg_get(k)
        data[k] = val if val is not None else default
    # Normaliser pin_enabled en bool pour compatibilité
    data["pin_enabled"] = bool(data["pin_enabled"])
    return data

def save(data):
    for k, v in data.items():
        if k in DEFAULTS:
            # Convertir bool → int pour REG_DWORD
            reg_set(k, int(v) if isinstance(v, bool) else v)
