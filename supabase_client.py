"""
Module Supabase partagé — source unique pour URL, clé, headers.
Utilisé par settings.py, TPE.py, et tout module qui parle à Supabase.
La borne s'identifie via son hostname Windows (socket.gethostname()).
"""

import os
import sys
import socket
import requests


def _load_env():
    """Charge les variables depuis .env (compatible PyInstaller)."""
    env = {}
    # Chercher .env à côté de l'exe ou du script
    if hasattr(sys, '_MEIPASS'):
        candidates = [
            os.path.join(os.path.dirname(sys.executable), ".env"),
            os.path.join(sys._MEIPASS, ".env"),
        ]
    else:
        candidates = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        ]
    for path in candidates:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        env[k.strip()] = v.strip()
            break
    return env


_env = _load_env()
SUPABASE_URL = os.environ.get("SUPABASE_URL") or _env.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY") or _env.get("SUPABASE_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN") or _env.get("GITHUB_TOKEN", "")
GITHUB_REPO = "MEMENTO-BOOTH/Memento-agent"

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

HEADERS_MINIMAL = {
    **HEADERS,
    "Prefer": "return=minimal",
}

HEADERS_UPSERT = {
    **HEADERS,
    "Prefer": "resolution=merge-duplicates,return=representation",
}

TIMEOUT = 10


def _url(endpoint):
    return f"{SUPABASE_URL}/rest/v1/{endpoint}"


