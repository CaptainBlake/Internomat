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

def _enable_wal_mode(conn):
    """Enable WAL mode for concurrent read/write from multiple threads.
    
    WAL (Write-Ahead Logging) allows readers and writers to coexist:
    - Multiple readers can run in parallel
    - One writer can run while readers work
    - Reduces lock contention significantly
    
    synchronous=NORMAL is safe with WAL:
    - Full ACID guarantees remain (same as FULL, different mechanism)
    - Faster writes than FULL or EXTRA
    """
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA cache_size=-64000")  # 64MB page cache
        conn.execute("PRAGMA temp_store=MEMORY")
    except Exception as e:
        import services.logger as logger
        logger.log_warning(f"[DB] WAL mode setup failed; proceeding with defaults: {e}")

def get_conn(db_file=None):
    db_path = db_file or DB_FILE
    conn = sqlite3.connect(
        db_path,
        timeout=10,
        factory=ManagedConnection,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    _enable_wal_mode(conn)
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
    """Open an explicit write transaction with process-local write serialization.
    
    Even with WAL mode, we maintain the process-level write lock to:
    - Ensure sequential commit ordering for deterministic state
    - Prevent concurrent multi-statement transactions that could deadlock
    - Keep restore/insertion logic predictable and debuggable
    """
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


@contextmanager
def optional_conn(conn=None, *, commit=False):
    """Context manager that creates a connection when *conn* is ``None``.

    On exit the connection is committed (when *commit* is ``True`` and the
    connection was created here) and closed.  Callers replace the recurring
    ``own_conn = conn is None; …; try/finally`` boilerplate with::

        with optional_conn(conn, commit=True) as c:
            execute_write(c, ...)
    """
    own = conn is None
    c = conn or get_conn()
    try:
        yield c
        if own and commit:
            c.commit()
    finally:
        if own:
            c.close()