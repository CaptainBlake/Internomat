"""Tests for db.stats_db — leaderboard queries."""

from unittest.mock import patch

import pytest

from tests.db.conftest import _make_player_stats


def _patch_conn(module_path, db_file):
    from db.connection_db import get_conn as _get_conn
    return patch(module_path, lambda: _get_conn(db_file))


class TestFetchTopKills:

    def test_top_kills_ordering(self, db_conn, db_file, seed_match, seed_player_stats):
        from db.stats_db import fetch_top_kills

        seed_match(
            match_kwargs={"match_id": "100"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        seed_player_stats(
            steamid64="76561198000000001", match_id="100", map_number=0,
            name="LowKiller", kills=5,
        )
        seed_player_stats(
            steamid64="76561198000000002", match_id="100", map_number=0,
            name="HighKiller", kills=30,
        )

        with _patch_conn("db.stats_db.get_conn", db_file):
            rows = fetch_top_kills(10)

        assert len(rows) == 2
        # HighKiller first
        assert rows[0][0] == "HighKiller"
        assert rows[0][2] == 30

    def test_top_kills_limit(self, db_conn, db_file, seed_match, seed_player_stats):
        from db.stats_db import fetch_top_kills

        seed_match(
            match_kwargs={"match_id": "110"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        for i in range(5):
            seed_player_stats(
                steamid64=f"7656119800000010{i}", match_id="110", map_number=0,
                name=f"Player{i}", kills=10 + i,
            )

        with _patch_conn("db.stats_db.get_conn", db_file):
            rows = fetch_top_kills(3)

        assert len(rows) == 3

    def test_top_kills_empty_db(self, db_conn, db_file):
        from db.stats_db import fetch_top_kills

        with _patch_conn("db.stats_db.get_conn", db_file):
            rows = fetch_top_kills(10)

        assert rows == []

    def test_top_kills_aggregates_across_matches(self, db_conn, db_file, seed_match, seed_player_stats):
        from db.stats_db import fetch_top_kills

        seed_match(
            match_kwargs={"match_id": "120"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        seed_match(
            match_kwargs={"match_id": "121"},
            map_kwargs={"map_number": 0, "map_name": "de_inferno"},
        )

        seed_player_stats(
            steamid64="76561198000000001", match_id="120", map_number=0,
            name="Agg", kills=10,
        )
        seed_player_stats(
            steamid64="76561198000000001", match_id="121", map_number=0,
            name="Agg", kills=15,
        )

        with _patch_conn("db.stats_db.get_conn", db_file):
            rows = fetch_top_kills(10)

        assert rows[0][2] == 25


class TestFetchTopDeaths:

    def test_top_deaths_ordering(self, db_conn, db_file, seed_match, seed_player_stats):
        from db.stats_db import fetch_top_deaths

        seed_match(
            match_kwargs={"match_id": "200"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        seed_player_stats(
            steamid64="76561198000000001", match_id="200", map_number=0,
            name="DiesAlot", deaths=25,
        )
        seed_player_stats(
            steamid64="76561198000000002", match_id="200", map_number=0,
            name="Survivor", deaths=5,
        )

        with _patch_conn("db.stats_db.get_conn", db_file):
            rows = fetch_top_deaths(10)

        assert rows[0][0] == "DiesAlot"
        assert rows[0][2] == 25

    def test_top_deaths_empty(self, db_conn, db_file):
        from db.stats_db import fetch_top_deaths

        with _patch_conn("db.stats_db.get_conn", db_file):
            assert fetch_top_deaths(10) == []


class TestFetchTopRatings:

    def test_top_ratings_ordering(self, db_conn, db_file, seed_player):
        from db.stats_db import fetch_top_ratings

        seed_player(steamid64="76561198000000001", name="Low", premier_rating=5000)
        seed_player(steamid64="76561198000000002", name="High", premier_rating=25000)

        with _patch_conn("db.stats_db.get_conn", db_file):
            rows = fetch_top_ratings(10)

        assert rows[0][0] == "High"
        assert rows[0][2] == 25000

    def test_top_ratings_empty(self, db_conn, db_file):
        from db.stats_db import fetch_top_ratings

        with _patch_conn("db.stats_db.get_conn", db_file):
            assert fetch_top_ratings(10) == []


class TestFetchAvgDamage:

    def test_avg_damage_calculation(self, db_conn, db_file, seed_match, seed_player_stats):
        from db.stats_db import fetch_avg_damage

        seed_match(
            match_kwargs={"match_id": "300"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        seed_match(
            match_kwargs={"match_id": "301"},
            map_kwargs={"map_number": 0, "map_name": "de_inferno"},
        )

        seed_player_stats(
            steamid64="76561198000000001", match_id="300", map_number=0,
            name="Damager", damage=2000,
        )
        seed_player_stats(
            steamid64="76561198000000001", match_id="301", map_number=0,
            name="Damager", damage=3000,
        )

        with _patch_conn("db.stats_db.get_conn", db_file):
            rows = fetch_avg_damage(10)

        assert len(rows) == 1
        assert rows[0][2] == 2500.0

    def test_avg_damage_empty(self, db_conn, db_file):
        from db.stats_db import fetch_avg_damage

        with _patch_conn("db.stats_db.get_conn", db_file):
            assert fetch_avg_damage(10) == []
