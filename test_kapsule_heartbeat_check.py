"""Tests de verifier_kapsule_heartbeat (v1.0.28.24).

Spec initiale (v1.0.28.23) :
 a) kapsule_timestamp NULL           -> ZERO alerte, ZERO erreur, ZERO log d'echec
 b) kapsule_timestamp > seuil        -> alerte kapsule_fige
 c) kapsule_timestamp recent + hostname mismatch -> alerte kapsule_mauvaise_borne

Nouveaux garde-fous v1.0.28.24 (3 fausses alertes vecues du 07 au 10/11) :
 1) Hors horaires d'ouverture du bar -> skip (borne eteinte la nuit)
 2) Agent lui-meme n'a pas poste recemment (reseau coupe) -> skip
 3) Seuil remonte de 120s a 300s (boot Kapsule + Windows peut legitiment
    depasser 2 min au demarrage)
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch
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
    am._alertes_cache_loaded = True


def _ts(delta_sec):
    """ISO timestamp avec delta_sec par rapport a maintenant."""
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_sec)).isoformat()


def _fresh_agent_row(kapsule_offset_sec, hostname="MB-X"):
    """Row avec agent timestamp frais (-30s) et kapsule_timestamp parametre."""
    return {
        "timestamp": _ts(-30),
        "kapsule_timestamp": _ts(kapsule_offset_sec) if kapsule_offset_sec is not None else None,
        "kapsule_hostname": hostname,
    }


def _run(borne_id, data, status=200, hostname_local="MB-X", in_horaires=True):
    """Lance verifier_kapsule_heartbeat en mockant tout l'ecosysteme."""
    created = []
    resolved = []
    with patch.object(am, "supa") as supa, \
         patch.object(am, "_est_dans_horaires", return_value=in_horaires), \
         patch.object(am, "_creer_alerte", side_effect=lambda *a, **kw: created.append(a[1])), \
         patch.object(am, "_resoudre_alertes", side_effect=lambda bid, types: resolved.append(types)), \
         patch("socket.gethostname", return_value=hostname_local):
        supa.http_get.return_value = FakeResp(status, data)
        supa.SUPABASE_URL = "https://x"
        supa.HEADERS = {}
        am.verifier_kapsule_heartbeat(borne_id, "Test Bar")
    return created, resolved


# --- Cas de la spec initiale ---------------------------------------------

def test_a_borne_sans_kapsule_zero_alerte():
    """NULL -> aucune alerte."""
    _reset()
    created, _ = _run("borne-a", [_fresh_agent_row(None)])
    assert created == [], f"Aucune alerte attendue, got {created}"
    print("[OK] a) borne sans Kapsule : 0 alerte")


def test_b_kapsule_fige_cree_alerte():
    """kapsule_timestamp -10 min (> seuil 300s), agent frais -> alerte kapsule_fige."""
    _reset()
    created, _ = _run("borne-b", [_fresh_agent_row(-600)])
    assert "kapsule_fige" in created, f"Attendu kapsule_fige, got {created}"
    print("[OK] b) kapsule vieux + agent frais : alerte kapsule_fige")


def test_c_hostname_mismatch_cree_alerte():
    """kapsule_timestamp recent + hostname != local -> alerte kapsule_mauvaise_borne."""
    _reset()
    row = _fresh_agent_row(-10, hostname="AUTRE-HOST")
    created, _ = _run("borne-c", [row], hostname_local="VRAI-HOST")
    assert "kapsule_mauvaise_borne" in created, f"Attendu kapsule_mauvaise_borne, got {created}"
    print("[OK] c) hostname mismatch : alerte kapsule_mauvaise_borne")


def test_d_nominal_zero_alerte():
    """Tout va bien : 0 alerte."""
    _reset()
    created, _ = _run("borne-d", [_fresh_agent_row(-10, hostname="MB-X")], hostname_local="MB-X")
    assert created == [], f"0 alerte attendue, got {created}"
    print("[OK] d) nominal : 0 alerte")


