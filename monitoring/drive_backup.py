"""Drive Backup — intégré dans MementoAgent.
Surveille les dossiers dslrBooth et copie les nouvelles photos
vers Google Drive automatiquement."""

import os
import glob
import json
import time
import shutil
import sqlite3
from datetime import datetime

import supabase_client as supa

from .dslrbooth_config import get_dslrbooth_base
DSLRBOOTH_BASE = get_dslrbooth_base()

# Mapping reason interne -> (type d'alerte Supabase, gabarit du message client).
# Le {bar} sera remplace par le nom du bar de la borne.
DRIVE_ALERTS = {
    "local_write_failed": {
        "type": "drive_deconnecte",
        "message": (
            "Google Drive est eteint ou bloque sur {bar}. Les photos ne sont "
            "plus sauvegardees en ligne. Redemarrer l'application Google Drive "
            "sur la borne."
        ),
    },
    "cloud_sync_silently_broken": {
        "type": "drive_sync_cassee",
        "message": (
            "Google Drive ne synchronise plus les photos vers le cloud sur {bar} "
            "— l'application tourne mais les fichiers restent en local. Verifier "
            "la connexion du compte Google sur la borne, il a probablement ete "
            "deconnecte."
        ),
    },
}
DSLRBOOTH_CONFIG = os.path.join(
    os.environ.get("APPDATA", ""), "dslrBooth", "app_settings_2021.json"
)
# dslrBooth renomme sa DB sqlite chaque annee (database_2025.db,
# database_2026.db, ...). On resoud dynamiquement le fichier le plus
# recent pour ne pas casser silencieusement au changement d'annee.
_DSLRBOOTH_DB_MATCHES = sorted(
    glob.glob(os.path.join(os.environ.get("APPDATA", ""), "dslrBooth", "database_*.db")),
    key=os.path.getmtime,
    reverse=True,
)
DSLRBOOTH_DB = _DSLRBOOTH_DB_MATCHES[0] if _DSLRBOOTH_DB_MATCHES else ""

# Vérification fichiers
TAILLE_MIN_ORIGINAL = 100_000   # 100 Ko
TAILLE_MIN_PRINT = 10_000       # 10 Ko

# Health checks Drive
# Niveau A : test ecriture/suppression dans le dossier local — detecte
#            Drive Desktop eteint, lecture-seule, dossier disparu.
# Niveau B : appel API Google Drive — seul moyen de detecter une sync
#            silencieusement cassee (Drive Desktop accepte le local mais
#            ne pousse plus vers le cloud, cas observe sur La Planque
#            29/04 : 42 sessions perdues pendant 60h sans alerte).
HEALTH_CHECK_INTERVAL_SEC = 60
API_HEALTH_CHECK_INTERVAL_SEC = 120  # 2 min (reduit de 5 min : on a un debounce maintenant)

# Debounce avant d'envoyer une vraie alerte (Twilio SMS).
# Sequence : 1ere detection -> log silencieux dans drive.log.
# Re-check >= DRIVE_ALERT_DEBOUNCE_SEC apres + toujours en panne -> vraie alerte
# (SMS + page dashboard). Evite les SMS pour les hiccups transitoires
# (relogin Drive Desktop, basculement reseau, etc.) qui se resolvent seuls.
DRIVE_ALERT_DEBOUNCE_SEC = 300  # 5 minutes

# Fenetre d'age d'un fichier "temoin" pour le check cloud end-to-end :
# - trop frais (< 120s) : Drive Desktop n'a peut-etre pas encore eu le temps
#   de pousser le fichier vers le cloud, faux negatif possible
# - trop vieux (> 1800s) : moins de signal sur l'etat actuel du sync
CLOUD_WITNESS_MIN_AGE_SEC = 120
CLOUD_WITNESS_MAX_AGE_SEC = 1800

# Bug Latina Cafe : sur certaines bornes, les .jpg sont deposes directement
# a la racine de C:\dslrBooth\ au lieu d'un sous-dossier <event>\Originals\.
# On considere qu'un fichier est "persistant a la racine" (= non transitoire,
# ne sera pas move par dslrbooth dans son event) s'il est encore la apres
# RACINE_PERSIST_SEC. L'agent le MOVE alors vers <bar>\Originals\ (ou <bar>
# = nom du bar de la borne), le scanner standard prendra ensuite le relais
# pour l'uploader vers Drive.
RACINE_PERSIST_SEC = 60

# Scope minimal pour le check API (lecture-seule, principe du moindre privilege)
DRIVE_API_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

