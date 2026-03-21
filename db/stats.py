from .connection import get_conn
import services.logger as logger

# sum of kills per player across all matches, ordered by total kills
def get_top_kills(limit=10):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT
                COALESCE(name, steamid64) AS player_name,
                steamid64,
                SUM(COALESCE(kills, 0)) AS total_kills
            FROM match_player_stats
            GROUP BY steamid64, player_name
            ORDER BY total_kills DESC, player_name ASC
            LIMIT ?
        """, (limit,))
        return cur.fetchall()

# sum of deaths per player across all matches, ordered by total deaths
def get_top_deaths(limit=10):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT
                COALESCE(name, steamid64) AS player_name,
                steamid64,
                SUM(COALESCE(deaths, 0)) AS total_deaths
            FROM match_player_stats
            GROUP BY steamid64, player_name
            ORDER BY total_deaths DESC, player_name ASC
            LIMIT ?
        """, (limit,))
        return cur.fetchall()

# sum of assists per player across all matches, ordered by total assists
def get_top_ratings(limit=10):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT
                name,
                steam64_id,
                COALESCE(premier_rating, CAST(leetify_rating * 10000 AS INTEGER), 0) AS rating
            FROM players
            WHERE name IS NOT NULL AND name != ''
            ORDER BY rating DESC, name ASC
            LIMIT ?
        """, (limit,))
        return cur.fetchall()

# average damage per player across all matches, ordered by average damage
def get_top_damage_per_match(limit=10):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT
                COALESCE(name, steamid64) AS player_name,
                steamid64,
                ROUND(AVG(COALESCE(damage, 0)), 1) AS avg_damage
            FROM match_player_stats
            GROUP BY steamid64, player_name
            ORDER BY avg_damage DESC, player_name ASC
            LIMIT ?
        """, (limit,))
        return cur.fetchall()
