from .connection import get_conn

def fetch_top_kills(limit):
    with get_conn() as conn:
        return conn.execute("""
            SELECT
                COALESCE(name, steamid64),
                steamid64,
                SUM(COALESCE(kills, 0))
            FROM match_player_stats
            GROUP BY steamid64, COALESCE(name, steamid64)
            ORDER BY 3 DESC, 1 ASC
            LIMIT ?
        """, (limit,)).fetchall()


def fetch_top_deaths(limit):
    with get_conn() as conn:
        return conn.execute("""
            SELECT
                COALESCE(name, steamid64),
                steamid64,
                SUM(COALESCE(deaths, 0))
            FROM match_player_stats
            GROUP BY steamid64, COALESCE(name, steamid64)
            ORDER BY 3 DESC, 1 ASC
            LIMIT ?
        """, (limit,)).fetchall()


def fetch_top_ratings(limit):
    with get_conn() as conn:
        return conn.execute("""
            SELECT
                name,
                steam64_id,
                COALESCE(premier_rating, CAST(leetify_rating * 10000 AS INTEGER), 0)
            FROM players
            WHERE name IS NOT NULL AND name != ''
            ORDER BY 3 DESC, 1 ASC
            LIMIT ?
        """, (limit,)).fetchall()


def fetch_avg_damage(limit):
    with get_conn() as conn:
        return conn.execute("""
            SELECT
                COALESCE(name, steamid64),
                steamid64,
                ROUND(AVG(COALESCE(damage, 0)), 1)
            FROM match_player_stats
            GROUP BY steamid64, COALESCE(name, steamid64)
            ORDER BY 3 DESC, 1 ASC
            LIMIT ?
        """, (limit,)).fetchall()