# Cle JSON du Service Account Google qui fait le health check API.
# Hardcodee ici (repo prive) pour que toutes les bornes — anciennes comme
# nouvelles — l'embarquent automatiquement via auto-update, sans avoir
# besoin d'editer le .env de chaque borne en TeamViewer.
# Override possible via env var GOOGLE_SA_JSON (utile en dev/test).
# Pour la rotation : remplacer la valeur ci-dessous + bump version + release.
# Le scope drive.readonly limite ce qu'un attaquant pourrait faire si l'exe
# fuitait (il pourrait juste LISTER les fichiers des dossiers partages).
_DEFAULT_GOOGLE_SA_JSON = r"""{"type":"service_account","project_id":"memento-monitoring","private_key_id":"6ef56637c9105f9f3e1895e8212caa43fdffc61f","private_key":"-----BEGIN PRIVATE KEY-----\nMIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQDecYuHAhrfec2A\nHK76pxRpYFJqwZo47ZjLGnqIubeoKRD6azl+JtDcTupXlxr0YhlH3emKpwlWqMHG\nyfMxlBYeJDDBn3Onqse53P2io8RDl+Q0McGq9xDPQ2/7o05tmPzHNsqZZskQA1UH\nmOdLY1ScoOKRHAZSUZ/KvYa+fZagUqF6I82TVir5mCzu20n/2DxCnkv+dAdTjFrV\nd2tJozHUSSUVSarlYaMnSZGNcakJSu1AQPH56AVy7kXG8/KzZ8IT7HEkkvHkRGVB\nw4NaEt3qd8HUZiPkTRjdM8n3fs7B6/Wjl/yBrjmfeiOzABS1y49iDWE66dba6dIq\nVDGTXjS/AgMBAAECggEAAJz7hNHCqom2wVBS7dShanDziTZ4wF4XT71bnR418rwP\nlJZ7FW1HTMmC597oxMezHiREd+IMqop945hm7ToP8uFSqRX8HE2M42byjreOMPQt\nkt9C6L++8h3+JF7Hi+ciEJfcEx7aFbXh+XVjHdgWQaBH6kfTf01DotbG6lDaUMgo\nN0ZiLOm3pTk5dICPFqGhJgrIJGOw5nxJO4cikWOYdRcQdHTngAv+cmqs/kB+Sa5G\n2Z8WjO7sMVXQBH7fWV/CcWt7tYJKoQW5IjKZoB30jf3UbfgEh21qh0ocKqFXLop9\nzDm+Kx8L+oc8nZL9l2Ua4YV+gNWHY/S9CpXARlrk0QKBgQD6JDZZXvg968IAldVL\n1ryIo6tMBUqXNY3svMpwh0I2+px+B+jt7A0MQA8n1GuUOpMZl7SlmVnkzSoAZ4IT\nAA3O56ehQqXKd/t1rcBAgZVjoD8NGx+gsRNk3GZJFjlqCKerMCbksQrnLn6m6OrJ\n8/5NHwmcPhVEBbHbcOS0swVSRQKBgQDjp0NATRRllKIzWQDnsRCteUMItHBZMgoq\nWGQbFFTqw6497ir0Th79ScUrAYt06kHwJGJ9d/kqrF8qfGmXjtQRnq0DYII2kKCR\nObQpRMY1Z+fQZ2berDfgWLHvTLcEiY1+Vd0rX3KH8Z8uLdRZUzxWKAh1LARuuLJM\ns5bjsVkdMwKBgGHvaaQGDdVYh8Vo5HDj6z7oLbn+3FxlaGLG68+w9VjHOBwUBruY\nTud78TMb9N69LDi5781iRBLTzN0JqaC8xas7gaMekAC8hyRk2b+nvJCb/fOoqfJl\nQf2cWSPGYsZECzl4CdJCCs3Go2nACaT2NZuGSmH04KiYPjF3euPQr4WtAoGAOKJz\n6JtEZ8ECWSPbRciXDZENTC0XhhkczkwPG22DcqQbxOxrYzvMGdcwZfKMbxmYLdXf\nardeFW+sfTVWT44I1BlVkXGA83Inf/mLCHlDliWzVfVjciIGBJoMKiw7m7VcrgFO\ndGvaYleJ8kMUgORkLkrnT78Tmzf3o31KHHsSYGECgYAj705ybD8xuJgqF85RvPio\nyNHSqa6Ck98t4RAOnT1EoLAWGjaYJK9vwUH6qkprMxYkREVvIuyKJKSOJSiTc9Ds\nTyIZdEF4a/hIseGGbIaepmA+oewIeOhO2XsF1I27vfqmW+NcUhnxPDmbtjsYX/6Z\n97hlBeQybgFTeV4MhJl9oQ==\n-----END PRIVATE KEY-----\n","client_email":"memento-agent-drive-check@memento-monitoring.iam.gserviceaccount.com","client_id":"103153800243120152339","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"https://www.googleapis.com/robot/v1/metadata/x509/memento-agent-drive-check%40memento-monitoring.iam.gserviceaccount.com","universe_domain":"googleapis.com"}"""


def _get_sa_json():
    """Retourne la cle SA — env var d'abord (override), sinon constante.
    Retourne une string vide si non configure (le check niveau B sera skipe)."""
    return os.environ.get("GOOGLE_SA_JSON") or _DEFAULT_GOOGLE_SA_JSON


