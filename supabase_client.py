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
DASHBOARD_URL = (
    os.environ.get("DASHBOARD_URL")
    or _env.get("DASHBOARD_URL")
    or "https://dashboard.mementobooth.fr"
).rstrip("/")
AGENT_API_TOKEN = os.environ.get("AGENT_API_TOKEN") or _env.get("AGENT_API_TOKEN", "")

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

# --- Session HTTP globale avec auto-reset ---------------------------------
# Pourquoi : quand la connexion reseau tombe pendant plusieurs heures (observe
# Parc Ohlain / MB-50 entre 20h30-9h30), le pool de sockets interne de
# `requests` garde des connexions mortes. Les requetes suivantes timeout
# silencieusement, meme quand le reseau revient. L'agent continue de tourner
# (logs locaux OK, ticks alive) mais tous ses POST/GET Supabase echouent, donc
# plus aucun heartbeat ni alerte n'arrive en base — et le verify_pin refuse
# le bon code parce que la requete /utilisateurs timeout. On centralise ici
# une Session unique, et on la recree apres N echecs reseau consecutifs.
import threading
_session = requests.Session()
_session_lock = threading.Lock()  # protege _session + _consec_failures
_consec_failures = 0
_RESET_THRESHOLD = 3


def _reset_session_locked():
    """Doit etre appele avec _session_lock deja detenu."""
    global _session, _consec_failures
    try:
        _session.close()
    except Exception:
        pass
    _session = requests.Session()
    _consec_failures = 0
    print(f"[SUPABASE] Pool HTTP reset ({_RESET_THRESHOLD} echecs consecutifs)")


def _call(method, url, **kw):
    """Wrapper autour de _session qui compte les echecs reseau et reset le
    pool apres _RESET_THRESHOLD timeouts/connection errors consecutifs.
    Les status HTTP (401/400/500) ne comptent PAS comme echec reseau — ce
    n'est pas le pool qui est mort, c'est le serveur qui refuse.

    Multi-thread : MonitoringEngine (QThread), code_pool/drive_backup
    (daemons), UI principale, main._create_borne tapent tous Supabase en
    parallele. Le lock protege contre un swap de session pendant qu'un
    autre thread est en plein appel (sockets arraches)."""
    global _consec_failures
    with _session_lock:
        sess = _session
    try:
        r = getattr(sess, method)(url, **kw)
        with _session_lock:
            _consec_failures = 0
        return r
    except requests.exceptions.RequestException as e:
        # Couvre Timeout, ConnectionError, ChunkedEncodingError, SSLError,
        # ContentDecodingError, RetryError — tout echec de transport. HTTP
        # 4xx/5xx n'est PAS une exception requests, donc pas compte.
        if not isinstance(e, (requests.Timeout, requests.ConnectionError,
                              requests.exceptions.ChunkedEncodingError,
                              requests.exceptions.ContentDecodingError,
                              requests.exceptions.RetryError,
                              requests.exceptions.SSLError)):
            raise
        with _session_lock:
            _consec_failures += 1
            if _consec_failures >= _RESET_THRESHOLD:
                _reset_session_locked()
        raise


def http_get(url, **kw):
    return _call("get", url, **kw)


def http_post(url, **kw):
    return _call("post", url, **kw)


def http_patch(url, **kw):
    return _call("patch", url, **kw)


def http_delete(url, **kw):
    return _call("delete", url, **kw)


def _url(endpoint):
    return f"{SUPABASE_URL}/rest/v1/{endpoint}"


