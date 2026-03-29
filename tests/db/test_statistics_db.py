"""Tests for db.statistics_db — overview and recent maps queries."""

from unittest.mock import patch

import pytest

from tests.db.conftest import _make_match, _make_match_map, _make_player_stats


def _patch_conn(module_path, db_file):
    from db.connection_db import get_conn as _get_conn
    return patch(module_path, lambda: _get_conn(db_file))


class TestFetchOverview:

    def test_empty_db_returns_zeros(self, db_conn, db_file):
        from db.statistics_db import fetch_overview

        with _patch_conn("db.statistics_db.get_conn", db_file):
            row = fetch_overview()

        assert row["total_matches"] == 0
        assert row["total_maps"] == 0
        assert row["unique_players"] == 0
        assert row["demo_matches"] == 0

    def test_overview_with_seeded_data(self, db_conn, db_file, seed_match, seed_player_stats):
        from db.statistics_db import fetch_overview

        seed_match(
            match_kwargs={"match_id": "100"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        seed_match(
            match_kwargs={"match_id": "101"},
            map_kwargs={"map_number": 0, "map_name": "de_inferno"},
        )
        seed_player_stats(steamid64="76561198000000001", match_id="100", map_number=0)
        seed_player_stats(steamid64="76561198000000002", match_id="101", map_number=0)

        with _patch_conn("db.statistics_db.get_conn", db_file):
            row = fetch_overview()

        assert row["total_matches"] == 2
        assert row["total_maps"] == 2
        assert row["unique_players"] == 2

    def test_overview_top_map(self, db_conn, db_file, seed_match):
        from db.statistics_db import fetch_overview

        seed_match(
            match_kwargs={"match_id": "200"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        seed_match(
            match_kwargs={"match_id": "201"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        seed_match(
            match_kwargs={"match_id": "202"},
            map_kwargs={"map_number": 0, "map_name": "de_inferno"},
        )

        with _patch_conn("db.statistics_db.get_conn", db_file):
            row = fetch_overview()

        assert row["top_map_name"] == "de_dust2"
        assert row["top_map_count"] == 2

    def test_overview_demo_count(self, db_conn, db_file, seed_match):
        from db.matches_db import set_match_has_demo
        from db.statistics_db import fetch_overview

        seed_match(match_kwargs={"match_id": "300"})
        seed_match(match_kwargs={"match_id": "301"})

        set_match_has_demo("300", has_demo=True, conn=db_conn)
        db_conn.commit()

        with _patch_conn("db.statistics_db.get_conn", db_file):
            row = fetch_overview()

        assert row["demo_matches"] == 1

    def test_overview_maps_with_stats(self, db_conn, db_file, seed_match, seed_player_stats):
        from db.statistics_db import fetch_overview

        seed_match(
            match_kwargs={"match_id": "400"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        seed_player_stats(steamid64="76561198000000001", match_id="400", map_number=0)

        with _patch_conn("db.statistics_db.get_conn", db_file):
            row = fetch_overview()

        assert row["maps_with_stats"] == 1


class TestFetchRecentMaps:

    def test_recent_maps_ordering(self, db_conn, db_file, seed_match):
        from db.statistics_db import fetch_recent_maps

        seed_match(
            match_kwargs={"match_id": "500", "start_time": "2026-01-01T10:00:00"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2",
                        "end_time": "2026-01-01T11:00:00"},
        )
        seed_match(
            match_kwargs={"match_id": "501", "start_time": "2026-01-02T10:00:00"},
            map_kwargs={"map_number": 0, "map_name": "de_inferno",
                        "end_time": "2026-01-02T11:00:00"},
        )

        with _patch_conn("db.statistics_db.get_conn", db_file):
            rows = fetch_recent_maps(10)

        # Most recent first
        assert len(rows) == 2
        assert rows[0]["map_name"] == "de_inferno"
        assert rows[1]["map_name"] == "de_dust2"

    def test_recent_maps_limit(self, db_conn, db_file, seed_match):
        from db.statistics_db import fetch_recent_maps

        for i in range(5):
            seed_match(
                match_kwargs={"match_id": str(600 + i)},
                map_kwargs={"map_number": 0, "map_name": f"de_map{i}",
                            "end_time": f"2026-01-0{i+1}T10:00:00"},
            )

        with _patch_conn("db.statistics_db.get_conn", db_file):
            rows = fetch_recent_maps(3)

        assert len(rows) == 3

    def test_recent_maps_empty_db(self, db_conn, db_file):
        from db.statistics_db import fetch_recent_maps

        with _patch_conn("db.statistics_db.get_conn", db_file):
            rows = fetch_recent_maps(10)

        assert rows == []
