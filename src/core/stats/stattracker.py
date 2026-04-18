from db import stattracker_db as stattracker_repo
from core.stats import metrics as M
from core.stats import rating_hltv as hltv
import services.logger as logger
from datetime import datetime


def get_overview():
    row = stattracker_repo.fetch_player_overview()

    result = {
        "tracked_players": int(row["tracked_players"] or 0),
        "player_stat_rows": int(row["player_stat_rows"] or 0),
        "unique_player_maps": int(row["unique_player_maps"] or 0),
    }

    logger.log(
        "[STATTRACKER] "
        f"overview tracked_players={result['tracked_players']} "
        f"player_stat_rows={result['player_stat_rows']} "
        f"unique_player_maps={result['unique_player_maps']}",
        level="DEBUG",
    )

    return result


def get_player_samples(limit=10):
    rows = stattracker_repo.fetch_top_player_samples(limit)

    result = [
        {
            "player_name": str(r["player_name"] or "?"),
            "steamid64": str(r["steamid64"] or ""),
            "map_entries": int(r["map_entries"] or 0),
            "total_kills": int(r["total_kills"] or 0),
            "total_deaths": int(r["total_deaths"] or 0),
        }
        for r in rows
    ]

    logger.log(f"[STATTRACKER] player samples size={len(result)}", level="DEBUG")
    return result


def get_player_options():
    rows = stattracker_repo.fetch_player_filter_options()
    options = [
        {
            "steamid64": str(r["steamid64"] or ""),
            "player_name": str(r["player_name"] or r["steamid64"] or "?"),
            "map_entries": int(r["map_entries"] or 0),
        }
        for r in rows
        if str(r["steamid64"] or "").strip()
    ]

    logger.log(f"[STATTRACKER] player options size={len(options)}", level="DEBUG")
    return options


def get_season_options():
    rows = stattracker_repo.fetch_elo_seasons()
    return [int(r["season"]) for r in rows]


def get_player_weapon_categories(steamid64, seasons=None):
    sid = str(steamid64 or "").strip()
    if not sid:
        return ["all"]

    rows = stattracker_repo.fetch_player_weapon_categories(sid, seasons=seasons)
    def _to_category_key(raw):
        value = str(raw or "unknown").strip().lower() or "unknown"
        if value in {"all", "unknown"}:
            return value
        return value if value.endswith("s") else f"{value}s"

    categories = ["all"]
    categories.extend(
        sorted(
            {
                _to_category_key(r["category"])
                for r in rows
                if str(r["category"] or "").strip()
            }
        )
    )

    logger.log(f"[STATTRACKER] weapon categories steamid={sid[:8]} size={len(categories)}", level="DEBUG")
    return categories


