"""LedStripWatcher - eclairage dynamique via Raspberry Pi Pico (RP2040).

Architecture:
- Le Pico est detecte par VID 0x2E8A / PID 0x0005 (mode MicroPython)
- Au 1er connect, on sonde le firmware ; si absent/ancien, on le deploie via raw REPL
- Un mini HTTP server tourne sur 127.0.0.1:8000, dslrBooth lui envoie ses triggers
- L'event 'capture_start' declenche un BOOST sur la bande LED via USB-serie
- Les valeurs (lumiere douce / boost) sont persistees dans la registry Windows

Pas de mpremote ni d'outils externes : tout est self-contained dans ce fichier.
"""

import binascii
import hashlib
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

from PyQt5.QtCore import QObject, pyqtSignal

from paths import reg_get, reg_set


# ---------------------------------------------------------------------------
# Detection du Pico (pyserial est optionnel)
# ---------------------------------------------------------------------------

PICO_VID = 0x2E8A
PICO_PID = 0x0005
HTTP_HOST = "127.0.0.1"
HTTP_PORT = 8000
# FIRMWARE_TAG est calcule plus bas (apres la definition de PICO_FIRMWARE)
# automatiquement a partir du hash du firmware : changer n'importe quelle
# valeur du firmware (timing, code) -> nouveau tag -> redeploy automatique.

try:
    import serial
    from serial.tools import list_ports as _list_ports
    _SERIAL_OK = True
except Exception as _e:
    serial = None
    _list_ports = None
    _SERIAL_OK = False
    print(f"[LED] pyserial indisponible ({_e}) - module desactive")


# ---------------------------------------------------------------------------
# Firmware MicroPython embarque - charge sur le Pico au 1er connect.
# ---------------------------------------------------------------------------

PICO_FIRMWARE = r"""
import sys
import select
import binascii
from machine import Pin, PWM
from utime import sleep_ms

PWM_PIN = 27
PWM_FREQ = 1000

NORMAL_BRIGHTNESS = 5
BOOST_BRIGHTNESS = 30

RAMP_UP_MS = 50
HOLD_MS = 200
RAMP_DOWN_MS = 350

pwm = PWM(Pin(PWM_PIN))
pwm.freq(PWM_FREQ)


def clamp(v, lo, hi):
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def set_brightness(percent):
    p = clamp(int(percent), 0, 100)
    pwm.duty_u16(int(p * 65535 / 100))


def boost_sequence():
    n = NORMAL_BRIGHTNESS
    b = BOOST_BRIGHTNESS
    steps_up = 20
    if steps_up > 0:
        d = (b - n) / steps_up
        for i in range(steps_up):
            set_brightness(n + d * (i + 1))
            sleep_ms(int(RAMP_UP_MS / steps_up))
    set_brightness(b)
    sleep_ms(HOLD_MS)
    steps_down = 40
    if steps_down > 0:
        d = (b - n) / steps_down
        for i in range(steps_down):
            set_brightness(b - d * (i + 1))
            sleep_ms(int(RAMP_DOWN_MS / steps_down))
    set_brightness(n)


set_brightness(NORMAL_BRIGHTNESS)
print("__FIRMWARE_TAG__")

poll = select.poll()
poll.register(sys.stdin, select.POLLIN)
buf = ""

while True:
    events = poll.poll(50)
    if events:
        ch = sys.stdin.read(1)
        if ch == "\n" or ch == "\r":
            cmd = buf.strip().upper()
            buf = ""
            if cmd == "":
                pass
            elif cmd == "BOOST":
                boost_sequence()
            elif cmd == "ON":
                set_brightness(NORMAL_BRIGHTNESS)
            elif cmd == "OFF":
                set_brightness(0)
            elif cmd == "FULL":
                set_brightness(100)
            elif cmd == "ID":
                print("__FIRMWARE_TAG__")
            elif cmd.startswith("BRIGHT:"):
                try:
                    set_brightness(int(cmd.split(":", 1)[1]))
                except Exception:
                    pass
            elif cmd.startswith("SETNORMAL:"):
                try:
                    NORMAL_BRIGHTNESS = clamp(int(cmd.split(":", 1)[1]), 0, 100)
                    set_brightness(NORMAL_BRIGHTNESS)
                except Exception:
                    pass
            elif cmd.startswith("SETBOOST:"):
                try:
                    BOOST_BRIGHTNESS = clamp(int(cmd.split(":", 1)[1]), 0, 100)
                except Exception:
                    pass
        else:
            buf += ch
            if len(buf) > 50:
                buf = ""
"""


