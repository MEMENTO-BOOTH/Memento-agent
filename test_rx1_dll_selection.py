"""Tests du support DS-RX1 via CyStat64.dll (v1.0.28.30).

Chaque famille DNP a sa propre DLL de statut. Utiliser la mauvaise provoque un
segfault natif qui tue le process agent entier (observe MB-50, v1.0.28.9, avec
Cx2Stat64 sur une DS-RX1). Ces tests verrouillent :

  1. le bon choix de DLL par modele
  2. qu'aucune DLL n'est ouverte sur les modeles non supportes
  3. que sur borne Kapsule, le compteur vienne de health.json pour les
     modeles que Kapsule sait lire (DS620) — on ne lui dispute pas un port
     qu'il utilise pour imprimer (v1.0.28.13). La DS-RX1 fait exception
     depuis v1.0.28.30 : Kapsule n'embarque que Cx2Stat64, il ne tient donc
     pas ce port et ne publiera jamais son compteur ; attendre reviendrait a
     laisser MB-50 aveugle.
  4. que les codes de statut d'un modele non valide en production ne soient
     jamais interpretes : ni alerte creee, ni alerte resolue.
  5. que printer_standby ne balaie plus le port d'une imprimante qui n'est
     pas une DS620.
"""

import os
import sys
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from monitoring.alertes.constants import get_printer_dll
from monitoring import printer_counter


class FakeDLL:
    """Faux WinDLL qui enregistre les appels PortInitialize."""

    def __init__(self, name, status=0x10001, counter=342, counter_r=None,
                 port_init_result=1, ports_ok=None):
        self.name = name
        self.port_init_calls = []
        self._port_init_result = port_init_result
        # Si fourni, seuls ces ports repondent — sinon PortInitialize reussit
        # sur n'importe quel port, ce qui rend les tests de balayage faux.
        self._ports_ok = ports_ok
        self._status = status
        self._counter = counter
        # Mesure MB-50 18/11/2026 : GetMediaCounter=480, offset=50,
        # GetMediaCounter_R=430, et l'outil DNP affiche 430.
        self._counter_r = (counter - 50) if counter_r is None else counter_r
        self.PortInitialize = self._make(self._port_initialize)
        self.GetStatus = self._make(lambda h: self._status)
        self.GetMediaCounter = self._make(lambda h: self._counter)
        self.GetMediaCounter_R = self._make(lambda h: self._counter_r)
        self.GetMediaCountOffset = self._make(lambda h: 50)
        # Utilisees par printer_standby. Sans elles, _open_ds620 leve un
        # AttributeError avale par son try/except global et retourne
        # (None, None) : le test "la RX1 n'est pas balayee" passerait alors
        # sans qu'aucun balayage n'ait eu lieu, donc sans rien prouver.
        self.GetStandbyTime = self._make(lambda h: 10)
        self.SetStandbyTime = self._make(lambda h, v: 0)

    def _make(self, fn):
        m = MagicMock(side_effect=fn)
        m.argtypes = None
        m.restype = None
        return m

    def _port_initialize(self, port):
        self.port_init_calls.append(port)
        if self._ports_ok is not None and port not in self._ports_ok:
            return -1  # rien de branche sur ce port
        return self._port_init_result  # < 0 = imprimante injoignable


def _fake_registry(printers):
    """Simule winreg avec la liste [(nom, port, driver), ...]."""
    winreg = MagicMock()
    winreg.HKEY_LOCAL_MACHINE = 0

    def enum_key(key, i):
        if i >= len(printers):
            raise OSError("fin")
        return printers[i][0]

    def query_value_ex(key, field):
        idx = getattr(key, "_idx", None)
        if idx is None:
            raise OSError("pas une cle imprimante")
        if field == "Port":
            return (printers[idx][1], 1)
        if field == "Printer Driver":
            return (printers[idx][2], 1)
        raise OSError("champ inconnu")

    def open_key(root, path):
        ctx = MagicMock()
        for i, (n, _p, _d) in enumerate(printers):
            if path.endswith("\\" + n):
                ctx._idx = i
                break
        ctx.__enter__ = lambda s: ctx
        ctx.__exit__ = lambda s, *a: False
        return ctx

    winreg.EnumKey = enum_key
    winreg.QueryValueEx = query_value_ex
    winreg.OpenKey = open_key
    return winreg


def _run_open(printers, is_kapsule=False):
    """Lance _PrinterHandle.open() et retourne (resultat, dlls_chargees)."""
    loaded = {}

    def fake_load(dll_name):
        if dll_name not in loaded:
            loaded[dll_name] = FakeDLL(dll_name)
        return loaded[dll_name]

    h = printer_counter._PrinterHandle()
    with patch.dict(sys.modules, {"winreg": _fake_registry(printers)}), \
         patch("monitoring.dnp_dll.load_dll", side_effect=fake_load), \
         patch("monitoring.photo_app.is_kapsule_borne", return_value=is_kapsule), \
         patch("monitoring.printer_counter.platform.system", return_value="Windows"):
        ok = h.open()
    return ok, loaded, h


def test_ds620_choisit_cx2stat():
    ok, loaded, h = _run_open([("DP-DS620", "USB001", "DP-DS620")])
    assert ok, "DS620 doit etre ouverte"
    assert "Cx2Stat64.dll" in loaded, f"DLL chargees: {list(loaded)}"
    assert "CyStat64.dll" not in loaded, "CyStat64 ne doit PAS etre chargee pour une DS620"
    assert loaded["Cx2Stat64.dll"].port_init_calls == ["USB001"]
    print("[OK] DS620 -> Cx2Stat64.dll")


