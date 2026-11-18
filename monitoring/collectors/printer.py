"""Lecture imprimante DNP via la DLL de statut correspondant au modele.

  DS620 series  -> Cx2Stat64.dll (DNP Status Monitor API)
  DS-RX1 series -> CyStat64.dll  (Printer Status API) depuis v1.0.28.30

Les autres modeles DNP (DS820, DS40, DS80, QW410) n'ont pas de DLL fournie :
ils restent remontes en "En veille" sans statut ni compteur.

Fonctionne uniquement sur Windows."""

import platform
from ..alertes.constants import (
    BASE_PRINTER_NAME, STATUS_MAP, is_dnp_printer,
    get_media_capacity, get_printer_dll, KAPSULE_PORT_ALLOWED_DLLS,
    dll_probe_rank, STATUS_CODES_TRUSTED_DLLS, ecarter_ports_ambigus,
)
from ..dnp_lock import DNP_PORT_LOCK
from ..dnp_dll import load_dll, call_optional, read_media_counter


def _log(msg):
    """Trace dans alertes.log. Les print() sont perdus en prod (fenetre
    cachee) : ce qui sert au diagnostic a distance passe par ici."""
    print(f"[PRINTER] {msg}")
    try:
        import activity_logger as alog
        alog.log_generic("PRINTER", msg)
    except Exception:
        pass


# Ne journaliser "modele X via DLL Y" qu'au changement, pas a chaque heartbeat.
_last_logged_choice = None


