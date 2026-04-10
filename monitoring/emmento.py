"""E-memento Watcher — intégré dans MementoAgent.
Surveille le log dslrBooth, génère des codes courts uniques (7 chars),
envoie les sessions dans la table 'ememento' de Supabase.
Codes expirés après 2 mois."""

import os
import re
import json
import time
import random
import string
from datetime import datetime

import requests
import supabase_client as supa

# Caractères sans ambiguïté (pas de 0/O, 1/I/L)
CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 7

# Fenêtre de temps (en secondes) pour chercher les Originals
ORIGINALS_TIME_WINDOW = 60

DSLRBOOTH_LOG = os.path.join(
    os.environ.get("APPDATA", ""), "dslrBooth", "Logs", "dslrbooth.log"
)
DSLRBOOTH_CONFIG = os.path.join(
    os.environ.get("APPDATA", ""), "dslrBooth", "app_settings_2021.json"
)
DSLRBOOTH_DB = os.path.join(
    os.environ.get("APPDATA", ""), "dslrBooth", "database_2025.db"
)
DSLRBOOTH_BASE = r"C:\dslrBooth"
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


def _generer_code_unique(borne_id):
    """Génère un code court de 7 caractères, vérifie l'unicité dans Supabase."""
    for _ in range(10):  # 10 tentatives max
        code = "".join(random.choices(CODE_CHARS, k=CODE_LENGTH))
        try:
            r = requests.get(
                f"{supa.SUPABASE_URL}/rest/v1/ememento"
                f"?code=eq.{code}&select=id&limit=1",
                headers=supa.HEADERS, timeout=10,
            )
            if r.status_code == 200 and not r.json():
                return code  # Code unique trouvé
        except Exception:
            pass
    # Fallback : code aléatoire (probabilité collision ~0 avec 7 chars)
    return "".join(random.choices(CODE_CHARS, k=CODE_LENGTH))


def _expirer_anciens_codes():
    """Marque les codes de plus de 2 mois comme expirés."""
    try:
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=60)).isoformat()
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
    try:
        relatif = chemin.replace(DSLRBOOTH_BASE + "\\", "")
        return relatif.split("\\")[0]
    except Exception:
        return "inconnu"


def _trouver_originals(bar, timestamp_print):
    originals_dir = os.path.join(DSLRBOOTH_BASE, bar, "Originals")
    if not os.path.exists(originals_dir):
        return []
    originals = []
    try:
        window_start = timestamp_print - ORIGINALS_TIME_WINDOW
        for f in os.listdir(originals_dir):
            if not f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp")):
                continue
            chemin = os.path.join(originals_dir, f)
            mtime = os.path.getmtime(chemin)
            if window_start <= mtime <= timestamp_print:
                originals.append(chemin)
    except Exception:
        pass
    originals.sort(key=lambda f: os.path.getmtime(f))
    return originals


