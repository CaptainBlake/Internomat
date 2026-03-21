from .connection import get_conn
import services.logger as logger

def get_maps():
    with get_conn() as conn:
        cur = conn.execute("SELECT name FROM maps ORDER BY name")
        result = [r[0] for r in cur.fetchall()]

    logger.log(f"[DB] Loaded map-pool = {len(result)}", level="DEBUG")
    return result


def add_map(name):
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO maps(name) VALUES(?)", (name.strip(),))

    logger.log(f"[DB] Add map {name}", level="INFO")


def delete_map(name):
    with get_conn() as conn:
        conn.execute("DELETE FROM maps WHERE name = ?", (name,))

    logger.log(f"[DB] Delete map {name}", level="INFO")


def map_exists(name):
    with get_conn() as conn:
        cur = conn.execute("SELECT 1 FROM maps WHERE name = ?", (name,))
        return cur.fetchone() is not None