def get_player_dashboard(steamid64, min_weapon_shots=1, weapon_category="all", seasons=None):
    sid = str(steamid64 or "").strip()
    if not sid:
        return {
            "kpis": {
                "maps_played": 0,
                "win_rate": 0.0,
                "kdr": 0.0,
                "adr": 0.0,
            },
            "map_rows": [],
            "weapon_rows": [],
            "best_map": "-",
            "worst_map": "-",
        }

    overall = stattracker_repo.fetch_player_overall_metrics(sid, seasons=seasons)
    movement_overall = stattracker_repo.fetch_player_overall_movement_metrics(sid, seasons=seasons)
    map_rows_raw = stattracker_repo.fetch_player_map_stats(sid, seasons=seasons)
    weapon_rows_raw = stattracker_repo.fetch_player_weapon_stats(
        sid,
        min_shots=max(1, int(min_weapon_shots)),
        weapon_category=str(weapon_category or "all").strip().lower(),
        seasons=seasons,
    )

    maps_played = int((overall["maps_played"] if overall else 0) or 0)
    map_wins = int((overall["map_wins"] if overall else 0) or 0)
    total_kills = int((overall["total_kills"] if overall else 0) or 0)
    total_deaths = int((overall["total_deaths"] if overall else 0) or 0)
    total_assists = int((overall["total_assists"] if overall else 0) or 0)
    total_damage = int((overall["total_damage"] if overall else 0) or 0)
    total_headshot_kills = int((overall["total_headshot_kills"] if overall else 0) or 0)
    total_rounds = int((overall["total_rounds"] if overall else 0) or 0)

    total_distance_units = float((movement_overall["total_distance_units"] if movement_overall else 0.0) or 0.0)
    total_strafe_distance_units = float((movement_overall["strafe_distance_units"] if movement_overall else 0.0) or 0.0)
    total_strafe_time_s = float((movement_overall["strafe_time_s"] if movement_overall else 0.0) or 0.0)
    total_alive_seconds = float((movement_overall["alive_seconds"] if movement_overall else 0.0) or 0.0)
    total_camp_time_s = float((movement_overall["camp_time_s"] if movement_overall else 0.0) or 0.0)

    raw_avg_kast = overall["avg_kast"] if overall else None
    avg_kast = float(raw_avg_kast) if raw_avg_kast is not None else None
    raw_avg_impact = overall["avg_impact"] if overall else None
    avg_impact = float(raw_avg_impact) if raw_avg_impact is not None else None
    raw_avg_rating = overall["avg_rating"] if overall else None
    avg_rating = float(raw_avg_rating) if raw_avg_rating is not None else None

    total_enemy2ks = int((overall["total_enemy2ks"] if overall else 0) or 0)
    total_enemy3ks = int((overall["total_enemy3ks"] if overall else 0) or 0)
    total_enemy4ks = int((overall["total_enemy4ks"] if overall else 0) or 0)
    total_enemy5ks = int((overall["total_enemy5ks"] if overall else 0) or 0)
    total_entry_count = int((overall["total_entry_count"] if overall else 0) or 0)
    total_entry_wins = int((overall["total_entry_wins"] if overall else 0) or 0)

    win_rate = M.win_rate(map_wins, maps_played)
    kdr = M.kd_ratio(total_kills, max(1, total_deaths)) if maps_played > 0 else 0.0
    adr = M.adr(total_damage, total_rounds) or 0.0
    avg_kills = M.safe_avg(total_kills, maps_played)
    avg_deaths = M.safe_avg(total_deaths, maps_played)
    avg_assists = M.safe_avg(total_assists, maps_played)
    hs_pct = M.hs_pct(total_headshot_kills, total_kills)
    # Performance index: lightweight composite until true per-map rating/kast persistence is added.
    performance_index = M.performance_index(total_kills, total_assists, total_deaths) if maps_played > 0 else 0.0

    # HLTV 3.0 sub-metrics
    kpr = hltv.kills_per_round(total_kills, total_rounds)
    dpr = hltv.deaths_per_round(total_deaths, total_rounds)
    mk_pct = hltv.multi_kill_pct(total_enemy2ks, total_enemy3ks, total_enemy4ks, total_enemy5ks, total_rounds)
    entry_success_pct = M.success_pct(total_entry_wins, total_entry_count)

    avg_speed_m_s = (total_distance_units * 0.0254 / total_alive_seconds) if total_alive_seconds > 0 else 0.0
    if total_alive_seconds > 0:
        strafe_ratio = total_strafe_time_s / total_alive_seconds
    else:
        strafe_ratio = (total_strafe_distance_units / total_distance_units) if total_distance_units > 0 else 0.0
    avg_camp_time_s = M.safe_avg(total_camp_time_s, maps_played)

    elo_rating = stattracker_repo.fetch_player_elo_rating(sid)

    map_rows = []
    for row in map_rows_raw:
        played = int(row["maps_played"] or 0)
        wins = int(row["map_wins"] or 0)
        kills = int(row["kills"] or 0)
        deaths = int(row["deaths"] or 0)
        damage = int(row["damage"] or 0)
        rounds = int(row["rounds_played"] or 0)
        map_rows.append(
            {
                "map_name": str(row["map_name"] or "unknown"),
                "maps_played": played,
                "wins": wins,
                "win_rate": M.win_rate(wins, played),
                "kdr": M.kd_ratio(kills, max(1, deaths)),
                "adr": M.adr(damage, rounds) if rounds > 0 else 0.0,
            }
        )

    best_map = "-"
    worst_map = "-"
    if map_rows:
        ranked = sorted(map_rows, key=lambda r: (r["win_rate"], r["kdr"], r["adr"], r["maps_played"]), reverse=True)
        best_map = str(ranked[0]["map_name"])
        worst_map = str(ranked[-1]["map_name"])

    weapon_rows = []
    for row in weapon_rows_raw:
        shots_fired = int(row["shots_fired"] or 0)
        shots_hit = int(row["shots_hit"] or 0)
        kills = int(row["kills"] or 0)
        hs = int(row["headshot_kills"] or 0)
        weapon_rows.append(
            {
                "weapon": str(row["weapon"] or "unknown"),
                "category": str(row["category"] or "unknown"),
                "shots_fired": shots_fired,
                "shots_hit": shots_hit,
                "accuracy": M.accuracy_pct(shots_hit, shots_fired),
                "kills": kills,
                "headshot_pct": M.hs_pct(hs, kills),
                "damage": int(row["damage"] or 0),
                "rounds_with_weapon": int(row["rounds_with_weapon"] or 0),
            }
        )

    weapon_kills_total = sum(int(r.get("kills") or 0) for r in weapon_rows)
    unattributed_kills = int(max(0, total_kills - weapon_kills_total))

    if unattributed_kills > 0:
        deltas = stattracker_repo.fetch_player_weapon_kill_attribution_deltas(sid, seasons=seasons)
        logger.log(
            "[STATTRACKER] "
            f"kill attribution filtered steamid={sid[:8]} total={total_kills} "
            f"weapon={weapon_kills_total} filtered={unattributed_kills}",
            level="DEBUG",
        )
        for row in deltas:
            logger.log(
                "[STATTRACKER][ATTR] "
                f"match={row['match_id']} map={row['map_number']} name={row['map_name']} "
                f"total={int(row['total_kills'] or 0)} weapon={int(row['weapon_kills'] or 0)} "
                f"delta={int(row['delta'] or 0)}",
                level="DEBUG",
            )

    result = {
        "kpis": {
            "elo_rating": elo_rating,
            "maps_played": maps_played,
            "win_rate": win_rate,
            "kdr": kdr,
            "adr": adr,
            "avg_kills": avg_kills,
            "avg_deaths": avg_deaths,
            "avg_assists": avg_assists,
            "hs_pct": hs_pct,
            "avg_kast": avg_kast,
            "avg_impact": avg_impact,
            "avg_rating": avg_rating,
            "performance_index": performance_index,
            "avg_speed_m_s": avg_speed_m_s,
            "strafe_ratio": strafe_ratio,
            "camp_time_s": avg_camp_time_s,
            "kpr": kpr,
            "dpr": dpr,
            "multi_kill_pct": mk_pct,
            "entry_success_pct": entry_success_pct,
        },
        "map_rows": map_rows,
        "weapon_rows": weapon_rows,
        "best_map": best_map,
        "worst_map": worst_map,
    }

    logger.log(
        "[STATTRACKER] "
        f"dashboard steamid={sid[:8]} maps={maps_played} weapons={len(weapon_rows)}",
        level="DEBUG",
    )
    return result