def get_borne():
    """Identifie la borne via le hostname. Retourne le dict complet ou None."""
    hostname = socket.gethostname()
    try:
        r = _call("get",
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
        r = _call("get",
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
        r = _call("post",
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
                _call("post",
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
        r = _call("get",
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
        r = _call("get",
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
        r_ins = _call("post",
            _url("horaires"),
            headers=HEADERS_MINIMAL, json=rows, timeout=TIMEOUT,
        )
        if r_ins.status_code in (200, 201):
            # INSERT OK → supprimer les anciens (ceux qui ne sont pas dans les nouveaux IDs)
            _call("delete",
                _url(f"horaires?borne_id=eq.{borne_id}"),
                headers=HEADERS_MINIMAL, timeout=TIMEOUT,
            )
            # Réinsérer proprement
            _call("post",
                _url("horaires"),
                headers=HEADERS_MINIMAL, json=rows, timeout=TIMEOUT,
            )
            return True
        else:
            print(f"[SUPABASE] insert horaires: {r_ins.status_code} {r_ins.text[:200]}")
            # Fallback : DELETE + INSERT classique
            _call("delete",
                _url(f"horaires?borne_id=eq.{borne_id}"),
                headers=HEADERS_MINIMAL, timeout=TIMEOUT,
            )
            r2 = _call("post",
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
        r = _call("patch",
            _url(f"bornes?id=eq.{borne_id}"),
            headers=HEADERS_MINIMAL, json=data, timeout=TIMEOUT,
        )
        return r.status_code in (200, 204)
    except Exception:
        return False


def supabase_patch_heartbeat(borne_id, data):
    """Met à jour un champ du heartbeat (ex: mode_coupe)."""
    try:
        r = _call("patch",
            _url(f"heartbeats?borne_id=eq.{borne_id}"),
            headers=HEADERS_MINIMAL, json=data, timeout=TIMEOUT,
        )
        return r.status_code in (200, 204)
    except Exception:
        return False


def get_alertes(borne_id, limit=50):
    """Récupère toutes les alertes récentes de la borne (pour la page alertes)."""
    try:
        r = _call("get",
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
        r = _call("get",
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
        r = _call("get",
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
        r = _call("get",
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
        r = _call("get",
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


def _get_borne_environnement(borne_id):
    """Lit le canal de mise a jour ('prod' ou 'dev') de la borne dans Supabase.
    Defaut 'prod' si la borne n'existe pas, si la requete echoue ou si la
    valeur est invalide."""
    if not borne_id:
        return "prod"
    try:
        r = _call("get",
            _url(f"bornes?id=eq.{borne_id}&select=environnement"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200 and r.json():
            env = r.json()[0].get("environnement")
            if env in ("prod", "dev"):
                return env
    except Exception:
        pass
    return "prod"


def _fetch_dashboard_release(channel):
    if not DASHBOARD_URL:
        return None
    headers = {}
    if AGENT_API_TOKEN:
        headers["Authorization"] = f"Bearer {AGENT_API_TOKEN}"
    try:
        r = _call("get",
            f"{DASHBOARD_URL}/api/agent/release/{channel}",
            headers=headers,
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            print(f"[MAJ] Dashboard {channel} HTTP {r.status_code}: {r.text[:120]}")
            return None
        return r.json()
    except Exception as e:
        print(f"[MAJ] Dashboard {channel} erreur: {e}")
        return None


def _fetch_github_release_fallback():
    """Fallback : appel direct GitHub /releases/latest si le dashboard est
    injoignable. Ne tape que les releases full (pas de pre-release) — donc
    se comporte comme le canal 'prod'."""
    if not GITHUB_TOKEN:
        return None
    try:
        r = _call("get",
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
        for asset in release.get("assets", []):
            if asset["name"].endswith(".exe"):
                return {
                    "version": release.get("tag_name", "").lstrip("v"),
                    "download_url": asset["url"],
                    "filename": asset["name"],
                    "notes": release.get("body", ""),
                    "channel": "prod",
                }
    except Exception:
        pass
    return None


def get_latest_release(borne_id=None):
    """Recupere la derniere release pour cette borne via le dashboard,
    selon son canal (`bornes.environnement` dans Supabase).

    Retour identique a l'ancien `get_latest_github_release` :
        {version, download_url, filename, notes}
    + champ `channel` ('prod'/'dev') pour le diagnostic.

    Fallback automatique sur GitHub /releases/latest (= canal 'prod')
    si le dashboard est injoignable ou non configure."""
    channel = _get_borne_environnement(borne_id)
    data = _fetch_dashboard_release(channel)
    if data:
        asset = data.get("asset") or {}
        return {
            "version": data.get("version", ""),
            "download_url": asset.get("downloadUrl", ""),
            "filename": asset.get("name", ""),
            "notes": data.get("notes", ""),
            "channel": data.get("channel", channel),
        }
    # Fallback GitHub direct (toujours canal prod)
    print(f"[MAJ] Fallback GitHub direct (canal={channel} -> prod)")
    return _fetch_github_release_fallback()


def get_utilisateurs():
    """Récupère les utilisateurs."""
    try:
        r = _call("get",
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
        r = _call("get",
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
        _call("delete",
            _url(f"alerte_destinataires?borne_id=eq.{borne_id}"),
            headers=HEADERS_MINIMAL, timeout=TIMEOUT,
        )
        # Insérer les nouveaux
        for c in contacts:
            if c.get("telephone") or c.get("email"):
                _call("post",
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
        r = _call("get",
            _url(f"paper_history?borne_id=eq.{borne_id}&recorded_at=gte.{today}&select=id&limit=1"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200 and r.json():
            return True
        r = _call("post",
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
        r = _call("get",
            _url("printer_status_config?select=*&order=status_code"),
            headers=HEADERS, timeout=TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []


def verifier_pin(pin):
    """Vérifie un PIN dans la table utilisateurs. Retourne le dict utilisateur ou None.

    v1.0.28.27 : instrumentation activity_logger pour diagnostiquer les
    refus PIN inexpliques (La Faluche 10/11 : PIN en base + curl OK depuis
    la machine, mais le process agent refuse). Chaque appel loggue dans
    alertes.log : duree du fetch, status HTTP, nb de users matches, retry
    apres reset session si timeout."""
    import time as _t
    pin_log = (pin[:2] + "****") if len(pin) >= 2 else "****"
    for attempt in (1, 2):
        t0 = _t.time()
        try:
            r = _call("get",
                _url(f"utilisateurs?pin=eq.{pin}&select=id,nom,is_admin,voir_ca"),
                headers=HEADERS, timeout=TIMEOUT,
            )
            dur_ms = int((_t.time() - t0) * 1000)
            users = r.json() if r.status_code == 200 else None
            n = len(users) if isinstance(users, list) else -1
            try:
                import activity_logger as alog
                alog.log_generic(
                    "AUTH",
                    f"verifier_pin({pin_log}) attempt={attempt} "
                    f"status={r.status_code} match={n} dur={dur_ms}ms",
                )
            except Exception:
                pass
            if r.status_code == 200 and users:
                user = users[0]
                user["role"] = "admin" if user.get("is_admin") else "technicien"
                return user
            # Status 2xx mais 0 user → PIN vraiment incorrect, pas la peine
            # de retry.
            if r.status_code == 200:
                return None
            # Status != 2xx : probleme serveur, on retente apres reset session
            if attempt == 1:
                try:
                    import activity_logger as alog
                    alog.log_generic(
                        "AUTH",
                        f"verifier_pin FAIL status={r.status_code} -> reset session + retry",
                    )
                except Exception:
                    pass
                with _session_lock:
                    _reset_session_locked()
                continue
            return None
        except requests.exceptions.RequestException as e:
            dur_ms = int((_t.time() - t0) * 1000)
            try:
                import activity_logger as alog
                alog.log_generic(
                    "AUTH",
                    f"verifier_pin({pin_log}) attempt={attempt} "
                    f"EXCEPTION {type(e).__name__}: {e} dur={dur_ms}ms",
                )
            except Exception:
                pass
            # Reseau mort : reset session + retry une fois
            if attempt == 1:
                with _session_lock:
                    _reset_session_locked()
                continue
            return None
        except Exception as e:
            try:
                import activity_logger as alog
                alog.log_generic("AUTH", f"verifier_pin UNEXPECTED {type(e).__name__}: {e}")
            except Exception:
                pass
            return None
    return None


def upsert_user_connection(user_id, borne_id):
    """Enregistre qu'un utilisateur s'est connecté sur une borne."""
    try:
        r = _call("post",
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
        r = _call("patch",
            _url(f"printer_status_config?id=eq.{config_id}"),
            headers=HEADERS_MINIMAL, json=data, timeout=TIMEOUT,
        )
        return r.status_code in (200, 204)
    except Exception:
        return False
