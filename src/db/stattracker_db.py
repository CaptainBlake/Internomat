from .connection_db import executemany_write, get_conn, optional_conn

_WEAPON_FROM = """
    FROM player_map_weapon_stats pmws
    LEFT JOIN weapon_alias wa ON LOWER(wa.raw_weapon) = LOWER(pmws.weapon)
    LEFT JOIN weapon_dim wd ON LOWER(wd.weapon) = LOWER(COALESCE(wa.canonical_weapon, pmws.weapon))
"""


def _normalize_seasons(seasons):
    if seasons is None:
        return None
    out = []
    for s in seasons:
        try:
            out.append(int(s))
        except Exception:
            continue
    return sorted(set(out))


def _season_filter_clause(match_expr, seasons):
    normalized = _normalize_seasons(seasons)
    if normalized is None:
        return "", []
    if not normalized:
        return " AND 1=0 ", []

    placeholders = ",".join("?" for _ in normalized)
    return (
        " AND EXISTS ("
        "SELECT 1 FROM elo_match_season ems "
        f"WHERE ems.match_id = {match_expr} AND ems.season IN ({placeholders})"
        ") ",
        normalized,
    )


def fetch_player_overview():
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                (SELECT COUNT(DISTINCT steam64_id) FROM players) AS tracked_players,
                (SELECT COUNT(*) FROM match_player_stats) AS player_stat_rows,
                (
                    SELECT COUNT(DISTINCT steamid64 || ':' || match_id || ':' || map_number)
                    FROM match_player_stats
                ) AS unique_player_maps
            """
        ).fetchone()

    return row


def fetch_top_player_samples(limit):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT
                COALESCE(name, steamid64) AS player_name,
                steamid64,
                COUNT(*) AS map_entries,
                SUM(COALESCE(kills, 0)) AS total_kills,
                SUM(COALESCE(deaths, 0)) AS total_deaths
            FROM match_player_stats
            GROUP BY steamid64, COALESCE(name, steamid64)
            ORDER BY total_kills DESC, map_entries DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def upsert_player_map_weapon_stats_many(rows, conn=None):
    if not rows:
        return

    query = """
        INSERT INTO player_map_weapon_stats (
            steamid64,
            match_id,
            map_number,
            weapon,
            shots_fired,
            shots_hit,
            kills,
            headshot_kills,
            damage,
            rounds_with_weapon,
            first_seen_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(steamid64, match_id, map_number, weapon) DO UPDATE SET
            shots_fired = excluded.shots_fired,
            shots_hit = excluded.shots_hit,
            kills = excluded.kills,
            headshot_kills = excluded.headshot_kills,
            damage = excluded.damage,
            rounds_with_weapon = excluded.rounds_with_weapon,
            updated_at = excluded.updated_at
    """

    params = [
        (
            str(row.get("steamid64") or ""),
            str(row.get("match_id") or ""),
            int(row.get("map_number") or 0),
            str(row.get("weapon") or ""),
            int(row.get("shots_fired") or 0),
            int(row.get("shots_hit") or 0),
            int(row.get("kills") or 0),
            int(row.get("headshot_kills") or 0),
            int(row.get("damage") or 0),
            int(row.get("rounds_with_weapon") or 0),
            str(row.get("first_seen_at") or ""),
            str(row.get("updated_at") or ""),
        )
        for row in rows
        if isinstance(row, dict)
        and str(row.get("steamid64") or "").strip()
        and str(row.get("match_id") or "").strip()
        and str(row.get("weapon") or "").strip()
    ]

    if not params:
        return

    with optional_conn(conn, commit=True) as c:
        discovered_weapons = sorted({p[3] for p in params if str(p[3]).strip()})
        if discovered_weapons:
            executemany_write(
                c,
                """
                INSERT INTO weapon_dim (weapon, display_name, category, source, is_active, first_seen_at, updated_at)
                VALUES (?, ?, 'unknown', 'observed', 1, datetime('now'), datetime('now'))
                ON CONFLICT(weapon) DO UPDATE SET
                    is_active = 1,
                    updated_at = datetime('now')
                """,
                [(w, w) for w in discovered_weapons],
            )

        executemany_write(c, query, params)


def upsert_player_round_weapon_stats_many(rows, conn=None):
    if not rows:
        return

    query = """
        INSERT INTO player_round_weapon_stats (
            steamid64,
            match_id,
            map_number,
            round_num,
            weapon,
            shots_fired,
            shots_hit,
            kills,
            headshot_kills,
            damage,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(steamid64, match_id, map_number, round_num, weapon) DO UPDATE SET
            shots_fired = excluded.shots_fired,
            shots_hit = excluded.shots_hit,
            kills = excluded.kills,
            headshot_kills = excluded.headshot_kills,
            damage = excluded.damage,
            updated_at = excluded.updated_at
    """

    params = [
        (
            str(row.get("steamid64") or ""),
            str(row.get("match_id") or ""),
            int(row.get("map_number") or 0),
            int(row.get("round_num") or 0),
            str(row.get("weapon") or ""),
            int(row.get("shots_fired") or 0),
            int(row.get("shots_hit") or 0),
            int(row.get("kills") or 0),
            int(row.get("headshot_kills") or 0),
            int(row.get("damage") or 0),
            str(row.get("updated_at") or ""),
        )
        for row in rows
        if isinstance(row, dict)
        and str(row.get("steamid64") or "").strip()
        and str(row.get("match_id") or "").strip()
        and int(row.get("round_num") or 0) > 0
        and str(row.get("weapon") or "").strip()
    ]

    if not params:
        return

    with optional_conn(conn, commit=True) as c:
        discovered_weapons = sorted({p[4] for p in params if str(p[4]).strip()})
        if discovered_weapons:
            executemany_write(
                c,
                """
                INSERT INTO weapon_dim (weapon, display_name, category, source, is_active, first_seen_at, updated_at)
                VALUES (?, ?, 'unknown', 'observed', 1, datetime('now'), datetime('now'))
                ON CONFLICT(weapon) DO UPDATE SET
                    is_active = 1,
                    updated_at = datetime('now')
                """,
                [(w, w) for w in discovered_weapons],
            )

        executemany_write(c, query, params)


def upsert_player_map_movement_stats_many(rows, conn=None):
    if not rows:
        return

    query = """
        INSERT INTO player_map_movement_stats (
            steamid64,
            match_id,
            map_number,
            total_distance_units,
            total_distance_m,
            avg_speed_units_s,
            avg_speed_m_s,
            max_speed_units_s,
            ticks_alive,
            alive_seconds,
            distance_per_round_units,
            freeze_distance_units,
            strafe_distance_units,
            strafe_ratio,
            stationary_ticks,
            sprint_ticks,
            camp_time_s,
            sprint_time_s,
            stationary_ratio,
            sprint_ratio,
            strafe_ticks,
            strafe_time_s,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(steamid64, match_id, map_number) DO UPDATE SET
            total_distance_units = excluded.total_distance_units,
            total_distance_m = excluded.total_distance_m,
            avg_speed_units_s = excluded.avg_speed_units_s,
            avg_speed_m_s = excluded.avg_speed_m_s,
            max_speed_units_s = excluded.max_speed_units_s,
            ticks_alive = excluded.ticks_alive,
            alive_seconds = excluded.alive_seconds,
            distance_per_round_units = excluded.distance_per_round_units,
            freeze_distance_units = excluded.freeze_distance_units,
            strafe_distance_units = excluded.strafe_distance_units,
            strafe_ratio = excluded.strafe_ratio,
            stationary_ticks = excluded.stationary_ticks,
            sprint_ticks = excluded.sprint_ticks,
            camp_time_s = excluded.camp_time_s,
            sprint_time_s = excluded.sprint_time_s,
            stationary_ratio = excluded.stationary_ratio,
            sprint_ratio = excluded.sprint_ratio,
            strafe_ticks = excluded.strafe_ticks,
            strafe_time_s = excluded.strafe_time_s,
            updated_at = excluded.updated_at
    """

    params = [
        (
            str(row.get("steamid64") or ""),
            str(row.get("match_id") or ""),
            int(row.get("map_number") or 0),
            float(row.get("total_distance_units") or 0.0),
            float(row.get("total_distance_m") or 0.0),
            float(row.get("avg_speed_units_s") or 0.0),
            float(row.get("avg_speed_m_s") or 0.0),
            float(row.get("max_speed_units_s") or 0.0),
            int(row.get("ticks_alive") or 0),
            float(row.get("alive_seconds") or 0.0),
            float(row.get("distance_per_round_units") or 0.0),
            float(row.get("freeze_distance_units") or 0.0),
            float(row.get("strafe_distance_units") or 0.0),
            float(row.get("strafe_ratio") or 0.0),
            int(row.get("stationary_ticks") or 0),
            int(row.get("sprint_ticks") or 0),
            float(row.get("camp_time_s") or 0.0),
            float(row.get("sprint_time_s") or 0.0),
            float(row.get("stationary_ratio") or 0.0),
            float(row.get("sprint_ratio") or 0.0),
            int(row.get("strafe_ticks") or 0),
            float(row.get("strafe_time_s") or 0.0),
            str(row.get("updated_at") or ""),
        )
        for row in rows
        if isinstance(row, dict)
        and str(row.get("steamid64") or "").strip()
        and str(row.get("match_id") or "").strip()
    ]

    if not params:
        return

    with optional_conn(conn, commit=True) as c:
        executemany_write(c, query, params)


def upsert_player_round_movement_stats_many(rows, conn=None):
    if not rows:
        return

    query = """
        INSERT INTO player_round_movement_stats (
            steamid64,
            match_id,
            map_number,
            round_num,
            side,
            distance_units,
            live_distance_units,
            freeze_distance_units,
            strafe_distance_units,
            strafe_ratio,
            avg_speed_units_s,
            max_speed_units_s,
            ticks_alive,
            alive_seconds,
            stationary_ticks,
            camp_time_s,
            sprint_ticks,
            sprint_time_s,
            strafe_ticks,
            strafe_time_s,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(steamid64, match_id, map_number, round_num) DO UPDATE SET
            side = excluded.side,
            distance_units = excluded.distance_units,
            live_distance_units = excluded.live_distance_units,
            freeze_distance_units = excluded.freeze_distance_units,
            strafe_distance_units = excluded.strafe_distance_units,
            strafe_ratio = excluded.strafe_ratio,
            avg_speed_units_s = excluded.avg_speed_units_s,
            max_speed_units_s = excluded.max_speed_units_s,
            ticks_alive = excluded.ticks_alive,
            alive_seconds = excluded.alive_seconds,
            stationary_ticks = excluded.stationary_ticks,
            camp_time_s = excluded.camp_time_s,
            sprint_ticks = excluded.sprint_ticks,
            sprint_time_s = excluded.sprint_time_s,
            strafe_ticks = excluded.strafe_ticks,
            strafe_time_s = excluded.strafe_time_s,
            updated_at = excluded.updated_at
    """

    params = [
        (
            str(row.get("steamid64") or ""),
            str(row.get("match_id") or ""),
            int(row.get("map_number") or 0),
            int(row.get("round_num") or 0),
            str(row.get("side") or ""),
            float(row.get("distance_units") or 0.0),
            float(row.get("live_distance_units") or 0.0),
            float(row.get("freeze_distance_units") or 0.0),
            float(row.get("strafe_distance_units") or 0.0),
            float(row.get("strafe_ratio") or 0.0),
            float(row.get("avg_speed_units_s") or 0.0),
            float(row.get("max_speed_units_s") or 0.0),
            int(row.get("ticks_alive") or 0),
            float(row.get("alive_seconds") or 0.0),
            int(row.get("stationary_ticks") or 0),
            float(row.get("camp_time_s") or 0.0),
            int(row.get("sprint_ticks") or 0),
            float(row.get("sprint_time_s") or 0.0),
            int(row.get("strafe_ticks") or 0),
            float(row.get("strafe_time_s") or 0.0),
            str(row.get("updated_at") or ""),
        )
        for row in rows
        if isinstance(row, dict)
        and str(row.get("steamid64") or "").strip()
        and str(row.get("match_id") or "").strip()
        and int(row.get("round_num") or 0) > 0
    ]

    if not params:
        return

    with optional_conn(conn, commit=True) as c:
        executemany_write(c, query, params)


def upsert_player_round_timeline_bins_many(rows, conn=None):
    if not rows:
        return

    query = """
        INSERT INTO player_round_timeline_bins (
            steamid64,
            match_id,
            map_number,
            round_num,
            bin_index,
            bin_start_sec,
            median_speed_m_s,
            mean_speed_m_s,
            p25_speed_m_s,
            p75_speed_m_s,
            max_speed_m_s,
            alive_ratio,
            samples,
            speed_samples,
            side,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(steamid64, match_id, map_number, round_num, bin_index) DO UPDATE SET
            bin_start_sec = excluded.bin_start_sec,
            median_speed_m_s = excluded.median_speed_m_s,
            mean_speed_m_s = excluded.mean_speed_m_s,
            p25_speed_m_s = excluded.p25_speed_m_s,
            p75_speed_m_s = excluded.p75_speed_m_s,
            max_speed_m_s = excluded.max_speed_m_s,
            alive_ratio = excluded.alive_ratio,
            samples = excluded.samples,
            speed_samples = excluded.speed_samples,
            side = excluded.side,
            updated_at = excluded.updated_at
    """

    params = [
        (
            str(row.get("steamid64") or ""),
            str(row.get("match_id") or ""),
            int(row.get("map_number") or 0),
            int(row.get("round_num") or 0),
            int(row.get("bin_index") or 0),
            float(row.get("bin_start_sec") or 0.0),
            float(row.get("median_speed_m_s") or 0.0),
            float(row.get("mean_speed_m_s") or 0.0),
            float(row.get("p25_speed_m_s") or 0.0),
            float(row.get("p75_speed_m_s") or 0.0),
            float(row.get("max_speed_m_s") or 0.0),
            float(row.get("alive_ratio") or 0.0),
            int(row.get("samples") or 0),
            int(row.get("speed_samples") or 0),
            str(row.get("side") or ""),
            str(row.get("updated_at") or ""),
        )
        for row in rows
        if isinstance(row, dict)
        and str(row.get("steamid64") or "").strip()
        and str(row.get("match_id") or "").strip()
        and int(row.get("round_num") or 0) > 0
    ]

    if not params:
        return

    with optional_conn(conn, commit=True) as c:
        executemany_write(c, query, params)


def upsert_player_round_events_many(rows, conn=None):
    if not rows:
        return

    query = """
        INSERT INTO player_round_events (
            steamid64,
            match_id,
            map_number,
            round_num,
            side,
            opening_attempt,
            opening_win,
            trade_kill_count,
            traded_death_count,
            clutch_enemy_count,
            clutch_win,
            won_round,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(steamid64, match_id, map_number, round_num) DO UPDATE SET
            side = excluded.side,
            opening_attempt = excluded.opening_attempt,
            opening_win = excluded.opening_win,
            trade_kill_count = excluded.trade_kill_count,
            traded_death_count = excluded.traded_death_count,
            clutch_enemy_count = excluded.clutch_enemy_count,
            clutch_win = excluded.clutch_win,
            won_round = excluded.won_round,
            updated_at = excluded.updated_at
    """

    params = [
        (
            str(row.get("steamid64") or ""),
            str(row.get("match_id") or ""),
            int(row.get("map_number") or 0),
            int(row.get("round_num") or 0),
            str(row.get("side") or ""),
            int(row.get("opening_attempt") or 0),
            int(row.get("opening_win") or 0),
            int(row.get("trade_kill_count") or 0),
            int(row.get("traded_death_count") or 0),
            int(row.get("clutch_enemy_count") or 0),
            int(row.get("clutch_win") or 0),
            int(row.get("won_round") or 0),
            str(row.get("updated_at") or ""),
        )
        for row in rows
        if isinstance(row, dict)
        and str(row.get("steamid64") or "").strip()
        and str(row.get("match_id") or "").strip()
        and int(row.get("round_num") or 0) > 0
    ]

    if not params:
        return

    with optional_conn(conn, commit=True) as c:
        executemany_write(c, query, params)


def upsert_player_kill_matrix_many(rows, conn=None):
    if not rows:
        return

    query = """
        INSERT INTO player_kill_matrix (
            attacker_steamid64,
            victim_steamid64,
            match_id,
            map_number,
            kills,
            headshot_kills,
            teamkills,
            damage,
            assists,
            flash_assists,
            flashes,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(attacker_steamid64, victim_steamid64, match_id, map_number) DO UPDATE SET
            kills = excluded.kills,
            headshot_kills = excluded.headshot_kills,
            teamkills = excluded.teamkills,
            damage = excluded.damage,
            assists = excluded.assists,
            flash_assists = excluded.flash_assists,
            flashes = excluded.flashes,
            updated_at = excluded.updated_at
    """

    params = [
        (
            str(row.get("attacker_steamid64") or ""),
            str(row.get("victim_steamid64") or ""),
            str(row.get("match_id") or ""),
            int(row.get("map_number") or 0),
            int(row.get("kills") or 0),
            int(row.get("headshot_kills") or 0),
            int(row.get("teamkills") or 0),
            int(row.get("damage") or 0),
            int(row.get("assists") or 0),
            int(row.get("flash_assists") or 0),
            int(row.get("flashes") or 0),
            str(row.get("updated_at") or ""),
        )
        for row in rows
        if isinstance(row, dict)
        and str(row.get("attacker_steamid64") or "").strip()
        and str(row.get("victim_steamid64") or "").strip()
        and str(row.get("match_id") or "").strip()
    ]

    if not params:
        return

    with optional_conn(conn, commit=True) as c:
        executemany_write(c, query, params)


def fetch_player_kill_relationships(steamid64, seasons=None):
    """Return favourite target + arch-nemesis for a player.

    Returns a list of rows with columns:
        opponent_steamid64, opponent_name, kills_dealt, kills_received,
        hs_dealt, hs_received, teamkills_dealt, teamkills_received,
        damage_dealt, damage_received, assists_dealt, assists_received,
        flash_assists_dealt, flash_assists_received,
        flashes_dealt, flashes_received
    ordered by total interactions descending.
    """
    sid = str(steamid64 or "").strip()
    if not sid:
        return []

    season_sql_a, season_params_a = _season_filter_clause("a.match_id", seasons)
    season_sql_r, season_params_r = _season_filter_clause("r.match_id", seasons)

    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT
                opponent,
                COALESCE(p.name, opponent) AS opponent_name,
                COALESCE(SUM(kills_dealt), 0) AS kills_dealt,
                COALESCE(SUM(kills_received), 0) AS kills_received,
                COALESCE(SUM(hs_dealt), 0) AS hs_dealt,
                COALESCE(SUM(hs_received), 0) AS hs_received,
                COALESCE(SUM(tk_dealt), 0) AS teamkills_dealt,
                COALESCE(SUM(tk_received), 0) AS teamkills_received,
                COALESCE(SUM(dmg_dealt), 0) AS damage_dealt,
                COALESCE(SUM(dmg_received), 0) AS damage_received,
                COALESCE(SUM(ast_dealt), 0) AS assists_dealt,
                COALESCE(SUM(ast_received), 0) AS assists_received,
                COALESCE(SUM(fa_dealt), 0) AS flash_assists_dealt,
                COALESCE(SUM(fa_received), 0) AS flash_assists_received,
                COALESCE(SUM(fl_dealt), 0) AS flashes_dealt,
                COALESCE(SUM(fl_received), 0) AS flashes_received
            FROM (
                SELECT
                    a.victim_steamid64 AS opponent,
                    SUM(a.kills) AS kills_dealt,
                    0 AS kills_received,
                    SUM(a.headshot_kills) AS hs_dealt,
                    0 AS hs_received,
                    SUM(a.teamkills) AS tk_dealt,
                    0 AS tk_received,
                    SUM(a.damage) AS dmg_dealt,
                    0 AS dmg_received,
                    SUM(a.assists) AS ast_dealt,
                    0 AS ast_received,
                    SUM(a.flash_assists) AS fa_dealt,
                    0 AS fa_received,
                    SUM(a.flashes) AS fl_dealt,
                    0 AS fl_received
                FROM player_kill_matrix a
                WHERE a.attacker_steamid64 = ?
                    {season_sql_a}
                GROUP BY a.victim_steamid64

                UNION ALL

                SELECT
                    r.attacker_steamid64 AS opponent,
                    0 AS kills_dealt,
                    SUM(r.kills) AS kills_received,
                    0 AS hs_dealt,
                    SUM(r.headshot_kills) AS hs_received,
                    0 AS tk_dealt,
                    SUM(r.teamkills) AS tk_received,
                    0 AS dmg_dealt,
                    SUM(r.damage) AS dmg_received,
                    0 AS ast_dealt,
                    SUM(r.assists) AS ast_received,
                    0 AS fa_dealt,
                    SUM(r.flash_assists) AS fa_received,
                    0 AS fl_dealt,
                    SUM(r.flashes) AS fl_received
                FROM player_kill_matrix r
                WHERE r.victim_steamid64 = ?
                    {season_sql_r}
                GROUP BY r.attacker_steamid64
            ) combined
            LEFT JOIN players p ON p.steam64_id = combined.opponent
            WHERE opponent != ?
            GROUP BY opponent
            ORDER BY (COALESCE(SUM(kills_dealt), 0) + COALESCE(SUM(kills_received), 0)) DESC
            """,
            (sid, *season_params_a, sid, *season_params_r, sid),
        ).fetchall()


def fetch_player_combat_summary(steamid64, seasons=None):
    """Aggregate combat-related stats from match_player_stats + player_round_events."""
    sid = str(steamid64 or "").strip()
    if not sid:
        return None

    season_sql, season_params = _season_filter_clause("mps.match_id", seasons)
    tk_season_sql, tk_season_params = _season_filter_clause("pkm.match_id", seasons)

    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT
                COUNT(*) AS maps_played,
                COALESCE(SUM(mps.kills), 0) AS total_kills,
                COALESCE(SUM(mps.deaths), 0) AS total_deaths,
                COALESCE(SUM(mps.assists), 0) AS total_assists,
                COALESCE(SUM(mps.damage), 0) AS total_damage,
                COALESCE(SUM(mps.head_shot_kills), 0) AS total_hs_kills,
                COALESCE(SUM(mps.flash_count), 0) AS total_flashes_thrown,
                COALESCE(SUM(mps.enemies_flashed), 0) AS total_enemies_flashed,
                COALESCE(SUM(mps.entry_count), 0) AS total_entry_attempts,
                COALESCE(SUM(mps.entry_wins), 0) AS total_entry_wins,
                COALESCE(SUM(mps.v1_count), 0) AS total_clutch_1v1,
                COALESCE(SUM(mps.v1_wins), 0) AS total_clutch_1v1_wins,
                COALESCE(SUM(mps.v2_count), 0) AS total_clutch_1v2,
                COALESCE(SUM(mps.v2_wins), 0) AS total_clutch_1v2_wins,
                COALESCE(SUM(mps.enemy5ks), 0) AS total_aces,
                COALESCE(SUM(mps.enemy4ks), 0) AS total_4ks,
                COALESCE(SUM(mps.enemy3ks), 0) AS total_3ks,
                COALESCE(tk.total_teamkills, 0) AS total_teamkills
            FROM match_player_stats mps
            LEFT JOIN (
                SELECT
                    attacker_steamid64,
                    SUM(teamkills) AS total_teamkills
                FROM player_kill_matrix pkm
                WHERE attacker_steamid64 = ?
                    {tk_season_sql}
                GROUP BY attacker_steamid64
            ) tk ON tk.attacker_steamid64 = mps.steamid64
            WHERE mps.steamid64 = ?
                {season_sql}
            """,
            (sid, *tk_season_params, sid, *season_params),
        ).fetchone()


def fetch_player_elo_rating(steamid64):
    """Return the current Elo rating for a player, or None if not yet rated."""
    sid = str(steamid64 or "").strip()
    if not sid:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT elo FROM elo_ratings WHERE steamid64 = ?",
            (sid,),
        ).fetchone()
        return float(row["elo"]) if row else None


def fetch_elo_seasons():
    """Return all Elo season rows ordered by season ASC."""
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM elo_seasons ORDER BY season ASC"
        ).fetchall()


def fetch_player_elo_history(steamid64, season=None):
    """Return chronological Elo snapshots for a player within a season."""
    sid = str(steamid64 or "").strip()
    if not sid:
        return []

    conditions = ["eh.steamid64 = ?"]
    params = [sid]

    if season is not None:
        conditions.append(
            "EXISTS (SELECT 1 FROM elo_match_season ems WHERE ems.match_id = eh.match_id AND ems.season = ?)"
        )
        params.append(int(season))

    where = " AND ".join(conditions)

    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT
                eh.match_id,
                eh.elo_before,
                eh.elo_after,
                eh.elo_delta,
                eh.result,
                eh.team_name,
                eh.adr,
                COALESCE(mm.map_name, 'unknown') AS map_name,
                COALESCE(mm.start_time, m.start_time, '') AS start_time
            FROM elo_history eh
            LEFT JOIN match_maps mm
              ON mm.match_id = eh.match_id AND mm.map_number = 0
            LEFT JOIN matches m ON m.match_id = eh.match_id
            WHERE {where}
            ORDER BY COALESCE(mm.start_time, m.start_time, eh.match_id) ASC
            """,
            tuple(params),
        ).fetchall()


def fetch_player_movement_match_series(steamid64, maps=None, seasons=None):
    sid = str(steamid64 or "").strip()
    if not sid:
        return []

    if maps is not None and len(maps) == 0:
        return []

    conditions = ["pmms.steamid64 = ?"]
    params = [sid]

    if maps:
        placeholders = ",".join("?" for _ in maps)
        conditions.append(f"COALESCE(mm.map_name, 'unknown') IN ({placeholders})")
        params.extend([str(m) for m in maps])

    season_sql, season_params = _season_filter_clause("pmms.match_id", seasons)
    params.extend(season_params)

    where = " AND ".join(conditions)

    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT
                pmms.match_id,
                pmms.map_number,
                COALESCE(mm.map_name, 'unknown') AS map_name,
                COALESCE(mm.start_time, m.start_time, '') AS start_time,
                COALESCE(pmms.total_distance_units, 0) AS total_distance_units,
                COALESCE(pmms.total_distance_m, 0) AS total_distance_m,
                COALESCE(pmms.avg_speed_units_s, 0) AS avg_speed_units_s,
                COALESCE(pmms.avg_speed_m_s, 0) AS avg_speed_m_s,
                COALESCE(pmms.max_speed_units_s, 0) AS max_speed_units_s,
                COALESCE(pmms.ticks_alive, 0) AS ticks_alive,
                COALESCE(pmms.alive_seconds, 0) AS alive_seconds,
                COALESCE(pmms.distance_per_round_units, 0) AS distance_per_round_units,
                COALESCE(pmms.freeze_distance_units, 0) AS freeze_distance_units,
                COALESCE(pmms.strafe_distance_units, 0) AS strafe_distance_units,
                COALESCE(pmms.stationary_ticks, 0) AS stationary_ticks,
                COALESCE(pmms.sprint_ticks, 0) AS sprint_ticks,
                CASE
                    WHEN COALESCE(pmms.camp_time_s, 0) > 0
                    THEN pmms.camp_time_s
                    ELSE COALESCE(pmms.stationary_ratio, 0) * COALESCE(pmms.alive_seconds, 0)
                END AS camp_time_s,
                CASE
                    WHEN COALESCE(pmms.sprint_time_s, 0) > 0
                    THEN pmms.sprint_time_s
                    ELSE COALESCE(pmms.sprint_ratio, 0) * COALESCE(pmms.alive_seconds, 0)
                END AS sprint_time_s,
                CASE
                    WHEN COALESCE(pmms.alive_seconds, 0) > 0
                    THEN (
                        CASE
                            WHEN COALESCE(pmms.camp_time_s, 0) > 0
                            THEN pmms.camp_time_s
                            ELSE COALESCE(pmms.stationary_ratio, 0) * pmms.alive_seconds
                        END
                    ) / pmms.alive_seconds
                    ELSE COALESCE(pmms.stationary_ratio, 0)
                END AS stationary_ratio,
                CASE
                    WHEN COALESCE(pmms.alive_seconds, 0) > 0
                    THEN (
                        CASE
                            WHEN COALESCE(pmms.sprint_time_s, 0) > 0
                            THEN pmms.sprint_time_s
                            ELSE COALESCE(pmms.sprint_ratio, 0) * pmms.alive_seconds
                        END
                    ) / pmms.alive_seconds
                    ELSE COALESCE(pmms.sprint_ratio, 0)
                END AS sprint_ratio,
                COALESCE(pmms.strafe_ticks, 0) AS strafe_ticks,
                CASE
                    WHEN COALESCE(pmms.strafe_time_s, 0) > 0
                    THEN pmms.strafe_time_s
                    ELSE COALESCE(pmms.strafe_ratio, 0) * COALESCE(pmms.alive_seconds, 0)
                END AS strafe_time_s,
                CASE
                    WHEN COALESCE(pmms.alive_seconds, 0) > 0
                    THEN (
                        CASE
                            WHEN COALESCE(pmms.strafe_time_s, 0) > 0
                            THEN pmms.strafe_time_s
                            ELSE COALESCE(pmms.strafe_ratio, 0) * pmms.alive_seconds
                        END
                    ) / pmms.alive_seconds
                    ELSE COALESCE(pmms.strafe_ratio, 0)
                END AS strafe_ratio
            FROM player_map_movement_stats pmms
            LEFT JOIN match_maps mm
              ON mm.match_id = pmms.match_id AND mm.map_number = pmms.map_number
            LEFT JOIN matches m ON m.match_id = pmms.match_id
            WHERE {where}
                            {season_sql}
            ORDER BY COALESCE(mm.start_time, m.start_time, pmms.match_id) ASC,
                     pmms.map_number ASC
            """,
            tuple(params),
        ).fetchall()


def fetch_player_movement_round_series(steamid64, maps=None, seasons=None):
    sid = str(steamid64 or "").strip()
    if not sid:
        return []

    if maps is not None and len(maps) == 0:
        return []

    conditions = ["prms.steamid64 = ?"]
    params = [sid]

    if maps:
        placeholders = ",".join("?" for _ in maps)
        conditions.append(f"COALESCE(mm.map_name, 'unknown') IN ({placeholders})")
        params.extend([str(m) for m in maps])

    season_sql, season_params = _season_filter_clause("prms.match_id", seasons)
    params.extend(season_params)

    where = " AND ".join(conditions)

    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT
                prms.match_id,
                prms.map_number,
                prms.round_num,
                COALESCE(mm.map_name, 'unknown') AS map_name,
                COALESCE(mm.start_time, m.start_time, '') AS start_time,
                COALESCE(prms.live_distance_units, prms.distance_units, 0) AS total_distance_units,
                COALESCE(prms.live_distance_units, prms.distance_units, 0) * 0.0254 AS total_distance_m,
                COALESCE(prms.avg_speed_units_s, 0) AS avg_speed_units_s,
                COALESCE(prms.avg_speed_units_s, 0) * 0.0254 AS avg_speed_m_s,
                COALESCE(prms.max_speed_units_s, 0) AS max_speed_units_s,
                COALESCE(prms.ticks_alive, 0) AS ticks_alive,
                COALESCE(prms.alive_seconds, 0) AS alive_seconds,
                COALESCE(prms.strafe_distance_units, 0) AS strafe_distance_units,
                CASE
                    WHEN COALESCE(prms.alive_seconds, 0) > 0
                    THEN (
                        CASE
                            WHEN COALESCE(prms.strafe_time_s, 0) > 0
                            THEN prms.strafe_time_s
                            WHEN COALESCE(prms.ticks_alive, 0) > 0
                            THEN CAST(COALESCE(prms.strafe_ticks, 0) AS REAL) / CAST(prms.ticks_alive AS REAL) * prms.alive_seconds
                            ELSE COALESCE(prms.strafe_ratio, 0) * prms.alive_seconds
                        END
                    ) / prms.alive_seconds
                    ELSE COALESCE(prms.strafe_ratio, 0)
                END AS strafe_ratio,
                COALESCE(prms.stationary_ticks, 0) AS stationary_ticks,
                COALESCE(prms.sprint_ticks, 0) AS sprint_ticks,
                COALESCE(prms.strafe_ticks, 0) AS strafe_ticks,
                CASE
                    WHEN COALESCE(prms.alive_seconds, 0) > 0
                    THEN (
                        CASE
                            WHEN COALESCE(prms.camp_time_s, 0) > 0
                            THEN prms.camp_time_s
                            WHEN COALESCE(prms.ticks_alive, 0) > 0
                            THEN CAST(COALESCE(prms.stationary_ticks, 0) AS REAL) / CAST(prms.ticks_alive AS REAL) * prms.alive_seconds
                            ELSE 0
                        END
                    ) / prms.alive_seconds
                    ELSE 0
                END AS stationary_ratio,
                CASE
                    WHEN COALESCE(prms.alive_seconds, 0) > 0
                    THEN (
                        CASE
                            WHEN COALESCE(prms.sprint_time_s, 0) > 0
                            THEN prms.sprint_time_s
                            WHEN COALESCE(prms.ticks_alive, 0) > 0
                            THEN CAST(COALESCE(prms.sprint_ticks, 0) AS REAL) / CAST(prms.ticks_alive AS REAL) * prms.alive_seconds
                            ELSE 0
                        END
                    ) / prms.alive_seconds
                    ELSE 0
                END AS sprint_ratio,
                CASE
                    WHEN COALESCE(prms.camp_time_s, 0) > 0
                    THEN prms.camp_time_s
                    WHEN COALESCE(prms.ticks_alive, 0) > 0
                    THEN CAST(COALESCE(prms.stationary_ticks, 0) AS REAL) / CAST(prms.ticks_alive AS REAL) * COALESCE(prms.alive_seconds, 0)
                    ELSE 0
                END AS camp_time_s,
                CASE
                    WHEN COALESCE(prms.sprint_time_s, 0) > 0
                    THEN prms.sprint_time_s
                    WHEN COALESCE(prms.ticks_alive, 0) > 0
                    THEN CAST(COALESCE(prms.sprint_ticks, 0) AS REAL) / CAST(prms.ticks_alive AS REAL) * COALESCE(prms.alive_seconds, 0)
                    ELSE 0
                END AS sprint_time_s,
                CASE
                    WHEN COALESCE(prms.strafe_time_s, 0) > 0
                    THEN prms.strafe_time_s
                    WHEN COALESCE(prms.ticks_alive, 0) > 0
                    THEN CAST(COALESCE(prms.strafe_ticks, 0) AS REAL) / CAST(prms.ticks_alive AS REAL) * COALESCE(prms.alive_seconds, 0)
                    ELSE 0
                END AS strafe_time_s
            FROM player_round_movement_stats prms
            LEFT JOIN match_maps mm
              ON mm.match_id = prms.match_id AND mm.map_number = prms.map_number
            LEFT JOIN matches m ON m.match_id = prms.match_id
            WHERE {where}
                            {season_sql}
            ORDER BY COALESCE(mm.start_time, m.start_time, prms.match_id) ASC,
                     prms.map_number ASC,
                     prms.round_num ASC
            """,
            tuple(params),
        ).fetchall()


def fetch_player_weapon_round_series(steamid64, weapons=None, map_name=None, seasons=None):
    sid = str(steamid64 or "").strip()
    if not sid:
        return []

    if weapons is not None and len(weapons) == 0:
        return []

    conditions = ["prws.steamid64 = ?"]
    params = [sid]

    if map_name and str(map_name).strip().lower() != "all":
        conditions.append("COALESCE(mm.map_name, 'unknown') = ?")
        params.append(str(map_name).strip())

    if weapons:
        placeholders = ",".join("?" for _ in weapons)
        conditions.append(f"COALESCE(wa.canonical_weapon, prws.weapon) IN ({placeholders})")
        params.extend([str(w) for w in weapons])

    season_sql, season_params = _season_filter_clause("prws.match_id", seasons)
    params.extend(season_params)

    where = " AND ".join(conditions)

    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT
                prws.match_id,
                prws.map_number,
                prws.round_num,
                COALESCE(mm.map_name, 'unknown') AS map_name,
                COALESCE(mm.start_time, m.start_time, '') AS start_time,
                COALESCE(wa.canonical_weapon, prws.weapon) AS weapon,
                COALESCE(NULLIF(wd.category, ''), 'unknown') AS category,
                COALESCE(prws.shots_fired, 0) AS shots_fired,
                COALESCE(prws.shots_hit, 0) AS shots_hit,
                COALESCE(prws.kills, 0) AS kills,
                COALESCE(prws.headshot_kills, 0) AS headshot_kills,
                COALESCE(prws.damage, 0) AS damage
            FROM player_round_weapon_stats prws
            LEFT JOIN weapon_alias wa ON LOWER(wa.raw_weapon) = LOWER(prws.weapon)
            LEFT JOIN weapon_dim wd ON LOWER(wd.weapon) = LOWER(COALESCE(wa.canonical_weapon, prws.weapon))
            LEFT JOIN match_maps mm
              ON mm.match_id = prws.match_id AND mm.map_number = prws.map_number
            LEFT JOIN matches m ON m.match_id = prws.match_id
            WHERE {where}
                            {season_sql}
            ORDER BY COALESCE(mm.start_time, m.start_time, prws.match_id) ASC,
                     prws.map_number ASC,
                     prws.round_num ASC,
                     weapon ASC
            """,
            tuple(params),
        ).fetchall()


def fetch_player_filter_options():
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT
                mps.steamid64 AS steamid64,
                COALESCE(MAX(NULLIF(mps.name, '')), mps.steamid64) AS player_name,
                COUNT(*) AS map_entries
            FROM match_player_stats mps
            GROUP BY mps.steamid64
            ORDER BY map_entries DESC, player_name COLLATE NOCASE ASC
            """
        ).fetchall()


def fetch_player_overall_metrics(steamid64, seasons=None):
    season_sql, season_params = _season_filter_clause("mps.match_id", seasons)
    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT
                COUNT(*) AS maps_played,
                SUM(COALESCE(mps.kills, 0)) AS total_kills,
                SUM(COALESCE(mps.deaths, 0)) AS total_deaths,
                SUM(COALESCE(mps.assists, 0)) AS total_assists,
                SUM(COALESCE(mps.damage, 0)) AS total_damage,
                SUM(COALESCE(mps.head_shot_kills, 0)) AS total_headshot_kills,
                SUM(COALESCE(mm.team1_score, 0) + COALESCE(mm.team2_score, 0)) AS total_rounds,
                SUM(CASE WHEN COALESCE(mm.winner, '') = COALESCE(mps.team, '') THEN 1 ELSE 0 END) AS map_wins,
                AVG(mps.kast) AS avg_kast,
                AVG(mps.impact) AS avg_impact,
                AVG(mps.rating) AS avg_rating
            FROM match_player_stats mps
            LEFT JOIN match_maps mm
              ON mm.match_id = mps.match_id
             AND mm.map_number = mps.map_number
            WHERE mps.steamid64 = ?
                            {season_sql}
            """,
                        (str(steamid64), *season_params),
        ).fetchone()


def fetch_player_overall_movement_metrics(steamid64, seasons=None):
    season_sql, season_params = _season_filter_clause("pmms.match_id", seasons)
    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT
                SUM(COALESCE(pmms.total_distance_units, 0)) AS total_distance_units,
                SUM(COALESCE(pmms.strafe_distance_units, 0)) AS strafe_distance_units,
                SUM(COALESCE(pmms.alive_seconds, 0)) AS alive_seconds,
                SUM(
                    CASE
                        WHEN COALESCE(pmms.strafe_time_s, 0) > 0
                        THEN pmms.strafe_time_s
                        ELSE COALESCE(pmms.strafe_ratio, 0) * COALESCE(pmms.alive_seconds, 0)
                    END
                ) AS strafe_time_s,
                SUM(
                    CASE
                        WHEN COALESCE(pmms.sprint_time_s, 0) > 0
                        THEN pmms.sprint_time_s
                        ELSE COALESCE(pmms.sprint_ratio, 0) * COALESCE(pmms.alive_seconds, 0)
                    END
                ) AS sprint_time_s,
                SUM(
                    CASE
                        WHEN COALESCE(pmms.camp_time_s, 0) > 0
                        THEN pmms.camp_time_s
                        ELSE COALESCE(pmms.stationary_ratio, 0) * COALESCE(pmms.alive_seconds, 0)
                    END
                ) AS camp_time_s
            FROM player_map_movement_stats pmms
            WHERE pmms.steamid64 = ?
                            {season_sql}
            """,
                        (str(steamid64), *season_params),
        ).fetchone()


def fetch_player_map_stats(steamid64, seasons=None):
    season_sql, season_params = _season_filter_clause("mps.match_id", seasons)
    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT
                COALESCE(mm.map_name, 'unknown') AS map_name,
                COUNT(*) AS maps_played,
                SUM(COALESCE(mps.kills, 0)) AS kills,
                SUM(COALESCE(mps.deaths, 0)) AS deaths,
                SUM(COALESCE(mps.damage, 0)) AS damage,
                SUM(COALESCE(mm.team1_score, 0) + COALESCE(mm.team2_score, 0)) AS rounds_played,
                SUM(CASE WHEN COALESCE(mm.winner, '') = COALESCE(mps.team, '') THEN 1 ELSE 0 END) AS map_wins
            FROM match_player_stats mps
            LEFT JOIN match_maps mm
              ON mm.match_id = mps.match_id
             AND mm.map_number = mps.map_number
            WHERE mps.steamid64 = ?
                            {season_sql}
            GROUP BY COALESCE(mm.map_name, 'unknown')
            ORDER BY maps_played DESC, map_name COLLATE NOCASE ASC
            """,
                        (str(steamid64), *season_params),
        ).fetchall()


def fetch_player_weapon_categories(steamid64, seasons=None):
    season_sql, season_params = _season_filter_clause("pmws.match_id", seasons)
    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT
                COALESCE(NULLIF(wd.category, ''), 'unknown') AS category,
                COUNT(*) AS rows_count
            {_WEAPON_FROM}
            WHERE pmws.steamid64 = ?
              {season_sql}
            GROUP BY COALESCE(NULLIF(wd.category, ''), 'unknown')
            ORDER BY category COLLATE NOCASE ASC
            """,
            (str(steamid64), *season_params),
        ).fetchall()


def fetch_player_weapon_stats(steamid64, min_shots=1, weapon_category=None, seasons=None):
    category_sql = ""
    params = [str(steamid64)]
    selected_category = str(weapon_category or "").strip().lower()
    if selected_category.endswith("s") and len(selected_category) > 3:
        selected_category = selected_category[:-1]
    if selected_category and selected_category != "all":
        plural = selected_category if selected_category.endswith("s") else f"{selected_category}s"
        category_sql = "AND LOWER(COALESCE(NULLIF(wd.category, ''), 'unknown')) IN (?, ?)"
        params.extend([selected_category, plural])
    season_sql, season_params = _season_filter_clause("pmws.match_id", seasons)
    params.extend(season_params)
    params.append(int(min_shots))

    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT
                COALESCE(wa.canonical_weapon, pmws.weapon) AS weapon,
                COALESCE(NULLIF(wd.category, ''), 'unknown') AS category,
                SUM(COALESCE(shots_fired, 0)) AS shots_fired,
                SUM(COALESCE(shots_hit, 0)) AS shots_hit,
                SUM(COALESCE(kills, 0)) AS kills,
                SUM(COALESCE(headshot_kills, 0)) AS headshot_kills,
                SUM(COALESCE(damage, 0)) AS damage,
                SUM(COALESCE(rounds_with_weapon, 0)) AS rounds_with_weapon
            {_WEAPON_FROM}
            WHERE pmws.steamid64 = ?
              {category_sql}
                            {season_sql}
            GROUP BY COALESCE(wa.canonical_weapon, pmws.weapon), COALESCE(NULLIF(wd.category, ''), 'unknown')
            HAVING SUM(COALESCE(shots_fired, 0)) >= ?
            ORDER BY shots_fired DESC, weapon COLLATE NOCASE ASC
            """,
            tuple(params),
        ).fetchall()


def fetch_player_weapon_kill_attribution_deltas(steamid64, seasons=None):
    season_sql, season_params = _season_filter_clause("mps.match_id", seasons)
    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT
                mps.match_id,
                mps.map_number,
                COALESCE(mm.map_name, 'unknown') AS map_name,
                COALESCE(mps.kills, 0) AS total_kills,
                COALESCE(w.weapon_kills, 0) AS weapon_kills,
                (COALESCE(mps.kills, 0) - COALESCE(w.weapon_kills, 0)) AS delta
            FROM match_player_stats mps
            LEFT JOIN match_maps mm
              ON mm.match_id = mps.match_id
             AND mm.map_number = mps.map_number
            LEFT JOIN (
                SELECT
                    pmws.steamid64,
                    pmws.match_id,
                    pmws.map_number,
                    SUM(COALESCE(pmws.kills, 0)) AS weapon_kills
                FROM player_map_weapon_stats pmws
                GROUP BY pmws.steamid64, pmws.match_id, pmws.map_number
            ) w
              ON w.steamid64 = mps.steamid64
             AND w.match_id = mps.match_id
             AND w.map_number = mps.map_number
            WHERE mps.steamid64 = ?
                            {season_sql}
              AND (COALESCE(mps.kills, 0) - COALESCE(w.weapon_kills, 0)) > 0
            ORDER BY mps.match_id DESC, mps.map_number ASC
            """,
                        (str(steamid64), *season_params),
        ).fetchall()