# ---------------------------------------------------------------------------
# Plot series: generic builder + two public wrappers
# ---------------------------------------------------------------------------


def _row_value(row, key, default=None):
    if row is None:
        return default
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        if hasattr(row, "get"):
            return row.get(key, default)
        return default
    return default if value is None else value

PLOT_METRICS = {
    "accuracy": {"label": "Accuracy %", "fn": lambda r: M.accuracy_pct(r["shots_hit"], r["shots_fired"]) if r["shots_fired"] > 0 else None},
    "hs_pct": {"label": "Headshot %", "fn": lambda r: M.hs_pct(r["headshot_kills"], r["kills"]) if r["kills"] > 0 else None},
    "kills": {"label": "Kills", "fn": lambda r: r["kills"]},
    "damage": {"label": "Damage", "fn": lambda r: r["damage"]},
    "shots_fired": {"label": "Shots Fired", "fn": lambda r: r["shots_fired"]},
    "shots_hit": {"label": "Shots Hit", "fn": lambda r: r["shots_hit"]},
}

MAP_PLOT_METRICS = {
    "kd_ratio": {"label": "K/D Ratio", "fn": lambda r: M.kd_ratio(r["kills"], max(1, r["deaths"]))},
    "kills": {"label": "Kills", "fn": lambda r: r["kills"]},
    "deaths": {"label": "Deaths", "fn": lambda r: r["deaths"]},
    "adr": {"label": "ADR", "fn": lambda r: M.adr(r["damage"], r["total_rounds"]) if r["total_rounds"] > 0 else None},
    "damage": {"label": "Damage", "fn": lambda r: r["damage"]},
    "hs_kills": {"label": "HS Kills", "fn": lambda r: r["head_shot_kills"]},
}

