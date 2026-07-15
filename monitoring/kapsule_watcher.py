"""Surveille Kapsule Bar via son health.json."""

import os
import json
import time
import subprocess
from datetime import datetime, timezone


HEALTH_PATH = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "Programs", "kapsule-bar", "health.json",
)

FROZEN_THRESHOLD_SEC = 300
BAD_STATE_ALERT_THRESHOLD_SEC = 300
RELAUNCH_COOLDOWN_SEC = 60
HEALTH_PARSE_KO_THRESHOLD_SEC = 300

DETACHED_PROCESS = 0x00000008
CREATE_NO_WINDOW = 0x08000000


class KapsuleWatcher:
    def __init__(self, borne_id, nom_lieu=None):
        self._borne_id = borne_id
        self._nom_lieu = nom_lieu or "la borne"
        self._last_relaunch_ts = 0.0
        self._first_bad_ts = None
        self._first_missing_exe_ts = None
        self._first_parse_ko_ts = None
        self._last_bad_type = None
        self._last_bad_msg = None

    def tick(self):
        try:
            self._tick_impl()
        except Exception as e:
            print(f"[KAPSULE] tick erreur: {e}")

    def _tick_impl(self):
        if not os.path.exists(HEALTH_PATH):
            return

        health = self._read_health()
        if health is None:
            self._handle_parse_ko()
            return
        self._first_parse_ko_ts = None
        self._resolve("kapsule_health_illisible")

        state = health.get("state")
        exe_path = health.get("exePath")
        updated_at = health.get("updatedAt")
        last_error = health.get("lastError")
        age_sec = self._age_of(updated_at)

        exe_missing = not exe_path or not os.path.exists(exe_path)
        is_crashed = state == "crashed"
        is_stopped = state == "stopped"
        is_frozen = age_sec is not None and age_sec > FROZEN_THRESHOLD_SEC

        if exe_missing:
            if self._first_missing_exe_ts is None:
                self._first_missing_exe_ts = time.time()
            if time.time() - self._first_missing_exe_ts > BAD_STATE_ALERT_THRESHOLD_SEC:
                self._raise("kapsule_exe_absent", f"Fichier kapsule-bar.exe absent sur {self._nom_lieu}.")
            return
        self._first_missing_exe_ts = None
        self._resolve("kapsule_exe_absent")

        if is_crashed or is_stopped or is_frozen:
            if self._first_bad_ts is None:
                self._first_bad_ts = time.time()

            if is_crashed:
                self._last_bad_type = "kapsule_crash"
                msg = f"Kapsule a crashe sur {self._nom_lieu} depuis > 5 min."
                if last_error:
                    msg += f" Erreur : {str(last_error)[:200]}"
                self._last_bad_msg = msg
            elif is_stopped:
                self._last_bad_type = "kapsule_ferme"
                self._last_bad_msg = f"Kapsule ferme sur {self._nom_lieu} depuis > 5 min."
            else:
                self._last_bad_type = "kapsule_ferme"
                self._last_bad_msg = f"Kapsule fige sur {self._nom_lieu} depuis > 5 min (dernier heartbeat {age_sec:.0f}s)."

            self._relaunch(exe_path)

            if time.time() - self._first_bad_ts > BAD_STATE_ALERT_THRESHOLD_SEC:
                self._raise(self._last_bad_type, self._last_bad_msg)
            return

        self._first_bad_ts = None
        self._resolve("kapsule_crash")
        self._resolve("kapsule_ferme")

    def _read_health(self):
        try:
            with open(HEALTH_PATH, encoding="utf-8-sig") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return None
            return data
        except Exception:
            return None

    def _age_of(self, iso_str):
        if not iso_str:
            return None
        try:
            s = iso_str.replace("Z", "+00:00")
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - dt).total_seconds()
        except Exception:
            return None

    def _handle_parse_ko(self):
        if self._first_parse_ko_ts is None:
            self._first_parse_ko_ts = time.time()
            return
        if time.time() - self._first_parse_ko_ts > HEALTH_PARSE_KO_THRESHOLD_SEC:
            self._raise("kapsule_health_illisible", f"health.json de Kapsule illisible depuis > 5 min sur {self._nom_lieu}.")

    def _relaunch(self, exe_path):
        now = time.time()
        if now - self._last_relaunch_ts < RELAUNCH_COOLDOWN_SEC:
            return
        self._last_relaunch_ts = now
        try:
            subprocess.Popen(
                [exe_path],
                creationflags=DETACHED_PROCESS | CREATE_NO_WINDOW,
                close_fds=True,
            )
            print(f"[KAPSULE] Relance {exe_path}")
            try:
                import activity_logger as alog
                alog.log_generic("KAPSULE", f"relance {os.path.basename(exe_path)}")
            except Exception:
                pass
        except Exception as e:
            print(f"[KAPSULE] Relance echouee: {e}")

    def _raise(self, type_alerte, message):
        try:
            from .alertes.alertes_monitor import _alerte_deja_ouverte, _creer_alerte
            if not _alerte_deja_ouverte(self._borne_id, type_alerte):
                _creer_alerte(self._borne_id, type_alerte, "kapsule", message, gravite="warning")
        except Exception as e:
            print(f"[KAPSULE] _raise {type_alerte} erreur: {e}")

    def _resolve(self, type_alerte):
        try:
            from .alertes.alertes_monitor import _resoudre_alertes
            _resoudre_alertes(self._borne_id, [type_alerte])
        except Exception:
            pass
