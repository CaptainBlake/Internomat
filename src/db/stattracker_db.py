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
            LEFT JOIN weapon_dim wd
              ON wd.weapon = pmws.weapon
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
                pmws.weapon,
                COALESCE(NULLIF(wd.category, ''), 'unknown') AS category,
                SUM(COALESCE(shots_fired, 0)) AS shots_fired,
                SUM(COALESCE(shots_hit, 0)) AS shots_hit,
                SUM(COALESCE(kills, 0)) AS kills,
                SUM(COALESCE(headshot_kills, 0)) AS headshot_kills,
                SUM(COALESCE(damage, 0)) AS damage,
                SUM(COALESCE(rounds_with_weapon, 0)) AS rounds_with_weapon
            FROM player_map_weapon_stats pmws
            LEFT JOIN weapon_dim wd
              ON wd.weapon = pmws.weapon
            WHERE pmws.steamid64 = ?
              {category_sql}
            GROUP BY pmws.weapon, COALESCE(NULLIF(wd.category, ''), 'unknown')
            HAVING SUM(COALESCE(shots_fired, 0)) >= ?
            ORDER BY shots_fired DESC, pmws.weapon COLLATE NOCASE ASC
            """,
            tuple(params),
        ).fetchall()
