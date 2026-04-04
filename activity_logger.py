"""Logger d'activité — écrit dans alertes.log avec rotation 10 Mo.
Chaque entrée est horodatée et détaillée."""

import os
import sys
from datetime import datetime

LOG_MAX_SIZE = 10 * 1024 * 1024  # 10 Mo

def _log_dir():
    if hasattr(sys, 'frozen'):
        return os.path.dirname(sys.executable)
    return os.path.join(os.path.expanduser("~"), ".mementoagent")

def _log_path():
    d = _log_dir()
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "alertes.log")

def _tpe_log_path():
    d = _log_dir()
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "tpe.log")

def _rotate(path):
    try:
        if os.path.exists(path) and os.path.getsize(path) > LOG_MAX_SIZE:
            old = path + ".old"
            if os.path.exists(old):
                os.remove(old)
            os.rename(path, old)
    except Exception:
        pass

def _write(lines):
    path = _log_path()
    _rotate(path)
    try:
        with open(path, "a", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
            f.write("\n")
    except Exception:
        pass

def _write_tpe(lines):
    path = _tpe_log_path()
    _rotate(path)
    try:
        with open(path, "a", encoding="utf-8") as f:
            for line in lines:
                f.write(line + "\n")
            f.write("\n")
    except Exception:
        pass

def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ════════════════════════════════════════════════════
#  API publique
# ════════════════════════════════════════════════════

def log_session(session_id, code, borne_name):
    _write([
        f"[{_ts()}] [EMMENTO] Nouvelle session détectée",
        f"  Session ID: {session_id}",
        f"  Code généré: {code} (7 chars, unicité vérifiée)",
        f"  Borne: {borne_name}",
    ])

def log_original(filename, size_bytes, full_path):
    size_mb = round(size_bytes / (1024 * 1024), 1) if size_bytes else 0
    _write([
        f"[{_ts()}] [EMMENTO] Original détecté",
        f"  Fichier: {filename}",
        f"  Taille: {size_mb} Mo",
        f"  Chemin: {full_path}",
    ])

def log_print(filename, size_bytes, session_id, bar):
    size_mb = round(size_bytes / (1024 * 1024), 1) if size_bytes else 0
    _write([
        f"[{_ts()}] [EMMENTO] Print détecté",
        f"  Fichier: {filename}",
        f"  Taille: {size_mb} Mo",
        f"  Session: {session_id}",
        f"  Bar: {bar}",
    ])

def log_supabase_ok(session_id, code, nb_prints, nb_originals):
    _write([
        f"[{_ts()}] [EMMENTO] Envoi Supabase",
        f"  Session: {session_id}",
        f"  Code: {code}",
        f"  Prints: {nb_prints}",
        f"  Originals: {nb_originals}",
        f"  Statut: OK",
    ])

def log_supabase_error(session_id, code, error):
    _write([
        f"[{_ts()}] [EMMENTO] Erreur envoi Supabase",
        f"  Session: {session_id}",
        f"  Code: {code}",
        f"  Erreur: {error}",
    ])

def log_drive_error(filename, src, dst, error):
    _write([
        f"[{_ts()}] [DRIVE] Erreur copie",
        f"  Fichier: {filename}",
        f"  Source: {src}",
        f"  Destination: {dst}",
        f"  Erreur: {error}",
    ])

def log_drive_inaccessible():
    _write([
        f"[{_ts()}] [DRIVE] Google Drive inaccessible",
    ])

def log_drive_event(event_name):
    _write([
        f"[{_ts()}] [DRIVE] Nouvel événement détecté",
        f"  Événement: {event_name}",
    ])

def log_alerte_creee(type_alerte, gravite, source, message, borne_id, status_code=None):
    lines = [
        f"[{_ts()}] [ALERTE] Alerte créée",
        f"  Type: {type_alerte}",
        f"  Gravité: {gravite}",
        f"  Source: {source}",
        f"  Message: {message}",
        f"  Borne: {borne_id}",
    ]
    if status_code is not None:
        lines.append(f"  Code imprimante: 0x{status_code:X}")
    _write(lines)

def log_alerte_resolue(type_alerte, resolue_par, status_code=None):
    lines = [
        f"[{_ts()}] [ALERTE] Alerte résolue",
        f"  Type: {type_alerte}",
        f"  Résolu par: {resolue_par}",
    ]
    if status_code is not None:
        lines.append(f"  Code imprimante: 0x{status_code:X}")
    _write(lines)

def log_alerte_maj_timestamp(type_alerte, alerte_id):
    _write([
        f"[{_ts()}] [ALERTE] Alerte toujours active — timestamp mis à jour",
        f"  Type: {type_alerte}",
        f"  ID: {alerte_id}",
    ])

def log_generic(category, message):
    _write([
        f"[{_ts()}] [{category}] {message}",
    ])


# ════════════════════════════════════════════════════
#  TPE / PAIEMENTS — fichier tpe.log
# ════════════════════════════════════════════════════

def log_tpe_paiement(montant_cents, heure, numero=None):
    n = f" (#{numero})" if numero else ""
    montant = int(montant_cents) / 100.0
    _write_tpe([
        f"[{_ts()}] [PAIEMENT] Crédit reçu{n}",
        f"  Montant: {montant:.2f}€ ({montant_cents} centimes)",
        f"  Heure CashInterface: {heure}",
    ])

def log_tpe_impression(key, credit_left, heure):
    _write_tpe([
        f"[{_ts()}] [IMPRESSION] Touche {key} envoyée à dslrBooth",
        f"  Crédit restant: {credit_left}",
        f"  Heure CashInterface: {heure}",
        f"  Statut: IMPRESSION DÉCLENCHÉE",
    ])

def log_tpe_receiver(receiver, heure):
    _write_tpe([
        f"[{_ts()}] [RECEIVER] {receiver}",
        f"  Heure CashInterface: {heure}",
    ])

def log_tpe_resumed(heure):
    _write_tpe([
        f"[{_ts()}] [TPE] RESUMED — accepte les cartes",
        f"  Heure: {heure}",
    ])

def log_tpe_inhibited(heure, delai=None):
    d = f" (délai: {delai}s)" if delai else ""
    _write_tpe([
        f"[{_ts()}] [TPE] INHIBITED — fermé{d}",
        f"  Heure: {heure}",
    ])

def log_tpe_confirmation(tx_id):
    _write_tpe([
        f"[{_ts()}] [CONFIRMATION] Impression confirmée dans Supabase",
        f"  Transaction: {tx_id}",
    ])

def log_tpe_anomalie(tx_id, flag):
    _write_tpe([
        f"[{_ts()}] [ANOMALIE] Impression non confirmée",
        f"  Transaction: {tx_id}",
        f"  Flag: {flag}",
    ])

def log_tpe_erreur(erreur):
    _write_tpe([
        f"[{_ts()}] [ERREUR] {erreur}",
    ])

def log_tpe_transaction_supabase(borne_id, montant, impression, flag, resumed, inhibited, delai):
    _write_tpe([
        f"[{_ts()}] [TRANSACTION] Nouvelle transaction Supabase",
        f"  Borne: {borne_id[:8] if borne_id else '?'}",
        f"  Montant: {montant}€",
        f"  Impression: {'OUI' if impression else 'NON'}",
        f"  Flag: {flag or 'aucun'}",
        f"  TPE resumed: {resumed or '—'}",
        f"  TPE inhibited: {inhibited or '—'}",
        f"  Délai: {delai}s" if delai else f"  Délai: —",
    ])


# ════════════════════════════════════════════════════
#  UI entries — pour l'affichage dans l'app
# ════════════════════════════════════════════════════

_ui_entries = []
_ui_max = 200

def _add_ui(entry_type, time_str, text, icon=None, resolved=False):
    """Ajoute une entrée pour l'affichage UI."""
    _ui_entries.append({
        "type": entry_type,
        "time": time_str,
        "text": text,
        "icon": icon or "",
        "resolved": resolved,
    })
    while len(_ui_entries) > _ui_max:
        _ui_entries.pop(0)

def ui_log(text):
    _add_ui("log", datetime.now().strftime("%H:%M:%S"), text)

def ui_alerte(text, icon, resolved=False):
    _add_ui("alerte", datetime.now().strftime("%H:%M:%S"), text, icon, resolved)

def get_ui_entries():
    return list(_ui_entries)
