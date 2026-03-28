import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Belt-and-suspenders: ensure src/ is importable even without pyproject.toml pythonpath.
_src = str(Path(__file__).resolve().parent.parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)


# -- Markers --

def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests as slow")
    config.addinivalue_line("markers", "live: marks tests requiring real external connections")


# -- Fixtures --

@pytest.fixture
def tmp_db(tmp_path):
    """Fresh SQLite DB (file-backed in tmp_path) with full Internomat schema."""
    from db.connection_db import get_conn
    from db.init_db import init_db

    db_file = str(tmp_path / "test.db")

    # init_db() internally calls get_conn() → patch it to point at our temp file.
    with patch("db.init_db.get_conn", lambda: get_conn(db_file)):
        init_db()

    # Return a *new* connection (init_db's connection is closed by its context manager).
    conn = get_conn(db_file)
    yield conn
    conn.close()


@pytest.fixture
def fresh_settings():
    """Return a brand-new Settings instance (not the module-level singleton)."""
    from core.settings.settings import Settings
    return Settings()
