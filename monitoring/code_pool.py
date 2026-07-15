"""Pool local de codes e-memento pre-inseres en base."""

import os
import sys
import json
import time
import secrets
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone


CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 7
POOL_THRESHOLD_LOW = 20
POOL_TARGET = 100
REFILL_INTERVAL_SEC = 600
REFILL_MIN_INTERVAL_SEC = 30

_LOCK = threading.RLock()
_LAST_REFILL_TS = 0.0
_TIMER_STARTED = False
_CACHED_BORNE_ID = None


def _pool_path():
    if hasattr(sys, "frozen"):
        return os.path.join(os.path.dirname(sys.executable), "code_pool.json")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "code_pool.json")


def _log(msg):
    try:
        import activity_logger as alog
        alog.log_generic("POOL", msg)
    except Exception:
        pass


def _read():
    path = _pool_path()
    if not os.path.exists(path):
        return {"available": [], "used": [], "pending_link": []}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data.setdefault("available", [])
        data.setdefault("used", [])
        data.setdefault("pending_link", [])
        return data
    except Exception as e:
        corrupt = f"{path}.corrupt-{int(time.time())}"
        try:
            os.rename(path, corrupt)
        except Exception:
            pass
        _log(f"corrompu ({e}), sauvegarde {corrupt}")
        return {"available": [], "used": [], "pending_link": []}


def _write(data):
    path = _pool_path()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _gen_code():
    return "".join(secrets.choice(CODE_CHARS) for _ in range(CODE_LENGTH))


def pop_code():
    with _LOCK:
        data = _read()
        if not data["available"]:
            return None
        code = data["available"].pop(0)
        data["used"].append(code)
        try:
            _write(data)
        except Exception:
            pass
    threading.Thread(target=_refill_async_fire, args=(None,), daemon=True).start()
    return code


def pending_link_add(code, session_data):
    with _LOCK:
        data = _read()
        if code in data["used"]:
            data["used"].remove(code)
        data["pending_link"] = [e for e in data["pending_link"] if e.get("code") != code]
        data["pending_link"].append(session_data)
        _write(data)


def _refill_async_fire(borne_id):
    try:
        if borne_id is None:
            borne_id = _cached_borne_id()
        if borne_id:
            refill_if_needed(borne_id)
    except Exception:
        pass


def _cached_borne_id():
    global _CACHED_BORNE_ID
    if _CACHED_BORNE_ID:
        return _CACHED_BORNE_ID
    try:
        import supabase_client as supa
        b = supa.get_or_create_borne()
        if b:
            _CACHED_BORNE_ID = b.get("id")
    except Exception:
        pass
    return _CACHED_BORNE_ID


def refill_if_needed(borne_id):
    global _LAST_REFILL_TS, _CACHED_BORNE_ID
    if borne_id:
        _CACHED_BORNE_ID = borne_id
    with _LOCK:
        now = time.time()
        if now - _LAST_REFILL_TS < REFILL_MIN_INTERVAL_SEC:
            return
        _LAST_REFILL_TS = now
        data = _read()
        available_count = len(data["available"])
        if available_count >= POOL_THRESHOLD_LOW:
            return
        need = POOL_TARGET - available_count

    added = 0
    attempts = 0
    while added < need and attempts < 5:
        attempts += 1
        batch_size = min(need - added, 100)
        candidates = list({_gen_code() for _ in range(batch_size * 2)})[:batch_size]
        ok = _post_batch(borne_id, candidates)
        if ok:
            with _LOCK:
                data = _read()
                data["available"].extend(ok)
                _write(data)
            added += len(ok)
        else:
            break

    if added > 0:
        _log(f"refill +{added} (pool {available_count + added})")


def _post_batch(borne_id, codes):
    import supabase_client as supa
    now_iso = datetime.now(timezone.utc).isoformat()
    rows = [{
        "borne_id": borne_id,
        "code": c,
        "session_id": f"pool_{c}",
        "bar": None,
        "timestamp": now_iso,
        "photos": "[]",
        "originals": "[]",
        "statut": "reserve",
    } for c in codes]
    body = json.dumps(rows).encode("utf-8")
    req = urllib.request.Request(
        f"{supa.SUPABASE_URL}/rest/v1/ememento",
        data=body, method="POST",
        headers={**supa.HEADERS_MINIMAL, "Prefer": "return=minimal"},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status in (200, 201, 204):
                return codes
    except urllib.error.HTTPError as e:
        if e.code == 409:
            return _post_individual(borne_id, codes)
    except Exception:
        pass
    return []


def _post_individual(borne_id, codes):
    import supabase_client as supa
    now_iso = datetime.now(timezone.utc).isoformat()
    ok = []
    for c in codes:
        row = {
            "borne_id": borne_id, "code": c, "session_id": f"pool_{c}", "bar": None,
            "timestamp": now_iso, "photos": "[]", "originals": "[]", "statut": "reserve",
        }
        req = urllib.request.Request(
            f"{supa.SUPABASE_URL}/rest/v1/ememento",
            data=json.dumps(row).encode("utf-8"), method="POST",
            headers={**supa.HEADERS_MINIMAL, "Prefer": "return=minimal"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status in (200, 201, 204):
                    ok.append(c)
        except Exception:
            pass
    return ok


def pending_link_flush():
    import supabase_client as supa
    with _LOCK:
        entries = list(_read()["pending_link"])
    if not entries:
        return

    still_pending = []
    flushed = 0
    for entry in entries:
        code = entry.get("code")
        if not code:
            continue
        photos = entry.get("photos")
        originals = entry.get("originals")
        payload = {
            "session_id": entry.get("session_id"),
            "bar": entry.get("bar"),
            "timestamp": entry.get("timestamp"),
            "photos": photos if isinstance(photos, str) else json.dumps(photos or []),
            "originals": originals if isinstance(originals, str) else json.dumps(originals or []),
            "statut": "en_attente",
        }
        url = f"{supa.SUPABASE_URL}/rest/v1/ememento?code=eq.{urllib.parse.quote(code)}"
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"), method="PATCH",
            headers=supa.HEADERS_MINIMAL,
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                if r.status in (200, 201, 204):
                    flushed += 1
                    continue
            still_pending.append(entry)
        except urllib.error.HTTPError as e:
            if e.code == 404 and _fallback_insert(entry, payload):
                flushed += 1
            else:
                still_pending.append(entry)
        except Exception:
            still_pending.append(entry)

    if flushed:
        with _LOCK:
            data = _read()
            still_codes = {e.get("code") for e in still_pending}
            data["pending_link"] = [e for e in data["pending_link"] if e.get("code") in still_codes]
            _write(data)
        _log(f"flush {flushed} OK, {len(still_pending)} retry")


def _fallback_insert(entry, payload):
    import supabase_client as supa
    insert_payload = {
        "borne_id": entry.get("borne_id"),
        "code": entry.get("code"),
        **payload,
    }
    req = urllib.request.Request(
        f"{supa.SUPABASE_URL}/rest/v1/ememento",
        data=json.dumps(insert_payload).encode("utf-8"), method="POST",
        headers={**supa.HEADERS_MINIMAL, "Prefer": "return=minimal"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status in (200, 201, 204)
    except Exception:
        return False


def start_background_refill(borne_id):
    global _TIMER_STARTED
    if _TIMER_STARTED:
        return
    _TIMER_STARTED = True

    def _loop():
        while True:
            try:
                refill_if_needed(borne_id)
            except Exception:
                pass
            time.sleep(REFILL_INTERVAL_SEC)

    t = threading.Thread(target=_loop, name="code_pool_refill", daemon=True)
    t.start()
