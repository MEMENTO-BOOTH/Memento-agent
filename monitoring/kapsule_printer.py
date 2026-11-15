"""Lecture du compteur papier DNP expose par Kapsule Bar.

POURQUOI
--------
Sur les bornes Kapsule, l'agent ne doit PAS toucher au port DNP : Kapsule
le tient pour imprimer, et le double acces provoquait un segfault C qui
bypassait faulthandler et tuait le process agent entier (observe MB-50 :
crash du dashboard 3 s apres ouverture). C'est pour ca que
PrinterCounterWatcher a ete desactive sur Kapsule en v1.0.28.13.

Effet de bord : plus aucune detection "paiement sans photo" sur ces bornes.
Mesure du 15/11/2026 : sur 259 paiements depuis le 13/11, seuls 41 etaient
verifies (les 3 bornes dslrBooth). Les 218 autres, tous sur Kapsule,
n'etaient surveilles par personne.

SOLUTION
--------
Kapsule publie la valeur brute du compteur dans son health.json (fichier
que l'agent lit deja via kapsule_watcher.py). L'agent la lit depuis le
disque : zero acces USB, donc le risque de segfault disparait, et toute
la logique metier (fenetre 180 s, anomalie non_delivree, alerte, SMS,
export Excel) reste cote agent, identique a ce qui tourne deja sur
dslrBooth.

Format attendu dans health.json :
    {
      "state": "...",                                   // existant
      "printer_media_counter": 342,                     // GetMediaCounter()
      "printer_counter_at": "2026-11-15T21:04:33.120Z"  // ISO 8601 UTC
    }
"""

import json
import os
from datetime import datetime, timezone

# Au-dela de ce delai, la valeur publiee par Kapsule est consideree perimee.
# Kapsule vise un rafraichissement toutes les 3 a 30 s ; 120 s laisse de la
# marge (redemarrage Kapsule, machine chargee) sans risquer de calculer une
# baisse de compteur sur une valeur morte.
MAX_AGE_SECONDS = 120

# Noms de champs acceptes, par ordre de preference. Tolerance au cas ou
# Kapsule publie sous un nom legerement different.
_COUNTER_KEYS = ("printer_media_counter", "media_counter", "printer_counter")
_TIMESTAMP_KEYS = ("printer_counter_at", "media_counter_at", "printer_counter_ts")


def _health_paths():
    return [
        os.path.join(os.environ.get("APPDATA", ""), "kapsule-bar", "health.json"),
        os.path.join(
            os.environ.get("LOCALAPPDATA", ""), "Programs", "kapsule-bar", "health.json"
        ),
    ]


def _first_key(data, keys):
    for k in keys:
        if k in data:
            return data[k]
    return None


def _parse_ts(raw):
    try:
        if not isinstance(raw, str):
            return None
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def read_media_counter(now=None):
    """Retourne le compteur papier publie par Kapsule, ou None.

    None quand : fichier absent, JSON illisible, champ absent (Kapsule pas
    encore a jour -> retrocompatible), valeur <= 0 (bug veille DNP, cf.
    Latina Cafe 14/06 ou GetMediaCounter renvoyait 0 en sommeil) ou valeur
    perimee de plus de MAX_AGE_SECONDS.

    Ne leve jamais : un probleme de lecture doit degrader vers 'pas de
    compteur', jamais casser le tick du watcher."""
    try:
        for path in _health_paths():
            if not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue

            raw = _first_key(data, _COUNTER_KEYS)
            if raw is None:
                # Kapsule n'expose pas (encore) le compteur sur cette borne
                continue
            try:
                counter = int(raw)
            except (TypeError, ValueError):
                continue
            # Meme filtre que la lecture DLL : 0 ou negatif = imprimante en
            # veille ou lecture aberrante, surtout pas une vraie valeur.
            if counter <= 0:
                return None

            # Si Kapsule date sa mesure, on refuse une valeur trop vieille.
            # Sans date, on accepte (Kapsule reecrit health.json en continu).
            ts = _parse_ts(_first_key(data, _TIMESTAMP_KEYS))
            if ts is not None:
                ref = now or datetime.now(timezone.utc)
                age = (ref - ts).total_seconds()
                if age > MAX_AGE_SECONDS or age < -MAX_AGE_SECONDS:
                    return None
            return counter
    except Exception:
        pass
    return None
