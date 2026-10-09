"""
Memento Agent — Point d'entrée principal.

Flux :
  Premier lancement → Setup (config) → Dashboard
  Relancement       → LockScreen (PIN) → Dashboard
  Déconnexion       → LockScreen (PIN) — monitoring continue en fond
"""

import sys
import os

_log_dir = os.path.join(os.path.expanduser("~"), ".mementoagent")
os.makedirs(_log_dir, exist_ok=True)
_log_path = os.path.join(_log_dir, "crash.log")

def _log(msg):
    try:
        with open(_log_path, "a", encoding="utf-8") as f:
            from datetime import datetime
            f.write(f"{datetime.now():%H:%M:%S} {msg}\n")
    except Exception:
        pass

_log("=== START (import phase) ===")


def _boot_alertes_log():
    """Ecrit une ligne 'BOOT' dans alertes.log DES le lancement, avant tout
    autre import lourd. But : empecher le watchdog de tuer l'agent pendant
    la fenetre d'init (environ 60 a 90 s), qui autrement declenchait une
    boucle de kills -> accumulation de dossiers _MEI PyInstaller -> disque
    plein (observe MB-39 et MB-13, env 730 Go de _MEI)."""
    try:
        from datetime import datetime
        if hasattr(sys, 'frozen'):
            log_dir = os.path.dirname(sys.executable)
        else:
            log_dir = os.path.join(os.path.expanduser("~"), ".mementoagent")
        os.makedirs(log_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(os.path.join(log_dir, "alertes.log"), "a", encoding="utf-8") as f:
            f.write(f"[{ts}] [BOOT] agent demarre, init en cours\n\n")
    except Exception:
        pass


def _cleanup_mei_orphans():
    """Supprime les dossiers _MEI* orphelins (> 1 h) dans %TEMP%. PyInstaller
    (mode onefile) extrait son runtime la a chaque demarrage ; si l'agent est
    kill brutalement sans PortRelease du bootloader, le dossier reste (209 Mo
    par instance). Observe sur MB-39 : env 3500 dossiers = 730 Go. On nettoie
    au boot comme filet de securite (le watchdog nettoie aussi en v1.0.28.14)."""
    try:
        from datetime import datetime, timedelta
        import tempfile, shutil
        temp = tempfile.gettempdir()
        cutoff = datetime.now() - timedelta(hours=1)
        current_mei = getattr(sys, '_MEIPASS', None)
        n = 0
        for name in os.listdir(temp):
            if not name.startswith("_MEI"):
                continue
            full = os.path.join(temp, name)
            if full == current_mei:
                continue  # le notre, on ne touche pas
            try:
                if datetime.fromtimestamp(os.path.getctime(full)) >= cutoff:
                    continue
                shutil.rmtree(full, ignore_errors=True)
                n += 1
            except Exception:
                pass
        if n > 0:
            _log(f"_MEI cleanup: {n} dossier(s) orphelin(s) supprime(s)")
    except Exception as e:
        _log(f"_MEI cleanup: {e}")


# Ces deux appels doivent tourner le PLUS TOT possible pour maximiser la
# chance que le watchdog voie l'agent "vivant" avant son 1er check (3 min).
_boot_alertes_log()
_cleanup_mei_orphans()

import faulthandler
try:
    _faulthandler_log = open(os.path.join(_log_dir, "faulthandler.log"), "a", buffering=1)
    faulthandler.enable(file=_faulthandler_log)
    _log("faulthandler enabled")
except Exception as _e:
    _log(f"faulthandler enable failed: {_e}")

try:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QFontDatabase
    from PyQt5.QtNetwork import QLocalServer, QLocalSocket
    from PyQt5.QtCore import QObject, QEvent
    _log("PyQt5 imported OK")
except Exception as e:
    _log(f"FATAL: PyQt5 import failed: {e}")
    sys.exit(1)

from paths import ASSETS_DIR, reg_get, reg_set
_log("paths imported OK")

_SERVER_NAME = "MementoAgent_SingleInstance_v1"


def is_first_launch():
    if bool(reg_get("setup_done")):
        return False
    # Créer la borne en fond — ne pas bloquer le démarrage
    def _create_borne():
        try:
            import supabase_client as supa
            supa.get_or_create_borne()
        except Exception:
            pass
    from threading import Thread
    Thread(target=_create_borne, daemon=True).start()
    return True


def open_dashboard(app):
    """Ouvre le dashboard."""
    _log("open_dashboard called")
    from dashboard import DashboardWindow
    from auth import LockScreen

    # Passer le monitoring déjà démarré au dashboard
    dashboard = DashboardWindow(monitor=getattr(app, '_monitor', None))
    app._dashboard = dashboard
    app._lock = None
    _log("DashboardWindow created")

    def on_disconnect():
        import user_session
        user_session.clear()
        dashboard.hide()
        dashboard.close()
        dashboard.deleteLater()
        app._dashboard = None
        # Retour à la page PIN
        app._lock = LockScreen()
        screen = app.primaryScreen().availableGeometry()
        app._lock.setMinimumSize(min(1050, screen.width()), min(650, screen.height()))
        app._lock.resize(min(1184, screen.width()), min(780, screen.height()))
        app._lock.setWindowTitle("Memento Agent")
        app._lock.unlocked.connect(lambda: _reopen(app))
        app._lock.show()

    def _reopen(application):
        if application._lock:
            application._lock.close()
            application._lock.deleteLater()
            application._lock = None
        open_dashboard(application)

    dashboard._on_disconnect = on_disconnect
    dashboard.show()
    _log("dashboard.show() done")


def _force_foreground(w):
    """Sur Windows, SetForegroundWindow est bloque quand l'app n'a pas le focus.
    Bypass via AttachThreadInput/AllowSetForegroundWindow + SetForegroundWindow direct."""
    try:
        w.showNormal()
        w.raise_()
        w.activateWindow()
    except Exception:
        pass
    try:
        import ctypes
        hwnd = int(w.winId())
        if hwnd:
            user32 = ctypes.windll.user32
            SW_RESTORE = 9
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)  # HWND_TOPMOST, NOMOVE|NOSIZE|SHOWWINDOW
            user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0040)  # HWND_NOTOPMOST
            user32.SetForegroundWindow(hwnd)
    except Exception as e:
        _log(f"_force_foreground ctypes fail: {e}")


