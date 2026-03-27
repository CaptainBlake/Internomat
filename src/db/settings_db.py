from db.connection_db import execute_write, get_conn


def get(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default


def set(key: str, value):
    with get_conn() as conn:
        execute_write(
            conn,
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value)),
        )