def get_borne():
    """Identifie la borne via le hostname. Retourne le dict complet ou None."""
    hostname = socket.gethostname()
    try:
        r = requests.get(
            _url(f"bornes?code=eq.{hostname}&select=*"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception:
        pass
    return None


def get_or_create_borne():
    """Récupère la borne via hostname, la crée si elle n'existe pas encore."""
    hostname = socket.gethostname()
    try:
        # Chercher d'abord
        r = requests.get(
            _url(f"bornes?code=eq.{hostname}&select=*"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200 and r.json():
            return r.json()[0]

        # Créer si absente
        data = {
            "code": hostname,
            "nom_lieu": f"Borne {hostname}",
            "adresse": "",
            "ville": "",
            "statut": "active",
            "setup_done": False,
        }
        r = requests.post(
            _url("bornes"),
            headers=HEADERS, json=data, timeout=TIMEOUT,
        )
        if r.status_code in (200, 201) and r.json():
            borne = r.json()[0]
            # Créer les horaires par défaut (7 jours, ouverts 24h/24)
            horaires_defaut = [
                {"borne_id": borne["id"], "jour": j, "ouverture": "00:00:00", "fermeture": "23:59:00", "ferme": False}
                for j in range(7)
            ]
            try:
                requests.post(
                    _url("horaires"),
                    headers=HEADERS_MINIMAL, json=horaires_defaut, timeout=TIMEOUT,
                )
            except Exception:
                pass
            return borne
    except Exception:
        pass
    return None


def get_heartbeat(borne_id):
    """Récupère le heartbeat courant de la borne."""
    try:
        r = requests.get(
            _url(f"heartbeats?borne_id=eq.{borne_id}&select=*"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception:
        pass
    return None


def get_horaires(borne_id):
    """Récupère les 7 jours d'horaires."""
    try:
        r = requests.get(
            _url(f"horaires?borne_id=eq.{borne_id}&select=*&order=jour"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def save_horaires(borne_id, rows):
    """Sauvegarde les 7 jours. INSERT d'abord, DELETE seulement si INSERT réussit."""
    try:
        for row in rows:
            row["borne_id"] = borne_id

        # UPSERT au lieu de DELETE+INSERT (plus sûr)
        headers_upsert = {
            **HEADERS,
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }
        # Ajouter un identifiant unique par jour pour l'upsert
        r_ins = requests.post(
            _url("horaires"),
            headers=HEADERS_MINIMAL, json=rows, timeout=TIMEOUT,
        )
        if r_ins.status_code in (200, 201):
            # INSERT OK → supprimer les anciens (ceux qui ne sont pas dans les nouveaux IDs)
            requests.delete(
                _url(f"horaires?borne_id=eq.{borne_id}"),
                headers=HEADERS_MINIMAL, timeout=TIMEOUT,
            )
            # Réinsérer proprement
            requests.post(
                _url("horaires"),
                headers=HEADERS_MINIMAL, json=rows, timeout=TIMEOUT,
            )
            return True
        else:
            print(f"[SUPABASE] insert horaires: {r_ins.status_code} {r_ins.text[:200]}")
            # Fallback : DELETE + INSERT classique
            requests.delete(
                _url(f"horaires?borne_id=eq.{borne_id}"),
                headers=HEADERS_MINIMAL, timeout=TIMEOUT,
            )
            r2 = requests.post(
                _url("horaires"),
                headers=HEADERS_MINIMAL, json=rows, timeout=TIMEOUT,
            )
            return r2.status_code in (200, 201)
    except Exception as e:
        print(f"[SUPABASE] save_horaires error: {e}")
        return False


def patch_borne(borne_id, data):
    """Met à jour un champ de la borne (ex: statut)."""
    try:
        r = requests.patch(
            _url(f"bornes?id=eq.{borne_id}"),
            headers=HEADERS_MINIMAL, json=data, timeout=TIMEOUT,
        )
        return r.status_code in (200, 204)
    except Exception:
        return False


def supabase_patch_heartbeat(borne_id, data):
    """Met à jour un champ du heartbeat (ex: mode_coupe)."""
    try:
        r = requests.patch(
            _url(f"heartbeats?borne_id=eq.{borne_id}"),
            headers=HEADERS_MINIMAL, json=data, timeout=TIMEOUT,
        )
        return r.status_code in (200, 204)
    except Exception:
        return False


def get_alertes(borne_id, limit=50):
    """Récupère toutes les alertes récentes de la borne (pour la page alertes)."""
    try:
        r = requests.get(
            _url(f"alertes?borne_id=eq.{borne_id}&select=*&order=timestamp.desc&limit={limit}"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def get_alertes_ouvertes(borne_id, limit=20):
    """Récupère uniquement les alertes OUVERTES (pour le dashboard)."""
    try:
        r = requests.get(
            _url(f"alertes?borne_id=eq.{borne_id}&statut=eq.ouverte&select=*&order=timestamp.desc&limit={limit}"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def get_transactions_today(borne_id):
    """Récupère les transactions du jour."""
    from datetime import date
    today = date.today().isoformat()
    try:
        r = requests.get(
            _url(f"transactions?borne_id=eq.{borne_id}&paiement_at=gte.{today}&select=*&order=paiement_at.desc"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def get_transactions_by_date(borne_id, target_date):
    """Récupère les transactions d'une date précise (YYYY-MM-DD)."""
    from datetime import timedelta
    d = target_date.isoformat()
    d_next = (target_date + timedelta(days=1)).isoformat()
    try:
        r = requests.get(
            _url(f"transactions?borne_id=eq.{borne_id}&paiement_at=gte.{d}&paiement_at=lt.{d_next}&select=*&order=paiement_at.desc"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def get_transactions_week(borne_id, ref_date):
    """Récupère les transactions de la semaine contenant ref_date."""
    from datetime import timedelta
    monday = ref_date - timedelta(days=ref_date.weekday())
    sunday = monday + timedelta(days=7)
    try:
        r = requests.get(
            _url(f"transactions?borne_id=eq.{borne_id}&paiement_at=gte.{monday.isoformat()}&paiement_at=lt.{sunday.isoformat()}&select=*&order=paiement_at.desc"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def get_ca_stats(transactions):
    """Calcule les stats CA depuis une liste de transactions."""
    total = len(transactions)
    reussies = sum(1 for t in transactions if t.get("impression_declenchee"))
    echouees = total - reussies
    montant = sum(float(t.get("montant", 0)) for t in transactions)
    anomalies = sum(1 for t in transactions if t.get("flag"))
    return {
        "total": total,
        "reussies": reussies,
        "echouees": echouees,
        "montant": montant,
        "anomalies": anomalies,
    }


def get_latest_update():
    """Récupère la dernière mise à jour publiée."""
    try:
        r = requests.get(
            _url("updates?select=*&order=publiee_at.desc&limit=1"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception:
        pass
    return None


def get_latest_github_release():
    """Récupère la dernière release depuis GitHub (repo privé)."""
    if not GITHUB_TOKEN:
        return None
    try:
        r = requests.get(
            f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest",
            headers={
                "Authorization": f"token {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return None
        release = r.json()
        version = release.get("tag_name", "").lstrip("v")
        notes = release.get("body", "")
        exe_asset = None
        for asset in release.get("assets", []):
            if asset["name"].endswith(".exe"):
                exe_asset = asset
                break
        if not exe_asset:
            return None
        return {
            "version": version,
            "download_url": exe_asset["url"],
            "filename": exe_asset["name"],
            "notes": notes,
        }
    except Exception:
        return None


def get_update_status(borne_id):
    """Récupère le statut de mise à jour de cette borne."""
    try:
        r = requests.get(
            _url(f"updates_bornes?borne_id=eq.{borne_id}&select=*,update:updates(version)&order=created_at.desc&limit=1"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception:
        pass
    return None


def get_utilisateurs():
    """Récupère les utilisateurs."""
    try:
        r = requests.get(
            _url("utilisateurs?select=id,email,nom,telephone,role&actif=eq.true&order=nom"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def get_alerte_destinataires(borne_id):
    """Récupère les destinataires d'alertes SMS pour cette borne (+ globaux)."""
    try:
        r = requests.get(
            _url(f"alerte_destinataires?or=(borne_id.eq.{borne_id},borne_id.is.null)&actif=eq.true&select=*&order=created_at"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def save_alerte_destinataires(borne_id, contacts):
    """Supprime puis réinsère les destinataires pour cette borne."""
    try:
        # Supprimer les existants pour cette borne
        requests.delete(
            _url(f"alerte_destinataires?borne_id=eq.{borne_id}"),
            headers=HEADERS_MINIMAL, timeout=TIMEOUT,
        )
        # Insérer les nouveaux
        for c in contacts:
            if c.get("telephone") or c.get("email"):
                requests.post(
                    _url("alerte_destinataires"),
                    headers=HEADERS_MINIMAL,
                    json={
                        "borne_id": borne_id,
                        "email": c.get("email", ""),
                        "telephone": c.get("telephone", ""),
                        "actif": True,
                    },
                    timeout=TIMEOUT,
                )
        return True
    except Exception:
        return False


def record_paper_history(borne_id, feuilles_restantes):
    """Insère une ligne dans paper_history (1x par jour max)."""
    from datetime import date
    today = date.today().isoformat()
    try:
        r = requests.get(
            _url(f"paper_history?borne_id=eq.{borne_id}&recorded_at=gte.{today}&select=id&limit=1"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200 and r.json():
            return True
        r = requests.post(
            _url("paper_history"),
            headers=HEADERS_MINIMAL,
            json={"borne_id": borne_id, "feuilles_restantes": feuilles_restantes},
            timeout=TIMEOUT,
        )
        return r.status_code in (200, 201)
    except Exception as e:
        print(f"[SUPABASE] record_paper_history error: {e}")
        return False


def get_printer_status_config():
    """Récupère la palette d'erreurs (table printer_status_config)."""
    try:
        r = requests.get(
            _url("printer_status_config?select=*&order=status_code"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def verifier_pin(pin):
    """Vérifie un PIN dans la table utilisateurs. Retourne le dict utilisateur ou None."""
    try:
        r = requests.get(
            _url(f"utilisateurs?pin=eq.{pin}&select=id,nom,role,voir_ca"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200 and r.json():
            return r.json()[0]
    except Exception:
        pass
    return None


def upsert_user_connection(user_id, borne_id):
    """Enregistre qu'un utilisateur s'est connecté sur une borne."""
    try:
        r = requests.post(
            _url("user_connections?on_conflict=user_id,borne_id"),
            headers=HEADERS_UPSERT,
            json={
                "user_id": user_id,
                "borne_id": borne_id,
                "last_seen": __import__("datetime").datetime.now().astimezone().isoformat(),
            },
            timeout=TIMEOUT,
        )
        return r.status_code in (200, 201)
    except Exception as e:
        print(f"[SUPABASE] upsert_user_connection error: {e}")
        return False


def save_printer_status_config(config_id, data):
    """Met à jour la gravité d'un code erreur."""
    try:
        r = requests.patch(
            _url(f"printer_status_config?id=eq.{config_id}"),
            headers=HEADERS_MINIMAL, json=data, timeout=TIMEOUT,
        )
        return r.status_code in (200, 204)
    except Exception:
        return False
