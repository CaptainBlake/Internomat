from datetime import datetime

from .connection_db import execute_write, executemany_write, get_conn, optional_conn
import services.logger as logger


_UPSERT_PLAYER_STATS_SQL = """
        INSERT INTO match_player_stats (
            steamid64, match_id, map_number,
            name, team,
            kills, deaths, assists, damage,
            enemy5ks, enemy4ks, enemy3ks, enemy2ks,
            utility_count, utility_damage, utility_successes, utility_enemies,
            flash_count, flash_successes,
            health_points_removed_total, health_points_dealt_total,
            shots_fired_total, shots_on_target_total,
            v1_count, v1_wins, v2_count, v2_wins,
            entry_count, entry_wins,
            equipment_value, money_saved, kill_reward, live_time,
            head_shot_kills, cash_earned, enemies_flashed,
            kast, impact, rating
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(steamid64, match_id, map_number) DO UPDATE SET
            name=excluded.name,
            team=excluded.team,
            kills=excluded.kills,
            deaths=excluded.deaths,
            assists=excluded.assists,
            damage=excluded.damage,
            enemy5ks=excluded.enemy5ks,
            enemy4ks=excluded.enemy4ks,
            enemy3ks=excluded.enemy3ks,
            enemy2ks=excluded.enemy2ks,
            utility_count=excluded.utility_count,
            utility_damage=excluded.utility_damage,
            utility_successes=excluded.utility_successes,
            utility_enemies=excluded.utility_enemies,
            flash_count=excluded.flash_count,
            flash_successes=excluded.flash_successes,
            health_points_removed_total=excluded.health_points_removed_total,
            health_points_dealt_total=excluded.health_points_dealt_total,
            shots_fired_total=excluded.shots_fired_total,
            shots_on_target_total=excluded.shots_on_target_total,
            v1_count=excluded.v1_count,
            v1_wins=excluded.v1_wins,
            v2_count=excluded.v2_count,
            v2_wins=excluded.v2_wins,
            entry_count=excluded.entry_count,
            entry_wins=excluded.entry_wins,
            equipment_value=excluded.equipment_value,
            money_saved=excluded.money_saved,
            kill_reward=excluded.kill_reward,
            live_time=excluded.live_time,
            head_shot_kills=excluded.head_shot_kills,
            cash_earned=excluded.cash_earned,
            enemies_flashed=excluded.enemies_flashed,
            kast=excluded.kast,
            impact=excluded.impact,
            rating=excluded.rating
        """


def _player_stats_params(data):
    return (
        data["steamid64"], data["match_id"], data["map_number"],
        data["name"], data["team"],
        data["kills"], data["deaths"], data["assists"], data["damage"],
        data["enemy5ks"], data["enemy4ks"], data["enemy3ks"], data["enemy2ks"],
        data["utility_count"], data["utility_damage"], data["utility_successes"], data["utility_enemies"],
        data["flash_count"], data["flash_successes"],
        data["health_points_removed_total"], data["health_points_dealt_total"],
        data["shots_fired_total"], data["shots_on_target_total"],
        data["v1_count"], data["v1_wins"], data["v2_count"], data["v2_wins"],
        data["entry_count"], data["entry_wins"],
        data["equipment_value"], data["money_saved"], data["kill_reward"], data["live_time"],
        data["head_shot_kills"], data["cash_earned"], data["enemies_flashed"],
        data.get("kast"), data.get("impact"), data.get("rating"),
    )


def insert_match(data, conn=None):
    with optional_conn(conn, commit=True) as c:
        execute_write(c, """
        INSERT INTO matches (
            match_id,
            start_time,
            end_time,
            winner,
            series_type,
            team1_name,
            team1_score,
            team2_name,
            team2_score,
            server_ip,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        ON CONFLICT(match_id) DO UPDATE SET
            end_time=excluded.end_time,
            winner=excluded.winner,
            team1_score=excluded.team1_score,
            team2_score=excluded.team2_score
        """, (
            data["match_id"],
            data.get("start_time"),
            data.get("end_time"),
            data.get("winner"),
            data.get("series_type"),
            data.get("team1_name"),
            data.get("team1_score"),
            data.get("team2_name"),
            data.get("team2_score"),
            data.get("server_ip"),
        ))

    logger.log(f"[DB] Upsert match {data['match_id']}", level="DEBUG")


def insert_match_map(data, conn=None):
    with optional_conn(conn, commit=True) as c:
        execute_write(c, """
        INSERT INTO match_maps (
            match_id,
            map_number,
            map_name,
            start_time,
            end_time,
            winner,
            team1_score,
            team2_score
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(match_id, map_number) DO UPDATE SET
            end_time=excluded.end_time,
            winner=excluded.winner,
            team1_score=excluded.team1_score,
            team2_score=excluded.team2_score
        """, (
            data["match_id"],
            data["map_number"],
            data["map_name"],
            data.get("start_time"),
            data.get("end_time"),
            data.get("winner"),
            data.get("team1_score"),
            data.get("team2_score"),
        ))

    logger.log(f"[DB] Upsert map match={data['match_id']} map={data['map_number']}", level="DEBUG")


