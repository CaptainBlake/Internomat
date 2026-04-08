import services.logger as logger
from db import stats_db as stats_repo
from db import elo_db


def _build_leaderboard(rows):
    return [(r[0], r[1], r[2]) for r in rows]


def get_top_kills(limit=10, season=None):
    rows = stats_repo.fetch_top_kills(limit, season=season)
    result = _build_leaderboard(rows)

    logger.log(f"[STATS] kills leaderboard size={len(result)}", level="DEBUG")
    return result


def get_top_deaths(limit=10, season=None):
    rows = stats_repo.fetch_top_deaths(limit, season=season)
    result = _build_leaderboard(rows)

    logger.log(f"[STATS] deaths leaderboard size={len(result)}", level="DEBUG")
    return result


def get_top_ratings(limit=10, season=None):
    rows = stats_repo.fetch_top_ratings(limit, season=season)
    result = _build_leaderboard(rows)

    logger.log(f"[STATS] rating leaderboard size={len(result)}", level="DEBUG")
    return result


def get_top_damage_per_match(limit=10, season=None):
    rows = stats_repo.fetch_avg_damage(limit, season=season)
    result = _build_leaderboard(rows)

    logger.log(f"[STATS] damage leaderboard size={len(result)}", level="DEBUG")
    return result


def get_season_options():
    rows = elo_db.get_elo_seasons()
    return [int(r["season"]) for r in rows]