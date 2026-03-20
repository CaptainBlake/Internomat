import sqlite3

DB_FILE = "internomat.db"

def get_conn():
    conn = sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn