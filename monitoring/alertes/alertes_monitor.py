"""Détection d'alertes — remplace twilio_1.0.0.pyw.
Vérifie les données collectées et crée/résout des alertes dans Supabase.
Inclut les 6 types manquants : camera, borne_hors_ligne, crash_dslrbooth,
disque_bas, disque_plein, crash_relance."""

from datetime import datetime, time as dtime
import requests
import supabase_client as supa

# Callbacks
_on_alerte_changed = None
_on_alerte_critique = None  # Appelé avec (True/False) quand une alerte critique apparaît/disparaît

def set_on_alerte_changed(callback):
    global _on_alerte_changed
    _on_alerte_changed = callback

def set_on_alerte_critique(callback):
    global _on_alerte_critique
    _on_alerte_critique = callback
from .constants import (
    ALERTES_CRITIQUES, ALERTES_WARNING, CODES_NORMAUX,
    SEUIL_ERREUR_MECANIQUE, SEUIL_PAPIER_BAS,
    SEUIL_DISQUE_BAS, SEUIL_DISQUE_PLEIN,
    TOUS_TYPES_ALERTES,
)


_horaires_cache = None


def set_horaires_cache(horaires_data):
    """Met à jour le cache horaires depuis l'app (quand on modifie dans Paramètres)."""
    global _horaires_cache
    _horaires_cache = horaires_data


def _est_dans_horaires(borne_id):
    """Vérifie si on est dans les horaires d'ouverture du bar.
    Charge une seule fois depuis Supabase au démarrage. Après, c'est l'app qui met à jour."""
    global _horaires_cache
    if _horaires_cache is None:
        _horaires_cache = supa.get_horaires(borne_id)

    try:
        horaires = _horaires_cache
        if not horaires:
            return True  # Pas d'horaires → toujours actif

        now = datetime.now()
        jour = now.weekday()  # 0=lundi, 6=dimanche

        # Trouver l'horaire du jour
        for h in horaires:
            if h.get("jour") == jour:
                if h.get("ferme"):
                    return False  # Bar fermé aujourd'hui

                ouverture = h.get("ouverture", "")
                fermeture = h.get("fermeture", "")
                if not ouverture or not fermeture:
                    return True

                # Parser HH:MM
                oh, om = int(ouverture[:2]), int(ouverture[3:5])
                fh, fm = int(fermeture[:2]), int(fermeture[3:5])

                t_now = now.hour * 60 + now.minute
                t_open = oh * 60 + om
                t_close = fh * 60 + fm

                # Cas normal : 17:00 - 23:00
                if t_close > t_open:
                    return t_open <= t_now <= t_close

                # Cas nuit : 17:00 - 02:00 (fermeture le lendemain)
                # On est dans les horaires si: après ouverture OU avant fermeture
                return t_now >= t_open or t_now <= t_close

        return True  # Jour pas trouvé → actif par défaut

    except Exception:
        return True  # En cas d'erreur → actif par défaut


# Cache local des alertes ouvertes — évite les GET à chaque cycle
_alertes_ouvertes = set()
_alertes_cache_loaded = False

# Compteur de confirmation pour "imprimante deconnectee" : nombre de heartbeats
# consecutifs ou GetStatus a retourne 0x80000000 (ou statut texte "deconnectee").
# Une seule lecture isolee a 0x80000000 (= imprimante busy, conflit DLL avec le
# printer_counter qui poll aussi, ou USB transient) creait jusqu'a present une
# alerte critique + SMS, auto-resolue ~75s plus tard au heartbeat suivant.
# Pattern observe : 10 fausses alertes de 70-96s sur 4 jours en juin 2026.
# Maintenant on attend N ticks confirmes avant de creer l'alerte.
_imprimante_disconnect_ticks = 0
IMPRIMANTE_DECONNECT_CONFIRMATION_TICKS = 2

# Meme pattern pour camera_deconnectee : appareil_connecte=False sur une seule
# lecture isolee (USB transient, lecture WIA ratee) declenchait l'alerte +
# SMS. Constate sur MB-18 et MB-29 le 19/06 a ~5h d'intervalle.
_camera_disconnect_ticks = 0
CAMERA_DECONNECT_CONFIRMATION_TICKS = 2

