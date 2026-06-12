"""Tests printer_counter.

Couverture :
  - Bug 'ne s'empile plus' (plusieurs paiements rapproches)
  - Bug 1 : feuilles_apres null quand DLL injoignable
  - Bug 2 : ordre des valeurs feuilles_apres (oldest = highest)
  - Bug 4 : decalage TZ (paiement_at UTC vs datetime.now() local)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta, timezone
from collections import deque
from monitoring.printer_counter import PrinterCounterWatcher


class FakePrinter:
    """Imprimante simulee avec compteur controlable."""
    def __init__(self, initial=100, status=0x10001):
        self._counter = initial
        self._status = status  # 0x10001 = "En veille" par defaut
        self.h_port = 0
        self.dll = None
        self.name = "FAKE"
        self.port = "FAKE"

    def open(self):
        return True

    def read_counter(self):
        return self._counter

    def read_counter_and_status(self):
        return self._counter, self._status

    def close(self):
        pass

    def drop(self, n=1):
        self._counter -= n

    def set_status(self, status):
        self._status = status


class FakePrinterDead(FakePrinter):
    """Imprimante dont la DLL ne repond pas (simule un disconnect)."""
    def read_counter(self):
        return None

    def read_counter_and_status(self):
        return None, None


def make_watcher(printer):
    w = PrinterCounterWatcher.__new__(PrinterCounterWatcher)
    w._borne_id = "test-borne"
    w._nom_lieu = "Test Bar"
    w._printer = printer
    w._history = deque(maxlen=400)
    w._resolved = set()
    w._on_print_started = None
    w._last_status_code = None
    w._failed_events = []
    # Mock le POST printer_events pour ne pas taper Supabase pendant les tests
    w._post_event = lambda payload: True
    return w


def install_fakes(watcher, pending, patches_log):
    state = {"pending": list(pending)}

    def fake_fetch():
        return [tx for tx in state["pending"] if tx["id"] not in watcher._resolved]

    def fake_patch(tx_id, data):
        patches_log.append((tx_id, data))
        for tx in state["pending"]:
            if tx["id"] == tx_id:
                tx.update(data)
        return True

    def fake_alerte(tx_id, paiement_at=None):
        patches_log.append((tx_id, {"_alerte": "non_delivree"}))

    watcher._fetch_pending_transactions = fake_fetch
    watcher._patch = fake_patch
    watcher._creer_alerte_non_delivree = fake_alerte
    return state


def iso_utc(dt):
    """Format ISO UTC explicite, comme paiement_at en base."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# ===========================================================================
#  Tests anciens (empilement) — adaptes UTC
# ===========================================================================

def test_two_clients_one_print():
    """A et B paient. Une seule feuille sort. Seul A doit etre marque."""
    printer = FakePrinter(initial=100)
    w = make_watcher(printer)

    now = datetime.now(timezone.utc)
    pa_a = now - timedelta(seconds=10)
    pa_b = now - timedelta(seconds=5)

    w._history.append((pa_a - timedelta(seconds=1), 100))
    w._history.append((pa_b - timedelta(seconds=1), 100))

    pending = [
        {"id": "tx-A", "paiement_at": iso_utc(pa_a), "feuilles_avant": None},
        {"id": "tx-B", "paiement_at": iso_utc(pa_b), "feuilles_avant": None},
    ]
    patches = []
    install_fakes(w, pending, patches)

    printer.drop(1)
    w.tick()

    a_marked = any(p[0] == "tx-A" and p[1].get("impression_verifiee_papier") for p in patches)
    b_marked = any(p[0] == "tx-B" and p[1].get("impression_verifiee_papier") for p in patches)
    assert a_marked, "A devrait etre marque imprime"
    assert not b_marked, f"B NE devrait PAS etre marque. Patches: {patches}"
    print("[OK] test_two_clients_one_print")


