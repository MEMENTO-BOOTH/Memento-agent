"""E-memento Watcher — intégré dans MementoAgent.
Surveille le log dslrBooth, génère des codes courts uniques (7 chars),
envoie les sessions dans la table 'ememento' de Supabase.
Codes expirés après 2 mois."""

import os
import re
import glob
import json
import time
import secrets
import string
from datetime import datetime

import requests
import supabase_client as supa

# Caractères sans ambiguïté (pas de 0/O, 1/I/L)
CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 7

# Fenêtre de temps (en secondes) pour chercher les Originals avant un print.
# Une session typique = 4 photos prises sur ~30s + un ecran preview/select
# pouvant durer 30-90s, puis print. La premiere photo peut donc avoir un
# mtime > 60s avant le print → elle etait perdue avec l'ancienne fenetre.
# 180s = couverture confortable pour la quasi-totalite des sessions sans
# risque significatif de cross-contamination (deux sessions completes en
# moins de 3 min sur la meme borne est rare).
ORIGINALS_TIME_WINDOW = 180

# Re-scan apres l'envoi initial : rattrape les originals movés en retard
# par dslrbooth (race condition entre l'ecriture du print_log et le move des
# fichiers vers <bar>\Originals\).
RESCAN_DELAY_SEC = 30      # delai entre l'envoi initial et le rescan
RESCAN_TTL_SEC = 300       # garde-fou contre une fuite memoire si un rescan
                           # bloque pour une raison quelconque

DSLRBOOTH_LOG = os.path.join(
    os.environ.get("APPDATA", ""), "dslrBooth", "Logs", "dslrbooth.log"
)
DSLRBOOTH_CONFIG = os.path.join(
    os.environ.get("APPDATA", ""), "dslrBooth", "app_settings_2021.json"
)
# dslrBooth renomme sa DB sqlite chaque annee (database_2025.db,
# database_2026.db, ...). On resoud dynamiquement le fichier le plus
# recent pour ne pas casser silencieusement au changement d'annee.
_DSLRBOOTH_DB_MATCHES = sorted(
    glob.glob(os.path.join(os.environ.get("APPDATA", ""), "dslrBooth", "database_*.db")),
    key=os.path.getmtime,
    reverse=True,
)
DSLRBOOTH_DB = _DSLRBOOTH_DB_MATCHES[0] if _DSLRBOOTH_DB_MATCHES else ""
from .dslrbooth_config import get_dslrbooth_base
DSLRBOOTH_BASE = get_dslrbooth_base()
QR_OUTPUT = r"C:\SocialBooth\qrcode.png"

# Config par défaut pour l'image du code
DEFAULT_CODE_CONFIG = {
    "image_largeur": 200,
    "image_hauteur": 200,
    "couleur_fond": "transparent",
    "taille_police": 50,
    "couleur_texte": "white",
    "police": "arial.ttf",
}

# Regex pour parser le log dslrBooth
RE_SESSION = re.compile(r"SessionID changed from .+ to (\S+)")
# Deux formats possibles selon la version de dslrBooth :
# Ancien: "File added to database for sessionNanoId: ABC123, file: C:\...\Prints\photo.jpg"
# Nouveau: "Setting picturebox image: C:\...\Prints\photo.jpg"
RE_PRINT_OLD = re.compile(r"File added to database for sessionNanoId: (\S+), file: (.+\\Prints\\.+)")
RE_PRINT_NEW = re.compile(r"Setting picturebox image: (.+\\Prints\\.+)")

# Headers Supabase pour ememento (UPSERT)
HEADERS_UPSERT = {
    "apikey": supa.SUPABASE_KEY,
    "Authorization": f"Bearer {supa.SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal,resolution=merge-duplicates",
}


def _load_code_config():
    """Charge la config du code depuis le registre Windows (paramètres de l'app)."""
    from paths import reg_get
    cfg = dict(DEFAULT_CODE_CONFIG)
    for key in cfg:
        val = reg_get(f"emmento_{key}")
        if val is not None:
            if key in ("image_largeur", "image_hauteur", "taille_police"):
                try:
                    val = int(val)
                except (ValueError, TypeError):
                    continue
            cfg[key] = val
    return cfg