# --- Nouveaux garde-fous v1.0.28.24 --------------------------------------

def test_1_hors_horaires_skip():
    """Bar ferme (hors horaires) -> skip total, 0 alerte, 0 resolution."""
    _reset()
    # Meme un kapsule_timestamp de -1h ne doit rien declencher hors horaires
    created, resolved = _run("borne-h", [_fresh_agent_row(-3600)], in_horaires=False)
    assert created == [], f"0 alerte attendue hors horaires, got {created}"
    assert resolved == [], f"0 resolution attendue hors horaires, got {resolved}"
    print("[OK] 1) hors horaires : skip total (ni alerte ni resolution)")


def test_2_agent_vieux_skip():
    """Si agent lui-meme n'a pas poste depuis > 180s, c'est reseau mort, pas Kapsule."""
    _reset()
    # agent vieux -5 min, kapsule vieux -10 min
    row = {
        "timestamp": _ts(-300),
        "kapsule_timestamp": _ts(-600),
        "kapsule_hostname": "MB-X",
    }
    created, _ = _run("borne-r", [row])
    assert created == [], f"Agent vieux = reseau mort, skip. got {created}"
    print("[OK] 2) agent vieux (reseau coupe) : skip (pas une alerte Kapsule)")


def test_3_seuil_entre_ancien_et_nouveau_zero_alerte():
    """kapsule_timestamp -2 min 30 (150s) : au-dessus de l'ancien seuil 120s
    mais SOUS le nouveau seuil 300s -> pas d'alerte. Evite les fausses alertes
    liees au temps de boot Windows + Kapsule."""
    _reset()
    created, _ = _run("borne-s", [_fresh_agent_row(-150, hostname="MB-X")], hostname_local="MB-X")
    assert created == [], f"150s sous seuil 300s, 0 alerte attendue, got {created}"
    print("[OK] 3) kapsule -150s (ancien seuil 120s KO, nouveau 300s OK) : 0 alerte")


def test_3bis_seuil_juste_au_dessus_cree_alerte():
    """kapsule_timestamp -6 min (360s) > nouveau seuil 300s -> alerte."""
    _reset()
    created, _ = _run("borne-s2", [_fresh_agent_row(-360, hostname="MB-X")], hostname_local="MB-X")
    assert "kapsule_fige" in created, f"360s > seuil 300s : alerte attendue, got {created}"
    print("[OK] 3bis) kapsule -360s (> seuil 300s) : alerte declenchee")


def test_e_robustesse_jamais_d_exception():
    """Aucune entree aberrante ne doit lever d'exception."""
    _reset()
    cas = [
        (500, None),
        (200, []),
        (200, [{}]),
        (200, [{"kapsule_timestamp": "pas-une-date", "timestamp": _ts(-30)}]),
        (200, [{"kapsule_timestamp": 12345, "timestamp": _ts(-30)}]),
        (200, [{"kapsule_timestamp": None, "kapsule_hostname": None, "timestamp": _ts(-30)}]),
        (200, [{"timestamp": None, "kapsule_timestamp": _ts(-600)}]),  # agent ts null
    ]
    for status, data in cas:
        data_ok = data if data is not None else []
        _run("borne-e", data_ok, status=status)
    print(f"[OK] e) robustesse : {len(cas)} cas aberrants sans exception")


if __name__ == "__main__":
    test_a_borne_sans_kapsule_zero_alerte()
    test_b_kapsule_fige_cree_alerte()
    test_c_hostname_mismatch_cree_alerte()
    test_d_nominal_zero_alerte()
    test_1_hors_horaires_skip()
    test_2_agent_vieux_skip()
    test_3_seuil_entre_ancien_et_nouveau_zero_alerte()
    test_3bis_seuil_juste_au_dessus_cree_alerte()
    test_e_robustesse_jamais_d_exception()
    print("\nTous les tests Kapsule heartbeat v1.0.28.24 OK !")
