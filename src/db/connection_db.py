from pathlib import Path
import sqlite3
from contextlib import contextmanager
from threading import RLock

# go to project root (Internomat)
BASE_DIR = Path(__file__).resolve().parents[2]
DB_FILE = BASE_DIR / "internomat.db"
_WRITE_LOCK = RLock()


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
        factory=ManagedConnection,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def write_lock():
    """Serialize SQLite write operations across threads in this process."""
    _WRITE_LOCK.acquire()
    try:
        yield
    finally:
        _WRITE_LOCK.release()


def execute_write(conn, query, params=()):
    with write_lock():
        return conn.execute(query, params)


def executemany_write(conn, query, seq_of_params):
    with write_lock():
        return conn.executemany(query, seq_of_params)


@contextmanager
def write_transaction(conn=None, begin_mode="IMMEDIATE"):
    """Open an explicit write transaction with process-local write serialization."""
    own_conn = conn is None
    conn = conn or get_conn()

    with write_lock():
        started_transaction = False
        try:
            if not conn.in_transaction:
                conn.execute(f"BEGIN {begin_mode}")
                started_transaction = True

            yield conn

            if started_transaction:
                conn.commit()
        except Exception:
            if started_transaction and conn.in_transaction:
                conn.rollback()
            raise
        finally:
            if own_conn:
                conn.close()