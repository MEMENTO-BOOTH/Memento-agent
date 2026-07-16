import os
import json
from collections import deque

EMMENTO_JSONL_PATHS = [
    os.path.join(os.environ.get("APPDATA", ""), "kapsule-bar", "ememento.jsonl"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "kapsule-bar", "ememento.jsonl"),
]

EMMENTO_JSONL = EMMENTO_JSONL_PATHS[0]

ROTATED_MAX = 5
MAX_SEEN_CODES = 10000


def _all_paths():
    paths = []
    for base in EMMENTO_JSONL_PATHS:
        paths.append(base)
        for i in range(1, ROTATED_MAX + 1):
            paths.append(f"{base}.{i}")
    return paths


class KapsuleEmmentoWatcher:
    def __init__(self, borne_id, nom_lieu=None):
        self._borne_id = borne_id
        self._nom_lieu = nom_lieu or ""
        self._seen = set()
        self._seen_order = deque()
        self._mtimes = {}
        self._boot_seen()

    def _boot_seen(self):
        for path in _all_paths():
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    for ligne in f:
                        code = self._extract_code(ligne)
                        if code:
                            self._mark_seen(code)
            except Exception as e:
                print(f"[KAPSULE_EMMENTO] boot read {path} erreur: {e}")

    def _extract_code(self, ligne):
        ligne = ligne.strip()
        if not ligne:
            return None
        try:
            data = json.loads(ligne)
        except Exception:
            return None
        return data.get("code") or None

    def _mark_seen(self, code):
        if code in self._seen:
            return
        self._seen.add(code)
        self._seen_order.append(code)
        while len(self._seen_order) > MAX_SEEN_CODES:
            oldest = self._seen_order.popleft()
            self._seen.discard(oldest)

    def tick(self):
        for path in _all_paths():
            if not os.path.exists(path):
                self._mtimes.pop(path, None)
                continue
            try:
                mtime = os.path.getmtime(path)
                if self._mtimes.get(path) == mtime:
                    continue
                self._mtimes[path] = mtime
                with open(path, "r", encoding="utf-8-sig") as f:
                    for ligne in f:
                        self._process_line(ligne)
            except Exception as e:
                print(f"[KAPSULE_EMMENTO] read {path} erreur: {e}")

    def _process_line(self, ligne):
        ligne = ligne.strip()
        if not ligne:
            return
        try:
            data = json.loads(ligne)
        except Exception:
            return

        code = data.get("code") or None
        if not code or code in self._seen:
            return
        self._mark_seen(code)

        bar = data.get("bar") or self._nom_lieu or "inconnu"
        photos = data.get("photos") or []
        originals = data.get("originals") or []

        try:
            import activity_logger as alog
            alog.log_session(code, code, bar)
            alog.ui_log(f"[Kapsule] Session {code} — {bar}")

            for chemin in photos:
                fname = os.path.basename(chemin)
                try:
                    fsize = os.path.getsize(chemin)
                except Exception:
                    fsize = 0
                alog.log_print(fname, fsize, code, bar)
                alog.ui_log(f"Print: {fname}")

            for chemin in originals:
                fname = os.path.basename(chemin)
                try:
                    fsize = os.path.getsize(chemin)
                except Exception:
                    fsize = 0
                alog.log_original(fname, fsize, chemin)
                alog.ui_log(f"Original: {fname}")
        except Exception as e:
            print(f"[KAPSULE_EMMENTO] Erreur log: {e}")
