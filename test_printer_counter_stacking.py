"""Test du fix 'ne s'empile plus' dans printer_counter.

Reproduit le scenario bug :
  - 2 clients paient coup sur coup
  - feuilles_avant snapshot identique pour les 2 (compteur n'a pas bouge)
  - Compteur baisse de 1 (impression du client A uniquement)
  - Avant le fix : A et B sont tous les deux marques imprimes (BUG)
  - Apres le fix : seul A est marque imprime (B reste pending)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
from collections import deque
from monitoring.printer_counter import PrinterCounterWatcher


class FakePrinter:
    """Imprimante simulee avec compteur controlable."""
    def __init__(self, initial=100):
        self._counter = initial
        self.h_port = 0  # >= 0 pour bypass open()
        self.dll = None
        self.name = "FAKE"
        self.port = "FAKE"

    def open(self):
        return True

    def read_counter(self):
        return self._counter

    def close(self):
        pass

    def drop(self, n=1):
        self._counter -= n


def make_watcher(printer):
    w = PrinterCounterWatcher.__new__(PrinterCounterWatcher)
    w._borne_id = "test-borne"
    w._nom_lieu = "Test Bar"
    w._printer = printer
    w._history = deque(maxlen=400)
    w._resolved = set()
    w._on_print_started = None
    return w


def install_fakes(watcher, pending, patches_log):
    """Remplace _fetch_pending et _patch par des fakes en memoire."""
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


def iso(dt):
    return dt.isoformat()


def test_two_clients_one_print():
    """A et B paient. Une seule feuille sort. Seul A doit etre marque."""
    printer = FakePrinter(initial=100)
    w = make_watcher(printer)

    now = datetime.now()
    pa_a = now - timedelta(seconds=10)  # paye il y a 10s
    pa_b = now - timedelta(seconds=5)   # paye il y a 5s

    # Historique du compteur : 100 au moment des 2 paiements
    w._history.append((pa_a - timedelta(seconds=1), 100))
    w._history.append((pa_b - timedelta(seconds=1), 100))

    pending = [
        {"id": "tx-A", "paiement_at": iso(pa_a), "feuilles_avant": None},
        {"id": "tx-B", "paiement_at": iso(pa_b), "feuilles_avant": None},
    ]
    patches = []
    install_fakes(w, pending, patches)

    # Simule baisse du compteur (impression A)
    printer.drop(1)
    w.tick()

    # Verifs : A doit etre verifie + imprime, B ne doit pas
    a_marked = any(p[0] == "tx-A" and p[1].get("impression_verifiee_papier") for p in patches)
    b_marked = any(p[0] == "tx-B" and p[1].get("impression_verifiee_papier") for p in patches)

    assert a_marked, "A devrait etre marque imprime"
    assert not b_marked, f"B NE devrait PAS etre marque imprime. Patches: {patches}"
    print("[OK] test_two_clients_one_print : A marque, B reste pending")


def test_two_clients_two_prints_same_tick():
    """A et B paient. Le compteur baisse de 2 dans le meme tick. Les 2 doivent etre marques."""
    printer = FakePrinter(initial=100)
    w = make_watcher(printer)

    now = datetime.now()
    pa_a = now - timedelta(seconds=10)
    pa_b = now - timedelta(seconds=5)

    w._history.append((pa_a - timedelta(seconds=1), 100))
    w._history.append((pa_b - timedelta(seconds=1), 100))

    pending = [
        {"id": "tx-A", "paiement_at": iso(pa_a), "feuilles_avant": None},
        {"id": "tx-B", "paiement_at": iso(pa_b), "feuilles_avant": None},
    ]
    patches = []
    install_fakes(w, pending, patches)

    printer.drop(2)
    w.tick()

    a_marked = any(p[0] == "tx-A" and p[1].get("impression_verifiee_papier") for p in patches)
    b_marked = any(p[0] == "tx-B" and p[1].get("impression_verifiee_papier") for p in patches)
    a_multiple = any(p[0] == "tx-A" and p[1].get("anomalie_impression") == "multiple" for p in patches)
    b_multiple = any(p[0] == "tx-B" and p[1].get("anomalie_impression") == "multiple" for p in patches)

    assert a_marked, "A devrait etre marque"
    assert b_marked, "B devrait etre marque"
    assert not a_multiple, "A ne devrait PAS avoir anomalie multiple (B est derriere)"
    assert not b_multiple, "B ne devrait PAS avoir anomalie multiple (1 feuille chacun)"
    print("[OK] test_two_clients_two_prints_same_tick : A et B marques sans anomalie")


def test_one_client_two_sheets_no_false_multiple():
    """1 seul client, 2 feuilles consommees. La detection 'multiple' est desactivee
    pour eviter les faux positifs (cf. commentaire dans tick). On verifie juste
    que la tx est marquee imprimee sans anomalie."""
    printer = FakePrinter(initial=100)
    w = make_watcher(printer)

    now = datetime.now()
    pa_a = now - timedelta(seconds=10)
    w._history.append((pa_a - timedelta(seconds=1), 100))

    pending = [
        {"id": "tx-A", "paiement_at": iso(pa_a), "feuilles_avant": None},
    ]
    patches = []
    install_fakes(w, pending, patches)

    printer.drop(2)
    w.tick()

    a_marked = any(p[0] == "tx-A" and p[1].get("impression_verifiee_papier") for p in patches)
    a_anomalie = any(p[0] == "tx-A" and p[1].get("anomalie_impression") for p in patches)
    assert a_marked, "A devrait etre marque imprime"
    assert not a_anomalie, "A ne doit PAS avoir d'anomalie auto (faux positifs evites)"
    print("[OK] test_one_client_two_sheets_no_false_multiple : marque sans anomalie")


def test_sequential_ticks_two_clients():
    """Tick 1: 1 baisse -> A marque. Tick 2: 1 baisse -> B marque."""
    printer = FakePrinter(initial=100)
    w = make_watcher(printer)

    now = datetime.now()
    pa_a = now - timedelta(seconds=10)
    pa_b = now - timedelta(seconds=5)
    w._history.append((pa_a - timedelta(seconds=1), 100))
    w._history.append((pa_b - timedelta(seconds=1), 100))

    pending = [
        {"id": "tx-A", "paiement_at": iso(pa_a), "feuilles_avant": None},
        {"id": "tx-B", "paiement_at": iso(pa_b), "feuilles_avant": None},
    ]
    patches = []
    install_fakes(w, pending, patches)

    # Tick 1 : impression A
    printer.drop(1)
    w.tick()

    # Tick 2 : impression B
    printer.drop(1)
    w.tick()

    a_marked = any(p[0] == "tx-A" and p[1].get("impression_verifiee_papier") for p in patches)
    b_marked = any(p[0] == "tx-B" and p[1].get("impression_verifiee_papier") for p in patches)
    b_anomalie = any(p[0] == "tx-B" and p[1].get("anomalie_impression") for p in patches)

    assert a_marked, "A devrait etre marque"
    assert b_marked, "B devrait etre marque (tick 2)"
    # B ne doit PAS avoir 'multiple' juste parce que A a consomme 1 feuille avant
    assert not b_anomalie, f"B ne doit PAS avoir d'anomalie. Patches: {patches}"
    print("[OK] test_sequential_ticks_two_clients : A puis B marques sans faux multiple")


def test_three_clients_one_print():
    """3 clients paient. 1 feuille sort. Seul le plus ancien est marque."""
    printer = FakePrinter(initial=100)
    w = make_watcher(printer)

    now = datetime.now()
    pa_a = now - timedelta(seconds=15)
    pa_b = now - timedelta(seconds=10)
    pa_c = now - timedelta(seconds=5)
    for pa in (pa_a, pa_b, pa_c):
        w._history.append((pa - timedelta(seconds=1), 100))

    pending = [
        {"id": "tx-A", "paiement_at": iso(pa_a), "feuilles_avant": None},
        {"id": "tx-B", "paiement_at": iso(pa_b), "feuilles_avant": None},
        {"id": "tx-C", "paiement_at": iso(pa_c), "feuilles_avant": None},
    ]
    patches = []
    install_fakes(w, pending, patches)

    printer.drop(1)
    w.tick()

    marked_ids = [p[0] for p in patches if p[1].get("impression_verifiee_papier")]
    assert marked_ids == ["tx-A"], f"Seul A devrait etre marque, got {marked_ids}"
    print("[OK] test_three_clients_one_print : seul A marque, B et C pending")


if __name__ == "__main__":
    test_two_clients_one_print()
    test_two_clients_two_prints_same_tick()
    test_one_client_two_sheets_no_false_multiple()
    test_sequential_ticks_two_clients()
    test_three_clients_one_print()
    print("\nTous les tests OK !")