def _reserver_code(borne_id, session_id, bar, timestamp):
    from . import code_pool
    code = code_pool.pop_code()
    if code is None:
        code = "".join(secrets.choice(CODE_CHARS) for _ in range(CODE_LENGTH))
        try:
            import activity_logger as alog
            alog.log_generic("POOL", f"pool vide, code fallback local : {code}")
        except Exception:
            pass
    code_pool.pending_link_add(code, {
        "code": code,
        "session_id": session_id,
        "bar": bar or "inconnu",
        "timestamp": timestamp,
        "photos": [],
        "originals": [],
        "borne_id": borne_id,
    })
    return code


def _expirer_anciens_codes():
    """Marque les codes de plus de 2 mois comme expirés."""
    try:
        from datetime import timedelta
        cutoff = (datetime.now().astimezone() - timedelta(days=60)).isoformat()
        requests.patch(
            f"{supa.SUPABASE_URL}/rest/v1/ememento"
            f"?timestamp=lt.{cutoff}&statut=eq.en_attente",
            headers=supa.HEADERS_MINIMAL,
            json={"statut": "expire"},
            timeout=10,
        )
    except Exception:
        pass


def _generer_image_code(code):
    """Génère l'image du code et la copie dans les templates dslrBooth.
    La taille de l'image s'adapte au texte avec du padding pour éviter les coupures."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("[EMMENTO] Pillow non installé, image non générée")
        return

    cfg = _load_code_config()
    couleur_fond = cfg["couleur_fond"]
    padding = 40  # marge de chaque côté pour éviter les coupures

    try:
        font = ImageFont.truetype(cfg["police"], cfg["taille_police"])
    except OSError:
        try:
            font = ImageFont.truetype(
                os.path.join("C:\\Windows\\Fonts", cfg["police"]),
                cfg["taille_police"],
            )
        except OSError:
            font = ImageFont.load_default()

    # Mesurer le texte d'abord, puis créer l'image à la bonne taille
    tmp = Image.new("RGBA", (1, 1))
    tmp_draw = ImageDraw.Draw(tmp)
    bbox = tmp_draw.textbbox((0, 0), code, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    # Image = taille du texte + padding, minimum la taille configurée
    img_w = max(cfg["image_largeur"], tw + padding * 2)
    img_h = max(cfg["image_hauteur"], th + padding * 2)

    if couleur_fond.lower() == "transparent":
        img = Image.new("RGBA", (img_w, img_h), (0, 0, 0, 0))
    else:
        img = Image.new("RGBA", (img_w, img_h), couleur_fond)

    draw = ImageDraw.Draw(img)
    draw.text(
        ((img_w - tw) // 2, (img_h - th) // 2),
        code,
        fill=cfg["couleur_texte"],
        font=font,
    )

    # Sauver dans le dossier QR
    os.makedirs(os.path.dirname(QR_OUTPUT), exist_ok=True)
    img.save(QR_OUTPUT)

    # Copier dans les templates dslrBooth
    templates_dir = os.path.join(
        os.environ.get("APPDATA", ""), "dslrBooth", "Templates"
    )
    try:
        for dossier in os.listdir(templates_dir):
            qr_path = os.path.join(templates_dir, dossier, "qrcode.png")
            if os.path.exists(qr_path):
                try:
                    img.save(qr_path)
                except Exception:
                    pass
    except Exception:
        pass

    print(f"[EMMENTO] Image code: {code}")


def _get_bar_from_path(chemin):
    """Extrait le nom du bar (dossier event sous DSLRBOOTH_BASE) depuis un
    chemin dslrBooth (typiquement le chemin d'un print ou d'un original).

    Retourne le nom du bar en cas de succes, ou **None** si le parsing
    echoue (path qui ne matche pas DSLRBOOTH_BASE, drive letter parasite,
    fragment vide, etc.). L'appelant doit alors fallback sur le bar
    courant (nom_lieu via _default_bar) plutot que d'inserer un artefact
    comme "C:" en base.

    Match insensible a la case (Windows : "C:\\dslrBooth" == "c:\\dslrbooth")."""
    if not chemin:
        return None
    try:
        prefix = (DSLRBOOTH_BASE + "\\").lower()
        if not chemin.lower().startswith(prefix):
            return None
        relatif = chemin[len(DSLRBOOTH_BASE) + 1:]
        bar = relatif.split("\\")[0].strip()
        # Filtrer les artefacts : vide, "inconnu", drive letter (C:, D:, etc.),
        # ou tout ce qui contient ":" (impossible dans un nom de dossier Windows).
        if not bar or bar.lower() == "inconnu" or ":" in bar:
            return None
        return bar
    except Exception:
        return None


def _trouver_originals(bar, timestamp_print, timestamp_max=None):
    """Cherche les originals dont le mtime tombe dans la fenetre
    [print_ts - ORIGINALS_TIME_WINDOW, timestamp_max].

    timestamp_max permet d'elargir la fenetre apres le print (utilise par le
    re-scan apres RESCAN_DELAY_SEC pour rattraper les fichiers movés en
    retard par dslrbooth). Si None, on plafonne au print_ts (comportement
    historique)."""
    originals_dir = os.path.join(DSLRBOOTH_BASE, bar, "Originals")
    if not os.path.exists(originals_dir):
        return []
    originals = []
    try:
        upper = timestamp_max if timestamp_max is not None else timestamp_print
        window_start = timestamp_print - ORIGINALS_TIME_WINDOW
        for f in os.listdir(originals_dir):
            if not f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                continue
            chemin = os.path.join(originals_dir, f)
            mtime = os.path.getmtime(chemin)
            if window_start <= mtime <= upper:
                originals.append(chemin)
    except Exception:
        pass
    originals.sort(key=lambda f: os.path.getmtime(f))
    return originals


def _envoyer_supabase(session_id, bar, timestamp, photos, code, originals, borne_id):
    if not bar or bar == "inconnu":
        print(f"[EMMENTO] Push skippe : bar inconnu pour session {session_id} (code {code})")
        try:
            import activity_logger as alog
            alog.log_generic("EMMENTO", f"Push skippe, bar inconnu (session {session_id}, code {code})")
        except Exception:
            pass
        return False

    from . import code_pool
    code_pool.pending_link_add(code, {
        "code": code,
        "session_id": session_id,
        "bar": bar,
        "timestamp": timestamp,
        "photos": [os.path.basename(p) for p in (photos or [])],
        "originals": [os.path.basename(p) for p in (originals or [])],
        "borne_id": borne_id,
    })
    try:
        import activity_logger as alog
        alog.log_supabase_ok(session_id, code, len(photos or []), len(originals or []))
        alog.ui_log(f"Code {code} enregistre pour push (session {session_id})")
    except Exception:
        pass
    return True


def _envoyer_supabase_legacy(session_id, bar, timestamp, photos, code, originals, borne_id):
    if not bar or bar == "inconnu":
        return False
    data = {
        "session_id": session_id,
        "code": code,
        "bar": bar,
        "timestamp": timestamp,
        "photos": json.dumps([os.path.basename(p) for p in (photos or [])]),
        "originals": json.dumps([os.path.basename(p) for p in (originals or [])]),
        "statut": "en_attente",
    }
    if borne_id:
        data["borne_id"] = borne_id

    for tentative in range(3):
        try:
            r = requests.post(
                f"{supa.SUPABASE_URL}/rest/v1/ememento?on_conflict=session_id",
                headers=HEADERS_UPSERT,
                json=data,
                timeout=10,
            )
            if r.status_code in (200, 201):
                return True
        except Exception:
            pass
        time.sleep(2)

    try:
        from . import pending_queue
        pending_queue.enqueue("session_update", {
            "session_id": session_id,
            "code": code,
            "bar": bar,
            "timestamp": timestamp,
            "photos": [os.path.basename(p) for p in (photos or [])],
            "originals": [os.path.basename(p) for p in (originals or [])],
            "borne_id": borne_id,
        })
    except Exception as e:
        print(f"[EMMENTO] Enqueue echec: {e}")
    return False


class EmentoWatcher:
    """Watcher e-memento — tourne dans le thread de monitoring."""

    def __init__(self, borne_id, nom_lieu=None):
        self._borne_id = borne_id
        # nom_lieu = nom du bar configure sur la borne (lu depuis Supabase au
        # boot du monitoring). Sert de default pour le champ "bar" quand on
        # ne peut pas encore le deduire du path d'un print dslrBooth.
        # Evite les sessions orphelines avec bar="inconnu" en base.
        self._nom_lieu = nom_lieu or None
        self._start_time = datetime.now()
        self._etat = {
            "session_id": None,
            "code": "",
            "photos": [],
            "originals": [],
            "bar": self._default_bar(),
            "timestamp": None,
        }
        # session_id -> {bar, print_ts, code, timestamp, photos,
        #                originals_envoyes, deadline}
        # Re-scan differé pour rattraper les originals movés en retard apres
        # le print_log (race condition dslrbooth).
        self._pending_rescans = {}
        # Démarrer à la fin du fichier — ne traiter que les NOUVELLES lignes
        self._position = 0
        try:
            if os.path.exists(DSLRBOOTH_LOG):
                self._position = os.path.getsize(DSLRBOOTH_LOG)
                self._charger_session_courante()
        except Exception:
            pass
        try:
            from . import code_pool
            code_pool.refill_if_needed(borne_id)
            code_pool.start_background_refill(borne_id)
        except Exception as e:
            print(f"[EMMENTO] Init code_pool echoue: {e}")

    def _default_bar(self):
        """Bar a utiliser par defaut quand aucun print n'a encore revele le
        path Windows (donc le bar). On utilise le nom_lieu configure sur la
        borne, sinon "inconnu" en dernier recours (et _envoyer_supabase
        skippera l'insert pour eviter de polluer la table)."""
        return self._nom_lieu or "inconnu"

    def _charger_session_courante(self):
        """Lit les dernières lignes du log pour trouver la session active.
        Réserve atomiquement un code et l'enregistre dans Supabase. La
        fonction ``_reserver_code`` garantit toujours un code valide
        (cascade 7→10→hash) — le ticket est imprimé dans tous les cas."""
        try:
            with open(DSLRBOOTH_LOG, "r", encoding="utf-8", errors="ignore") as f:
                lignes = f.readlines()
                for ligne in reversed(lignes[-500:]):
                    m = RE_SESSION.search(ligne)
                    if m:
                        session_id = m.group(1)
                        bar = self._default_bar()
                        timestamp = datetime.now().astimezone().isoformat()
                        code = _reserver_code(self._borne_id, session_id, bar, timestamp)
                        self._etat = {
                            "session_id": session_id,
                            "code": code,
                            "photos": [],
                            "originals": [],
                            "bar": bar,
                            "timestamp": timestamp,
                        }
                        print(f"[EMMENTO] Session en cours récupérée: {session_id} → code: {code}")
                        _generer_image_code(code)
                        return
        except Exception:
            pass

    def _replay_pending(self):
        """Tente de rejouer les sessions en attente dans le cahier de secours.
        Max 3 par tick pour ne pas bloquer le thread monitoring."""
        try:
            from . import pending_queue
        except Exception:
            return
        items = pending_queue.peek()
        if not items:
            return
        traites = items[:3]
        restants = items[3:]
        for entry in traites:
            kind = entry.get("kind")
            p = entry.get("payload") or {}
            try:
                if kind == "code_reserve":
                    data = {
                        "session_id": p["session_id"],
                        "code": p["code"],
                        "bar": p.get("bar") or "inconnu",
                        "timestamp": p["timestamp"],
                        "photos": json.dumps([]),
                        "originals": json.dumps([]),
                        "statut": "en_attente",
                    }
                    if p.get("borne_id"):
                        data["borne_id"] = p["borne_id"]
                    r = requests.post(
                        f"{supa.SUPABASE_URL}/rest/v1/ememento?on_conflict=session_id",
                        headers=HEADERS_UPSERT, json=data, timeout=5,
                    )
                    ok = r.status_code in (200, 201, 409)
                elif kind == "session_update":
                    data = {
                        "session_id": p["session_id"],
                        "code": p["code"],
                        "bar": p.get("bar") or "inconnu",
                        "timestamp": p["timestamp"],
                        "photos": json.dumps(p.get("photos") or []),
                        "originals": json.dumps(p.get("originals") or []),
                        "statut": "en_attente",
                    }
                    if p.get("borne_id"):
                        data["borne_id"] = p["borne_id"]
                    r = requests.post(
                        f"{supa.SUPABASE_URL}/rest/v1/ememento?on_conflict=session_id",
                        headers=HEADERS_UPSERT, json=data, timeout=5,
                    )
                    ok = r.status_code in (200, 201, 409)
                else:
                    ok = True  # kind inconnu = on droppe
            except Exception:
                ok = False
            if not ok:
                entry["retry_count"] = entry.get("retry_count", 0) + 1
                restants.append(entry)
            else:
                try:
                    import activity_logger as alog
                    alog.log_generic("PENDING", f"Replay OK {kind} session={p.get('session_id', '?')[:12]}")
                except Exception:
                    pass
        if len(restants) != len(items):
            pending_queue.replace_all(restants)

    def tick(self):
        try:
            from . import code_pool
            code_pool.pending_link_flush()
        except Exception as e:
            print(f"[EMMENTO] pending_link_flush erreur: {e}")
        self._replay_pending()
        self._process_rescans()

        if not os.path.exists(DSLRBOOTH_LOG):
            return

        try:
            taille = os.path.getsize(DSLRBOOTH_LOG)
            # Rotation détectée — on relit mais on ignore les lignes anciennes
            if taille < self._position:
                self._position = 0
                self._rotation = True
            else:
                self._rotation = False

            with open(DSLRBOOTH_LOG, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(self._position)
                for ligne in f:
                    self._traiter_ligne(ligne)
                self._position = f.tell()
        except Exception as e:
            print(f"[EMMENTO] Erreur lecture log: {e}")

    def _traiter_ligne(self, ligne):
        # Ignorer les lignes antérieures au démarrage (protection rotation log)
        try:
            ts_str = ligne[:23].strip()  # "2026-04-07 15:16:10.188"
            if ts_str and len(ts_str) >= 19:
                ts_ligne = datetime.strptime(ts_str[:19], "%Y-%m-%d %H:%M:%S")
                if ts_ligne < self._start_time:
                    return
        except (ValueError, IndexError):
            pass

        # Nouvelle session (ignorer si même session_id)
        m = RE_SESSION.search(ligne)
        if m:
            nouveau_id = m.group(1)
            if nouveau_id == self._etat.get("session_id"):
                return
            bar = self._default_bar()
            timestamp = datetime.now().astimezone().isoformat()
            code = _reserver_code(self._borne_id, nouveau_id, bar, timestamp)
            self._etat = {
                "session_id": nouveau_id,
                "code": code,
                "photos": [],
                "originals": [],
                "bar": bar,
                "timestamp": timestamp,
            }
            print(f"[EMMENTO] Nouvelle session: {nouveau_id} → code: {code}")
            import activity_logger as alog
            alog.log_session(nouveau_id, code, "")
            alog.ui_log(f"Nouvelle session — code {code}")
            _generer_image_code(code)
            return

        # Print détecté — essayer ancien format puis nouveau
        chemin = None
        m = RE_PRINT_OLD.search(ligne)
        if m:
            chemin = m.group(2).strip()
        else:
            m = RE_PRINT_NEW.search(ligne)
            if m:
                chemin = m.group(1).strip()

        if not chemin:
            return

        # Pas de session en cours → ignorer
        if not self._etat.get("session_id"):
            return

        # Photo déjà détectée → ignorer (doublon ancien/nouveau format)
        if chemin in self._etat.get("photos", []):
            return

        self._etat["photos"].append(chemin)
        # On override le bar UNIQUEMENT si le parsing du path a reussi.
        # Sinon on garde le default (nom_lieu via _default_bar) pose au
        # session start — evite de polluer la row avec "C:" ou autre
        # artefact de parsing quand le path ne matche pas DSLRBOOTH_BASE.
        parsed_bar = _get_bar_from_path(chemin)
        if parsed_bar:
            self._etat["bar"] = parsed_bar
        self._etat["originals"] = _trouver_originals(
            self._etat["bar"], time.time()
        )

        # Logger chaque fichier
        import activity_logger as alog
        fname = os.path.basename(chemin)
        try:
            fsize = os.path.getsize(chemin)
        except Exception:
            fsize = 0
        alog.log_print(fname, fsize, self._etat["session_id"], self._etat["bar"])
        alog.ui_log(f"Print: {fname}")

        for orig in self._etat["originals"]:
            ofname = os.path.basename(orig)
            try:
                osize = os.path.getsize(orig)
            except Exception:
                osize = 0
            alog.log_original(ofname, osize, orig)
            alog.ui_log(f"Original: {ofname}")

        _envoyer_supabase(
            session_id=self._etat["session_id"],
            bar=self._etat["bar"],
            timestamp=self._etat["timestamp"],
            photos=self._etat["photos"],
            code=self._etat["code"],
            originals=self._etat["originals"],
            borne_id=self._borne_id,
        )

        # Programmer un re-scan des Originals pour rattraper les fichiers
        # movés en retard par dslrbooth. Si un nouveau print arrive avant
        # que le rescan ne fire, on ECRASE l'entree existante avec le nouvel
        # etat + nouvelle deadline (donc rescan = 30s apres le DERNIER print
        # de la session, pas du premier).
        self._pending_rescans[self._etat["session_id"]] = {
            "bar": self._etat["bar"],
            "print_ts": time.time(),
            "code": self._etat["code"],
            "timestamp": self._etat["timestamp"],
            "photos": list(self._etat["photos"]),
            "originals_envoyes": list(self._etat["originals"]),
            "deadline": time.time() + RESCAN_DELAY_SEC,
        }

    def _process_rescans(self):
        """Traite les re-scans en attente : nettoie les expirés (TTL),
        et pour chaque deadline atteinte, re-liste <bar>\\Originals\\ pour
        detecter les fichiers movés en retard. UPDATE Supabase si de
        nouveaux originals sont apparus."""
        now = time.time()

        # Garde-fou : nettoyer les rescans coinces depuis trop longtemps
        # (theoriquement impossible, mais evite une fuite memoire silencieuse
        # si une exception non-attrapée tuait le rescan a mi-parcours).
        stale_ids = [
            sid for sid, r in self._pending_rescans.items()
            if now - r["deadline"] > RESCAN_TTL_SEC
        ]
        for sid in stale_ids:
            self._pending_rescans.pop(sid, None)
            print(f"[EMMENTO] Rescan {sid} expire (>{RESCAN_TTL_SEC}s), abandon")

        # Traiter les rescans dont le deadline est atteint
        ready_ids = [
            sid for sid, r in self._pending_rescans.items()
            if r["deadline"] <= now
        ]
        for sid in ready_ids:
            r = self._pending_rescans.pop(sid)
            try:
                new_originals = _trouver_originals(
                    r["bar"], r["print_ts"], timestamp_max=now,
                )
                envoyes = set(r["originals_envoyes"])
                trouves = set(new_originals)
                ajoutes = trouves - envoyes
                if not ajoutes:
                    continue  # rien de neuf, pas de update inutile

                _envoyer_supabase(
                    session_id=sid,
                    bar=r["bar"],
                    timestamp=r["timestamp"],
                    photos=r["photos"],
                    code=r["code"],
                    originals=sorted(new_originals, key=lambda p: os.path.getmtime(p)),
                    borne_id=self._borne_id,
                )
                print(
                    f"[EMMENTO] Rescan {sid}: +{len(ajoutes)} originals "
                    f"(total {len(new_originals)})"
                )
                import activity_logger as alog
                alog.log_generic(
                    "EMMENTO",
                    f"Rescan {r['code']}: +{len(ajoutes)} originals "
                    f"rattrapes (total {len(new_originals)})",
                )
                alog.ui_log(f"Rescan {r['code']}: +{len(ajoutes)} originals rattrapes")
            except Exception as e:
                print(f"[EMMENTO] Erreur rescan {sid}: {e}")

    def _confirmer_impression(self):
        """Marque la transaction la plus ancienne non-confirmee (FIFO).

        order=asc : un signal d'impression correspond a la session qui vient
        de finir = la PLUS ANCIENNE pending. Avec desc, plusieurs paiements
        rapproches voyaient leur signal mal attribue (cf. fix similaire dans
        cashinterface.py)."""
        if not self._borne_id:
            return
        try:
            # Trouver la plus ancienne transaction sans impression confirmee
            r = requests.get(
                f"{supa.SUPABASE_URL}/rest/v1/transactions"
                f"?borne_id=eq.{self._borne_id}"
                f"&impression_declenchee=eq.false"
                f"&order=paiement_at.asc&limit=1&select=id,paiement_at",
                headers=supa.HEADERS, timeout=5,
            )
            if r.status_code == 200 and r.json():
                tx_id = r.json()[0]["id"]
                # Vérifier que la transaction est récente (< 5 min)
                from datetime import timezone
                tx_time = r.json()[0].get("paiement_at", "")
                if tx_time:
                    tx_dt = datetime.fromisoformat(tx_time.replace("+00:00", "+00:00"))
                    now_utc = datetime.now(timezone.utc)
                    ecart = abs((now_utc - tx_dt).total_seconds())
                    if ecart > 300:  # > 5 min = trop vieux
                        return

                requests.patch(
                    f"{supa.SUPABASE_URL}/rest/v1/transactions?id=eq.{tx_id}",
                    headers=supa.HEADERS_MINIMAL,
                    json={"impression_declenchee": True},
                    timeout=5,
                )
                import activity_logger as alog
                alog.log_tpe_confirmation(tx_id)
                print(f"[EMMENTO] Impression confirmée: {tx_id[:8]}")
        except Exception as e:
            print(f"[EMMENTO] Erreur confirmation impression: {e}")
