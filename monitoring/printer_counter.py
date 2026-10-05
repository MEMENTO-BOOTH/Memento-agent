"""PrinterCounterWatcher - verification physique de l'impression via le compteur DNP DS620.

Principe
--------
La DLL Cx2Stat64 expose GetMediaCounter qui donne le nombre de feuilles restantes
sur le rouleau. Ce compteur decroit de 1 a chaque impression physique reelle
(papier effectivement consomme, pas juste "job envoye").

On maintient un historique glissant du compteur (dernieres 10 minutes) et on
detecte pour chaque transaction Nayax si le papier est reellement sorti dans
une fenetre de 180 secondes apres paiement_at.

Cas traites
-----------
- Baisse detectee dans la fenetre : impression_verifiee_papier=true + impression_declenchee=true
- Aucune baisse apres 180 s      : anomalie_impression='non_delivree' + alerte critique
- DLL injoignable                : on ne touche pas la transaction (fallback keystroke P existant)
- Baisses multiples pour 1 tx    : anomalie_impression='multiple'
- Photo-booth sans TPE           : baisse ignoree (pas de pending)

Integration
-----------
Tick toutes les 3 s dans MonitoringEngine (comme EmentoWatcher / CashWatcher).
"""

import os
import sys
import ctypes
import platform
from datetime import datetime, timedelta, timezone
from collections import deque

import requests
import supabase_client as supa
from .dnp_lock import DNP_PORT_LOCK


# --- Configuration ---------------------------------------------------
FENETRE_VERIFICATION_S = 180          # 3 min max entre paiement et sortie papier
HISTORIQUE_MAX_S = 600                # garder 10 min de compteur en RAM
TX_LOOKBACK_S = 300                   # transactions a prendre en compte (5 min)

# Garde-fou contre les fausses baisses du compteur (cf. bug DNP veille=0).
# DS620 imprime en ~10s/photo et on poll toutes les 3s -> drop physique max
# par tick = 1 ou 2 photos. Au-dela, c'est un retour de veille / lecture
# DLL aberrante -> on ignore (pas d'event printer_events).
MAX_DROP_PER_TICK = 20


# --- Localisation DLL et imprimante (reprise de collectors/printer.py) ---
def _find_dll():
    monitoring_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(monitoring_dir, "coupe_2pouces", "Cx2Stat64.dll"),
        os.path.join(monitoring_dir, "Cx2Stat64.dll"),
    ]
    if hasattr(sys, "_MEIPASS"):
        candidates.insert(
            0,
            os.path.join(sys._MEIPASS, "monitoring", "coupe_2pouces", "Cx2Stat64.dll"),
        )
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def _is_ds620(name):
    # IMPORTANT: ce watcher polle la DLL Cx2Stat64 toutes les 3s. On NE DOIT
    # appeler PortInitialize que sur une DS620 reellement supportee par la DLL.
    # Appeler sur DS-RX1 (ou autres DNP non-DS620) peut provoquer un segfault
    # natif qui tue le process agent entier (observe v1.0.28.9 sur MB-50).
    # On garde donc le filtrage specifique DS620 ici, pas la detection DNP
    # generique.
    from .alertes.constants import is_cx2stat_compatible
    return is_cx2stat_compatible(name)


