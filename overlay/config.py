"""Lecture/ecriture de la configuration overlay dans la registry Windows."""
from paths import reg_get, reg_set


KEYS = (
    "overlay_enabled",
    "overlay_style",
    "overlay_color_main",
    "overlay_color_text",
    "overlay_color_bg",
    "overlay_font",
    "overlay_position",
    "overlay_duration",
    "overlay_glow",
)

DEFAULT = {
    "enabled": False,
    "style": "memento",
    "color_main": "#B6FF56",
    "color_text": "#FFFFFF",
    "color_bg": "#0F172A",
    "font": "Satoshi",
    "position": "bottom_right",
    "duration": 18,
    "glow": True,
}


def load():
    return {
        "enabled": bool(reg_get("overlay_enabled")),
        "style": reg_get("overlay_style"),
        "color_main": reg_get("overlay_color_main"),
        "color_text": reg_get("overlay_color_text"),
        "color_bg": reg_get("overlay_color_bg"),
        "font": reg_get("overlay_font"),
        "position": reg_get("overlay_position"),
        "duration": int(reg_get("overlay_duration") or 18),
        "glow": bool(reg_get("overlay_glow")),
    }


def save(cfg):
    reg_set("overlay_enabled", 1 if cfg["enabled"] else 0)
    reg_set("overlay_style", cfg["style"])
    reg_set("overlay_color_main", cfg["color_main"])
    reg_set("overlay_color_text", cfg["color_text"])
    reg_set("overlay_color_bg", cfg["color_bg"])
    reg_set("overlay_font", cfg["font"])
    reg_set("overlay_position", cfg["position"])
    reg_set("overlay_duration", int(cfg["duration"]))
    reg_set("overlay_glow", 1 if cfg["glow"] else 0)