# Snooze de la page rupture : timestamp Unix jusqu'auquel elle ne se re-affiche
# pas, meme si une alerte critique reste ouverte. Set par snooze_rupture() quand
# le tech valide le PIN. 0 = pas en snooze. NE PERSISTE PAS au reboot (in-memory),
# de sorte qu'un reboot reaffiche immediatement la rupture.
_rupture_snoozed_until = 0.0
RUPTURE_SNOOZE_SEC = 300  # 5 minutes


def _charger_cache_alertes(borne_id):
    """Charge les alertes ouvertes depuis Supabase une seule fois au démarrage.

    Si des alertes visuellement critiques sont encore ouvertes en base, on
    reaffiche IMMEDIATEMENT la page rupture (sans nouveau SMS — on rappelle
    juste le callback Qt visuel, pas _creer_alerte). Cela couvre le cas
    'reboot agent alors qu'une alerte critique etait en cours'.

    Bug v1.0.24.8 et avant : `_alertes_cache_loaded = True` etait set meme
    si la requete Supabase echouait (reseau pas pret au boot Windows).
    Cache vide pour toute la session -> resolutions ulterieures skipees
    -> alertes restees ouvertes indefiniment. Fix : on ne marque le cache
    comme charge que si la requete reussit, sinon on retentera."""
    global _alertes_ouvertes, _alertes_cache_loaded
    if _alertes_cache_loaded:
        return
    try:
        r = requests.get(
            f"{supa.SUPABASE_URL}/rest/v1/alertes"
            f"?borne_id=eq.{borne_id}&statut=eq.ouverte&select=type",
            headers=supa.HEADERS, timeout=10,
        )
        if r.status_code == 200:
            _alertes_ouvertes = {a["type"] for a in r.json()}
            print(f"  [CACHE] Alertes ouvertes: {_alertes_ouvertes}")
            # Re-affichage immediat de la rupture au reboot si critiques en cours.
            critiques = _alertes_ouvertes - _TYPES_WARNING_VISUEL
            if critiques and _on_alerte_critique:
                _on_alerte_critique(True)
                print(f"  [CACHE] Re-affichage rupture au boot (critiques: {critiques})")
            _alertes_cache_loaded = True
        else:
            print(f"  [CACHE] Echec chargement (status {r.status_code}), retry au prochain tick")
    except Exception as e:
        print(f"  [CACHE] Echec chargement ({type(e).__name__}), retry au prochain tick")


def snooze_rupture(seconds=RUPTURE_SNOOZE_SEC):
    """Cache la page rupture pour `seconds` (defaut RUPTURE_SNOOZE_SEC = 5 min).

    Appele par rupture_screen.py quand le tech valide le PIN. NE TOUCHE PAS
    a l'alerte en base ni au cache _alertes_ouvertes — la page reviendra
    automatiquement quand le snooze expire SI l'alerte est toujours ouverte
    (check_rupture_resume), et reste cachee si l'agent a entre-temps detecte
    que la cause physique a disparu (= _resoudre_alertes appele)."""
    global _rupture_snoozed_until
    import time as _t
    _rupture_snoozed_until = _t.time() + seconds
    print(f"  [RUPTURE] Snoozee pour {seconds}s par validation PIN")


def check_rupture_resume():
    """Appele tous les ~60s par engine.py. Si le snooze a expire ET qu'il
    reste au moins une alerte critique en cache, on rappelle le callback
    pour re-afficher la rupture. Aucun SMS n'est envoye (pas d'INSERT
    Supabase, juste l'affichage visuel)."""
    import time as _t
    if _t.time() < _rupture_snoozed_until:
        return  # encore en snooze
    critiques = _alertes_ouvertes - _TYPES_WARNING_VISUEL
    if critiques and _on_alerte_critique:
        _on_alerte_critique(True)


def _alerte_deja_ouverte(borne_id, type_alerte):
    """Vérifie si une alerte est déjà ouverte — cache local, pas de requête Supabase."""
    _charger_cache_alertes(borne_id)
    return type_alerte in _alertes_ouvertes