def test_rx1_prefixee_choisit_cystat():
    ok, loaded, h = _run_open([("DP-DS-RX1", "USB002", "DP-DS-RX1")])
    assert ok, "DS-RX1 doit maintenant etre ouverte"
    assert "CyStat64.dll" in loaded, f"DLL chargees: {list(loaded)}"
    assert "Cx2Stat64.dll" not in loaded, "Cx2Stat64 sur une RX1 = segfault (MB-50)"
    assert loaded["CyStat64.dll"].port_init_calls == ["USB002"]
    print("[OK] DP-DS-RX1 -> CyStat64.dll")


def test_rx1_renommee_choisit_cystat():
    """L'operateur renomme parfois l'imprimante sans le prefixe DP-."""
    ok, loaded, h = _run_open([("DS-RX1", "USB003", "DP-DS-RX1")])
    assert ok and "CyStat64.dll" in loaded
    assert "Cx2Stat64.dll" not in loaded
    print("[OK] DS-RX1 renommee -> CyStat64.dll")


def test_rx1_detectee_via_driver_registre():
    """Nom completement custom, mais le driver du registre trahit le modele."""
    ok, loaded, h = _run_open([("Imprimante du bar", "USB004", "DP-DS-RX1")])
    assert ok, "doit etre reconnue via le driver"
    assert "CyStat64.dll" in loaded
    print("[OK] nom custom + driver DP-DS-RX1 -> CyStat64.dll")


def test_ds820_aucune_dll():
    """Modele DNP sans DLL fournie : on ne l'ouvre jamais."""
    ok, loaded, h = _run_open([("DP-DS820", "USB005", "DP-DS820")])
    assert not ok, "DS820 ne doit pas etre ouverte"
    assert loaded == {}, f"aucune DLL ne doit etre chargee, got {list(loaded)}"
    print("[OK] DS820 -> aucune DLL, fallback inchange")


def test_imprimante_non_dnp_ignoree():
    ok, loaded, h = _run_open([("Microsoft Print to PDF", "PORTPROMPT", "MS PDF")])
    assert not ok and loaded == {}
    print("[OK] imprimante non-DNP ignoree")


def test_melange_ds620_et_rx1():
    """Deux DNP branchees : chacune doit etre interrogee avec SA DLL."""
    ok, loaded, h = _run_open([
        ("DP-DS620", "USB001", "DP-DS620"),
        ("DP-DS-RX1", "USB002", "DP-DS-RX1"),
    ])
    assert ok
    # Le tri deterministe (nom le plus court d'abord) prend DP-DS620
    assert h.name == "DP-DS620", f"tri deterministe casse, got {h.name}"
    assert loaded["Cx2Stat64.dll"].port_init_calls == ["USB001"]
    # CyStat64 ne doit pas avoir ete sollicitee : la premiere a repondu
    assert "CyStat64.dll" not in loaded or loaded["CyStat64.dll"].port_init_calls == []
    print("[OK] melange DS620 + RX1 : chacune sa DLL, tri deterministe respecte")


def test_kapsule_health_json_prioritaire():
    """Quand health.json fournit le compteur, on s'arrete la : aucun acces au
    port, aucune DLL chargee.

    PORTEE REELLE DE CE TEST, pour ne pas s'y fier plus qu'il ne vaut : il ne
    prouve pas qu'aucun port n'est jamais ouvert sur borne Kapsule — depuis
    v1.0.28.30 c'est faux pour la RX1, cf.
    test_kapsule_rx1_health_json_muet_lit_le_port. Il prouve seulement que la
    source health.json a la priorite quand elle repond."""
    loaded = {}

    def fake_load(dll_name):
        loaded.setdefault(dll_name, FakeDLL(dll_name))
        return loaded[dll_name]

    h = printer_counter._PrinterHandle()
    with patch("monitoring.photo_app.is_kapsule_borne", return_value=True), \
         patch("monitoring.kapsule_printer.read_media_counter", return_value=127), \
         patch("monitoring.dnp_dll.load_dll", side_effect=fake_load), \
         patch.object(h, "open", side_effect=AssertionError("open() INTERDIT sur Kapsule")):
        counter, status = h.read_counter_and_status()

    assert counter == 127, f"doit lire le compteur de health.json, got {counter}"
    assert status is None, "pas de status DNP via health.json"
    assert loaded == {}, f"AUCUNE DLL ne doit etre chargee sur Kapsule, got {list(loaded)}"
    print("[OK] borne Kapsule : health.json prioritaire, aucun port ouvert")


def test_kapsule_ds620_health_json_muet_reste_silencieux():
    """Kapsule + DS620, health.json sans compteur : on ATTEND, on ne va pas
    disputer le port a Kapsule. Il sait lire ce modele (il embarque
    Cx2Stat64), donc un health.json muet est transitoire — demarrage ou
    impression en cours."""
    loaded = {}

    def fake_load(dll_name):
        loaded.setdefault(dll_name, FakeDLL(dll_name))
        return loaded[dll_name]

    h = printer_counter._PrinterHandle()
    with patch.dict(sys.modules, {"winreg": _fake_registry(
            [("DP-DS620", "USB001", "DP-DS620")])}), \
         patch("monitoring.photo_app.is_kapsule_borne", return_value=True), \
         patch("monitoring.kapsule_printer.read_media_counter", return_value=None), \
         patch("monitoring.dnp_dll.load_dll", side_effect=fake_load), \
         patch("monitoring.printer_counter.platform.system", return_value="Windows"):
        counter, status = h.read_counter_and_status()

    assert counter is None and status is None
    assert "Cx2Stat64.dll" not in loaded, \
        "sur Kapsule, une DS620 ne doit pas etre ouverte par le watcher"
    print("[OK] Kapsule + DS620 + health.json muet : on n'ouvre pas le port")


