from .connection_db import get_conn


def _fetch_match_stat_leaderboard(aggregate_expr, limit, season=None):
    """Generic leaderboard query on match_player_stats."""
    season_sql = ""
    params = [limit]
    if season is not None:
        season_sql = (
            " AND EXISTS ("
            "SELECT 1 FROM elo_match_season ems "
            "WHERE ems.match_id = mps.match_id AND ems.season = ?"
            ")"
        )
        params = [int(season), limit]

    with get_conn() as conn:
        return conn.execute(
            f"""
            SELECT
                COALESCE(name, steamid64),
                steamid64,
                {aggregate_expr}
            FROM match_player_stats mps
            WHERE 1=1 {season_sql}
            GROUP BY steamid64, COALESCE(name, steamid64)
            ORDER BY 3 DESC, 1 ASC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()


def fetch_top_kills(limit, season=None):
    return _fetch_match_stat_leaderboard("SUM(COALESCE(kills, 0))", limit, season=season)


def fetch_top_deaths(limit, season=None):
    return _fetch_match_stat_leaderboard("SUM(COALESCE(deaths, 0))", limit, season=season)


def fetch_avg_damage(limit, season=None):
    return _fetch_match_stat_leaderboard("ROUND(AVG(COALESCE(damage, 0)), 1)", limit, season=season)


def fetch_top_ratings(limit, season=None):
    with get_conn() as conn:
        if season is None:
            return conn.execute(
                """
                SELECT
                    COALESCE(NULLIF(p.name, ''), p.steamid64) AS name,
                    p.steamid64 AS steamid64,
                    COALESCE(pr.premier_rating, 0) AS rating
                FROM players p
                LEFT JOIN prime_ratings pr ON pr.steamid64 = p.steamid64
                ORDER BY rating DESC, name COLLATE NOCASE ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return conn.execute(
            """
            SELECT
                COALESCE(NULLIF(p.name, ''), ers.steamid64) AS name,
                ers.steamid64 AS steamid64,
                ROUND(COALESCE(ers.elo, 1500.0), 2) AS rating
            FROM elo_ratings_season ers
            LEFT JOIN players p ON p.steamid64 = ers.steamid64
            WHERE ers.season = ?
            ORDER BY rating DESC, name COLLATE NOCASE ASC
            LIMIT ?
            """,
            (int(season), limit),
        ).fetchall()