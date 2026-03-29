from .connection_db import executemany_write, get_conn


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

    own_conn = conn is None
    conn = conn or get_conn()

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

    try:
        discovered_weapons = sorted({p[3] for p in params if str(p[3]).strip()})
        if discovered_weapons:
            executemany_write(
                conn,
                """
                INSERT INTO weapon_dim (weapon, display_name, category, source, is_active, first_seen_at, updated_at)
                VALUES (?, ?, 'unknown', 'observed', 1, datetime('now'), datetime('now'))
                ON CONFLICT(weapon) DO UPDATE SET
                    is_active = 1,
                    updated_at = datetime('now')
                """,
                [(w, w) for w in discovered_weapons],
            )

        executemany_write(conn, query, params)
        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()


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


def fetch_player_overall_metrics(steamid64):
    with get_conn() as conn:
        return conn.execute(
            """
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
            """,
            (str(steamid64),),
        ).fetchone()


def fetch_player_map_stats(steamid64):
    with get_conn() as conn:
        return conn.execute(
            """
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
            GROUP BY COALESCE(mm.map_name, 'unknown')
            ORDER BY maps_played DESC, map_name COLLATE NOCASE ASC
            """,
            (str(steamid64),),
        ).fetchall()


def fetch_player_weapon_categories(steamid64):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT
                COALESCE(NULLIF(wd.category, ''), 'unknown') AS category,
                COUNT(*) AS rows_count
            FROM player_map_weapon_stats pmws
                        LEFT JOIN weapon_alias wa
                            ON wa.raw_weapon = pmws.weapon
            LEFT JOIN weapon_dim wd
                            ON wd.weapon = COALESCE(wa.canonical_weapon, pmws.weapon)
            WHERE pmws.steamid64 = ?
            GROUP BY COALESCE(NULLIF(wd.category, ''), 'unknown')
            ORDER BY category COLLATE NOCASE ASC
            """,
            (str(steamid64),),
        ).fetchall()


def fetch_player_weapon_stats(steamid64, min_shots=1, weapon_category=None):
    category_sql = ""
    params = [str(steamid64)]
    selected_category = str(weapon_category or "").strip().lower()
    if selected_category and selected_category != "all":
        category_sql = "AND COALESCE(NULLIF(wd.category, ''), 'unknown') = ?"
        params.append(selected_category)
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
            FROM player_map_weapon_stats pmws
                        LEFT JOIN weapon_alias wa
                            ON wa.raw_weapon = pmws.weapon
            LEFT JOIN weapon_dim wd
                            ON wd.weapon = COALESCE(wa.canonical_weapon, pmws.weapon)
            WHERE pmws.steamid64 = ?
              {category_sql}
                        GROUP BY COALESCE(wa.canonical_weapon, pmws.weapon), COALESCE(NULLIF(wd.category, ''), 'unknown')
            HAVING SUM(COALESCE(shots_fired, 0)) >= ?
                        ORDER BY shots_fired DESC, weapon COLLATE NOCASE ASC
            """,
            tuple(params),
        ).fetchall()


def fetch_player_weapon_kill_attribution_deltas(steamid64):
    with get_conn() as conn:
        return conn.execute(
            """
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
              AND (COALESCE(mps.kills, 0) - COALESCE(w.weapon_kills, 0)) > 0
            ORDER BY mps.match_id DESC, mps.map_number ASC
            """,
            (str(steamid64),),
        ).fetchall()


def fetch_player_weapon_match_series(steamid64, weapons=None, map_name=None):
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
            FROM player_map_weapon_stats pmws
            LEFT JOIN weapon_alias wa ON wa.raw_weapon = pmws.weapon
            LEFT JOIN weapon_dim wd ON wd.weapon = COALESCE(wa.canonical_weapon, pmws.weapon)
            LEFT JOIN match_maps mm
              ON mm.match_id = pmws.match_id AND mm.map_number = pmws.map_number
            LEFT JOIN matches m ON m.match_id = pmws.match_id
            WHERE {where}
            ORDER BY COALESCE(mm.start_time, m.start_time, pmws.match_id) ASC,
                     pmws.map_number ASC,
                     weapon ASC
            """,
            tuple(params),
        ).fetchall()


def fetch_player_map_match_series(steamid64, maps=None):
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
            ORDER BY COALESCE(mm.start_time, m.start_time, mps.match_id) ASC,
                     mps.map_number ASC
            """,
            tuple(params),
        ).fetchall()