def test_two_clients_two_prints_same_tick():
    """A et B paient. 2 baisses dans le tick. Les 2 marques sans anomalie."""
    printer = FakePrinter(initial=100)
    w = make_watcher(printer)

    now = datetime.now(timezone.utc)
    pa_a = now - timedelta(seconds=10)
    pa_b = now - timedelta(seconds=5)
    w._history.append((pa_a - timedelta(seconds=1), 100))
    w._history.append((pa_b - timedelta(seconds=1), 100))

    pending = [
        {"id": "tx-A", "paiement_at": iso_utc(pa_a), "feuilles_avant": None},
        {"id": "tx-B", "paiement_at": iso_utc(pa_b), "feuilles_avant": None},
    ]
    patches = []
    install_fakes(w, pending, patches)

    printer.drop(2)
    w.tick()

    a_marked = any(p[0] == "tx-A" and p[1].get("impression_verifiee_papier") for p in patches)
    b_marked = any(p[0] == "tx-B" and p[1].get("impression_verifiee_papier") for p in patches)
    a_anomalie = any(p[0] == "tx-A" and p[1].get("anomalie_impression") for p in patches)
    b_anomalie = any(p[0] == "tx-B" and p[1].get("anomalie_impression") for p in patches)
    assert a_marked and b_marked, "A et B devraient etre marques"
    assert not a_anomalie and not b_anomalie, "Pas d'anomalie pour 1 feuille chacun"
    print("[OK] test_two_clients_two_prints_same_tick")


def test_three_clients_one_print():
    """3 clients paient. 1 feuille sort. Seul le plus ancien est marque."""
    printer = FakePrinter(initial=100)
    w = make_watcher(printer)

    now = datetime.now(timezone.utc)
    pas = [now - timedelta(seconds=15-i*5) for i in range(3)]
    for pa in pas:
        w._history.append((pa - timedelta(seconds=1), 100))

    pending = [
        {"id": f"tx-{c}", "paiement_at": iso_utc(pas[i]), "feuilles_avant": None}
        for i, c in enumerate(["A", "B", "C"])
    ]
    patches = []
    install_fakes(w, pending, patches)

    printer.drop(1)
    w.tick()

    marked_ids = [p[0] for p in patches if p[1].get("impression_verifiee_papier")]
    assert marked_ids == ["tx-A"], f"Seul A devrait etre marque, got {marked_ids}"
    print("[OK] test_three_clients_one_print")


# ===========================================================================
#  Tests nouveaux fixes
# ===========================================================================

def test_bug2_feuilles_apres_in_correct_order():
    """Bug 2 : feuilles_apres pour le plus ancien doit etre le plus HAUT.
    Si A, B, C paient avec compteur a 100 puis baisse a 97 :
      - A imprime d'abord -> feuilles_apres = 99
      - B ensuite         -> feuilles_apres = 98
      - C en dernier      -> feuilles_apres = 97
    Avant le fix : A=97, B=98, C=99 (inverse)."""
    printer = FakePrinter(initial=100)
    w = make_watcher(printer)

    now = datetime.now(timezone.utc)
    pas = [now - timedelta(seconds=15-i*5) for i in range(3)]
    for pa in pas:
        w._history.append((pa - timedelta(seconds=1), 100))

    pending = [
        {"id": f"tx-{c}", "paiement_at": iso_utc(pas[i]), "feuilles_avant": None}
        for i, c in enumerate(["A", "B", "C"])
    ]
    patches = []
    install_fakes(w, pending, patches)

    printer.drop(3)  # 3 prints
    w.tick()

    # Extraire les feuilles_apres assignees (dernier patch par tx)
    feuilles_apres = {}
    for tx_id, data in patches:
        if "feuilles_apres" in data:
            feuilles_apres[tx_id] = data["feuilles_apres"]

    assert feuilles_apres.get("tx-A") == 99, f"A devrait avoir 99, got {feuilles_apres.get('tx-A')}"
    assert feuilles_apres.get("tx-B") == 98, f"B devrait avoir 98, got {feuilles_apres.get('tx-B')}"
    assert feuilles_apres.get("tx-C") == 97, f"C devrait avoir 97, got {feuilles_apres.get('tx-C')}"
    print(f"[OK] test_bug2_feuilles_apres_in_correct_order : A={feuilles_apres['tx-A']}, B={feuilles_apres['tx-B']}, C={feuilles_apres['tx-C']}")


