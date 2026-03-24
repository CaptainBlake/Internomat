from .connection_db import get_conn


def fetch_overview():
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM matches) AS total_matches,
                (SELECT COUNT(DISTINCT steamid64) FROM match_player_stats) AS unique_players,
                (
                    SELECT ROUND(AVG(COALESCE(team1_score, 0) + COALESCE(team2_score, 0)), 2)
                    FROM match_maps
                ) AS avg_map_total_score
            """
        ).fetchone()

    return row


def fetch_recent_maps(limit):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT
                match_id,
                map_number,
                map_name,
                winner,
                team1_score,
                team2_score,
                COALESCE(end_time, start_time) AS played_at
            FROM match_maps
            ORDER BY COALESCE(end_time, start_time) DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