# Hash du firmware -> tag de version. Toute modification du firmware (timing,
# code, etc.) change le hash, ce qui force l'agent a redeployer au prochain
# connect (compare avec ce que le Pico repond a "ID"). Aucun bump manuel a faire.
FIRMWARE_TAG = "MEMENTO_LED " + hashlib.md5(PICO_FIRMWARE.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------------
# HTTP Handler factory
# ---------------------------------------------------------------------------

def _make_handler(watcher):
    class _Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            # Silencieux par defaut (BaseHTTPRequestHandler logue sur stderr)
            return

        def do_GET(self):
            try:
                qs = parse_qs(urlparse(self.path).query)
                ev = (qs.get("event_type", [""])[0] or "").lower()
                # On accuse reception meme si LED desactive (dslrBooth ne doit pas timeout)
                if reg_get("led_enabled"):
                    if ev == "capture_start":
                        watcher.boost()
                    elif ev in ("session_start", "session_end"):
                        watcher.on()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"OK")
            except Exception as e:
                try:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(str(e).encode("utf-8", "ignore"))
                except Exception:
                    pass

    return _Handler


# ---------------------------------------------------------------------------
# LedStripWatcher
# ---------------------------------------------------------------------------

class LedStripWatcher(QObject):
    """Watcher LED - tourne en arriere-plan, expose status_changed pour l'UI."""

    # (connected: bool, message: str)
    status_changed = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self._serial = None        # type: serial.Serial | None
        self._port = None
        self._connected = False
        self._http_server = None
        self._http_thread = None
        self._stop_flag = False
        self._last_normal = None
        self._last_boost = None

    # ---- API publique ------------------------------------------------

    def start(self):
        if not _SERIAL_OK:
            self._emit_status(False, "pyserial absent")
            return
        # HTTP server (toujours, meme si Pico pas encore detecte)
        try:
            handler = _make_handler(self)
            self._http_server = HTTPServer((HTTP_HOST, HTTP_PORT), handler)
            self._http_thread = threading.Thread(
                target=self._http_server.serve_forever,
                name="LedStripHTTP",
                daemon=True,
            )
            self._http_thread.start()
            print(f"[LED] Watcher demarre - port HTTP {HTTP_PORT} en ecoute")
        except OSError as e:
            print(f"[LED] Impossible d'ouvrir le port HTTP {HTTP_PORT}: {e}")
            self._http_server = None
        # Tentative de connexion immediate (la suite se fait via tick)
        self._emit_status(False, "Recherche du Pico...")
        self._try_connect()

    def stop(self):
        self._stop_flag = True
        try:
            if self._serial and self._serial.is_open:
                # Eteindre la bande avant de partir
                try:
                    self._serial.write(b"OFF\n")
                    self._serial.flush()
                except Exception:
                    pass
                self._serial.close()
        except Exception:
            pass
        self._serial = None
        self._connected = False
        if self._http_server:
            try:
                self._http_server.shutdown()
                self._http_server.server_close()
            except Exception:
                pass
            self._http_server = None
        print("[LED] Watcher arrete")

    def tick(self):
        """Appele toutes les ~3s par MonitoringEngine."""
        if self._stop_flag or not _SERIAL_OK:
            return
        # Reconnexion si debranche
        if not self._is_serial_alive():
            self._connected = False
            self._try_connect()
            return
        # Si la registry a change les valeurs, les pousser
        n = int(reg_get("led_normal_pct") or 5)
        b = int(reg_get("led_boost_pct") or 30)
        if n != self._last_normal:
            self._send(f"SETNORMAL:{n}")
            self._last_normal = n
        if b != self._last_boost:
            self._send(f"SETBOOST:{b}")
            self._last_boost = b

    def boost(self):
        if not int(reg_get("led_enabled") or 0):
            return
        self._send("BOOST")

    def on(self):
        self._send("ON")

    def off(self):
        self._send("OFF")

    def set_normal(self, pct):
        pct = max(0, min(100, int(pct)))
        reg_set("led_normal_pct", pct)
        self._last_normal = pct
        self._send(f"SETNORMAL:{pct}")

    def set_boost(self, pct):
        pct = max(0, min(100, int(pct)))
        reg_set("led_boost_pct", pct)
        self._last_boost = pct
        self._send(f"SETBOOST:{pct}")

    def is_connected(self):
        return self._connected

    def port_name(self):
        return self._port

    # ---- Detection / connexion --------------------------------------

    def _is_serial_alive(self):
        if not self._serial:
            return False
        try:
            return self._serial.is_open
        except Exception:
            return False

    def _find_port(self):
        if not _list_ports:
            return None
        for p in _list_ports.comports():
            try:
                if p.vid == PICO_VID and p.pid == PICO_PID:
                    return p.device
            except Exception:
                continue
        return None

    def _try_connect(self):
        port = self._find_port()
        if not port:
            self._emit_status(False, "Pico non detecte")
            return
        # Si meme port deja teste : retry rapide
        try:
            ser = serial.Serial(port, 115200, timeout=0.3, write_timeout=1)
        except Exception as e:
            self._emit_status(False, f"Erreur ouverture {port}: {e}")
            return

        # Sonder le firmware d'abord
        if not self._probe_firmware(ser):
            print(f"[LED] Firmware absent/ancien sur {port} - deploiement...")
            ok = self._deploy_firmware(ser, port)
            if not ok:
                try:
                    ser.close()
                except Exception:
                    pass
                self._emit_status(False, f"Echec deploiement firmware sur {port}")
                return
            # Reouvrir apres soft reboot
            try:
                ser.close()
            except Exception:
                pass
            time.sleep(2.0)
            try:
                ser = serial.Serial(port, 115200, timeout=0.3, write_timeout=1)
            except Exception as e:
                self._emit_status(False, f"Erreur reouverture apres deploy {port}: {e}")
                return
            if not self._probe_firmware(ser):
                try:
                    ser.close()
                except Exception:
                    pass
                self._emit_status(False, "Firmware non detecte apres deploiement")
                return
            print(f"[LED] Firmware deploye et Pico redemarre")

        # Ouverture normale OK
        with self._lock:
            self._serial = ser
            self._port = port
            self._connected = True

        # Pousser les valeurs registry
        normal = int(reg_get("led_normal_pct") or 5)
        boost = int(reg_get("led_boost_pct") or 30)
        self._send(f"SETNORMAL:{normal}")
        self._send(f"SETBOOST:{boost}")
        if int(reg_get("led_enabled") or 0):
            self._send("ON")
        else:
            self._send("OFF")
        self._last_normal = normal
        self._last_boost = boost
        print(f"[LED] Connecte sur {port} (normal={normal}%, boost={boost}%)")
        self._emit_status(True, port)

    def _probe_firmware(self, ser):
        """Envoie 'ID' et attend 'MEMENTO_LED_v2' (max 1.5s)."""
        try:
            try:
                ser.reset_input_buffer()
            except Exception:
                pass
            ser.write(b"\r\nID\r\n")
            ser.flush()
            deadline = time.time() + 1.5
            buf = b""
            while time.time() < deadline:
                chunk = ser.read(64)
                if chunk:
                    buf += chunk
                    if FIRMWARE_TAG.encode() in buf:
                        return True
                else:
                    time.sleep(0.05)
        except Exception:
            return False
        return False

    def _deploy_firmware(self, ser, port):
        """Charge le firmware via raw REPL paste mode.
        - Ctrl-C x2 pour casser tout programme en cours
        - Ctrl-A pour entrer en raw REPL
        - Coller un script qui ouvre 'main.py' wb et fait binascii.unhexlify chunks
        - Ctrl-D pour executer, attendre OK
        - Ctrl-B pour quitter raw REPL, Ctrl-D pour soft reboot
        """
        try:
            # Le firmware contient le placeholder __FIRMWARE_TAG__ : on le
            # remplace par la valeur de FIRMWARE_TAG (defini au top du module),
            # comme ca on n'a qu'une seule source de verite pour la version.
            firmware_text = PICO_FIRMWARE.replace("__FIRMWARE_TAG__", FIRMWARE_TAG)
            firmware_bytes = firmware_text.encode("utf-8")
            firmware_hex = binascii.hexlify(firmware_bytes).decode("ascii")

            # Reset / break
            ser.write(b"\x03\x03")  # Ctrl-C Ctrl-C
            time.sleep(0.2)
            try:
                ser.reset_input_buffer()
            except Exception:
                pass
            # Raw REPL
            ser.write(b"\x01")  # Ctrl-A
            time.sleep(0.3)
            try:
                ser.reset_input_buffer()
            except Exception:
                pass

            # Construire le script d'install
            chunk_size = 256  # 256 chars hex = 128 octets
            chunks = [
                firmware_hex[i:i + chunk_size]
                for i in range(0, len(firmware_hex), chunk_size)
            ]
            installer_lines = [
                "import binascii",
                "f = open('main.py', 'wb')",
            ]
            for c in chunks:
                installer_lines.append(f"f.write(binascii.unhexlify('{c}'))")
            installer_lines.append("f.close()")
            installer_lines.append("print('OK')")
            installer = "\r\n".join(installer_lines) + "\r\n"

            # Envoyer le script en raw mode
            ser.write(installer.encode("ascii"))
            ser.flush()
            ser.write(b"\x04")  # Ctrl-D = run
            ser.flush()

            # Attendre 'OK' (ecriture du fichier peut prendre quelques secondes)
            deadline = time.time() + 10.0
            buf = b""
            ok = False
            while time.time() < deadline:
                chunk = ser.read(128)
                if chunk:
                    buf += chunk
                    if b"OK" in buf:
                        ok = True
                        break
                else:
                    time.sleep(0.05)

            if not ok:
                print(f"[LED] Pas de OK dans la reponse raw REPL: {buf[-200:]!r}")
                return False

            # Quitter raw REPL et redemarrer
            ser.write(b"\x02")  # Ctrl-B
            time.sleep(0.2)
            ser.write(b"\x04")  # Ctrl-D = soft reboot
            ser.flush()
            time.sleep(1.5)
            return True
        except Exception as e:
            print(f"[LED] Erreur deploy firmware: {e}")
            return False

    # ---- Envoi serie ------------------------------------------------

    def _send(self, command):
        if not self._serial:
            return False
        try:
            with self._lock:
                if not self._serial or not self._serial.is_open:
                    return False
                line = (command.strip() + "\n").encode("ascii", "ignore")
                self._serial.write(line)
                self._serial.flush()
            return True
        except Exception as e:
            print(f"[LED] Erreur ecriture serie: {e}")
            self._connected = False
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None
            self._emit_status(False, f"Deconnecte: {e}")
            return False

    def _emit_status(self, connected, msg):
        try:
            self.status_changed.emit(bool(connected), str(msg))
        except Exception:
            pass