MOVEMENT_PLOT_METRICS = {
    "avg_speed_m_s": {"label": "Avg Speed (m/s)", "fn": lambda r: float(r["avg_speed_m_s"])},
    "max_speed_units_s": {"label": "Max Speed (units/s)", "fn": lambda r: float(r["max_speed_units_s"])},
    "total_distance_m": {"label": "Distance (m)", "fn": lambda r: float(r["total_distance_m"])},
    "alive_seconds": {"label": "Alive Time (s)", "fn": lambda r: float(r["alive_seconds"])},
    "strafe_ratio": {"label": "Strafe Ratio %", "fn": lambda r: float(r["strafe_ratio"] or 0.0) * 100.0},
    "stationary_ratio": {"label": "Stationary Ratio %", "fn": lambda r: float(r["stationary_ratio"] or 0.0) * 100.0},
    "sprint_ratio": {"label": "Sprint Ratio %", "fn": lambda r: float(r["sprint_ratio"] or 0.0) * 100.0},
    "strafe_distance_m": {"label": "Strafe Distance (m)", "fn": lambda r: float(r["strafe_distance_units"] or 0.0) * 0.0254},
    "camp_time_s": {
        "label": "Camp Time (s)",
        "fn": lambda r: (
            float(_row_value(r, "camp_time_s", 0.0) or 0.0)
            if float(_row_value(r, "camp_time_s", 0.0) or 0.0) > 0.0
            else float(_row_value(r, "stationary_ratio", 0.0) or 0.0)
            * float(_row_value(r, "alive_seconds", 0.0) or 0.0)
        ),
    },
}


def get_plot_metric_options():
    return [{"key": k, "label": v["label"]} for k, v in PLOT_METRICS.items()]


def get_map_plot_metric_options():
    return [{"key": k, "label": v["label"]} for k, v in MAP_PLOT_METRICS.items()]


def get_movement_plot_metric_options():
    return [{"key": k, "label": v["label"]} for k, v in MOVEMENT_PLOT_METRICS.items()]


def _format_match_time_subtitle(start_time):
    text = str(start_time or "").strip()
    if not text:
        return ""

    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized).strftime("%m-%d %H:%M")
    except ValueError:
        cleaned = text.replace("T", " ")
        if len(cleaned) >= 16:
            # Keep the compact "MM-DD HH:MM" style for readability.
            return cleaned[5:16]
        return cleaned


def _format_match_x_label(row):
    map_name = str(row["map_name"] or "unknown").strip() or "unknown"
    subtitle = _format_match_time_subtitle(row["start_time"])
    if subtitle:
        return f"{map_name}\n{subtitle}"

    match_id = str(row["match_id"] or "?")
    map_number = int(row["map_number"] or 0)
    return f"{map_name}\n{match_id}:{map_number}"


def _build_match_series(rows, metric_fn, series_key_fn, log_tag):
    """Generic helper: build plot-ready {x_labels, series} from DB rows.

    *series_key_fn(row)* returns the series name (weapon name or map name).
    """
    match_keys = []
    match_key_set = set()
    x_labels = []
    used_x_labels = set()
    for r in rows:
        key = (str(r["match_id"]), int(r["map_number"]))
        if key not in match_key_set:
            match_key_set.add(key)
            match_keys.append(key)
            label = _format_match_x_label(r)
            if label in used_x_labels:
                lines = label.split("\n", 1)
                if len(lines) == 2:
                    label = f"{lines[0]}\n{lines[1]} · M{int(r['map_number']) + 1}"
                else:
                    label = f"{label} · M{int(r['map_number']) + 1}"
            used_x_labels.add(label)
            x_labels.append(label)

    match_index = {k: i for i, k in enumerate(match_keys)}

    series: dict[str, list] = {}
    for r in rows:
        s_key = series_key_fn(r)
        key = (str(r["match_id"]), int(r["map_number"]))
        idx = match_index.get(key)
        if idx is None:
            continue
        if s_key not in series:
            series[s_key] = [None] * len(match_keys)
        series[s_key][idx] = metric_fn(r)

    return match_keys, x_labels, series