def _create_lock(app):
    """Cree (ou recree) la fenetre LockScreen. Utilise au boot ET par
    _show_from_tray quand la fenetre existante est zombie (winId == 0)."""
    from auth import LockScreen
    lock = LockScreen()
    screen = app.primaryScreen().availableGeometry()
    lock.setMinimumSize(min(1050, screen.width()), min(650, screen.height()))
    lock.resize(min(1184, screen.width()), min(780, screen.height()))
    lock.setWindowTitle("Memento Agent")
    lock.unlocked.connect(lambda: _reopen(app))
    return lock


def _show_from_tray(app):
    """Affiche la fenêtre principale (PIN, dashboard ou setup).

    Robuste au cas 'widget zombie' : l'attribut app._lock/dashboard/setup pointe
    vers un QWidget dont la fenetre native a ete detruite (winId()==0) apres un
    close+deleteLater precedent. Dans ce cas, showNormal() est un no-op silencieux
    et le user voit 'rien' quand il clique. On detecte et on recree.
    """
    for attr in ('_setup', '_dashboard', '_lock'):
        w = getattr(app, attr, None)
        if w is None:
            continue
        try:
            wid = int(w.winId())
        except Exception:
            wid = 0
        if wid:
            _force_foreground(w)
            _log(f"_show_from_tray: showed {attr} (winId={wid})")
            return
        _log(f"_show_from_tray: {attr} is zombie (winId=0), sera recree")

    # Aucune fenetre viable -> recreer LockScreen fraîche (fallback safe).
    try:
        app._lock = _create_lock(app)
        app._lock.show()
        _force_foreground(app._lock)
        _log("_show_from_tray: LockScreen recreee et affichee")
    except Exception as e:
        _log(f"_show_from_tray: recreation LockScreen echec: {e}")


def _check_single_instance(app):
    """Retourne True si c'est la première instance, False si une autre tourne déjà."""
    sock = QLocalSocket()
    sock.connectToServer(_SERVER_NAME)
    if sock.waitForConnected(500):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(500)
        sock.disconnectFromServer()
        _log("another instance detected — sent show signal")
        return False

    QLocalServer.removeServer(_SERVER_NAME)
    server = QLocalServer()
    if not server.listen(_SERVER_NAME):
        _log(f"QLocalServer listen failed: {server.errorString()}")
        return True

    def _on_new_conn():
        conn = server.nextPendingConnection()
        if conn is None:
            return
        _log("received activation from 2nd instance")
        _show_from_tray(app)
        conn.disconnectFromServer()

    server.newConnection.connect(_on_new_conn)
    app._server = server
    _log("QLocalServer listening — first instance")
    return True