def insert_match_player_stats(data, conn=None):
    with optional_conn(conn, commit=True) as c:
        execute_write(c, _UPSERT_PLAYER_STATS_SQL, _player_stats_params(data))


def insert_match_player_stats_many(rows, conn=None):
    if not rows:
        return

    with optional_conn(conn, commit=True) as c:
        params = [_player_stats_params(row) for row in rows]
        executemany_write(c, _UPSERT_PLAYER_STATS_SQL, params)


def match_exists(match_id):
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT 1 FROM matches WHERE match_id = ? LIMIT 1",
            (match_id,)
        )
        exists = cur.fetchone() is not None

    logger.log(f"[DB] Match exists={exists} match={str(match_id)[:6]}", level="DEBUG")

    return exists


def set_match_has_demo(match_id, has_demo=True, conn=None):
    with optional_conn(conn, commit=True) as c:
        execute_write(c,
            "UPDATE matches SET demo = ? WHERE match_id = ?",
            (1 if has_demo else 0, str(match_id)),
        )

    logger.log(f"[DB] Match demo={1 if has_demo else 0} match={match_id}", level="DEBUG")


def set_demo_flags_by_match_ids(match_ids, conn=None):
    ids = [str(mid) for mid in (match_ids or []) if str(mid).strip()]

    with optional_conn(conn, commit=True) as c:
        execute_write(c, "UPDATE matches SET demo = 0")

        if ids:
            placeholders = ",".join("?" for _ in ids)
            execute_write(c,
                f"UPDATE matches SET demo = 1 WHERE match_id IN ({placeholders})",
                ids,
            )

    logger.log(
        f"[DB] Reconciled match demo flags from cache matches={len(ids)}",
        level="INFO",
    )


def get_match_map_steamids(match_id, map_number, conn=None):
    with optional_conn(conn) as c:
        rows = c.execute(
            """
            SELECT DISTINCT steamid64
            FROM match_player_stats
            WHERE match_id = ?
              AND map_number = ?
              AND steamid64 IS NOT NULL
              AND steamid64 != ''
            """,
            (str(match_id), int(map_number)),
        ).fetchall()

    return {str(row["steamid64"]) for row in rows}


def get_next_local_match_id(conn=None, start_from=1):
    """Return the next positive integer match_id reserved for Internomat-local ids."""
    with optional_conn(conn) as c:
        row = c.execute(
            """
            SELECT MAX(CAST(match_id AS INTEGER)) AS max_id
            FROM matches
            WHERE match_id GLOB '[0-9]*'
            """
        ).fetchone()

    max_id = 0
    if row is not None and row["max_id"] is not None:
        try:
            max_id = int(row["max_id"])
        except Exception:
            max_id = 0

    next_id = max(max_id + 1, int(start_from))
    return str(next_id)


def _parse_sortable_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None

    normalized = text.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except Exception:
        return None


def _table_has_column(conn, table_name, column_name):
    try:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    except Exception:
        return False

    return any(str(r[1]) == str(column_name) for r in rows)


def _table_exists(conn, table_name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (str(table_name),),
    ).fetchone()
    return row is not None


