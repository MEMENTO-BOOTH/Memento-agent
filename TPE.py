"""
Page TPE — Terminal de Paiement
Design shadcn Total Transaction Card
"""

import os
from datetime import date, timedelta
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame,
)
from PyQt5.QtCore import Qt, QRect, QRectF, QThread, pyqtSignal
from PyQt5.QtGui import QPainter, QColor, QPen, QPainterPath, QFont, QPixmap

from dashboard import T, TEXT_BLACK, TEXT_WHITE, LIME_GREEN, ASSETS_DIR
import supabase_client as supa


class _FetchWorker(QThread):
    finished = pyqtSignal(object)
    def __init__(self, func, *args):
        super().__init__()
        self._f, self._a = func, args
    def run(self):
        try:
            self.finished.emit(self._f(*self._a))
        except Exception:
            self.finished.emit(None)


# ════════════════════════════════════════════════════
#  BAR CHART — barres arrondies style shadcn
# ════════════════════════════════════════════════════

class _WeekBarChart(QWidget):
    """Bar chart hebdomadaire style shadcn — barres arrondies avec labels, cliquables."""
    bar_clicked = pyqtSignal(int)  # émet l'index du jour cliqué (0=Lun, 6=Dim)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(220)
        self._data = []
        self._highlight = -1
        self.setCursor(Qt.PointingHandCursor)

    def set_data(self, data, highlight=-1):
        self._data = data
        self._highlight = highlight
        self.update()

    def _bar_rects(self):
        """Calcule les rectangles de chaque barre."""
        if not self._data:
            return []
        w = self.width()
        h = self.height()
        n = len(self._data)
        bar_w = min(40, (w - 60) // n - 12)
        spacing = (w - n * bar_w) / (n + 1)
        chart_bot = h - 28
        rects = []
        for i in range(n):
            x = spacing + i * (bar_w + spacing)
            rects.append(QRectF(x - 5, 0, bar_w + 10, chart_bot + 24))
        return rects

    def mousePressEvent(self, event):
        rects = self._bar_rects()
        for i, rect in enumerate(rects):
            if rect.contains(event.pos()):
                self._highlight = i
                self.update()
                self.bar_clicked.emit(i)
                return

    def paintEvent(self, event):
        if not self._data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        n = len(self._data)
        max_val = max((v for _, v in self._data), default=1) or 1
        bar_w = min(40, (w - 60) // n - 12)
        spacing = (w - n * bar_w) / (n + 1)
        chart_top = 30
        chart_bot = h - 28
        chart_h = chart_bot - chart_top

        for i, (label, val) in enumerate(self._data):
            x = spacing + i * (bar_w + spacing)
            bar_h = int(val / max_val * chart_h) if max_val > 0 else 0
            bar_h = max(bar_h, 4)
            y = chart_bot - bar_h

            # Barre
            is_highlight = (i == self._highlight)
            color = QColor("#16A34A") if is_highlight else QColor("#16A34A40")
            bar = QPainterPath()
            bar.addRoundedRect(QRectF(x, y, bar_w, bar_h), 8, 8)
            p.fillPath(bar, color)

            # Label valeur au-dessus
            if val > 0:
                font_val = QFont("Satoshi")
                font_val.setPixelSize(13)
                font_val.setWeight(QFont.DemiBold)
                p.setFont(font_val)
                p.setPen(QColor(T()["text"]))
                txt = f"{val / 1000:.0f}K" if val >= 1000 else f"{val:.0f}"
                if val < 1000:
                    txt = f"{val:.0f}€"
                p.drawText(QRect(int(x) - 5, y - 22, bar_w + 10, 20), Qt.AlignCenter, txt)

            # Label jour en bas
            font_lbl = QFont("Satoshi")
            font_lbl.setPixelSize(12)
            p.setFont(font_lbl)
            p.setPen(QColor(T()["text"]))
            p.drawText(QRect(int(x) - 5, chart_bot + 4, bar_w + 10, 20), Qt.AlignCenter, label)

        p.end()


# ════════════════════════════════════════════════════
#  STAT BOX — icône + label + valeur
# ════════════════════════════════════════════════════

def _load_icon(filename, size):
    """Charge un SVG feather en noir."""
    from PyQt5.QtSvg import QSvgRenderer
    from PyQt5.QtCore import QByteArray
    path = os.path.join(ASSETS_DIR, filename)
    if not os.path.exists(path):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        return pm
    with open(path, "r") as f:
        data = f.read()
    data = data.replace('stroke="currentColor"', 'stroke="#0F172A"')
    renderer = QSvgRenderer(QByteArray(data.encode()))
    scale = 2
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    renderer.render(painter)
    painter.end()
    pm.setDevicePixelRatio(scale)
    return pm


class _StatBox(QWidget):
    """Boîte stat sobre — icône noire, texte noir, fond blanc."""
    def __init__(self, icon_file, icon_color, label, value, parent=None):
        super().__init__(parent)
        self.setFixedHeight(110)
        self._icon_file = icon_file
        self._label = label
        self._value = value

    def set_value(self, value):
        self._value = value
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        cx = w // 2

        # Icône carrée arrondie — fond gris clair
        icon_sz = 44
        icon_x = cx - icon_sz // 2
        icon_y = 8
        icon_path = QPainterPath()
        icon_path.addRoundedRect(QRectF(icon_x, icon_y, icon_sz, icon_sz), 8, 8)
        p.fillPath(icon_path, QColor("#F1F5F9"))

        # Icône SVG noire
        icon = _load_icon(self._icon_file, 20)
        if not icon.isNull():
            isz = int(icon.width() / icon.devicePixelRatio())
            p.drawPixmap(icon_x + (icon_sz - isz) // 2, icon_y + (icon_sz - isz) // 2, icon)

        # Label — noir
        font_lbl = QFont("Satoshi")
        font_lbl.setPixelSize(11)
        p.setFont(font_lbl)
        p.setPen(QColor(T()["text"]))
        p.drawText(QRect(0, icon_y + icon_sz + 10, w, 16), Qt.AlignCenter, self._label)

        # Valeur
        font_val = QFont("Satoshi")
        font_val.setPixelSize(20)
        font_val.setWeight(QFont.DemiBold)
        p.setFont(font_val)
        p.setPen(QColor(T()["text"]))
        p.drawText(QRect(0, icon_y + icon_sz + 24, w, 26), Qt.AlignCenter, self._value)

        p.end()


# ════════════════════════════════════════════════════
#  CARD — carte avec bordure arrondie
# ════════════════════════════════════════════════════

class _Card(QWidget):
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 12, 12)
        p.fillPath(path, QColor(T()["card_bg"]))
        p.setPen(QPen(QColor(T()["card_border"]), 1.7))
        p.drawPath(path)
        p.end()


# ════════════════════════════════════════════════════
#  SESSION LOG — ligne de log
# ════════════════════════════════════════════════════

def _separator():
    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background-color: {T()['row_sep']}; border: none;")
    return sep


# ════════════════════════════════════════════════════
#  TPE WIDGET — page principale
# ════════════════════════════════════════════════════

class TPEWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers = []
        self._borne_id = None
        self._selected_date = date.today()
        self._ca_week = [0] * 7
        self._ca_today = 0
        self._tx_count = 0
        self._anomalies = 0
        self._sessions = []
        self._build()
        self._fetch_borne()

        # Auto-refresh toutes les 60 secondes
        from PyQt5.QtCore import QTimer
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._auto_refresh)
        self._refresh_timer.start(300_000)  # 5 minutes

    def _auto_refresh(self):
        if self._borne_id:
            self._fetch_all()

    def _run(self, func, cb, *args):
        w = _FetchWorker(func, *args)
        w.finished.connect(cb)
        self._workers.append(w)
        w.start()

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        from touch_scroll import enable_touch_scroll
        enable_touch_scroll(scroll)
        bg = T()["content_bg"]
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: {bg}; }}
            QScrollBar:vertical {{ width: 6px; background: transparent; }}
            QScrollBar::handle:vertical {{ background: {T()['scroll_handle']}; border-radius: 3px; min-height: 30px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        inner = QWidget()
        inner.setStyleSheet(f"background: {bg};")
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(28, 20, 28, 28)
        vl.setSpacing(16)

        # Titre
        title = QLabel("Terminal de Paiement")
        title.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 22px; font-weight: 700; background: transparent;")
        vl.addWidget(title)

        sub = QLabel("Aperçu hebdomadaire des transactions")
        sub.setStyleSheet(f"color: #0F172A; font-family: 'Satoshi'; font-size: 13px; background: transparent;")
        vl.addWidget(sub)
        vl.addSpacing(4)

        # ── Carte principale (2 colonnes) ──
        main_card = _Card()
        main_layout = QHBoxLayout(main_card)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Colonne gauche : bar chart
        left = QWidget()
        left.setStyleSheet("background: transparent;")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(24, 20, 24, 20)
        left_layout.setSpacing(8)

        chart_title = QLabel("Total Transactions")
        chart_title.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 16px; font-weight: 600; background: transparent;")
        left_layout.addWidget(chart_title)

        chart_sub = QLabel("Aperçu de la semaine")
        chart_sub.setStyleSheet(f"color: #0F172A; font-family: 'Satoshi'; font-size: 12px; background: transparent;")
        left_layout.addWidget(chart_sub)
        left_layout.addSpacing(8)

        self._bar_chart = _WeekBarChart()
        self._bar_chart.bar_clicked.connect(self._on_bar_clicked)
        left_layout.addWidget(self._bar_chart)

        main_layout.addWidget(left, 3)

        # Séparateur vertical
        vsep = QFrame()
        vsep.setFrameShape(QFrame.VLine)
        vsep.setFixedWidth(1)
        vsep.setStyleSheet(f"background-color: {T()['card_border']}; border: none;")
        main_layout.addWidget(vsep)

        # Colonne droite : rapport
        right = QWidget()
        right.setStyleSheet("background: transparent;")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(24, 20, 24, 20)
        right_layout.setSpacing(12)

        report_title = QLabel("Rapport")
        report_title.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 16px; font-weight: 600; background: transparent;")
        right_layout.addWidget(report_title)

        self._lbl_last_month = QLabel("Transactions du mois : —")
        self._lbl_last_month.setStyleSheet(f"color: #0F172A; font-family: 'Satoshi'; font-size: 12px; background: transparent;")
        right_layout.addWidget(self._lbl_last_month)
        right_layout.addSpacing(8)

        # Deux stat boxes côte à côte
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)

        self._stat_ca = _StatBox("icon_stat_euro.svg", "#16A34A", "Cette semaine", "—")
        self._stat_anomalies = _StatBox("icon_stat_anomalie.svg", "#F59E0B", "Anomalies", "0")
        stats_row.addWidget(self._stat_ca)

        # Séparateur
        stat_sep = QFrame()
        stat_sep.setFrameShape(QFrame.VLine)
        stat_sep.setFixedWidth(1)
        stat_sep.setStyleSheet(f"background-color: {T()['card_border']}; border: none;")
        stats_row.addWidget(stat_sep)

        stats_row.addWidget(self._stat_anomalies)
        right_layout.addLayout(stats_row)
        right_layout.addStretch()

        # Séparateur + footer
        right_layout.addWidget(_separator())

        footer = QHBoxLayout()
        footer.setSpacing(12)

        perf_col = QVBoxLayout()
        perf_col.setSpacing(2)
        perf_lbl = QLabel("Transactions")
        perf_lbl.setStyleSheet(f"color: #0F172A; font-family: 'Satoshi'; font-size: 11px; background: transparent;")
        perf_col.addWidget(perf_lbl)
        self._lbl_tx_count = QLabel("—")
        self._lbl_tx_count.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 18px; font-weight: 600; background: transparent;")
        perf_col.addWidget(self._lbl_tx_count)
        footer.addLayout(perf_col)
        footer.addStretch()

        right_layout.addLayout(footer)

        main_layout.addWidget(right, 2)
        vl.addWidget(main_card)
        self._main_card = main_card
        # Cacher le CA si l'utilisateur n'a pas le droit
        import user_session
        if not user_session.can_see_ca():
            main_card.hide()

        # ── Navigation jours (si pas de CA, le bar chart est caché) ──
        import user_session as _us
        if not _us.can_see_ca():
            nav_row = QHBoxLayout()
            nav_row.setSpacing(6)
            jours_nav = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
            for i, j in enumerate(jours_nav):
                btn = QPushButton(j)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setFixedHeight(32)
                is_today = (i == date.today().weekday())
                bg = "#0F172A" if is_today else "#F1F5F9"
                fg = "#FFFFFF" if is_today else "#0F172A"
                btn.setStyleSheet(f"""
                    QPushButton {{
                        background: {bg}; color: {fg}; border: none; border-radius: 6px;
                        padding: 4px 12px; font-family: 'Satoshi'; font-size: 12px; font-weight: 600;
                    }}
                    QPushButton:hover {{ background: #E2E8F0; color: #0F172A; }}
                """)
                btn.clicked.connect(lambda checked, idx=i: self._on_bar_clicked(idx))
                nav_row.addWidget(btn)
            nav_row.addStretch()
            vl.addLayout(nav_row)

        # ── Sessions / Logs ──
        self._logs_title = QLabel("Sessions du jour")
        self._logs_title.setStyleSheet(f"color: {T()['text']}; font-family: 'Satoshi'; font-size: 16px; font-weight: 600; background: transparent;")
        vl.addWidget(self._logs_title)

        self._logs_container = QVBoxLayout()
        self._logs_container.setSpacing(8)
        vl.addLayout(self._logs_container)

        # Placeholder
        lbl_placeholder = QLabel("Aucune transaction pour aujourd'hui")
        lbl_placeholder.setStyleSheet(f"color: #0F172A; font-family: 'Satoshi'; font-size: 13px; background: transparent;")
        self._logs_container.addWidget(lbl_placeholder)

        vl.addStretch()
        scroll.setWidget(inner)
        outer.addWidget(scroll)

    # ─── Fetch data ─────────────────────────────
    def _on_bar_clicked(self, day_index):
        """Quand on clique sur une barre, charger les transactions de ce jour."""
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        clicked_date = monday + timedelta(days=day_index)
        jours = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
        jour_nom = jours[day_index]

        if clicked_date == today:
            self._logs_title.setText("Sessions du jour")
        else:
            self._logs_title.setText(f"Sessions — {jour_nom} {clicked_date.strftime('%d/%m')}")

        if self._borne_id:
            self._run(supa.get_transactions_by_date, self._on_today, self._borne_id, clicked_date)

    def _fetch_borne(self):
        self._run(supa.get_borne, self._on_borne)

    def _on_borne(self, data):
        if data:
            self._borne_id = data["id"]
            self._fetch_all()

    def _fetch_all(self):
        if not self._borne_id:
            return
        # Transactions du jour
        self._run(supa.get_transactions_today, self._on_today, self._borne_id)
        # CA par jour de la semaine
        self._run(self._fetch_week_data, self._on_week_data, self._borne_id)

    @staticmethod
    def _fetch_week_data(borne_id):
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        week_data = []
        total_anomalies = 0
        total_montant = 0
        total_tx = 0
        for d in range(7):
            day = monday + timedelta(days=d)
            tx = supa.get_transactions_by_date(borne_id, day)
            stats = supa.get_ca_stats(tx)
            week_data.append(stats["montant"])
            total_anomalies += stats["anomalies"]
            total_montant += stats["montant"]
            total_tx += stats["total"]
        return {
            "week": week_data,
            "anomalies": total_anomalies,
            "montant": total_montant,
            "tx_count": total_tx,
        }

    def _on_week_data(self, data):
        if not data:
            return
        jours = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
        today_idx = date.today().weekday()
        chart_data = [(jours[i], data["week"][i]) for i in range(7)]
        self._bar_chart.set_data(chart_data, highlight=today_idx)

        self._stat_ca.set_value(f"{data['montant']:.0f} €")
        self._stat_anomalies.set_value(str(data["anomalies"]))
        self._lbl_tx_count.setText(str(data["tx_count"]))
        self._lbl_last_month.setText(f"Total semaine : {data['montant']:.0f} €")

    def _on_today(self, data):
        # Nettoyer les anciens
        while self._logs_container.count() > 0:
            item = self._logs_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not data:
            lbl = QLabel("Aucune transaction pour aujourd'hui")
            lbl.setStyleSheet(f"color: #0F172A; font-family: 'Satoshi'; font-size: 13px; background: transparent;")
            self._logs_container.addWidget(lbl)
            return

        # Construire le détail chronologique de chaque transaction
        from dashboard import _utc_to_local

        for i, tx in enumerate(data[:10]):
            card = _Card()
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 10, 16, 10)
            cl.setSpacing(2)

            montant = float(tx.get("montant", 0))
            ok = tx.get("impression_declenchee", False)
            flag = tx.get("flag", "")
            resumed = tx.get("tpe_resumed_at")
            paiement = tx.get("paiement_at")
            inhibited = tx.get("tpe_inhibited_at")
            delai = tx.get("delai_avant_inhibited")

            def _add_line(text, bold=False):
                lbl = QLabel(text)
                w = "600" if bold else "400"
                lbl.setStyleSheet(
                    f"color: {T()['text']}; font-family: 'Satoshi'; "
                    f"font-size: 12px; font-weight: {w}; background: transparent;"
                )
                cl.addWidget(lbl)

            # RESUMED
            if resumed:
                h = _utc_to_local(resumed).split(" ")[-1]
                _add_line(f"{h}   TPE RESUMED — accepte les cartes")

            # PAIEMENT
            if paiement:
                h = _utc_to_local(paiement).split(" ")[-1]
                _add_line(f"{h}   Paiement {montant:.2f}€", bold=True)

            # IMPRESSION ou ANOMALIE
            if ok:
                _add_line(f"             Impression déclenchée")
            elif flag:
                lbl = QLabel(f"             Anomalie: {flag}")
                lbl.setStyleSheet(
                    f"color: #DC2626; font-family: 'Satoshi'; "
                    f"font-size: 12px; font-weight: 600; background: transparent;"
                )
                cl.addWidget(lbl)

            # INHIBITED
            if inhibited:
                h = _utc_to_local(inhibited).split(" ")[-1]
                d = f" ({delai}s)" if delai else ""
                _add_line(f"{h}   TPE INHIBITED — fermé{d}")

            # Badge statut en haut à droite
            badge_text = "Imprimé" if ok else (flag if flag else "En attente")
            badge_bg = "#DCFCE7" if ok else ("#FEF2F2" if flag else "#FEF9C3")
            badge_fg = "#16A34A" if ok else ("#DC2626" if flag else "#A16207")

            self._logs_container.addWidget(card)

