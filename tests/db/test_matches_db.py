"""Tests for db.matches_db — match, map, and player-stats CRUD."""

from unittest.mock import patch

import pytest

from tests.db.conftest import (
    _make_match,
    _make_match_map,
    _make_player_stats,
)


def _patch_conn(module_path, db_file):
    from db.connection_db import get_conn as _get_conn
    return patch(module_path, lambda: _get_conn(db_file))


class TestInsertMatch:

    def test_insert_match_then_fetch(self, db_conn):
        from db.matches_db import insert_match

        m = _make_match(match_id="200")
        insert_match(m, conn=db_conn)
        db_conn.commit()

        row = db_conn.execute(
            "SELECT * FROM matches WHERE match_id = ?", ("200",)
        ).fetchone()

        assert row is not None
        assert row["match_id"] == "200"
        assert row["team1_name"] == "team_alpha"
        assert row["team1_score"] == 13

    def test_insert_match_upsert_updates_on_conflict(self, db_conn):
        from db.matches_db import insert_match

        insert_match(_make_match(match_id="201", team1_score=10), conn=db_conn)
        db_conn.commit()

        # Re-insert same match_id with different score
        insert_match(_make_match(match_id="201", team1_score=16), conn=db_conn)
        db_conn.commit()

        row = db_conn.execute(
            "SELECT team1_score FROM matches WHERE match_id = ?", ("201",)
        ).fetchone()
        assert row["team1_score"] == 16

    def test_match_exists_true(self, db_conn, db_file, seed_match):
        from db.matches_db import match_exists

        seed_match(match_kwargs={"match_id": "202"})

        with _patch_conn("db.matches_db.get_conn", db_file):
            assert match_exists("202") is True

    def test_match_exists_false(self, db_conn, db_file):
        from db.matches_db import match_exists

        with _patch_conn("db.matches_db.get_conn", db_file):
            assert match_exists("999") is False