def test_kapsule_rx1_health_json_muet_lit_le_port():
    """MB-50 : Kapsule n'embarque que Cx2Stat64, il ne publiera JAMAIS le
    compteur d'une RX1 (health.json -> "printer_media_counter": null).
    Attendre reviendrait a rester aveugle indefiniment : 13 fausses alertes
    'photo non sortie' depuis le 15/11. On lit donc le port nous-memes,
    puisque Kapsule ne le tient pas (mesure du 18/11 : 15 lectures pendant
    que Kapsule tournait, aucun incident)."""
    loaded = {}

    def fake_load(dll_name):
        loaded.setdefault(dll_name, FakeDLL(dll_name, counter=480))
        return loaded[dll_name]

    h = printer_counter._PrinterHandle()
    with patch.dict(sys.modules, {"winreg": _fake_registry(
            [("DS-RX1", "USB003", "DS-RX1")])}), \
         patch("monitoring.photo_app.is_kapsule_borne", return_value=True), \
         patch("monitoring.kapsule_printer.read_media_counter", return_value=None), \
         patch("monitoring.dnp_dll.load_dll", side_effect=fake_load), \
         patch("monitoring.printer_counter.platform.system", return_value="Windows"):
        counter, status = h.read_counter_and_status()

    assert "CyStat64.dll" in loaded, "la RX1 doit etre lue directement"
    assert loaded["CyStat64.dll"].port_init_calls == ["USB003"]
    assert counter == 430, \
        f"doit publier GetMediaCounter_R (430), pas GetMediaCounter (480) ; got {counter}"
    assert status == 0x10001
    print("[OK] Kapsule + RX1 : lecture directe, compteur 430 (pas 480)")


def test_compteur_rx1_utilise_media_counter_r():
    """La RX1 expose deux compteurs. GetMediaCounter renvoie un brut dont il
    faut retrancher GetMediaCountOffset ; GetMediaCounter_R fait la
    soustraction. Verifie sur MB-50 contre l'outil officiel DNP, qui affiche
    bien 430. Prendre le mauvais publierait 50 feuilles de trop et l'alerte
    papier bas (seuil 50) n'arriverait jamais a temps."""
    from monitoring.dnp_dll import read_media_counter

    rx1 = FakeDLL("CyStat64.dll", counter=480)
    assert read_media_counter(rx1, "CyStat64.dll", 1) == 430
    assert rx1.GetMediaCounter_R.called
    assert not rx1.GetMediaCounter.called, \
        "GetMediaCounter ne doit PAS etre appelee sur une RX1"

    ds620 = FakeDLL("Cx2Stat64.dll", counter=342)
    assert read_media_counter(ds620, "Cx2Stat64.dll", 1) == 342
    assert ds620.GetMediaCounter.called
    assert not ds620.GetMediaCounter_R.called, \
        "la DS620 garde GetMediaCounter - aucune regression sur les 28 bornes"
    print("[OK] compteur : RX1 -> GetMediaCounter_R, DS620 -> GetMediaCounter")


def test_cx2stat_sondee_avant_cystat():
    """REGRESSION A NE PAS INTRODUIRE : le tri par longueur de nom est
    arbitraire vis-a-vis du modele. Une entree RX1 au nom court passerait
    avant une DS620 au nom long, et on sonderait le port avec le chemin neuf
    avant le chemin eprouve sur ~28 bornes. dll_probe_rank force l'ordre."""
    from monitoring.alertes.constants import dll_probe_rank
    assert dll_probe_rank("Cx2Stat64.dll") < dll_probe_rank("CyStat64.dll")

    # "DS-RX1" (6 car.) est plus court que "DP-DS620 (Copie 1)" (18 car.) :
    # sans le rank, la RX1 serait sondee en premier.
    ok, loaded, h = _run_open([
        ("DS-RX1", "USB003", "DS-RX1"),
        ("DP-DS620 (Copie 1)", "USB001", "DP-DS620"),
    ])
    assert ok
    assert h.dll_name == "Cx2Stat64.dll", \
        f"la DS620 doit etre essayee en premier, got {h.dll_name}"
    assert loaded["Cx2Stat64.dll"].port_init_calls == ["USB001"]
    assert "CyStat64.dll" not in loaded, \
        "CyStat64 ne doit meme pas etre chargee si la DS620 repond"
    print("[OK] ordre de sondage : Cx2Stat64 avant CyStat64")


def _run_collector(printers, load_result, is_kapsule=False):
    """Lance collectors.printer.lire_imprimante() sur un faux registre.

    ATTENTION : le collector fait `from ..dnp_dll import load_dll` au niveau
    module. Patcher "monitoring.dnp_dll.load_dll" ne l'atteint donc PAS — il
    faut patcher la reference importee, sinon le test touche la vraie DLL et
    ne prouve rien."""
    from monitoring.collectors import printer as collector
    with patch.dict(sys.modules, {"winreg": _fake_registry(printers)}), \
         patch("monitoring.photo_app.is_kapsule_borne", return_value=is_kapsule), \
         patch.object(collector, "load_dll", side_effect=load_result), \
         patch("monitoring.collectors.printer.platform.system", return_value="Windows"):
        return collector.lire_imprimante()


def test_collector_dll_introuvable_ne_se_declare_pas_sain():
    """REGRESSION CORRIGEE : quand aucune DLL n'est chargeable et qu'une
    seconde imprimante DNP est declaree, le code retombait sur le repli
    'En veille' (code 0x10001). alertes_monitor traite ce code comme sain :
    il resout l'alerte imprimante_deconnectee et l'agent se declare en bonne
    sante alors qu'il ne lit plus rien. Scenario reel : dossier _MEI efface
    en cours de route (cf. v1.0.28.28)."""
    res = _run_collector(
        [("DP-DS620", "USB001", "DP-DS620"), ("DP-DS820", "USB002", "DP-DS820")],
        load_result=lambda dll_name: None,
    )
    assert res["imprimante_statut"] == "DLL introuvable", \
        f"doit dire la verite, got {res['imprimante_statut']!r}"
    assert res["imprimante_statut_code"] is None, \
        "aucun code ne doit etre publie quand on n'a rien lu"
    assert res["feuilles_restantes"] is None
    print("[OK] collector : DLL introuvable -> pas de faux 'En veille'")


