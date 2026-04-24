"""Detecteur d'impression temps reel (main thread, QTimer 500 ms).

Le handle d'imprimante Windows est ouvert UNE seule fois au demarrage et
garde ouvert : chaque tick fait juste un EnumJobs sur ce handle (quelques ms).

Trois signaux combines, le premier qui fire declenche la barre :
  1. Win32 EnumJobs : nouveau JobId dans la queue (plus precoce)
  2. DNP GetStatus bit 0x0002 : imprimante passe en mode PRINTING
  3. DNP GetMediaCounter : baisse (filet de secours, fire a la coupe papier)

Ecrit dans ~/.mementoagent/overlay.log a chaque evenement pour debug.
"""
import os
import sys
import ctypes
import platform
from datetime import datetime
from PyQt5.QtCore import QObject, QTimer

try:
    import win32print
    HAS_WIN32PRINT = True
except ImportError:
    HAS_WIN32PRINT = False


POLL_MS = 500
REINIT_EVERY = 120
LOG_PATH = os.path.join(os.path.expanduser("~"), ".mementoagent", "overlay.log")


def _log(msg):
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%H:%M:%S.%f} {msg}\n")
    except Exception:
        pass


def _is_ds620(name):
    from monitoring.alertes.constants import PRINTER_PATTERNS
    n = name.upper()
    return any(p.upper() in n for p in PRINTER_PATTERNS)


def _find_dll():
    here = os.path.dirname(os.path.abspath(__file__))
    mon_dir = os.path.normpath(os.path.join(here, os.pardir, "monitoring"))
    candidates = [
        os.path.join(mon_dir, "coupe_2pouces", "Cx2Stat64.dll"),
        os.path.join(mon_dir, "Cx2Stat64.dll"),
    ]
    if hasattr(sys, "_MEIPASS"):
        candidates.insert(0, os.path.join(sys._MEIPASS, "monitoring", "coupe_2pouces", "Cx2Stat64.dll"))
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


class PrintStartDetector(QObject):
    def __init__(self, on_print_started, on_print_completed=None, parent=None):
        super().__init__(parent)
        self._cb_start = on_print_started
        self._cb_done = on_print_completed
        self._printer_handle = None
        self._printer_name = None
        self._known_jobs = set()
        self._dll = None
        self._dll_port = -1
        self._last_media = None
        self._last_printing = False
        self._retry_count = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    def start(self):
        self._init_spool()
        self._init_dll()
        self._timer.start(POLL_MS)
        _log(f"detector start (spool={self._printer_handle is not None}, dll_port={self._dll_port})")

    def stop(self):
        self._timer.stop()
        self._close_spool()
        self._close_dll()

    def _init_spool(self):
        if not HAS_WIN32PRINT:
            _log("win32print unavailable")
            return
        try:
            flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
            for pinfo in win32print.EnumPrinters(flags):
                name = pinfo[2]
                if not _is_ds620(name):
                    continue
                try:
                    h = win32print.OpenPrinter(name)
                    jobs = win32print.EnumJobs(h, 0, 200, 1)
                    self._printer_handle = h
                    self._printer_name = name
                    self._known_jobs = {j["JobId"] for j in jobs}
                    _log(f"spool open {name} jobs={sorted(self._known_jobs)}")
                    return
                except Exception as e:
                    _log(f"spool open error {name}: {e}")
        except Exception as e:
            _log(f"EnumPrinters error: {e}")

    def _close_spool(self):
        if self._printer_handle is not None:
            try:
                win32print.ClosePrinter(self._printer_handle)
            except Exception:
                pass
        self._printer_handle = None

    def _init_dll(self):
        if platform.system() != "Windows":
            return
        dll_path = _find_dll()
        if not dll_path:
            _log("dll not found")
            return
        try:
            self._dll = ctypes.WinDLL(dll_path)
            self._dll.PortInitialize.argtypes = [ctypes.c_wchar_p]
            self._dll.PortInitialize.restype = ctypes.c_int
            self._dll.GetStatus.argtypes = [ctypes.c_int]
            self._dll.GetStatus.restype = ctypes.c_uint
            self._dll.GetMediaCounter.argtypes = [ctypes.c_int]
            self._dll.GetMediaCounter.restype = ctypes.c_int
            for p in ("USB004", "USB003", "USB002", "USB001"):
                port = self._dll.PortInitialize(p)
                if port >= 0:
                    status = self._dll.GetStatus(port)
                    if status != 0x80000000:
                        self._dll_port = port
                        self._last_media = self._dll.GetMediaCounter(port)
                        self._last_printing = bool(status & 0x0002)
                        _log(f"dll open {p} media={self._last_media} printing={self._last_printing}")
                        return
                    try:
                        self._dll.PortRelease(port)
                    except Exception:
                        pass
        except Exception as e:
            _log(f"dll init error: {e}")

    def _close_dll(self):
        if self._dll is not None and self._dll_port >= 0:
            try:
                self._dll.PortRelease(self._dll_port)
            except Exception:
                pass
        self._dll_port = -1

    def _fire_start(self, source):
        _log(f"START from {source}")
        try:
            self._cb_start()
        except Exception as e:
            _log(f"cb_start error: {e}")

    def _fire_done(self, source):
        _log(f"DONE from {source}")
        if self._cb_done is None:
            return
        try:
            self._cb_done()
        except Exception as e:
            _log(f"cb_done error: {e}")

    def _poll_spool(self):
        if self._printer_handle is None:
            return
        try:
            jobs = win32print.EnumJobs(self._printer_handle, 0, 200, 1)
            cur = {j["JobId"] for j in jobs}
            new_jobs = cur - self._known_jobs
            self._known_jobs |= cur
            if new_jobs:
                self._fire_start(f"spool jobs={sorted(new_jobs)}")
        except Exception as e:
            _log(f"spool poll error: {e}")
            self._close_spool()

    def _poll_dll(self):
        if self._dll is None or self._dll_port < 0:
            return
        try:
            status = self._dll.GetStatus(self._dll_port)
            printing = bool(status & 0x0002)
            if printing and not self._last_printing:
                self._fire_start(f"dll status printing=1 (raw=0x{status:08X})")
            self._last_printing = printing

            media = self._dll.GetMediaCounter(self._dll_port)
            if self._last_media is not None and media < self._last_media:
                self._fire_done(f"dll media {self._last_media} -> {media}")
            self._last_media = media
        except Exception as e:
            _log(f"dll poll error: {e}")
            self._close_dll()

    def _retry_if_needed(self):
        self._retry_count += 1
        if self._retry_count % REINIT_EVERY != 0:
            return
        if self._printer_handle is None:
            self._init_spool()
        if self._dll is None or self._dll_port < 0:
            self._init_dll()

    def _tick(self):
        self._retry_if_needed()
        self._poll_spool()
        self._poll_dll()