class _PrinterHandle:
    """Encapsule la DLL et le handle port. Recree si disconnect."""

    def __init__(self):
        self.dll = None
        self.h_port = -1
        self.name = None
        self.port = None

    def open(self):
        if platform.system() != "Windows":
            return False
        if self.h_port >= 0:
            return True
        dll_path = _find_dll()
        if not dll_path:
            return False
        try:
            import winreg
            self.dll = ctypes.WinDLL(dll_path)
            self.dll.PortInitialize.argtypes = [ctypes.c_wchar_p]
            self.dll.PortInitialize.restype = ctypes.c_int
            self.dll.GetStatus.argtypes = [ctypes.c_int]
            self.dll.GetStatus.restype = ctypes.c_uint
            self.dll.GetMediaCounter.argtypes = [ctypes.c_int]
            self.dll.GetMediaCounter.restype = ctypes.c_int

            reg_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Print\Printers"
            candidats = []
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                for i in range(100):
                    try:
                        name = winreg.EnumKey(key, i)
                        if _is_ds620(name):
                            with winreg.OpenKey(
                                winreg.HKEY_LOCAL_MACHINE, f"{reg_path}\\{name}"
                            ) as pk:
                                port, _ = winreg.QueryValueEx(pk, "Port")
                                candidats.append((name, port))
                    except OSError:
                        break

            # PortInitialize + PortRelease serialises via DNP_PORT_LOCK pour
            # ne pas entrer en conflit avec le collector heartbeat. Sans ce
            # lock, quand printer_counter poll toutes les 3s et que le
            # heartbeat tombe pile au meme moment, l'un des deux echoue et
            # l'agent conclut a une 'Imprimante deconnectee' (fausse alerte).
            with DNP_PORT_LOCK:
                for name, port in candidats:
                    h = self.dll.PortInitialize(port)
                    if h >= 0 and self.dll.GetStatus(h) != 0x80000000:
                        self.name = name
                        self.port = port
                        self.h_port = h
                        return True
                    if h >= 0:
                        try:
                            self.dll.PortRelease(h)
                        except Exception:
                            pass
            return False
        except Exception as e:
            print(f"[PRINTER_COUNTER] Erreur init DLL: {e}")
            return False

    def read_counter(self):
        """Retourne le compteur feuilles_restantes ou None si indisponible.
        Ouvre et ferme le port a chaque lecture pour ne pas bloquer l'impression."""
        c, _ = self.read_counter_and_status()
        return c

    def read_counter_and_status(self):
        """Retourne (compteur, status) ou (None, None) si indisponible.
        Une seule ouverture/fermeture du port pour les 2 valeurs.
        - status = bitfield brut DNP (cf STATUS_MAP de constants.py).
        - 0x80000000 = imprimante en erreur generale -> None.

        Bug DNP : quand l'imprimante est en veille / sommeil, GetMediaCounter
        renvoie 0 au lieu du vrai compteur. Si on le considere valide,
        on calcule un faux drop massif (ex: 353 -> 0 = 353 photos sorties).
        Resultat observe sur Latina Cafe le 14/06 : 3566 photos faussement
        comptees pour ~10 vraies sorties. -> on filtre counter <= 0 = None.

        Toute la sequence open+read+close tourne sous DNP_PORT_LOCK pour
        que le collector heartbeat ne tente pas de PortInitialize pendant
        qu'on tient le port (sinon il conclut a une deconnexion).
        """
        with DNP_PORT_LOCK:
            if not self.open():
                return None, None
            try:
                counter = self.dll.GetMediaCounter(self.h_port)
                status = self.dll.GetStatus(self.h_port)
                self.close()
                return (
                    counter if counter > 0 else None,
                    status if status != 0x80000000 else None,
                )
            except Exception:
                self.close()
                return None, None

    def close(self):
        with DNP_PORT_LOCK:
            if self.dll and self.h_port >= 0:
                try:
                    self.dll.PortRelease(self.h_port)
                except Exception:
                    pass
            self.h_port = -1


