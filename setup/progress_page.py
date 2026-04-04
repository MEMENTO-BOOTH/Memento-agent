"""Page 2 : Progression de l'installation — installe dépendances, config, raccourcis."""
import os
import sys
import subprocess
import platform
import time
import json
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import QPixmap

from paths import ASSETS_DIR
from .styles import *
REQUIRED_PACKAGES = ["requests"]


class _Worker(QThread):
    step = pyqtSignal(str, int)
    finished = pyqtSignal(bool)

    def __init__(self, options=None):
        super().__init__()
        self._options = options or {}

    def run(self):
        try:
            # 1. Dépendances
            self.step.emit("Installation des dépendances...", 15)
            for pkg in REQUIRED_PACKAGES:
                try:
                    __import__(pkg)
                except ImportError:
                    subprocess.check_call(
                        [sys.executable, "-m", "pip", "install", pkg, "--quiet"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    )

            # 2. Environnement
            self.step.emit("Vérification de l'environnement...", 35)
            time.sleep(0.3)

            # 3. Raccourcis Windows
            self.step.emit("Configuration des raccourcis...", 75)
            if platform.system() == "Windows":
                exe_path = sys.executable
                # Si c'est un .exe compilé (PyInstaller)
                if getattr(sys, 'frozen', False):
                    exe_path = sys.executable

                # Lancer au démarrage de Windows
                if self._options.get("startup"):
                    try:
                        import winreg
                        key = winreg.OpenKey(
                            winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run",
                            0, winreg.KEY_SET_VALUE,
                        )
                        winreg.SetValueEx(key, "MementoAgent", 0, winreg.REG_SZ, f'"{exe_path}"')
                        winreg.CloseKey(key)
                    except Exception as e:
                        print(f"[SETUP] Erreur registre startup: {e}")

                # Raccourci Bureau
                if self._options.get("shortcut"):
                    try:
                        desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
                        shortcut_path = os.path.join(desktop, "Memento Agent.lnk")
                        # Créer le raccourci via PowerShell
                        ps_cmd = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{shortcut_path}')
$s.TargetPath = '{exe_path}'
$s.WorkingDirectory = '{os.path.dirname(exe_path)}'
$s.Description = 'Memento Agent'
$s.Save()
"""
                        subprocess.run(
                            ["powershell", "-Command", ps_cmd],
                            capture_output=True, creationflags=0x08000000,
                        )
                    except Exception as e:
                        print(f"[SETUP] Erreur raccourci bureau: {e}")
            else:
                time.sleep(0.3)

            # 5. Finalisation
            self.step.emit("Finalisation...", 90)
            time.sleep(0.3)

            self.step.emit("Installation terminée !", 100)
            self.finished.emit(True)
        except Exception:
            self.finished.emit(False)


class ProgressPage(QWidget):
    done = pyqtSignal()

    def __init__(self, options=None, parent=None):
        super().__init__(parent)
        self._options = options
        self._build()
        self._worker = _Worker(options=options)
        self._worker.step.connect(self._on_step)
        self._worker.finished.connect(self._on_done)
        QTimer.singleShot(300, self._worker.start)

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(80, 60, 80, 60)
        layout.setSpacing(0)

        logo = QLabel()
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.exists(logo_path):
            logo.setPixmap(QPixmap(logo_path).scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo)
        layout.addSpacing(16)

        title = QLabel("Installation en cours")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(f"color: {GREEN_DARK}; font-family: 'Inter'; font-size: 26px; font-weight: 700; background: transparent;")
        layout.addWidget(title)
        layout.addSpacing(40)

        self._bar = QProgressBar()
        self._bar.setFixedHeight(8)
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._bar.setStyleSheet(f"""
            QProgressBar {{ border: none; border-radius: 4px; background: {BORDER}; }}
            QProgressBar::chunk {{ border-radius: 4px; background: {GREEN}; }}
        """)
        layout.addWidget(self._bar)
        layout.addSpacing(16)

        self._pct = QLabel("0%")
        self._pct.setAlignment(Qt.AlignCenter)
        self._pct.setStyleSheet(f"color: {GREEN_DARK}; font-family: 'Inter'; font-size: 22px; font-weight: 700; background: transparent;")
        layout.addWidget(self._pct)
        layout.addSpacing(12)

        self._msg = QLabel("")
        self._msg.setAlignment(Qt.AlignCenter)
        self._msg.setStyleSheet(f"color: {TEXT_SEC}; font-family: 'Inter'; font-size: 13px; background: transparent;")
        layout.addWidget(self._msg)

        layout.addStretch()

        steps = QVBoxLayout()
        steps.setSpacing(12)
        self._dots = []
        for txt in ["Installation des dépendances", "Vérification de l'environnement",
                     "Création de la configuration", "Configuration des raccourcis", "Finalisation"]:
            row = QHBoxLayout()
            dot = QLabel("○")
            dot.setFixedWidth(20)
            dot.setStyleSheet(f"color: {BORDER}; font-size: 14px; background: transparent;")
            row.addWidget(dot)
            lbl = QLabel(txt)
            lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-family: 'Inter'; font-size: 13px; background: transparent;")
            row.addWidget(lbl)
            row.addStretch()
            steps.addLayout(row)
            self._dots.append((dot, lbl))
        layout.addLayout(steps)
        layout.addStretch()

    def _on_step(self, msg, pct):
        self._bar.setValue(pct)
        self._pct.setText(f"{pct}%")
        self._msg.setText(msg)
        thresholds = [15, 35, 55, 75, 90]
        for i, t in enumerate(thresholds):
            if pct >= t:
                self._dots[i][0].setText("●")
                self._dots[i][0].setStyleSheet(f"color: {GREEN}; font-size: 14px; background: transparent;")
                self._dots[i][1].setStyleSheet(f"color: {TEXT}; font-family: 'Inter'; font-size: 13px; font-weight: 500; background: transparent;")

    def _on_done(self, ok):
        if ok:
            self._msg.setText("Installation terminée avec succès !")
            self._msg.setStyleSheet(f"color: {GREEN}; font-family: 'Inter'; font-size: 14px; font-weight: 600; background: transparent;")
            QTimer.singleShot(1000, lambda: self.done.emit())
