from .connection_db import get_conn


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
