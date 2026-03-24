from pathlib import Path
import sqlite3

# go to project root (Internomat)
BASE_DIR = Path(__file__).resolve().parents[2]
DB_FILE = BASE_DIR / "internomat.db"


class ManagedConnection(sqlite3.Connection):
    """sqlite3 connection that also closes on context-manager exit."""

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            return super().__exit__(exc_type, exc_val, exc_tb)
        finally:
            self.close()

def get_conn(db_file=None):
    db_path = db_file or DB_FILE
    conn = sqlite3.connect(
        db_path,
        timeout=10,
        check_same_thread=False,
        factory=ManagedConnection,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn