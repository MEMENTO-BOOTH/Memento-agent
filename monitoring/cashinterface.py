"""Watcher CashInterface — surveille le log pour détecter les paiements et impressions.
Lit le fichier log.txt de CashInterface et envoie les événements dans l'activité."""

import os
import re
from datetime import datetime

import supabase_client as supa

# Chemin du log CashInterface
CASHINTERFACE_LOG = os.path.join(
    os.environ.get("APPDATA", ""), "bksoft", "CI2Keystroke", "log.txt"
)

# Regex pour parser les lignes
RE_CREDIT_IN = re.compile(r"(\d{2}\.\d{2}\.\d{4}),(\d{2}:\d{2}:\d{2}),.*Credit IN=(\d+)")
RE_KEYSTROKE = re.compile(r"(\d{2}\.\d{2}\.\d{4}),(\d{2}:\d{2}:\d{2}),keystroke (\w) sent, credit left=(\d+)")
RE_CHARGE = re.compile(r"(\d{2}\.\d{2}\.\d{4}),(\d{2}:\d{2}:\d{2}),Charge costs=(\d+)")
RE_RECEIVER = re.compile(r"(\d{2}\.\d{2}\.\d{4}),(\d{2}:\d{2}:\d{2}),Receiver: (.+)")
RE_ERROR = re.compile(r"(\d{2}\.\d{2}\.\d{4}),(\d{2}:\d{2}:\d{2}),Error: (.+)")


def _parse_datetime(date_str, time_str):
    """Parse '02.04.2026' + '15:53:16' → datetime."""
    try:
        return datetime.strptime(f"{date_str} {time_str}", "%d.%m.%Y %H:%M:%S")
    except Exception:
        return None


class CashInterfaceWatcher:
    """Surveille le log CashInterface pour détecter paiements et impressions."""

    def __init__(self, borne_id):
        self._borne_id = borne_id
        self._position = 0
        # Démarrer à la fin du fichier
        try:
            if os.path.exists(CASHINTERFACE_LOG):
                self._position = os.path.getsize(CASHINTERFACE_LOG)
        except Exception:
            pass

    def tick(self):
        """Appelé toutes les 3 secondes par le monitoring."""
        if not os.path.exists(CASHINTERFACE_LOG):
            return

        try:
            taille = os.path.getsize(CASHINTERFACE_LOG)
            if taille < self._position:
                self._position = 0  # Rotation

            with open(CASHINTERFACE_LOG, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self._position)
                for ligne in f:
                    self._traiter_ligne(ligne.strip())
                self._position = f.tell()
        except Exception as e:
            print(f"[CASH] Erreur lecture log: {e}")

    def _traiter_ligne(self, ligne):
        if not ligne:
            return

        import activity_logger as alog

        # Credit IN = paiement reçu
        m = RE_CREDIT_IN.search(ligne)
        if m:
            date_str, time_str, montant_cents = m.group(1), m.group(2), m.group(3)
            montant = int(montant_cents) / 100.0
            dt = _parse_datetime(date_str, time_str)
            heure = dt.strftime("%H:%M:%S") if dt else time_str
            numero = None
            # Extraire le numéro de transaction si présent (ex: 000028)
            num_match = re.search(r",(\d{6}),Credit", ligne)
            if num_match:
                numero = num_match.group(1)
            # Pas dans ACTIVITÉ — uniquement dans tpe.log
            alog.log_tpe_paiement(montant_cents, heure, numero)
            return

        # Charge costs
        m = RE_CHARGE.search(ligne)
        if m:
            return  # Déjà logué avec Credit IN

        # Keystroke P sent = impression déclenchée
        m = RE_KEYSTROKE.search(ligne)
        if m:
            date_str, time_str, key, credit_left = m.group(1), m.group(2), m.group(3), m.group(4)
            dt = _parse_datetime(date_str, time_str)
            heure = dt.strftime("%H:%M:%S") if dt else time_str
            # Pas dans ACTIVITÉ — uniquement dans tpe.log
            alog.log_tpe_impression(key, credit_left, heure)
            self._confirmer_impression(dt)
            return

        # Receiver = envoi à dslrBooth
        m = RE_RECEIVER.search(ligne)
        if m:
            date_str, time_str = m.group(1), m.group(2)
            receiver = m.group(3).strip()
            heure = time_str
            alog.log_tpe_receiver(receiver, heure)
            return

        # CASH_TOTALBLOCKING — ignorer
        if "CASH_TOTALBLOCKING" in ligne:
            return

        # Erreur
        m = RE_ERROR.search(ligne)
        if m:
            error = m.group(3).strip()
            # Pas dans ACTIVITÉ — uniquement dans tpe.log
            alog.log_tpe_erreur(error)

    def _confirmer_impression(self, keystroke_dt):
        """Marque la dernière transaction comme imprimée dans Supabase."""
        if not self._borne_id:
            return
        try:
            import requests
            r = requests.get(
                f"{supa.SUPABASE_URL}/rest/v1/transactions"
                f"?borne_id=eq.{self._borne_id}"
                f"&impression_declenchee=eq.false"
                f"&order=paiement_at.desc&limit=1&select=id,paiement_at",
                headers=supa.HEADERS, timeout=5,
            )
            if r.status_code == 200 and r.json():
                tx_id = r.json()[0]["id"]
                # Vérifier que la transaction est récente (< 5 min)
                if keystroke_dt:
                    tx_time = r.json()[0].get("paiement_at", "")
                    if tx_time:
                        from datetime import timezone
                        try:
                            tx_dt = datetime.fromisoformat(tx_time.replace("+00:00", ""))
                            ecart = abs((keystroke_dt - tx_dt).total_seconds())
                            if ecart > 300:
                                return
                        except Exception:
                            pass

                requests.patch(
                    f"{supa.SUPABASE_URL}/rest/v1/transactions?id=eq.{tx_id}",
                    headers=supa.HEADERS_MINIMAL,
                    json={"impression_declenchee": True},
                    timeout=5,
                )
                import activity_logger as alog
                alog.log_tpe_confirmation(tx_id)
                # Pas dans ACTIVITÉ — uniquement dans tpe.log
                print(f"[CASH] Impression confirmée: {tx_id[:8]}")
        except Exception as e:
            print(f"[CASH] Erreur confirmation: {e}")