def test_collector_rx1_injoignable_ne_bloque_pas_la_borne():
    """Une RX1 qui ne repond pas ne doit declencher NI alerte critique, NI
    fausse resolution.

    'Imprimante deconnectee' et 'DLL introuvable' sont tous deux dans la
    liste de alertes_monitor qui mene a l'alerte critique + SMS + ecran de
    rupture plein ecran. Avant v1.0.28.30, une RX1 tombait toujours en repli
    silencieux et ne pouvait declencher aucune alerte : un chemin neuf ne
    doit pas pouvoir faire pire que ce qu'il remplace.

    Mais pas 'En veille'/0x10001 non plus : ce code est dans CODES_NORMAUX,
    il ferait croire a une imprimante saine, resoudrait a tort les alertes
    ouvertes, et la borne apparaitrait verte au dashboard avec une
    imprimante morte. Il faut un statut qui ne conclut rien."""
    from monitoring.alertes.constants import CODES_NORMAUX

    for libelle, dll in (
        ("port qui ne repond pas", FakeDLL("CyStat64.dll", port_init_result=-1)),
        ("DLL qui ne charge pas", None),
    ):
        res = _run_collector(
            [("DS-RX1", "USB003", "DS-RX1")],
            load_result=lambda dll_name, _d=dll: _d,
        )
        statut = res["imprimante_statut"]
        assert statut not in ("Imprimante déconnectée", "Imprimante non trouvée",
                              "DLL introuvable"), \
            f"{libelle}: '{statut}' declencherait l'alerte critique qui bloque la borne"
        assert res["imprimante_statut_code"] not in CODES_NORMAUX, \
            f"{libelle}: un code 'sain' resoudrait a tort les alertes ouvertes"
        assert res["imprimante_statut_code"] is None, \
            f"{libelle}: aucun code ne doit etre publie, on n'a rien lu"
        assert statut == "Lecture impossible", f"{libelle}: got {statut!r}"

    print("[OK] collector : RX1 injoignable -> ni alerte, ni fausse resolution")


def test_collector_ds620_nominal_inchange():
    """NON-REGRESSION des ~28 bornes DS620 : chemin nominal, statut et
    compteur identiques a avant le changement."""
    ds620 = FakeDLL("Cx2Stat64.dll", status=0x10001, counter=342)
    res = _run_collector(
        [("DP-DS620", "USB001", "DP-DS620")],
        load_result=lambda dll_name: ds620,
    )
    assert res["nom_imprimante"] == "DP-DS620"
    assert res["imprimante_statut"] == "En veille"
    assert res["imprimante_statut_code"] == 0x10001
    assert res["feuilles_restantes"] == 342, \
        f"GetMediaCounter inchange sur DS620, got {res['feuilles_restantes']}"
    assert res["capacite_imprimante"] == 400
    assert res["imprimante_dll"] == "Cx2Stat64.dll"
    print("[OK] collector : DS620 nominal inchange (342 feuilles)")


def test_collector_rx1_publie_le_bon_compteur():
    """Bout en bout : une RX1 lue par le collector doit publier 430, le
    chiffre affiche par l'outil officiel DNP, et non 480."""
    rx1 = FakeDLL("CyStat64.dll", counter=480)
    res = _run_collector(
        [("DS-RX1", "USB003", "DS-RX1")],
        load_result=lambda dll_name: rx1,
    )
    assert res["feuilles_restantes"] == 430, \
        f"doit publier GetMediaCounter_R, got {res['feuilles_restantes']}"
    assert res["capacite_imprimante"] == 700, "capacite RX1"
    assert res["imprimante_dll"] == "CyStat64.dll"
    print("[OK] collector : RX1 publie 430 feuilles (pas 480)")


def _run_verifier_alertes(donnees):
    """Exerce reellement alertes_monitor.verifier_alertes().

    Retourne (alertes_creees, types_resolus). Aucun test ne faisait ca
    jusqu'ici — c'est precisement pour cette raison qu'un garde pose sur une
    seule des quatre branches de decision est passe inapercu."""
    from monitoring.alertes import alertes_monitor as am
    creees, resolus = [], []
    with patch.object(am, "verifier_kapsule_heartbeat"), \
         patch("monitoring.photo_app.is_kapsule_borne", return_value=False), \
         patch.object(am, "_est_dans_horaires", return_value=True), \
         patch.object(am, "_alerte_deja_ouverte", return_value=False), \
         patch.object(am, "_creer_alerte",
                      side_effect=lambda bid, t, cat, msg, grav: creees.append((t, grav))), \
         patch.object(am, "_resoudre_alertes",
                      side_effect=lambda bid, types: resolus.extend(types)):
        am._dernier_code_non_interprete = None
        am.verifier_alertes("borne-test", "Bar de test", donnees)
    return creees, resolus