class TestInsertMatchMap:

    def test_insert_match_map_linked(self, db_conn, seed_match):
        seed_match(
            match_kwargs={"match_id": "300"},
            map_kwargs={"map_number": 0, "map_name": "de_inferno"},
        )

        row = db_conn.execute(
            "SELECT * FROM match_maps WHERE match_id = ? AND map_number = ?",
            ("300", 0),
        ).fetchone()

        assert row is not None
        assert row["map_name"] == "de_inferno"

    def test_insert_match_map_upsert(self, db_conn, seed_match):
        from db.matches_db import insert_match_map

        seed_match(
            match_kwargs={"match_id": "301"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2", "team1_score": 10},
        )

        # Upsert same match_id+map_number with different score
        insert_match_map(
            _make_match_map(match_id="301", map_number=0, map_name="de_dust2", team1_score=16),
            conn=db_conn,
        )
        db_conn.commit()

        row = db_conn.execute(
            "SELECT team1_score FROM match_maps WHERE match_id = ? AND map_number = ?",
            ("301", 0),
        ).fetchone()
        assert row["team1_score"] == 16

    def test_multiple_maps_per_match(self, db_conn):
        from db.matches_db import insert_match, insert_match_map

        insert_match(_make_match(match_id="302"), conn=db_conn)
        insert_match_map(
            _make_match_map(match_id="302", map_number=0, map_name="de_mirage"),
            conn=db_conn,
        )
        insert_match_map(
            _make_match_map(match_id="302", map_number=1, map_name="de_nuke"),
            conn=db_conn,
        )
        db_conn.commit()

        rows = db_conn.execute(
            "SELECT * FROM match_maps WHERE match_id = ? ORDER BY map_number", ("302",)
        ).fetchall()

        assert len(rows) == 2
        assert rows[0]["map_name"] == "de_mirage"
        assert rows[1]["map_name"] == "de_nuke"


class TestInsertMatchPlayerStats:

    def test_insert_player_stats_then_fetch(self, db_conn, seed_match, seed_player_stats):
        seed_match(
            match_kwargs={"match_id": "400"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        ps = seed_player_stats(
            steamid64="76561198000000001",
            match_id="400",
            map_number=0,
            kills=25,
            deaths=12,
        )

        row = db_conn.execute(
            "SELECT * FROM match_player_stats WHERE steamid64 = ? AND match_id = ? AND map_number = ?",
            ("76561198000000001", "400", 0),
        ).fetchone()

        assert row is not None
        assert row["kills"] == 25
        assert row["deaths"] == 12

    def test_player_stats_upsert_on_conflict(self, db_conn, seed_match, seed_player_stats):
        seed_match(
            match_kwargs={"match_id": "401"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        seed_player_stats(
            steamid64="76561198000000001", match_id="401", map_number=0, kills=10
        )
        # Upsert with different kills
        seed_player_stats(
            steamid64="76561198000000001", match_id="401", map_number=0, kills=30
        )

        row = db_conn.execute(
            "SELECT kills FROM match_player_stats WHERE steamid64 = ? AND match_id = ? AND map_number = ?",
            ("76561198000000001", "401", 0),
        ).fetchone()
        assert row["kills"] == 30

    def test_insert_many_player_stats(self, db_conn, seed_match):
        from db.matches_db import insert_match_player_stats_many

        seed_match(
            match_kwargs={"match_id": "402"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )

        rows = [
            _make_player_stats(steamid64="76561198000000001", match_id="402", map_number=0, kills=20),
            _make_player_stats(steamid64="76561198000000002", match_id="402", map_number=0, kills=15),
        ]
        insert_match_player_stats_many(rows, conn=db_conn)
        db_conn.commit()

        count = db_conn.execute(
            "SELECT COUNT(*) AS c FROM match_player_stats WHERE match_id = ?", ("402",)
        ).fetchone()["c"]
        assert count == 2

    def test_insert_many_empty_list(self, db_conn):
        from db.matches_db import insert_match_player_stats_many

        # Should not raise
        insert_match_player_stats_many([], conn=db_conn)
        insert_match_player_stats_many(None, conn=db_conn)


class TestGetMatchMapSteamids:

    def test_returns_set_of_steamids(self, db_conn, seed_match, seed_player_stats):
        seed_match(
            match_kwargs={"match_id": "500"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        seed_player_stats(steamid64="76561198000000001", match_id="500", map_number=0)
        seed_player_stats(steamid64="76561198000000002", match_id="500", map_number=0)

        from db.matches_db import get_match_map_steamids

        result = get_match_map_steamids("500", 0, conn=db_conn)

        assert isinstance(result, set)
        assert result == {"76561198000000001", "76561198000000002"}


class TestGetAllMatchesWithMaps:

    def test_returns_matches_with_maps(self, db_conn, seed_match):
        from db.matches_db import get_all_matches_with_maps

        seed_match(
            match_kwargs={"match_id": "600"},
            map_kwargs={"map_number": 0, "map_name": "de_inferno"},
        )

        result = get_all_matches_with_maps(conn=db_conn)
        assert len(result) == 1
        assert result[0]["match_id"] == "600"
        assert len(result[0]["maps"]) == 1
        assert result[0]["maps"][0]["map_name"] == "de_inferno"


class TestSetMatchHasDemo:

    def test_set_demo_flag(self, db_conn, seed_match):
        from db.matches_db import set_match_has_demo

        seed_match(match_kwargs={"match_id": "700"})

        set_match_has_demo("700", has_demo=True, conn=db_conn)
        db_conn.commit()

        row = db_conn.execute(
            "SELECT demo FROM matches WHERE match_id = ?", ("700",)
        ).fetchone()
        assert row["demo"] == 1


class TestGetTotalMatchesCount:

    def test_count_with_seeded_matches(self, db_conn, seed_match):
        from db.matches_db import get_total_matches_count

        seed_match(match_kwargs={"match_id": "800"})
        seed_match(match_kwargs={"match_id": "801"})

        assert get_total_matches_count(conn=db_conn) == 2

    def test_count_empty_db(self, db_conn):
        from db.matches_db import get_total_matches_count

        assert get_total_matches_count(conn=db_conn) == 0


class TestGetMapPlayCounts:

    def test_map_play_counts(self, db_conn, seed_match):
        from db.matches_db import get_map_play_counts

        seed_match(
            match_kwargs={"match_id": "900"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        seed_match(
            match_kwargs={"match_id": "901"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        seed_match(
            match_kwargs={"match_id": "902"},
            map_kwargs={"map_number": 0, "map_name": "de_inferno"},
        )

        counts = get_map_play_counts(conn=db_conn)
        assert counts["de_dust2"] == 2
        assert counts["de_inferno"] == 1