def test_bug1_feuilles_apres_not_null_when_dll_dead():
    """Bug 1 : si DLL injoignable au tick deadline, feuilles_apres ne doit
    pas etre null. Fallback sur derniere valeur connue de l'historique."""
    printer = FakePrinterDead()  # DLL injoignable
    w = make_watcher(printer)

    # Historique avec une derniere valeur connue (lecture precedente reussie)
    last_known_ts = datetime.now(timezone.utc) - timedelta(seconds=300)
    w._history.append((last_known_ts, 150))  # derniere valeur connue = 150

    # Tx paye il y a > 180s -> deadline depassee
    now = datetime.now(timezone.utc)
    pa = now - timedelta(seconds=200)
    pending = [
        {"id": "tx-A", "paiement_at": iso_utc(pa), "feuilles_avant": 151},
    ]
    patches = []
    install_fakes(w, pending, patches)

    w.tick()

    # Le tick doit avoir marque non_delivree avec feuilles_apres = 150 (fallback)
    non_delivree_patches = [p for p in patches if p[1].get("anomalie_impression") == "non_delivree"]
    assert non_delivree_patches, "Devrait avoir une patch non_delivree"
    feuilles_apres = non_delivree_patches[0][1].get("feuilles_apres")
    assert feuilles_apres == 150, f"feuilles_apres devrait etre 150 (fallback historique), got {feuilles_apres}"
    print(f"[OK] test_bug1_feuilles_apres_not_null_when_dll_dead : feuilles_apres={feuilles_apres}")


def test_bug4_tz_no_false_non_delivree_on_fresh_tx():
    """Bug 4 : une tx fresh (10s) ne doit pas etre marquee non_delivree.
    Avant le fix : paiement_at UTC strippe vs datetime.now() local = +2h
    en CEST -> deadline 180s tirait immediatement."""
    printer = FakePrinter(initial=100)
    w = make_watcher(printer)

    now = datetime.now(timezone.utc)
    # Tx fresh, paye il y a 10s
    pa = now - timedelta(seconds=10)
    pending = [
        {"id": "tx-A", "paiement_at": iso_utc(pa), "feuilles_avant": 100},
    ]
    patches = []
    install_fakes(w, pending, patches)

    # Pas de baisse compteur (print pas encore sorti)
    w.tick()

    # Aucune patch ne doit avoir mis non_delivree
    non_delivree = [p for p in patches if p[1].get("anomalie_impression") == "non_delivree"]
    assert not non_delivree, f"Pas de non_delivree pour tx fresh. Patches: {patches}"
    print("[OK] test_bug4_tz_no_false_non_delivree_on_fresh_tx")


def test_bug4_tz_real_deadline_still_works():
    """Bug 4 : meme avec TZ fixe, une tx >180s sans baisse DOIT etre marquee
    non_delivree (regression check)."""
    printer = FakePrinter(initial=100)
    w = make_watcher(printer)

    now = datetime.now(timezone.utc)
    pa = now - timedelta(seconds=200)  # 200s > 180s
    pending = [
        {"id": "tx-A", "paiement_at": iso_utc(pa), "feuilles_avant": 100},
    ]
    patches = []
    install_fakes(w, pending, patches)

    w.tick()  # pas de baisse

    non_delivree = [p for p in patches if p[1].get("anomalie_impression") == "non_delivree"]
    assert non_delivree, f"Tx >180s sans baisse DOIT etre non_delivree. Patches: {patches}"
    feuilles_apres = non_delivree[0][1].get("feuilles_apres")
    assert feuilles_apres == 100, f"feuilles_apres devrait etre counter_now=100, got {feuilles_apres}"
    print(f"[OK] test_bug4_tz_real_deadline_still_works : non_delivree avec feuilles_apres={feuilles_apres}")


if __name__ == "__main__":
    test_two_clients_one_print()
    test_two_clients_two_prints_same_tick()
    test_three_clients_one_print()
    test_bug2_feuilles_apres_in_correct_order()
    test_bug1_feuilles_apres_not_null_when_dll_dead()
    test_bug4_tz_no_false_non_delivree_on_fresh_tx()
    test_bug4_tz_real_deadline_still_works()
    print("\nTous les tests OK !")