def test_alertes_codes_rx1_aucune_conclusion():
    """GARDE CENTRAL, teste sur le vrai code de decision.

    Les tables de codes ont ete construites sur la DS620. Tant que la RX1
    n'est pas validee, AUCUNE des quatre branches ne doit conclure :
      - ALERTES_CRITIQUES : 7 codes -> alerte critique + SMS + ecran de
        rupture plein ecran qui bloque la borne pour les clients ;
      - le fourre-tout >= 0x40001 -> idem ;
      - ALERTES_WARNING ;
      - CODES_NORMAUX -> resout a tort 9 types d'alertes, ce qui effacerait
        une vraie panne.
    Un garde pose sur une seule branche ne sert a rien."""
    from monitoring.alertes.constants import (
        ALERTES_CRITIQUES, ALERTES_WARNING, CODES_NORMAUX, SEUIL_ERREUR_MECANIQUE,
    )
    # Seuls les verdicts IMPRIMANTE nous interessent ici : verifier_alertes
    # controle aussi camera, dslrBooth, disque, etc., qui reagissent au jeu
    # de donnees minimal du test.
    types_imprimante = (
        {i["type"] for i in ALERTES_CRITIQUES.values()}
        | {i["type"] for i in ALERTES_WARNING.values()}
        | {"erreur_mecanique", "papier_bas"}
    )
    codes = (list(ALERTES_CRITIQUES) + list(ALERTES_WARNING) + list(CODES_NORMAUX)
             + [SEUIL_ERREUR_MECANIQUE, 0x40008])
    for code in codes:
        creees, resolus = _run_verifier_alertes({
            "imprimante_statut_code": code,
            "imprimante_statut": "peu importe",
            "imprimante_dll": "CyStat64.dll",
            "feuilles_restantes": None,
        })
        creees_imp = [c for c in creees if c[0] in types_imprimante]
        resolus_imp = [t for t in resolus if t in types_imprimante]
        assert creees_imp == [], f"code 0x{code:08X} sur RX1 a cree {creees_imp}"
        assert resolus_imp == [], f"code 0x{code:08X} sur RX1 a resolu {resolus_imp}"
    print(f"[OK] alertes : {len(codes)} codes RX1 -> aucune alerte, aucune resolution")


def test_alertes_ds620_inchangees():
    """NON-REGRESSION des 28 bornes DS620 : le garde ne doit rien changer
    pour elles, et un chemin qui ne renseigne pas la DLL (cache heartbeat)
    doit garder le comportement d'avant."""
    from monitoring.alertes.constants import ALERTES_CRITIQUES

    code_bourrage = 0x20002
    attendu = ALERTES_CRITIQUES[code_bourrage]["type"]
    for dll in ("Cx2Stat64.dll", None):
        creees, _ = _run_verifier_alertes({
            "imprimante_statut_code": code_bourrage,
            "imprimante_statut": "Bourrage papier",
            "imprimante_dll": dll,
            "feuilles_restantes": 200,
        })
        assert (attendu, "critique") in creees, \
            f"dll={dll} : le bourrage papier doit toujours alerter, got {creees}"

    # Erreur mecanique (fourre-tout) sur DS620 : inchangee aussi.
    creees, _ = _run_verifier_alertes({
        "imprimante_statut_code": 0x40008,
        "imprimante_statut": "Erreur cutter",
        "imprimante_dll": "Cx2Stat64.dll",
        "feuilles_restantes": 200,
    })
    assert ("erreur_mecanique", "critique") in creees

    # Code normal : resout bien les alertes imprimante.
    _, resolus = _run_verifier_alertes({
        "imprimante_statut_code": 0x10001,
        "imprimante_statut": "En veille",
        "imprimante_dll": "Cx2Stat64.dll",
        "feuilles_restantes": 200,
    })
    assert "bourrage_papier" in resolus
    print("[OK] alertes : DS620 strictement inchangees (alerte + resolution)")


def test_ports_ambigus_ecartes():
    """Le registre Windows identifie un PILOTE, pas le materiel branche. Une
    entree residuelle "DP-DS620" laissee par une imprimante remplacee porte
    le nom ET le driver d'une DS620 : "le driver prime" ne la distingue pas
    de la vraie. Si une RX1 est branchee sur ce meme port, on appellerait
    Cx2Stat64 sur une RX1. Deux familles sur un meme port -> on n'y touche
    avec aucune des deux."""
    from monitoring.alertes.constants import ecarter_ports_ambigus

    retenus, ecartes = ecarter_ports_ambigus([
        ("DP-DS620", "USB003", "Cx2Stat64.dll"),   # entree fantome
        ("DS-RX1", "USB003", "CyStat64.dll"),      # la vraie imprimante
    ])
    assert retenus == [] and ecartes == {"USB003"}, \
        f"le port ambigu doit etre ecarte, got retenus={retenus}"

    # Deux entrees DS620 sur le meme port (copie fantome O divin Bethune) :
    # meme famille, aucune ambiguite -> on ne casse rien.
    memes = [("DP-DS620", "USB001", "Cx2Stat64.dll"),
             ("DP-DS620 (Copie 1)", "USB001", "Cx2Stat64.dll")]
    retenus, ecartes = ecarter_ports_ambigus(memes)
    assert retenus == memes and ecartes == set(), \
        "deux DS620 sur le meme port ne sont pas ambigues"

    # Bout en bout : le collector ne doit sonder aucun des deux.
    sondees = {}

    def fake_load(dll_name):
        sondees.setdefault(dll_name, FakeDLL(dll_name))
        return sondees[dll_name]

    res = _run_collector(
        [("DP-DS620", "USB003", "DP-DS620"), ("DS-RX1", "USB003", "DS-RX1")],
        load_result=fake_load,
    )
    for dll in sondees.values():
        assert dll.port_init_calls == [], \
            f"aucun port ne doit etre ouvert, {dll.name} a tente {dll.port_init_calls}"
    assert res["feuilles_restantes"] is None
    print("[OK] port ambigu : aucune des deux DLL ne touche au port")


