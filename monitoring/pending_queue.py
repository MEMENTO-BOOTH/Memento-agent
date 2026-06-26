"""Cahier de secours local pour les sessions e-memento.

Incident REV3 22/06/2026 : agent mort + wifi mort -> sessions perdues.
Quand l'envoi a Supabase echoue (wifi mort, Supabase down, etc.), on ecrit
le payload dans pending_sessions.json. Au prochain tick(), on essaie de
vider la queue. Les payloads qui passent sont retires, ceux qui echouent
sont remis en queue.

Rotation : quand le fichier atteint MAX_ENTRIES, il est renomme en
pending_sessions.json.1 et un nouveau fichier vide est cree. On garde
MAX_ARCHIVES archives (.1 a .5). Au-dela, la plus ancienne est supprimee.

Anti-doublon : le rejeu utilise upsert sur session_id cote ememento, donc
re-envoyer la meme session ne cree pas de doublon en base.
"""

import os
import sys
import json
import time
from datetime import datetime


MAX_ENTRIES = 1000
MAX_ARCHIVES = 5


def _queue_dir():
    """Dossier ou vit le cahier (= dossier de l'agent si frozen, sinon repo)."""
    if hasattr(sys, "frozen"):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _queue_path():
    return os.path.join(_queue_dir(), "pending_sessions.json")


def _archive_path(n):
    return f"{_queue_path()}.{n}"


def _log(msg):
    try:
        import activity_logger as alog
        alog.log_generic("PENDING", msg)
    except Exception:
        pass


def _read_safe():
    """Lit la queue. Si JSON corrompu, sauvegarde + repart sur liste vide."""
    path = _queue_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            raise ValueError("queue not a list")
        return data
    except Exception as e:
        corrupt = f"{path}.corrupt-{int(time.time())}"
        try:
            os.rename(path, corrupt)
        except Exception:
            pass
        _log(f"Queue corrompue ({e}), sauvegardee en {corrupt}, redemarre vide")
        return []


def _write_atomic(items):
    """Ecrit la queue atomiquement (tmp + os.replace)."""
    path = _queue_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _rotate_if_needed(items):
    """Si la liste depasse MAX_ENTRIES, rotation .json -> .json.1 etc."""
    if len(items) < MAX_ENTRIES:
        return items
    oldest = _archive_path(MAX_ARCHIVES)
    if os.path.exists(oldest):
        try:
            os.remove(oldest)
        except Exception:
            pass
    for n in range(MAX_ARCHIVES - 1, 0, -1):
        src = _archive_path(n)
        dst = _archive_path(n + 1)
        if os.path.exists(src):
            try:
                os.rename(src, dst)
            except Exception:
                pass
    try:
        _write_atomic(items)
        os.rename(_queue_path(), _archive_path(1))
        _log(f"Rotation: {MAX_ENTRIES} entries archivees en .json.1 (cahier reinitialise)")
    except Exception as e:
        _log(f"Rotation echouee: {e}")
    return []


def enqueue(kind, payload):
    """Ajoute une entree dans la queue. kind = 'code_reserve' ou 'session_update'."""
    items = _read_safe()
    items.append({
        "kind": kind,
        "payload": payload,
        "first_attempt": datetime.now().astimezone().isoformat(),
        "retry_count": 0,
    })
    items = _rotate_if_needed(items)
    try:
        _write_atomic(items)
        _log(f"Enqueue {kind} session={payload.get('session_id', '?')[:12]} "
             f"(total queue: {len(items)})")
    except Exception as e:
        _log(f"Enqueue echoue ({kind}): {e}")


def peek(limit=None):
    """Lit la queue sans la vider. Si limit, retourne les N premieres."""
    items = _read_safe()
    return items[:limit] if limit else items


def replace_all(items):
    """Remplace la queue par la liste donnee (pour replay : on garde les echecs)."""
    try:
        _write_atomic(items)
    except Exception as e:
        _log(f"Replace echoue: {e}")