def _build_round_series(rows, metric_fn, series_key_fn, log_tag):
    round_keys = []
    round_key_set = set()
    x_labels = []
    used_x_labels = set()

    for r in rows:
        key = (str(r["match_id"]), int(r["map_number"]), int(r["round_num"]))
        if key in round_key_set:
            continue
        round_key_set.add(key)
        round_keys.append(key)

        map_name = str(r["map_name"] or "unknown").strip() or "unknown"
        round_num = int(r["round_num"] or 0)
        subtitle = _format_match_time_subtitle(r["start_time"])
        label = f"{map_name} R{round_num:02d}"
        if subtitle:
            label = f"{label}\n{subtitle}"

        if label in used_x_labels:
            label = f"{label} · {str(r['match_id'])}:{int(r['map_number'])}"
        used_x_labels.add(label)
        x_labels.append(label)

    round_index = {k: i for i, k in enumerate(round_keys)}
    series: dict[str, list] = {}
    for r in rows:
        s_key = series_key_fn(r)
        key = (str(r["match_id"]), int(r["map_number"]), int(r["round_num"]))
        idx = round_index.get(key)
        if idx is None:
            continue
        if s_key not in series:
            series[s_key] = [None] * len(round_keys)
        series[s_key][idx] = metric_fn(r)

    return round_keys, x_labels, series


def get_weapon_match_series(steamid64, weapons=None, metric="accuracy", map_name=None, seasons=None):
    sid = str(steamid64 or "").strip()
    if not sid:
        return {"metric_label": "", "x_labels": [], "series": {}, "match_keys": []}

    metric_def = PLOT_METRICS.get(metric, PLOT_METRICS["accuracy"])
    rows = stattracker_repo.fetch_player_weapon_match_series(sid, weapons=weapons, map_name=map_name, seasons=seasons)
    match_keys, x_labels, series = _build_match_series(
        rows, metric_def["fn"], lambda r: str(r["weapon"]), "weapon",
    )

    logger.log(
        f"[STATTRACKER] plot series steamid={sid[:8]} metric={metric} "
        f"matches={len(match_keys)} weapons={len(series)}",
        level="DEBUG",
    )
    return {
        "metric_label": metric_def["label"],
        "x_labels": x_labels,
        "series": series,
        "match_keys": [f"{mk[0]}:{mk[1]}" for mk in match_keys],
    }


def get_weapon_round_series(steamid64, weapons=None, metric="accuracy", map_name=None, seasons=None):
    sid = str(steamid64 or "").strip()
    if not sid:
        return {"metric_label": "", "x_labels": [], "series": {}, "match_keys": []}

    metric_def = PLOT_METRICS.get(metric, PLOT_METRICS["accuracy"])
    rows = stattracker_repo.fetch_player_weapon_round_series(sid, weapons=weapons, map_name=map_name, seasons=seasons)
    round_keys, x_labels, series = _build_round_series(
        rows, metric_def["fn"], lambda r: str(r["weapon"]), "weapon-round",
    )

    logger.log(
        f"[STATTRACKER] weapon round series steamid={sid[:8]} metric={metric} "
        f"rounds={len(round_keys)} weapons={len(series)}",
        level="DEBUG",
    )
    return {
        "metric_label": metric_def["label"],
        "x_labels": x_labels,
        "series": series,
        "match_keys": [f"{rk[0]}:{rk[1]}:{rk[2]}" for rk in round_keys],
    }


def get_map_match_series(steamid64, maps=None, metric="kd_ratio", seasons=None):
    sid = str(steamid64 or "").strip()
    if not sid:
        return {"metric_label": "", "x_labels": [], "series": {}, "match_keys": []}

    metric_def = MAP_PLOT_METRICS.get(metric, MAP_PLOT_METRICS["kd_ratio"])
    rows = stattracker_repo.fetch_player_map_match_series(sid, maps=maps, seasons=seasons)
    match_keys, x_labels, series = _build_match_series(
        rows, metric_def["fn"], lambda r: str(r["map_name"] or "unknown"), "map",
    )

    logger.log(
        f"[STATTRACKER] map plot series steamid={sid[:8]} metric={metric} "
        f"matches={len(match_keys)} maps={len(series)}",
        level="DEBUG",
    )
    return {
        "metric_label": metric_def["label"],
        "x_labels": x_labels,
        "series": series,
        "match_keys": [f"{mk[0]}:{mk[1]}" for mk in match_keys],
    }


