"""Orchestre l'affichage de l'overlay sur evenement impression."""
import time
from PyQt5.QtCore import QObject

from . import config as cfg_mod
from .window import OverlayWindow
from .detector import PrintStartDetector


# Fenetre de dedup pour les signaux DLL sans JobId (spool indispo / fallback).
# Pourquoi 3s : le detecteur poll a 500ms, le bit 'printing' DNP arrive en
# general <1s apres l'apparition du JobId Windows. 3s couvre largement et
# laisse passer 2 vraies impressions consecutives (la DS620 met ~10s/photo).
DEDUP_DLL_FALLBACK_S = 3

# Plafond de la memoire des JobIds vus pour eviter une fuite sur sessions
# longues (1000+ prints). Garde uniquement les N plus recents.
JOBS_SEEN_MAX = 200


class PrintOverlayManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._window = None
        self._cfg = cfg_mod.load()
        # JobIds Windows deja affiches : 1 barre par impression reelle, dedup
        # precise meme pour 2 prints en rafale (resultat: la 2e barre s'empile
        # bien, alors qu'avant le dedup temporel de 25s la masquait).
        self._jobs_seen = []  # ordre d'arrivee, capped a JOBS_SEEN_MAX
        self._jobs_seen_set = set()  # lookup O(1)
        # Timestamp du dernier add_bar — sert a dedupliquer le signal DLL qui
        # suit un signal spool pour la MEME impression.
        self._last_start = 0.0
        self._detector = None
        if self._cfg.get("enabled"):
            self._ensure_detector()

    def _ensure_detector(self):
        if self._detector is not None:
            return
        self._detector = PrintStartDetector(
            on_print_started=self._on_start_signal,
            on_print_completed=self._on_done_signal,
            parent=self,
        )
        self._detector.start()

    def reload_config(self):
        self._cfg = cfg_mod.load()
        if self._cfg.get("enabled"):
            self._ensure_detector()

    def _on_start_signal(self, job_id=None):
        self.on_print_started(job_id)

    def _on_done_signal(self):
        """Compteur DNP a baisse = papier sorti. Marquer la barre active comme terminee."""
        if self._window is None:
            return
        self._window.mark_current_done()

    def _remember_job(self, job_id):
        self._jobs_seen.append(job_id)
        self._jobs_seen_set.add(job_id)
        # Cap : on jette les plus anciens
        while len(self._jobs_seen) > JOBS_SEEN_MAX:
            old = self._jobs_seen.pop(0)
            self._jobs_seen_set.discard(old)

    def _add_bar(self):
        if self._window is None:
            self._window = OverlayWindow()
        self._window.add_bar(self._cfg, self._cfg.get("duration", 18))
        self._last_start = time.time()

    def on_print_started(self, job_id=None):
        if not self._cfg.get("enabled"):
            return
        # Cas 1 — signal spool avec JobId Windows : dedup precis par job.
        if job_id is not None:
            if job_id in self._jobs_seen_set:
                return
            self._remember_job(job_id)
            self._add_bar()
            return
        # Cas 2 — signal DLL sans JobId (filet de secours) : dedup court avec
        # le dernier add_bar. Si un spool a fire pour cette impression dans
        # les DEDUP_DLL_FALLBACK_S, c'est le meme print -> on ignore.
        if time.time() - self._last_start < DEDUP_DLL_FALLBACK_S:
            return
        self._add_bar()

    def trigger_preview(self):
        # Force l'affichage sans toucher aux JobIds (preview admin).
        self._add_bar()
