from .connection_db import execute_write, get_conn
import services.logger as logger

def get_maps():
    with get_conn() as conn:
        cur = conn.execute("SELECT name FROM maps ORDER BY name")
        result = [r[0] for r in cur.fetchall()]

    logger.log(f"[DB] Loaded map-pool = {len(result)}", level="DEBUG")
    return result


def add_map(name):
    with get_conn() as conn:
        execute_write(conn, "INSERT OR IGNORE INTO maps(name) VALUES(?)", (name.strip(),))

    logger.log(f"[DB] Add map {name}", level="INFO")


def delete_map(name):
    with get_conn() as conn:
        execute_write(conn, "DELETE FROM maps WHERE name = ?", (name,))

    logger.log(f"[DB] Delete map {name}", level="INFO")


def map_exists(name):
    with get_conn() as conn:
        cur = conn.execute("SELECT 1 FROM maps WHERE name = ?", (name,))
        return cur.fetchone() is not None


def import_maps_from_match_history(conn=None):
    own_conn = conn is None
    conn = conn or get_conn()

    try:
        before = conn.execute("SELECT COUNT(*) AS total FROM maps").fetchone()["total"]

        execute_write(
            conn,
            """
            INSERT OR IGNORE INTO maps(name)
            SELECT DISTINCT TRIM(map_name)
            FROM match_maps
            WHERE map_name IS NOT NULL
              AND TRIM(map_name) != ''
            """,
        )

        after = conn.execute("SELECT COUNT(*) AS total FROM maps").fetchone()["total"]

        if own_conn:
            conn.commit()
    finally:
        if own_conn:
            conn.close()

    imported = int(after or 0) - int(before or 0)
    logger.log(f"[DB] Imported maps from history count={imported}", level="INFO")
    return max(0, imported)

