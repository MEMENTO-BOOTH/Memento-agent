"""Moteur de monitoring — tourne en arrière-plan dans l'agent.
Remplace les 4 scripts séparés (remontee, twilio, ememento_watcher, drive).
Lance le heartbeat + alertes + e-memento + drive backup dans un QThread."""

import os
import time
import socket
from PyQt5.QtCore import QThread, pyqtSignal
import supabase_client as supa
from .collectors import collecter_donnees, envoyer_heartbeat
from .alertes import verifier_alertes, HEARTBEAT_INTERVAL
from .coupe_2pouces import startup_hardware
from .emmento import EmentoWatcher, _expirer_anciens_codes
from .drive_backup import DriveBackup
from .cashinterface import CashInterfaceWatcher
from .printer_counter import PrinterCounterWatcher


class MonitoringEngine(QThread):
    """Thread principal de monitoring — collecte + heartbeat + alertes.

    Signaux émis :
        data_updated(dict)  — données collectées à chaque cycle
        alerte_created(str) — type de la nouvelle alerte
        error(str)          — message d'erreur
    """
    data_updated = pyqtSignal(object)
    alerte_created = pyqtSignal(str)
    alerte_changed = pyqtSignal()
    alerte_critique = pyqtSignal(bool)  # True = alerte critique, False = plus d'alertes
    error = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = True
        self._maintenance = False
        self._borne_id = None
        self._nom_lieu = None
        self._interval = HEARTBEAT_INTERVAL

    def set_maintenance(self, on):
        """Active/désactive le mode maintenance.
        En maintenance : heartbeat continue mais PAS de création d'alertes."""
        self._maintenance = on
        print(f"[MONITORING] Mode maintenance: {'ON' if on else 'OFF'}")

    def stop(self):
        self._running = False

    def run(self):
        # Attendre le réseau
        for i in range(30):
            if not self._running:
                return
            try:
                import requests
                requests.get(supa.SUPABASE_URL, timeout=5)
                break
            except Exception:
                time.sleep(2)

        # Identifier la borne
        borne = supa.get_borne()
        if not borne:
            self.error.emit("Impossible d'identifier la borne")
            return

        self._borne_id = borne["id"]
        self._nom_lieu = borne.get("nom_lieu", socket.gethostname())

        # Lire le statut maintenance depuis Supabase au démarrage
        if borne.get("statut") == "maintenance":
            self._maintenance = True
            print(f"[MONITORING] Mode maintenance actif (lu depuis Supabase)")

        print(f"[MONITORING] Borne: {self._nom_lieu} ({borne.get('code')})")
        print(f"[MONITORING] Intervalle: {self._interval}s")

        # Réactiver la coupe 2 pouces si le flag est actif
        startup_hardware()

        # Connecter les callbacks alertes → signaux Qt
        from .alertes.alertes_monitor import set_on_alerte_changed, set_on_alerte_critique
        set_on_alerte_changed(lambda: self.alerte_changed.emit())
        set_on_alerte_critique(self._on_critique)

        # Initialiser e-memento watcher + drive backup
        self._emmento = EmentoWatcher(self._borne_id)
        self._cash = CashInterfaceWatcher(self._borne_id)
        self._printer_counter = PrinterCounterWatcher(self._borne_id, self._nom_lieu)
        drive_folder = f"{self._nom_lieu} ({borne.get('code', socket.gethostname())})"
        self._drive = DriveBackup(drive_folder)
        print("[MONITORING] E-memento + CashInterface + PrinterCounter + Drive backup initialisés")

        # Expirer les anciens codes au démarrage
        try:
            _expirer_anciens_codes()
        except Exception:
            pass

        compteur = 0
        emmento_tick = 0
        update_check_interval = 360  # vérifier mise à jour toutes les 6 heures
        tx_check_interval = 1  # vérifier transactions à chaque cycle (60s)
        delai_demarrage = 3  # ignorer alertes crash pendant 3 cycles (3 min)
        self._last_tx_count = 0
        self._check_initial_tx()

        # Vérifier mise à jour dès le démarrage
        print("[MAJ] Vérification au démarrage...")
        try:
            self._auto_update()
            print("[MAJ] Vérification terminée")
        except Exception as e:
            print(f"[MAJ] Erreur au démarrage: {e}")
            import traceback
            traceback.print_exc()

        while self._running:
            compteur += 1
            try:
                # 1. Collecter les données
                donnees = collecter_donnees()

                # 2. Envoyer le heartbeat (UPSERT)
                ok = envoyer_heartbeat(self._borne_id, donnees)
                if ok:
                    print(f"[MONITORING] #{compteur} ✓ {donnees.get('imprimante_statut', '?')} | {donnees.get('feuilles_restantes', '?')} feuilles")
                else:
                    print(f"[MONITORING] #{compteur} ✗ Échec envoi heartbeat")

                # 3. Vérifier les alertes (SAUF en mode maintenance)
                if not self._maintenance:
                    # Pendant les 3 premières minutes, ignorer les crash dslrBooth/CashInterface
                    if compteur <= delai_demarrage:
                        donnees["dslrbooth_running"] = True
                        donnees["cash_interface_running"] = True
                    verifier_alertes(self._borne_id, self._nom_lieu, donnees)
                else:
                    print(f"[MONITORING] #{compteur} ⏸ Maintenance — alertes suspendues")

                # 4. Drive backup — scanner les nouveaux fichiers
                try:
                    self._drive.tick()
                except Exception as e:
                    print(f"[DRIVE] Erreur: {e}")

                # 5. Vérifier nouvelles transactions TPE (toutes les 5 min)
                if compteur % tx_check_interval == 0:
                    try:
                        self._check_new_transactions()
                    except Exception as e:
                        print(f"[TPE] Erreur: {e}")

                # 6. Émettre le signal pour mettre à jour l'UI
                self.data_updated.emit(donnees)

                # 6. Vérifier mise à jour automatique toutes les 6h
                if compteur % update_check_interval == 0:
                    try:
                        self._auto_update()
                    except Exception as e:
                        print(f"[MAJ] Erreur: {e}")

            except Exception as e:
                self.error.emit(str(e))
                print(f"[MONITORING] Erreur: {e}")

            # E-memento : scanner le log dslrBooth toutes les 3 secondes
            # (le heartbeat tourne toutes les 60s, mais e-memento doit être réactif)
            for sec in range(self._interval):
                if not self._running:
                    return
                time.sleep(1)
                emmento_tick += 1
                if emmento_tick >= 3:
                    emmento_tick = 0
                    try:
                        self._emmento.tick()
                    except Exception as e:
                        print(f"[EMMENTO] Erreur: {e}")
                    try:
                        self._cash.tick()
                    except Exception as e:
                        print(f"[CASH] Erreur: {e}")
                    try:
                        self._printer_counter.tick()
                    except Exception as e:
                        print(f"[PRINTER_COUNTER] Erreur: {e}")

        print(f"[MONITORING] Arrêté après {compteur} cycles.")

    def _on_critique(self, has_critique):
        self.alerte_critique.emit(has_critique)

    def _check_initial_tx(self):
        """Compte les transactions existantes au démarrage pour ne pas les afficher comme nouvelles."""
        for _ in range(3):
            try:
                tx = supa.get_transactions_today(self._borne_id)
                self._last_tx_count = len(tx) if tx else 0
                print(f"[TPE] Transactions existantes: {self._last_tx_count}")
                return
            except Exception:
                import time
                time.sleep(2)
        self._last_tx_count = 999  # Fallback — ne rien afficher

    def _check_new_transactions(self):
        """Vérifie s'il y a de nouvelles transactions et les affiche dans les logs."""
        try:
            tx = supa.get_transactions_today(self._borne_id)
            if not tx:
                return
            current_count = len(tx)
            if current_count <= self._last_tx_count:
                return

            # Nouvelles transactions
            import activity_logger as alog
            from dashboard import _utc_to_local
            new_tx = tx[:current_count - self._last_tx_count]
            for t in reversed(new_tx):
                ts = t.get("paiement_at", "")
                heure = _utc_to_local(ts).split(" ")[-1] if ts else "?"
                montant = float(t.get("montant", 0))
                ok = t.get("impression_declenchee", False)
                flag = t.get("flag", "")
                resumed = t.get("tpe_resumed_at")
                inhibited = t.get("tpe_inhibited_at")
                delai = t.get("delai_avant_inhibited")

                # Log RESUMED
                if resumed:
                    r_heure = _utc_to_local(resumed).split(" ")[-1]
                    # Pas dans ACTIVITÉ — uniquement dans tpe.log
                    alog.log_tpe_resumed(r_heure)

                # Log PAIEMENT
                statut = "Imprimé" if ok else f"Anomalie: {flag}" if flag else "En attente"
                # Pas dans ACTIVITÉ — uniquement dans tpe.log
                alog.log_tpe_transaction_supabase(self._borne_id, montant, ok, flag, resumed, inhibited, delai)

                # Log INHIBITED
                if inhibited:
                    i_heure = _utc_to_local(inhibited).split(" ")[-1]
                    delai_txt = f" ({delai}s)" if delai else ""
                    # Pas dans ACTIVITÉ — uniquement dans tpe.log
                    alog.log_tpe_inhibited(i_heure, delai)

                # Anomalie
                if not ok and flag:
                    alog.log_tpe_anomalie(t.get("id", "?"), flag)

            self._last_tx_count = current_count
        except Exception as e:
            print(f"[TPE] Erreur check transactions: {e}")

    def _log_maj(self, msg):
        """Log mise à jour dans un fichier dédié."""
        try:
            log_path = os.path.join(os.environ.get("LOCALAPPDATA", ""), "MementoAgent", "maj.log")
            with open(log_path, "a", encoding="utf-8") as f:
                from datetime import datetime
                f.write(f"{datetime.now().strftime('%H:%M:%S')} {msg}\n")
        except Exception:
            pass
        print(msg)

    def _auto_update(self):
        """Vérifie et installe automatiquement les mises à jour depuis GitHub."""
        import requests
        import tempfile
        import subprocess

        from version import VERSION

        self._log_maj(f"[MAJ] Verification... VERSION={VERSION} TOKEN={'OK' if supa.GITHUB_TOKEN else 'MANQUANT'}")
        release = supa.get_latest_github_release()
        self._log_maj(f"[MAJ] Release GitHub: {release.get('version') if release else 'RIEN'}")
        if not release:
            return

        latest = release.get("version", "")
        download_url = release.get("download_url", "")

        if not latest or latest == VERSION:
            self._log_maj(f"[MAJ] Deja a jour ({VERSION})")
            return

        # Comparer les versions numériquement pour éviter les downgrades
        def _parse_version(v):
            try:
                return [int(x) for x in v.split(".")]
            except (ValueError, AttributeError):
                return [0]

        if _parse_version(latest) <= _parse_version(VERSION):
            self._log_maj(f"[MAJ] Pas de mise a jour ({latest} <= {VERSION})")
            return

        if not download_url:
            return

        self._log_maj(f"[MAJ] Nouvelle version: {latest} (actuelle: {VERSION}), telechargement...")

        try:
            r = requests.get(download_url, timeout=120, stream=True, headers={
                "Authorization": f"token {supa.GITHUB_TOKEN}",
                "Accept": "application/octet-stream",
            })

            if r.status_code != 200:
                print(f"[MAJ] Erreur téléchargement: HTTP {r.status_code}")
                return

            tmp = tempfile.NamedTemporaryFile(suffix=".exe", delete=False)
            for chunk in r.iter_content(chunk_size=8192):
                tmp.write(chunk)
            tmp.close()

            # Vérifier que le fichier est un vrai .exe (> 1 Mo)
            if os.path.getsize(tmp.name) < 1_000_000:
                print(f"[MAJ] Fichier trop petit ({os.path.getsize(tmp.name)} octets), pas un .exe valide")
                os.unlink(tmp.name)
                return

            print(f"[MAJ] Téléchargé: {tmp.name} ({os.path.getsize(tmp.name)} octets)")

            # Lancer l'installeur silencieusement (/VERYSILENT pour Inno Setup)
            print(f"[MAJ] Installation silencieuse...")
            subprocess.Popen(
                [tmp.name, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"],
                shell=True,
            )

        except Exception as e:
            print(f"[MAJ] Erreur: {e}")