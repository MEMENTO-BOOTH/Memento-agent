"""AlertesWidget — page complète des alertes, branchée à Supabase."""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from dashboard import T, LIME_GREEN, TEXT_BLACK
import supabase_client as supa

from .stat_cards import AlerteStatCard
from .filter_bar import FilterButton
from .table import AlerteTable
from .stats import compute_stats
from .filters import filter_alertes
from .data import fetch_alertes


class _Worker(QThread):
    finished = pyqtSignal(object)
    def __init__(self, func, *args):
        super().__init__()
        self._f, self._a = func, args
    def run(self):
        try:
            self.finished.emit(self._f(*self._a))
        except Exception:
            self.finished.emit(None)


class AlertesWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers = []
        self._borne_id = None
        self._all_alertes = []
        self._current_filter = None  # None = toutes
        self._build()
        self._fetch_borne()

        # Auto-refresh toutes les 30 secondes
        from PyQt5.QtCore import QTimer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh)
        self._refresh_timer.start(300_000)  # 5 minutes

    def _auto_refresh(self):
        if self._borne_id:
            self._fetch_alertes()

    def _run(self, func, cb, *args):
        w = _Worker(func, *args)
        w.finished.connect(cb)
        self._workers.append(w)
        w.start()

    # ═══════════════════════════════════════════════
    #  BUILD UI
    # ═══════════════════════════════════════════════

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

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
        vl.setContentsMargins(24, 16, 24, 24)
        vl.setSpacing(14)

        # Titre + badge
        title_row = QHBoxLayout()
        title_lbl = QLabel("Alertes")
        title_lbl.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 22px; font-weight: 700; background: transparent;")
        title_row.addWidget(title_lbl)
        title_row.addStretch()

        self._badge_count = QLabel("  — alertes  ")
        self._badge_count.setFixedHeight(22)
        self._badge_count.setStyleSheet(f"background-color: #FEE2E2; color: #EF4444; font-family: 'Satoshi'; font-size: 10px; font-weight: 600; border: 1px solid #EF4444; border-radius: 11px; padding: 2px 10px;")
        title_row.addWidget(self._badge_count)
        vl.addLayout(title_row)

        # Cartes stats style shadcn
        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        self._card_critiques = AlerteStatCard("Critiques", "—", "#EF4444", "icon_stat_critique.svg")
        self._card_warnings = AlerteStatCard("Avertissements", "—", "#F59E0B", "icon_stat_warning.svg")
        self._card_ouvertes = AlerteStatCard("Ouvertes", "—", "#3B82F6", "icon_stat_ouvertes.svg")
        self._card_resolues = AlerteStatCard("Résolues", "—", "#22C55E", "icon_stat_resolues.svg")
        for c in (self._card_critiques, self._card_warnings, self._card_ouvertes, self._card_resolues):
            stats_row.addWidget(c)
        vl.addLayout(stats_row)

        # Filtres
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        self._filters = []
        for label, key in [("Toutes", None), ("Critiques", "critique"), ("Warnings", "warning"), ("Info", "info")]:
            btn = FilterButton(label, active=(key is None), on_click=lambda k=key: self._apply_filter(k))
            self._filters.append((key, btn))
            filter_row.addWidget(btn)

        filter_row.addStretch()
        vl.addLayout(filter_row)

        # Table alertes
        self._table = AlerteTable(on_refresh=self._refresh)
        vl.addWidget(self._table)

        # Tableau d'activité (logs + alertes)
        vl.addSpacing(12)
        from .activity_table import ActivityTable
        self._activity = ActivityTable()
        vl.addWidget(self._activity)

        vl.addStretch()

        scroll.setWidget(inner)
        outer.addWidget(scroll)

    # ═══════════════════════════════════════════════
    #  FETCH SUPABASE
    # ═══════════════════════════════════════════════

    def _fetch_borne(self):
        self._run(supa.get_borne, self._on_borne)

    def _on_borne(self, data):
        if not data:
            return
        self._borne_id = data["id"]
        self._fetch_alertes()

    def _fetch_alertes(self):
        if self._borne_id:
            self._run(fetch_alertes, self._on_alertes, self._borne_id)

    def _on_alertes(self, data):
        if data is None:
            data = []
        self._all_alertes = data
        self._update_stats()
        self._apply_filter(self._current_filter)

    def _refresh(self):
        self._update_stats()

    # ═══════════════════════════════════════════════
    #  STATS + FILTRES
    # ═══════════════════════════════════════════════

    def _update_stats(self):
        s = compute_stats(self._all_alertes)
        self._badge_count.setText(f"  {s['total']} alertes  ")
        self._card_critiques.set_data(s["critiques"], badge_text="Alertes critiques")
        self._card_warnings.set_data(s["warnings"], badge_text="Avertissements")
        self._card_ouvertes.set_data(s["ouvertes"], badge_text="Non résolues")
        self._card_resolues.set_data(s["resolues"], badge_text="Résolues auto")

        # Mettre à jour les compteurs sur les filtres
        counts = {
            None: s["total"],
            "critique": s["critiques"],
            "warning": s["warnings"],
            "info": s["total"] - s["critiques"] - s["warnings"],
        }
        for key, btn in self._filters:
            btn.set_count(counts.get(key, 0))

    def _apply_filter(self, gravite):
        self._current_filter = gravite
        # Activer le bon bouton
        for key, btn in self._filters:
            btn.set_active(key == gravite)

        # Filtrer et afficher
        filtered = filter_alertes(self._all_alertes, gravite=gravite)
        self._table.set_alertes(filtered)