# Types visuellement "warning" : affichés en orange, PAS de page rupture
# Mais envoyés comme "critique" à Supabase pour déclencher le SMS
_TYPES_WARNING_VISUEL = {"surchauffe", "papier_bas", "disque_bas", "coupe_incoherente", "crash_relance", "borne_hors_ligne", "impression_non_delivree", "drive_deconnecte", "drive_sync_cassee", "borne_eteinte_3_jours"}

# Types envoyés à Supabase en gravité "warning" au lieu de "critique" :
# affichés sur le dashboard mais NE DECLENCHENT PAS le SMS. Les alertes
# Drive sont majoritairement de faux positifs / hiccups transitoires qui
# se resolvent d'eux-memes -> pas de valeur ajoutee d'alerter par SMS.
_TYPES_NO_SMS = {"drive_deconnecte", "drive_sync_cassee"}


def _creer_alerte(borne_id, type_alerte, source, message, gravite="critique"):
    try:
        # Gravité visuelle (orange ou rouge sur l'UI)
        gravite_visuelle = "warning" if type_alerte in _TYPES_WARNING_VISUEL else "critique"

        # 1. D'ABORD mettre à jour l'app (cache + UI + écran rupture)
        _alertes_ouvertes.add(type_alerte)
        print(f"  [ALERTE] {type_alerte} créée — visuel={gravite_visuelle}, supabase=critique")

        import activity_logger as alog
        icon_map = {
            "capot_ouvert": "alert_capot_ouvert.svg",
            "bourrage_papier": "alert_bourrage_papier.svg",
            "fin_papier": "alert_fin_de_papier.svg",
            "fin_ruban": "alert_fin_de_papier.svg",
            "erreur_ruban": "alert_erreur_ruban.svg",
            "erreur_donnees": "alert_erreur_donnees.svg",
            "bac_chutes_plein": "alert_disque_plein_new.svg",
            "erreur_mecanique": "alert_erreur_mecanique.svg",
            "crash_dslrbooth": "alert_crash_dslrbooth.svg",
            "crash_cashinterface": "alert_crash_dslrbooth.svg",
            "imprimante_deconnectee": "alert_erreur_mecanique.svg",
            "camera_deconnectee": "icon_camera_deconnectee.svg",
            "borne_hors_ligne": "icon_borne_hors_ligne.svg",
            "surchauffe": "icon_surchauffe.svg",
            "papier_bas": "icon_papier_bas.svg",
            "disque_bas": "icon_disque_bas.svg",
            "disque_plein": "alert_disque_plein_new.svg",
            "coupe_incoherente": "icon_coupe_incoherente.svg",
        }
        alog.log_alerte_creee(type_alerte, gravite_visuelle, source, message, borne_id)
        alog.ui_alerte(f"{message}", icon_map.get(type_alerte, "icon_borne_hors_ligne.svg"), resolved=False)

        if _on_alerte_changed:
            _on_alerte_changed()
        # Page rupture uniquement pour les alertes visuellement critiques (rouges)
        if gravite_visuelle == "critique" and _on_alerte_critique:
            _on_alerte_critique(True)

        # 2. ENSUITE envoyer à Supabase — gravité "warning" pour les types
        # qui ne doivent pas déclencher de SMS (drive_*), "critique" sinon.
        gravite_supabase = "warning" if type_alerte in _TYPES_NO_SMS else "critique"
        payload = {
            "borne_id": borne_id,
            "type": type_alerte,
            "source": source,
            "message": message,
            "gravite": gravite_supabase,
            "statut": "ouverte",
            "timestamp": datetime.now().astimezone().isoformat(),
        }
        r = requests.post(
            f"{supa.SUPABASE_URL}/rest/v1/alertes",
            headers=supa.HEADERS_MINIMAL,
            json=payload,
            timeout=10,
        )
        if r.status_code not in (200, 201):
            print(f"  [ALERTE] ERREUR Supabase {type_alerte}: {r.status_code}")
        return True
    except Exception as e:
        print(f"  [ALERTE] EXCEPTION création {type_alerte}: {e}")
        return False