class _HideOnClose(QObject):
    """Intercepte la croix rouge sur les fenêtres principales pour les cacher au lieu de quitter."""
    def __init__(self, app):
        super().__init__()
        self._app = app

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Close:
            if getattr(self._app, '_really_quit', False):
                return False
            class_name = type(obj).__name__
            if class_name in ('DashboardWindow', 'LockScreen'):
                obj.hide()
                event.ignore()
                return True
        return False


def _install_exception_hook():
    """Capte les exceptions main thread, threads Python et threads Qt.

    Incident REV3 22/06/2026 : agent mort silencieusement, aucune trace.
    Cause probable = exception dans un thread Qt non capturee par sys.excepthook.
    threading.excepthook (Python 3.8+) capte les threads Python ; pour les
    threads Qt on installe aussi un wrapper sur QThread.run."""
    import traceback as _tb
    import threading as _th

    def _log_exc(prefix, exc_type, exc_value, exc_tb):
        msg = "".join(_tb.format_exception(exc_type, exc_value, exc_tb))
        _log(f"{prefix}:\n{msg}")
        print(f"[{prefix}] {msg}")
        try:
            import activity_logger as _alog
            _alog.log_generic("CRASH", f"{prefix}: {msg[:500]}")
        except Exception:
            pass

    def _hook_main(exc_type, exc_value, exc_tb):
        _log_exc("UNHANDLED EXCEPTION", exc_type, exc_value, exc_tb)
    sys.excepthook = _hook_main

    def _hook_thread(args):
        _log_exc(
            f"UNHANDLED THREAD EXCEPTION ({args.thread.name})",
            args.exc_type, args.exc_value, args.exc_traceback,
        )
    _th.excepthook = _hook_thread


def _start_monitoring_early(app):
    """Démarre le monitoring AVANT l'écran PIN pour que les alertes, e-memento et drive fonctionnent immédiatement."""
    try:
        from monitoring import MonitoringEngine
        app._monitor = MonitoringEngine()
        app._monitor.alerte_critique.connect(lambda has: _on_early_critique(has))
        if hasattr(app, '_overlay_manager') and app._overlay_manager:
            app._monitor.print_started.connect(app._overlay_manager.on_print_started)
        app._monitor.start()
        _log("monitoring started (before PIN)")
    except Exception as e:
        _log(f"monitoring early start failed: {e}")
        app._monitor = None


def _setup_print_overlay(app):
    """Instancie le PrintOverlayManager — affichage overlay lors des impressions."""
    from monitoring.photo_app import is_kapsule_borne
    if is_kapsule_borne():
        # Borne Kapsule : Kapsule affiche son propre écran d'impression, et le
        # détecteur tiendrait le port DNP ouvert → conflit avec la coupe Kapsule.
        _log("borne Kapsule — print overlay désactivé")
        app._overlay_manager = None
        return
    try:
        from overlay import PrintOverlayManager
        app._overlay_manager = PrintOverlayManager()
        _log("print overlay manager created")
    except Exception as e:
        _log(f"print overlay init failed: {e}")
        app._overlay_manager = None


def _on_early_critique(has_critique):
    """Gère les alertes critiques même avant le dashboard."""
    from rupture_screen import show_rupture, hide_rupture
    if has_critique:
        show_rupture()
    else:
        hide_rupture()