def get_movement_match_series(steamid64, maps=None, metric="avg_speed_m_s", seasons=None):
    sid = str(steamid64 or "").strip()
    if not sid:
        return {"metric_label": "", "x_labels": [], "series": {}, "match_keys": []}

    metric_def = MOVEMENT_PLOT_METRICS.get(metric, MOVEMENT_PLOT_METRICS["avg_speed_m_s"])
    rows = stattracker_repo.fetch_player_movement_match_series(sid, maps=maps, seasons=seasons)
    match_keys, x_labels, series = _build_match_series(
        rows, metric_def["fn"], lambda r: "Movement", "movement",
    )

    logger.log(
        f"[STATTRACKER] movement series steamid={sid[:8]} metric={metric} "
        f"matches={len(match_keys)}",
        level="DEBUG",
    )
    return {
        "metric_label": metric_def["label"],
        "x_labels": x_labels,
        "series": series,
        "match_keys": [f"{mk[0]}:{mk[1]}" for mk in match_keys],
    }


def get_movement_round_series(steamid64, maps=None, metric="avg_speed_m_s", seasons=None):
    sid = str(steamid64 or "").strip()
    if not sid:
        return {"metric_label": "", "x_labels": [], "series": {}, "match_keys": []}

    metric_def = MOVEMENT_PLOT_METRICS.get(metric, MOVEMENT_PLOT_METRICS["avg_speed_m_s"])
    rows = stattracker_repo.fetch_player_movement_round_series(sid, maps=maps, seasons=seasons)
    round_keys, x_labels, series = _build_round_series(
        rows, metric_def["fn"], lambda r: "Movement", "movement-round",
    )

    logger.log(
        f"[STATTRACKER] movement round series steamid={sid[:8]} metric={metric} "
        f"rounds={len(round_keys)}",
        level="DEBUG",
    )
    return {
        "metric_label": metric_def["label"],
        "x_labels": x_labels,
        "series": series,
        "match_keys": [f"{rk[0]}:{rk[1]}:{rk[2]}" for rk in round_keys],
    }


# ---------------------------------------------------------------------------
# Players view: combat summary, kill relationships, Elo history
# ---------------------------------------------------------------------------

PLAYERS_PLOT_METRICS = {
    "elo": {"label": "Elo Rating", "fn": lambda r: float(r["elo_after"])},
    "elo_delta": {"label": "Elo Delta", "fn": lambda r: float(r["elo_delta"])},
    "premier": {"label": "Premier Rating", "fn": None},
}


def get_players_plot_metric_options():
    return [{"key": k, "label": v["label"]} for k, v in PLAYERS_PLOT_METRICS.items()]


def get_player_combat_summary(steamid64, seasons=None):
    sid = str(steamid64 or "").strip()
    if not sid:
        return {}

    row = stattracker_repo.fetch_player_combat_summary(sid, seasons=seasons)
    if not row:
        return {}

    maps_played = int(row["maps_played"] or 0)
    total_kills = int(row["total_kills"] or 0)
    total_deaths = int(row["total_deaths"] or 0)

    return {
        "maps_played": maps_played,
        "total_kills": total_kills,
        "total_deaths": total_deaths,
        "total_assists": int(row["total_assists"] or 0),
        "total_damage": int(row["total_damage"] or 0),
        "total_hs_kills": int(row["total_hs_kills"] or 0),
        "kdr": M.kd_ratio(total_kills, max(1, total_deaths)),
        "hs_pct": M.hs_pct(int(row["total_hs_kills"] or 0), total_kills),
        "total_flashes_thrown": int(row["total_flashes_thrown"] or 0),
        "total_enemies_flashed": int(row["total_enemies_flashed"] or 0),
        "total_entry_attempts": int(row["total_entry_attempts"] or 0),
        "total_entry_wins": int(row["total_entry_wins"] or 0),
        "entry_success_pct": M.win_rate(int(row["total_entry_wins"] or 0), int(row["total_entry_attempts"] or 0)),
        "total_clutch_1v1": int(row["total_clutch_1v1"] or 0),
        "total_clutch_1v1_wins": int(row["total_clutch_1v1_wins"] or 0),
        "total_clutch_1v2": int(row["total_clutch_1v2"] or 0),
        "total_clutch_1v2_wins": int(row["total_clutch_1v2_wins"] or 0),
        "total_aces": int(row["total_aces"] or 0),
        "total_4ks": int(row["total_4ks"] or 0),
        "total_3ks": int(row["total_3ks"] or 0),
        "total_teamkills": int(row["total_teamkills"] or 0),
    }


