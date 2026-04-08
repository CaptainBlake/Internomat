"""ADR-influenced Elo rating system (strict timeline).

Each player's expected ADR is derived only from matches already processed,
preventing the statistical look-ahead leakage that would occur if global
averages were computed from the full dataset including future matches.

All DB writes use upserts — safe to call repeatedly over the same data.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from db import elo_db
from db.connection_db import get_conn, write_transaction
import db.settings_db as settings_db
import services.logger as logger


# ── Tuning ────────────────────────────────────────────────────────────

TUNE = {
    "K_FACTOR":              24.0,    # rating swing per match
    "BASE_RATING":         1500.0,    # starting Elo for new players
    "ADR_ALPHA":              0.20,   # ADR influence strength
    "ADR_SPREAD":            22.0,    # z-score denominator
    "ADR_MIN_MULT":           0.85,   # floor for individual multiplier
    "ADR_MAX_MULT":           1.15,   # ceiling for individual multiplier
    "ADR_PRIOR_MATCHES":      5.0,    # Bayesian smoothing weight
    "INITIAL_GLOBAL_ANCHOR": 80.0,    # starting global ADR expectation
}


# ── Public API ────────────────────────────────────────────────────────

def recalculate_elo(*, season: int | None = None) -> dict:
    """Full Elo recalculation from match history.

    Processes every known match in chronological order and persists:
      - elo_history   (per-player per-match detail rows)
      - elo_ratings   (current rating snapshot per player)
      - elo_state     (global anchor, season tag)

    Returns ``{"players_rated", "matches_processed", "global_anchor"}``.
    """
    with get_conn() as conn:
        match_outcomes = _load_match_outcomes(conn)
        adr_lookup = _load_adr_lookup(conn)
        all_players = _load_all_players(conn)

    season_ranges = _assign_seasons(match_outcomes, forced_season=season)
    if season is not None:
        current_season_hint = int(season)
    else:
        current_season_hint = _resolve_season(datetime.now().isoformat(timespec="seconds"), season_ranges)

    tune = _load_tune_from_settings()

    season_dim_rows = _build_season_dimension_rows(season_ranges)
    season_match_rows = _build_match_season_rows(match_outcomes)

    with write_transaction() as conn:
        elo_db.init_elo_tables(conn)
        season_tune_map = _load_or_seed_season_tuning_map(conn, season_ranges, tune)

        history_rows, rating_rows, season_rating_rows, global_anchor, current_season = _compute_elo(
            match_outcomes, adr_lookup, season_tune_map, all_players, current_season_hint
        )

        elo_db.clear_elo_tables(conn=conn)
        elo_db.clear_elo_seasons(conn=conn)
        elo_db.upsert_elo_history_many(history_rows, conn=conn)
        elo_db.upsert_elo_ratings_many(rating_rows, conn=conn)
        elo_db.upsert_elo_ratings_season_many(season_rating_rows, conn=conn)
        elo_db.upsert_elo_seasons_many(season_dim_rows, conn=conn)
        elo_db.upsert_elo_match_season_many(season_match_rows, conn=conn)
        elo_db.upsert_elo_state("global_anchor", str(global_anchor), conn=conn)
        elo_db.upsert_elo_state("season", str(current_season), conn=conn)

    n_matches = len({r["match_id"] for r in history_rows})
    logger.log(
        f"[ELO] Recalculated: {len(rating_rows)} players, "
        f"{n_matches} matches, season={current_season}, anchor={global_anchor:.2f}",
        level="INFO",
    )
    return {
        "players_rated": len(rating_rows),
        "matches_processed": n_matches,
        "season": current_season,
        "global_anchor": global_anchor,
    }


def bind_current_settings_tuning_to_season(season: int, *, source: str = "settings_ui") -> None:
    """Persist current settings tuning as the locked tuning profile for one season."""
    tune = _load_tune_from_settings()
    with write_transaction() as conn:
        elo_db.init_elo_tables(conn)
        elo_db.upsert_elo_season_tuning(int(season), tune, source=source, conn=conn)


# ── Data loading ──────────────────────────────────────────────────────

def _load_match_outcomes(conn):
    """One row per player per match with win/loss determination.

    Returns a chronologically-sorted list of dicts::
        {match_id, steamid64, player_name, team_name, result}
    """
    # 1. Distinct player entries (collapsed across maps)
    rows = conn.execute("""
        SELECT DISTINCT
            CAST(match_id AS TEXT)   AS match_id,
            CAST(steamid64 AS TEXT)  AS steamid64,
            TRIM(team)               AS team,
            TRIM(name)               AS player_name
        FROM match_player_stats
        WHERE steamid64 IS NOT NULL
          AND TRIM(COALESCE(team, '')) <> ''
          AND TRIM(COALESCE(name, '')) <> ''
        ORDER BY CAST(match_id AS TEXT) ASC, team, name
    """).fetchall()

    by_match: dict[str, list[dict]] = {}
    seen: set[tuple[str, str]] = set()
    for r in rows:
        mid, sid = r["match_id"], r["steamid64"]
        if (mid, sid) in seen:
            continue
        seen.add((mid, sid))
        by_match.setdefault(mid, []).append({
            "steamid64": sid,
            "team": r["team"],
            "player_name": r["player_name"],
        })

    # 2. Winner + time source: matches table, fallback winner from match_maps
    winners: dict[str, str] = {}
    played_at_by_match: dict[str, str] = {}
    for r in conn.execute("""
        SELECT CAST(match_id AS TEXT) AS match_id,
               TRIM(COALESCE(winner, '')) AS winner,
               TRIM(COALESCE(NULLIF(end_time, ''), NULLIF(start_time, ''), NULLIF(created_at, ''), '')) AS played_at
        FROM matches
    """).fetchall():
        w = r["winner"]
        if w:
            winners[r["match_id"]] = w
        if r["played_at"]:
            played_at_by_match[r["match_id"]] = r["played_at"]

    for r in conn.execute("""
        SELECT CAST(match_id AS TEXT) AS match_id,
               MAX(TRIM(COALESCE(winner, ''))) AS winner
        FROM match_maps
        GROUP BY CAST(match_id AS TEXT)
    """).fetchall():
        mid = r["match_id"]
        if mid not in winners or not winners[mid]:
            w = r["winner"]
            if w:
                winners[mid] = w

    # 3. Build outcomes with team normalization
    result_rows: list[dict] = []
    for mid in sorted(by_match, key=_match_sort_key):
        players = by_match[mid]
        team_map = _build_team_mapping(players)
        raw_winner = winners.get(mid, "")
        winner = _apply_mapping(raw_winner, team_map)

        for p in players:
            team = _apply_mapping(p["team"], team_map)
            if not team or team.lower() == "all":
                continue

            if not winner:
                result = "unknown"
            elif team == winner:
                result = "win"
            else:
                result = "loss"

            result_rows.append({
                "match_id": mid,
                "steamid64": p["steamid64"],
                "player_name": p["player_name"],
                "team_name": team,
                "result": result,
                "played_at": played_at_by_match.get(mid, ""),
                "season": 0,
            })
    return result_rows


def _load_all_players(conn):
    """Return all known players so season resets can include idle players at 1500."""
    players = set()

    for row in conn.execute("SELECT CAST(steam64_id AS TEXT) AS sid FROM players WHERE steam64_id IS NOT NULL"):
        sid = (row["sid"] or "").strip()
        if sid:
            players.add(sid)

    for row in conn.execute("SELECT DISTINCT CAST(steamid64 AS TEXT) AS sid FROM match_player_stats WHERE steamid64 IS NOT NULL"):
        sid = (row["sid"] or "").strip()
        if sid:
            players.add(sid)

    return sorted(players)


def _assign_seasons(outcomes, forced_season=None):
    """Mutate outcome rows with season from settings date ranges or override."""
    if forced_season is not None:
        for row in outcomes:
            row["season"] = int(forced_season)
        return [{"season": int(forced_season), "start": None, "end": None}]

    season_ranges = _load_season_ranges_from_settings()
    if not season_ranges:
        season_ranges = [{"season": 0, "start": _infer_first_match_datetime(outcomes), "end": None}]
    for row in outcomes:
        row["season"] = _resolve_season(row.get("played_at"), season_ranges)
    return season_ranges


def _build_season_dimension_rows(season_ranges):
    rows = []
    for r in season_ranges or [{"season": 0, "start": None, "end": None}]:
        start = r.get("start")
        end = r.get("end")
        rows.append({
            "season": int(r.get("season", 0)),
            "start_at": start.isoformat(timespec="seconds") if start is not None else None,
            "end_at": end.isoformat(timespec="seconds") if end is not None else None,
            "is_open_ended": end is None,
            "source": "settings",
        })
    return rows


def _build_match_season_rows(outcomes):
    rows_by_match = {}
    for row in outcomes:
        match_id = str(row.get("match_id") or "").strip()
        if not match_id:
            continue
        if match_id not in rows_by_match:
            rows_by_match[match_id] = {
                "match_id": match_id,
                "season": int(row.get("season", 0)),
                "played_at": str(row.get("played_at") or "").strip() or None,
                "source": "elo_recalc",
            }

    return [rows_by_match[mid] for mid in sorted(rows_by_match, key=_match_sort_key)]


def _infer_first_match_datetime(outcomes):
    first = None
    for row in outcomes:
        dt = _parse_datetime(row.get("played_at"))
        if dt is None:
            continue
        if first is None or dt < first:
            first = dt
    return first


def _load_or_seed_season_tuning_map(conn, season_ranges, default_tune):
    out = {}
    for row in elo_db.get_elo_season_tunings(conn=conn):
        out[int(row["season"])] = {
            "K_FACTOR": float(row["k_factor"]),
            "BASE_RATING": float(row["base_rating"]),
            "ADR_ALPHA": float(row["adr_alpha"]),
            "ADR_SPREAD": float(row["adr_spread"]),
            "ADR_MIN_MULT": float(row["adr_min_mult"]),
            "ADR_MAX_MULT": float(row["adr_max_mult"]),
            "ADR_PRIOR_MATCHES": float(row["adr_prior_matches"]),
            "INITIAL_GLOBAL_ANCHOR": float(row["initial_global_anchor"]),
        }

    for item in season_ranges or [{"season": 0}]:
        sid = int(item.get("season", 0))
        if sid not in out:
            elo_db.upsert_elo_season_tuning(sid, default_tune, source="settings", conn=conn)
            out[sid] = dict(default_tune)

    return out


def _load_season_ranges_from_settings():
    """Parse `elo_seasons_json` setting.

    Expected format:
    [
      {"season": 0, "end": "2026-04-06"},
      {"season": 1, "start": "2026-04-07", "end": "2026-08-31"},
      {"season": 2, "start": "2026-09-01"}
    ]
    """
    raw = str(settings_db.get("elo_seasons_json", "[]") or "[]").strip()
    if not raw:
        return []

    try:
        data = json.loads(raw)
    except Exception:
        logger.log_warning("[ELO] Invalid elo_seasons_json; using season 0 for all matches")
        return []

    if not isinstance(data, list):
        logger.log_warning("[ELO] elo_seasons_json must be a list; using season 0")
        return []

    ranges = []
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            season = int(item.get("season", 0))
        except Exception:
            continue
        start_dt = _parse_datetime(_normalize_open_end_token(item.get("start")), end_of_day=False)
        end_dt = _parse_datetime(_normalize_open_end_token(item.get("end")), end_of_day=True)
        ranges.append({"season": season, "start": start_dt, "end": end_dt})

    ranges.sort(key=lambda r: r["season"])
    validated = _validate_season_ranges(ranges)
    if validated is None:
        logger.log_warning("[ELO] Invalid season range configuration; falling back to season 0")
        return []
    return validated


def _validate_season_ranges(ranges):
    """Return validated season ranges, or None when invalid.

    Rules:
    - Season ids must be contiguous starting at 0.
    - For season i>0, start date is required.
    - end must be >= start when both are present.
    - You cannot start a new season if previous season is open-ended.
    - Gaps are allowed (off-season), but overlap is forbidden.
    """
    if not ranges:
        return []

    normalized = []
    prev_end = None
    for idx, r in enumerate(ranges):
        season = int(r.get("season", idx))
        if season != idx:
            return None

        start = r.get("start")
        end = r.get("end")

        if idx > 0 and start is None:
            return None
        if start is not None and end is not None and end < start:
            return None

        if idx > 0:
            if prev_end is None:
                return None
            if start.date() <= prev_end.date():
                return None

        normalized.append({"season": season, "start": start, "end": end})
        prev_end = end

    return normalized


def _load_tune_from_settings():
    """Load tuning from settings with safe fallbacks to TUNE defaults."""
    key_map = {
        "elo_k_factor": "K_FACTOR",
        "elo_base_rating": "BASE_RATING",
        "elo_adr_alpha": "ADR_ALPHA",
        "elo_adr_spread": "ADR_SPREAD",
        "elo_adr_min_mult": "ADR_MIN_MULT",
        "elo_adr_max_mult": "ADR_MAX_MULT",
        "elo_adr_prior_matches": "ADR_PRIOR_MATCHES",
        "elo_initial_global_anchor": "INITIAL_GLOBAL_ANCHOR",
    }

    tune = dict(TUNE)
    for setting_key, tune_key in key_map.items():
        raw = settings_db.get(setting_key, tune[tune_key])
        try:
            tune[tune_key] = float(raw)
        except Exception:
            logger.log_warning(f"[ELO] Invalid setting '{setting_key}={raw}', using default {tune[tune_key]}")

    # Hard guards to avoid invalid math behavior from bad settings edits.
    tune["K_FACTOR"] = max(0.0, tune["K_FACTOR"])
    tune["BASE_RATING"] = max(0.0, tune["BASE_RATING"])
    tune["ADR_SPREAD"] = max(0.0001, tune["ADR_SPREAD"])
    tune["ADR_PRIOR_MATCHES"] = max(0.0, tune["ADR_PRIOR_MATCHES"])
    if tune["ADR_MIN_MULT"] > tune["ADR_MAX_MULT"]:
        tune["ADR_MIN_MULT"], tune["ADR_MAX_MULT"] = tune["ADR_MAX_MULT"], tune["ADR_MIN_MULT"]

    return tune


def _parse_datetime(value, end_of_day=False):
    txt = str(value or "").strip()
    if not txt:
        return None

    is_date_only = len(txt) == 10 and txt[4] == "-" and txt[7] == "-"

    # Normalize common UTC suffix for fromisoformat.
    if txt.endswith("Z"):
        txt = txt[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(txt)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        if end_of_day and is_date_only:
            dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        return dt
    except Exception:
        pass

    # Date-only fallback
    try:
        dt = datetime.fromisoformat(txt[:10])
        if end_of_day:
            dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
        return dt
    except Exception:
        return None


def _normalize_open_end_token(value):
    txt = str(value or "").strip().lower()
    if txt in {"", "none", "null", "open", "open_end", "open-end", "inf", "infinite"}:
        return None
    return value


def _resolve_season(played_at, ranges):
    if not ranges:
        return 0

    dt = _parse_datetime(played_at)
    if dt is None:
        return int(ranges[0]["season"])

    for r in ranges:
        start_ok = r["start"] is None or dt >= r["start"]
        end_ok = r["end"] is None or dt <= r["end"]
        if start_ok and end_ok:
            return int(r["season"])

    # Outside explicit ranges: assign to highest declared season.
    return int(max(r["season"] for r in ranges))


def _load_adr_lookup(conn):
    """ADR per player per match.

    Returns ``{(match_id, steamid64): adr_float}``.
    """
    damage: dict[tuple[str, str], int] = {}
    for r in conn.execute("""
        SELECT CAST(match_id AS TEXT)   AS match_id,
               CAST(steamid64 AS TEXT)  AS steamid64,
               SUM(COALESCE(damage, 0)) AS total_damage
        FROM match_player_stats
        GROUP BY CAST(match_id AS TEXT), CAST(steamid64 AS TEXT)
    """).fetchall():
        damage[(r["match_id"], r["steamid64"])] = r["total_damage"] or 0

    rounds: dict[str, int] = {}
    for r in conn.execute("""
        SELECT CAST(match_id AS TEXT) AS match_id,
               SUM(COALESCE(team1_score, 0)
                 + COALESCE(team2_score, 0)) AS total_rounds
        FROM match_maps
        GROUP BY CAST(match_id AS TEXT)
    """).fetchall():
        tr = r["total_rounds"]
        if tr and tr > 0:
            rounds[r["match_id"]] = tr

    adr: dict[tuple[str, str], float] = {}
    for (mid, sid), dmg in damage.items():
        tr = rounds.get(mid)
        if tr and tr > 0:
            adr[(mid, sid)] = dmg / tr
    return adr


# ── Team normalization ────────────────────────────────────────────────

def _build_team_mapping(player_list):
    """Map raw team names → canonical ``TeamA`` / ``TeamB``."""
    seen: list[str] = []
    for p in player_list:
        team = (p["team"] or "").strip()
        if not team or team.lower() == "all":
            continue
        if team.lower() in ("teama", "teamb"):
            return {}                       # already canonical
        if team not in seen:
            seen.append(team)

    mapping: dict[str, str] = {}
    if len(seen) >= 1:
        mapping[seen[0]] = "TeamA"
    if len(seen) >= 2:
        mapping[seen[1]] = "TeamB"
    return mapping


def _apply_mapping(raw, mapping):
    txt = (raw or "").strip()
    if not txt:
        return txt
    low = txt.lower()
    if low == "teama":
        return "TeamA"
    if low == "teamb":
        return "TeamB"
    return mapping.get(txt, txt)


# ── Helpers ───────────────────────────────────────────────────────────

def _match_sort_key(match_id):
    txt = str(match_id)
    try:
        return (0, int(txt))
    except ValueError:
        return (1, txt)


def _clip(x, lo, hi):
    return max(lo, min(hi, x))


# ── Core algorithm ────────────────────────────────────────────────────

def _split_teams(players):
    """Split a match's player list into exactly two teams.

    Returns ``((name, result, [players]), (name, result, [players]))``
    or *None* if the match can't be cleanly split.
    """
    teams: dict[str, dict] = {}
    for p in players:
        team = p["team_name"]
        if not team or team.lower() == "all":
            continue
        if p["result"] not in ("win", "loss"):
            continue
        if team not in teams:
            teams[team] = {"result": p["result"], "players": []}
        teams[team]["players"].append(p)
    if len(teams) != 2:
        return None
    items = list(teams.items())
    return (
        (items[0][0], items[0][1]["result"], items[0][1]["players"]),
        (items[1][0], items[1][1]["result"], items[1][1]["players"]),
    )


def _compute_elo(outcomes, adr_lookup, season_tune_map, all_players, current_season_hint=None):
    """Run strict-timeline ADR-Elo over chronological match outcomes.

    Returns ``(history_rows, rating_rows, season_rating_rows, final_global_anchor, current_season)``.
    """
    default_tune = dict(TUNE)

    # Keep only matches with a known result
    outcomes = [o for o in outcomes if o["result"] in ("win", "loss")]

    # Group by (season, match_id), preserving first-seen order for stability.
    ordered_by_season: dict[int, list[str]] = {}
    by_season_match: dict[tuple[int, str], list[dict]] = {}
    played_at_by_match: dict[tuple[int, str], str] = {}
    seen_in_match: set[tuple[int, str, str]] = set()
    for o in outcomes:
        season = int(o.get("season", 0))
        mid = o["match_id"]
        sid = o["steamid64"]
        if (season, mid, sid) in seen_in_match:
            continue
        seen_in_match.add((season, mid, sid))
        key = (season, mid)
        if season not in ordered_by_season:
            ordered_by_season[season] = []
        if mid not in ordered_by_season[season]:
            ordered_by_season[season].append(mid)
        by_season_match.setdefault(key, []).append(o)
        played_at_by_match[key] = str(o.get("played_at") or "")

    history_rows: list[dict] = []

    season_rating_rows: dict[int, dict[str, dict]] = {}
    season_anchor: dict[int, float] = {}

    for season in sorted(ordered_by_season.keys()):
        season_tune = season_tune_map.get(season, default_tune)
        k = float(season_tune["K_FACTOR"])
        base = float(season_tune["BASE_RATING"])
        alpha = float(season_tune["ADR_ALPHA"])
        spread = float(season_tune["ADR_SPREAD"])
        min_m = float(season_tune["ADR_MIN_MULT"])
        max_m = float(season_tune["ADR_MAX_MULT"])
        prior = float(season_tune["ADR_PRIOR_MATCHES"])
        anchor0 = float(season_tune["INITIAL_GLOBAL_ANCHOR"])

        # Reset state at season boundary.
        ratings: dict[str, float] = {}
        player_adr_sum: dict[str, float] = {}
        player_adr_count: dict[str, int] = {}
        global_adr_sum = 0.0
        global_adr_count = 0

        player_wins: dict[str, int] = {}
        player_losses: dict[str, int] = {}
        player_matches: dict[str, int] = {}

        ordered_ids = sorted(
            ordered_by_season[season],
            key=lambda mid: (
                0 if _parse_datetime(played_at_by_match.get((season, mid), "")) else 1,
                _parse_datetime(played_at_by_match.get((season, mid), "")) or datetime.min,
                _match_sort_key(mid),
            ),
        )

        for match_id in ordered_ids:
            key = (season, match_id)
            split = _split_teams(by_season_match[key])
            if split is None:
                continue

            (tn_a, res_a, pls_a), (tn_b, res_b, pls_b) = split
            score_a = 1.0 if res_a == "win" else 0.0
            score_b = 1.0 - score_a

            # Initialise new players
            for p in pls_a + pls_b:
                ratings.setdefault(p["steamid64"], base)

            ids_a = [p["steamid64"] for p in pls_a]
            ids_b = [p["steamid64"] for p in pls_b]
            elo_a = sum(ratings[s] for s in ids_a) / max(1, len(ids_a))
            elo_b = sum(ratings[s] for s in ids_b) / max(1, len(ids_b))

            exp_a = 1.0 / (1.0 + 10.0 ** ((elo_b - elo_a) / 400.0))
            exp_b = 1.0 - exp_a
            delta_a = k * (score_a - exp_a)
            delta_b = k * (score_b - exp_b)

            # Process both sides
            for tn, pls, result, t_elo, o_elo, t_delta in [
                (tn_a, pls_a, res_a, elo_a, elo_b, delta_a),
                (tn_b, pls_b, res_b, elo_b, elo_a, delta_b),
            ]:
                for p in pls:
                    sid = p["steamid64"]

                    # ── ADR multiplier (strict timeline, per season) ──
                    anchor = (
                        global_adr_sum / global_adr_count
                        if global_adr_count > 0
                        else anchor0
                    )
                    p_cnt = player_adr_count.get(sid, 0)
                    p_sum = player_adr_sum.get(sid, 0.0)

                    if p_cnt > 0:
                        p_mean = p_sum / p_cnt
                        expected_adr = (
                            (p_mean * p_cnt + anchor * prior) / (p_cnt + prior)
                        )
                    else:
                        expected_adr = anchor

                    observed_adr = adr_lookup.get((match_id, sid))
                    if observed_adr is None:
                        observed_adr = expected_adr     # no data → mult = 1.0

                    adr_z = (observed_adr - expected_adr) / spread
                    mult = _clip(1.0 + alpha * adr_z, min_m, max_m)

                    elo_before = ratings[sid]
                    elo_delta = t_delta * mult
                    ratings[sid] += elo_delta

                    # Bookkeeping
                    player_matches[sid] = player_matches.get(sid, 0) + 1
                    if result == "win":
                        player_wins[sid] = player_wins.get(sid, 0) + 1
                    else:
                        player_losses[sid] = player_losses.get(sid, 0) + 1

                    history_rows.append({
                        "steamid64":           sid,
                        "match_id":            match_id,
                        "season":              season,
                        "elo_before":          elo_before,
                        "elo_after":           ratings[sid],
                        "elo_delta":           elo_delta,
                        "result":              result,
                        "team_name":           tn,
                        "team_elo_before":     t_elo,
                        "opp_team_elo_before": o_elo,
                        "adr":                 observed_adr,
                        "adr_expected":        expected_adr,
                        "adr_multiplier":      mult,
                        "global_anchor_used":  anchor,
                    })

            # Update ADR accumulators *after* the full match is scored
            for p in pls_a + pls_b:
                sid = p["steamid64"]
                obs = adr_lookup.get((match_id, sid))
                if obs is not None:
                    player_adr_sum[sid] = player_adr_sum.get(sid, 0.0) + obs
                    player_adr_count[sid] = player_adr_count.get(sid, 0) + 1
                    global_adr_sum += obs
                    global_adr_count += 1

        season_anchor[season] = (
            global_adr_sum / global_adr_count
            if global_adr_count > 0
            else anchor0
        )

        season_rating_rows[season] = {}
        for sid, elo in ratings.items():
            season_rating_rows[season][sid] = {
                "steamid64": sid,
                "season": season,
                "elo": round(elo, 2),
                "matches_played": player_matches.get(sid, 0),
                "wins": player_wins.get(sid, 0),
                "losses": player_losses.get(sid, 0),
            }

    if current_season_hint is None:
        current_season = max(season_rating_rows.keys(), default=0)
    else:
        current_season = int(current_season_hint)
    current_rows = season_rating_rows.get(current_season, {})
    current_tune = season_tune_map.get(current_season, default_tune)
    current_base = float(current_tune["BASE_RATING"])
    current_anchor0 = float(current_tune["INITIAL_GLOBAL_ANCHOR"])

    # Ensure players with no matches this season still read as 1500.
    rating_rows: list[dict] = []
    for sid in all_players:
        row = current_rows.get(sid)
        if row is None:
            rating_rows.append({
                "steamid64": sid,
                "season": current_season,
                "elo": round(current_base, 2),
                "matches_played": 0,
                "wins": 0,
                "losses": 0,
            })
        else:
            rating_rows.append(row)

    final_anchor = season_anchor.get(current_season, current_anchor0)

    season_rating_rows_flat: list[dict] = []
    for s in sorted(season_rating_rows.keys()):
        for row in season_rating_rows[s].values():
            season_rating_rows_flat.append(row)

    return history_rows, rating_rows, season_rating_rows_flat, final_anchor, current_season