def reindex_local_match_ids_by_datetime(conn=None):
    """Reindex positive integer match IDs so oldest played match gets ID 1.

    This keeps existing semantic links intact by rewriting all known match_id-
    carrying tables in one pass. Only positive integer match IDs are remapped;
    non-numeric/external IDs remain untouched.
    """
    with optional_conn(conn, commit=True) as c:
        rows = c.execute(
            """
            SELECT
                m.match_id,
                m.start_time,
                m.end_time,
                m.created_at,
                MIN(mm.start_time) AS min_map_start_time,
                MIN(mm.end_time) AS min_map_end_time
            FROM matches m
            LEFT JOIN match_maps mm ON mm.match_id = m.match_id
            WHERE m.match_id GLOB '[0-9]*'
              AND CAST(m.match_id AS INTEGER) > 0
            GROUP BY m.match_id, m.start_time, m.end_time, m.created_at
            """
        ).fetchall()

        ranked = []
        for row in rows:
            raw_match_id = str(row["match_id"])
            try:
                match_id_int = int(raw_match_id)
            except Exception:
                continue

            candidates = [
                row["min_map_start_time"],
                row["start_time"],
                row["min_map_end_time"],
                row["end_time"],
                row["created_at"],
            ]
            best_dt = None
            for candidate in candidates:
                parsed = _parse_sortable_datetime(candidate)
                if parsed is None:
                    continue
                if best_dt is None or parsed < best_dt:
                    best_dt = parsed

            ranked.append((match_id_int, best_dt))

        ranked.sort(key=lambda item: (item[1] is None, item[1] or datetime.max, item[0]))

        remap = {old_id: idx + 1 for idx, (old_id, _dt) in enumerate(ranked)}
        changed = {old: new for old, new in remap.items() if old != new}
        if not changed:
            return 0

        # Two-pass remap (tmp marker -> final) avoids UNIQUE conflicts while rewriting ids.
        id_columns = [
            ("matches", "match_id"),
            ("match_maps", "match_id"),
            ("match_player_stats", "match_id"),
            ("player_map_weapon_stats", "match_id"),
            ("player_round_weapon_stats", "match_id"),
            ("player_map_movement_stats", "match_id"),
            ("player_round_movement_stats", "match_id"),
            ("player_round_timeline_bins", "match_id"),
            ("player_round_events", "match_id"),
            ("cache_restore_state", "canonical_match_id"),
        ]

        for table_name, column_name in id_columns:
            if not _table_exists(c, table_name) or not _table_has_column(c, table_name, column_name):
                continue
            for old_id, new_id in changed.items():
                execute_write(
                    c,
                    f"UPDATE {table_name} SET {column_name} = ? WHERE {column_name} = ?",
                    (f"__RID__{new_id}", str(old_id)),
                )

        for table_name, column_name in id_columns:
            if not _table_exists(c, table_name) or not _table_has_column(c, table_name, column_name):
                continue
            for _old_id, new_id in changed.items():
                execute_write(
                    c,
                    f"UPDATE {table_name} SET {column_name} = ? WHERE {column_name} = ?",
                    (str(new_id), f"__RID__{new_id}"),
                )

    logger.log(
        f"[DB] Reindexed local match_ids by datetime remapped={len(changed)}",
        level="INFO",
    )
    return len(changed)


def get_next_map_number_for_match(match_id, conn=None, start_from=0):
    with optional_conn(conn) as c:
        row = c.execute(
            """
            SELECT MAX(map_number) AS max_map
            FROM match_maps
            WHERE match_id = ?
            """,
            (str(match_id),),
        ).fetchone()

    max_map = None
    if row is not None:
        max_map = row["max_map"]

    if max_map is None:
        return int(start_from)

    try:
        return int(max_map) + 1
    except Exception:
        return int(start_from)


def match_map_has_player_stats(match_id, map_number, conn=None):
    with optional_conn(conn) as c:
        row = c.execute(
            """
            SELECT 1
            FROM match_player_stats
            WHERE match_id = ?
              AND map_number = ?
            LIMIT 1
            """,
            (str(match_id), int(map_number)),
        ).fetchone()

    return row is not None


def get_match_map_players(match_id, map_number, conn=None):
    with optional_conn(conn) as c:
        rows = c.execute(
            """
            SELECT steamid64, name
            FROM match_player_stats
            WHERE match_id = ?
              AND map_number = ?
              AND steamid64 IS NOT NULL
              AND steamid64 != ''
            """,
            (str(match_id), int(map_number)),
        ).fetchall()

    players = []
    for row in rows:
        steam64_id = str(row["steamid64"]).strip()
        if not steam64_id:
            continue
        players.append(
            {
                "steam64_id": steam64_id,
                "name": str(row["name"] or steam64_id),
            }
        )

    return players


def get_all_matches_with_maps(conn=None):
    with optional_conn(conn) as c:
        rows = c.execute("""
        SELECT 
            m.match_id,
            m.team1_name,
            m.team2_name,
            mm.map_number,
            mm.map_name
        FROM matches m
        LEFT JOIN match_maps mm 
            ON m.match_id = mm.match_id
        ORDER BY m.match_id, mm.map_number
        """).fetchall()

    matches = {}

    for row in rows:
        match_id = row["match_id"]
        t1 = row["team1_name"]
        t2 = row["team2_name"]
        map_num = row["map_number"]
        map_name = row["map_name"]

        if match_id not in matches:
            matches[match_id] = {
                "match_id": match_id,
                "team1": t1,
                "team2": t2,
                "maps": []
            }

        if map_num is not None:
            matches[match_id]["maps"].append({
                "map_number": int(map_num),
                "map_name": map_name
            })

    return list(matches.values())


def get_total_matches_count(conn=None):
    with optional_conn(conn) as c:
        row = c.execute("SELECT COUNT(*) AS total FROM matches").fetchone()

    return int(row["total"] or 0) if row else 0


def get_map_play_counts(conn=None):
    with optional_conn(conn) as c:
        rows = c.execute(
            """
            SELECT map_name, COUNT(*) AS played_count
            FROM match_maps
            WHERE map_name IS NOT NULL
              AND map_name != ''
            GROUP BY map_name
            """
        ).fetchall()

    return {
        str(row["map_name"]): int(row["played_count"] or 0)
        for row in rows
    }
