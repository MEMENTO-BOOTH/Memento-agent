"""Heartbeat — collecte et envoie les données à Supabase (UPSERT).
Remplace remontee_finale_1.0.0.pyw."""

from datetime import datetime
import requests
import supabase_client as supa
from .printer import lire_imprimante
from .system import lire_processus, lire_wifi, lire_wifi_signal, lire_disque, lire_appareil_photo, lire_versions


def collecter_donnees():
    """Collecte toutes les données de la borne."""
    imprimante = lire_imprimante()
    processus = lire_processus()
    appareil = lire_appareil_photo()
    versions = lire_versions()

    speed, qualite = lire_wifi_signal()

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
        return r.status_code in (200, 201)
    except Exception:
        return False
