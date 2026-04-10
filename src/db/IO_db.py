from .connection_db import get_conn
from .players_db import upsert_player
from services.IO_manager import IOManager
import services.logger as logger


def get_players_payload():
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT
                steamid64,
                name
            FROM players
            """
        )

        columns = [c[0] for c in cur.description]
        rows = cur.fetchall()

    return [dict(zip(columns, row)) for row in rows]


def import_players_payload(players):
    if not isinstance(players, list):
        logger.log_error("[DB] Import players failed: expected list payload")
        return 0

    count = 0

    with get_conn() as conn:
        for p in players:
            if not isinstance(p, dict):
                continue

            if not p.get("steamid64") or not p.get("name"):
                continue

            try:
                player = {
                    "steamid64": p["steamid64"],
                    "name": p["name"]
                }

                upsert_player(player, mode="import", conn=conn)
                count += 1

            except Exception as e:
                logger.log_error(f"Import error {p.get('steamid64')}", exc=e)

    return count


def get_maps_payload():
    with get_conn() as conn:
        cur = conn.execute(
            """
            SELECT name
            FROM maps
            ORDER BY name
            """
        )

        columns = [c[0] for c in cur.description]
        rows = cur.fetchall()

    return [dict(zip(columns, row)) for row in rows]


def import_maps_payload(maps_data):
    if not isinstance(maps_data, list):
        logger.log_error("[DB] Import maps failed: expected list payload")
        return 0

    count = 0
    with get_conn() as conn:
        for item in maps_data:
            map_name = None

            if isinstance(item, str):
                map_name = item
            elif isinstance(item, dict):
                map_name = item.get("name")

            if map_name is None:
                continue

            map_name = str(map_name).strip()
            if not map_name:
                continue

            try:
                conn.execute(
                    "INSERT OR IGNORE INTO maps(name) VALUES(?)",
                    (map_name,),
                )
                count += 1
            except Exception as e:
                logger.log_error(f"Import map error {map_name}", exc=e)

    return count


def import_players(filepath):

    players = IOManager.read_json(filepath)
    count = import_players_payload(players)

    logger.log(f"[DB] Import players count={count}", level="INFO")


def export_players(filepath):
    players = get_players_payload()

    IOManager.write_json(filepath, players)

    logger.log(f"[DB] Export players count={len(players)} -> {filepath}", level="INFO")


def import_maps(filepath):
    maps_data = IOManager.read_json(filepath)
    count = import_maps_payload(maps_data)

    logger.log(f"[DB] Import maps count={count}", level="INFO")


def export_maps(filepath):
    maps_data = get_maps_payload()

    IOManager.write_json(filepath, maps_data)
    logger.log(f"[DB] Export maps count={len(maps_data)} -> {filepath}", level="INFO")