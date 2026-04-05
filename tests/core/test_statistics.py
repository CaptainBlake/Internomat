"""Tests for core.stats.statistics (get_overview, get_recent_maps)."""

import pytest
from unittest.mock import patch

from core.stats.statistics import get_overview, get_recent_maps


class TestGetOverview:
    def test_with_seeded_data(self, seeded_db, monkeypatch_db):
        result = get_overview()
        assert result["total_matches"] == 3
        assert result["total_maps"] == 3
        # 6 distinct steamid64 values across all player stats
        assert result["unique_players"] == 6
        assert result["top_map_name"] == "de_dust2"
        assert result["top_map_count"] == 2
        assert result["maps_with_stats"] == 3

    def test_empty_db(self, db_conn, monkeypatch_db):
        result = get_overview()
        assert result["total_matches"] == 0
        assert result["total_maps"] == 0
        assert result["unique_players"] == 0
        assert result["top_map_name"] == ""
        assert result["top_map_count"] == 0
        assert result["demo_matches"] == 0

    def test_overview_keys(self, seeded_db, monkeypatch_db):
        result = get_overview()
        expected_keys = {
            "total_matches", "total_maps", "unique_players",
            "demo_matches", "maps_with_stats", "total_rounds_played",
            "top_map_name", "top_map_count",
        }
        assert set(result.keys()) == expected_keys

    def test_overview_types(self, seeded_db, monkeypatch_db):
        result = get_overview()
        assert isinstance(result["total_matches"], int)
        assert isinstance(result["total_maps"], int)
        assert isinstance(result["unique_players"], int)
        assert isinstance(result["top_map_name"], str)


class TestGetRecentMaps:
    @pytest.fixture(autouse=True)
    def _mock_demo_cache(self):
        """Mock demo_cache calls so get_recent_maps doesn't touch the filesystem."""
        with patch("core.stats.statistics.demo_cache") as mock_cache:
            mock_cache.list_existing_cached_demos_default.return_value = []
            mock_cache.load_parsed_demo_default.return_value = None
            yield mock_cache

    def test_returns_all_maps(self, seeded_db, monkeypatch_db):
        result = get_recent_maps(limit=10)
        assert len(result) == 3

    def test_limit_respected(self, seeded_db, monkeypatch_db):
        result = get_recent_maps(limit=2)
        assert len(result) == 2

    def test_ordering_by_time_desc(self, seeded_db, monkeypatch_db):
        result = get_recent_maps(limit=10)
        # Most recent match (102) should be first
        assert result[0]["match_id"] == "102"
        assert result[-1]["match_id"] == "100"

    def test_row_structure(self, seeded_db, monkeypatch_db):
        result = get_recent_maps(limit=1)
        row = result[0]
        assert "match_id" in row
        assert "map_name" in row
        assert "winner" in row
        assert "team1_score" in row
        assert "team2_score" in row
        assert "played_at" in row
        assert "db_has_data" in row

    def test_empty_db(self, db_conn, monkeypatch_db):
        result = get_recent_maps(limit=10)
        assert result == []

    def test_map_names_correct(self, seeded_db, monkeypatch_db):
        result = get_recent_maps(limit=10)
        map_names = [r["map_name"] for r in result]
        assert "de_dust2" in map_names
        assert "de_inferno" in map_names

    def test_scores_populated(self, seeded_db, monkeypatch_db):
        result = get_recent_maps(limit=10)
        for row in result:
            assert isinstance(row["team1_score"], int)
            assert isinstance(row["team2_score"], int)
            assert row["team1_score"] + row["team2_score"] > 0