def _trouver_google_drive():
    """Détecte automatiquement le chemin Google Drive (FR ou EN).

    Couvre 2 modes de Drive Desktop :
      - mode 'stream' : virtual drive monte sur une lettre (G:, H:, ...)
      - mode 'mirror' : sous-dossier dans le profil utilisateur Windows
        C:\\Users\\<user>\\ — observe sur certaines bornes apres un update
        de Drive Desktop qui change le mode par defaut.
    """
    for lettre in "GHIJDEFKLM":
        for nom in ("Mon Drive", "My Drive"):
            chemin = f"{lettre}:\\{nom}"
            if os.path.isdir(chemin):
                return chemin
    user_profile = os.environ.get("USERPROFILE")
    if user_profile:
        for nom in ("Mon Drive", "My Drive"):
            chemin = os.path.join(user_profile, nom)
            if os.path.isdir(chemin):
                return chemin
    return None


def _detecter_tous_evenements():
    """Liste TOUS les sous-dossiers de C:\\dslrBooth\\ qui ont une structure
    d'event (= au moins un sous-dossier Originals\\ ou Prints\\). Exclus les
    dossiers systeme (Settings, Templates).

    Pourquoi tous : l'agent ne peut pas faire confiance a 'l'event courant'
    de dslrbooth pour decider quoi scanner. Cas observes :
      - bornes multi-event qui basculent vite entre soirees
      - rattrapage des fichiers moves a la racine vers <bar>\\Originals\\
        (cf. _scan_racine, bug Latina Cafe) — <bar> n'est jamais l'event
        courant, donc invisible au scanner mono-event
      - sessions en cours dans un ancien dossier event que dslrbooth a oublie
        de marquer comme actif (cas La Planque 2026-04-29)
    """
    events = []
    EXCLUS = {"Settings", "Templates"}
    try:
        for nom in os.listdir(DSLRBOOTH_BASE):
            if nom in EXCLUS:
                continue
            chemin = os.path.join(DSLRBOOTH_BASE, nom)
            if not os.path.isdir(chemin):
                continue
            if (os.path.isdir(os.path.join(chemin, "Originals")) or
                    os.path.isdir(os.path.join(chemin, "Prints"))):
                events.append(nom)
    except Exception:
        pass
    return events


def _detecter_evenement():
    """Lit l'événement actif depuis la config dslrBooth.
    Si la DB est vide ou absente, utilise le dossier le plus récent dans C:\\dslrBooth\\.
    Conserve pour le logging d'event 'principal' uniquement — le scanner traite
    desormais TOUS les events (cf. _detecter_tous_evenements)."""
    event_id = None
    try:
        with open(DSLRBOOTH_CONFIG, "r", encoding="utf-8") as f:
            config = json.load(f)
            event_id = config.get("EventId", "")
    except Exception:
        pass

    # Méthode 1 : chercher dans la DB (versions récentes de dslrBooth)
    if event_id:
        try:
            db_size = os.path.getsize(DSLRBOOTH_DB) if os.path.exists(DSLRBOOTH_DB) else 0
            if db_size > 0:
                conn = sqlite3.connect(DSLRBOOTH_DB)
                cur = conn.cursor()
                cur.execute("SELECT AlbumName FROM FileItems WHERE EventId=? LIMIT 1", (event_id,))
                row = cur.fetchone()
                conn.close()
                if row and row[0]:
                    dossier = os.path.join(DSLRBOOTH_BASE, row[0])
                    if os.path.isdir(dossier):
                        return row[0]
        except Exception:
            pass

    # Méthode 2 : dossier avec les fichiers Prints les plus récents dans C:\dslrBooth\
    EXCLUS = {"Settings", "Templates"}
    try:
        dossiers = []
        for nom in os.listdir(DSLRBOOTH_BASE):
            chemin = os.path.join(DSLRBOOTH_BASE, nom)
            if not os.path.isdir(chemin) or nom in EXCLUS:
                continue
            # Chercher le fichier le plus récent dans Prints
            prints_dir = os.path.join(chemin, "Prints")
            if os.path.isdir(prints_dir):
                try:
                    fichiers = [os.path.join(prints_dir, f) for f in os.listdir(prints_dir)
                                if f.lower().endswith((".jpg", ".jpeg", ".png"))]
                    if fichiers:
                        dernier = max(os.path.getmtime(f) for f in fichiers)
                        dossiers.append((dernier, nom))
                except Exception:
                    pass
        if dossiers:
            dossiers.sort(reverse=True)
            return dossiers[0][1]
    except Exception:
        pass

    return None


def _lister_jpgs(directory, exclure_thumb=False):
    try:
        fichiers = set()
        for f in os.listdir(directory):
            if f.lower().endswith((".jpg", ".jpeg")):
                if exclure_thumb and "thumb" in f.lower():
                    continue
                fichiers.add(f)
        return fichiers
    except Exception:
        return set()