def lire_imprimante():
    """Lit le statut, feuilles restantes, serial et mode coupe de l'imprimante."""
    result = {
        "nom_imprimante": None,
        "serial_imprimante": None,
        "imprimante_statut": None,
        "imprimante_statut_code": None,
        "feuilles_restantes": None,
        "ruban_restant": None,  # compteur ruban (ribbon) DNP, separe du papier
        "mode_coupe": None,
        "capacite_imprimante": 400,  # default DS620, override selon modele detecte
        # DLL effectivement utilisee pour lire cette imprimante. Consomme par
        # alertes_monitor, retire du payload heartbeat (pas de colonne).
        "imprimante_dll": None,
    }

    if platform.system() != "Windows":
        result["imprimante_statut"] = "Non disponible (pas Windows)"
        return result

    try:
        import ctypes
        import winreg
        from ..photo_app import is_kapsule_borne

        # Modeles ouvrables sur borne Kapsule : cf. KAPSULE_PORT_ALLOWED_DLLS,
        # qui contient DS620 ET RX1 depuis v1.0.28.30. Evalue une fois, pas a
        # chaque imprimante du registre.
        kapsule_borne = is_kapsule_borne()

        # Trouver l'imprimante dans le registre
        reg = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Print\Printers"
        printer_name = None
        printer_port = None

        # Trouver TOUTES les imprimantes DNP (DS620, DS-RX1, DS820, DS40, DS80, QW410...).
        # On filtre d'abord sur is_dnp_printer, puis get_printer_dll() associe a
        # chacune la DLL qui sait la lire. Utiliser la mauvaise DLL segfault le
        # process (observe sur DS-RX1 avec Cx2Stat64, v1.0.28.9) : un modele sans
        # DLL connue part en fallback degrade plutot que d'etre interroge.
        all_printers = []       # (nom, port, dll_name) : lisibles via une DLL
        other_dnp_name = None   # Autre modele DNP present, remonte en degraded sans DLL
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg) as key:
            for i in range(100):
                # EnumKey leve OSError quand i depasse le nombre de clefs -> break
                # legitime (fin de l'enumeration). Mais si un OSError arrive PLUS
                # LOIN (sur OpenKey/QueryValueEx d'une imprimante particuliere a la
                # structure registre atypique, ex: "Microsoft Print to PDF"), on
                # DOIT juste skipper cette entree et continuer — pas abandonner
                # tout le scan. Sinon la vraie DNP enumeree APRES l'imprimante
                # fautive n'est jamais trouvee (observe Les Follies 06/11 :
                # DP-DS620 presente et fonctionnelle, mais agent remontait en
                # permanence "Imprimante non trouvee").
                try:
                    name = winreg.EnumKey(key, i)
                except OSError:
                    break
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, f"{reg}\\{name}") as pk:
                        port, _ = winreg.QueryValueEx(pk, "Port")
                        try:
                            driver, _ = winreg.QueryValueEx(pk, "Printer Driver")
                        except OSError:
                            driver = ""
                    # Robustesse : certains utilisateurs renomment l'imprimante
                    # (ex "DS-RX1" tout court, sans prefixe DP-). On regarde
                    # DONC le nom affiche ET le "Printer Driver" du registre
                    # (reste toujours "DP-DS620", "DP-DS-RX1", etc. meme apres renommage).
                    if not (is_dnp_printer(name) or is_dnp_printer(driver)):
                        continue
                    # v1.0.28.30 : chaque modele a sa DLL. Le driver du
                    # registre prime sur le nom affiche (editable par
                    # l'operateur) ; identification contradictoire -> None.
                    dll_name = get_printer_dll(name, driver)
                    # Sur borne Kapsule, on n'ouvre que les modeles listes
                    # dans KAPSULE_PORT_ALLOWED_DLLS. ATTENTION en lisant ce
                    # code : depuis v1.0.28.30 cette liste contient DS620 ET
                    # RX1, donc ce filtre ne retire plus rien en pratique. Il
                    # reste ici pour le jour ou un modele devra en etre exclu
                    # — c'est le seul endroit a modifier pour couper l'acces
                    # au port d'un modele sur les bornes Kapsule.
                    # La justification du cas RX1 est dans constants.py
                    # (Kapsule n'embarque que Cx2Stat64, il ne tient donc pas
                    # ce port et ne publie jamais son compteur).
                    if dll_name and kapsule_borne and dll_name not in KAPSULE_PORT_ALLOWED_DLLS:
                        dll_name = None
                    if dll_name:
                        all_printers.append((name, port, dll_name))
                    elif other_dnp_name is None:
                        other_dnp_name = name
                except OSError:
                    continue

        # Tri DETERMINISTE : Cx2Stat64 (DS620) d'abord — cf. dll_probe_rank —
        # puis le nom le plus court (donc "DP-DS620" avant "DP-DS620 (Copie 1)"),
        # puis ordre alphabetique. Sans ce tri, winreg.EnumKey retourne les
        # clefs dans un ordre non stable et quand Windows a plusieurs entrees
        # pour la meme imprimante physique (observe prod O divin Bethune 30/10),
        # on choisissait tantot l'une tantot l'autre -> compteur et status
        # aleatoires.
        all_printers.sort(key=lambda x: (dll_probe_rank(x[2]), len(x[0]), x[0]))

        # Deux entrees sur le meme port mais de familles differentes = on ne
        # sait pas ce qui est branche. On ne sonde ce port avec aucune des
        # deux plutot que de parier (cf. ecarter_ports_ambigus).
        all_printers, ports_ecartes = ecarter_ports_ambigus(all_printers)
        if ports_ecartes:
            _log(f"ports ambigus ecartes (deux familles DNP declarees): {sorted(ports_ecartes)}")

        def _fallback_other_dnp():
            """Remonte une DNP sans DLL de statut connue (DS820, DS40, DS80,
            QW410) en 'En veille'. On ne touche PAS a la DLL : utiliser la
            mauvaise segfault le process. Code status normal (0x10001) pour
            que le dashboard l'affiche OK sans declencher d'alerte deconnexion.

            Depuis v1.0.28.30 les DS-RX1 ne passent plus ici : elles ont leur
            propre DLL (CyStat64) et suivent le meme chemin que les DS620."""
            result["nom_imprimante"] = other_dnp_name
            result["imprimante_statut"] = "En veille"
            result["imprimante_statut_code"] = 0x10001
            result["capacite_imprimante"] = get_media_capacity(other_dnp_name)
            try:
                from monitoring.coupe_2pouces.coupe import est_coupe_active
                result["mode_coupe"] = "Coupe activée" if est_coupe_active() else "Coupe désactivée"
            except Exception:
                pass

        if not all_printers:
            if other_dnp_name:
                _fallback_other_dnp()
                return result
            result["imprimante_statut"] = "Imprimante non trouvée"
            return result

        # Tout ce qui touche a la DLL DNP passe par DNP_PORT_LOCK pour ne pas
        # entrer en conflit avec le PrinterCounterWatcher (qui poll toutes
        # les 3s). Sans ce lock : le collecteur echoue PortInitialize quand
        # le port est deja pris -> fausse alerte 'Imprimante deconnectee'.
        with DNP_PORT_LOCK:
            # Tester chaque port — prendre celle qui répond (pas 0x80000000).
            # v1.0.28.30 : chaque imprimante est interrogee avec SA DLL.
            h_port = -1
            dll = None
            chosen_dll_name = None
            any_dll_loaded = False
            for name, port, dll_name in all_printers:
                candidate_dll = load_dll(dll_name)
                if candidate_dll is None:
                    # load_dll journalise deja la raison dans alertes.log.
                    continue
                any_dll_loaded = True
                try:
                    candidate_dll.PortInitialize.argtypes = [ctypes.c_wchar_p]
                    candidate_dll.PortInitialize.restype = ctypes.c_int
                    h = candidate_dll.PortInitialize(port)
                except Exception as e:
                    _log(f"PortInitialize {name} ({dll_name}, {port}) a leve: {e}")
                    continue
                if h >= 0:
                    try:
                        candidate_dll.GetStatus.argtypes = [ctypes.c_int]
                        candidate_dll.GetStatus.restype = ctypes.c_uint
                        st = candidate_dll.GetStatus(h)
                    except Exception as e:
                        _log(f"GetStatus {name} ({dll_name}) a leve: {e}")
                        continue
                    if st != 0x80000000:
                        # Cette imprimante répond
                        printer_name = name
                        printer_port = port
                        h_port = h
                        dll = candidate_dll
                        chosen_dll_name = dll_name
                        global _last_logged_choice
                        choice = (name, dll_name)
                        if choice != _last_logged_choice:
                            _log(f"DNP {name} lue via {dll_name} (port {port})")
                            _last_logged_choice = choice
                        break
                    # Sinon essayer la suivante

            # ORDRE IMPORTANT : ce bloc passe AVANT "DLL introuvable".
            #
            # Echec de lecture sur un modele dont le chemin n'a pas encore
            # tourne en production (RX1 via CyStat64), quelle que soit la
            # cause : DLL qui ne charge pas (CyStat64 a besoin de CSJCYLM.DLL,
            # deposee par le pilote DP-DS-RX1 — reinstallation du pilote,
            # antivirus, extraction _MEI incomplete), ou port qui ne repond
            # pas. Avant v1.0.28.30, une RX1 tombait toujours en repli
            # silencieux et ne pouvait declencher AUCUNE alerte. Un chemin
            # neuf ne doit pas pouvoir faire pire que ce qu'il remplace :
            # "DLL introuvable" comme "Imprimante deconnectee" sont dans la
            # liste de alertes_monitor qui mene a l'alerte critique + SMS +
            # ecran de rupture plein ecran, et qui ne se resout jamais tant
            # que la cause dure.
            #
            # On publie donc un statut HONNETE qui ne declenche rien et ne
            # resout rien : absent de la liste "deconnecte", et sans code
            # numerique, donc statut_lisible reste faux cote alertes_monitor.
            # Surtout pas "En veille"/0x10001, qui ferait croire a une
            # imprimante saine et resoudrait a tort les alertes ouvertes.
            # A retirer quand les codes RX1 auront ete observes en production.
            if h_port < 0 and all(
                d not in STATUS_CODES_TRUSTED_DLLS for _, _, d in all_printers
            ):
                fallback_name = all_printers[0][0]
                _log(
                    f"lecture {fallback_name} impossible "
                    f"(dll_chargee={any_dll_loaded}) -> statut non concluant"
                )
                result["nom_imprimante"] = fallback_name
                result["capacite_imprimante"] = get_media_capacity(fallback_name)
                result["imprimante_statut"] = "Lecture impossible"
                return result

            # AUCUNE DLL n'a pu etre chargee : on ne sait rien de cette
            # imprimante. Avant v1.0.28.30, ce cas etait detecte en amont et
            # remontait "DLL introuvable". Il ne doit surtout pas tomber dans
            # le repli _fallback_other_dnp() ci-dessous, qui publie le code
            # 0x10001 "En veille" : alertes_monitor traite ce code comme sain,
            # resout l'alerte imprimante_deconnectee, et l'agent se declare
            # donc en bonne sante alors qu'il ne lit plus rien.
            if h_port < 0 and not any_dll_loaded:
                fallback_name = all_printers[0][0]
                _log(f"aucune DLL chargeable pour {fallback_name} -> DLL introuvable")
                result["nom_imprimante"] = fallback_name
                result["capacite_imprimante"] = get_media_capacity(fallback_name)
                result["imprimante_statut"] = "DLL introuvable"
                return result

            # Si TOUTES les imprimantes avec DLL sont fantomes (0x80000000) et
            # qu'une autre DNP sans DLL est detectee (DS820 branchee a la place
            # sur un autre USB), c'est elle la vraie imprimante. On la remonte
            # en degraded plutot que faux "Erreur generale" / deconnectee.
            if h_port < 0 and other_dnp_name:
                _fallback_other_dnp()
                return result

            # Si aucune n'a répondu et pas d'alternative, prendre la première quand même
            if h_port < 0:
                printer_name, printer_port, first_dll_name = all_printers[0]
                dll = load_dll(first_dll_name)
                chosen_dll_name = first_dll_name
                if dll is None:
                    result["nom_imprimante"] = printer_name
                    result["capacite_imprimante"] = get_media_capacity(printer_name)
                    result["imprimante_statut"] = "DLL introuvable"
                    return result
                try:
                    dll.PortInitialize.argtypes = [ctypes.c_wchar_p]
                    dll.PortInitialize.restype = ctypes.c_int
                    h_port = dll.PortInitialize(printer_port)
                except Exception:
                    h_port = -1

            result["nom_imprimante"] = printer_name
            result["capacite_imprimante"] = get_media_capacity(printer_name)

            if h_port < 0:
                result["imprimante_statut"] = "Imprimante déconnectée"
                return result

            # Statut
            dll.GetStatus.argtypes = [ctypes.c_int]
            dll.GetStatus.restype = ctypes.c_uint
            status = dll.GetStatus(h_port)
            result["imprimante_statut_code"] = status
            result["imprimante_statut"] = STATUS_MAP.get(status, f"Inconnu (0x{status:X})")
            # Transmis a alertes_monitor (puis retire du payload heartbeat) :
            # les codes d'un modele non encore valide en production ne doivent
            # pas passer dans le fourre-tout "erreur mecanique".
            result["imprimante_dll"] = chosen_dll_name
            # La trace du code brut (pour constituer la table des codes
            # reels de ce modele) est ecrite par alertes_monitor, qui la
            # deduplique sur la valeur du code. La refaire ici ajouterait
            # ~1 400 lignes par jour pour un code qui ne change jamais, et
            # noierait justement celui qu'on attend : celui d'une vraie panne.

            # Feuilles restantes. La fonction a appeler depend du modele :
            # GetMediaCounter sur DS620, GetMediaCounter_R sur RX1 (cf.
            # MEDIA_COUNTER_FUNC dans dnp_dll.py). Appeler la mauvaise sur une
            # RX1 publie 50 feuilles de trop.
            feuilles = read_media_counter(dll, chosen_dll_name, h_port)
            result["feuilles_restantes"] = (
                feuilles if feuilles is not None and feuilles >= 0 else None
            )

            # Ruban restant (ribbon counter DNP) — tente plusieurs symboles
            # possibles de la DLL Cx2Stat64 selon version du SDK. Fallback
            # sur le code status : 0x10010 = "Fin de ruban" -> 0.
            ribbon = None
            for sym in ("GetRibbonCounter", "GetRibbonRemain", "GetMediaRibbonCounter"):
                fn = getattr(dll, sym, None)
                if fn is None:
                    continue
                try:
                    fn.argtypes = [ctypes.c_int]
                    fn.restype = ctypes.c_int
                    val = fn(h_port)
                    if val >= 0:
                        ribbon = val
                        break
                except Exception:
                    continue
            if ribbon is None and status == 0x10010:
                # Pas de fonction SDK dispo mais status dit "Fin de ruban".
                ribbon = 0
            result["ruban_restant"] = ribbon

            # Serial
            try:
                buf = ctypes.create_string_buffer(256)
                dll.GetSerialNo.argtypes = [ctypes.c_int, ctypes.c_char_p]
                dll.GetSerialNo.restype = ctypes.c_int
                if dll.GetSerialNo(h_port, buf) >= 0:
                    serial = buf.value.decode("ascii", errors="ignore").strip()
                    if serial:
                        result["serial_imprimante"] = serial
            except Exception:
                pass

            # Liberer. PortRelease n'existe dans AUCUNE des deux DLL (verifie
            # avec pefile le 18/11/2026 : absent de Cx2Stat64 comme de
            # CyStat64). L'appel historique levait donc un AttributeError
            # avale silencieusement. On passe par call_optional pour que ce
            # soit explicite : si DNP ajoute la fonction un jour, elle sera
            # utilisee, sinon on ne fait rien.
            call_optional(dll, "PortRelease", h_port)

        # Mode coupe — lire le flag fichier (pas le registre HKLM qui ne reflète pas la clé utilisateur)
        # (hors lock : ne touche pas a la DLL DNP)
        from monitoring.coupe_2pouces.coupe import est_coupe_active
        result["mode_coupe"] = "Coupe activée" if est_coupe_active() else "Coupe désactivée"

    except Exception as e:
        result["imprimante_statut"] = f"Erreur: {e}"

    return result
