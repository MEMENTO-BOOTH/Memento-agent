"""Composants UI style shadcn — Toast, HoverCard, Tooltip.
Utilisables partout dans l'app via import."""

from PyQt5.QtWidgets import (
    QWidget, QLabel, QPushButton, QHBoxLayout, QVBoxLayout,
    QGraphicsDropShadowEffect, QApplication,
)
from PyQt5.QtCore import Qt, QTimer, QRectF, QPoint, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QPainter, QColor, QPainterPath, QFont, QPen


# ════════════════════════════════════════════════════
#  TOAST — notification temporaire style sonner
# ════════════════════════════════════════════════════

class Toast(QWidget):
    """Toast notification style shadcn/sonner.
    Apparaît en bas à droite, disparaît après 3s, avec bouton X."""

    _stack = []  # pile des toasts actifs pour les empiler

    def __init__(self, message, variant="default", duration=3000, parent=None):
        # Parenter au top-level window
        if parent is None:
            parent = QApplication.activeWindow()
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedHeight(52)

        self._message = message
        self._variant = variant
        self._duration = duration
        self._opacity = 1.0

        # Couleurs par variante
        self._colors = {
            "default":  {"bg": "#0F172A", "text": "#FFFFFF", "border": "#1E293B"},
            "success":  {"bg": "#052E16", "text": "#4ADE80", "border": "#166534"},
            "error":    {"bg": "#450A0A", "text": "#FCA5A5", "border": "#991B1B"},
            "warning":  {"bg": "#451A03", "text": "#FCD34D", "border": "#92400E"},
        }

        self._build()
        self._position()

        Toast._stack.append(self)
        self.show()

        # Auto-close
        QTimer.singleShot(self._duration, self._close)

    def _build(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 8, 0)
        layout.setSpacing(12)

        colors = self._colors.get(self._variant, self._colors["default"])

        # Icône
        icons = {"success": "✓", "error": "✕", "warning": "⚠", "default": "ℹ"}
        icon_lbl = QLabel(icons.get(self._variant, "ℹ"))
        icon_lbl.setFixedSize(20, 20)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(
            f"color: {colors['text']}; font-size: 12px; font-weight: 700; "
            f"background: rgba(255,255,255,0.1); border-radius: 10px;"
        )
        layout.addWidget(icon_lbl)

        # Message
        msg = QLabel(self._message)
        msg.setStyleSheet(
            f"color: {colors['text']}; font-family: 'Satoshi'; "
            f"font-size: 13px; font-weight: 500; background: transparent;"
        )
        layout.addWidget(msg, 1)

        # Bouton fermer
        btn = QPushButton("✕")
        btn.setFixedSize(24, 24)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: rgba(255,255,255,0.4); "
            f"border: none; font-size: 12px; }} "
            f"QPushButton:hover {{ color: white; }}"
        )
        btn.clicked.connect(self._close)
        layout.addWidget(btn)

        # Ombre
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 60))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

    def _position(self):
        parent = self.parent()
        if not parent:
            return
        pw = parent.width()
        ph = parent.height()
        toast_w = min(380, pw - 40)
        self.setFixedWidth(toast_w)

        # Empiler les toasts (dernier en bas)
        idx = len(Toast._stack)
        x = pw - toast_w - 20
        y = ph - 20 - (idx + 1) * 60
        self.move(x, y)

    def _close(self):
        if self in Toast._stack:
            Toast._stack.remove(self)
        try:
            self.hide()
            self.deleteLater()
        except RuntimeError:
            pass  # Parent déjà détruit
        # Repositionner les toasts restants
        for i, t in enumerate(Toast._stack):
            parent = t.parent()
            if parent:
                y = parent.height() - 20 - (i + 1) * 60
                t.move(t.x(), y)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        colors = self._colors.get(self._variant, self._colors["default"])
        rect = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        p.fillPath(path, QColor(colors["bg"]))
        p.setPen(QPen(QColor(colors["border"]), 1))
        p.drawPath(path)
        p.end()


def toast(message, variant="default", duration=3000):
    """Affiche un toast. Variantes: default, success, error, warning."""
    return Toast(message, variant, duration)


# ════════════════════════════════════════════════════
#  HOVERCARD — popup au survol style shadcn
# ════════════════════════════════════════════════════

