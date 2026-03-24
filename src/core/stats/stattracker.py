import services.logger as logger
from db import stattracker_db as tracker_repo


def get_overview():
    row = tracker_repo.fetch_overview()

    result = {
        "total_matches": int(row["total_matches"] or 0),
        "unique_players": int(row["unique_players"] or 0),
        "avg_map_total_score": float(row["avg_map_total_score"] or 0.0),
    }

    logger.log(
        "[STATTRACKER] "
        f"overview matches={result['total_matches']} "
        f"players={result['unique_players']} avg_score={result['avg_map_total_score']}",
        level="DEBUG",
    )

    return result


def get_recent_maps(limit=10):
    rows = tracker_repo.fetch_recent_maps(limit)

    result = [
        {
            "match_id": str(r["match_id"]),
            "map_number": int(r["map_number"] or 0),
            "map_name": str(r["map_name"] or "?"),
            "winner": str(r["winner"] or "?"),
            "team1_score": int(r["team1_score"] or 0),
            "team2_score": int(r["team2_score"] or 0),
            "played_at": str(r["played_at"] or ""),
        }
        for r in rows
    ]

    logger.log(f"[STATTRACKER] recent maps size={len(result)}", level="DEBUG")

    return result
