"""Tests for services.matchzy — MatchZy MySQL-to-SQLite sync with mocked MySQL."""

from unittest.mock import patch, MagicMock

import pytest

from services.matchzy import MatchZy


# ---------------------------------------------------------------------------
# Canned MySQL data
# ---------------------------------------------------------------------------

# matchzy_stats_matches columns:
# (match_id, start_time, end_time, winner, series_type,
#  team1_name, team1_score, team2_name, team2_score, server_ip)
CANNED_MATCHES = [
    ("M1", "2026-01-10T20:00:00", "2026-01-10T21:00:00", "team_a",
     "bo1", "team_a", 13, "team_b", 7, "10.0.0.1"),
]

# matchzy_stats_maps columns:
# (match_id, map_number, start_time, end_time, winner, map_name,
#  team1_score, team2_score)
CANNED_MAPS = [
    ("M1", 0, "2026-01-10T20:00:00", "2026-01-10T21:00:00",
     "team_a", "de_dust2", 13, 7),
]

# matchzy_stats_players columns:
# (match_id, map_number, steamid64, team, name,
#  kills, deaths, damage, assists,
#  enemy5ks, enemy4ks, enemy3ks, enemy2ks,
#  utility_count, utility_damage, utility_successes, utility_enemies,
#  flash_count, flash_successes,
#  health_points_removed_total, health_points_dealt_total,
#  shots_fired_total, shots_on_target_total,
#  v1_count, v1_wins, v2_count, v2_wins,
#  entry_count, entry_wins,
#  equipment_value, money_saved, kill_reward, live_time,
#  head_shot_kills, cash_earned, enemies_flashed)
CANNED_PLAYERS = [
    ("M1", 0, "76561198000000001", "team_a", "Alice",
     20, 10, 2400, 5,
     0, 1, 2, 3,
     10, 200, 5, 3,
     8, 4,
     1800, 2400,
     150, 50,
     3, 2, 1, 0,
     5, 3,
     25000, 1200, 3000, 900,
     12, 18000, 6),
]


def _query_side_effect(query):
    """Route MatchZy._query calls to canned data based on SQL table name."""
    if "matchzy_stats_maps" in query:
        return list(CANNED_MAPS)
    if "matchzy_stats_players" in query:
        return list(CANNED_PLAYERS)
    if "matchzy_stats_matches" in query:
        return list(CANNED_MATCHES)
    return []


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def matchzy_settings(monkeypatch):
    """Populate the settings singleton with valid MatchZy config."""
    from core.settings.settings import settings

    monkeypatch.setattr(settings, "matchzy_host", "127.0.0.1")
    monkeypatch.setattr(settings, "matchzy_port", 3306)
    monkeypatch.setattr(settings, "matchzy_user", "testuser")
    monkeypatch.setattr(settings, "matchzy_password", "testpass")
    monkeypatch.setattr(settings, "matchzy_database", "matchzy_db")
    monkeypatch.setattr(settings, "auto_import_match_players", False)


# ---------------------------------------------------------------------------
# Tests: _validate_config
# ---------------------------------------------------------------------------

class TestValidateConfig:

    def test_missing_host_raises(self, monkeypatch):
        from core.settings.settings import settings
        monkeypatch.setattr(settings, "matchzy_host", "")
        monkeypatch.setattr(settings, "matchzy_port", 3306)
        monkeypatch.setattr(settings, "matchzy_user", "u")
        monkeypatch.setattr(settings, "matchzy_database", "d")

        mz = MatchZy()
        with pytest.raises(RuntimeError, match="Missing MatchZy config"):
            mz._validate_config()

    def test_valid_config_does_not_raise(self, matchzy_settings):
        mz = MatchZy()
        mz._validate_config()  # Should not raise


# ---------------------------------------------------------------------------
# Tests: connect
# ---------------------------------------------------------------------------

class TestConnect:

    def test_connect_success(self, matchzy_settings):
        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True

        with patch("mysql.connector.connect", return_value=mock_conn):
            mz = MatchZy()
            conn = mz.connect()
            assert conn is mock_conn

    def test_connect_failure_raises_runtime_error(self, matchzy_settings):
        from mysql.connector import Error

        with patch("mysql.connector.connect", side_effect=Error("Connection refused")):
            mz = MatchZy()
            with pytest.raises(RuntimeError, match="MySQL connection failed"):
                mz.connect()

    def test_connect_reuses_existing_connection(self, matchzy_settings):
        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True

        with patch("mysql.connector.connect", return_value=mock_conn) as mock_connect:
            mz = MatchZy()
            mz.connect()
            mz.connect()
            # mysql.connector.connect should be called only once
            mock_connect.assert_called_once()


# ---------------------------------------------------------------------------
# Tests: _to_int
# ---------------------------------------------------------------------------

class TestToInt:

    def test_valid_int(self):
        assert MatchZy()._to_int(42) == 42

    def test_valid_str_int(self):
        assert MatchZy()._to_int("13") == 13

    def test_none_returns_zero(self):
        assert MatchZy()._to_int(None) == 0

    def test_invalid_str_returns_zero(self):
        assert MatchZy()._to_int("abc") == 0


# ---------------------------------------------------------------------------
# Tests: sync_to_local (the main integration point)
# ---------------------------------------------------------------------------

