from .connection_db import get_conn


def _fetch_match_stat_leaderboard(aggregate_expr, limit):
    """Generic leaderboard query on match_player_stats."""
    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT
                COALESCE(name, steamid64),
                steamid64,
                {aggregate_expr}
            FROM match_player_stats
            GROUP BY steamid64, COALESCE(name, steamid64)
            ORDER BY 3 DESC, 1 ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def fetch_top_kills(limit):
    return _fetch_match_stat_leaderboard("SUM(COALESCE(kills, 0))", limit)


def fetch_top_deaths(limit):
    return _fetch_match_stat_leaderboard("SUM(COALESCE(deaths, 0))", limit)


def fetch_avg_damage(limit):
    return _fetch_match_stat_leaderboard("ROUND(AVG(COALESCE(damage, 0)), 1)", limit)


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