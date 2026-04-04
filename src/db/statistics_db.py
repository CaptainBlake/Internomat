from .connection_db import get_conn


def fetch_overview():
    with get_conn() as conn:
        row = conn.execute(
            """
            WITH top_map AS (
                SELECT map_name, COUNT(*) AS cnt
                FROM match_maps
                WHERE map_name IS NOT NULL AND map_name != ''
                GROUP BY map_name
                ORDER BY cnt DESC, map_name ASC
                LIMIT 1
            )
            SELECT
                (SELECT COUNT(*) FROM matches) AS total_matches,
                (SELECT COUNT(*) FROM match_maps) AS total_maps,
                (SELECT COUNT(DISTINCT steamid64) FROM match_player_stats) AS unique_players,
                (
                    SELECT COUNT(*)
                    FROM matches
                    WHERE COALESCE(demo, 0) = 1
                ) AS demo_matches,
                (
                    SELECT COUNT(*)
                    FROM (
                        SELECT 1
                        FROM match_player_stats
                        GROUP BY match_id, map_number
                    )
                ) AS maps_with_stats,
                (SELECT map_name FROM top_map) AS top_map_name,
                (SELECT cnt FROM top_map) AS top_map_count
            """
        ).fetchone()

    return row


def fetch_recent_maps(limit):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT
                mm.match_id,
                mm.map_number,
                mm.map_name,
                COALESCE(mm.winner, m.winner) AS winner,
                COALESCE(mm.team1_score, m.team1_score) AS team1_score,
                COALESCE(mm.team2_score, m.team2_score) AS team2_score,
                CASE
                    WHEN COALESCE(mm.team1_score, m.team1_score) IS NULL
                      OR COALESCE(mm.team2_score, m.team2_score) IS NULL
                    THEN NULL
                    ELSE COALESCE(mm.team1_score, m.team1_score) + COALESCE(mm.team2_score, m.team2_score)
                END AS db_rounds,
                mps.db_kills,
                COALESCE(mm.end_time, mm.start_time, m.end_time, m.start_time) AS played_at,
                COALESCE(m.demo, 0) AS has_demo
            FROM match_maps mm
            LEFT JOIN matches m ON mm.match_id = m.match_id
            LEFT JOIN (
                SELECT
                    match_id,
                    map_number,
                    SUM(COALESCE(kills, 0)) AS db_kills
                FROM match_player_stats
                GROUP BY match_id, map_number
            ) mps
                ON mps.match_id = mm.match_id
               AND mps.map_number = mm.map_number
            ORDER BY COALESCE(mm.end_time, mm.start_time, m.end_time, m.start_time) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