def test_printer_standby_ne_touche_pas_la_rx1():
    """CONSTAT N°1 DES DEUX RELECTEURS. printer_standby desactive la mise en
    veille firmware des DS620. Il cherche les DS620 par NOM strict, puis, s'il
    n'en trouve aucune, balaie USB001..USB004 a l'aveugle avec Cx2Stat64.

    Sur MB-50 l'unique entree registre s'appelle "DS-RX1" : la liste restait
    vide et ce balayage appelait Cx2Stat64.PortInitialize sur la RX1 (USB003)
    a CHAQUE demarrage de l'agent, puis GetStandbyTime/SetStandbyTime, deux
    fonctions que CyStat64 n'expose meme pas. C'est le seul chemin du genre
    qui s'execute a coup sur au boot, et aucun garde ne le couvrait."""
    from monitoring import printer_standby

    # Seule la RX1 est physiquement branchee, sur USB003.
    fake = FakeDLL("Cx2Stat64.dll", ports_ok={"USB003"})
    with patch.dict(sys.modules, {"winreg": _fake_registry(
            [("DS-RX1", "USB003", "DS-RX1")])}), \
         patch.object(printer_standby, "_find_dll", return_value="C:\\fake.dll"), \
         patch.object(printer_standby.platform, "system", return_value="Windows"), \
         patch("ctypes.WinDLL", return_value=fake):
        dll, h = printer_standby._open_ds620()

    assert "USB003" not in fake.port_init_calls, \
        f"Cx2Stat64 ne doit JAMAIS toucher le port de la RX1, tente: {fake.port_init_calls}"
    assert dll is None and h is None, "aucune DS620 ici, rien a configurer"
    print("[OK] printer_standby : le port de la RX1 n'est plus balaye au boot")


def test_printer_standby_trouve_encore_les_ds620():
    """NON-REGRESSION : le balayage de repli doit rester disponible pour les
    DS620 dont l'entree registre ne matche aucun motif connu (imprimante
    renommee par l'exploitant)."""
    from monitoring import printer_standby

    # La DS620 renommee est branchee sur USB002.
    fake = FakeDLL("Cx2Stat64.dll", ports_ok={"USB002"})
    with patch.dict(sys.modules, {"winreg": _fake_registry(
            [("Imprimante du bar", "USB002", "")])}), \
         patch.object(printer_standby, "_find_dll", return_value="C:\\fake.dll"), \
         patch.object(printer_standby.platform, "system", return_value="Windows"), \
         patch("ctypes.WinDLL", return_value=fake):
        dll, h = printer_standby._open_ds620()

    assert dll is not None and h is not None, "le repli doit encore fonctionner"
    assert "USB002" in fake.port_init_calls, "le balayage doit avoir atteint USB002"
    print("[OK] printer_standby : repli conserve pour les DS620 renommees")


def test_imprimante_dll_hors_payload_heartbeat():
    """La table heartbeats de Supabase n'a pas de colonne imprimante_dll. Un
    champ inconnu fait rejeter le POST en 400 et le heartbeat est perdu —
    bug deja vecu en v1.0.28.14 (MB-16/MB-31/MB-37 muettes >27 min)."""
    from monitoring.collectors import heartbeat
    envoye = {}

    class _Rep:
        status_code = 201
        text = ""

    def fake_post(url, **kw):
        envoye.update(kw.get("json") or {})
        return _Rep()

    with patch("supabase_client.http_post", side_effect=fake_post), \
         patch("supabase_client.SUPABASE_URL", "https://exemple.test"):
        heartbeat.envoyer_heartbeat("borne-test", {
            "imprimante_statut": "En veille",
            "imprimante_dll": "CyStat64.dll",
            "nom_imprimante": "DS-RX1",
            "capacite_imprimante": 700,
            "feuilles_restantes": 430,
        })

    assert "imprimante_dll" not in envoye, \
        "imprimante_dll ne doit pas partir vers Supabase (colonne inexistante)"
    assert "nom_imprimante" not in envoye, \
        "nom_imprimante n'a toujours pas de colonne"
    assert envoye.get("feuilles_restantes") == 430, "le reste doit bien partir"
    # v1.0.28.32 : la colonne heartbeats.capacite_imprimante existe en prod
    # depuis le 18/11/2026. Le dashboard web en a besoin : il avait 400 en dur
    # et affichait un pourcentage faux pour MB-50 (rouleaux de 700).
    assert envoye.get("capacite_imprimante") == 700, \
        f"capacite_imprimante doit partir vers Supabase, got {envoye.get('capacite_imprimante')}"
    print("[OK] heartbeat : capacite envoyee, imprimante_dll et nom exclus")


