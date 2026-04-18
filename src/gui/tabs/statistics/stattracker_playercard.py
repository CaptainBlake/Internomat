"""Player card widget inspired by the HLTV Rating 3.0 stats card.

Renders a compact dark-themed card with:
  - A semicircular rating gauge (center) with the overall HLTV-style rating.
  - Six metric tiles arranged in a 3×2 grid, each with a coloured quality bar.
  - Player name, maps played, and an Elo badge.

The arcs and bars are drawn with QPainter; no external images are required.
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QFont,
    QPainter,
    QPainterPath,
    QPen,
    QLinearGradient,
)
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.stats import rating_hltv as hltv

# ---------------------------------------------------------------------------
# Colour palette (dark-themed card, matching HLTV aesthetic)
# ---------------------------------------------------------------------------
_CARD_BG = "#1B2838"
_CARD_BORDER = "#2A3A4A"
_TEXT_PRIMARY = "#FFFFFF"
_TEXT_SECONDARY = "#8B9DAF"
_TEXT_LABEL = "#6B7D8F"
_ACCENT_GREEN = "#4CAF50"
_ACCENT_YELLOW = "#FFC107"
_ACCENT_RED = "#E74C3C"
_GAUGE_TRACK = "#2A3A4A"
_TILE_BG = "#1E2D3D"
_TILE_BORDER = "#263545"

_TIER_COLORS = {
    hltv.GOOD: _ACCENT_GREEN,
    hltv.AVERAGE: _ACCENT_YELLOW,
    hltv.BAD: _ACCENT_RED,
}


def _tier_color(tier: str) -> str:
    return _TIER_COLORS.get(tier, _ACCENT_YELLOW)


# ---------------------------------------------------------------------------
# Gauge widget (semicircular arc for rating)
# ---------------------------------------------------------------------------

class _RatingGauge(QWidget):
    """Draws a semicircular gauge showing a rating value 0.5 – 1.6."""

    def __init__(self, value: float | None, label: str = "RATING", parent=None):
        super().__init__(parent)
        self._value = value
        self._label = label
        self.setMinimumSize(180, 110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(110)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        cx = w / 2.0
        cy = h - 12.0
        radius = min(cx - 10, cy - 8) * 0.85
        arc_width = 10.0

        # Arc spans from 180° to 0° (left to right semicircle).
        # Qt angles are in 1/16 degrees; 0° is at 3-o'clock, CCW positive.
        start_angle_deg = 180.0
        span_deg = -180.0

        # Track (background)
        rect = QRectF(cx - radius, cy - radius, 2 * radius, 2 * radius)
        pen = QPen(QColor(_GAUGE_TRACK), arc_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        painter.drawArc(rect, int(start_angle_deg * 16), int(span_deg * 16))

        # Coloured fill
        if self._value is not None:
            frac = hltv.bar_fraction("rating", self._value)
            tier = hltv.quality_tier("rating", self._value)
            fill_span = span_deg * frac
            color = QColor(_tier_color(tier))
            pen2 = QPen(color, arc_width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            painter.setPen(pen2)
            painter.drawArc(rect, int(start_angle_deg * 16), int(fill_span * 16))

        # Central value text
        painter.setPen(QColor(_TEXT_PRIMARY))
        value_font = QFont("Segoe UI", 22, QFont.Weight.Bold)
        painter.setFont(value_font)
        val_text = f"{self._value:.2f}" if self._value is not None else "-"
        painter.drawText(QRectF(0, cy - radius * 0.85, w, radius * 0.7),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, val_text)

        # Tier label
        if self._value is not None:
            tier = hltv.quality_tier("rating", self._value)
            painter.setPen(QColor(_tier_color(tier)))
            tier_font = QFont("Segoe UI", 8, QFont.Weight.Bold)
            painter.setFont(tier_font)
            painter.drawText(QRectF(0, cy - radius * 0.32, w, 16),
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, tier)

        # Label below value
        painter.setPen(QColor(_TEXT_SECONDARY))
        lbl_font = QFont("Segoe UI", 8)
        painter.setFont(lbl_font)
        painter.drawText(QRectF(0, cy - 10, w, 16),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, self._label)

        painter.end()


# ---------------------------------------------------------------------------
# Metric tile (value + coloured bar)
# ---------------------------------------------------------------------------

class _MetricTile(QFrame):
    """Single metric box: value, label, and a thin quality bar."""

    def __init__(self, metric_key: str, value, label: str, fmt: str = "{:.2f}", suffix: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background-color: {_TILE_BG}; border: 1px solid {_TILE_BORDER}; border-radius: 6px;"
        )
        self.setMinimumWidth(100)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(72)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(2)

        # Value
        if value is not None:
            val_text = fmt.format(float(value)) + suffix
        else:
            val_text = "-"
        val_label = QLabel(val_text)
        val_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        val_label.setStyleSheet(
            f"color: {_TEXT_PRIMARY}; font-size: 18px; font-weight: bold; "
            f"border: none; background: transparent;"
        )
        layout.addWidget(val_label)

        # Label
        name_label = QLabel(label)
        name_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        name_label.setStyleSheet(
            f"color: {_TEXT_LABEL}; font-size: 9px; font-weight: 600; "
            f"border: none; background: transparent; text-transform: uppercase;"
        )
        layout.addWidget(name_label)

        # Quality bar
        self._bar = _QualityBar(metric_key, float(value) if value is not None else None)
        layout.addWidget(self._bar)


class _QualityBar(QWidget):
    """Thin horizontal bar coloured by quality tier."""

    def __init__(self, metric_key: str, value: float | None, parent=None):
        super().__init__(parent)
        self._metric_key = metric_key
        self._value = value
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        h = self.height()
        radius = h / 2.0

        # Track
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(_GAUGE_TRACK))
        painter.drawRoundedRect(QRectF(0, 0, w, h), radius, radius)

        # Fill
        if self._value is not None:
            frac = hltv.bar_fraction(self._metric_key, self._value)
            tier = hltv.quality_tier(self._metric_key, self._value)
            fill_w = max(h, w * frac)  # at least one circle-cap wide
            painter.setBrush(QColor(_tier_color(tier)))
            painter.drawRoundedRect(QRectF(0, 0, fill_w, h), radius, radius)

        painter.end()


# ---------------------------------------------------------------------------
# Small stat badge (Elo, Maps, Win Rate at the top of the card)
# ---------------------------------------------------------------------------

class _StatBadge(QFrame):
    """Compact badge showing a single labelled number."""

    def __init__(self, value_text: str, label: str, accent: str | None = None, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            f"background-color: {_TILE_BG}; border: 1px solid {_TILE_BORDER}; border-radius: 4px;"
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(40)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setSpacing(0)

        v = QLabel(value_text)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        color = accent or _TEXT_PRIMARY
        v.setStyleSheet(
            f"color: {color}; font-size: 13px; font-weight: bold; "
            f"border: none; background: transparent;"
        )
        layout.addWidget(v)

        l = QLabel(label)
        l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        l.setStyleSheet(
            f"color: {_TEXT_LABEL}; font-size: 8px; "
            f"border: none; background: transparent;"
        )
        layout.addWidget(l)


# ---------------------------------------------------------------------------
# Public: build_player_card
# ---------------------------------------------------------------------------

def build_player_card(
    player_name: str,
    kpis: dict,
    nemesis: str = "-",
    practice_target: str = "-",
    parent: QWidget | None = None,
) -> QFrame:
    """Build and return the complete player card widget.

    *kpis* is the dict from ``stattracker.get_player_dashboard()["kpis"]``.
    """
    card = QFrame(parent)
    card.setStyleSheet(
        f"QFrame {{ background-color: {_CARD_BG}; border: 1px solid {_CARD_BORDER}; border-radius: 10px; }}"
    )
    card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    outer = QVBoxLayout(card)
    outer.setContentsMargins(14, 10, 14, 10)
    outer.setSpacing(8)

    # --- Top row: player name + badges ---
    top = QHBoxLayout()
    top.setSpacing(8)

    name_lbl = QLabel(player_name)
    name_lbl.setStyleSheet(
        f"color: {_TEXT_PRIMARY}; font-size: 16px; font-weight: bold; border: none;"
    )
    top.addWidget(name_lbl)
    top.addStretch()

    elo_val = kpis.get("elo_rating")
    elo_text = f"{elo_val:.0f}" if elo_val is not None else "-"
    top.addWidget(_StatBadge(elo_text, "ELO", accent="#64B5F6"))

    maps_played = int(kpis.get("maps_played") or 0)
    top.addWidget(_StatBadge(str(maps_played), "MAPS"))

    wr = kpis.get("win_rate")
    wr_text = f"{float(wr):.1f}%" if wr is not None else "-"
    top.addWidget(_StatBadge(wr_text, "WIN RATE", accent=_ACCENT_GREEN if (wr or 0) >= 50 else _ACCENT_RED))

    outer.addLayout(top)

    # --- Rating gauge ---
    avg_rating = kpis.get("avg_rating")
    gauge = _RatingGauge(avg_rating, label="RATING")
    outer.addWidget(gauge, alignment=Qt.AlignmentFlag.AlignHCenter)

    # --- 3×2 metric grid ---
    grid = QGridLayout()
    grid.setSpacing(6)

    # Row 0: HS%, DPR, KAST
    grid.addWidget(
        _MetricTile("hs_pct", kpis.get("hs_pct"), "HS%", fmt="{:.1f}", suffix="%"),
        0, 0,
    )
    grid.addWidget(
        _MetricTile("dpr", kpis.get("dpr"), "DPR", fmt="{:.2f}"),
        0, 1,
    )
    grid.addWidget(
        _MetricTile("kast", kpis.get("avg_kast"), "KAST", fmt="{:.1f}", suffix="%"),
        0, 2,
    )

    # Row 1: Multi-Kill, ADR, KPR
    grid.addWidget(
        _MetricTile("multi_kill_pct", kpis.get("multi_kill_pct"), "MULTI-KILL", fmt="{:.1f}", suffix="%"),
        1, 0,
    )
    grid.addWidget(
        _MetricTile("adr", kpis.get("adr"), "ADR", fmt="{:.1f}"),
        1, 1,
    )
    grid.addWidget(
        _MetricTile("kpr", kpis.get("kpr"), "KPR", fmt="{:.2f}"),
        1, 2,
    )

    outer.addLayout(grid)

    # --- Bottom row: Nemesis / Practice Target ---
    bottom = QHBoxLayout()
    bottom.setSpacing(8)

    nem_lbl = QLabel(f"Nemesis: {nemesis}")
    nem_lbl.setStyleSheet(
        f"color: {_TEXT_SECONDARY}; font-size: 10px; border: none;"
    )
    bottom.addWidget(nem_lbl)
    bottom.addStretch()

    tgt_lbl = QLabel(f"Practice-Target: {practice_target}")
    tgt_lbl.setStyleSheet(
        f"color: {_TEXT_SECONDARY}; font-size: 10px; border: none;"
    )
    bottom.addWidget(tgt_lbl)

    outer.addLayout(bottom)

    return card
