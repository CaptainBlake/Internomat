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