def test_jauge_papier_capacite_rx1():
    """Constate sur MB-50 le 18/11/2026 apres installation de la 1.0.28.30 :
    la jauge affichait 430/400, alors que la RX1 a des rouleaux de 700.

    Deux chemins mettent a jour la jauge, et les deux forcaient 400 :
      - le temps reel (_apply_monitoring) avait 400 ecrit en dur, alors que
        la bonne capacite (700) arrivait dans les donnees ;
      - le rafraichissement Supabase (_apply_data) relisait la capacite
        dans la table heartbeats, qui ne la stocke pas -> 400 par defaut,
        ce qui ecrasait la bonne valeur a chaque rafraichissement.
    Invisible tant que tout le parc etait en DS620, qui fait justement 400."""
    import dashboard

    class _Faux:
        """Juste ce que lisent les deux gestionnaires de la fenetre."""
        def __init__(self):
            self._donut = MagicMock()
            self._lbl_pct = MagicMock()
            self._capacite_locale = None
            self._maj_jauge_papier = (
                lambda f, t: dashboard.DashboardWindow._maj_jauge_papier(self, f, t))

    W = dashboard.DashboardWindow

    # 1. RX1, temps reel : 430 sur 700, et non 430 sur 400.
    fen = _Faux()
    W._apply_monitoring(fen, {"feuilles_restantes": 430, "capacite_imprimante": 700})
    assert fen._donut.total == 700, f"capacite RX1 attendue 700, got {fen._donut.total}"
    assert fen._lbl_pct.setText.call_args[0][0] == "38 % utilisés"

    # 2. Le rafraichissement Supabase ne doit plus ecraser 700 par 400 : la
    #    ligne heartbeats n'a ni capacite ni nom d'imprimante. On appelle le
    #    VRAI gestionnaire, sur une fenetre factice qui absorbe tous les
    #    autres widgets qu'il met a jour.
    #
    #    ISOLATION : _apply_data cherche aussi un logo local dans
    #    ~/.mementoagent et le charge avec QPixmap — fatal sans QApplication,
    #    le processus meurt sans trace (0xC0000409). Il lit aussi le wifi
    #    reel si le heartbeat n'a pas de ssid. On lui donne donc un dossier
    #    personnel vide et un ssid.
    import tempfile
    with tempfile.TemporaryDirectory() as home_vide,          patch("os.path.expanduser", return_value=home_vide):
        def _charger(capacite_locale, feuilles, capacite_supabase=None):
            fen_sb = MagicMock()
            fen_sb._capacite_locale = capacite_locale
            W._apply_data(fen_sb, {"heartbeat": {
                "feuilles_restantes": feuilles, "ssid_wifi": "test",
                "capacite_imprimante": capacite_supabase}})
            return fen_sb

        _charger(700, 430)._maj_jauge_papier.assert_called_with(430, 700)

        # v1.0.28.32 : Supabase porte aussi la capacite. Elle sert quand le
        # monitoring local n'a encore rien lu...
        _charger(None, 430, 700)._maj_jauge_papier.assert_called_with(430, 700)
        # ...mais la lecture locale, faite a l'instant sur l'imprimante
        # reellement branchee, prime sur une ligne Supabase en retard d'un
        # heartbeat (imprimante changee entre-temps).
        _charger(700, 430, 400)._maj_jauge_papier.assert_called_with(430, 700)

        # 2bis. Fenetre ouverte avant tout cycle de monitoring ET sans cache :
        #       comportement d'avant (400), sans planter.
        _charger(None, 342)._maj_jauge_papier.assert_called_with(342, 400)

    # 2ter. Fenetre recreee apres un deverrouillage par PIN : le monitoring
    #       tourne deja et a mis la derniere lecture en cache. La capacite
    #       doit etre connue des l'ouverture, sans attendre son prochain cycle
    #       (jusqu'a 60 s pendant lesquels la RX1 affichait encore 400).
    from monitoring.collectors import heartbeat as hb_mod
    with patch.object(hb_mod, "_PRINTER_LAST_OK",
                      [{"capacite_imprimante": 700, "feuilles_restantes": 430}]):
        assert W._capacite_en_cache() == 700
    with patch.object(hb_mod, "_PRINTER_LAST_OK", [None]):
        assert W._capacite_en_cache() is None, "aucune lecture encore : None"

    # 3. DS620 : strictement inchange.
    fen = _Faux()
    W._apply_monitoring(fen, {"feuilles_restantes": 342, "capacite_imprimante": 400})
    assert fen._donut.total == 400
    assert fen._lbl_pct.setText.call_args[0][0] == "14 % utilisés"

    # 4. Donnees sans capacite (ancien cache heartbeat) : 400 comme avant.
    fen = _Faux()
    W._apply_monitoring(fen, {"feuilles_restantes": 342})
    assert fen._donut.total == 400

    # 5. Plus jamais de pourcentage negatif a l'ecran (MB-50 affichait -7 %).
    #    Mais l'incoherence n'est pas perdue : c'est le "-7 %" qui avait
    #    revele le bug de MB-50. Elle doit atterrir dans alertes.log (les
    #    print() sont perdus sur les bornes), une seule fois par valeur.
    fen = _Faux()
    with patch("activity_logger.log_generic") as log:
        fen._maj_jauge_papier(430, 400)
        fen._maj_jauge_papier(430, 400)   # meme valeur : pas de doublon
        fen._maj_jauge_papier(342, 400)   # coherent : rien a tracer
    assert fen._lbl_pct.setText.call_args[0][0] == "14 % utilisés"
    assert log.call_count == 1, f"une seule trace attendue, got {log.call_count}"
    assert "430" in log.call_args[0][1] and "400" in log.call_args[0][1]
    fen._maj_jauge_papier(430, 400)
    assert fen._lbl_pct.setText.call_args[0][0] == "0 % utilisés"
    print("[OK] jauge papier : RX1 430/700 (38 %), DS620 inchangee, plus de % negatif")


def test_selection_dll_table():
    """Table de verite du selecteur, independamment du registre."""
    cas = [
        ("DP-DS620", "Cx2Stat64.dll"),
        ("DP-DS620 (Copie 1)", "Cx2Stat64.dll"),
        ("DP-DS-RX1", "CyStat64.dll"),
        ("DS-RX1", "CyStat64.dll"),
        ("DSRX1", "CyStat64.dll"),
        ("DP-DS820", None),
        ("DS40", None),
        ("DS80", None),
        ("QW410", None),
        ("", None),
        (None, None),
    ]
    for nom, attendu in cas:
        r = get_printer_dll(nom)
        assert r == attendu, f"{nom!r}: attendu {attendu}, got {r}"
    print(f"[OK] table de selection : {len(cas)} cas")


def test_driver_prime_sur_le_nom():
    """Le nom est editable par l'operateur, le driver est la source fiable.
    Une entree renommee 'DP-DS620' dont le driver dit DS-RX1 ne doit PAS
    faire charger Cx2Stat64 : ce serait le segfault MB-50."""
    r = get_printer_dll("DP-DS620", "DP-DS-RX1")
    assert r != "Cx2Stat64.dll", f"Cx2Stat64 sur une RX1 = segfault, got {r}"
    print(f"[OK] nom 'DP-DS620' + driver RX1 -> {r} (pas Cx2Stat64)")


def test_identification_contradictoire_refuse():
    """Nom et driver designent deux familles -> None, on ne devine pas."""
    assert get_printer_dll("DP-DS620", "DP-DS-RX1") is None
    assert get_printer_dll("DP-DS-RX1", "DP-DS620") is None
    print("[OK] identification contradictoire -> None")


