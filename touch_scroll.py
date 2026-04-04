"""Active le scroll tactile (glisser avec le doigt) sur les QScrollArea."""
from PyQt5.QtWidgets import QScroller, QScrollArea


def enable_touch_scroll(scroll_area):
    """Active le scroll par glissement tactile sur une QScrollArea."""
    QScroller.grabGesture(scroll_area.viewport(), QScroller.LeftMouseButtonGesture)
