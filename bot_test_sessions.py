"""Bot de test : simule un toucher au centre de l'ecran toutes les N secondes
pour declencher des sessions dslrbooth, afin de stresser l'agent et mesurer
le taux de race condition rattrapée par le rescan emmento.

Usage :
    python bot_test_sessions.py [--interval 90] [--duration 720] [--sessions 0]

Arguments :
    --interval  : secondes entre chaque clic (default 90s, evite le chevauchement
                  avec le rescan de 30s)
    --duration  : duree totale en minutes (default 720 = 12h, mettre 0 pour infini)
    --sessions  : nombre max de sessions (default 0 = pas de limite)

Le bot :
- Loggue chaque trigger dans bot_test.log avec timestamp
- Clique au centre de l'ecran principal (toute la page dslrbooth est cliquable)
- Utilise Win32 SendInput (mouse_event) sans dependance externe (pure ctypes)

Ctrl-C pour arreter.
"""

import argparse
import ctypes
import os
import sys
import time
from ctypes import wintypes
from datetime import datetime


# ---------------------------------------------------------------------------
# Win32 mouse simulation via SendInput (plus fiable que SetCursorPos+mouse_event)
# ---------------------------------------------------------------------------

INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_ABSOLUTE = 0x8000


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]


def _screen_size():
    """Taille du moniteur principal en pixels."""
    user32 = ctypes.windll.user32
    user32.SetProcessDPIAware()
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


# ---------------------------------------------------------------------------
# Mise au premier plan + maximisation de dslrbooth
# ---------------------------------------------------------------------------

SW_RESTORE = 9
SW_MAXIMIZE = 3
SW_SHOWMAXIMIZED = 3


VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x0002


def _alt_press_release():
    """Trick Windows : appuyer/relacher ALT debloque la possibilite de changer
    le foreground window via SetForegroundWindow. Sans ca, Windows refuse
    silencieusement et fait juste flasher l'icone dans la taskbar."""
    user32 = ctypes.windll.user32
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)


def _find_dslrbooth_hwnd():
    """Cherche la fenetre dslrbooth, retourne son hwnd ou None."""
    user32 = ctypes.windll.user32
    EnumWindowsProc = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM,
    )
    found = []

    def callback(hwnd, lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        if title and "dslrbooth" in title.lower():
            found.append((hwnd, title))
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return found[0] if found else None


def _foreground_title():
    """Titre de la fenetre actuellement au premier plan."""
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _bring_dslrbooth_front():
    """Trouve dslrbooth, la maximise et la passe au premier plan.
    Retourne True si la fenetre est bien au premier plan apres l'operation."""
    user32 = ctypes.windll.user32
    res = _find_dslrbooth_hwnd()
    if not res:
        return False
    hwnd, _title = res

    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.ShowWindow(hwnd, SW_SHOWMAXIMIZED)
    _alt_press_release()
    user32.BringWindowToTop(hwnd)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)  # delai pour que Windows applique
    return user32.GetForegroundWindow() == hwnd


def _click(x, y):
    """Clic absolu en (x, y) via SendInput."""
    user32 = ctypes.windll.user32
    sw, sh = _screen_size()
    # Coordonnees absolues SendInput : 0..65535
    abs_x = int(x * 65535 / sw)
    abs_y = int(y * 65535 / sh)

    inputs = (INPUT * 3)()
    inputs[0] = INPUT(INPUT_MOUSE, _INPUTUNION(MOUSEINPUT(
        abs_x, abs_y, 0, MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE, 0, None,
    )))
    inputs[1] = INPUT(INPUT_MOUSE, _INPUTUNION(MOUSEINPUT(
        0, 0, 0, MOUSEEVENTF_LEFTDOWN, 0, None,
    )))
    inputs[2] = INPUT(INPUT_MOUSE, _INPUTUNION(MOUSEINPUT(
        0, 0, 0, MOUSEEVENTF_LEFTUP, 0, None,
    )))
    user32.SendInput(3, ctypes.byref(inputs), ctypes.sizeof(INPUT))


# ---------------------------------------------------------------------------
# Boucle bot
# ---------------------------------------------------------------------------

LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bot_test.log")


def log(msg):
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval", type=int, default=90,
                        help="Secondes entre les clics (default 90)")
    parser.add_argument("--duration", type=int, default=720,
                        help="Duree max en minutes (default 720 = 12h, 0 = infini)")
    parser.add_argument("--sessions", type=int, default=0,
                        help="Nombre max de sessions (default 0 = illimite)")
    args = parser.parse_args()

    sw, sh = _screen_size()
    cx, cy = sw // 2, sh // 2

    deadline = None
    if args.duration > 0:
        deadline = time.time() + args.duration * 60

    log(f"=== BOT START ecran {sw}x{sh} clic ({cx},{cy}) "
        f"interval={args.interval}s duration={args.duration}min "
        f"max_sessions={args.sessions or 'inf'} ===")

    n = 0
    try:
        while True:
            n += 1
            # Avant chaque clic : remettre dslrbooth en plein ecran et au premier plan
            ok_focus = _bring_dslrbooth_front()
            fg_title = _foreground_title()
            if not ok_focus:
                log(f"#{n} ATTENTION focus pas sur dslrbooth — fg='{fg_title}'")
            time.sleep(0.2)
            log(f"#{n} trigger session — clic ({cx},{cy}) sur fg='{fg_title}'")
            _click(cx, cy)
            if args.sessions and n >= args.sessions:
                log(f"=== STOP atteint sessions={args.sessions} ===")
                break
            if deadline and time.time() >= deadline:
                log(f"=== STOP duration atteinte ===")
                break
            time.sleep(args.interval)
    except KeyboardInterrupt:
        log(f"=== STOP Ctrl-C apres {n} sessions ===")


if __name__ == "__main__":
    if sys.platform != "win32":
        print("Bot Windows-only (utilise Win32 SendInput)")
        sys.exit(1)
    main()
