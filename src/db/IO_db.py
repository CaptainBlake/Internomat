from .connection_db import get_conn
from .players_db import upsert_player
from services.IO_manager import IOManager
import services.logger as logger


def import_players(filepath):

    players = IOManager.read_json(filepath)

    count = 0

    with get_conn() as conn:
        for p in players:
            if not isinstance(p, dict):
                continue

            if not p.get("steam64_id") or not p.get("name"):
                continue

            try:
                player = {
                    "steam64_id": p["steam64_id"],
                    "name": p["name"]
                }

                upsert_player(player, mode="import", conn=conn)
                count += 1

            except Exception as e:
                logger.log_error(f"Import error {p.get('steam64_id')}", exc=e)

    logger.log(f"[DB] Import players count={count}", level="INFO")


def export_players(filepath):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT
                steam64_id,
                name
            FROM players
        """)

        columns = [c[0] for c in cur.description]
        rows = cur.fetchall()

        players = [dict(zip(columns, row)) for row in rows]

    IOManager.write_json(filepath, players)

    logger.log(f"[DB] Export players count={len(players)} -> {filepath}", level="INFO")