def fetch_player_weapon_match_series(steamid64, weapons=None, map_name=None, seasons=None):
    """Return per-match, per-weapon rows for a player ordered chronologically.

    Each row contains: match_id, map_number, map_name, start_time,
    weapon, category, shots_fired, shots_hit, kills, headshot_kills,
    damage, rounds_with_weapon, total_rounds.

    Optional filters:
        weapons  – list of canonical weapon names to include (None = all)
        map_name – restrict to a specific map (None = all maps)
    """
    sid = str(steamid64 or "").strip()
    if not sid:
        return []

    # Explicit empty selection should yield no rows (not "all weapons").
    if weapons is not None and len(weapons) == 0:
        return []

    conditions = ["pmws.steamid64 = ?"]
    params: list = [sid]

    if map_name and str(map_name).strip().lower() != "all":
        conditions.append("COALESCE(mm.map_name, 'unknown') = ?")
        params.append(str(map_name).strip())

    if weapons:
        placeholders = ",".join("?" for _ in weapons)
        conditions.append(f"COALESCE(wa.canonical_weapon, pmws.weapon) IN ({placeholders})")
        params.extend([str(w) for w in weapons])

    season_sql, season_params = _season_filter_clause("pmws.match_id", seasons)
    params.extend(season_params)

    where = " AND ".join(conditions)

    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT
                pmws.match_id,
                pmws.map_number,
                COALESCE(mm.map_name, 'unknown') AS map_name,
                COALESCE(mm.start_time, m.start_time, '') AS start_time,
                COALESCE(wa.canonical_weapon, pmws.weapon) AS weapon,
                COALESCE(NULLIF(wd.category, ''), 'unknown') AS category,
                COALESCE(pmws.shots_fired, 0) AS shots_fired,
                COALESCE(pmws.shots_hit, 0) AS shots_hit,
                COALESCE(pmws.kills, 0) AS kills,
                COALESCE(pmws.headshot_kills, 0) AS headshot_kills,
                COALESCE(pmws.damage, 0) AS damage,
                COALESCE(pmws.rounds_with_weapon, 0) AS rounds_with_weapon,
                COALESCE(mm.team1_score, 0) + COALESCE(mm.team2_score, 0) AS total_rounds
            {_WEAPON_FROM}
            LEFT JOIN match_maps mm
              ON mm.match_id = pmws.match_id AND mm.map_number = pmws.map_number
            LEFT JOIN matches m ON m.match_id = pmws.match_id
            WHERE {where}
                            {season_sql}
            ORDER BY COALESCE(mm.start_time, m.start_time, pmws.match_id) ASC,
                     pmws.map_number ASC,
                     weapon ASC
            """,
            tuple(params),
        ).fetchall()


def fetch_player_map_match_series(steamid64, maps=None, seasons=None):
    """Return per-match rows for a player's map performances, ordered chronologically.

    Each row: match_id, map_number, map_name, start_time, kills, deaths,
    assists, damage, head_shot_kills, total_rounds, won.

    Optional filter:
        maps – list of map names to include (None = all)
    """
    sid = str(steamid64 or "").strip()
    if not sid:
        return []

    # Explicit empty selection should yield no rows (not "all maps").
    if maps is not None and len(maps) == 0:
        return []

    conditions = ["mps.steamid64 = ?"]
    params: list = [sid]

    if maps:
        placeholders = ",".join("?" for _ in maps)
        conditions.append(f"COALESCE(mm.map_name, 'unknown') IN ({placeholders})")
        params.extend([str(m) for m in maps])

    season_sql, season_params = _season_filter_clause("mps.match_id", seasons)
    params.extend(season_params)

    where = " AND ".join(conditions)

    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT
                mps.match_id,
                mps.map_number,
                COALESCE(mm.map_name, 'unknown') AS map_name,
                COALESCE(mm.start_time, m.start_time, '') AS start_time,
                COALESCE(mps.kills, 0) AS kills,
                COALESCE(mps.deaths, 0) AS deaths,
                COALESCE(mps.assists, 0) AS assists,
                COALESCE(mps.damage, 0) AS damage,
                COALESCE(mps.head_shot_kills, 0) AS head_shot_kills,
                COALESCE(mm.team1_score, 0) + COALESCE(mm.team2_score, 0) AS total_rounds,
                CASE WHEN COALESCE(mm.winner, '') = COALESCE(mps.team, '') THEN 1 ELSE 0 END AS won
            FROM match_player_stats mps
            LEFT JOIN match_maps mm
              ON mm.match_id = mps.match_id AND mm.map_number = mps.map_number
            LEFT JOIN matches m ON m.match_id = mps.match_id
            WHERE {where}
                            {season_sql}
            ORDER BY COALESCE(mm.start_time, m.start_time, mps.match_id) ASC,
                     mps.map_number ASC
            """,
            tuple(params),
        ).fetchall()