# --- Watcher principal -----------------------------------------------
class PrinterCounterWatcher:
    """Surveille le compteur DS620 et reconcilie avec les transactions Supabase.

    Flux (tick toutes les 3 s) :
      1. Lit compteur, ajoute a l'historique glissant
      2. Charge transactions des 5 dernieres minutes (impression_verifiee_papier=false)
      3. Pour chaque tx :
         - Si pas encore feuilles_avant : snapshot depuis historique au paiement_at
         - Si baisse detectee depuis paiement_at : PATCH verifiee=true + declenchee=true
         - Si deadline depassee : PATCH anomalie='non_delivree' + alerte
    """

    def __init__(self, borne_id, nom_lieu=None, on_print_started=None):
        self._borne_id = borne_id
        self._nom_lieu = nom_lieu or ""
        self._printer = _PrinterHandle()
        # Historique : deque de (datetime_utc, compteur)
        self._history = deque(maxlen=400)  # ~20 min a 3s
        # Memo des transactions deja resolues pour eviter logs en double
        self._resolved = set()
        # Callback declenche quand le compteur baisse (impression physique detectee)
        self._on_print_started = on_print_started
        # printer_events : derniere valeur de statut connue (pour detecter les
        # transitions = un event seulement quand ca change, pas a chaque tick).
        self._last_status_code = None
        # Buffer des events qui ont rate leur POST (reseau coupe, Supabase
        # injoignable...). Reessaye au tick suivant. Cap a 100 pour eviter
        # une fuite memoire en cas d'incident reseau prolonge.
        self._failed_events = []

    def set_on_print_started(self, cb):
        self._on_print_started = cb

    # --- Lecture compteur & historique -------------------------------
    def _tick_counter(self):
        counter, status = self._printer.read_counter_and_status()
        # Historique en UTC tz-aware : paiement_at est UTC en base, donc le
        # lookup _counter_at(paiement_at) doit comparer des datetimes dans
        # le meme referentiel sinon decalage de 2h (= CEST). Cf. Bug 4.
        now = datetime.now(timezone.utc)

        # Detecter baisse compteur = photo physiquement sortie
        drop = 0
        if counter is not None and self._history and counter < self._history[-1][1]:
            drop = self._history[-1][1] - counter
            # Garde-fou : un drop trop gros est physiquement impossible
            # (DS620 imprime ~10s/photo, on lit toutes les 3s). Cause typique :
            # retour de veille ou lecture DLL aberrante apres un counter=0
            # passe au travers du filtre. On ignore et on ne contamine pas
            # l'historique (sinon le tick suivant repropage la fausse baisse).
            if drop > MAX_DROP_PER_TICK:
                print(
                    f"[PRINTER_COUNTER] drop ignore = {drop} (>{MAX_DROP_PER_TICK}), "
                    f"counter={counter}, last={self._history[-1][1]}"
                )
                return counter
            if self._on_print_started:
                try:
                    self._on_print_started()
                except Exception as e:
                    print(f"[PRINTER_COUNTER] on_print_started error: {e}")

        if counter is not None:
            self._history.append((now, counter))
            # Nettoyage > HISTORIQUE_MAX_S
            cutoff = now - timedelta(seconds=HISTORIQUE_MAX_S)
            while self._history and self._history[0][0] < cutoff:
                self._history.popleft()

        # printer_events : log d'evenement event-based pour la table d'historique
        # imprimante. Une ligne soit a chaque baisse de compteur (= photo
        # physique sortie), soit a chaque changement de statut. Permet au
        # dashboard d'afficher l'etat exact au moment de chaque photo (pas
        # juste 'Impression') et de tracer les sorties non payees (tests).
        status_changed = (status is not None and status != self._last_status_code)
        if drop > 0 or status_changed:
            self._log_printer_event(now, counter, drop, status)
        if status is not None:
            self._last_status_code = status

        # Retry des events qui ont rate (au cas ou Supabase etait injoignable)
        if self._failed_events:
            self._flush_failed_events()

        return counter

    # --- printer_events : historique imprimante event-based ----------
    def _statut_clair(self, status_code):
        """Decode le bitfield DNP en texte humain via STATUS_MAP."""
        from .alertes.constants import STATUS_MAP
        if status_code is None:
            return "Inconnu"
        return STATUS_MAP.get(status_code, f"Code non mappe (0x{status_code:08X})")

    def _log_printer_event(self, ts_utc, counter, drop, status_code):
        """Construit le payload et tente le POST. En cas d'echec, bufferise."""
        if not self._borne_id:
            return
        payload = {
            "borne_id": self._borne_id,
            "timestamp": ts_utc.isoformat(),
            "feuilles_restantes": counter,
            "photos_sorties": drop,
            "imprimante_statut": self._statut_clair(status_code),
        }
        if not self._post_event(payload):
            self._failed_events.append(payload)
            # Cap : on garde les 100 plus recents en cas de panne reseau longue
            if len(self._failed_events) > 100:
                self._failed_events = self._failed_events[-100:]

    def _post_event(self, payload):
        """POST silencieux sur printer_events. Retourne True si succes."""
        try:
            r = requests.post(
                f"{supa.SUPABASE_URL}/rest/v1/printer_events",
                headers=supa.HEADERS_MINIMAL,
                json=payload,
                timeout=3,
            )
            return r.status_code in (200, 201, 204)
        except Exception:
            return False

    def _flush_failed_events(self):
        """Retry les events bufferises. Garde ceux qui echouent encore."""
        still_failing = []
        for ev in self._failed_events:
            if not self._post_event(ev):
                still_failing.append(ev)
        self._failed_events = still_failing

    def tick_counter_only(self):
        """Poll rapide du compteur uniquement (pour overlay reactif).
        N'effectue aucun appel Supabase, ne fait que detecter la baisse."""
        self._tick_counter()

    def _counter_at(self, ts_utc):
        """Retourne le compteur connu au plus proche (avant ou egal) de ts_utc.
        None si historique ne remonte pas assez loin."""
        best = None
        for t, v in self._history:
            if t <= ts_utc:
                best = v
            else:
                break
        return best

    # --- Supabase ----------------------------------------------------
    def _fetch_pending_transactions(self):
        cutoff = (
            datetime.now().astimezone() - timedelta(seconds=TX_LOOKBACK_S)
        ).isoformat().replace("+", "%2B")
        try:
            r = requests.get(
                f"{supa.SUPABASE_URL}/rest/v1/transactions"
                f"?borne_id=eq.{self._borne_id}"
                f"&impression_verifiee_papier=eq.false"
                f"&anomalie_impression=is.null"
                f"&paiement_at=gte.{cutoff}"
                f"&montant=gt.0"
                f"&order=paiement_at.asc"
                f"&select=id,paiement_at,feuilles_avant,carte_4_derniers",
                headers=supa.HEADERS, timeout=5,
            )
            if r.status_code == 200:
                return r.json() or []
        except Exception as e:
            print(f"[PRINTER_COUNTER] Erreur fetch tx: {e}")
        return []

    def _patch(self, tx_id, data):
        try:
            requests.patch(
                f"{supa.SUPABASE_URL}/rest/v1/transactions?id=eq.{tx_id}",
                headers=supa.HEADERS_MINIMAL,
                json=data,
                timeout=5,
            )
            return True
        except Exception as e:
            print(f"[PRINTER_COUNTER] Erreur PATCH {tx_id[:8]}: {e}")
            return False

    def _creer_alerte_non_delivree(self, tx_id, carte_4_derniers=None, paiement_at=None):
        bar = self._nom_lieu or "la borne"
        suffixe_carte = f" (**{carte_4_derniers})" if carte_4_derniers else ""
        if paiement_at is not None:
            local = paiement_at.astimezone() if paiement_at.tzinfo else paiement_at
            heure = local.strftime("%H:%M")
        else:
            heure = datetime.now().strftime("%H:%M")
        message = f"Un client{suffixe_carte} a paye sur {bar} a {heure} mais sa photo n'est pas sortie de l'imprimante."
        try:
            import requests
            payload = {
                "borne_id": self._borne_id,
                "type": "impression_non_delivree",
                "source": "printer_counter",
                "message": message,
                "gravite": "critique",
                "statut": "ouverte",
                "timestamp": datetime.now().astimezone().isoformat(),
            }
            requests.post(
                f"{supa.SUPABASE_URL}/rest/v1/alertes",
                headers=supa.HEADERS_MINIMAL,
                json=payload,
                timeout=10,
            )
            import activity_logger as alog
            alog.ui_alerte(
                message,
                "icon_impression_non_delivree.svg",
                resolved=False,
            )
            print(f"[PRINTER_COUNTER] Alerte creee pour tx {tx_id[:8]}")
        except Exception as e:
            print(f"[PRINTER_COUNTER] Erreur creation alerte: {e}")

    # --- Tick principal ----------------------------------------------
    def tick(self):
        """Appele toutes les 3 s par MonitoringEngine.

        Algo en 3 phases pour eviter plusieurs bugs historiques :

          Phase 1 — Snapshot feuilles_avant manquant pour chaque pending.
                    On le fait separement de la marquage pour pouvoir
                    pre-calculer combien de tx vont etre marquees.

          Phase 2 — Decider combien de tx marquer comme imprimees (oldest
                    first). On itere et incremente un compteur de feuilles
                    deja attribuees aux plus anciennes : ca empeche le bug
                    'ne s'empile plus' (toutes les pending marquees d'un coup
                    a la 1ere baisse) tout en respectant l'ordre FIFO.

          Phase 3 — Marquer : la feuille la plus haute pour la tx la plus
                    ancienne (Bug 2 fixe — avant, l'ordre etait inverse).

        Bugs traites au passage :
          - Bug 1 : feuilles_apres = None quand DLL injoignable au tick
                    deadline -> fallback sur la derniere valeur connue de
                    l'historique, sinon on omet la cle.
          - Bug 4 : paiement_at est UTC, datetime.now() etait local Paris
                    -> ecart gonfle de 2h -> deadline 180s tirait toujours.
                    Tout est desormais tz-aware en UTC.
        """
        counter_now = self._tick_counter()

        pending = self._fetch_pending_transactions()
        if not pending:
            return

        now_utc = datetime.now(timezone.utc)

        # Parser paiement_at en tz-aware (Bug 4 : avant on strippait la tz et
        # on comparait a un local naive -> 2h de decalage en CEST).
        parsed = []
        for tx in pending:
            if tx["id"] in self._resolved:
                continue
            paiement_at_str = tx.get("paiement_at") or ""
            try:
                clean = paiement_at_str.replace("Z", "+00:00")
                paiement_at = datetime.fromisoformat(clean)
                if paiement_at.tzinfo is None:
                    # Format inattendu sans tz : on assume UTC (paiement_at
                    # est stocke en UTC en base Supabase).
                    paiement_at = paiement_at.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            parsed.append((tx, paiement_at))

        if not parsed:
            return

        # --- Phase 1 : snapshot feuilles_avant manquant ---
        if counter_now is not None:
            for tx, paiement_at in parsed:
                if tx.get("feuilles_avant") is None:
                    ref = self._counter_at(paiement_at)
                    if ref is None:
                        ref = counter_now
                    self._patch(tx["id"], {"feuilles_avant": ref})
                    tx["feuilles_avant"] = ref

        # --- Phase 2 : combien de tx marquer (oldest first) ---
        to_mark = []
        if counter_now is not None:
            for tx, paiement_at in parsed:
                feuilles_avant = tx.get("feuilles_avant")
                if feuilles_avant is None:
                    break
                # Compteur 'effectif' : decremente d'autant que de tx deja
                # marquees dans CE tick. Quand plusieurs paiements en rafale
                # ont le meme feuilles_avant, ca repartit la baisse globale
                # une feuille a la fois sur les plus anciennes.
                effective_counter = counter_now + len(to_mark)
                baisse = feuilles_avant - effective_counter
                if baisse >= 1:
                    to_mark.append((tx, paiement_at))
                else:
                    # Les tx suivantes (asc) auraient effective_counter encore
                    # plus haut -> baisse encore plus negative -> break.
                    break

        # --- Phase 3 : marquer to_mark avec feuilles_apres descendant ---
        # Plus ancienne = plus haute valeur (juste apres la 1ere impression).
        # Plus recente = plus basse valeur (= counter_now actuel).
        nb = len(to_mark)
        marked_ids = set()
        for i, (tx, _) in enumerate(to_mark):
            feuilles_apres = counter_now + (nb - 1 - i)
            self._patch(tx["id"], {
                "feuilles_apres": feuilles_apres,
                "impression_verifiee_papier": True,
                "impression_declenchee": True,
                "anomalie_impression": None,
            })
            self._resolved.add(tx["id"])
            marked_ids.add(tx["id"])
            import activity_logger as alog
            alog.log_tpe_confirmation(tx["id"])
            print(
                f"[PRINTER_COUNTER] Impression verifiee {tx['id'][:8]} "
                f"({tx.get('feuilles_avant')}->{feuilles_apres})"
            )

        # --- Phase 4 : deadline pour les non marquees ---
        for tx, paiement_at in parsed:
            tx_id = tx["id"]
            if tx_id in marked_ids or tx_id in self._resolved:
                continue
            ecart = (now_utc - paiement_at).total_seconds()
            if ecart > FENETRE_VERIFICATION_S:
                # Bug 1 : ne pas ecrire null si DLL injoignable. On retombe
                # sur la derniere valeur connue de l'historique. Si on a
                # vraiment rien (process qui vient de demarrer), on omet la
                # cle plutot que d'ecrire null.
                last_known = counter_now
                if last_known is None and self._history:
                    last_known = self._history[-1][1]
                data = {"anomalie_impression": "non_delivree"}
                if last_known is not None:
                    data["feuilles_apres"] = last_known
                self._patch(tx_id, data)
                self._resolved.add(tx_id)
                self._creer_alerte_non_delivree(tx_id, tx.get("carte_4_derniers"), paiement_at)
                print(
                    f"[PRINTER_COUNTER] NON DELIVREE {tx_id[:8]} "
                    f"(feuilles_apres={last_known}, deadline depassee de "
                    f"{ecart-FENETRE_VERIFICATION_S:.0f}s)"
                )

    def close(self):
        self._printer.close()