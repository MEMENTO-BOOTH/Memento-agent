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
DSLRBOOTH_CONFIG = os.path.join(
    os.environ.get("APPDATA", ""), "dslrBooth", "app_settings_2021.json"
)
DSLRBOOTH_DB = os.path.join(
    os.environ.get("APPDATA", ""), "dslrBooth", "database_2025.db"
)

# Vérification fichiers
TAILLE_MIN_ORIGINAL = 100_000   # 100 Ko
TAILLE_MIN_PRINT = 10_000       # 10 Ko


def _trouver_google_drive():
    """Détecte automatiquement le chemin Google Drive (FR ou EN)."""
    for lettre in "GHIJDEFKLM":
        for nom in ("Mon Drive", "My Drive"):
            chemin = f"{lettre}:\\{nom}"
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

    def __init__(self, nom_lieu):
        self._nom_lieu = nom_lieu
        self._drive_base = None
        self._events = {}  # event_name → {"originals": set, "prints": set}
        self._current_event = None
        self._total_copies = 0
        self._init_drive()

    def _init_drive(self):
        drive = _trouver_google_drive()
        if not drive:
            print("[DRIVE] Google Drive non détecté")
            import activity_logger as alog
            alog.log_drive_inaccessible()
            alog.ui_log("Google Drive inaccessible")
            return
        self._drive_base = os.path.join(drive, "dslrBooth", self._nom_lieu)
        print(f"[DRIVE] Base: {self._drive_base}")

    def tick(self):
        """Appelé à chaque cycle du monitoring."""
        if not self._drive_base:
            # Réessayer de trouver Google Drive
            self._init_drive()
            if not self._drive_base:
                return

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
        """Initialise le suivi + rattrapage des fichiers manquants."""
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

        # Rattrapage : copier les fichiers manquants
        local_orig = _lister_jpgs(orig_local)
        local_prints = _lister_jpgs(prints_local, exclure_thumb=True)
        drive_orig_set = _lister_jpgs(drive_orig)
        drive_prints_set = _lister_jpgs(drive_prints, exclure_thumb=True)

        manquants_orig = local_orig - drive_orig_set
        manquants_prints = local_prints - drive_prints_set

        nb = 0
        for f in sorted(manquants_orig):
            src = os.path.join(orig_local, f)
            if _fichier_valide(src, TAILLE_MIN_ORIGINAL):
                if _copier(src, os.path.join(drive_orig, f)):
                    nb += 1
        for f in sorted(manquants_prints):
            src = os.path.join(prints_local, f)
            if _fichier_valide(src, TAILLE_MIN_PRINT):
                if _copier(src, os.path.join(drive_prints, f)):
                    nb += 1

        if nb:
            print(f"[DRIVE] Rattrapage {event_name}: {nb} fichier(s)")

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