def _lister_jpgs_racine(directory):
    """Liste les .jpg/.jpeg directement a la racine de `directory`, en ignorant
    les sous-dossiers (Settings, Templates, events). En mode standard dslrbooth
    ce set est toujours vide. S'il n'est pas vide -> bornes type Latina Cafe."""
    try:
        fichiers = set()
        for entry in os.listdir(directory):
            full = os.path.join(directory, entry)
            if not os.path.isfile(full):
                continue
            if entry.lower().endswith((".jpg", ".jpeg")):
                fichiers.add(entry)
        return fichiers
    except Exception:
        return set()


def _fichier_valide(path, taille_min):
    if not os.path.exists(path):
        return False
    try:
        taille = os.path.getsize(path)
        return taille >= taille_min
    except Exception:
        return False


def _copier(src, dst):
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return os.path.getsize(src) == os.path.getsize(dst)
    except Exception:
        return False


class DriveBackup:
    """Backup Google Drive — tourne dans le thread de monitoring."""

    def __init__(self, nom_lieu, borne_id=None):
        self._nom_lieu = nom_lieu
        self._borne_id = borne_id
        self._drive_base = None
        self._events = {}  # event_name → {"originals": set, "prints": set}
        self._current_event = None
        self._total_copies = 0
        self._start_time = time.time()  # Ne copier que les fichiers créés après ce moment

        # Health checks
        self._last_local_check_ts = 0.0
        self._last_api_check_ts = 0.0
        self._drive_root_folder_id = None  # cache, resolu via API au 1er check B

        # Debounce : timestamp de la 1ere detection d'echec, None si tout va bien.
        # Une alerte ne fire qu'une fois que la panne persiste > DRIVE_ALERT_DEBOUNCE_SEC.
        self._local_first_failure_ts = None
        self._cloud_first_failure_ts = None

        # Scan racine (bug Latina Cafe) : pour chaque .jpg vu a la racine,
        # on note l'instant de la 1ere observation. Si le fichier persiste
        # > RACINE_PERSIST_SEC, c'est qu'il ne sera pas move par dslrbooth
        # -> on le DEPLACE en local vers <RACINE_FALLBACK_EVENT>/Originals/
        # et le scanner standard l'upload ensuite vers Drive.
        self._racine_seen_at = {}  # filename -> first_seen_ts

        self._init_drive()

    def _init_drive(self):
        drive = _trouver_google_drive()
        if not drive:
            print("[DRIVE] Google Drive non détecté")
            import activity_logger as alog
            alog.log_drive_inaccessible()
            alog.ui_log("Google Drive inaccessible")
            # Debounce : on log mais on n'alerte pas immediatement
            self._on_local_failure()
            return
        # Construire le chemin specifique de cette borne et tester l'ecriture
        # SUR CE CHEMIN (pas sur la racine). Si le sous-dossier est en lecture
        # seule alors que la racine ecrit, on detecte ici la difference.
        drive_base = os.path.join(drive, "dslrBooth", self._nom_lieu)
        try:
            os.makedirs(drive_base, exist_ok=True)
            test_path = os.path.join(drive_base, ".memento_test")
            with open(test_path, "w") as f:
                f.write("test")
            os.remove(test_path)
        except Exception as e:
            print(f"[DRIVE] {drive_base} en lecture seule ou inaccessible: {e}")
            import activity_logger as alog
            alog.ui_log("Google Drive déconnecté ou en lecture seule")
            self._on_local_failure()
            return
        # Tout OK — résoudre l'alerte si elle était ouverte + reset debounce
        self._drive_base = drive_base
        self._on_local_success()
        print(f"[DRIVE] Base: {self._drive_base}")

    # --- Debounce helpers : evitent les SMS pour les hiccups transitoires ----

    def _on_local_failure(self):
        """Une detection d'echec local. La 1ere fois : log silencieux, pas
        d'alerte. Si persiste > DRIVE_ALERT_DEBOUNCE_SEC : vraie alerte."""
        now = time.time()
        if self._local_first_failure_ts is None:
            self._local_first_failure_ts = now
            try:
                import activity_logger as alog
                alog.log_generic(
                    "DRIVE",
                    f"Health check local FAIL #1 — debounce {DRIVE_ALERT_DEBOUNCE_SEC}s avant alerte",
                )
            except Exception:
                pass
        elif now - self._local_first_failure_ts >= DRIVE_ALERT_DEBOUNCE_SEC:
            try:
                import activity_logger as alog
                alog.log_generic(
                    "DRIVE",
                    "Health check local FAIL persistant — alerte declenchee",
                )
            except Exception:
                pass
            self._creer_alerte_drive("local_write_failed")

    def _on_local_success(self):
        """Le local marche. Reset le debounce et resoud l'alerte si ouverte."""
        if self._local_first_failure_ts is not None:
            try:
                import activity_logger as alog
                alog.log_generic("DRIVE", "Health check local OK — debounce reset")
            except Exception:
                pass
        self._local_first_failure_ts = None
        self._resoudre_alerte_drive("local_write_failed")

    def _on_cloud_failure(self):
        """Une detection d'echec cloud (sync silencieusement cassee). 1ere fois :
        log silencieux. Si persiste > DRIVE_ALERT_DEBOUNCE_SEC : vraie alerte."""
        now = time.time()
        if self._cloud_first_failure_ts is None:
            self._cloud_first_failure_ts = now
            try:
                import activity_logger as alog
                alog.log_generic(
                    "DRIVE",
                    f"Health check cloud FAIL #1 — debounce {DRIVE_ALERT_DEBOUNCE_SEC}s avant alerte",
                )
            except Exception:
                pass
        elif now - self._cloud_first_failure_ts >= DRIVE_ALERT_DEBOUNCE_SEC:
            try:
                import activity_logger as alog
                alog.log_generic(
                    "DRIVE",
                    "Health check cloud FAIL persistant — alerte declenchee",
                )
            except Exception:
                pass
            self._creer_alerte_drive("cloud_sync_silently_broken")

    def _on_cloud_success(self):
        """Le cloud marche. Reset le debounce et resoud l'alerte si ouverte."""
        if self._cloud_first_failure_ts is not None:
            try:
                import activity_logger as alog
                alog.log_generic("DRIVE", "Health check cloud OK — debounce reset")
            except Exception:
                pass
        self._cloud_first_failure_ts = None
        self._resoudre_alerte_drive("cloud_sync_silently_broken")

    def _creer_alerte_drive(self, reason="local_write_failed"):
        """Cree l'alerte correspondant a `reason` si pas deja ouverte en base.

        La deduplication est assuree par _alerte_deja_ouverte() qui consulte
        Supabase — la source unique de verite. Pas de flag local : un flag
        bloquerait la re-creation apres une resolution externe (admin manuel
        ou bug de fausse resolution).

        reasons supportees :
          - 'local_write_failed' -> alerte drive_deconnecte
          - 'cloud_sync_silently_broken' -> alerte drive_sync_cassee
        """
        if not self._borne_id:
            return
        spec = DRIVE_ALERTS.get(reason)
        if not spec:
            print(f"[DRIVE] reason inconnu: {reason}")
            return
        try:
            from monitoring.alertes.alertes_monitor import _creer_alerte, _alerte_deja_ouverte
            if _alerte_deja_ouverte(self._borne_id, spec["type"]):
                return
            bar = self._nom_lieu.split(" (")[0] if " (" in self._nom_lieu else self._nom_lieu
            _creer_alerte(
                self._borne_id, spec["type"], "drive",
                spec["message"].format(bar=bar),
                "warning",
            )
        except Exception as e:
            print(f"[DRIVE] Erreur creation alerte: {e}")

    def _resoudre_alerte_drive(self, reason=None):
        """Resout l'alerte associee a `reason`. Si reason est None, resout les
        deux types (utilise au demarrage / reconnexion globale)."""
        if not self._borne_id:
            return
        if reason is None:
            types = [spec["type"] for spec in DRIVE_ALERTS.values()]
        else:
            spec = DRIVE_ALERTS.get(reason)
            if not spec:
                return
            types = [spec["type"]]
        try:
            from monitoring.alertes.alertes_monitor import _resoudre_alertes
            _resoudre_alertes(self._borne_id, types)
        except Exception:
            pass

    # --- Health checks ----------------------------------------------------

    def _drive_writable_local(self):
        """Niveau A : test ecriture/suppression d'un fichier sentinelle dans
        le sous-dossier de cette borne. Detecte les pannes filesystem
        (Drive Desktop eteint, dossier disparu, permissions cassees).
        Ne detecte PAS le cas 'sync silencieusement cassee' (cf. niveau B)."""
        if not self._drive_base or not os.path.isdir(self._drive_base):
            return False
        sentinel = os.path.join(self._drive_base, ".memento_health")
        try:
            with open(sentinel, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(sentinel)
            return True
        except Exception as e:
            print(f"[DRIVE] Health check local FAIL: {e}")
            return False

    def _find_witness_file(self):
        """Cherche un fichier 'temoin' local pour le check end-to-end : un
        .jpg present dans <drive_base>/.../Originals/ ou /Prints/ dont le
        mtime est dans [CLOUD_WITNESS_MIN_AGE_SEC, CLOUD_WITNESS_MAX_AGE_SEC].

        Pourquoi cette fenetre :
        - Trop frais (< 2 min) : Drive Desktop n'a peut-etre pas eu le temps
          de pousser le fichier vers le cloud, faux negatif possible.
        - Trop vieux (> 30 min) : ne reflete pas l'etat actuel du sync.

        Retourne le nom du fichier (basename) ou None si rien a verifier.
        """
        if not self._drive_base or not os.path.isdir(self._drive_base):
            return None
        now = time.time()
        min_mtime = now - CLOUD_WITNESS_MAX_AGE_SEC
        max_mtime = now - CLOUD_WITNESS_MIN_AGE_SEC
        try:
            for root, _dirs, files in os.walk(self._drive_base):
                for f in files:
                    if not f.lower().endswith((".jpg", ".jpeg", ".png")):
                        continue
                    try:
                        mtime = os.path.getmtime(os.path.join(root, f))
                    except OSError:
                        continue
                    if min_mtime <= mtime <= max_mtime:
                        return f
        except Exception:
            pass
        return None

    def _drive_api_check(self):
        """Niveau B (vrai test end-to-end) : verifie qu'un fichier .jpg local
        recent est bien present dans le cloud Drive via l'API du Service
        Account. Si oui = sync OK. Si non = sync silencieusement cassee
        (Drive Desktop accepte les ecritures locales mais ne pousse plus
        vers le cloud — scenario observe sur La Planque / Comptoir des copains).

        Le SA doit avoir un acces 'Lecteur' sur le dossier
        Mon Drive/dslrBooth/<nom_lieu>/ partage manuellement.

        Retourne :
          - True  : fichier temoin trouve a la fois en local ET dans le cloud
          - False : fichier temoin present en local mais absent du cloud
                    (= sync casse)
          - None  : pas de fichier temoin a verifier (borne inactive recemment),
                    ou config SA absente, ou libs google absentes, ou exception
                    sur l'appel API — on n'a pas l'info, on skip gracieusement.
        """
        sa_json_str = _get_sa_json()
        if not sa_json_str:
            return None
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            return None

        witness_name = self._find_witness_file()
        if not witness_name:
            # Pas de fichier .jpg recent (entre 2 et 30 min) — rien a verifier.
            # Soit la borne est inactive, soit on vient de demarrer. On skip
            # silencieusement (ne reset PAS le debounce — un eventuel echec
            # en cours reste actif).
            return None

        try:
            creds = service_account.Credentials.from_service_account_info(
                json.loads(sa_json_str),
                scopes=DRIVE_API_SCOPES,
            )
            service = build("drive", "v3", credentials=creds, cache_discovery=False)

            # Query Drive API pour le fichier temoin par nom exact, scope SA
            # (limite a tout ce que le SA peut voir = sous-arbre <nom_lieu>).
            # Si le sync marche, le fichier doit avoir ete pousse vers le cloud
            # et donc etre listable via l'API.
            results = service.files().list(
                q=f"name='{witness_name}' and trashed=false",
                pageSize=1,
                fields="files(id,name)",
                supportsAllDrives=False,
                includeItemsFromAllDrives=False,
            ).execute()
            if results.get("files"):
                return True
            print(
                f"[DRIVE] Health check API FAIL: fichier temoin '{witness_name}' "
                f"present en local mais introuvable dans le cloud"
            )
            return False
        except Exception as e:
            print(f"[DRIVE] Health check API erreur: {e}")
            # Exception sur l'appel API : on ne sait pas si c'est cassee ou
            # juste un blip reseau. On skip et on garde le debounce en cours
            # (si y'en a un). N'augmente PAS le compteur d'echec.
            return None

    def _resolve_root_folder_id(self, service):
        """Cherche le folder Drive 'dslrBooth/<nom_lieu>' partage avec le SA.
        Retourne son folder_id ou None si pas trouve / pas partage."""
        try:
            results = service.files().list(
                q=(
                    f"name='{self._nom_lieu}' and "
                    f"mimeType='application/vnd.google-apps.folder' and "
                    f"trashed=false"
                ),
                pageSize=10,
                fields="files(id,name)",
                supportsAllDrives=False,
                includeItemsFromAllDrives=False,
            ).execute()
            files = results.get("files", [])
            if not files:
                print(f"[DRIVE] Aucun folder '{self._nom_lieu}' partage avec le SA")
                return None
            # Si plusieurs (ne devrait pas arriver), on prend le premier
            return files[0]["id"]
        except Exception as e:
            print(f"[DRIVE] Erreur resolution root folder: {e}")
            return None

    # --- Rattrapage fichiers racine C:\dslrBooth\ (bug Latina Cafe) ------

    def _scan_racine(self):
        """Sur les bornes en mode anormal (cas Latina Cafe), dslrbooth depose
        les .jpg directement a la racine de C:\\dslrBooth\\ au lieu d'un
        sous-dossier <event>\\Originals\\. Le code legacy ne les voyait jamais.

        Strategie silencieuse : pour chaque .jpg vu a la racine, on note
        l'instant. Si le fichier persiste plus de RACINE_PERSIST_SEC (= il
        n'a pas ete move par dslrbooth, donc on est dans le cas anormal),
        on le DEPLACE vers `C:\\dslrBooth\\<RACINE_FALLBACK_EVENT>\\Originals\\`.

        Le scanner standard (via _detecter_evenement + _scanner) prendra
        ensuite le relais pour uploader le fichier vers Drive normalement.
        Pas d'alerte : c'est un fix transparent."""
        if not self._drive_base:
            return

        actuels = _lister_jpgs_racine(DSLRBOOTH_BASE)
        now = time.time()

        # Oublier les fichiers qui ont disparu (dslrbooth les a moves
        # = ils etaient transitoires sur une borne en mode standard)
        for f in list(self._racine_seen_at.keys()):
            if f not in actuels:
                self._racine_seen_at.pop(f)

        # Noter les nouveaux a leur 1ere apparition
        for f in actuels:
            if f not in self._racine_seen_at:
                self._racine_seen_at[f] = now

        # Move les fichiers persistants vers <bar>\Originals\ (= meme convention
        # que dslrbooth normal, ou le nom du bar est l'event)
        bar = self._nom_lieu.split(" (")[0] if " (" in self._nom_lieu else self._nom_lieu
        target_dir = os.path.join(DSLRBOOTH_BASE, bar, "Originals")
        moves = 0
        for f, first_seen in list(self._racine_seen_at.items()):
            if now - first_seen < RACINE_PERSIST_SEC:
                continue
            src = os.path.join(DSLRBOOTH_BASE, f)
            try:
                if os.path.getmtime(src) < self._start_time:
                    self._racine_seen_at.pop(f)  # pre-existant, on n'y touche pas
                    continue
            except OSError:
                self._racine_seen_at.pop(f)
                continue
            if not _fichier_valide(src, TAILLE_MIN_ORIGINAL):
                continue
            try:
                os.makedirs(target_dir, exist_ok=True)
                dst = os.path.join(target_dir, f)
                if os.path.exists(dst):
                    # Collision (ne devrait pas arriver vu que dslrbooth
                    # genere des noms uniques). Skip pour ne rien ecraser.
                    self._racine_seen_at.pop(f)
                    continue
                shutil.move(src, dst)
                self._racine_seen_at.pop(f)
                moves += 1
            except Exception as e:
                print(f"[DRIVE] Erreur move {f} -> {target_dir}: {e}")

        if moves:
            print(
                f"[DRIVE] {moves} fichier(s) racine moves vers "
                f"{bar}/Originals/ (le scanner les uploadera)"
            )

    # --- Tick principal ---------------------------------------------------

    def tick(self):
        """Cycle de monitoring Drive (appele toutes les ~60s par engine.run)."""
        if not self._drive_base:
            self._init_drive()
            if not self._drive_base:
                return

        now = time.time()

        # Niveau A : ecriture locale toutes les HEALTH_CHECK_INTERVAL_SEC
        if now - self._last_local_check_ts >= HEALTH_CHECK_INTERVAL_SEC:
            # DEBUG : delta reel entre 2 checks (detecte les tick stretches dus
            # a CPU starvation, blocage Supabase, etc.)
            delta = now - self._last_local_check_ts if self._last_local_check_ts else 0
            self._last_local_check_ts = now
            writable = self._drive_writable_local()
            if not writable:
                elapsed = (now - self._local_first_failure_ts) if self._local_first_failure_ts else 0
                try:
                    import activity_logger as alog
                    alog.log_generic(
                        "DRIVE",
                        f"DEBUG local check #{int(now)} : FAIL "
                        f"(delta_tick={delta:.1f}s, elapsed_failure={elapsed:.1f}s, "
                        f"debounce={DRIVE_ALERT_DEBOUNCE_SEC}s)",
                    )
                except Exception:
                    pass
                # _on_local_failure gere le debounce : 1ere fois = log silencieux,
                # apres DRIVE_ALERT_DEBOUNCE_SEC de panne persistante = vraie alerte.
                self._on_local_failure()
                # Si l'alerte a vraiment ete creee (debounce expire), on reset
                # drive_base pour forcer un re-init au prochain tick.
                if (self._local_first_failure_ts is not None and
                        now - self._local_first_failure_ts >= DRIVE_ALERT_DEBOUNCE_SEC):
                    self._drive_base = None
                    return
            else:
                try:
                    import activity_logger as alog
                    alog.log_generic(
                        "DRIVE",
                        f"DEBUG local check #{int(now)} : OK (delta_tick={delta:.1f}s)",
                    )
                except Exception:
                    pass
                # Local OK -> reset debounce + resout l'alerte si ouverte
                self._on_local_success()

        # Niveau B : appel API toutes les API_HEALTH_CHECK_INTERVAL_SEC
        if now - self._last_api_check_ts >= API_HEALTH_CHECK_INTERVAL_SEC:
            delta_api = now - self._last_api_check_ts if self._last_api_check_ts else 0
            self._last_api_check_ts = now
            api_ok = self._drive_api_check()
            elapsed_cloud = (now - self._cloud_first_failure_ts) if self._cloud_first_failure_ts else 0
            try:
                import activity_logger as alog
                alog.log_generic(
                    "DRIVE",
                    f"DEBUG cloud check #{int(now)} : api_ok={api_ok} "
                    f"(delta_tick={delta_api:.1f}s, elapsed_failure={elapsed_cloud:.1f}s)",
                )
            except Exception:
                pass
            if api_ok is False:
                # Vrai echec : fichier temoin local present mais absent du cloud.
                # Debounce 5 min avant la vraie alerte (Twilio SMS).
                self._on_cloud_failure()
                # Ne pas reset _drive_base : on continue a copier en local
                # en attendant que le cloud reparte.
            elif api_ok is True:
                # Vrai succes : fichier temoin trouve en local ET dans le cloud.
                self._on_cloud_success()
            # api_ok is None -> SA non configure, pas de fichier temoin recent,
            # ou exception API : on n'a pas l'info, on ne touche pas au debounce
            # en cours (un echec persistant continue de courir).

        # Rattrapage des fichiers a la racine de C:\dslrBooth\ (bug Latina Cafe)
        self._scan_racine()

        # Scanner TOUS les events presents sur disque (pas juste le courant).
        # cf. _detecter_tous_evenements pour le pourquoi.
        events = _detecter_tous_evenements()
        if not events:
            return

        principal = _detecter_evenement()
        if principal and principal != self._current_event:
            print(f"[DRIVE] Événement: {principal}")
            import activity_logger as alog
            alog.log_drive_event(principal)
            alog.ui_log(f"Nouvel événement détecté: {principal}")
            self._current_event = principal

        for event in events:
            if event not in self._events:
                self._init_event(event)
            if event in self._events:
                try:
                    self._scanner(event)
                except Exception as e:
                    print(f"[DRIVE] Erreur scan {event}: {e}")

    def _init_event(self, event_name):
        """Initialise le suivi. Ne copie que les fichiers créés après le démarrage de l'agent."""
        orig_local = os.path.join(DSLRBOOTH_BASE, event_name, "Originals")
        prints_local = os.path.join(DSLRBOOTH_BASE, event_name, "Prints")
        drive_orig = os.path.join(self._drive_base, event_name, "Originals")
        drive_prints = os.path.join(self._drive_base, event_name, "Prints")

        try:
            os.makedirs(drive_orig, exist_ok=True)
            os.makedirs(drive_prints, exist_ok=True)
        except Exception as e:
            print(f"[DRIVE] Erreur création dossiers: {e}")
            return

        # Lister les fichiers locaux (tous) pour le suivi
        local_orig = _lister_jpgs(orig_local)
        local_prints = _lister_jpgs(prints_local, exclure_thumb=True)

        # Copier uniquement les fichiers manquants dans le Drive ET créés après le démarrage
        drive_orig_set = _lister_jpgs(drive_orig)
        drive_prints_set = _lister_jpgs(drive_prints, exclure_thumb=True)
        manquants_orig = local_orig - drive_orig_set
        manquants_prints = local_prints - drive_prints_set

        nb = 0
        for f in sorted(manquants_orig):
            src = os.path.join(orig_local, f)
            if os.path.getmtime(src) >= self._start_time and _fichier_valide(src, TAILLE_MIN_ORIGINAL):
                if _copier(src, os.path.join(drive_orig, f)):
                    nb += 1
        for f in sorted(manquants_prints):
            src = os.path.join(prints_local, f)
            if os.path.getmtime(src) >= self._start_time and _fichier_valide(src, TAILLE_MIN_PRINT):
                if _copier(src, os.path.join(drive_prints, f)):
                    nb += 1

        if nb:
            print(f"[DRIVE] Copie {event_name}: {nb} nouveau(x) fichier(s)")

        self._events[event_name] = {
            "originals": local_orig,
            "prints": local_prints,
        }
        self._total_copies += nb

    def _scanner(self, event_name):
        """Scanne les nouveaux fichiers et les copie vers Drive."""
        etat = self._events[event_name]
        orig_local = os.path.join(DSLRBOOTH_BASE, event_name, "Originals")
        prints_local = os.path.join(DSLRBOOTH_BASE, event_name, "Prints")
        drive_orig = os.path.join(self._drive_base, event_name, "Originals")
        drive_prints = os.path.join(self._drive_base, event_name, "Prints")

        actuels_orig = _lister_jpgs(orig_local)
        actuels_prints = _lister_jpgs(prints_local, exclure_thumb=True)

        nouveaux_orig = actuels_orig - etat["originals"]
        nouveaux_prints = actuels_prints - etat["prints"]

        if not nouveaux_orig and not nouveaux_prints:
            return

        import activity_logger as alog
        for f in sorted(nouveaux_orig):
            src = os.path.join(orig_local, f)
            dst = os.path.join(drive_orig, f)
            if _fichier_valide(src, TAILLE_MIN_ORIGINAL):
                if _copier(src, dst):
                    etat["originals"].add(f)
                    self._total_copies += 1
                else:
                    alog.log_drive_error(f, src, dst, "Copie échouée")
                    alog.ui_log(f"Erreur copie Drive: {f}")

        for f in sorted(nouveaux_prints):
            src = os.path.join(prints_local, f)
            dst = os.path.join(drive_prints, f)
            if _fichier_valide(src, TAILLE_MIN_PRINT):
                if _copier(src, dst):
                    etat["prints"].add(f)
                    self._total_copies += 1
                else:
                    alog.log_drive_error(f, src, dst, "Copie échouée")
                    alog.ui_log(f"Erreur copie Drive: {f}")
