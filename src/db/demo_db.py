from .matches_db import get_all_matches_with_maps, get_match_map_steamids
import services.logger as logger


def load_demo_match_catalog(conn=None):
    matches = get_all_matches_with_maps(conn=conn)

    catalog = {}

    for match in matches:
        match_id = str(match["match_id"])

        maps_by_name = {}
        for match_map in match.get("maps", []):
            map_name = match_map.get("map_name")
            map_number = match_map.get("map_number")

            if map_name is None or map_number is None:
                continue

            maps_by_name[str(map_name)] = int(map_number)

        catalog[match_id] = {
            "match_id": match_id,
            "team1": match.get("team1"),
            "team2": match.get("team2"),
            "maps_by_name": maps_by_name,
        }

    logger.log(f"[DB] Loaded demo catalog matches={len(catalog)}", level="DEBUG")

    return catalog


def resolve_map_number(catalog, match_id, map_name):
    match = catalog.get(str(match_id))
    if not match:
        logger.log(
            f"[DB] Resolve map_number miss match={match_id} map={map_name}",
            level="DEBUG",
        )
        return None

    map_number = match["maps_by_name"].get(map_name)

    if map_number is None:
        logger.log(
            f"[DB] Resolve map_number miss match={match_id} map={map_name}",
            level="DEBUG",
        )

    return map_number


def get_expected_demo_players(match_id, map_number, conn=None):
    players = get_match_map_steamids(
        match_id=match_id,
        map_number=map_number,
        conn=conn
    )

    logger.log(
        f"[DB] Loaded expected demo players match={match_id} map={map_number} count={len(players)}",
        level="DEBUG",
    )

    return players
