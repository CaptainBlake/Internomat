"""Tests for db.players_db — player CRUD operations."""

from unittest.mock import patch

import pytest


def _patch_conn(module_path, db_file):
    from db.connection_db import get_conn as _get_conn
    return patch(module_path, lambda: _get_conn(db_file))


class TestInsertAndFetchPlayer:

    def test_insert_player_then_fetch(self, db_conn, seed_player):
        p = seed_player(steam64_id="76561198000000001", name="Alice", premier_rating=18000)

        row = db_conn.execute(
            "SELECT * FROM players WHERE steam64_id = ?", (p["steam64_id"],)
        ).fetchone()

        assert row is not None
        assert row["name"] == "Alice"
        assert row["premier_rating"] == 18000

    def test_insert_player_sets_timestamps(self, db_conn, seed_player):
        p = seed_player()

        row = db_conn.execute(
            "SELECT added_at, last_updated FROM players WHERE steam64_id = ?",
            (p["steam64_id"],),
        ).fetchone()

        assert row["added_at"] is not None
        assert row["last_updated"] is not None


class TestUpdatePlayer:

    def test_update_player_name(self, db_conn, seed_player):
        from db.players_db import update_player

        p = seed_player(steam64_id="76561198000000002", name="Bob")

        update_player(
            {"steam64_id": "76561198000000002", "name": "Bobby"},
            conn=db_conn,
        )
        db_conn.commit()

        row = db_conn.execute(
            "SELECT name FROM players WHERE steam64_id = ?", ("76561198000000002",)
        ).fetchone()
        assert row["name"] == "Bobby"


class TestUpsertPlayer:

    def test_upsert_inserts_new_player(self, db_conn):
        from db.players_db import upsert_player

        upsert_player(
            {"steam64_id": "76561198000000010", "name": "NewGuy", "premier_rating": 12000},
            conn=db_conn,
        )
        db_conn.commit()

        row = db_conn.execute(
            "SELECT * FROM players WHERE steam64_id = ?", ("76561198000000010",)
        ).fetchone()

        assert row is not None
        assert row["name"] == "NewGuy"
        assert row["premier_rating"] == 12000

    def test_upsert_updates_existing_player(self, db_conn, seed_player):
        from db.players_db import upsert_player

        seed_player(steam64_id="76561198000000011", name="OldName", premier_rating=10000)

        upsert_player(
            {"steam64_id": "76561198000000011", "name": "NewName", "premier_rating": 20000},
            conn=db_conn,
        )
        db_conn.commit()

        row = db_conn.execute(
            "SELECT name, premier_rating FROM players WHERE steam64_id = ?",
            ("76561198000000011",),
        ).fetchone()

        assert row["name"] == "NewName"
        assert row["premier_rating"] == 20000

    def test_upsert_import_mode_only_sets_name(self, db_conn, seed_player):
        from db.players_db import upsert_player

        seed_player(steam64_id="76561198000000012", name="ImportGuy", premier_rating=15000)

        upsert_player(
            {"steam64_id": "76561198000000012", "name": "ImportGuyRenamed"},
            mode="import",
            conn=db_conn,
        )
        db_conn.commit()

        row = db_conn.execute(
            "SELECT name, premier_rating FROM players WHERE steam64_id = ?",
            ("76561198000000012",),
        ).fetchone()

        assert row["name"] == "ImportGuyRenamed"
        # premier_rating should stay unchanged — import mode doesn't touch it
        assert row["premier_rating"] == 15000


class TestDeletePlayer:

    def test_delete_player_removes_row(self, db_conn, db_file, seed_player):
        from db.players_db import delete_player

        seed_player(steam64_id="76561198000000020", name="Doomed")

        with _patch_conn("db.players_db.get_conn", db_file):
            delete_player("76561198000000020")

        row = db_conn.execute(
            "SELECT 1 FROM players WHERE steam64_id = ?", ("76561198000000020",)
        ).fetchone()
        assert row is None


class TestGetPlayers:

    def test_get_players_returns_all(self, db_conn, db_file, seed_player):
        from db.players_db import get_players

        seed_player(steam64_id="76561198000000030", name="P1", premier_rating=10000)
        seed_player(steam64_id="76561198000000031", name="P2", premier_rating=20000)

        with _patch_conn("db.players_db.get_conn", db_file):
            rows = get_players()

        assert len(rows) == 2

    def test_get_players_ordered_by_rating_desc(self, db_conn, db_file, seed_player):
        from db.players_db import get_players

        seed_player(steam64_id="76561198000000040", name="Low", premier_rating=5000)
        seed_player(steam64_id="76561198000000041", name="High", premier_rating=25000)

        with _patch_conn("db.players_db.get_conn", db_file):
            rows = get_players()

        assert rows[0]["name"] == "High"
        assert rows[1]["name"] == "Low"

    def test_get_players_empty_db(self, db_conn, db_file):
        from db.players_db import get_players

        with _patch_conn("db.players_db.get_conn", db_file):
            rows = get_players()

        assert rows == []


class TestUpsertPlayersFromMatchStats:

    def test_imports_players_from_stat_rows(self, db_conn):
        from db.players_db import upsert_players_from_match_stats

        rows = [
            {"steam64_id": "76561198000000050", "name": "StatPlayer1"},
            {"steamid64": "76561198000000051", "name": "StatPlayer2"},
        ]

        count = upsert_players_from_match_stats(rows, conn=db_conn)
        db_conn.commit()

        assert count == 2
        row = db_conn.execute(
            "SELECT 1 FROM players WHERE steam64_id = ?", ("76561198000000050",)
        ).fetchone()
        assert row is not None

    def test_skips_duplicate_steamids(self, db_conn):
        from db.players_db import upsert_players_from_match_stats

        rows = [
            {"steam64_id": "76561198000000060", "name": "Dup"},
            {"steam64_id": "76561198000000060", "name": "Dup"},
        ]

        count = upsert_players_from_match_stats(rows, conn=db_conn)
        assert count == 1

    def test_empty_rows_returns_zero(self, db_conn):
        from db.players_db import upsert_players_from_match_stats

        assert upsert_players_from_match_stats([], conn=db_conn) == 0
        assert upsert_players_from_match_stats(None, conn=db_conn) == 0