class HoverCard(QWidget):
    """Popup flottant au survol — style shadcn HoverCard."""

    _current = None  # un seul HoverCard à la fois

    def __init__(self, parent_widget, content_builder, anchor="bottom"):
        top_window = parent_widget.window()
        super().__init__(top_window)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._anchor = anchor

        # Construire le contenu
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(6)
        content_builder(layout)

        self.adjustSize()

        # Ombre
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(24)
        shadow.setColor(QColor(0, 0, 0, 40))
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)

        # Positionner sous le widget parent
        global_pos = parent_widget.mapToGlobal(QPoint(0, 0))
        local_pos = top_window.mapFromGlobal(global_pos)
        if anchor == "bottom":
            x = local_pos.x() + (parent_widget.width() - self.width()) // 2
            y = local_pos.y() + parent_widget.height() + 8
        else:
            x = local_pos.x() + (parent_widget.width() - self.width()) // 2
            y = local_pos.y() - self.height() - 8
        # Garder dans les limites de la fenêtre
        x = max(8, min(x, top_window.width() - self.width() - 8))
        y = max(8, min(y, top_window.height() - self.height() - 8))
        self.move(x, y)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(rect, 10, 10)
        p.fillPath(path, QColor("#FFFFFF"))
        p.setPen(QPen(QColor("#E2E8F0"), 1))
        p.drawPath(path)
        p.end()

    @staticmethod
    def show_card(parent_widget, content_builder, anchor="bottom"):
        """Affiche un HoverCard. Ferme l'ancien s'il existe."""
        HoverCard.hide_current()
        card = HoverCard(parent_widget, content_builder, anchor)
        HoverCard._current = card
        card.show()
        card.raise_()
        return card

    @staticmethod
    def hide_current():
        if HoverCard._current:
            HoverCard._current.hide()
            HoverCard._current.deleteLater()
            HoverCard._current = None


def _hc_title(text):
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color: #0F172A; font-family: 'Satoshi'; font-size: 13px; "
        "font-weight: 600; background: transparent;"
    )
    return lbl


def _hc_value(text):
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color: #0F172A; font-family: 'Satoshi'; font-size: 20px; "
        "font-weight: 700; background: transparent;"
    )
    return lbl


def _hc_sub(text):
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color: #64748B; font-family: 'Satoshi'; font-size: 11px; "
        "background: transparent;"
    )
    return lbl


# ════════════════════════════════════════════════════
#  TOOLTIP — tooltip au survol style shadcn
# ════════════════════════════════════════════════════

class Tooltip(QWidget):
    """Tooltip compacte style shadcn — fond noir, texte blanc."""

    _current = None

    def __init__(self, parent_widget, text, badge_text=None, badge_color=None):
        top_window = parent_widget.window()
        super().__init__(top_window)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.SubWindow)
        self.setAttribute(Qt.WA_TranslucentBackground)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        msg = QLabel(text)
        msg.setStyleSheet(
            "color: white; font-family: 'Satoshi'; font-size: 12px; "
            "font-weight: 400; background: transparent;"
        )
        layout.addWidget(msg)

        if badge_text:
            badge = QLabel(f"  {badge_text}  ")
            bg = badge_color or "#334155"
            badge.setStyleSheet(
                f"color: white; background: {bg}; font-family: 'Satoshi'; "
                f"font-size: 10px; font-weight: 600; border-radius: 4px; "
                f"padding: 2px 6px;"
            )
            layout.addWidget(badge)

        self.adjustSize()

        # Positionner au-dessus du widget
        global_pos = parent_widget.mapToGlobal(QPoint(0, 0))
        local_pos = top_window.mapFromGlobal(global_pos)
        x = local_pos.x() + (parent_widget.width() - self.width()) // 2
        y = local_pos.y() - self.height() - 6
        x = max(4, min(x, top_window.width() - self.width() - 4))
        self.move(x, y)

        # Ombre
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(12)
        shadow.setColor(QColor(0, 0, 0, 40))
        shadow.setOffset(0, 2)
        self.setGraphicsEffect(shadow)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)
        p.fillPath(path, QColor("#0F172A"))
        p.end()

    @staticmethod
    def show_tooltip(parent_widget, text, badge_text=None, badge_color=None):
        Tooltip.hide_current()
        tip = Tooltip(parent_widget, text, badge_text, badge_color)
        Tooltip._current = tip
        tip.show()
        tip.raise_()
        return tip

    @staticmethod
    def hide_current():
        if Tooltip._current:
            Tooltip._current.hide()
            Tooltip._current.deleteLater()
            Tooltip._current = None