def _resoudre_alertes(borne_id, types):
    """Resout une alerte si elle est ouverte en cache OU en base.

    Bug v1.0.24.8 et avant : `if t not in _alertes_ouvertes: continue` skipait
    le PATCH Supabase si le cache local etait desynchronise (= cache vide
    car _charger_cache_alertes avait echoue au boot, ou crash de l'agent
    entre creation et resolution). Resultat : alerte fantome en base meme
    apres que la condition ait disparu - page rupture maintenue.

    Fix : on tente TOUJOURS le PATCH Supabase. Le GET initial est de toute
    facon necessaire pour avoir l'ID. Si rien en base -> on skip silencieusement
    (cas nominal ou il n'y a vraiment rien a resoudre)."""
    for t in types:
        was_in_cache = t in _alertes_ouvertes
        try:
            # 1. Mettre a jour le cache local et l'UI (si l'alerte etait connue)
            if was_in_cache:
                _alertes_ouvertes.discard(t)
                print(f"  [RÉSOLU] {t}")
                import activity_logger as alog
                from alertes.data import TYPE_LABELS, TYPE_TO_ICON
                label = TYPE_LABELS.get(t, t)
                icon = TYPE_TO_ICON.get(t, "icon_borne_hors_ligne.svg")
                alog.log_alerte_resolue(t, "agent-auto")
                alog.ui_alerte(f"{label} — Résolu par Agent", icon, resolved=True)

                if _on_alerte_changed:
                    _on_alerte_changed()
                # Cacher la page rupture s'il ne reste plus d'alertes visuellement critiques
                alertes_critiques_restantes = _alertes_ouvertes - _TYPES_WARNING_VISUEL
                if _on_alerte_critique and not alertes_critiques_restantes:
                    _on_alerte_critique(False)

            # 2. TOUJOURS chercher en base pour rattraper les alertes orphelines
            #    (cache desynchro, alerte creee par un agent precedent, etc.)
            r = requests.get(
                f"{supa.SUPABASE_URL}/rest/v1/alertes"
                f"?borne_id=eq.{borne_id}&type=eq.{t}&statut=eq.ouverte&select=id",
                headers=supa.HEADERS, timeout=10,
            )
            if r.status_code == 200 and r.json():
                alerte_id = r.json()[0]["id"]
                requests.patch(
                    f"{supa.SUPABASE_URL}/rest/v1/alertes?id=eq.{alerte_id}",
                    headers=supa.HEADERS_MINIMAL,
                    json={
                        "statut": "resolue",
                        "resolue_par": "agent-auto",
                        "resolue_at": datetime.now().astimezone().isoformat(),
                    },
                    timeout=10,
                )
        except Exception as e:
            print(f"  [RÉSOLU] ERREUR {t}: {e}")


