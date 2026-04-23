"""Dispatch vers le renderer correspondant au style demande."""
from . import memento, gaming, festif, minimal, pixel


_RENDERERS = {
    "memento": memento.render,
    "gaming":  gaming.render,
    "festif":  festif.render,
    "minimal": minimal.render,
    "pixel":   pixel.render,
}


def render(style, painter, rect, cfg, progress, label, timer_text, done):
    fn = _RENDERERS.get(style) or memento.render
    fn(painter, rect, cfg, progress, label, timer_text, done)
