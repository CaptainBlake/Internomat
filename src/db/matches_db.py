from .connection_db import get_conn
import services.logger as logger


def insert_match(data, conn=None):
    own_conn = conn is None
    conn = conn or get_conn()

    try:
        conn.execute("""
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

        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()

    logger.log(f"[DB] Upsert match {data['match_id']}", level="DEBUG")


def insert_match_map(data, conn=None):
    own_conn = conn is None
    conn = conn or get_conn()

    try:
        conn.execute("""
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

        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()

    logger.log(f"[DB] Upsert map match={data['match_id']} map={data['map_number']}", level="DEBUG")


def insert_match_player_stats(data, conn=None):
    own_conn = conn is None
    conn = conn or get_conn()

    try:
        conn.execute("""
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
            head_shot_kills, cash_earned, enemies_flashed
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(steamid64, match_id, map_number) DO UPDATE SET
            kills=excluded.kills,
            deaths=excluded.deaths,
            assists=excluded.assists,
            damage=excluded.damage,
            cash_earned=excluded.cash_earned
        """, (
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
            data["head_shot_kills"], data["cash_earned"], data["enemies_flashed"]
        ))

        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()


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
    own_conn = conn is None
    conn = conn or get_conn()

    try:
        conn.execute(
            "UPDATE matches SET demo = ? WHERE match_id = ?",
            (1 if has_demo else 0, str(match_id)),
        )

        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()

    logger.log(f"[DB] Match demo={1 if has_demo else 0} match={match_id}", level="DEBUG")


def set_demo_flags_by_match_ids(match_ids, conn=None):
    own_conn = conn is None
    conn = conn or get_conn()

    ids = [str(mid) for mid in (match_ids or []) if str(mid).strip()]

    try:
        conn.execute("UPDATE matches SET demo = 0")

        if ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(
                f"UPDATE matches SET demo = 1 WHERE match_id IN ({placeholders})",
                ids,
            )

        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()

    logger.log(
        f"[DB] Reconciled match demo flags from cache matches={len(ids)}",
        level="INFO",
    )


def get_match_map_steamids(match_id, map_number, conn=None):
    own_conn = conn is None
    conn = conn or get_conn()

    try:
        rows = conn.execute(
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
    finally:
        if own_conn:
            conn.close()

    return {str(row["steamid64"]) for row in rows}


def get_all_matches_with_maps(conn=None):
    own_conn = conn is None
    conn = conn or get_conn()

    try:
        rows = conn.execute("""
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
    finally:
        if own_conn:
            conn.close()

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
