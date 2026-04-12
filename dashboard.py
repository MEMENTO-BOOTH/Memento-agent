import sys
import os
import re
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget,
    QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QScrollArea, QFrame,
    QSizePolicy, QGraphicsDropShadowEffect,
    QStackedWidget, QMenu, QAction,
    QSystemTrayIcon,
)
from PyQt5.QtCore import Qt, QRect, QRectF, QByteArray, QPointF, QThread, pyqtSignal, QTimer
from PyQt5.QtGui import (
    QPixmap, QPainter, QColor, QPen,
    QPainterPath, QFont, QFontDatabase, QIcon
)
from PyQt5.QtSvg import QSvgRenderer


from paths import ASSETS_DIR


def _utc_to_local(ts_str):
    """Convertit un timestamp UTC Supabase en heure locale lisible."""
    if not ts_str:
        return "—"
    try:
        from datetime import datetime, timezone, timedelta
        # Parse ISO format (2026-03-30T14:59:58.462539+00:00)
        clean = ts_str.replace("+00:00", "").replace("Z", "")
        if "." in clean:
            clean = clean[:clean.index(".")]  # Retirer microsecondes
        utc_dt = datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S")
        utc_dt = utc_dt.replace(tzinfo=timezone.utc)
        local_dt = utc_dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts_str[:19].replace("T", " ")

# ─── Palette fixe (ne change pas avec le thème) ────
SIDEBAR_BG = "#101010"
REVENUE_BG = "#242223"
BAR_GRAY = "#535252"
LIME_GREEN = "#B6FF56"
YELLOW_BADGE = "#F7DB2C"
SIGNAL_BLUE = "#4D29EC"
SIGNAL_GRAY = "#DBDBDB"
PROFILE_BG = "#B6FF56"
TEXT_BLACK = "#000000"
TEXT_WHITE = "#FFFFFF"
TEXT_MUTED = "#BFBFBF"
DONUT_GREEN = "#22C55E"

# ─── Thèmes clair / sombre ────────────────────────
LIGHT_THEME = {
    "content_bg": "#FFFFFF",
    "text": "#000000",
    "card_border": "#CCCCCC",
    "card_bg": "#FFFFFF",
    "table_header_bg": "#F7F7F7",
    "table_border": "#DCDADA",
    "row_sep": "#EEEEEE",
    "donut_ring": "#000000",
    "donut_stripe": "#AAAAAA",
    "donut_text": "#0F172A",
    "donut_sub": "#334155",
    "toolbar_icon": "#111111",
    "scroll_handle": "#CBD5E1",
    "header_text": "#000000",
}

DARK_THEME = {
    "content_bg": "#1A1A1A",
    "text": "#E0E0E0",
    "card_border": "#3A3A3A",
    "card_bg": "#2A2A2A",
    "table_header_bg": "#2A2A2A",
    "table_border": "#3A3A3A",
    "row_sep": "#3A3A3A",
    "donut_ring": "#333333",
    "donut_stripe": "#555555",
    "donut_text": "#FFFFFF",
    "donut_sub": "#999999",
    "toolbar_icon": "#CCCCCC",
    "scroll_handle": "#555555",
    "header_text": "#E0E0E0",
}

_current_theme = LIGHT_THEME

def T():
    """Retourne le thème actif."""
    return _current_theme


def load_svg(filename, size=24, color_override=None):
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        return pm
    with open(path, "r") as f:
        data = f.read()
    if color_override:
        data = data.replace('stroke="black"', f'stroke="{color_override}"')
        data = data.replace('stroke="white"', f'stroke="{color_override}"')
        data = data.replace('stroke="#111111"', f'stroke="{color_override}"')
        data = data.replace('stroke="#020202"', f'stroke="{color_override}"')
        data = data.replace('fill="black"', f'fill="{color_override}"')
        data = data.replace('fill="white"', f'fill="{color_override}"')
    renderer = QSvgRenderer(QByteArray(data.encode()))
    # Rendu HiDPI : on dessine à 2x puis on indique le ratio
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    renderer.render(p)
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


# ════════════════════════════════════════════════════
#  WIDGETS CUSTOM PEINTS (pas de QSS border hérité)
# ════════════════════════════════════════════════════

class BorderedCard(QWidget):
    """Carte avec bordure dessinée via QPainter, pas QSS → pas d'héritage."""
    def __init__(self, radius=20, parent=None):
        super().__init__(parent)
        self._radius = radius
        self._hover_builder = None  # fonction pour construire le contenu du HoverCard
        self.setMouseTracking(True)

    def set_hover(self, builder):
        """Définit le contenu du HoverCard au survol. builder(layout) → ajoute les widgets."""
        self._hover_builder = builder

    def enterEvent(self, event):
        if self._hover_builder:
            from ui_components import HoverCard
            HoverCard.show_card(self, self._hover_builder)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._hover_builder:
            from ui_components import HoverCard
            HoverCard.hide_current()
        super().leaveEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        p.fillPath(path, QColor(T()["card_bg"]))
        p.setPen(QPen(QColor(T()["card_border"]), 1.7))
        p.drawPath(path)
        p.end()


