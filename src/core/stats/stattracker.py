from db import stattracker_db as stattracker_repo
import services.logger as logger


def get_overview():
    row = stattracker_repo.fetch_player_overview()

    result = {
        "tracked_players": int(row["tracked_players"] or 0),
        "player_stat_rows": int(row["player_stat_rows"] or 0),
        "unique_player_maps": int(row["unique_player_maps"] or 0),
    }

    logger.log(
        "[STATTRACKER] "
        f"overview tracked_players={result['tracked_players']} "
        f"player_stat_rows={result['player_stat_rows']} "
        f"unique_player_maps={result['unique_player_maps']}",
        level="DEBUG",
    )

    return result


def get_player_samples(limit=10):
    rows = stattracker_repo.fetch_top_player_samples(limit)

    result = [
        {
            "player_name": str(r["player_name"] or "?"),
            "steamid64": str(r["steamid64"] or ""),
            "map_entries": int(r["map_entries"] or 0),
            "total_kills": int(r["total_kills"] or 0),
            "total_deaths": int(r["total_deaths"] or 0),
        }
        for r in rows
    ]

    logger.log(f"[STATTRACKER] player samples size={len(result)}", level="DEBUG")
    return result