def _envoyer_supabase(session_id, bar, timestamp, photos, code, originals, borne_id):
    """Envoie dans la table ememento (UPSERT sur session_id)."""
    data = {
        "session_id": session_id,
        "code": code,
        "bar": bar,
        "timestamp": timestamp,
        "photos": json.dumps(photos),
        "originals": json.dumps(originals or []),
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
                print(f"[EMMENTO] Session {session_id} | code {code} | {len(photos)} prints | OK")
                import activity_logger as alog
                alog.log_supabase_ok(session_id, code, len(photos), len(originals or []))
                alog.ui_log(f"Code {code} envoyé dans Supabase")
                return True
            else:
                print(f"[EMMENTO] Erreur HTTP {r.status_code}: {r.text[:100]}")
                import activity_logger as alog
                alog.log_supabase_error(session_id, code, f"HTTP {r.status_code}")
        except Exception as e:
            print(f"[EMMENTO] Erreur envoi: {e}")
            import activity_logger as alog
            alog.log_supabase_error(session_id, code, str(e))
        time.sleep(2)

    print(f"[EMMENTO] Abandon session {session_id} après 3 tentatives")
    return False


class EmentoWatcher:
    """Watcher e-memento — tourne dans le thread de monitoring."""

    def __init__(self, borne_id):
        self._borne_id = borne_id
        self._start_time = datetime.now()
        self._etat = {
            "session_id": None,
            "code": "",
            "photos": [],
            "originals": [],
            "bar": "inconnu",
            "timestamp": None,
        }
        # Démarrer à la fin du fichier — ne traiter que les NOUVELLES lignes
        self._position = 0
        try:
            if os.path.exists(DSLRBOOTH_LOG):
                self._position = os.path.getsize(DSLRBOOTH_LOG)
        except Exception:
            pass

    def tick(self):
        """Appelé à chaque cycle du monitoring (~3s).
        Lit les nouvelles lignes du log dslrBooth."""
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
                return  # Même session, ignorer le doublon
            code = _generer_code_unique(self._borne_id)
            self._etat = {
                "session_id": nouveau_id,
                "code": code,
                "photos": [],
                "originals": [],
                "bar": "inconnu",
                "timestamp": datetime.now().isoformat(),
            }
            print(f"[EMMENTO] Nouvelle session: {nouveau_id} → code: {code}")
            import activity_logger as alog
            alog.log_session(nouveau_id, code, "")
            alog.ui_log(f"Nouvelle session — code {code}")
            _generer_image_code(code)
            # Envoyer immédiatement dans Supabase (sans photos, sera mis à jour au Print)
            _envoyer_supabase(
                session_id=nouveau_id,
                bar="inconnu",
                timestamp=self._etat["timestamp"],
                photos=[],
                code=code,
                originals=[],
                borne_id=self._borne_id,
            )
            return

        # Print détecté — ancien format (avec session_id)
        m = RE_PRINT_OLD.search(ligne)
        if m:
            session_id = m.group(1)
            chemin = m.group(2).strip()
            if self._etat.get("session_id") != session_id:
                code = _generer_code_unique(self._borne_id)
                self._etat = {
                    "session_id": session_id,
                    "code": code,
                    "photos": [],
                    "originals": [],
                    "timestamp": datetime.now().isoformat(),
                }
                _generer_image_code(code)
                # Envoyer immédiatement dans Supabase
                _envoyer_supabase(
                    session_id=session_id,
                    bar="inconnu",
                    timestamp=self._etat["timestamp"],
                    photos=[],
                    code=code,
                    originals=[],
                    borne_id=self._borne_id,
                )
        else:
            # Print détecté — nouveau format (sans session_id)
            m = RE_PRINT_NEW.search(ligne)
            if m:
                chemin = m.group(1).strip()
                session_id = self._etat.get("session_id")
                if not session_id:
                    return  # Pas de session en cours

        if m:
            # Ignorer si cette photo est déjà détectée (doublon ancien/nouveau format)
            if chemin in self._etat.get("photos", []):
                return

            self._etat["photos"].append(chemin)
            self._etat["bar"] = _get_bar_from_path(chemin)
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
            alog.log_print(fname, fsize, session_id, self._etat["bar"])
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
                session_id=session_id,
                bar=self._etat["bar"],
                timestamp=self._etat["timestamp"],
                photos=self._etat["photos"],
                code=self._etat["code"],
                originals=self._etat["originals"],
                borne_id=self._borne_id,
            )

    def _confirmer_impression(self):
        """Marque la dernière transaction non-confirmée comme imprimée dans Supabase."""
        if not self._borne_id:
            return
        try:
            # Trouver la dernière transaction sans impression confirmée
            r = requests.get(
                f"{supa.SUPABASE_URL}/rest/v1/transactions"
                f"?borne_id=eq.{self._borne_id}"
                f"&impression_declenchee=eq.false"
                f"&order=paiement_at.desc&limit=1&select=id,paiement_at",
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