def get_player_kill_relationships(steamid64, seasons=None):
    sid = str(steamid64 or "").strip()
    if not sid:
        return {"favourite_target": None, "arch_nemesis": None, "rows": []}

    raw_rows = stattracker_repo.fetch_player_kill_relationships(sid, seasons=seasons)

    rows = []
    favourite_target = None
    arch_nemesis = None
    max_dealt = 0
    max_received = 0

    for r in raw_rows:
        dealt = int(r["kills_dealt"] or 0)
        received = int(r["kills_received"] or 0)
        entry = {
            "opponent_steamid64": str(r["opponent"] or ""),
            "opponent_name": str(r["opponent_name"] or "?"),
            "kills_dealt": dealt,
            "kills_received": received,
            "hs_dealt": int(r["hs_dealt"] or 0),
            "hs_received": int(r["hs_received"] or 0),
            "teamkills_dealt": int(r["teamkills_dealt"] or 0),
            "teamkills_received": int(r["teamkills_received"] or 0),
            "damage_dealt": int(r["damage_dealt"] or 0),
            "damage_received": int(r["damage_received"] or 0),
            "assists_dealt": int(r["assists_dealt"] or 0),
            "assists_received": int(r["assists_received"] or 0),
            "flash_assists_dealt": int(r["flash_assists_dealt"] or 0),
            "flash_assists_received": int(r["flash_assists_received"] or 0),
            "flashes_dealt": int(r["flashes_dealt"] or 0),
            "flashes_received": int(r["flashes_received"] or 0),
            "net": dealt - received,
        }
        rows.append(entry)

        if dealt > max_dealt:
            max_dealt = dealt
            favourite_target = entry
        if received > max_received:
            max_received = received
            arch_nemesis = entry

    return {
        "favourite_target": favourite_target,
        "arch_nemesis": arch_nemesis,
        "rows": rows,
    }


def get_player_elo_history_series(steamid64, metric="elo", season=None):
    sid = str(steamid64 or "").strip()
    if not sid:
        return {"metric_label": "", "x_labels": [], "series": {}, "match_keys": []}

    if metric == "premier":
        return get_player_premier_history_series(sid)

    metric_def = PLAYERS_PLOT_METRICS.get(metric, PLAYERS_PLOT_METRICS["elo"])
    if metric_def.get("fn") is None:
        return {"metric_label": metric_def["label"], "x_labels": [], "series": {}, "match_keys": []}

    rows = stattracker_repo.fetch_player_elo_history(sid, season=season)

    match_keys = []
    x_labels = []
    values = []

    for r in rows:
        mk = str(r["match_id"])
        match_keys.append(mk)
        map_name = str(r["map_name"] or "unknown")
        subtitle = _format_match_time_subtitle(r["start_time"])
        label = map_name
        if subtitle:
            label = f"{map_name}\n{subtitle}"
        x_labels.append(label)
        values.append(metric_def["fn"](r))

    series_name = "Elo" if metric == "elo" else metric_def["label"]

    return {
        "metric_label": metric_def["label"],
        "x_labels": x_labels,
        "series": {series_name: values},
        "match_keys": match_keys,
    }


def get_player_premier_history_series(steamid64):
    sid = str(steamid64 or "").strip()
    if not sid:
        return {"metric_label": "Premier Rating", "x_labels": [], "series": {}, "match_keys": []}

    rows = stattracker_repo.fetch_player_premier_rating_history(sid)

    x_labels = []
    values = []
    match_keys = []

    for r in rows:
        mk = str(r["leetify_match_id"] or "")
        match_keys.append(mk)
        map_name = str(r["map_name"] or "profile")
        ts = r["game_played_at"] or r["recorded_at"]
        subtitle = _format_match_time_subtitle(ts)
        label = map_name
        if subtitle:
            label = f"{map_name}\n{subtitle}"
        x_labels.append(label)
        values.append(int(r["premier_rating"]))

    return {
        "metric_label": "Premier Rating",
        "x_labels": x_labels,
        "series": {"Premier": values},
        "match_keys": match_keys,
    }
