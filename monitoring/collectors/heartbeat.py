"""Heartbeat — collecte et envoie les données à Supabase (UPSERT).
Remplace remontee_finale_1.0.0.pyw."""

from datetime import datetime
import requests
import supabase_client as supa
from .printer import lire_imprimante
from .system import lire_processus, lire_wifi, lire_wifi_signal, lire_disque, lire_appareil_photo, lire_versions


def collecter_donnees():
    """Collecte toutes les données de la borne."""
    _log_hb("collect: lire_imprimante...")
    imprimante = lire_imprimante()
    _log_hb(f"collect: lire_imprimante OK statut={imprimante.get('imprimante_statut')} feuilles={imprimante.get('feuilles_restantes')}")
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
