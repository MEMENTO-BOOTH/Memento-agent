"""Test du fix multi-event scan dans drive_backup.

Verifie que `_detecter_tous_evenements` retourne tous les sous-dossiers de
C:\\dslrBooth\\ qui ont une structure d'event (Originals\\ ou Prints\\),
en excluant les dossiers systeme.
"""

import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import monitoring.drive_backup as drive_backup


def test_detecte_tous_les_events():
    """Cree une fausse arbo C:\\dslrBooth\\ et verifie que tous les events sont vus."""
    tmp = tempfile.mkdtemp()
    try:
        # Patch DSLRBOOTH_BASE le temps du test
        original_base = drive_backup.DSLRBOOTH_BASE
        drive_backup.DSLRBOOTH_BASE = tmp

        # Arbo : 3 events + Settings + Templates + un fichier .jpg a la racine
        for event in ("clubtrotter", "Latina Cafe", "The People"):
            os.makedirs(os.path.join(tmp, event, "Originals"))
            os.makedirs(os.path.join(tmp, event, "Prints"))
        os.makedirs(os.path.join(tmp, "Settings"))
        os.makedirs(os.path.join(tmp, "Templates"))
        # Dossier sans Originals/Prints — doit etre ignore
        os.makedirs(os.path.join(tmp, "DossierVide"))
        # Un fichier .jpg a la racine — doit etre ignore (c'est un fichier, pas un dossier)
        with open(os.path.join(tmp, "rogue.jpg"), "w") as f:
            f.write("fake")

        events = drive_backup._detecter_tous_evenements()
        events_set = set(events)

        assert events_set == {"clubtrotter", "Latina Cafe", "The People"}, (
            f"Events detectes incorrects: {events_set}"
        )
        print(f"[OK] test_detecte_tous_les_events : {sorted(events_set)}")
    finally:
        drive_backup.DSLRBOOTH_BASE = original_base
        shutil.rmtree(tmp, ignore_errors=True)


def test_event_avec_seulement_originals():
    """Un dossier avec juste Originals\\ (pas de Prints) doit etre detecte."""
    tmp = tempfile.mkdtemp()
    try:
        original_base = drive_backup.DSLRBOOTH_BASE
        drive_backup.DSLRBOOTH_BASE = tmp

        os.makedirs(os.path.join(tmp, "soiree", "Originals"))
        # Pas de Prints

        events = drive_backup._detecter_tous_evenements()
        assert "soiree" in events, f"soiree devrait etre detecte: {events}"
        print("[OK] test_event_avec_seulement_originals : detecte avec Originals seul")
    finally:
        drive_backup.DSLRBOOTH_BASE = original_base
        shutil.rmtree(tmp, ignore_errors=True)


def test_base_inexistante():
    """Si C:\\dslrBooth\\ n'existe pas, retourne []."""
    original_base = drive_backup.DSLRBOOTH_BASE
    drive_backup.DSLRBOOTH_BASE = r"X:\path\does\not\exist"
    try:
        events = drive_backup._detecter_tous_evenements()
        assert events == [], f"Devrait retourner [] si base inexistante, got {events}"
        print("[OK] test_base_inexistante : [] retourne")
    finally:
        drive_backup.DSLRBOOTH_BASE = original_base


if __name__ == "__main__":
    test_detecte_tous_les_events()
    test_event_avec_seulement_originals()
    test_base_inexistante()
    print("\nTous les tests OK !")
