"""Bundle de certificats TLS persistant.

PROBLEME (diagnostique Le confess 13/11/2026)
----------------------------------------------
PyInstaller onefile extrait certifi/cacert.pem dans %TEMP%\\_MEIxxxxx\\.
Ce dossier est supprime par :
  - le watchdog (_MEI cleanup, ajoute en v1.0.28.14 pour les 730 Go accumules)
  - le Nettoyage de disque Windows
  - certains antivirus / outils de nettoyage

Quand le dossier disparait pendant que l'agent tourne, requests leve :
  OSError: Could not find a suitable TLS CA certificate bundle, invalid path:
  C:\\...\\Temp\\_MEI118242\\certifi\\cacert.pem

Consequence : PLUS AUCUN HTTPS ne marche. Heartbeat, verifier_pin (= PIN
admin refuse alors que le code est bon), PATCH transactions, alertes :
tout echoue silencieusement jusqu'au prochain restart de l'agent.

FIX
---
Au boot, on copie le bundle dans %LOCALAPPDATA%\\MementoAgent\\cacert.pem
(dossier persistant, jamais nettoye) et on pointe SSL_CERT_FILE +
REQUESTS_CA_BUNDLE dessus. L'agent devient immunise contre la suppression
du _MEI, quelle qu'en soit la cause.
"""

import os
import shutil


def _persistent_dir():
    d = os.path.join(
        os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "MementoAgent"
    )
    os.makedirs(d, exist_ok=True)
    return d


def install_persistent_ca_bundle():
    """Copie cacert.pem dans un dossier persistant et pointe requests dessus.

    Retourne le chemin utilise, ou None si on n'a pas pu (on laisse alors
    le comportement par defaut de requests/certifi)."""
    dest = os.path.join(_persistent_dir(), "cacert.pem")

    src = None
    try:
        import certifi
        src = certifi.where()
    except Exception:
        src = None

    # Copie si la source existe et que la destination est absente ou differente.
    # On compare la taille : suffisant pour detecter une MAJ du bundle entre
    # deux versions de l'agent, sans relire 200 Ko a chaque boot.
    try:
        if src and os.path.exists(src):
            need_copy = True
            if os.path.exists(dest):
                try:
                    need_copy = os.path.getsize(dest) != os.path.getsize(src)
                except OSError:
                    need_copy = True
            if need_copy:
                shutil.copy2(src, dest)
    except Exception:
        pass

    # Meme si la copie a echoue, un bundle d'un boot precedent peut etre la :
    # c'est exactement le cas qu'on veut couvrir (le _MEI a disparu, donc src
    # est injoignable, mais dest survit).
    if os.path.exists(dest):
        os.environ["SSL_CERT_FILE"] = dest
        os.environ["REQUESTS_CA_BUNDLE"] = dest
        return dest
    return None