def verifier_alertes(borne_id, nom_lieu, donnees):
    """Vérifie toutes les données collectées et crée/résout les alertes.

    donnees = dict avec les clés du heartbeat :
        imprimante_statut_code, feuilles_restantes, appareil_connecte,
        dslrbooth_running, disque_libre_go, ssid_wifi
    """
    status = donnees.get("imprimante_statut_code")
    feuilles = donnees.get("feuilles_restantes")
    bar = nom_lieu or "la borne"
    print(f"  [ALERTES] status=0x{status:X}, feuilles={feuilles}" if status else f"  [ALERTES] status=None, feuilles={feuilles}")

    # Si le bar est fermé → aucune alerte (tout est éteint, c'est normal)
    if not _est_dans_horaires(borne_id):
        return

    # ══════════════════════════════════════════════
    # 0. IMPRIMANTE DÉCONNECTÉE
    # ══════════════════════════════════════════════

    global _imprimante_disconnect_ticks
    imprimante_statut = donnees.get("imprimante_statut") or ""
    deconnecte = (
        status == 0x80000000
        or imprimante_statut in ("Imprimante déconnectée", "Imprimante non trouvée", "DLL introuvable")
    )
    # status=None et statut="" ou None : lecture pas encore faite ou DLL en hang.
    # On NE declenche PAS d'alerte dans ce cas (eviterait les fausses alertes).
    # On ne touche PAS au compteur non plus (pas d'info -> on suspend le decompte).
    statut_lisible = status is not None and bool(imprimante_statut)

    if deconnecte:
        _imprimante_disconnect_ticks += 1
        # Une seule lecture deconnectee = transient (DLL busy, conflit avec
        # printer_counter, USB glitch). On exige IMPRIMANTE_DECONNECT_CONFIRMATION_TICKS
        # heartbeats consecutifs pour creer l'alerte (= ~2 minutes de vraie deconnexion).
        if _imprimante_disconnect_ticks >= IMPRIMANTE_DECONNECT_CONFIRMATION_TICKS:
            if not _alerte_deja_ouverte(borne_id, "imprimante_deconnectee"):
                _creer_alerte(borne_id, "imprimante_deconnectee", "imprimante",
                              f"Imprimante déconnectée sur {bar}.", "critique")
        else:
            print(f"  [ALERTES] imprimante deconnectee tick {_imprimante_disconnect_ticks}/{IMPRIMANTE_DECONNECT_CONFIRMATION_TICKS} (transient, pas d'alerte)")
    elif statut_lisible:
        # Statut clairement OK : reset compteur + resout d'eventuelles alertes ouvertes
        _imprimante_disconnect_ticks = 0
        _resoudre_alertes(borne_id, ["imprimante_deconnectee"])

    # ══════════════════════════════════════════════
    # 1. ALERTES IMPRIMANTE (codes DNP)
    # ══════════════════════════════════════════════

    if status and status in ALERTES_CRITIQUES:
        info = ALERTES_CRITIQUES[status]
        if not _alerte_deja_ouverte(borne_id, info["type"]):
            _creer_alerte(borne_id, info["type"], "imprimante",
                          f"{info['message']} ({bar})", "critique")

    elif status and status >= SEUIL_ERREUR_MECANIQUE and status != 0x80000000:
        if not _alerte_deja_ouverte(borne_id, "erreur_mecanique"):
            _creer_alerte(borne_id, "erreur_mecanique", "imprimante",
                          f"Erreur mécanique sur {bar}. SAV nécessaire.", "critique")

    elif status and status in ALERTES_WARNING:
        info = ALERTES_WARNING[status]
        if not _alerte_deja_ouverte(borne_id, info["type"]):
            _creer_alerte(borne_id, info["type"], "imprimante",
                          f"{info['message']} ({bar})", "warning")

    # Statut normal → résoudre les alertes imprimante
    if status and status in CODES_NORMAUX:
        _resoudre_alertes(borne_id, [
            "bourrage_papier", "fin_papier", "fin_ruban", "erreur_ruban",
            "capot_ouvert", "bac_chutes_plein", "erreur_mecanique", "erreur_donnees",
            "surchauffe",
        ])

    # ══════════════════════════════════════════════
    # 2. PAPIER BAS (< 50 feuilles)
    # ══════════════════════════════════════════════

    if feuilles is not None and 0 < feuilles < SEUIL_PAPIER_BAS:
        if not _alerte_deja_ouverte(borne_id, "papier_bas"):
            _creer_alerte(borne_id, "papier_bas", "imprimante",
                          f"Papier bas sur {bar}. Moins de {SEUIL_PAPIER_BAS} feuilles.", "warning")
    elif feuilles is not None and feuilles >= SEUIL_PAPIER_BAS:
        _resoudre_alertes(borne_id, ["papier_bas"])

    # ══════════════════════════════════════════════
    # 3. CAMÉRA DÉCONNECTÉE
    # ══════════════════════════════════════════════

    global _camera_disconnect_ticks
    appareil = donnees.get("appareil_connecte", False)
    if not appareil:
        _camera_disconnect_ticks += 1
        # Meme garde-fou que imprimante_deconnectee : on exige
        # CAMERA_DECONNECT_CONFIRMATION_TICKS heartbeats consecutifs avant alerte.
        if _camera_disconnect_ticks >= CAMERA_DECONNECT_CONFIRMATION_TICKS:
            if not _alerte_deja_ouverte(borne_id, "camera_deconnectee"):
                _creer_alerte(borne_id, "camera_deconnectee", "camera",
                              f"Caméra déconnectée sur {bar}. Vérifier le câble USB.", "critique")
        else:
            print(f"  [ALERTES] camera deconnectee tick {_camera_disconnect_ticks}/{CAMERA_DECONNECT_CONFIRMATION_TICKS} (transient, pas d'alerte)")
    else:
        _camera_disconnect_ticks = 0
        _resoudre_alertes(borne_id, ["camera_deconnectee"])

    # ══════════════════════════════════════════════
    # 4. CRASH DSLRBOOTH
    # ══════════════════════════════════════════════

    dslrbooth = donnees.get("dslrbooth_running", False)
    if not dslrbooth:
        if not _alerte_deja_ouverte(borne_id, "crash_dslrbooth"):
            _creer_alerte(borne_id, "crash_dslrbooth", "dslrbooth",
                          f"DSLRBOOTH ne tourne pas sur {bar}.", "critique")
    else:
        _resoudre_alertes(borne_id, ["crash_dslrbooth"])

    # ══════════════════════════════════════════════
    # 5. CRASH CASH INTERFACE
    # ══════════════════════════════════════════════

    cash_running = donnees.get("cash_interface_running", False)
    if not cash_running:
        if not _alerte_deja_ouverte(borne_id, "crash_cashinterface"):
            _creer_alerte(borne_id, "crash_cashinterface", "cashinterface",
                          f"Cash Interface ne tourne pas sur {bar}.", "critique")
    else:
        _resoudre_alertes(borne_id, ["crash_cashinterface"])

    # ══════════════════════════════════════════════
    # 6. DISQUE BAS / PLEIN
    # ══════════════════════════════════════════════

    disque = donnees.get("disque_libre_go")
    if disque is not None:
        if disque < SEUIL_DISQUE_PLEIN:
            if not _alerte_deja_ouverte(borne_id, "disque_plein"):
                _creer_alerte(borne_id, "disque_plein", "système",
                              f"Disque plein sur {bar}. Moins de {SEUIL_DISQUE_PLEIN} Go.", "critique")
        elif disque < SEUIL_DISQUE_BAS:
            _resoudre_alertes(borne_id, ["disque_plein"])
            if not _alerte_deja_ouverte(borne_id, "disque_bas"):
                _creer_alerte(borne_id, "disque_bas", "système",
                              f"Disque bas sur {bar}. Moins de {SEUIL_DISQUE_BAS} Go.", "warning")
        else:
            _resoudre_alertes(borne_id, ["disque_plein", "disque_bas"])

    # ══════════════════════════════════════════════
    # 6. BORNE HORS LIGNE (pas de WiFi)
    # ══════════════════════════════════════════════

    wifi = donnees.get("ssid_wifi")
    if not wifi:
        if not _alerte_deja_ouverte(borne_id, "borne_hors_ligne"):
            _creer_alerte(borne_id, "borne_hors_ligne", "réseau",
                          f"Borne hors ligne sur {bar}. Pas de connexion réseau.", "critique")
    else:
        _resoudre_alertes(borne_id, ["borne_hors_ligne"])

    # ══════════════════════════════════════════════
    # 8. COUPE 2 POUCES — vérifier que le mode est cohérent
    # ══════════════════════════════════════════════

    mode_coupe = donnees.get("mode_coupe")
    if mode_coupe == "Coupe désactivée":
        if not _alerte_deja_ouverte(borne_id, "coupe_incoherente"):
            nom_imp = donnees.get("nom_imprimante") or "imprimante"
            _creer_alerte(borne_id, "coupe_incoherente", "imprimante",
                          f"Coupe 2 pouces désactivée sur {nom_imp} ({bar}).", "warning")
    elif mode_coupe == "Coupe activée":
        _resoudre_alertes(borne_id, ["coupe_incoherente"])