def test_driver_seul_suffit():
    """Nom maison, driver fiable."""
    assert get_printer_dll("Imprimante du bar", "DP-DS-RX1") == "CyStat64.dll"
    assert get_printer_dll("Imprimante du bar", "DP-DS620") == "Cx2Stat64.dll"
    print("[OK] driver seul suffit a identifier")


def test_cache_dll_ne_memorise_pas_les_echecs():
    """Un echec de chargement ne doit PAS etre mis en cache : il figerait
    'DLL introuvable' pour toute la vie du process, ce qui declenche une
    alerte critique + SMS jamais resolue (alertes_monitor range cette valeur
    avec 'Imprimante deconnectee')."""
    from monitoring import dnp_dll
    with patch.dict(dnp_dll._cache, {}, clear=True):
        # 1er appel : la DLL est introuvable
        with patch.object(dnp_dll, "find_dll_path", return_value=None):
            assert dnp_dll.load_dll("Cx2Stat64.dll") is None
        assert "Cx2Stat64.dll" not in dnp_dll._cache, \
            "un echec ne doit JAMAIS etre mis en cache"
        # 2e appel : la DLL est de nouveau la -> doit etre rechargee
        fake = FakeDLL("Cx2Stat64.dll")
        with patch.object(dnp_dll, "find_dll_path", return_value="C:\\fake.dll"), \
             patch("ctypes.WinDLL", return_value=fake):
            assert dnp_dll.load_dll("Cx2Stat64.dll") is fake
    print("[OK] cache DLL : les echecs ne sont pas memorises")


def test_politique_kapsule():
    """REGRESSION A NE PAS INTRODUIRE : sur les bornes Kapsule + DS620, le
    collector heartbeat ouvre le port depuis des mois sans incident et c'est
    ce qui alimente feuilles_restantes (Barrillet remonte bien 127). Un garde
    Kapsule global casserait ces bornes.

    La RX1 a rejoint la liste en v1.0.28.30, sur mesure et non par analogie :
    Kapsule 0.1.60 n'embarque que Cx2Stat64 (verifie dans ses resources sur
    MB-50), il ne tient donc pas le port d'une RX1 et ne publie jamais son
    compteur. En revanche health.json reste la source pour les modeles que
    Kapsule SAIT lire — on ne lui dispute pas un port qu'il utilise."""
    from monitoring.alertes.constants import (
        KAPSULE_PORT_ALLOWED_DLLS, KAPSULE_HEALTH_JSON_DLLS,
    )
    assert "Cx2Stat64.dll" in KAPSULE_PORT_ALLOWED_DLLS, \
        "les DS620 doivent rester ouvrables sur Kapsule"
    assert "CyStat64.dll" in KAPSULE_PORT_ALLOWED_DLLS, \
        "la RX1 doit etre lisible sur Kapsule, sinon MB-50 reste aveugle"
    assert "Cx2Stat64.dll" in KAPSULE_HEALTH_JSON_DLLS, \
        "le compteur DS620 sur Kapsule vient de health.json, pas du port"
    assert "CyStat64.dll" not in KAPSULE_HEALTH_JSON_DLLS, \
        "Kapsule ne publie pas le compteur RX1 : attendre = rester aveugle"
    print("[OK] politique Kapsule : DS620 via health.json, RX1 en direct")


def test_codes_statut_rx1_non_interpretes():
    """Un seul code RX1 a ete observe a ce jour (0x00010001 'En veille',
    identique a la DS620). Le fourre-tout 'tout code >= 0x40001 = panne
    mecanique' ne doit pas s'appliquer a un modele dont on ne connait pas la
    table : il declenche une alerte critique, un SMS, et l'ecran de rupture
    plein ecran qui bloque la borne pour les clients."""
    from monitoring.alertes.constants import STATUS_CODES_TRUSTED_DLLS
    assert "Cx2Stat64.dll" in STATUS_CODES_TRUSTED_DLLS
    assert "CyStat64.dll" not in STATUS_CODES_TRUSTED_DLLS, \
        "les codes RX1 ne sont pas encore valides en production"
    print("[OK] codes statut : RX1 journalisee, pas interpretee")


if __name__ == "__main__":
    test_selection_dll_table()
    test_driver_prime_sur_le_nom()
    test_identification_contradictoire_refuse()
    test_driver_seul_suffit()
    test_cache_dll_ne_memorise_pas_les_echecs()
    test_politique_kapsule()
    test_codes_statut_rx1_non_interpretes()
    test_compteur_rx1_utilise_media_counter_r()
    test_cx2stat_sondee_avant_cystat()
    test_ds620_choisit_cx2stat()
    test_rx1_prefixee_choisit_cystat()
    test_rx1_renommee_choisit_cystat()
    test_rx1_detectee_via_driver_registre()
    test_ds820_aucune_dll()
    test_imprimante_non_dnp_ignoree()
    test_melange_ds620_et_rx1()
    test_kapsule_health_json_prioritaire()
    test_kapsule_ds620_health_json_muet_reste_silencieux()
    test_kapsule_rx1_health_json_muet_lit_le_port()
    test_collector_dll_introuvable_ne_se_declare_pas_sain()
    test_collector_rx1_injoignable_ne_bloque_pas_la_borne()
    test_collector_ds620_nominal_inchange()
    test_collector_rx1_publie_le_bon_compteur()
    test_alertes_codes_rx1_aucune_conclusion()
    test_alertes_ds620_inchangees()
    test_ports_ambigus_ecartes()
    test_printer_standby_ne_touche_pas_la_rx1()
    test_printer_standby_trouve_encore_les_ds620()
    test_imprimante_dll_hors_payload_heartbeat()
    test_jauge_papier_capacite_rx1()
    print("\nTous les tests RX1 OK !")
