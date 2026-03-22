from pathlib import Path
import sqlite3

# go to project root (Internomat)
BASE_DIR = Path(__file__).resolve().parents[2]
DB_FILE = BASE_DIR / "internomat.db"

def get_conn():
    conn = sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn