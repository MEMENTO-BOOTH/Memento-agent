"""Tests de verifier_kapsule_heartbeat (v1.0.28.23).

Les 3 cas de la spec de l'autre Claude :
 a) kapsule_timestamp NULL           -> ZERO alerte, ZERO erreur, ZERO log d'echec
 b) kapsule_timestamp > 2 min        -> alerte kapsule_fige
 c) kapsule_timestamp recent + hostname mismatch -> alerte kapsule_mauvaise_borne

Et un test fuzz : tout ce qui est aberrant dans la reponse ne doit JAMAIS
lever d'exception vers l'appelant.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from monitoring.alertes import alertes_monitor as am


class FakeResp:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data
    def json(self):
        return self._data


def _reset():
    am._alertes_ouvertes.clear()
    am._alertes_cache_loaded = True  # skippe le chargement reseau au boot


def test_a_borne_sans_kapsule_zero_alerte():
    """Spec : NULL -> aucune alerte, aucun log d'erreur."""
    _reset()
    created = []
    resolved = []
    with patch.object(am, "supa") as supa, \
         patch.object(am, "_creer_alerte", side_effect=lambda *a, **kw: created.append(a)), \
         patch.object(am, "_resoudre_alertes", side_effect=lambda bid, types: resolved.append(types)):
        supa.http_get.return_value = FakeResp(200, [{"kapsule_timestamp": None, "kapsule_hostname": None}])
        supa.SUPABASE_URL = "https://x"
        supa.HEADERS = {}
        am.verifier_kapsule_heartbeat("borne-a", "Test Bar")
    assert created == [], f"Aucune alerte attendue, got {created}"
    # On autorise une tentative de resolution (idempotent) mais pas d'alerte
    print(f"[OK] a) borne sans Kapsule : 0 alerte cree (resolutions idempotentes autorisees: {resolved})")


def test_b_kapsule_fige_cree_alerte():
    """Spec : timestamp > 2 min -> alerte kapsule_fige."""
    _reset()
    created = []
    old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    with patch.object(am, "supa") as supa, \
         patch.object(am, "_creer_alerte", side_effect=lambda *a, **kw: created.append(a[1])), \
         patch.object(am, "_resoudre_alertes", side_effect=lambda bid, types: None):
        supa.http_get.return_value = FakeResp(200, [{"kapsule_timestamp": old, "kapsule_hostname": "MB-X"}])
        supa.SUPABASE_URL = "https://x"
        supa.HEADERS = {}
        am.verifier_kapsule_heartbeat("borne-b", "Test Bar")
    assert "kapsule_fige" in created, f"Attendu kapsule_fige, got {created}"
    print(f"[OK] b) kapsule_timestamp > 2 min : alerte kapsule_fige creee")


def test_c_hostname_mismatch_cree_alerte():
    """Spec : timestamp recent + hostname != local -> alerte kapsule_mauvaise_borne."""
    _reset()
    created = []
    fresh = datetime.now(timezone.utc).isoformat()
    with patch.object(am, "supa") as supa, \
         patch.object(am, "_creer_alerte", side_effect=lambda *a, **kw: created.append(a[1])), \
         patch.object(am, "_resoudre_alertes", side_effect=lambda bid, types: None), \
         patch("socket.gethostname", return_value="VRAI-HOST"):
        supa.http_get.return_value = FakeResp(200, [{"kapsule_timestamp": fresh, "kapsule_hostname": "AUTRE-HOST"}])
        supa.SUPABASE_URL = "https://x"
        supa.HEADERS = {}
        am.verifier_kapsule_heartbeat("borne-c", "Test Bar")
    assert "kapsule_mauvaise_borne" in created, f"Attendu kapsule_mauvaise_borne, got {created}"
    print(f"[OK] c) hostname mismatch : alerte kapsule_mauvaise_borne creee")


def test_d_timestamp_recent_hostname_ok_zero_alerte():
    """Cas nominal : tout va bien, aucune alerte."""
    _reset()
    created = []
    fresh = datetime.now(timezone.utc).isoformat()
    with patch.object(am, "supa") as supa, \
         patch.object(am, "_creer_alerte", side_effect=lambda *a, **kw: created.append(a[1])), \
         patch.object(am, "_resoudre_alertes", side_effect=lambda bid, types: None), \
         patch("socket.gethostname", return_value="MB-X"):
        supa.http_get.return_value = FakeResp(200, [{"kapsule_timestamp": fresh, "kapsule_hostname": "MB-X"}])
        supa.SUPABASE_URL = "https://x"
        supa.HEADERS = {}
        am.verifier_kapsule_heartbeat("borne-d", "Test Bar")
    assert created == [], f"Aucune alerte attendue, got {created}"
    print(f"[OK] d) nominal (recent + hostname OK) : 0 alerte")


def test_e_robustesse_jamais_d_exception():
    """Spec : aucune entree aberrante ne doit lever d'exception vers l'appelant."""
    _reset()
    cas_aberrants = [
        (500, None),                                              # HTTP 500
        (200, []),                                                # pas de ligne
        (200, [{}]),                                              # pas de colonne kapsule_*
        (200, [{"kapsule_timestamp": "pas-une-date"}]),           # timestamp illisible
        (200, [{"kapsule_timestamp": 12345}]),                    # timestamp int
        (200, [{"kapsule_timestamp": None, "kapsule_hostname": None}]),  # tout null
    ]
    for status, data in cas_aberrants:
        with patch.object(am, "supa") as supa, \
             patch.object(am, "_creer_alerte"), \
             patch.object(am, "_resoudre_alertes"):
            resp = FakeResp(status, data) if data is not None else FakeResp(status, [])
            supa.http_get.return_value = resp
            supa.SUPABASE_URL = "https://x"
            supa.HEADERS = {}
            # Ne doit JAMAIS raise
            am.verifier_kapsule_heartbeat("borne-e", "Test")
    print(f"[OK] e) robustesse : {len(cas_aberrants)} cas aberrants gerés sans exception")


if __name__ == "__main__":
    test_a_borne_sans_kapsule_zero_alerte()
    test_b_kapsule_fige_cree_alerte()
    test_c_hostname_mismatch_cree_alerte()
    test_d_timestamp_recent_hostname_ok_zero_alerte()
    test_e_robustesse_jamais_d_exception()
    print("\nTous les tests Kapsule heartbeat OK !")
