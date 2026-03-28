"""Service-layer test fixtures.

Provides DB plumbing (reuses root ``tmp_db``), a monkeypatch that redirects
``db.connection_db.DB_FILE`` to the temp test DB, and mock factories for
common external dependencies (MySQL, HTTP, FTP).
"""

import pytest
from unittest.mock import MagicMock, Mock


# ---------------------------------------------------------------------------
# Base DB plumbing (reuses root tmp_db)
# ---------------------------------------------------------------------------

@pytest.fixture
def db_conn(tmp_db):
    """Function-scoped SQLite connection with full Internomat schema."""
    return tmp_db


@pytest.fixture
def db_file(db_conn):
    """Return the file path of the test database."""
    row = db_conn.execute("PRAGMA database_list").fetchone()
    return row[2]


@pytest.fixture
def monkeypatch_db(monkeypatch, db_file):
    """Redirect every ``get_conn()`` call (no-arg) to the temp test DB."""
    monkeypatch.setattr("db.connection_db.DB_FILE", db_file)


# ---------------------------------------------------------------------------
# Mock factories
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_mysql_conn():
    """Return a mock ``mysql.connector`` connection with configurable cursor."""
    conn = MagicMock()
    conn.is_connected.return_value = True
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    return conn


@pytest.fixture
def mock_http_response():
    """Factory fixture: call with (status_code, text=..., json_data=...) to
    build a ``requests.Response``-like mock."""

    def _factory(status_code=200, text="", json_data=None):
        resp = Mock()
        resp.status_code = status_code
        resp.text = text
        resp.json = Mock(return_value=json_data or {})
        return resp

    return _factory
