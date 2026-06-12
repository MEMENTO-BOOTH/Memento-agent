"""SettingsWidget — assembleur principal de la page Paramètres.
Charge les données depuis Supabase + config locale, branche les actions."""

import os
import sys
import re
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea
)
from PyQt5.QtCore import Qt

from dashboard import T, DARK_THEME, LIME_GREEN, TEXT_BLACK
import supabase_client as supa

from .config import load as load_config, save as save_config
from .worker import ApiWorker
from .widgets import section_title, label, separator
from .overlays import PinOverlay, HorairesOverlay, PaletteOverlay, AnimationOverlay
from .sections import (
    build_borne_section,
    build_imprimante_section,
    build_emmento_section,
    build_horaires_section,
    build_systeme_section,
    build_notifications_section,
    build_apparence_section,
    build_mise_a_jour_section,
    build_animation_section,
    build_led_section,
)
from overlay import config as overlay_cfg
from overlay.presets import get as get_preset


class SettingsWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers = []
        self._borne_id = None
        self._build()
        self._fetch_borne()

    def _run(self, func, on_done, *args):
        """Lance un ApiWorker, connecte le callback, garde la ref."""
        # Nettoyer les workers terminés
        self._workers = [w for w in self._workers if w.isRunning()]
        w = ApiWorker(func, *args)
        w.finished.connect(on_done)
        w.error.connect(lambda e: print(f"[SETTINGS] Erreur: {e}"))
        self._workers.append(w)
        w.start()

    # ═══════════════════════════════════════════════
    #  BUILD UI
    # ═══════════════════════════════════════════════

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        from touch_scroll import enable_touch_scroll
        enable_touch_scroll(scroll)
        bg = T()["content_bg"]
        handle = T()["scroll_handle"]
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: {bg}; }}
            QScrollBar:vertical {{ width: 6px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {handle}; border-radius: 3px; min-height: 30px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        inner = QWidget()
        inner.setStyleSheet(f"background: {bg};")
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(28, 20, 28, 28)
        vl.setSpacing(16)

        # Titre
        title = QLabel("Paramètres")
        title.setStyleSheet(f"color: {T()['text']}; font-family: 'Inter'; font-size: 22px; font-weight: 700; background: transparent;")
        vl.addWidget(title)
        vl.addSpacing(4)

        # ── BORNE ──
        t, c, refs = build_borne_section()
        self._ref_borne = refs
        self._ref_borne["btn_photo"].clicked.connect(self._change_photo)
        vl.addWidget(t)
        vl.addWidget(c)

        # ── IMPRIMANTE ──
        t, c, refs = build_imprimante_section()
        self._ref_imp = refs
        self._ref_imp["toggle_coupe"].mousePressEvent_orig = self._ref_imp["toggle_coupe"].mousePressEvent
        self._ref_imp["toggle_coupe"].mousePressEvent = self._on_toggle_coupe
        vl.addWidget(t)
        vl.addWidget(c)

        # ── CODE E-MEMENTO ──
        t, c, refs = build_emmento_section()
        self._ref_emmento = refs
        vl.addWidget(t)
        vl.addWidget(c)

        # ── PALETTE D'ERREURS ──
        from .widgets import SectionCard, lime_btn
        vl.addWidget(section_title("PALETTE D'ERREURS"))
        palette_card = SectionCard()
        pc_layout = QHBoxLayout(palette_card)
        pc_layout.setContentsMargins(20, 16, 20, 16)
        pc_layout.addWidget(label("Types d'erreurs et criticité", bold=True))
        pc_layout.addStretch()
        btn_palette = lime_btn("Configurer")
        btn_palette.clicked.connect(self._show_palette_overlay)
        pc_layout.addWidget(btn_palette)
        vl.addWidget(palette_card)

        # ── HORAIRES ──
        t, c, refs = build_horaires_section()
        self._ref_hor = refs
        self._ref_hor["btn_modifier"].clicked.connect(self._show_horaires_overlay)
        vl.addWidget(t)
        vl.addWidget(c)

        # ── SYSTÈME ──
        t, c, refs = build_systeme_section()
        self._ref_sys = refs
        self._ref_sys["toggle_maint"].mousePressEvent_orig = self._ref_sys["toggle_maint"].mousePressEvent
        self._ref_sys["toggle_maint"].mousePressEvent = self._on_toggle_maintenance
        vl.addWidget(t)
        vl.addWidget(c)

        # ── NOTIFICATIONS ──
        header_layout, card, refs = build_notifications_section()
        self._ref_notif = refs
        self._ref_notif["btn_add"].clicked.connect(self._add_contact)
        self._ref_notif["btn_save"].clicked.connect(self._save_contacts)
        vl.addLayout(header_layout)
        vl.addWidget(card)
        vl.addLayout(self._ref_notif["save_row"])

        # ── APPARENCE ──
        cfg = load_config()
        theme_idx = 1 if cfg.get("theme") == "dark" else 0
        lang_idx = 1 if cfg.get("langue") == "en" else 0
        t, c, refs = build_apparence_section(theme_idx, lang_idx)
        self._ref_app = refs
        self._ref_app["combo_theme"].currentIndexChanged.connect(self._on_theme_changed)
        self._ref_app["combo_lang"].currentIndexChanged.connect(self._on_lang_changed)
        vl.addWidget(t)
        vl.addWidget(c)

        # ── ANIMATION IMPRESSION ──
        t, c, refs = build_animation_section()
        self._ref_anim = refs
        self._ref_anim["toggle"].mousePressEvent_orig = self._ref_anim["toggle"].mousePressEvent
        self._ref_anim["toggle"].mousePressEvent = self._on_toggle_animation
        self._ref_anim["btn_config"].clicked.connect(self._show_animation_overlay)
        vl.addWidget(t)
        vl.addWidget(c)

        # ── ÉCLAIRAGE (Pico LED) ──
        t, c, refs = build_led_section()
        self._ref_led = refs
        self._ref_led["toggle_enabled"].mousePressEvent_orig = self._ref_led["toggle_enabled"].mousePressEvent
        self._ref_led["toggle_enabled"].mousePressEvent = self._on_led_toggle
        self._ref_led["slider_normal"].valueChanged.connect(self._on_led_normal_changed)
        self._ref_led["slider_normal"].sliderReleased.connect(self._on_led_normal_released)
        self._ref_led["slider_boost"].valueChanged.connect(self._on_led_boost_changed)
        self._ref_led["slider_boost"].sliderReleased.connect(self._on_led_boost_released)
        self._ref_led["btn_test"].clicked.connect(self._on_led_test)
        self._wire_led_watcher()
        vl.addWidget(t)
        vl.addWidget(c)

        # ── MISE À JOUR ──
        t, c, refs = build_mise_a_jour_section()
        self._ref_maj = refs
        self._ref_maj["btn_check"].clicked.connect(self._check_update)
        self._ref_maj["btn_install"].clicked.connect(self._install_update)
        self._latest_update = None
        vl.addWidget(t)
        vl.addWidget(c)

        vl.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)

    # ═══════════════════════════════════════════════
    #  CHARGEMENT CONFIG LOCALE
    # ═══════════════════════════════════════════════

    # ═══════════════════════════════════════════════
    #  FETCH SUPABASE — cascade: borne → heartbeat, horaires, updates
    # ═══════════════════════════════════════════════

    def _fetch_borne(self):
        self._run(supa.get_borne, self._on_borne_loaded)

    def _on_borne_loaded(self, data):
        if not data:
            self._ref_borne["lbl_nom"].setText("Hors ligne")
            self._ref_borne["avatar"].set_nom("Hors ligne")
            return
        self._borne_id = data["id"]
        nom = data.get("nom_lieu") or "—"
        self._ref_borne["lbl_nom"].setText(nom)
        self._ref_borne["lbl_ville"].setText(data.get("ville") or "—")
        self._ref_borne["lbl_code"].setText(data.get("code") or "—")
        self._ref_borne["lbl_sub"].setText(data.get("code", ""))

        # Avatar : initiales du nom du lieu
        self._ref_borne["avatar"].set_nom(nom)

        # Charger le logo : partenaire → bornes.logo_url → local
        pid = data.get("partenaire_id")
        if pid:
            self._run(self._fetch_logo, self._on_logo_loaded, pid)
        elif data.get("logo_url"):
            self._run(self._fetch_logo_from_url, self._on_logo_loaded, data["logo_url"])
        else:
            self._load_local_logo()

        # Maintenance toggle
        is_maint = data.get("statut") == "maintenance"
        self._ref_sys["toggle_maint"].set_on(is_maint)

        # Cascade
        self._fetch_heartbeat()
        self._fetch_horaires()
        self._fetch_updates()
        self._fetch_contacts()

    @staticmethod
    def _fetch_logo(partenaire_id):
        """Récupère l'URL du logo depuis la table partenaires."""
        import requests
        try:
            r = requests.get(
                f"{supa.SUPABASE_URL}/rest/v1/partenaires?id=eq.{partenaire_id}&select=logo_url",
                headers=supa.HEADERS, timeout=10,
            )
            if r.status_code == 200 and r.json():
                url = r.json()[0].get("logo_url")
                if url:
                    img = requests.get(url, timeout=10)
                    if img.status_code == 200:
                        return img.content
        except Exception:
            pass
        return None

    @staticmethod
    def _fetch_logo_from_url(url):
        """Récupère le logo directement depuis une URL (fallback sans partenaire)."""
        import requests
        try:
            img = requests.get(url, timeout=10)
            if img.status_code == 200:
                return img.content
        except Exception:
            pass
        return None

    def _load_local_logo(self):
        """Charge le logo depuis le fichier local s'il existe."""
        from PyQt5.QtGui import QPixmap
        local_dir = os.path.join(os.path.expanduser("~"), ".mementoagent")
        for ext in ("png", "jpg", "jpeg", "svg"):
            p = os.path.join(local_dir, f"logo.{ext}")
            if os.path.exists(p):
                pm = QPixmap(p)
                if not pm.isNull():
                    self._ref_borne["avatar"].set_logo(pm)
                return

    def _on_logo_loaded(self, img_bytes):
        if img_bytes:
            from PyQt5.QtGui import QPixmap
            pm = QPixmap()
            pm.loadFromData(img_bytes)
            if not pm.isNull():
                self._ref_borne["avatar"].set_logo(pm)

    def _fetch_heartbeat(self):
        self._run(supa.get_heartbeat, self._on_heartbeat_loaded, self._borne_id)

    def _on_heartbeat_loaded(self, data):
        if not data:
            return
        # Recuperer le nom de l'imprimante en arriere-plan (peut hanger sur DLL DNP)
        self._ref_imp["lbl_nom"].setText("—")
        from monitoring.collectors.heartbeat import _lire_imprimante_safe
        self._run(_lire_imprimante_safe, self._on_imprimante_loaded)
        self._ref_imp["lbl_serial"].setText(data.get("serial_imprimante") or "—")
        self._ref_imp["lbl_statut"].setText(data.get("imprimante_statut") or "—")
        coupe_on = data.get("mode_coupe") == "Coupe activée"
        self._ref_imp["toggle_coupe"].set_on(coupe_on)

    def _on_imprimante_loaded(self, imp):
        if not imp:
            return
        self._ref_imp["lbl_nom"].setText(imp.get("nom_imprimante") or "—")

        # Version agent — toujours afficher la version locale
        from version import VERSION
        self._ref_maj["lbl_version"].setText(f"Version actuelle : v{VERSION}")

    def _fetch_horaires(self):
        self._run(supa.get_horaires, self._on_horaires_loaded, self._borne_id)

    def _on_horaires_loaded(self, data):
        if not data:
            return
        jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        new_data = []
        for row in sorted(data, key=lambda x: x["jour"]):
            j = row["jour"]
            if j < len(jours):
                if row.get("ferme"):
                    new_data.append((jours[j], "Fermé"))
                else:
                    o = str(row.get("ouverture", ""))[:5]
                    f = str(row.get("fermeture", ""))[:5]
                    new_data.append((jours[j], f"{o} – {f}"))

        if len(new_data) == 7:
            self._ref_hor["horaires_data"][:] = new_data
            self._refresh_horaires_labels(new_data)

    def _refresh_horaires_labels(self, data=None):
        data = data or self._ref_hor["horaires_data"]
        for i, (jour, heures) in enumerate(data):
            if i < len(self._ref_hor["horaires_labels"]):
                lbl = self._ref_hor["horaires_labels"][i]
                is_ferme = heures == "Fermé"
                color = "#888888" if is_ferme else T()["text"]
                lbl.setText(heures)
                lbl.setStyleSheet(f"color: {color}; font-family: 'Inter'; font-size: 12px; font-weight: 400; background: transparent;")

    def _fetch_updates(self):
        self._run(supa.get_latest_release, self._on_update_checked, self._borne_id)

    # ═══════════════════════════════════════════════
    #  ACTIONS — MAINTENANCE
    # ═══════════════════════════════════════════════

    def _on_toggle_coupe(self, event):
        toggle = self._ref_imp["toggle_coupe"]
        toggle.mousePressEvent_orig(event)
        activate = toggle.is_on()

        from ui_components import toast
        toast("Coupe 2 pouces en cours..." if activate else "Désactivation en cours...", "warning")
        toggle.setEnabled(False)

        def _do_coupe():
            from monitoring.coupe_2pouces import activer_coupe, desactiver_coupe
            if activate:
                activer_coupe()
            else:
                desactiver_coupe()

        def _on_done(_):
            toggle.setEnabled(True)
            from ui_components import toast as _toast
            if activate:
                _toast("Coupe 2 pouces activée", "success")
            else:
                _toast("Coupe 2 pouces désactivée")
            # Heartbeat + alertes
            if self._borne_id:
                mode = "Coupe activée" if activate else "Coupe désactivée"
                self._run(
                    supa.supabase_patch_heartbeat, lambda ok: None,
                    self._borne_id, {"mode_coupe": mode},
                )
                from monitoring.alertes.alertes_monitor import _resoudre_alertes, _creer_alerte, _alerte_deja_ouverte
                if activate:
                    _resoudre_alertes(self._borne_id, ["coupe_incoherente"])
                else:
                    if not _alerte_deja_ouverte(self._borne_id, "coupe_incoherente"):
                        nom_imp = self._ref_imp["lbl_nom"].text() or "imprimante"
                        _creer_alerte(self._borne_id, "coupe_incoherente", "imprimante",
                                      f"Coupe 2 pouces désactivée sur {nom_imp}.", "warning")

        self._run(_do_coupe, _on_done)

    def _on_toggle_maintenance(self, event):
        toggle = self._ref_sys["toggle_maint"]
        toggle.mousePressEvent_orig(event)
        is_maint = toggle.is_on()

        # 1. Mettre à jour dans Supabase
        if self._borne_id:
            new_statut = "maintenance" if is_maint else "active"
            self._run(supa.patch_borne, lambda ok: None, self._borne_id, {"statut": new_statut})

        # 2. Dire au moteur de monitoring de suspendre les alertes
        dashboard = self.window()
        if hasattr(dashboard, '_monitor'):
            dashboard._monitor.set_maintenance(is_maint)

        from ui_components import toast
        toast("Mode maintenance " + ("activé" if is_maint else "désactivé"), "warning" if is_maint else "success")

    # ═══════════════════════════════════════════════
    #  ACTIONS — HORAIRES
    # ═══════════════════════════════════════════════

    def _show_horaires_overlay(self):
        main_win = self.window()
        if hasattr(self, '_hor_overlay') and self._hor_overlay:
            self._hor_overlay.deleteLater()
        self._hor_overlay = HorairesOverlay(self._ref_hor["horaires_data"], main_win)
        self._hor_overlay.set_on_confirm(self._update_horaires)
        self._hor_overlay.setGeometry(main_win.rect())
        self._hor_overlay.raise_()
        self._hor_overlay.show()

    def _update_horaires(self, new_data):
        self._ref_hor["horaires_data"][:] = new_data
        self._refresh_horaires_labels(new_data)

        # Sauvegarder dans Supabase
        if self._borne_id:
            rows = []
            for i, (jour, heures) in enumerate(new_data):
                ferme = heures == "Fermé"
                ouverture, fermeture = "00:00", "00:00"
                if not ferme and " – " in heures:
                    parts = heures.split(" – ")
                    ouverture, fermeture = parts[0].strip(), parts[1].strip()
                rows.append({
                    "jour": i,
                    "ouverture": ouverture,
                    "fermeture": fermeture,
                    "ferme": ferme,
                })
            print(f"[SETTINGS] Saving horaires for borne {self._borne_id}: {rows}")
            # Mettre à jour le cache local immédiatement
            from monitoring.alertes.alertes_monitor import set_horaires_cache
            set_horaires_cache(rows)
            self._run(supa.save_horaires, self._on_horaires_saved, self._borne_id, rows)
        else:
            print("[SETTINGS] Cannot save horaires: borne_id is None")

    def _on_horaires_saved(self, ok):
        from ui_components import toast
        if ok:
            toast("Horaires enregistrés", "success")
        else:
            toast("Erreur sauvegarde horaires", "error")

    # ═══════════════════════════════════════════════
    #  ACTIONS — PIN
    # ═══════════════════════════════════════════════

    def _change_photo(self):
        """Ouvre un sélecteur de fichier pour choisir le logo du bar,
        l'upload dans Supabase Storage, et met à jour partenaires.logo_url."""
        from PyQt5.QtWidgets import QFileDialog
        from PyQt5.QtGui import QPixmap

        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir la photo du bar", "",
            "Images (*.png *.jpg *.jpeg *.svg)"
        )
        if not path:
            return

        # Sauver une copie locale persistante
        import shutil
        local_dir = os.path.join(os.path.expanduser("~"), ".mementoagent")
        os.makedirs(local_dir, exist_ok=True)
        ext = path.rsplit(".", 1)[-1].lower()
        local_logo = os.path.join(local_dir, f"logo.{ext}")
        shutil.copy2(path, local_logo)
        # Nettoyer les anciens logos d'extensions différentes
        for old_ext in ("png", "jpg", "jpeg", "svg"):
            old = os.path.join(local_dir, f"logo.{old_ext}")
            if old != local_logo and os.path.exists(old):
                os.remove(old)

        # Afficher immédiatement en local
        pm = QPixmap(path)
        if not pm.isNull():
            self._ref_borne["avatar"].set_logo(pm)

            # Aussi mettre à jour dans la sidebar du dashboard
            dashboard = self.window()
            from dashboard import ProfileCard, CollapsedProfile
            for card in dashboard.findChildren(ProfileCard):
                card._logo = pm.scaled(50, 50, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                card.update()
            for cp in dashboard.findChildren(CollapsedProfile):
                cp._logo = pm.scaled(40, 40, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                cp.update()

        from ui_components import toast
        toast("Photo du bar mise à jour", "success")

        # Upload vers Supabase Storage en arrière-plan
        if self._borne_id:
            self._run(self._upload_logo, lambda ok: None, path, self._borne_id)

    @staticmethod
    def _upload_logo(file_path, borne_id):
        """Upload le logo dans Supabase Storage et met à jour partenaires.logo_url."""
        import requests
        try:
            # Lire le fichier
            with open(file_path, "rb") as f:
                file_data = f.read()

            ext = file_path.rsplit(".", 1)[-1].lower()
            content_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "svg": "image/svg+xml"}.get(ext, "image/png")
            filename = f"logo_{borne_id}.{ext}"

            # Upload dans le bucket "logos"
            r = requests.post(
                f"{supa.SUPABASE_URL}/storage/v1/object/logos/{filename}",
                headers={
                    "apikey": supa.SUPABASE_KEY,
                    "Authorization": f"Bearer {supa.SUPABASE_KEY}",
                    "Content-Type": content_type,
                    "x-upsert": "true",
                },
                data=file_data,
                timeout=30,
            )

            if r.status_code in (200, 201):
                logo_url = f"{supa.SUPABASE_URL}/storage/v1/object/public/logos/{filename}"

                borne = supa.get_borne()
                if borne:
                    # Sauvegarder sur le partenaire si il existe
                    pid = borne.get("partenaire_id")
                    if pid:
                        requests.patch(
                            f"{supa.SUPABASE_URL}/rest/v1/partenaires?id=eq.{pid}",
                            headers=supa.HEADERS_MINIMAL,
                            json={"logo_url": logo_url},
                            timeout=10,
                        )
                    # Aussi sauvegarder directement sur la borne (fallback)
                    requests.patch(
                        f"{supa.SUPABASE_URL}/rest/v1/bornes?id=eq.{borne['id']}",
                        headers=supa.HEADERS_MINIMAL,
                        json={"logo_url": logo_url},
                        timeout=10,
                    )
                    print(f"[SETTINGS] Logo uploadé: {logo_url}")
                    return True
        except Exception as e:
            print(f"[SETTINGS] Erreur upload logo: {e}")
        return False

    def _show_palette_overlay(self):
        main_win = self.window()
        if hasattr(self, '_palette_overlay') and self._palette_overlay:
            self._palette_overlay.deleteLater()
        self._palette_overlay = PaletteOverlay(on_save=self._on_palette_saved, parent=main_win)
        self._palette_overlay.setGeometry(main_win.rect())
        self._palette_overlay.raise_()
        self._palette_overlay.show()

    def _on_palette_saved(self, data):
        """data = {"borne_hors_ligne": "critique", "camera_deconnectee": "warning", ...}"""
        # Sauvegarder dans Supabase via printer_status_config
        # Pour l'instant on print, le branchement complet se fait quand la table est prête
        print(f"[SETTINGS] Palette sauvegardée: {data}")

    # ═══════════════════════════════════════════════
    #  ACTIONS — ANIMATION IMPRESSION
    # ═══════════════════════════════════════════════

    def _on_toggle_animation(self, event):
        self._ref_anim["toggle"].mousePressEvent_orig(event)
        cfg = overlay_cfg.load()
        cfg["enabled"] = self._ref_anim["toggle"].is_on()
        overlay_cfg.save(cfg)
        self._notify_overlay_reload()

    def _show_animation_overlay(self):
        main_win = self.window()
        if hasattr(self, '_anim_overlay') and self._anim_overlay:
            self._anim_overlay.deleteLater()
        self._anim_overlay = AnimationOverlay(main_win)
        self._anim_overlay.set_on_saved(self._on_animation_saved)
        self._anim_overlay.setGeometry(main_win.rect())
        self._anim_overlay.raise_()
        self._anim_overlay.show()

    def _on_animation_saved(self, cfg):
        self._ref_anim["toggle"].set_on(bool(cfg.get("enabled")))
        self._ref_anim["lbl_style"].setText(get_preset(cfg.get("style", "memento"))["name"])
        self._ref_anim["lbl_duration"].setText(f"{cfg.get('duration', 18)}s")
        self._notify_overlay_reload()

    def _notify_overlay_reload(self):
        """Informe le PrintOverlayManager qu'il doit relire sa config."""
        try:
            from PyQt5.QtWidgets import QApplication
            mgr = getattr(QApplication.instance(), "_overlay_manager", None)
            if mgr:
                mgr.reload_config()
        except Exception:
            pass

    # ═══════════════════════════════════════════════
    #  ACTIONS — NOTIFICATIONS (table alerte_destinataires)
    # ═══════════════════════════════════════════════

    def _add_contact(self):
        self._add_contact_row("", "", removable=True)

    def _add_contact_row(self, email, tel, removable=True):
        from .sections.notifications import create_contact_row
        if self._ref_notif["contact_rows"]:
            sep = separator()
            sep.setStyleSheet(f"background-color: {T()['row_sep']}; border: none;")
            self._ref_notif["notif_layout"].addSpacing(10)
            self._ref_notif["notif_layout"].addWidget(sep)

        row = create_contact_row(email, tel, removable, on_remove=self._remove_contact)
        self._ref_notif["contact_rows"].append(row)
        self._ref_notif["notif_layout"].addWidget(row)

    def _remove_contact(self, widget):
        if widget in self._ref_notif["contact_rows"]:
            self._ref_notif["contact_rows"].remove(widget)
            self._ref_notif["notif_layout"].removeWidget(widget)
            widget.deleteLater()
        # Sauvegarder après suppression
        self._save_contacts()

    def _fetch_contacts(self):
        if self._borne_id:
            self._run(supa.get_alerte_destinataires, self._on_contacts_loaded, self._borne_id)

    def _on_contacts_loaded(self, data):
        if not data:
            return
        # Vider les contacts existants
        for w in self._ref_notif["contact_rows"][:]:
            self._ref_notif["contact_rows"].remove(w)
            self._ref_notif["notif_layout"].removeWidget(w)
            w.deleteLater()
        # Ajouter depuis Supabase
        for i, contact in enumerate(data):
            self._add_contact_row(
                contact.get("email", ""),
                contact.get("telephone", ""),
                removable=(i > 0),
            )

    def _save_contacts(self):
        """Sauvegarde tous les contacts dans alerte_destinataires."""
        if not self._borne_id:
            return
        contacts = []
        for row in self._ref_notif["contact_rows"]:
            email = row._inp_email.text().strip()
            tel = row._inp_tel.text().strip()
            if email or tel:
                contacts.append({"email": email, "telephone": tel})
        def _on_contacts_saved(ok):
            from ui_components import toast
            if ok:
                toast("Contacts mis à jour", "success")
            else:
                toast("Erreur sauvegarde contacts", "error")
        self._run(supa.save_alerte_destinataires, _on_contacts_saved, self._borne_id, contacts)

    # ═══════════════════════════════════════════════
    #  ACTIONS — MISE À JOUR
    # ═══════════════════════════════════════════════

    def _check_update(self):
        """Vérifie si une nouvelle version est disponible."""
        self._ref_maj["lbl_latest"].setText("Vérification en cours...")
        self._ref_maj["lbl_latest"].setStyleSheet(
            "color: rgba(255,255,255,0.7); font-family: 'Satoshi'; "
            "font-size: 12px; background: transparent;"
        )
        self._run(supa.get_latest_release, self._on_update_checked, self._borne_id)

    def _on_update_checked(self, data):
        from version import VERSION
        current = VERSION
        if not data:
            self._ref_maj["lbl_latest"].setText("Votre application est à jour.")
            self._ref_maj["lbl_notes"].hide()
            self._ref_maj["btn_install"].hide()
            return

        latest_version = data.get("version", "")
        # Match canal : on installe la release du canal des qu'elle differe de
        # la version installee, qu'elle soit plus recente (upgrade) ou plus
        # ancienne (downgrade voulu suite a un switch dev -> prod).
        if latest_version and latest_version != current:
            self._latest_update = data
            self._ref_maj["lbl_latest"].setText(
                f"Une nouvelle version est disponible : v{latest_version}"
            )
            self._ref_maj["lbl_latest"].setStyleSheet(
                "color: white; font-family: 'Satoshi'; "
                "font-size: 12px; background: transparent;"
            )
            notes = data.get("notes", "")
            if notes:
                self._ref_maj["lbl_notes"].setText(notes)
                self._ref_maj["lbl_notes"].show()
            self._ref_maj["btn_install"].show()
        else:
            self._ref_maj["lbl_latest"].setText("Votre application est à jour.")
            self._ref_maj["lbl_notes"].hide()
            self._ref_maj["btn_install"].hide()

    def _install_update(self):
        """Télécharge et installe la mise à jour."""
        if not self._latest_update:
            return

        self._ref_maj["btn_install"].setText("Téléchargement...")
        self._ref_maj["btn_install"].setEnabled(False)
        self._run(self._download_and_install, self._on_install_done, self._latest_update)

    @staticmethod
    def _download_and_install(update_data):
        """Télécharge le .exe depuis GitHub Releases (repo privé)."""
        import requests
        import tempfile
        import os

        url = update_data.get("download_url", "") or update_data.get("fichier_url", "")
        if not url:
            return {"ok": False, "error": "URL manquante"}

        try:
            headers = {}
            if "api.github.com" in url:
                headers = {
                    "Authorization": f"token {supa.GITHUB_TOKEN}",
                    "Accept": "application/octet-stream",
                }
            r = requests.get(url, timeout=120, stream=True, headers=headers)
            if r.status_code != 200:
                return {"ok": False, "error": f"HTTP {r.status_code}"}

            tmp = tempfile.NamedTemporaryFile(suffix=".exe", delete=False)
            for chunk in r.iter_content(chunk_size=8192):
                tmp.write(chunk)
            tmp.close()

            if os.path.getsize(tmp.name) < 1_000_000:
                os.unlink(tmp.name)
                return {"ok": False, "error": "Fichier trop petit"}

            return {"ok": True, "path": tmp.name, "version": update_data.get("version")}

        except Exception as e:
            return {"ok": False, "error": str(e)}

    def _on_install_done(self, result):
        if not result or not result.get("ok"):
            error = result.get("error", "Erreur inconnue") if result else "Erreur"
            self._ref_maj["btn_install"].setText(f"Erreur : {error}")
            self._ref_maj["btn_install"].setEnabled(True)
            return

        import platform
        import subprocess

        path = result["path"]
        version = result.get("version", "")

        self._ref_maj["btn_install"].setText(f"v{version} téléchargée !")
        self._ref_maj["badge"].setText("  Installation...  ")

        # Lancer l'installeur en mode silencieux (pas de fenêtres, pas de questions)
        if platform.system() == "Windows" and path.endswith((".exe", ".msi")):
            subprocess.Popen([path, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], shell=True)
        else:
            print(f"[MAJ] Fichier téléchargé : {path}")

    # ═══════════════════════════════════════════════
    #  ACTIONS — APPARENCE
    # ═══════════════════════════════════════════════

    def _on_theme_changed(self, index):
        dashboard = self.window()
        if hasattr(dashboard, '_toggle_theme'):
            current_is_dark = (T() is DARK_THEME)
            target_is_dark = (index == 1)
            if current_is_dark != target_is_dark:
                dashboard._toggle_theme()
        cfg = load_config()
        cfg["theme"] = "dark" if index == 1 else "light"
        save_config(cfg)
        from ui_components import toast
        toast("Thème " + ("sombre" if index == 1 else "clair") + " activé")

    def _on_lang_changed(self, index):
        cfg = load_config()
        cfg["langue"] = "en" if index == 1 else "fr"
        save_config(cfg)

    # ═══════════════════════════════════════════════
    #  ACTIONS — ÉCLAIRAGE (Pico LED)
    # ═══════════════════════════════════════════════

    def _led_watcher(self):
        """Retourne le LedStripWatcher actif, ou None si le monitoring n'est pas encore en place."""
        try:
            mon = getattr(self.window(), "_monitor", None)
            return getattr(mon, "_led", None) if mon else None
        except Exception:
            return None

    def _wire_led_watcher(self):
        """Connecte status_changed du watcher au label de statut + affiche l'etat initial."""
        from paths import reg_get
        w = self._led_watcher()
        if w is None:
            self._on_led_status_changed(False, "Monitoring inactif")
            return
        try:
            w.status_changed.connect(self._on_led_status_changed)
        except Exception:
            pass
        if w.is_connected():
            self._on_led_status_changed(True, w.port_name() or "Connecte")
        else:
            self._on_led_status_changed(False, "Recherche...")

    def _on_led_status_changed(self, connected, msg):
        lbl = self._ref_led.get("lbl_status")
        if not lbl:
            return
        if connected:
            text, color = f"Connecte ({msg})", "#3DA755"
        elif msg in ("Monitoring inactif", "pyserial absent"):
            text, color = msg, "#888888"
        elif "Recherche" in msg or "non detecte" in msg:
            text, color = msg, "#888888"
        else:
            text, color = msg, "#D14B4B"
        lbl.setText(text)
        lbl.setStyleSheet(
            f"color: {color}; font-family: 'Inter'; font-size: 13px; "
            f"font-weight: 600; background: transparent;"
        )

    def _on_led_toggle(self, event):
        from paths import reg_set
        from ui_components import toast
        toggle = self._ref_led["toggle_enabled"]
        toggle.mousePressEvent_orig(event)
        is_on = toggle.is_on()
        reg_set("led_enabled", 1 if is_on else 0)
        w = self._led_watcher()
        if w:
            if is_on:
                w.on()
            else:
                w.off()
        toast("Eclairage " + ("active" if is_on else "desactive"),
              "success" if is_on else "warning")

    def _on_led_normal_changed(self, value):
        self._ref_led["lbl_normal_value"].setText(f"{int(value)}%")

    def _on_led_normal_released(self):
        value = int(self._ref_led["slider_normal"].value())
        w = self._led_watcher()
        if w:
            w.set_normal(value)
        else:
            from paths import reg_set
            reg_set("led_normal_pct", value)

    def _on_led_boost_changed(self, value):
        self._ref_led["lbl_boost_value"].setText(f"{int(value)}%")

    def _on_led_boost_released(self):
        value = int(self._ref_led["slider_boost"].value())
        w = self._led_watcher()
        if w:
            w.set_boost(value)
        else:
            from paths import reg_set
            reg_set("led_boost_pct", value)

    def _on_led_test(self):
        from ui_components import toast
        w = self._led_watcher()
        if not w or not w.is_connected():
            toast("Pico non connecte - test impossible", "error")
            return
        w.boost()
        toast("Boost envoye", "success")

    # ═══════════════════════════════════════════════
    #  RESIZE — garder les overlays à la bonne taille
    # ═══════════════════════════════════════════════

    def resizeEvent(self, event):
        super().resizeEvent(event)
        main_win = self.window()
        for attr in ('_pin_overlay', '_hor_overlay'):
            overlay = getattr(self, attr, None)
            if overlay and overlay.isVisible():
                overlay.setGeometry(main_win.rect())
