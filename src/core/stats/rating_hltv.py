"""HLTV Rating 3.0 approximation and sub-metric quality evaluation.

Rating 3.0 (released Aug 2025) consists of six eco-adjusted sub-ratings:
  Kill Rating, Damage Rating, Survival Rating, KAST Rating,
  Multi-Kill Rating, and Round Swing.

The exact formula is proprietary.  Round Swing requires round-level win
probability models that depend on map, side, economy, and alive-counts
— data we cannot derive from our per-match aggregates.

This module therefore provides:
  1.  Per-metric quality classification (GOOD / AVERAGE / BAD) using
      thresholds calibrated for competitive amateur play.
  2.  KPR, DPR, and Multi-Kill % helpers not yet in metrics.py.
  3.  An *approximate* composite rating modelled on the published 2.0
      sub-rating structure with adjustments toward 3.0 philosophy
      (multi-kill replaces impact, KAST weight increased).

All thresholds are tuneable via the ``THRESHOLDS`` dict.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Quality tiers
# ---------------------------------------------------------------------------

GOOD = "GOOD"
AVERAGE = "AVERAGE"
BAD = "BAD"

# Thresholds: (bad_upper, good_lower)
# Values between bad_upper and good_lower are AVERAGE.
# For "lower is better" metrics (like DPR), the scale is inverted.
THRESHOLDS: dict[str, dict] = {
    "rating": {"bad_upper": 0.90, "good_lower": 1.05, "invert": False},
    "kpr": {"bad_upper": 0.55, "good_lower": 0.72, "invert": False},
    "dpr": {"bad_upper": 0.72, "good_lower": 0.58, "invert": True},
    "adr": {"bad_upper": 62.0, "good_lower": 78.0, "invert": False},
    "kast": {"bad_upper": 62.0, "good_lower": 72.0, "invert": False},
    "multi_kill_pct": {"bad_upper": 12.0, "good_lower": 20.0, "invert": False},
    "hs_pct": {"bad_upper": 35.0, "good_lower": 50.0, "invert": False},
    "entry_success_pct": {"bad_upper": 40.0, "good_lower": 55.0, "invert": False},
}

# Display ranges for progress bar fill: (min_display, max_display)
DISPLAY_RANGES: dict[str, tuple[float, float]] = {
    "rating": (0.50, 1.60),
    "kpr": (0.30, 1.10),
    "dpr": (0.90, 0.30),  # inverted: lower is better
    "adr": (40.0, 110.0),
    "kast": (40.0, 95.0),
    "multi_kill_pct": (0.0, 35.0),
    "hs_pct": (15.0, 70.0),
    "entry_success_pct": (20.0, 80.0),
}


def quality_tier(metric_key: str, value: float | None) -> str:
    """Return GOOD / AVERAGE / BAD for a given metric value."""
    if value is None:
        return AVERAGE
    t = THRESHOLDS.get(metric_key)
    if t is None:
        return AVERAGE
    if t.get("invert"):
        # lower is better
        if value <= t["good_lower"]:
            return GOOD
        if value >= t["bad_upper"]:
            return BAD
        return AVERAGE
    else:
        if value >= t["good_lower"]:
            return GOOD
        if value <= t["bad_upper"]:
            return BAD
        return AVERAGE


def bar_fraction(metric_key: str, value: float | None) -> float:
    """Return 0.0–1.0 representing where *value* falls in the display range."""
    if value is None:
        return 0.0
    rng = DISPLAY_RANGES.get(metric_key)
    if rng is None:
        return 0.5
    lo, hi = rng
    if abs(hi - lo) < 1e-9:
        return 0.5
    frac = (value - lo) / (hi - lo)
    return max(0.0, min(1.0, frac))


# ---------------------------------------------------------------------------
# Derived per-round metrics
# ---------------------------------------------------------------------------

def kills_per_round(kills: int, rounds: int) -> float | None:
    if rounds <= 0:
        return None
    return float(kills) / float(rounds)


def deaths_per_round(deaths: int, rounds: int) -> float | None:
    if rounds <= 0:
        return None
    return float(deaths) / float(rounds)


def multi_kill_pct(enemy2ks: int, enemy3ks: int, enemy4ks: int, enemy5ks: int, rounds: int) -> float | None:
    """Percentage of rounds in which the player scored 2+ kills."""
    if rounds <= 0:
        return None
    total = int(enemy2ks or 0) + int(enemy3ks or 0) + int(enemy4ks or 0) + int(enemy5ks or 0)
    return 100.0 * float(total) / float(rounds)


# ---------------------------------------------------------------------------
# Approximate composite rating (2.0-style with 3.0 adjustments)
# ---------------------------------------------------------------------------
# The classic HLTV 2.0 formula (published 2017) uses five sub-ratings:
#   Rating = 0.0073*KAST + 0.3591*KPR − 0.5329*DPR + 0.2372*Impact + 0.0032*ADR + 0.1587
#
# In 3.0, Impact is replaced by Round-Swing + Multi-Kill rating and
# eco-adjustment is applied.  Since we lack round-swing and eco data
# we keep the 2.0 skeleton but replace Impact with a multi-kill proxy.
#
# This is explicitly an *approximation* — the awpy library rating stored
# in the DB is still the primary "HLTV rating" field.

_W_KAST = 0.0073
_W_KPR = 0.3591
_W_DPR = -0.5329
_W_MULTI = 0.2372    # replaces Impact weight
_W_ADR = 0.0032
_W_CONST = 0.1587


def approximate_rating(
    kast_pct: float | None,
    kpr: float | None,
    dpr: float | None,
    multi_kill_rate: float | None,
    adr_val: float | None,
) -> float | None:
    """Compute an approximate HLTV-style rating from per-round metrics.

    Parameters use the same scale as HLTV:
      kast_pct   – 0-100 (percentage)
      kpr        – kills per round  (e.g. 0.75)
      dpr        – deaths per round (e.g. 0.62)
      multi_kill_rate – multi-kill rounds per round (e.g. 0.22)
      adr_val    – average damage per round (e.g. 80)

    Returns a float centred around 1.00.
    """
    if kpr is None or dpr is None:
        return None
    _kast = kast_pct if kast_pct is not None else 70.0
    _multi = multi_kill_rate if multi_kill_rate is not None else 0.0
    _adr = adr_val if adr_val is not None else 75.0
    return (
        _W_KAST * _kast
        + _W_KPR * kpr
        + _W_DPR * dpr
        + _W_MULTI * _multi
        + _W_ADR * _adr
        + _W_CONST
    )
