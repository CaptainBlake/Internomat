from db import stattracker_db as stattracker_repo
import services.logger as logger


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


def get_player_weapon_categories(steamid64):
    sid = str(steamid64 or "").strip()
    if not sid:
        return ["all"]

    rows = stattracker_repo.fetch_player_weapon_categories(sid)
    categories = ["all"]
    categories.extend(
        sorted(
            {
                str(r["category"] or "unknown").strip().lower()
                for r in rows
                if str(r["category"] or "").strip()
            }
        )
    )

    logger.log(f"[STATTRACKER] weapon categories steamid={sid[:8]} size={len(categories)}", level="DEBUG")
    return categories


def get_player_dashboard(steamid64, min_weapon_shots=1, weapon_category="all"):
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

    overall = stattracker_repo.fetch_player_overall_metrics(sid)
    map_rows_raw = stattracker_repo.fetch_player_map_stats(sid)
    weapon_rows_raw = stattracker_repo.fetch_player_weapon_stats(
        sid,
        min_shots=max(1, int(min_weapon_shots)),
        weapon_category=str(weapon_category or "all").strip().lower(),
    )

    maps_played = int((overall["maps_played"] if overall else 0) or 0)
    map_wins = int((overall["map_wins"] if overall else 0) or 0)
    total_kills = int((overall["total_kills"] if overall else 0) or 0)
    total_deaths = int((overall["total_deaths"] if overall else 0) or 0)
    total_assists = int((overall["total_assists"] if overall else 0) or 0)
    total_damage = int((overall["total_damage"] if overall else 0) or 0)
    total_headshot_kills = int((overall["total_headshot_kills"] if overall else 0) or 0)
    total_rounds = int((overall["total_rounds"] if overall else 0) or 0)

    raw_avg_kast = overall["avg_kast"] if overall else None
    avg_kast = float(raw_avg_kast) if raw_avg_kast is not None else None
    raw_avg_impact = overall["avg_impact"] if overall else None
    avg_impact = float(raw_avg_impact) if raw_avg_impact is not None else None
    raw_avg_rating = overall["avg_rating"] if overall else None
    avg_rating = float(raw_avg_rating) if raw_avg_rating is not None else None

    win_rate = (100.0 * map_wins / maps_played) if maps_played > 0 else 0.0
    kdr = (float(total_kills) / float(max(1, total_deaths))) if maps_played > 0 else 0.0
    adr = (float(total_damage) / float(max(1, total_rounds))) if total_rounds > 0 else 0.0
    avg_kills = (float(total_kills) / float(max(1, maps_played))) if maps_played > 0 else 0.0
    avg_deaths = (float(total_deaths) / float(max(1, maps_played))) if maps_played > 0 else 0.0
    avg_assists = (float(total_assists) / float(max(1, maps_played))) if maps_played > 0 else 0.0
    hs_pct = (100.0 * float(total_headshot_kills) / float(max(1, total_kills))) if total_kills > 0 else 0.0
    # Performance index: lightweight composite until true per-map rating/kast persistence is added.
    performance_index = ((total_kills + 0.5 * total_assists) / float(max(1, total_deaths))) if maps_played > 0 else 0.0

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
                "win_rate": (100.0 * wins / played) if played > 0 else 0.0,
                "kdr": float(kills) / float(max(1, deaths)),
                "adr": float(damage) / float(max(1, rounds)) if rounds > 0 else 0.0,
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
                "accuracy": (100.0 * shots_hit / shots_fired) if shots_fired > 0 else 0.0,
                "kills": kills,
                "headshot_pct": (100.0 * hs / kills) if kills > 0 else 0.0,
                "damage": int(row["damage"] or 0),
                "rounds_with_weapon": int(row["rounds_with_weapon"] or 0),
            }
        )

    weapon_kills_total = sum(int(r.get("kills") or 0) for r in weapon_rows)
    unattributed_kills = int(max(0, total_kills - weapon_kills_total))
    effective_total_kills = int(total_kills - unattributed_kills)

    if unattributed_kills > 0:
        deltas = stattracker_repo.fetch_player_weapon_kill_attribution_deltas(sid)
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

    # Filter unattributed kill events from KPI kill-derived metrics so values
    # align with the visible per-weapon table.
    kdr = (float(effective_total_kills) / float(max(1, total_deaths))) if maps_played > 0 else 0.0
    avg_kills = (float(effective_total_kills) / float(max(1, maps_played))) if maps_played > 0 else 0.0
    hs_pct = (
        100.0 * float(min(total_headshot_kills, effective_total_kills)) / float(max(1, effective_total_kills))
        if effective_total_kills > 0
        else 0.0
    )
    performance_index = (
        (effective_total_kills + 0.5 * total_assists) / float(max(1, total_deaths))
        if maps_played > 0
        else 0.0
    )

    result = {
        "kpis": {
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
# Plot series: per-match metric trends for selected weapons
# ---------------------------------------------------------------------------

PLOT_METRICS = {
    "accuracy": {"label": "Accuracy %", "fn": lambda r: (100.0 * r["shots_hit"] / r["shots_fired"]) if r["shots_fired"] > 0 else None},
    "hs_pct": {"label": "Headshot %", "fn": lambda r: (100.0 * r["headshot_kills"] / r["kills"]) if r["kills"] > 0 else None},
    "kills": {"label": "Kills", "fn": lambda r: r["kills"]},
    "damage": {"label": "Damage", "fn": lambda r: r["damage"]},
    "shots_fired": {"label": "Shots Fired", "fn": lambda r: r["shots_fired"]},
    "shots_hit": {"label": "Shots Hit", "fn": lambda r: r["shots_hit"]},
}


def get_plot_metric_options():
    return [{"key": k, "label": v["label"]} for k, v in PLOT_METRICS.items()]


def get_weapon_match_series(steamid64, weapons=None, metric="accuracy", map_name=None):
    """Build plot-ready series: one line per weapon, x = match index, y = metric value.

    Returns:
        {
            "metric_label": str,
            "x_labels": ["map_name (match_id)", ...],   # shared x-axis labels
            "series": {
                "ak-47": [value_or_None, ...],
                "m4a1-s": [value_or_None, ...],
            }
        }
    """
    sid = str(steamid64 or "").strip()
    if not sid:
        return {"metric_label": "", "x_labels": [], "series": {}}

    metric_def = PLOT_METRICS.get(metric, PLOT_METRICS["accuracy"])
    metric_fn = metric_def["fn"]

    rows = stattracker_repo.fetch_player_weapon_match_series(
        sid, weapons=weapons, map_name=map_name,
    )

    # Build ordered list of unique match points (match_id, map_number)
    match_keys = []
    match_key_set = set()
    x_labels = []
    for r in rows:
        key = (str(r["match_id"]), int(r["map_number"]))
        if key not in match_key_set:
            match_key_set.add(key)
            match_keys.append(key)
            map_label = str(r["map_name"] or "?")
            x_labels.append(map_label)

    match_index = {k: i for i, k in enumerate(match_keys)}

    # Build per-weapon series
    series: dict[str, list] = {}
    for r in rows:
        weapon = str(r["weapon"])
        key = (str(r["match_id"]), int(r["map_number"]))
        idx = match_index.get(key)
        if idx is None:
            continue

        if weapon not in series:
            series[weapon] = [None] * len(match_keys)

        val = metric_fn(r)
        series[weapon][idx] = val

    logger.log(
        f"[STATTRACKER] plot series steamid={sid[:8]} metric={metric} "
        f"matches={len(match_keys)} weapons={len(series)}",
        level="DEBUG",
    )

    return {
        "metric_label": metric_def["label"],
        "x_labels": x_labels,
        "series": series,
    }


# ---------------------------------------------------------------------------
# Map-level per-match series (K/D, ADR, Kills, etc. per map played)
# ---------------------------------------------------------------------------

MAP_PLOT_METRICS = {
    "kd_ratio": {
        "label": "K/D Ratio",
        "fn": lambda r: (float(r["kills"]) / max(1, r["deaths"])),
    },
    "kills": {"label": "Kills", "fn": lambda r: r["kills"]},
    "deaths": {"label": "Deaths", "fn": lambda r: r["deaths"]},
    "adr": {
        "label": "ADR",
        "fn": lambda r: (float(r["damage"]) / max(1, r["total_rounds"])) if r["total_rounds"] > 0 else None,
    },
    "damage": {"label": "Damage", "fn": lambda r: r["damage"]},
    "hs_kills": {"label": "HS Kills", "fn": lambda r: r["head_shot_kills"]},
}


def get_map_plot_metric_options():
    return [{"key": k, "label": v["label"]} for k, v in MAP_PLOT_METRICS.items()]


def get_map_match_series(steamid64, maps=None, metric="kd_ratio"):
    """Build plot-ready series for map performance: one line per map, x = match index.

    Returns:
        {
            "metric_label": str,
            "x_labels": ["match #1", ...],
            "series": {
                "de_dust2": [value_or_None, ...],
                ...
            }
        }
    """
    sid = str(steamid64 or "").strip()
    if not sid:
        return {"metric_label": "", "x_labels": [], "series": {}}

    metric_def = MAP_PLOT_METRICS.get(metric, MAP_PLOT_METRICS["kd_ratio"])
    metric_fn = metric_def["fn"]

    rows = stattracker_repo.fetch_player_map_match_series(sid, maps=maps)

    # Build ordered list of unique match points
    match_keys = []
    match_key_set = set()
    x_labels = []
    for r in rows:
        key = (str(r["match_id"]), int(r["map_number"]))
        if key not in match_key_set:
            match_key_set.add(key)
            match_keys.append(key)
            x_labels.append(str(r["map_name"] or "?"))

    match_index = {k: i for i, k in enumerate(match_keys)}

    # Build per-map series
    series: dict[str, list] = {}
    for r in rows:
        map_name = str(r["map_name"] or "unknown")
        key = (str(r["match_id"]), int(r["map_number"]))
        idx = match_index.get(key)
        if idx is None:
            continue

        if map_name not in series:
            series[map_name] = [None] * len(match_keys)

        series[map_name][idx] = metric_fn(r)

    logger.log(
        f"[STATTRACKER] map plot series steamid={sid[:8]} metric={metric} "
        f"matches={len(match_keys)} maps={len(series)}",
        level="DEBUG",
    )

    return {
        "metric_label": metric_def["label"],
        "x_labels": x_labels,
        "series": series,
    }
