from db.connection_db import get_conn


def get(key: str, default=None):
    conn = get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default
    finally:
        cursor.close()
        conn.close()


def set(key: str, value):
    conn = get_conn()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, str(value))
        )
        conn.commit()
    finally:
        cursor.close()
        conn.close()