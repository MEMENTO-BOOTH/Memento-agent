"""Overlay de configuration de l'animation d'impression."""
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter, QColor

from dashboard import T, LIME_GREEN, TEXT_BLACK
from ...widgets import separator, styled_combo, ToggleSwitch
from overlay import config as cfg_mod
from overlay.presets import list_all as list_presets, apply as apply_preset, get as get_preset

from .preview import AnimationPreview
from .color_row import ColorRow


POSITIONS = [("bottom_right", "Bas droite"), ("bottom_center", "Bas centre"), ("top_right", "Haut droite")]
FONTS = ["Satoshi", "Inter", "Impact", "Courier New"]


class AnimationOverlay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._cfg = cfg_mod.load()
        self._on_saved = None
        self._build()

    def set_on_saved(self, cb):
        self._on_saved = cb

    def _build(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignCenter)

        card = QWidget()
        card.setFixedSize(520, 640)
        card.setObjectName("anim_card")
        card.setStyleSheet(f"QWidget#anim_card {{ background: {T()['card_bg']}; border: 1px solid {T()['card_border']}; border-radius: 16px; }}")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(28, 22, 28, 22)
        cl.setSpacing(14)

        cl.addLayout(self._header())
        cl.addWidget(self._preview_zone(), 0, Qt.AlignCenter)
        cl.addLayout(self._preset_row())
        cl.addWidget(separator())
        cl.addWidget(self._row_main)
        cl.addWidget(self._row_text)
        cl.addWidget(self._row_bg)
        cl.addWidget(separator())
        cl.addLayout(self._position_row())
        cl.addLayout(self._font_row())
        cl.addLayout(self._duration_row())
        cl.addLayout(self._glow_row())
        cl.addStretch()
        cl.addLayout(self._buttons())

        layout.addWidget(card)

    def _header(self):
        hl = QHBoxLayout()
        title = QLabel("Animation d'impression")
        title.setStyleSheet(f"color: {T()['text']}; font-family: 'Inter'; font-size: 17px; font-weight: 700; background: transparent;")
        hl.addWidget(title)
        hl.addStretch()
        close = QPushButton("✕")
        close.setFixedSize(30, 30)
        close.setCursor(Qt.PointingHandCursor)
        close.setStyleSheet(f"QPushButton {{ background: transparent; color: {T()['text']}; font-size: 16px; border: none; border-radius: 15px; }} QPushButton:hover {{ background: {T()['row_sep']}; }}")
        close.clicked.connect(self._close)
        hl.addWidget(close)
        return hl

    def _preview_zone(self):
        self._preview = AnimationPreview(self._cfg)
        return self._preview

    def _preset_row(self):
        hl = QHBoxLayout()
        lbl = QLabel("Style")
        lbl.setStyleSheet(f"color: {T()['text']}; font-family: 'Inter'; font-size: 13px; font-weight: 600; background: transparent;")
        hl.addWidget(lbl)
        hl.addStretch()
        items = list_presets()
        self._preset_ids = [k for k, _ in items]
        current_idx = self._preset_ids.index(self._cfg.get("style")) if self._cfg.get("style") in self._preset_ids else 0
        self._combo_preset = styled_combo([n for _, n in items], current_idx)
        self._combo_preset.currentIndexChanged.connect(self._on_preset)
        hl.addWidget(self._combo_preset)

        self._row_main = ColorRow("Couleur principale", self._cfg["color_main"])
        self._row_text = ColorRow("Couleur texte", self._cfg["color_text"])
        self._row_bg = ColorRow("Couleur fond barre", self._cfg["color_bg"])
        self._row_main.changed.connect(lambda v: self._set("color_main", v))
        self._row_text.changed.connect(lambda v: self._set("color_text", v))
        self._row_bg.changed.connect(lambda v: self._set("color_bg", v))
        return hl

    def _position_row(self):
        hl = QHBoxLayout()
        lbl = QLabel("Position")
        lbl.setStyleSheet(f"color: {T()['text']}; font-family: 'Inter'; font-size: 13px; font-weight: 600; background: transparent;")
        hl.addWidget(lbl)
        hl.addStretch()
        self._position_ids = [k for k, _ in POSITIONS]
        idx = self._position_ids.index(self._cfg.get("position")) if self._cfg.get("position") in self._position_ids else 0
        self._combo_pos = styled_combo([n for _, n in POSITIONS], idx)
        self._combo_pos.currentIndexChanged.connect(lambda i: self._set("position", self._position_ids[i]))
        hl.addWidget(self._combo_pos)
        return hl

    def _font_row(self):
        hl = QHBoxLayout()
        lbl = QLabel("Police")
        lbl.setStyleSheet(f"color: {T()['text']}; font-family: 'Inter'; font-size: 13px; font-weight: 600; background: transparent;")
        hl.addWidget(lbl)
        hl.addStretch()
        idx = FONTS.index(self._cfg.get("font")) if self._cfg.get("font") in FONTS else 0
        self._combo_font = styled_combo(FONTS, idx)
        self._combo_font.currentIndexChanged.connect(lambda i: self._set("font", FONTS[i]))
        hl.addWidget(self._combo_font)
        return hl

    def _duration_row(self):
        hl = QHBoxLayout()
        lbl = QLabel("Duree (secondes)")
        lbl.setStyleSheet(f"color: {T()['text']}; font-family: 'Inter'; font-size: 13px; font-weight: 600; background: transparent;")
        hl.addWidget(lbl)
        hl.addStretch()
        self._spin = QSpinBox()
        self._spin.setRange(5, 60)
        self._spin.setValue(int(self._cfg.get("duration", 18)))
        self._spin.setFixedSize(100, 34)
        self._spin.setStyleSheet(f"QSpinBox {{ border: 1.5px solid {T()['card_border']}; border-radius: 6px; padding: 4px 8px; font-family: 'Inter'; font-size: 13px; color: {T()['text']}; background: {T()['card_bg']}; }}")
        self._spin.valueChanged.connect(lambda v: self._set("duration", v))
        hl.addWidget(self._spin)
        return hl

    def _glow_row(self):
        hl = QHBoxLayout()
        lbl = QLabel("Effet glow")
        lbl.setStyleSheet(f"color: {T()['text']}; font-family: 'Inter'; font-size: 13px; font-weight: 600; background: transparent;")
        hl.addWidget(lbl)
        hl.addStretch()
        self._toggle_glow = ToggleSwitch(on=bool(self._cfg.get("glow")))
        orig = self._toggle_glow.mousePressEvent
        def _click(ev):
            orig(ev)
            self._set("glow", self._toggle_glow.is_on())
        self._toggle_glow.mousePressEvent = _click
        hl.addWidget(self._toggle_glow)

        enabled_lbl = QLabel("     Activer")
        enabled_lbl.setStyleSheet(f"color: {T()['text']}; font-family: 'Inter'; font-size: 13px; font-weight: 600; background: transparent;")
        hl.addWidget(enabled_lbl)
        self._toggle_enabled = ToggleSwitch(on=bool(self._cfg.get("enabled")))
        orig2 = self._toggle_enabled.mousePressEvent
        def _click2(ev):
            orig2(ev)
            self._cfg["enabled"] = self._toggle_enabled.is_on()
        self._toggle_enabled.mousePressEvent = _click2
        hl.addWidget(self._toggle_enabled)
        return hl

    def _buttons(self):
        hl = QHBoxLayout()
        reset = QPushButton("Reinitialiser")
        reset.setCursor(Qt.PointingHandCursor)
        reset.setFixedHeight(38)
        reset.setStyleSheet(f"background: transparent; color: {T()['text']}; border: 1px solid {T()['card_border']}; border-radius: 8px; padding: 0 16px; font-family: 'Inter'; font-size: 13px; font-weight: 500;")
        reset.clicked.connect(self._reset)

        test = QPushButton("Tester")
        test.setCursor(Qt.PointingHandCursor)
        test.setFixedHeight(38)
        test.setStyleSheet(f"background: transparent; color: {T()['text']}; border: 1px solid {T()['card_border']}; border-radius: 8px; padding: 0 16px; font-family: 'Inter'; font-size: 13px; font-weight: 500;")
        test.clicked.connect(self._test)

        save = QPushButton("Enregistrer")
        save.setCursor(Qt.PointingHandCursor)
        save.setFixedHeight(38)
        save.setStyleSheet(f"background: {LIME_GREEN}; color: {TEXT_BLACK}; border: none; border-radius: 8px; padding: 0 16px; font-family: 'Inter'; font-size: 13px; font-weight: 700;")
        save.clicked.connect(self._save)

        hl.addWidget(reset, 1)
        hl.addWidget(test, 1)
        hl.addWidget(save, 1)
        return hl

    def _test(self):
        """Sauve la config courante puis declenche une vraie barre overlay."""
        cfg_mod.save(self._cfg)
        from PyQt5.QtWidgets import QApplication
        mgr = getattr(QApplication.instance(), "_overlay_manager", None)
        if mgr:
            mgr.reload_config()
            mgr.trigger_preview()

    def _on_preset(self, idx):
        style_id = self._preset_ids[idx]
        apply_preset(self._cfg, style_id)
        self._row_main.set_value(self._cfg["color_main"])
        self._row_text.set_value(self._cfg["color_text"])
        self._row_bg.set_value(self._cfg["color_bg"])
        if self._cfg["font"] in FONTS:
            self._combo_font.setCurrentIndex(FONTS.index(self._cfg["font"]))
        self._toggle_glow.set_on(bool(self._cfg.get("glow")))
        self._preview.set_cfg(self._cfg)

    def _set(self, key, value):
        self._cfg[key] = value
        self._preview.set_cfg(self._cfg)

    def _reset(self):
        self._cfg = dict(cfg_mod.DEFAULT)
        self._combo_preset.setCurrentIndex(0)
        self._on_preset(0)
        self._combo_pos.setCurrentIndex(0)
        self._spin.setValue(self._cfg["duration"])
        self._toggle_enabled.set_on(False)
        self._cfg["enabled"] = False
        self._preview.set_cfg(self._cfg)

    def _save(self):
        cfg_mod.save(self._cfg)
        if self._on_saved:
            self._on_saved(self._cfg)
        self._close()

    def _close(self):
        self._preview.stop()
        self.hide()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 140))
        p.end()

    def mousePressEvent(self, event):
        if self.childAt(event.pos()) is None:
            self._close()
