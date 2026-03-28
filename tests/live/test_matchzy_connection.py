"""Live smoke test: MatchZy MySQL connectivity.

Reads MySQL credentials from the settings singleton (which loads from DB)
or falls back to environment variables.
Skipped unless INTERNOMAT_LIVE_TESTS=1.
"""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = pytest.mark.live


@pytest.fixture
def mysql_creds():
    """Gather MySQL credentials from environment."""
    host = os.getenv("MATCHZY_HOST", "")
    port = int(os.getenv("MATCHZY_PORT", 3306))
    user = os.getenv("MATCHZY_USER", "")
    password = os.getenv("MATCHZY_PASSWORD", "")
    database = os.getenv("MATCHZY_DATABASE", "")
    if not all([host, user, database]):
        pytest.skip("MatchZy MySQL credentials not configured in environment")
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "database": database,
    }


def test_mysql_select_one(require_live, mysql_creds):
    """Connect to MySQL and execute SELECT 1."""
    mysql_connector = pytest.importorskip("mysql.connector")
    conn = mysql_connector.connect(
        **mysql_creds,
        autocommit=True,
        connection_timeout=10,
        use_pure=True,
    )
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        assert result == (1,)
        cursor.close()
    finally:
        conn.close()


def test_mysql_matchzy_table_accessible(require_live, mysql_creds):
    """Optionally verify the matchzy_stats_matches table exists and is queryable."""
    mysql_connector = pytest.importorskip("mysql.connector")
    conn = mysql_connector.connect(
        **mysql_creds,
        autocommit=True,
        connection_timeout=10,
        use_pure=True,
    )
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM matchzy_stats_matches")
        (count,) = cursor.fetchone()
        assert isinstance(count, int)
        assert count >= 0
        cursor.close()
    finally:
        conn.close()
