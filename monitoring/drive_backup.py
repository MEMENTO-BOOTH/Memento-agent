"""Drive Backup — intégré dans MementoAgent.
Surveille les dossiers dslrBooth et copie les nouvelles photos
vers Google Drive automatiquement."""

import os
import json
import time
import shutil
import sqlite3
from datetime import datetime

import supabase_client as supa

DSLRBOOTH_BASE = r"C:\dslrBooth"

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
DSLRBOOTH_DB = os.path.join(
    os.environ.get("APPDATA", ""), "dslrBooth", "database_2025.db"
)

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
API_HEALTH_CHECK_INTERVAL_SEC = 300

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
_DEFAULT_GOOGLE_SA_JSON = ""  # ← coller ici le contenu JSON du SA, sur 1 ligne


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


def _detecter_evenement():
    """Lit l'événement actif depuis la config dslrBooth.
    Si la DB est vide ou absente, utilise le dossier le plus récent dans C:\\dslrBooth\\."""
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

        self._init_drive()

    def _init_drive(self):
        drive = _trouver_google_drive()
        if not drive:
            print("[DRIVE] Google Drive non détecté")
            import activity_logger as alog
            alog.log_drive_inaccessible()
            alog.ui_log("Google Drive inaccessible")
            self._creer_alerte_drive()
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
            self._creer_alerte_drive()
            return
        # Tout OK — résoudre l'alerte si elle était ouverte
        self._drive_base = drive_base
        self._resoudre_alerte_drive()
        print(f"[DRIVE] Base: {self._drive_base}")

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

    def _drive_api_check(self):
        """Niveau B : appel API Google Drive via le Service Account.
        Le SA doit avoir un acces 'Lecteur' sur le dossier
        Mon Drive\\dslrBooth\\<nom_lieu>\\ partage manuellement.

        Retourne :
          - True si l'API repond et le dossier est accessible (cloud OK)
          - False si l'API echoue (sync silencieusement cassee)
          - None si non configure (GOOGLE_SA_JSON absent ou libs google
            absentes) — le niveau B est skipe gracieusement, le niveau A
            continue de tourner.
        """
        sa_json_str = _get_sa_json()
        if not sa_json_str:
            return None
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            return None
        try:
            creds = service_account.Credentials.from_service_account_info(
                json.loads(sa_json_str),
                scopes=DRIVE_API_SCOPES,
            )
            service = build("drive", "v3", credentials=creds, cache_discovery=False)

            if not self._drive_root_folder_id:
                self._drive_root_folder_id = self._resolve_root_folder_id(service)
                if not self._drive_root_folder_id:
                    # Pas de dossier partage avec le SA — rien a check pour cette borne
                    return None

            # Liste les enfants : un appel reussi = cloud accessible
            service.files().list(
                q=f"'{self._drive_root_folder_id}' in parents and trashed=false",
                pageSize=5,
                fields="files(id,name)",
                supportsAllDrives=False,
                includeItemsFromAllDrives=False,
            ).execute()
            return True
        except Exception as e:
            print(f"[DRIVE] Health check API FAIL: {e}")
            return False

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
            self._last_local_check_ts = now
            if not self._drive_writable_local():
                import activity_logger as alog
                alog.log_generic(
                    "DRIVE",
                    "Health check local FAIL — Drive Desktop ne repond pas",
                )
                self._drive_base = None
                self._creer_alerte_drive("local_write_failed")
                return
            else:
                # Local OK -> resoudre l'alerte 'drive_deconnecte' si elle etait ouverte
                self._resoudre_alerte_drive("local_write_failed")

        # Niveau B : appel API toutes les API_HEALTH_CHECK_INTERVAL_SEC
        if now - self._last_api_check_ts >= API_HEALTH_CHECK_INTERVAL_SEC:
            self._last_api_check_ts = now
            api_ok = self._drive_api_check()
            if api_ok is False:
                # Local marche, mais le cloud ne repond pas -> sync cassee
                import activity_logger as alog
                alog.log_generic(
                    "DRIVE",
                    "Health check API FAIL — sync vers cloud cassee",
                )
                self._creer_alerte_drive("cloud_sync_silently_broken")
                # Ne pas reset _drive_base : on continue a copier en local
                # en attendant que le cloud reparte.
            elif api_ok is True:
                self._resoudre_alerte_drive("cloud_sync_silently_broken")
            # api_ok is None -> SA non configure, on skip silencieusement

        # Détecter l'événement actif
        event = _detecter_evenement()
        if not event:
            return

        if event != self._current_event:
            print(f"[DRIVE] Événement: {event}")
            import activity_logger as alog
            alog.log_drive_event(event)
            alog.ui_log(f"Nouvel événement détecté: {event}")
            self._current_event = event
            if event not in self._events:
                self._init_event(event)

        if event not in self._events:
            return

        self._scanner(event)

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