class TestSyncToLocal:

    def test_sync_inserts_match_and_map_and_players(
        self, monkeypatch_db, db_conn, matchzy_settings
    ):
        """Full happy-path: mocked MySQL rows land in local SQLite."""
        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True

        with patch("mysql.connector.connect", return_value=mock_conn):
            mz = MatchZy()
            mz._query = MagicMock(side_effect=_query_side_effect)
            mz.sync_to_local()

        # Verify match inserted
        row = db_conn.execute(
            "SELECT * FROM matches WHERE match_id = ?", ("M1",)
        ).fetchone()
        assert row is not None
        assert row["team1_name"] == "team_a"
        assert row["team1_score"] == 13

        # Verify map inserted
        mrow = db_conn.execute(
            "SELECT * FROM match_maps WHERE match_id = ? AND map_number = ?",
            ("M1", 0),
        ).fetchone()
        assert mrow is not None
        assert mrow["map_name"] == "de_dust2"

        # Verify player stats inserted
        prow = db_conn.execute(
            "SELECT * FROM match_player_stats WHERE match_id = ? AND steamid64 = ?",
            ("M1", "76561198000000001"),
        ).fetchone()
        assert prow is not None
        assert prow["kills"] == 20
        assert prow["deaths"] == 10
        assert prow["name"] == "Alice"

    def test_sync_skips_existing_match(
        self, monkeypatch_db, db_conn, matchzy_settings
    ):
        """If a match already exists in local DB, it should be skipped."""
        from db.matches_db import insert_match

        insert_match({"match_id": "M1"}, conn=db_conn)
        db_conn.commit()

        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True

        with patch("mysql.connector.connect", return_value=mock_conn):
            mz = MatchZy()
            mz._query = MagicMock(side_effect=_query_side_effect)
            mz.sync_to_local()

        # No map should be inserted for the skipped match
        mrow = db_conn.execute(
            "SELECT * FROM match_maps WHERE match_id = ?", ("M1",)
        ).fetchone()
        assert mrow is None

    def test_sync_skips_unfinished_match(
        self, monkeypatch_db, db_conn, matchzy_settings
    ):
        """Maps with no end_time should be skipped."""
        unfinished_maps = [
            ("M2", 0, "2026-01-10T20:00:00", None,  # end_time=None
             "team_a", "de_inferno", 5, 3),
        ]

        def query_side(query):
            if "matchzy_stats_maps" in query:
                return unfinished_maps
            if "matchzy_stats_players" in query:
                return []
            if "matchzy_stats_matches" in query:
                return []
            return []

        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True

        with patch("mysql.connector.connect", return_value=mock_conn):
            mz = MatchZy()
            mz._query = MagicMock(side_effect=query_side)
            mz.sync_to_local()

        row = db_conn.execute(
            "SELECT * FROM matches WHERE match_id = ?", ("M2",)
        ).fetchone()
        assert row is None

    def test_sync_match_without_match_data_inserts_minimal(
        self, monkeypatch_db, db_conn, matchzy_settings
    ):
        """If matchzy_stats_matches has no row for a match_id, insert a
        minimal match record with just the match_id."""
        maps_only = [
            ("ORPHAN", 0, "2026-01-10T20:00:00", "2026-01-10T21:00:00",
             "team_x", "de_mirage", 13, 10),
        ]

        def query_side(query):
            if "matchzy_stats_maps" in query:
                return maps_only
            if "matchzy_stats_players" in query:
                return []
            if "matchzy_stats_matches" in query:
                return []  # no match row
            return []

        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True

        with patch("mysql.connector.connect", return_value=mock_conn):
            mz = MatchZy()
            mz._query = MagicMock(side_effect=query_side)
            mz.sync_to_local()

        row = db_conn.execute(
            "SELECT * FROM matches WHERE match_id = ?", ("ORPHAN",)
        ).fetchone()
        assert row is not None
        assert row["match_id"] == "ORPHAN"
        # team data should be None since no matches row existed
        assert row["team1_name"] is None

    def test_sync_auto_import_players(
        self, monkeypatch_db, db_conn, matchzy_settings, monkeypatch
    ):
        """When auto_import_match_players is True, players should be
        upserted into the pool and maps imported."""
        from core.settings.settings import settings
        monkeypatch.setattr(settings, "auto_import_match_players", True)

        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True

        with patch("mysql.connector.connect", return_value=mock_conn):
            mz = MatchZy()
            mz._query = MagicMock(side_effect=_query_side_effect)
            mz.sync_to_local()

        # Player should exist in the players pool
        prow = db_conn.execute(
            "SELECT * FROM players WHERE steam64_id = ?",
            ("76561198000000001",),
        ).fetchone()
        assert prow is not None
        assert prow["name"] == "Alice"

    def test_sync_closes_mysql_connection(self, monkeypatch_db, db_conn, matchzy_settings):
        """sync_to_local must close the MySQL connection in the finally block."""
        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True

        with patch("mysql.connector.connect", return_value=mock_conn):
            mz = MatchZy()
            # Set conn so close() sees an active connection
            mz.conn = mock_conn
            mz._query = MagicMock(side_effect=_query_side_effect)
            mz.sync_to_local()

            mock_conn.close.assert_called()

    def test_sync_empty_data(self, monkeypatch_db, db_conn, matchzy_settings):
        """sync_to_local with empty tables should succeed without inserting anything."""
        mock_conn = MagicMock()
        mock_conn.is_connected.return_value = True

        with patch("mysql.connector.connect", return_value=mock_conn):
            mz = MatchZy()
            mz._query = MagicMock(return_value=[])
            mz.sync_to_local()

        count = db_conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
        assert count == 0
