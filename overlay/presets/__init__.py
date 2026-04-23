"""Presets de styles pour l'overlay d'impression."""
from . import memento, gaming, festif, minimal, pixel


PRESETS = {
    "memento": memento.PRESET,
    "gaming":  gaming.PRESET,
    "festif":  festif.PRESET,
    "minimal": minimal.PRESET,
    "pixel":   pixel.PRESET,
}


def get(style_id):
    return PRESETS.get(style_id) or PRESETS["memento"]


def list_all():
    return [(k, p["name"]) for k, p in PRESETS.items()]


def apply(cfg, style_id):
    p = get(style_id)
    cfg["style"] = style_id
    cfg["color_main"] = p["color_main"]
    cfg["color_text"] = p["color_text"]
    cfg["color_bg"] = p["color_bg"]
    cfg["font"] = p["font"]
    cfg["glow"] = p["glow"]
    return cfg
