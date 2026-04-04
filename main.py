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

try:
    from PyQt5.QtWidgets import QApplication
    from PyQt5.QtGui import QFontDatabase
    _log("PyQt5 imported OK")
except Exception as e:
    _log(f"FATAL: PyQt5 import failed: {e}")
    sys.exit(1)

from paths import ASSETS_DIR, reg_get, reg_set
_log("paths imported OK")


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

    dashboard = DashboardWindow()
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


def _install_exception_hook():
    """Installe un hook global pour que les exceptions Python
    ne tuent pas le process Qt (crash C++ silencieux)."""
    import traceback as _tb
    def _hook(exc_type, exc_value, exc_tb):
        msg = "".join(_tb.format_exception(exc_type, exc_value, exc_tb))
        _log(f"UNHANDLED EXCEPTION:\n{msg}")
        print(f"[EXCEPTION] {msg}")
    sys.excepthook = _hook


def main():
    _log("main() enter")
    _install_exception_hook()
    app = QApplication(sys.argv)
    _log("QApplication created")

    QFontDatabase.addApplicationFont(os.path.join(ASSETS_DIR, "Inter-Regular.ttf"))
    QFontDatabase.addApplicationFont(os.path.join(ASSETS_DIR, "Inter-SemiBold.ttf"))
    QFontDatabase.addApplicationFont(os.path.join(ASSETS_DIR, "Satoshi-Regular.ttf"))
    QFontDatabase.addApplicationFont(os.path.join(ASSETS_DIR, "Satoshi-Medium.ttf"))
    QFontDatabase.addApplicationFont(os.path.join(ASSETS_DIR, "Satoshi-Bold.ttf"))
    _log("fonts loaded")

    first = is_first_launch()
    _log(f"is_first_launch = {first}")

    if first:
        from setup import SetupWindow
        app._setup = SetupWindow()
        _log("SetupWindow created")

        def on_setup_done():
            _log("on_setup_done called")
            app._setup.close()
            open_dashboard(app)

        app._setup.setup_complete.connect(on_setup_done)
        app._setup.show()
        _log("setup.show() done")
    else:
        # Toujours afficher la page PIN pour identifier l'utilisateur
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
        app._lock.show()
        _log("lock.show() done")

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