def _setup_global_tray(app):
    """Crée le tray dès le démarrage pour que l'app tourne en fond même sur l'écran PIN."""
    from PyQt5.QtWidgets import QSystemTrayIcon, QMenu, QAction
    from PyQt5.QtGui import QIcon

    if not QSystemTrayIcon.isSystemTrayAvailable():
        _log("tray NOT available on this system")
        return

    icon_path = os.path.join(ASSETS_DIR, "logo.ico")
    icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()

    # Créer avec un parent (app ne marche pas, utiliser None mais stocker les refs)
    tray = QSystemTrayIcon(icon)
    tray_menu = QMenu()

    def _show_window():
        _show_from_tray(app)

    def _quit():
        app._really_quit = True
        if hasattr(app, '_monitor') and app._monitor and app._monitor.isRunning():
            app._monitor.stop()
            app._monitor.wait(3000)
        tray.hide()
        app.quit()

    act_show = tray_menu.addAction("Ouvrir Memento Agent")
    act_show.triggered.connect(_show_window)
    tray_menu.addSeparator()
    act_quit = tray_menu.addAction("Quitter")
    act_quit.triggered.connect(_quit)

    tray.setContextMenu(tray_menu)
    tray.setToolTip("Memento Agent — Monitoring actif")
    tray.activated.connect(lambda reason: _show_window() if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger) else None)
    tray.show()

    # Stocker tout pour éviter le garbage collection
    app._tray = tray
    app._tray_menu = tray_menu
    _log(f"tray created (global), visible={tray.isVisible()}")


def main():
    _log("main() enter")
    _install_exception_hook()
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # Ne pas quitter quand toutes les fenêtres sont fermées
    app._really_quit = False
    _log("QApplication created")

    # Empêche les doubles lancements — si une instance tourne, on la réveille puis on sort
    if not _check_single_instance(app):
        _log("exiting — another instance is running")
        sys.exit(0)

    # Croix rouge → cacher au lieu de fermer (l'app continue dans le tray)
    app._close_filter = _HideOnClose(app)
    app.installEventFilter(app._close_filter)
    _log("single-instance + close-filter installed")

    QFontDatabase.addApplicationFont(os.path.join(ASSETS_DIR, "Inter-Regular.ttf"))
    QFontDatabase.addApplicationFont(os.path.join(ASSETS_DIR, "Inter-SemiBold.ttf"))
    QFontDatabase.addApplicationFont(os.path.join(ASSETS_DIR, "Satoshi-Regular.ttf"))
    QFontDatabase.addApplicationFont(os.path.join(ASSETS_DIR, "Satoshi-Medium.ttf"))
    QFontDatabase.addApplicationFont(os.path.join(ASSETS_DIR, "Satoshi-Bold.ttf"))
    _log("fonts loaded")

    # Tray global — l'app tourne en fond même sur l'écran PIN
    _setup_global_tray(app)

    # Overlay d'impression — instance globale pour recevoir les signaux du monitoring
    _setup_print_overlay(app)

    first = is_first_launch()
    _log(f"is_first_launch = {first}")

    # Démarrer le monitoring AVANT le PIN (mais PAS avant le setup)
    if not first:
        _start_monitoring_early(app)

    if first:
        from setup import SetupWindow
        app._setup = SetupWindow()
        _log("SetupWindow created")

        def on_setup_done():
            _log("on_setup_done called")
            app._setup.close()
            app._setup.deleteLater()
            app._setup = None
            # Démarrer le monitoring APRÈS le setup (le nom est enregistré)
            _start_monitoring_early(app)
            open_dashboard(app)

        app._setup.setup_complete.connect(on_setup_done)
        app._setup.show()
        _log("setup.show() done")
    else:
        # Démarrer caché dans le tray — monitoring tourne en fond
        # L'utilisateur ouvre l'app via le tray ou l'icône du bureau
        from auth import LockScreen
        app._lock = LockScreen()
        screen = app.primaryScreen().availableGeometry()
        app._lock.setMinimumSize(min(1050, screen.width()), min(650, screen.height()))
        app._lock.resize(min(1184, screen.width()), min(780, screen.height()))
        app._lock.setWindowTitle("Memento Agent")

        def on_unlock():
            _log("on_unlock called")
            app._lock.close()
            app._lock.deleteLater()
            app._lock = None
            open_dashboard(app)

        app._lock.unlocked.connect(on_unlock)
        # Ne pas afficher la fenêtre au démarrage — rester dans le tray
        # L'utilisateur ouvre via le tray ou l'icône du bureau
        _log("app started hidden in tray")

    _log("entering app.exec_()")
    ret = app.exec_()
    _log(f"app.exec_() returned {ret}")
    sys.exit(ret)


if __name__ == "__main__":
    try:
        main()
    except SystemExit as e:
        _log(f"SystemExit: {e}")
    except Exception:
        import traceback
        _log("EXCEPTION:")
        with open(_log_path, "a", encoding="utf-8") as f:
            traceback.print_exc(file=f)
    _log("=== END ===")
