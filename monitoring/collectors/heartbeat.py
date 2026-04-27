"""Heartbeat — collecte et envoie les données à Supabase (UPSERT).
Remplace remontee_finale_1.0.0.pyw."""

import concurrent.futures
from datetime import datetime
import requests
import supabase_client as supa
from .printer import lire_imprimante
from .system import lire_processus, lire_wifi, lire_wifi_signal, lire_disque, lire_appareil_photo, lire_versions


# Executeur dedie : 1 thread reutilise pour toutes les lectures imprimante.
# Si la DLL hang, on retourne le cache du dernier resultat valide
# pour eviter de faire passer une imprimante operationnelle pour deconnectee.
_PRINTER_EXEC = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="printer-reader")
_PRINTER_PENDING = [None]
_PRINTER_TIMEOUT_S = 8.0
_PRINTER_LAST_OK = [None]
_PRINTER_NULL = {
    "nom_imprimante": None,
    "serial_imprimante": None,
    "imprimante_statut": None,
    "imprimante_statut_code": None,
    "feuilles_restantes": None,
    "mode_coupe": None,
}


def _lire_imprimante_safe():
    """Lecture imprimante protegee par timeout. Si la DLL hang, on retourne le
    dernier resultat connu pour ne pas declencher de fausses alertes."""
    f = _PRINTER_PENDING[0]
    if f is not None and not f.done():
        return _PRINTER_LAST_OK[0] or _PRINTER_NULL.copy()
    new_f = _PRINTER_EXEC.submit(lire_imprimante)
    _PRINTER_PENDING[0] = new_f
    try:
        result = new_f.result(timeout=_PRINTER_TIMEOUT_S)
        _PRINTER_LAST_OK[0] = result
        return result
    except concurrent.futures.TimeoutError:
        return _PRINTER_LAST_OK[0] or _PRINTER_NULL.copy()
    except Exception:
        return _PRINTER_LAST_OK[0] or _PRINTER_NULL.copy()


def collecter_donnees():
    """Collecte toutes les données de la borne."""
    _log_hb("collect: lire_imprimante (safe)...")
    imprimante = _lire_imprimante_safe()
    _log_hb(f"collect: lire_imprimante done statut={imprimante.get('imprimante_statut')} feuilles={imprimante.get('feuilles_restantes')}")
    _log_hb("collect: lire_processus...")
    processus = lire_processus()
    _log_hb("collect: lire_appareil_photo...")
    appareil = lire_appareil_photo()
    _log_hb("collect: lire_versions...")
    versions = lire_versions()
    _log_hb("collect: lire_wifi_signal...")
    speed, qualite = lire_wifi_signal()
    _log_hb("collect: done")

    return {
        **versions,
        **imprimante,
        **appareil,
        **processus,
        "ssid_wifi": lire_wifi(),
        "wifi_speed_mbps": speed,
        "wifi_qualite": qualite,
        "disque_libre_go": lire_disque(),
    }


def _log_hb(msg):
    import os
    try:
        path = os.path.join(os.path.expanduser("~"), ".mementoagent", "monitoring.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%H:%M:%S} {msg}\n")
    except Exception:
        pass


def envoyer_heartbeat(borne_id, donnees):
    """UPSERT dans la table heartbeats — une seule ligne par borne."""
    # Retirer les champs qui ne sont pas dans la table heartbeats
    exclure = {"imprimante_statut_code", "wifi_speed_mbps", "wifi_qualite", "nom_imprimante"}
    data = {k: v for k, v in donnees.items() if k not in exclure}
    data["borne_id"] = borne_id
    data["timestamp"] = datetime.now().astimezone().isoformat()

    try:
        r = requests.post(
            f"{supa.SUPABASE_URL}/rest/v1/heartbeats?on_conflict=borne_id",
            headers=supa.HEADERS_UPSERT,
            json=data,
            timeout=10,
        )
        if r.status_code in (200, 201):
            _log_hb(f"heartbeat OK ({r.status_code})")
            return True
        body = r.text[:300] if r.text else ""
        _log_hb(f"heartbeat FAIL status={r.status_code} body={body}")
        return False
    except Exception as e:
        _log_hb(f"heartbeat EXCEPTION {type(e).__name__}: {e}")
        return False
