"""Tests de kapsule_printer.read_media_counter (v1.0.28.29).

Objectif : garantir que la lecture du compteur publie par Kapsule dans
health.json est robuste, et surtout qu'elle degrade proprement vers None
dans tous les cas douteux plutot que de propager une valeur fausse (une
fausse valeur ferait calculer une fausse baisse -> fausse confirmation
d'impression, ou pire un faux 'photo non sortie' avec SMS a la cle).
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from monitoring import kapsule_printer as kp


def _with_health(content, fn):
    """Ecrit un health.json temporaire et pointe le module dessus."""
    d = tempfile.mkdtemp()
    path = os.path.join(d, "health.json")
    if content is not None:
        with open(path, "w", encoding="utf-8") as f:
            if isinstance(content, str):
                f.write(content)
            else:
                json.dump(content, f)
    with patch.object(kp, "_health_paths", return_value=[path]):
        return fn()


def _iso(delta_sec=0):
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_sec)).isoformat()


def test_nominal():
    """Compteur frais et valide -> renvoye tel quel."""
    r = _with_health(
        {"state": "ok", "printer_media_counter": 342, "printer_counter_at": _iso(-5)},
        kp.read_media_counter,
    )
    assert r == 342, f"attendu 342, got {r}"
    print("[OK] nominal : compteur 342 lu")


def test_sans_timestamp():
    """Pas de date de mesure -> on accepte (Kapsule reecrit en continu)."""
    r = _with_health({"state": "ok", "printer_media_counter": 200}, kp.read_media_counter)
    assert r == 200, f"attendu 200, got {r}"
    print("[OK] sans timestamp : accepte")


def test_champ_absent():
    """Kapsule pas encore a jour -> None, retrocompatible, zero regression."""
    r = _with_health({"state": "ok"}, kp.read_media_counter)
    assert r is None, f"attendu None, got {r}"
    print("[OK] champ absent (Kapsule pas a jour) : None")


def test_compteur_zero_veille_dnp():
    """Bug veille DNP (GetMediaCounter renvoie 0) -> None, jamais 0.

    C'est le bug Latina Cafe 14/06 : 3566 photos faussement comptees."""
    for bad in (0, -1, -999):
        r = _with_health(
            {"printer_media_counter": bad, "printer_counter_at": _iso(-5)},
            kp.read_media_counter,
        )
        assert r is None, f"compteur {bad} doit donner None, got {r}"
    print("[OK] compteur <= 0 (veille DNP) : None")


def test_valeur_perimee():
    """Valeur trop vieille -> None (sinon on calculerait une baisse sur du mort)."""
    r = _with_health(
        {"printer_media_counter": 300, "printer_counter_at": _iso(-999)},
        kp.read_media_counter,
    )
    assert r is None, f"valeur perimee doit donner None, got {r}"
    print("[OK] valeur perimee (>120s) : None")


def test_valeur_dans_le_futur():
    """Horloge Kapsule en avance -> None plutot que de faire confiance."""
    r = _with_health(
        {"printer_media_counter": 300, "printer_counter_at": _iso(600)},
        kp.read_media_counter,
    )
    assert r is None, f"timestamp futur doit donner None, got {r}"
    print("[OK] timestamp dans le futur : None")


def test_limite_fraicheur():
    """Juste sous la limite -> accepte ; juste au-dessus -> refuse."""
    ok = _with_health(
        {"printer_media_counter": 150, "printer_counter_at": _iso(-(kp.MAX_AGE_SECONDS - 10))},
        kp.read_media_counter,
    )
    ko = _with_health(
        {"printer_media_counter": 150, "printer_counter_at": _iso(-(kp.MAX_AGE_SECONDS + 10))},
        kp.read_media_counter,
    )
    assert ok == 150, f"sous la limite doit passer, got {ok}"
    assert ko is None, f"au-dessus doit etre refuse, got {ko}"
    print(f"[OK] limite fraicheur {kp.MAX_AGE_SECONDS}s respectee")


def test_noms_alternatifs():
    """Tolerance si Kapsule publie sous un nom legerement different."""
    r = _with_health(
        {"media_counter": 77, "media_counter_at": _iso(-5)}, kp.read_media_counter
    )
    assert r == 77, f"attendu 77, got {r}"
    print("[OK] noms de champs alternatifs acceptes")


def test_robustesse_jamais_d_exception():
    """Aucune entree aberrante ne doit lever : une lecture ratee degrade
    vers None, elle ne casse jamais le tick du watcher."""
    cas = [
        None,                                             # fichier absent
        "pas du json {{{",                                # JSON invalide
        "[1,2,3]",                                        # JSON mais pas un dict
        {"printer_media_counter": "abc"},                 # valeur non numerique
        {"printer_media_counter": None},                  # valeur null
        {"printer_media_counter": 100, "printer_counter_at": "pas-une-date"},
        {"printer_media_counter": {"nested": 1}},         # type inattendu
        {},                                               # dict vide
    ]
    for c in cas:
        r = _with_health(c, kp.read_media_counter)
        assert r is None or isinstance(r, int), f"retour inattendu {r!r} pour {c!r}"
    print(f"[OK] robustesse : {len(cas)} cas aberrants sans exception")


def test_fichier_absent():
    """Borne dslrBooth (pas de health.json du tout) -> None."""
    with patch.object(kp, "_health_paths", return_value=["Z:\\nexiste\\pas\\health.json"]):
        r = kp.read_media_counter()
    assert r is None, f"attendu None, got {r}"
    print("[OK] fichier absent : None")


if __name__ == "__main__":
    test_nominal()
    test_sans_timestamp()
    test_champ_absent()
    test_compteur_zero_veille_dnp()
    test_valeur_perimee()
    test_valeur_dans_le_futur()
    test_limite_fraicheur()
    test_noms_alternatifs()
    test_robustesse_jamais_d_exception()
    test_fichier_absent()
    print("\nTous les tests kapsule_printer OK !")