class DonutChart(QWidget):
    def __init__(self, value=120, total=400, parent=None):
        super().__init__(parent)
        self.value = value
        self.total = total
        self.setFixedSize(108, 108)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        cx = self.width() // 2
        cy = self.height() // 2
        rayon = 38
        epaisseur = 10

        # --- Fond anneau gris ---
        p.setPen(QPen(QColor("#E2E8F0"), epaisseur, Qt.SolidLine, Qt.RoundCap))
        p.drawEllipse(cx - rayon, cy - rayon, rayon * 2, rayon * 2)

        # --- Arc coloré ---
        pct = self.value / self.total if self.total > 0 else 0
        angle_total = int(360 * pct * 16)
        if pct > 0.5:
            couleur = "#22C55E"
        elif pct > 0.25:
            couleur = "#F59E0B"
        else:
            couleur = "#EF4444"

        arc_rect = QRectF(cx - rayon, cy - rayon, rayon * 2, rayon * 2)
        p.setPen(QPen(QColor(couleur), epaisseur, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(arc_rect, 90 * 16, -angle_total)

        # --- Texte central ---
        p.setPen(QColor(T()["text"]))
        font = QFont("Satoshi")
        font.setPixelSize(20)
        font.setWeight(QFont.Bold)
        p.setFont(font)
        p.drawText(self.rect(), Qt.AlignCenter, f"{self.value}")

        # Sous-texte
        p.setPen(QColor(T()["text"]))
        font.setPixelSize(9)
        font.setWeight(QFont.Normal)
        p.setFont(font)
        p.drawText(self.rect().adjusted(0, 24, 0, 0), Qt.AlignCenter, f"/{self.total}")

        p.end()


class BarChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(145)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.bars = [0, 0, 0, 0, 0, 0, 0]

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()
        count = len(self.bars)
        bar_w = min(56, (w - 40) // count - 10)
        spacing = (w - count * bar_w) / (count + 1)
        max_h = self.height() - 5
        bottom = self.height()

        for i, val in enumerate(self.bars):
            x = spacing + i * (bar_w + spacing)
            full_h = max_h
            val_h = int(val * max_h)

            bg = QPainterPath()
            bg.addRoundedRect(QRectF(x, bottom - full_h, bar_w, full_h), 10, 10)
            p.fillPath(bg, QColor(BAR_GRAY))

            fg = QPainterPath()
            fg.addRoundedRect(QRectF(x, bottom - val_h, bar_w, val_h), 10, 10)
            p.fillPath(fg, QColor(LIME_GREEN))
        p.end()


class WifiBar(QWidget):
    def __init__(self, strength=86, parent=None):
        super().__init__(parent)
        self.strength = strength
        self.setFixedSize(151, 12)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        bg = QPainterPath()
        bg.addRoundedRect(QRectF(0, 0, 151, 12), 6, 6)
        p.fillPath(bg, QColor(SIGNAL_GRAY))
        fw = int(151 * self.strength / 100)
        fg = QPainterPath()
        fg.addRoundedRect(QRectF(0, 0, fw, 12), 6, 6)
        p.fillPath(fg, QColor(SIGNAL_BLUE))
        p.end()


class NavItem(QPushButton):
    """Nav item style shadcn — fond subtil au hover/active, icône + label noirs."""
    def __init__(self, svg_file, label, active=False, parent=None):
        super().__init__(parent)
        self._label = label
        self._active = active
        self._svg_file = svg_file
        self._hovered = False
        self.setFixedHeight(40)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("border: none; background: transparent;")
        self._icon = load_svg(svg_file, 20, "#000000")
        self.clicked.connect(self._on_click)

    def set_active(self, active):
        self._active = active
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()

    def leaveEvent(self, event):
        self._hovered = False
        self.update()

    def _on_click(self):
        parent = self.parentWidget()
        if parent:
            for child in parent.findChildren(NavItem):
                child.set_active(False)
        self.set_active(True)
        dashboard = self.window()
        if hasattr(dashboard, '_nav_items') and hasattr(dashboard, '_stacked'):
            idx = dashboard._nav_items.index(self) if self in dashboard._nav_items else 0
            dashboard._switch_page(idx)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Fond arrondi — vert lime si actif, gris très léger si hover
        if self._active:
            bg_rect = QRectF(4, 2, w - 8, h - 4)
            bg_path = QPainterPath()
            bg_path.addRoundedRect(bg_rect, 8, 8)
            p.fillPath(bg_path, QColor(LIME_GREEN))
        elif self._hovered:
            bg_rect = QRectF(4, 2, w - 8, h - 4)
            bg_path = QPainterPath()
            bg_path.addRoundedRect(bg_rect, 8, 8)
            p.fillPath(bg_path, QColor("#F1F5F9"))

        # Icône
        p.drawPixmap(14, (h - 20) // 2, self._icon)

        # Label — noir pur
        p.setPen(QColor("#000000"))
        fw = QFont.DemiBold if self._active else QFont.Normal
        p.setFont(QFont("Satoshi", 12, fw))
        p.drawText(QRect(42, 0, w - 50, h), Qt.AlignVCenter | Qt.AlignLeft, self._label)
        p.end()


class ProfileCard(QWidget):
    """Carte profil peinte manuellement pour éviter les artefacts QSS."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(160)
        self.setCursor(Qt.PointingHandCursor)
        self._nom = "—"
        self._code = "—"
        self._logo = None
        self._signout = load_svg("icon_signout.svg", 18, TEXT_BLACK)
        self._hover_btn = False

    def set_borne_info(self, nom, code):
        self._nom = nom
        self._code = code
        self.update()

    def set_avatar_from_url(self, url):
        """Télécharge le logo du partenaire depuis une URL."""
        try:
            import requests
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                pm = QPixmap()
                pm.loadFromData(r.content)
                if not pm.isNull():
                    self._logo = pm.scaled(50, 50, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                    self.update()
        except Exception:
            pass

    def _btn_rect(self):
        return QRectF(12, self.height() - 52, self.width() - 24, 40)

    def mousePressEvent(self, event):
        if self._btn_rect().contains(event.pos()):
            self._disconnect()

    def _disconnect(self):
        """Verrouille l'agent — affiche le lock screen PIN."""
        dashboard = self.window()
        if isinstance(dashboard, DashboardWindow) and hasattr(dashboard, '_on_disconnect'):
            dashboard._on_disconnect()
        else:
            # Fallback — chercher la MainWindow parent
            parent = dashboard.parent()
            while parent:
                if hasattr(parent, '_on_disconnect'):
                    parent._on_disconnect()
                    return
                parent = parent.parent()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # Fond vert lime arrondi
        card_rect = QRectF(0, 0, w, h)
        card_path = QPainterPath()
        card_path.addRoundedRect(card_rect, 10, 10)
        p.fillPath(card_path, QColor(LIME_GREEN))

        # Avatar 40x40
        ax, ay = 14, 16
        avatar_rect = QRectF(ax, ay, 40, 40)
        clip = QPainterPath()
        clip.addEllipse(avatar_rect)
        p.setClipPath(clip)
        if self._logo and not self._logo.isNull():
            p.drawPixmap(ax, ay, self._logo)
        else:
            default_path = os.path.join(ASSETS_DIR, "avatar_default.png")
            if os.path.exists(default_path):
                pm = QPixmap(default_path).scaled(40, 40, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                p.drawPixmap(ax, ay, pm)
            else:
                p.fillPath(clip, QColor("#FFFFFF"))
        p.setClipping(False)

        # Nom + code — noir sur vert
        p.setPen(QColor(TEXT_BLACK))
        p.setFont(QFont("Satoshi", 11, QFont.DemiBold))
        p.drawText(QRect(ax + 48, ay + 2, w - ax - 60, 18), Qt.AlignVCenter | Qt.AlignLeft, self._nom)
        p.setFont(QFont("Satoshi", 10))
        p.drawText(QRect(ax + 48, ay + 20, w - ax - 60, 16), Qt.AlignVCenter | Qt.AlignLeft, self._code)

        # Séparateur subtil
        sep_y = ay + 52
        p.setPen(QPen(QColor(0, 0, 0, 30), 0.5))
        p.drawLine(12, sep_y, w - 12, sep_y)

        # Bouton Déconnexion — fond noir
        btn_rect = self._btn_rect()
        btn_path = QPainterPath()
        btn_path.addRoundedRect(btn_rect, 8, 8)
        p.fillPath(btn_path, QColor(TEXT_BLACK))
        p.setPen(QColor(TEXT_WHITE))
        p.setFont(QFont("Satoshi", 11, QFont.DemiBold))
        p.drawText(QRect(int(btn_rect.x()) + 12, int(btn_rect.y()), int(btn_rect.width()) - 40, int(btn_rect.height())),
                   Qt.AlignVCenter | Qt.AlignLeft, "Déconnexion")
        if not self._signout.isNull():
            icon_x = int(btn_rect.x() + btn_rect.width() - 30)
            icon_y = int(btn_rect.y() + (btn_rect.height() - 18) / 2)
            p.drawPixmap(icon_x, icon_y, load_svg("icon_signout.svg", 18, TEXT_WHITE))

        p.end()


class CollapsedNavPill(QWidget):
    """Pilule vert lime avec icônes nav pour sidebar repliée."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(57, 220)
        self.setCursor(Qt.PointingHandCursor)
        self._active_index = 0
        self._n = 4
        self._icons_black = [
            load_svg("icon_grid.svg", 22, TEXT_BLACK),
            load_svg("icon_activity.svg", 22, TEXT_BLACK),
            load_svg("icon_dollar.svg", 22, TEXT_BLACK),
            load_svg("icon_settings.svg", 22, TEXT_BLACK),
        ]
        self._icons_white = [
            load_svg("icon_grid.svg", 22, TEXT_WHITE),
            load_svg("icon_activity.svg", 22, TEXT_WHITE),
            load_svg("icon_dollar.svg", 22, TEXT_WHITE),
            load_svg("icon_settings.svg", 22, TEXT_WHITE),
        ]

    def set_active(self, index):
        self._active_index = index
        self.update()

    def _icon_center_y(self, i):
        spacing = self.height() / (self._n + 1)
        return int(spacing * (i + 1))

    def mousePressEvent(self, event):
        y = event.pos().y()
        # Déterminer quel icône a été cliqué
        best = 0
        best_dist = abs(y - self._icon_center_y(0))
        for i in range(1, self._n):
            d = abs(y - self._icon_center_y(i))
            if d < best_dist:
                best = i
                best_dist = d
        self.set_active(best)
        # Synchroniser avec les NavItems expanded
        dashboard = self.window()
        if hasattr(dashboard, '_nav_items'):
            for j, nav in enumerate(dashboard._nav_items):
                nav.set_active(j == best)
        if hasattr(dashboard, '_stacked'):
            dashboard._switch_page(best)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Pilule lime green
        pill = QPainterPath()
        pill.addRoundedRect(QRectF(0, 0, w, h), 22, 22)
        p.fillPath(pill, QColor(LIME_GREEN))

        # 4 icônes espacées verticalement
        for i in range(self._n):
            cy = self._icon_center_y(i)
            cx = w // 2

            if i == self._active_index:
                # Cercle noir pour l'item actif
                r = 22
                circle = QPainterPath()
                circle.addEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))
                p.fillPath(circle, QColor(TEXT_BLACK))
                p.drawPixmap(cx - 11, cy - 11, self._icons_white[i])
            else:
                p.drawPixmap(cx - 11, cy - 11, self._icons_black[i])

        p.end()


class CollapsedProfile(QWidget):
    """Profil replié : pilule lime avec sign-out + initiales en dessous."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(57, 105)
        self.setCursor(Qt.PointingHandCursor)
        self._signout = load_svg("icon_signout.svg", 24, TEXT_BLACK)
        self._initiales = "—"
        self._grad_idx = 0
        self._logo = None

    def set_borne_info(self, nom):
        parts = nom.strip().split()
        if len(parts) >= 2:
            self._initiales = (parts[0][0] + parts[1][0]).upper()
        elif len(parts) == 1 and len(parts[0]) >= 2:
            self._initiales = parts[0][:2].upper()
        self.update()

    def set_logo(self, pixmap):
        self._logo = pixmap.scaled(40, 40, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w = self.width()

        # Petite pilule lime pour sign-out
        pill_h = 50
        pill = QPainterPath()
        pill.addRoundedRect(QRectF(0, 0, w, pill_h), 10, 10)
        p.fillPath(pill, QColor(LIME_GREEN))

        if not self._signout.isNull():
            p.drawPixmap((w - 24) // 2, (pill_h - 24) // 2, self._signout)

        # Avatar en dessous
        avatar_y = pill_h + 12
        avatar_rect = QRectF((w - 40) / 2, avatar_y, 40, 40)
        clip = QPainterPath()
        clip.addEllipse(avatar_rect)

        if self._logo and not self._logo.isNull():
            p.setClipPath(clip)
            p.drawPixmap(int((w - 40) / 2), int(avatar_y), self._logo)
            p.setClipping(False)
        else:
            default_path = os.path.join(ASSETS_DIR, "avatar_default.png")
            if os.path.exists(default_path):
                pm = QPixmap(default_path).scaled(40, 40, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                p.setClipPath(clip)
                p.drawPixmap(int((w - 40) / 2), int(avatar_y), pm)
                p.setClipping(False)
            else:
                p.fillPath(clip, QColor("#F1F5F9"))
            p.setPen(QPen(QColor("#E2E8F0"), 1.7))
            p.drawEllipse(avatar_rect.adjusted(0.5, 0.5, -0.5, -0.5))

        p.end()

    def mousePressEvent(self, event):
        # Clic sur la pilule sign-out (zone y < 50)
        if event.pos().y() <= 50:
            dashboard = self.window()
            if hasattr(dashboard, '_on_disconnect'):
                dashboard._on_disconnect()


class _SupabaseWorker(QThread):
    """Worker pour charger les données Supabase en arrière-plan.
    Défini au niveau module pour éviter les crashs PyInstaller avec pyqtSignal."""
    done = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)

    def run(self):
        import supabase_client as supa
        import requests as req
        result = {}
        try:
            borne = supa.get_borne()
            if borne:
                result["borne"] = borne
                result["heartbeat"] = supa.get_heartbeat(borne["id"])
                result["alertes"] = supa.get_alertes(borne["id"], limit=16)
                # CA du jour
                tx_today = supa.get_transactions_today(borne["id"])
                result["ca"] = supa.get_ca_stats(tx_today)
                # CA par jour de la semaine (pour le bar chart)
                from datetime import date as dt_date, timedelta as dt_td
                today = dt_date.today()
                monday = today - dt_td(days=today.weekday())
                ca_week = []
                for d in range(7):
                    day = monday + dt_td(days=d)
                    tx_day = supa.get_transactions_by_date(borne["id"], day)
                    stats = supa.get_ca_stats(tx_day)
                    ca_week.append(stats["montant"])
                result["ca_week"] = ca_week
                # Charger le logo : partenaire d'abord, sinon fallback borne.logo_url
                logo_url = None
                pid = borne.get("partenaire_id")
                if pid:
                    try:
                        r = req.get(
                            f"{supa.SUPABASE_URL}/rest/v1/partenaires?id=eq.{pid}&select=logo_url",
                            headers=supa.HEADERS, timeout=10,
                        )
                        if r.status_code == 200 and r.json():
                            logo_url = r.json()[0].get("logo_url")
                    except Exception:
                        pass
                if not logo_url:
                    logo_url = borne.get("logo_url")
                if logo_url:
                    try:
                        img = req.get(logo_url, timeout=10)
                        if img.status_code == 200:
                            result["logo_bytes"] = img.content
                    except Exception:
                        pass
        except Exception:
            pass
        self.done.emit(result)


class _AlertesFastWorker(QThread):
    """Worker léger — ne charge que les alertes (pas borne, CA, logo)."""
    done = pyqtSignal(object)

    def __init__(self, borne_id, parent=None):
        super().__init__(parent)
        self._borne_id = borne_id

    def run(self):
        import supabase_client as supa
        try:
            alertes = supa.get_alertes(self._borne_id, limit=16)
            self.done.emit({"alertes": alertes})
        except Exception:
            self.done.emit({})


class ErrorTableWidget(QWidget):
    """Tableau d'erreurs entièrement peint pour un rendu propre."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self._icons = []
        self._dots_light = load_svg("icon_dots.svg", 18, TEXT_BLACK)
        self._dots_dark = load_svg("icon_dots.svg", 18, "#CCCCCC")
        self._hover_row = -1
        self.setMinimumWidth(780)

        self._header_h = 52
        self._row_h = 60
        h = self._header_h + len(self.rows) * self._row_h
        self.setFixedHeight(h)
        self.setMouseTracking(True)

    def mouseMoveEvent(self, event):
        row_idx = self._row_at(event.pos().y())
        if row_idx != self._hover_row:
            self._hover_row = row_idx
            # Tooltip sur le badge statut
            if row_idx >= 0 and row_idx < len(self.rows):
                w = self.width()
                badge_x = int(0.82 * w)
                if event.pos().x() >= badge_x - 10 and event.pos().x() <= badge_x + 80:
                    from ui_components import Tooltip
                    statut = self.rows[row_idx][8] if len(self.rows[row_idx]) > 8 else "ouverte"
                    if statut == "resolue":
                        Tooltip.show_tooltip(self, "Résolu par Agent", "Résolu", "#16A34A")
                    else:
                        Tooltip.show_tooltip(self, "Alerte non résolue", "Critique", "#DC2626")
                else:
                    from ui_components import Tooltip
                    Tooltip.hide_current()
            else:
                from ui_components import Tooltip
                Tooltip.hide_current()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover_row = -1
        from ui_components import Tooltip
        Tooltip.hide_current()
        super().leaveEvent(event)

    def _row_at(self, y):
        """Retourne l'index de la ligne à la position y, ou -1."""
        if y < self._header_h:
            return -1
        idx = int((y - self._header_h) / self._row_h)
        return idx if idx < len(self.rows) else -1

    def mousePressEvent(self, event):
        row_idx = self._row_at(event.pos().y())
        if row_idx < 0:
            return
        # Vérifier si le clic est dans la zone des 3 points
        w = self.width()
        dots_x = int(0.942 * w)
        if event.pos().x() >= dots_x - 10:
            self._show_row_menu(row_idx, event.globalPos())

    def _show_detail_overlay(self, type_label, message, heure, source, statut):
        """Overlay sobre pour afficher les détails d'une alerte."""
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton
        dlg = QDialog(self.window())
        dlg.setWindowTitle("Détails de l'alerte")
        dlg.setFixedSize(420, 280)
        dlg.setStyleSheet(f"background: {T()['card_bg']}; border-radius: 12px;")
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(24, 20, 24, 20)
        vl.setSpacing(12)

        title = QLabel(type_label)
        title.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 16px; font-weight: 700; background: transparent;")
        vl.addWidget(title)

        def _row(label_text, value_text):
            r = QHBoxLayout()
            l = QLabel(label_text)
            l.setStyleSheet(f"color: #333333; font-family: 'Satoshi'; font-size: 12px; background: transparent;")
            v = QLabel(value_text)
            v.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 12px; background: transparent;")
            v.setWordWrap(True)
            r.addWidget(l)
            r.addStretch()
            r.addWidget(v)
            return r

        vl.addLayout(_row("Heure", heure))
        vl.addLayout(_row("Source", source))
        vl.addLayout(_row("Statut", statut.capitalize()))
        msg_lbl = QLabel(message)
        msg_lbl.setWordWrap(True)
        msg_lbl.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 12px; background: transparent; padding-top: 8px;")
        vl.addWidget(msg_lbl)
        vl.addStretch()

        btn = QPushButton("Fermer")
        btn.setFixedHeight(34)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"QPushButton {{ background: {TEXT_BLACK}; color: {TEXT_WHITE}; border-radius: 6px; font-family: 'Satoshi'; font-size: 12px; font-weight: 600; border: none; }} QPushButton:hover {{ background: #333333; }}")
        btn.clicked.connect(dlg.close)
        vl.addWidget(btn)
        dlg.exec_()

    def _show_row_menu(self, row_idx, global_pos):
        """Menu contextuel pour une ligne du tableau."""
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {T()['card_bg']};
                border: 1.7px solid {T()['card_border']};
                border-radius: 8px;
                padding: 4px 0;
                font-family: 'Satoshi';
                font-size: 13px;
                color: {T()['text']};
            }}
            QMenu::item {{
                padding: 8px 24px;
            }}
            QMenu::item:selected {{
                background-color: {LIME_GREEN};
                color: {TEXT_BLACK};
            }}
        """)
        err_type = self.rows[row_idx][0]

        act_detail = menu.addAction("Voir les détails")

        # Sous-menu Assigner → liste des utilisateurs depuis Supabase
        assign_menu = menu.addMenu("Assigner à")
        import supabase_client as supa
        users = supa.get_utilisateurs()
        assign_actions = {}
        if users:
            for u in users:
                nom = u.get("nom", u.get("email", "—"))
                a = assign_menu.addAction(nom)
                assign_actions[a] = nom
        else:
            assign_menu.addAction("Gauthier").setData("Gauthier")
            assign_menu.addAction("Jules").setData("Jules")
            assign_menu.addAction("Collins").setData("Collins")
            for a in assign_menu.actions():
                assign_actions[a] = a.text()

        act_resolve = menu.addAction("Marquer résolu")
        menu.addSeparator()
        act_delete = menu.addAction("Supprimer")

        chosen = menu.exec_(global_pos)

        # Récupérer l'ID de l'alerte (stocké dans la 6ème colonne cachée)
        alerte_id = self.rows[row_idx][6] if len(self.rows[row_idx]) > 6 else None

        if chosen == act_detail:
            msg = self.rows[row_idx][7] if len(self.rows[row_idx]) > 7 else err_type
            ts = self.rows[row_idx][2] if len(self.rows[row_idx]) > 2 else ""
            source = self.rows[row_idx][3] if len(self.rows[row_idx]) > 3 else ""
            statut_txt = self.rows[row_idx][8] if len(self.rows[row_idx]) > 8 else "ouverte"
            from alertes.data import TYPE_LABELS
            label_type = TYPE_LABELS.get(err_type, err_type)
            self._show_detail_overlay(label_type, msg, ts, source, statut_txt)

        elif chosen in assign_actions:
            assignee_nom = assign_actions[chosen]
            if alerte_id:
                from alertes.data import assign_alerte
                if assign_alerte(alerte_id, assignee_nom):
                    # Mettre à jour la colonne "Assignée à" dans la row
                    row = list(self.rows[row_idx])
                    row[4] = assignee_nom
                    self.rows[row_idx] = tuple(row)
                    self.update()

        elif chosen == act_resolve:
            if alerte_id:
                from alertes.data import resolve_alerte
                if resolve_alerte(alerte_id):
                    row = list(self.rows[row_idx])
                    row[5] = "oui"
                    if len(row) > 8:
                        row[8] = "resolue"
                    self.rows[row_idx] = tuple(row)
                    # Recharger l'icône en blanc
                    fname = row[1]
                    p2 = os.path.join(ASSETS_DIR, fname)
                    if os.path.exists(p2):
                        import re as _re
                        with open(p2, "r") as ff:
                            raw = ff.read()
                        raw = _re.sub(r'stroke="[^"]*"', 'stroke="#FFFFFF"', raw)
                        raw = _re.sub(r'fill="[^"]*"', 'fill="#FFFFFF"', raw)
                        from PyQt5.QtSvg import QSvgRenderer
                        rdr = QSvgRenderer(QByteArray(raw.encode()))
                        sc = 2; pm = QPixmap(32 * sc, 32 * sc); pm.fill(Qt.transparent)
                        pp = QPainter(pm); rdr.render(pp); pp.end()
                        pm.setDevicePixelRatio(sc)
                        self._icons[row_idx] = pm
                    self.update()

        elif chosen == act_delete:
            if alerte_id:
                from alertes.data import delete_alerte
                delete_alerte(alerte_id)
            self.rows.pop(row_idx)
            self._icons.pop(row_idx)
            h = self._header_h + len(self.rows) * self._row_h
            self.setFixedHeight(max(h, self._header_h))
            self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        total_h = self.height()
        r = 16.0

        # Fond + bordure arrondie
        outer = QPainterPath()
        outer.addRoundedRect(QRectF(0.5, 0.5, w - 1, total_h - 1), r, r)
        p.fillPath(outer, QColor(T()["card_bg"]))
        p.setPen(QPen(QColor(T()["table_border"]), 1.7))
        p.drawPath(outer)

        # En-tête — fond subtil
        hdr = QPainterPath()
        hdr.moveTo(1, self._header_h)
        hdr.lineTo(1, r)
        hdr.arcTo(QRectF(1, 1, r * 2, r * 2), 180, -90)
        hdr.lineTo(w - r - 1, 1)
        hdr.arcTo(QRectF(w - r * 2 - 1, 1, r * 2, r * 2), 90, -90)
        hdr.lineTo(w - 1, self._header_h)
        hdr.closeSubpath()
        p.fillPath(hdr, QColor(T()["table_header_bg"]))
        # Ligne sous header
        p.setPen(QPen(QColor(T()["table_border"]), 1.7))
        p.drawLine(0, self._header_h, w, self._header_h)

        # Colonnes proportionnelles
        col_ratios = [0.067, 0.27, 0.47, 0.65, 0.82, 0.95]
        cols_x = [int(ratio * w) for ratio in col_ratios]
        icon_x = int(0.02 * w)
        col_headers = ["Alerte", "Heure", "Source", "Assignée à", "Statut", ""]

        # Texte en-tête — Satoshi Medium, uppercase, petit, espacé
        font_header = QFont("Satoshi")
        font_header.setPixelSize(11)
        font_header.setWeight(57)  # Medium
        font_header.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
        p.setFont(font_header)
        p.setPen(QColor(T()["text"]))
        for i, (x, txt) in enumerate(zip(cols_x, col_headers)):
            if txt:
                col_w = (cols_x[i + 1] if i + 1 < len(cols_x) else w) - x
                p.drawText(QRect(x, 0, col_w, self._header_h), Qt.AlignVCenter | Qt.AlignLeft, txt.upper())

        # Lignes de données
        for row_idx, row_data in enumerate(self.rows):
            from alertes.data import TYPE_LABELS
            err_type = TYPE_LABELS.get(row_data[0], row_data[0])
            time_str = row_data[2]
            source = row_data[3]
            assigned = row_data[4]
            statut = row_data[8] if len(row_data) > 8 else "ouverte"
            resolue_par = row_data[9] if len(row_data) > 9 else "—"
            is_resolved = (statut == "resolue")
            y = self._header_h + row_idx * self._row_h

            # Séparateur fin
            if row_idx > 0:
                p.setPen(QPen(QColor(T()["row_sep"]), 1))
                p.drawLine(16, y, w - 16, y)

            cy = y + self._row_h // 2

            # Icône alerte 32x32 — vert+noir si résolu, rouge+blanc sinon
            if row_idx < len(self._icons):
                icon = self._icons[row_idx]
                if not icon.isNull():
                    p.drawPixmap(icon_x, cy - 16, icon)

            # Type d'erreur — Satoshi DemiBold, noir
            font_type = QFont("Satoshi")
            font_type.setPixelSize(13)
            font_type.setWeight(63)
            p.setFont(font_type)
            p.setPen(QColor(T()["text"]))
            p.drawText(QRect(cols_x[0], y, cols_x[1] - cols_x[0], self._row_h), Qt.AlignVCenter | Qt.AlignLeft, err_type)

            # Heure, Source, Assignée à — Satoshi Regular, noir
            font_body = QFont("Satoshi")
            font_body.setPixelSize(12)
            p.setFont(font_body)
            p.setPen(QColor(T()["text"]))
            p.drawText(QRect(cols_x[1], y, cols_x[2] - cols_x[1], self._row_h), Qt.AlignVCenter | Qt.AlignLeft, time_str)
            p.drawText(QRect(cols_x[2], y, cols_x[3] - cols_x[2], self._row_h), Qt.AlignVCenter | Qt.AlignLeft, source)
            # Assignée à — si résolu, afficher qui a résolu
            col4_text = resolue_par if is_resolved and resolue_par != "—" else assigned
            p.drawText(QRect(cols_x[3], y, cols_x[4] - cols_x[3], self._row_h), Qt.AlignVCenter | Qt.AlignLeft, col4_text)

            # Badge statut
            if is_resolved:
                badge_text = "Résolu"
                badge_bg = "#F0FDF4"
                badge_fg = "#16A34A"
            else:
                badge_text = "Actif"
                badge_bg = "#FEF2F2"
                badge_fg = "#DC2626"

            font_badge = QFont("Satoshi")
            font_badge.setPixelSize(11)
            font_badge.setWeight(63)
            p.setFont(font_badge)
            tw = p.fontMetrics().horizontalAdvance(badge_text) + 18
            bx = cols_x[4]
            by = cy - 11
            badge_path = QPainterPath()
            badge_path.addRoundedRect(QRectF(bx, by, tw, 22), 11, 11)
            p.fillPath(badge_path, QColor(badge_bg))
            p.setPen(QColor(badge_fg))
            p.drawText(QRect(int(bx), int(by), int(tw), 22), Qt.AlignCenter, badge_text)

            # Menu 3 points
            dots = self._dots_dark if T() is DARK_THEME else self._dots_light
            if not dots.isNull():
                p.drawPixmap(cols_x[5], cy - 9, dots)

        p.end()


# ════════════════════════════════════════════════════
#  FENÊTRE PRINCIPALE
# ════════════════════════════════════════════════════

class DashboardWindow(QMainWindow):
    def __init__(self, monitor=None):
        super().__init__()
        self._existing_monitor = monitor
        self.setWindowTitle("Memento Agent — Dashboard")
        # Adapter à la taille de l'écran
        screen = QApplication.primaryScreen().availableGeometry()
        self.setMinimumSize(min(1050, screen.width()), min(650, screen.height()))
        self.resize(min(1184, screen.width()), min(780, screen.height()))
        icon_path = os.path.join(ASSETS_DIR, "logo.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        self._sidebar_expanded = True

        central = QWidget()
        central.setStyleSheet(f"background-color: {T()["content_bg"]};")
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)
        root.addWidget(self._build_content(), 1)

        # Charger les données depuis Supabase
        try:
            self._fetch_supabase_data()
        except Exception:
            pass

        # Démarrer le monitoring en arrière-plan
        try:
            self._start_monitoring()
        except Exception:
            pass

        # System tray — l'app tourne en fond quand on ferme la fenêtre
        self._setup_tray()

        # Auto-refresh Supabase toutes les 60 secondes
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh)
        self._refresh_timer.start(300_000)  # 5 minutes

    def _start_monitoring(self):
        """Connecte le moteur de monitoring (déjà démarré dans main.py)."""
        if self._existing_monitor and self._existing_monitor.isRunning():
            self._monitor = self._existing_monitor
            self._monitor.data_updated.connect(self._on_monitoring_data)
            self._monitor.alerte_changed.connect(self._on_alerte_changed)
            self._monitor.alerte_critique.connect(self._on_alerte_critique)
        else:
            # Fallback : démarrer un nouveau monitoring si aucun n'existe
            from monitoring import MonitoringEngine
            self._monitor = MonitoringEngine()
            self._monitor.data_updated.connect(self._on_monitoring_data)
            self._monitor.alerte_changed.connect(self._on_alerte_changed)
            self._monitor.alerte_critique.connect(self._on_alerte_critique)
            self._monitor.start()

    def _on_alerte_critique(self, has_critique):
        """Alerte critique → afficher/cacher l'écran de rupture."""
        from rupture_screen import show_rupture, hide_rupture
        if has_critique:
            show_rupture()
        else:
            hide_rupture()

    def _on_alerte_changed(self):
        """Une alerte a été créée ou résolue — rafraîchir rapidement (alertes uniquement)."""
        # Worker léger : ne charge que les alertes, pas borne/CA/logo
        if hasattr(self, '_borne_id_cache') and self._borne_id_cache:
            if not (hasattr(self, '_fast_worker') and self._fast_worker and self._fast_worker.isRunning()):
                self._fast_worker = _AlertesFastWorker(self._borne_id_cache)
                self._fast_worker.done.connect(self._on_data_loaded)
                self._fast_worker.start()
        # Rafraîchir la page alertes si elle existe
        if hasattr(self, '_page_alertes') and hasattr(self._page_alertes, '_auto_refresh'):
            try:
                self._page_alertes._auto_refresh()
            except Exception:
                pass

    def _on_monitoring_data(self, donnees):
        """Mise à jour en temps réel depuis le monitoring."""
        if not donnees:
            return
        try:
            self._apply_monitoring(donnees)
        except Exception as e:
            print(f"[DASHBOARD] monitoring update error: {e}")

    def _apply_monitoring(self, donnees):
        # Papier
        feuilles = donnees.get("feuilles_restantes")
        if feuilles is not None:
            total = 400
            self._donut.value = feuilles
            self._donut.total = total
            self._donut.update()
            pct = int((1 - feuilles / total) * 100) if total > 0 else 0
            self._lbl_pct.setText(f"{pct} % utilisés")

        # WiFi
        ssid = donnees.get("ssid_wifi")
        if ssid:
            self._lbl_wifi_name.setText(ssid)
            speed = donnees.get("wifi_speed_mbps")
            qualite = donnees.get("wifi_qualite", 80)
            self._wifi_bar.strength = qualite
            self._wifi_bar.update()
            if speed:
                self._lbl_signal.setText(f"Signal: {speed} Mbps ({qualite}%)")
            else:
                self._lbl_signal.setText(f"Signal: connecté ({qualite}%)")

    def _setup_tray(self):
        """Crée l'icône system tray pour que l'app tourne en fond."""
        icon_path = os.path.join(ASSETS_DIR, "logo.ico")
        icon = QIcon(icon_path) if os.path.exists(icon_path) else QIcon()
        self._tray = QSystemTrayIcon(icon, self)
        tray_menu = QMenu()
        act_show = tray_menu.addAction("Ouvrir Memento Agent")
        act_show.triggered.connect(self._tray_show)
        tray_menu.addSeparator()
        act_quit = tray_menu.addAction("Quitter")
        act_quit.triggered.connect(self._tray_quit)
        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.setToolTip("Memento Agent — Monitoring actif")
        self._tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self._tray_show()

    def _tray_show(self):
        self.showNormal()
        self.activateWindow()

    def _tray_quit(self):
        """Quitter vraiment l'application."""
        self._force_quit = True
        if hasattr(self, '_refresh_timer'):
            self._refresh_timer.stop()
        # Arrêter le monitoring seulement si on quitte vraiment l'app
        if hasattr(self, '_monitor') and self._monitor and not self._existing_monitor:
            # Monitoring créé par le dashboard (fallback) → on peut l'arrêter
            if self._monitor.isRunning():
                self._monitor.stop()
                self._monitor.wait(3000)
        if hasattr(self, '_tray'):
            self._tray.hide()
        QApplication.instance().quit()

    def _auto_refresh(self):
        """Rafraîchit les données Supabase automatiquement."""
        try:
            self._fetch_supabase_data()
        except Exception:
            pass

    def _manual_refresh(self):
        """Rafraîchissement manuel (bouton refresh)."""
        from ui_components import toast
        toast("Rafraîchissement...")
        self._fetch_supabase_data()

    def closeEvent(self, event):
        """Minimise dans le tray au lieu de quitter — le monitoring continue."""
        if getattr(self, '_force_quit', False):
            super().closeEvent(event)
            return
        event.ignore()
        self.hide()
        if hasattr(self, '_tray'):
            self._tray.showMessage(
                "Memento Agent",
                "L'application continue en arrière-plan.",
                QSystemTrayIcon.Information,
                2000,
            )

    def _fetch_supabase_data(self):
        """Charge borne + heartbeat + alertes depuis Supabase en arrière-plan."""
        # Ne pas lancer si un worker tourne déjà
        if hasattr(self, '_data_worker') and self._data_worker and self._data_worker.isRunning():
            return
        self._data_worker = _SupabaseWorker(self)
        self._data_worker.done.connect(self._on_data_loaded)
        self._data_worker.start()

    def _on_data_loaded(self, data):
        """Met à jour tous les widgets avec les données Supabase."""
        if not data:
            return
        try:
            self._apply_data(data)
        except Exception as e:
            print(f"[DASHBOARD] _on_data_loaded error: {e}")

    def _apply_data(self, data):

        # Profile card + collapsed profile
        borne = data.get("borne")
        if borne:
            self._borne_id_cache = borne.get("id")
            nom = borne.get("nom_lieu") or "—"
            code = borne.get("code") or "—"
            for card in self.findChildren(ProfileCard):
                card.set_borne_info(nom, code)
            for cp in self.findChildren(CollapsedProfile):
                cp.set_borne_info(nom)

        # Logo : Supabase d'abord, sinon fichier local
        logo_bytes = data.get("logo_bytes")
        pm = None
        if logo_bytes:
            pm = QPixmap()
            pm.loadFromData(logo_bytes)
            if pm.isNull():
                pm = None
        if not pm:
            local_dir = os.path.join(os.path.expanduser("~"), ".mementoagent")
            for ext in ("png", "jpg", "jpeg", "svg"):
                p = os.path.join(local_dir, f"logo.{ext}")
                if os.path.exists(p):
                    pm = QPixmap(p)
                    if pm.isNull():
                        pm = None
                    break
        if pm:
            for card in self.findChildren(ProfileCard):
                card._logo = pm.scaled(50, 50, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                card.update()
            for cp in self.findChildren(CollapsedProfile):
                cp._logo = pm.scaled(40, 40, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                cp.update()

        # Heartbeat → papier, wifi
        hb = data.get("heartbeat")
        if hb:
            feuilles = hb.get("feuilles_restantes")
            if feuilles is not None:
                total = 400  # capacité standard DNP DS620
                self._donut.value = feuilles
                self._donut.total = total
                self._donut.update()
                pct = int((1 - feuilles / total) * 100) if total > 0 else 0
                self._lbl_pct.setText(f"{pct} % utilisés")

            ssid = hb.get("ssid_wifi")
            if ssid:
                self._lbl_wifi_name.setText(ssid)
                self._wifi_bar.strength = 80
                self._wifi_bar.update()
                self._lbl_signal.setText("Signal: bon")

        # Fallback WiFi local si pas de heartbeat ou ssid absent
        if not (hb and hb.get("ssid_wifi")):
            try:
                from monitoring.collectors.system import lire_wifi
                ssid_local = lire_wifi()
                if ssid_local:
                    self._lbl_wifi_name.setText(ssid_local)
                    self._wifi_bar.strength = 80
                    self._wifi_bar.update()
                    self._lbl_signal.setText("Signal: bon")
            except Exception:
                pass

        # CA du jour → revenue card + bar chart
        ca = data.get("ca")
        if ca:
            self._lbl_revenue.setText(f"{ca['montant']:.0f} €")

        ca_week = data.get("ca_week")
        if ca_week:
            max_ca = max(ca_week) if max(ca_week) > 0 else 1
            self._bar_chart.bars = [v / max_ca for v in ca_week]
            self._bar_chart.update()
            # Badge : total semaine
            total_semaine = sum(ca_week)
            self._revenue_badge.setText(f"{total_semaine:.0f} € cette semaine")

        # Alertes → table d'erreurs
        alertes = data.get("alertes")
        if alertes and hasattr(self, '_table'):
            new_rows = []
            from alertes.data import TYPE_TO_ICON
            type_to_svg = TYPE_TO_ICON
            for a in alertes[:16]:
                svg = type_to_svg.get(a.get("type", ""), "icon_borne_hors_ligne.svg")
                ts = _utc_to_local(a.get("timestamp", ""))
                source = a.get("source", "—")
                assignee = a.get("assignee_a") or "—"
                statut = a.get("statut", "ouverte")
                _rp = a.get("resolue_par", "") if statut == "resolue" else ""
                resolue_par = "Agent" if _rp else "—"
                resolu = "oui" if statut == "resolue" else "N/A"
                alerte_id = a.get("id", "")
                message = a.get("message", "")
                new_rows.append((a.get("type", "—"), svg, ts, source, assignee, resolu, alerte_id, message, statut, resolue_par))

            if new_rows:
                self._table.rows = new_rows
                # Charger les icônes Figma — blanc si résolu
                from PyQt5.QtSvg import QSvgRenderer
                def _load_alert_icon(fname, sz=32, resolved=False):
                    p2 = os.path.join(ASSETS_DIR, fname)
                    if not os.path.exists(p2):
                        pm = QPixmap(sz, sz); pm.fill(Qt.transparent); return pm
                    with open(p2, "r") as ff:
                        raw = ff.read()
                    if resolved:
                        # Cercle rouge → vert, icône blanche → noire
                        raw = raw.replace('#EF4444', '#22C55E').replace('#ef4444', '#22C55E')
                        raw = raw.replace('#F59E0B', '#22C55E').replace('#f59e0b', '#22C55E')
                        raw = raw.replace('stroke="white"', 'stroke="black"')
                        raw = raw.replace('fill="white"', 'fill="black"')
                    rdr = QSvgRenderer(QByteArray(raw.encode()))
                    sc = 2; pm = QPixmap(sz * sc, sz * sc); pm.fill(Qt.transparent)
                    pp = QPainter(pm); rdr.render(pp); pp.end()
                    pm.setDevicePixelRatio(sc)
                    return pm
                self._table._icons = [_load_alert_icon(r[1], 32, r[8] == "resolue" if len(r) > 8 else False) for r in new_rows]
                h = self._table._header_h + len(new_rows) * self._table._row_h
                self._table.setFixedHeight(h)
                self._table.update()

    def _toggle_theme(self):
        global _current_theme
        _current_theme = DARK_THEME if _current_theme is LIGHT_THEME else LIGHT_THEME
        self._apply_theme()

    def _apply_theme(self):
        t = T()
        bg = t["content_bg"]
        tc = t["text"]
        icon_c = t["toolbar_icon"]

        # Fond global
        self._content.setStyleSheet(f"background-color: {bg};")
        self._inner.setStyleSheet(f"background: {bg};")
        self._toolbar.setStyleSheet(f"background-color: {bg};")
        self._sep.setStyleSheet(f"background-color: {t['table_border']}; border: none;")
        self._apply_scroll_style()

        # Sidebar — adapter au thème
        sidebar_bg = bg
        sidebar_border = t["table_border"]
        self.sidebar.setStyleSheet(f"background-color: {sidebar_bg}; border-right: 1px solid {sidebar_border};")

        # Icônes toolbar
        self._moon_btn.setIcon(QIcon(load_svg("icon_moon.svg", 24, icon_c)))
        self._refresh_btn.setIcon(QIcon(load_svg("icon_refresh.svg", 24, icon_c)))

        # Labels cartes
        for lbl in (self._lbl_papier, self._lbl_pct, self._lbl_wifi_title,
                     self._lbl_wifi_name, self._lbl_signal):
            ss = lbl.styleSheet()
            ss = re.sub(r'color:\s*#[0-9A-Fa-f]+', f'color: {tc}', ss)
            lbl.setStyleSheet(ss)

        # Repaint tous les widgets peints
        for w in (self._card_papier, self._card_wifi, self._donut, self._table):
            w.update()

        # Sauvegarder l'index courant avant de reconstruire
        idx_current = self._stacked.currentIndex()

        # Reconstruire page alertes pour le nouveau thème
        from alertes import AlertesWidget
        self._stacked.removeWidget(self._page_alertes)
        self._page_alertes.deleteLater()
        self._page_alertes = AlertesWidget()
        self._stacked.insertWidget(1, self._page_alertes)

        # Reconstruire page TPE pour le nouveau thème
        from TPE import TPEWidget
        self._stacked.removeWidget(self._page_tpe)
        self._page_tpe.deleteLater()
        self._page_tpe = TPEWidget()
        self._stacked.insertWidget(2, self._page_tpe)

        # Reconstruire la page paramètres pour le nouveau thème
        if self._settings_widget is not None:
            from settings import SettingsWidget
            self._stacked.removeWidget(self._settings_widget)
            self._settings_widget.deleteLater()
            self._settings_widget = SettingsWidget()
            self._stacked.insertWidget(3, self._settings_widget)

        # Restaurer la page active
        self._stacked.setCurrentIndex(idx_current)

    def _toggle_sidebar(self):
        self._sidebar_expanded = not self._sidebar_expanded
        if self._sidebar_expanded:
            # Sync active index from collapsed → expanded
            idx = self._collapsed_pill._active_index
            for i, nav in enumerate(self._nav_items):
                nav.set_active(i == idx)
            self.sidebar.setFixedWidth(220)
            self.sidebar.setStyleSheet("background-color: #FFFFFF; border-right: 1px solid #E2E8F0;")
            self._sidebar_title.show()
            self._nav_expanded.show()
            self._nav_collapsed.hide()
            self._profile_expanded.show()
            self._profile_collapsed.hide()
        else:
            # Sync active index from expanded → collapsed
            for i, nav in enumerate(self._nav_items):
                if nav._active:
                    self._collapsed_pill.set_active(i)
                    break
            self.sidebar.setFixedWidth(80)
            self.sidebar.setStyleSheet("background-color: #FFFFFF; border-right: 1px solid #E2E8F0;")
            self._sidebar_title.hide()
            self._nav_expanded.hide()
            self._nav_collapsed.show()
            self._profile_expanded.hide()
            self._profile_collapsed.show()

    # ─── Sidebar ────────────────────────────────────
    def _build_sidebar(self):
        sidebar = QWidget()
        sidebar.setFixedWidth(220)
        sidebar.setStyleSheet("background-color: #FFFFFF; border-right: 1px solid #E2E8F0;")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Logo + titre
        header = QWidget()
        header.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 10, 12, 10)
        hl.setSpacing(8)

        logo = QLabel()
        logo_path = os.path.join(ASSETS_DIR, "logo.png")
        if os.path.exists(logo_path):
            logo.setPixmap(QPixmap(logo_path).scaled(36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        logo.setStyleSheet("background: transparent;")
        hl.addWidget(logo)

        self._sidebar_title = QLabel("Memento Agent")
        self._sidebar_title.setStyleSheet("color: #0F172A; font-family: 'Satoshi'; font-size: 15px; font-weight: 700; background: transparent;")
        hl.addWidget(self._sidebar_title)
        hl.addStretch()
        layout.addWidget(header)

        # Séparateur
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        sep.setStyleSheet("background-color: #E2E8F0; border: none;")
        layout.addWidget(sep)
        layout.addSpacing(8)

        # ── Navigation étendue (mode expanded) ──
        self._nav_expanded = QWidget()
        self._nav_expanded.setStyleSheet("background: transparent;")
        nl = QVBoxLayout(self._nav_expanded)
        nl.setContentsMargins(8, 0, 8, 0)
        nl.setSpacing(4)
        self._nav_items = [
            NavItem("icon_grid.svg", "Dashboard", active=True),
            NavItem("icon_activity.svg", "Alertes"),
            NavItem("icon_dollar.svg", "TPE"),
            NavItem("icon_settings.svg", "Paramètre"),
        ]
        for item in self._nav_items:
            nl.addWidget(item)
        layout.addWidget(self._nav_expanded)

        # ── Navigation repliée (mode collapsed) ──
        self._nav_collapsed = QWidget()
        self._nav_collapsed.setStyleSheet("background: transparent;")
        nc_layout = QHBoxLayout(self._nav_collapsed)
        nc_layout.setContentsMargins(12, 0, 12, 0)
        self._collapsed_pill = CollapsedNavPill()
        nc_layout.addWidget(self._collapsed_pill, 0, Qt.AlignCenter)
        self._nav_collapsed.hide()
        layout.addWidget(self._nav_collapsed)

        layout.addStretch(1)

        # ── Profil étendu (mode expanded) ──
        self._profile_expanded = QWidget()
        self._profile_expanded.setStyleSheet("background: transparent;")
        pw_layout = QHBoxLayout(self._profile_expanded)
        pw_layout.setContentsMargins(17, 0, 17, 17)
        pw_layout.addWidget(ProfileCard())
        layout.addWidget(self._profile_expanded)

        # ── Profil replié (mode collapsed) ──
        self._profile_collapsed = QWidget()
        self._profile_collapsed.setStyleSheet("background: transparent;")
        pc_layout = QHBoxLayout(self._profile_collapsed)
        pc_layout.setContentsMargins(12, 0, 12, 17)
        pc_layout.addWidget(CollapsedProfile(), 0, Qt.AlignCenter)
        self._profile_collapsed.hide()
        layout.addWidget(self._profile_collapsed)

        return sidebar

    def _switch_page(self, index):
        """Basculer entre les pages du stacked widget."""
        # Lazy-load des Paramètres au premier accès
        if index == 3 and self._settings_widget is None:
            from settings import SettingsWidget
            self._settings_widget = SettingsWidget()
            self._stacked.removeWidget(self._settings_placeholder)
            self._settings_placeholder.deleteLater()
            self._stacked.insertWidget(3, self._settings_widget)
        self._stacked.setCurrentIndex(index)

    # ─── Contenu principal ──────────────────────────
    def _build_content(self):
        self._content = QWidget()
        self._content.setStyleSheet(f"background-color: {T()['content_bg']};")

        vl = QVBoxLayout(self._content)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        self._toolbar = self._build_toolbar()
        vl.addWidget(self._toolbar)

        self._sep = QFrame()
        self._sep.setFrameShape(QFrame.HLine)
        self._sep.setFixedHeight(1)
        self._sep.setStyleSheet(f"background-color: {T()['table_border']}; border: none;")
        vl.addWidget(self._sep)

        # ── Stacked Widget pour navigation entre pages ──
        self._stacked = QStackedWidget()
        self._stacked.setStyleSheet("background: transparent; border: none;")

        # Page 0 : Dashboard
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._apply_scroll_style()
        from touch_scroll import enable_touch_scroll
        enable_touch_scroll(self._scroll)

        self._inner = QWidget()
        self._inner.setStyleSheet(f"background: {T()['content_bg']};")
        il = QVBoxLayout(self._inner)
        il.setContentsMargins(20, 12, 20, 20)
        il.setSpacing(12)

        il.addLayout(self._build_cards_section())
        self._table = ErrorTableWidget()
        il.addWidget(self._table)
        il.addStretch()

        self._scroll.setWidget(self._inner)
        self._stacked.addWidget(self._scroll)  # index 0

        # Page 1 : Alertes
        from alertes import AlertesWidget
        self._page_alertes = AlertesWidget()
        self._stacked.addWidget(self._page_alertes)  # index 1

        # Page 2 : TPE
        from TPE import TPEWidget
        self._page_tpe = TPEWidget()
        self._stacked.addWidget(self._page_tpe)  # index 2

        # Page 3 : Paramètres (chargement lazy pour éviter crash au démarrage)
        self._settings_widget = None
        self._settings_placeholder = self._build_placeholder("Paramètres", "Chargement...")
        self._stacked.addWidget(self._settings_placeholder)  # index 3

        vl.addWidget(self._stacked)

        return self._content

    def _build_placeholder(self, title, subtitle):
        """Page placeholder pour les onglets pas encore implémentés."""
        page = QWidget()
        page.setStyleSheet(f"background: {T()['content_bg']};")
        vl = QVBoxLayout(page)
        vl.setContentsMargins(28, 40, 28, 28)
        vl.setSpacing(8)
        lbl_t = QLabel(title)
        lbl_t.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 22px; font-weight: 700; background: transparent;")
        vl.addWidget(lbl_t)
        lbl_s = QLabel(subtitle)
        lbl_s.setStyleSheet(f"color: #333333; font-family: 'Satoshi'; font-size: 14px; background: transparent;")
        vl.addWidget(lbl_s)
        vl.addStretch()
        return page

    def _apply_scroll_style(self):
        bg = T()["content_bg"]
        handle = T()["scroll_handle"]
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: {bg}; }}
            QScrollBar:vertical {{ width: 6px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {handle}; border-radius: 3px; min-height: 30px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    # ─── Barre d'outils ────────────────────────────
    def _build_toolbar(self):
        bar = QWidget()
        bar.setFixedHeight(38)
        bar.setStyleSheet(f"background-color: {T()["content_bg"]};")
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(8, 6, 16, 6)
        hl.setSpacing(16)

        t_btn = QPushButton()
        t_btn.setIcon(QIcon(load_svg("icon_table.svg", 24, TEXT_BLACK)))
        t_btn.setFixedSize(28, 28)
        t_btn.setCursor(Qt.PointingHandCursor)
        t_btn.setStyleSheet("border: none; background: transparent;")
        t_btn.clicked.connect(self._toggle_sidebar)
        hl.addWidget(t_btn)
        hl.addStretch()

        self._moon_btn = QPushButton()
        self._moon_btn.setIcon(QIcon(load_svg("icon_moon.svg", 24, "#111111")))
        self._moon_btn.setFixedSize(28, 28)
        self._moon_btn.setCursor(Qt.PointingHandCursor)
        self._moon_btn.setStyleSheet("border: none; background: transparent;")
        self._moon_btn.clicked.connect(self._toggle_theme)
        hl.addWidget(self._moon_btn)

        self._refresh_btn = QPushButton()
        self._refresh_btn.setIcon(QIcon(load_svg("icon_refresh.svg", 24, "#111111")))
        self._refresh_btn.setFixedSize(28, 28)
        self._refresh_btn.setCursor(Qt.PointingHandCursor)
        self._refresh_btn.setStyleSheet("border: none; background: transparent;")
        self._refresh_btn.clicked.connect(self._manual_refresh)
        hl.addWidget(self._refresh_btn)
        return bar

    # ─── Section cartes (Papier+Wifi à gauche, Revenus à droite) ───
    def _build_cards_section(self):
        row = QHBoxLayout()
        row.setSpacing(12)

        # Colonne gauche : Papier restant + Wifi empilés
        left_col = QVBoxLayout()
        left_col.setSpacing(12)

        # Papier restant
        self._card_papier = BorderedCard(radius=20)
        self._card_papier.setMinimumSize(200, 134)
        self._card_papier.setMaximumHeight(134)
        pl = QHBoxLayout(self._card_papier)
        pl.setContentsMargins(16, 12, 16, 12)
        pl.setSpacing(12)
        self._donut = DonutChart(0, 400)
        pl.addWidget(self._donut)

        txt = QVBoxLayout()
        txt.setSpacing(8)
        txt.addStretch()
        self._lbl_papier = QLabel("Papier restant")
        self._lbl_papier.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 14px; font-weight: 600; background: transparent;")
        txt.addWidget(self._lbl_papier)
        self._lbl_pct = QLabel("— % utilisés")
        self._lbl_pct.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 10px; background: transparent;")
        txt.addWidget(self._lbl_pct)
        txt.addStretch()
        pl.addLayout(txt)
        left_col.addWidget(self._card_papier)

        # Wifi
        self._card_wifi = BorderedCard(radius=20)
        self._card_wifi.setMinimumSize(200, 134)
        self._card_wifi.setMaximumHeight(134)
        cl = QVBoxLayout(self._card_wifi)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(6)
        self._lbl_wifi_title = QLabel("Wifi")
        self._lbl_wifi_title.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 11px; background: transparent;")
        cl.addWidget(self._lbl_wifi_title)
        self._lbl_wifi_name = QLabel("—")
        self._lbl_wifi_name.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 14px; font-weight: 600; background: transparent;")
        cl.addWidget(self._lbl_wifi_name)
        cl.addStretch()
        self._wifi_bar = WifiBar(0)
        cl.addWidget(self._wifi_bar)
        cl.addSpacing(4)

        self._lbl_signal = QLabel("Signal: —")
        self._lbl_signal.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 11px; background: transparent;")
        cl.addWidget(self._lbl_signal)
        left_col.addWidget(self._card_wifi)
        left_col.addStretch()

        row.addLayout(left_col)

        # Colonne droite : Revenus (toujours sombre)
        rev = QWidget()
        rev.setFixedHeight(280)
        rev.setStyleSheet(f"background-color: {REVENUE_BG}; border-radius: 20px;")

        rl = QVBoxLayout(rev)
        rl.setContentsMargins(26, 18, 26, 10)
        rl.setSpacing(2)

        lbl = QLabel("Revenus")
        lbl.setStyleSheet(f"color: {TEXT_MUTED}; font-family: 'Satoshi'; font-size: 12px; background: transparent;")
        rl.addWidget(lbl)
        rl.addSpacing(8)

        ar = QHBoxLayout()
        ar.setSpacing(20)
        self._lbl_revenue = QLabel("— €")
        self._lbl_revenue.setStyleSheet(f"color: {TEXT_WHITE}; font-family: 'Satoshi'; font-size: 26px; font-weight: 800; background: transparent;")
        ar.addWidget(self._lbl_revenue)

        self._revenue_badge = QLabel("—")
        self._revenue_badge.setStyleSheet(f"background-color: {YELLOW_BADGE}; color: {TEXT_BLACK}; font-family: 'Satoshi'; font-size: 11px; border-radius: 10px; padding: 8px 10px;")
        ar.addWidget(self._revenue_badge)
        ar.addStretch()
        rl.addLayout(ar)
        rl.addSpacing(8)
        self._bar_chart = BarChart()
        rl.addWidget(self._bar_chart)

        row.addWidget(rev, 1, Qt.AlignTop)
        self._rev_widget = rev
        # Cacher le CA si l'utilisateur n'a pas le droit
        import user_session
        if not user_session.can_see_ca():
            rev.hide()
            # Retirer les cartes de la colonne verticale
            while left_col.count():
                left_col.takeAt(0)
            # Les remettre dans le row principal côte à côte
            self._card_papier.setFixedHeight(130)
            self._card_wifi.setFixedHeight(130)
            self._card_papier.setMinimumSize(0, 130)
            self._card_wifi.setMinimumSize(0, 130)
            row.addWidget(self._card_papier, 1)
            row.addWidget(self._card_wifi, 1)
            self._card_papier.setFixedHeight(130)
            self._card_wifi.setFixedHeight(130)

        # HoverCards sur les cartes
        def _papier_hover(layout):
            from ui_components import _hc_title, _hc_value, _hc_sub
            layout.addWidget(_hc_title("Papier restant"))
            layout.addWidget(_hc_value(f"{self._donut.value} feuilles"))
            total = self._donut.total or 400
            pct = int(self._donut.value / total * 100) if total > 0 else 0
            layout.addWidget(_hc_sub(f"Capacité : {total} · {pct}% restant"))

        def _wifi_hover(layout):
            from ui_components import _hc_title, _hc_value, _hc_sub
            layout.addWidget(_hc_title("Connexion WiFi"))
            layout.addWidget(_hc_value(self._lbl_wifi_name.text()))
            layout.addWidget(_hc_sub(self._lbl_signal.text()))

        self._card_papier.set_hover(_papier_hover)
        self._card_wifi.set_hover(_wifi_hover)

        return row


if __name__ == "__main__":
    app = QApplication(sys.argv)

    QFontDatabase.addApplicationFont(os.path.join(ASSETS_DIR, "Inter-Regular.ttf"))
    QFontDatabase.addApplicationFont(os.path.join(ASSETS_DIR, "Inter-SemiBold.ttf"))

    window = DashboardWindow()
    window.show()
    sys.exit(app.exec_())
