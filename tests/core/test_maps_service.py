"""Tests for core.maps.service.choose_map."""

import pytest
from unittest.mock import patch

from core.maps.service import choose_map


class TestChooseMapUniform:
    """choose_map(maps, use_history=False) → uniform random selection."""

    def test_returns_element_from_pool(self):
        maps = ["de_dust2", "de_inferno", "de_mirage"]
        result = choose_map(maps, use_history=False)
        assert result in maps

    def test_single_map_always_returned(self):
        for _ in range(20):
            assert choose_map(["de_nuke"], use_history=False) == "de_nuke"

    def test_empty_pool_raises(self):
        with pytest.raises(ValueError, match="No maps"):
            choose_map([], use_history=False)

    def test_all_maps_can_be_selected(self):
        """Run enough iterations to statistically cover all maps."""
        maps = ["de_dust2", "de_inferno", "de_mirage"]
        seen = set()
        for _ in range(200):
            seen.add(choose_map(maps, use_history=False))
        assert seen == set(maps)


class TestChooseMapHistory:
    """choose_map(maps, use_history=True) — weighted by inverse play count.

    Requires DB access since _build_history_weights calls matches_db functions.
    """

    def test_history_mode_with_seeded_data(self, seeded_db, monkeypatch_db):
        """With seeded data (dust2 played 2x, inferno 1x), less-played maps
        should have higher weight and thus appear more often."""
        maps = ["de_dust2", "de_inferno", "de_mirage"]
        counts = {m: 0 for m in maps}
        for _ in range(300):
            result = choose_map(maps, use_history=True)
            assert result in maps
            counts[result] += 1

        # de_mirage was never played → should have highest weight (1.0)
        # de_inferno was played 1 out of 3 → weight ~0.67
        # de_dust2 was played 2 out of 3 → weight ~0.33
        # With 300 trials we expect de_mirage > de_dust2
        assert counts["de_mirage"] > counts["de_dust2"]

    def test_history_mode_single_map(self, seeded_db, monkeypatch_db):
        result = choose_map(["de_dust2"], use_history=True)
        assert result == "de_dust2"

    def test_history_mode_empty_db(self, db_conn, monkeypatch_db):
        """No matches in DB → _build_history_weights returns {} → falls back to random."""
        maps = ["de_dust2", "de_inferno"]
        result = choose_map(maps, use_history=True)
        assert result in maps

    def test_history_mode_all_maps_unknown(self, seeded_db, monkeypatch_db):
        """Maps not in history get weight 1.0, effectively uniform among unknowns."""
        maps = ["de_ancient", "de_vertigo", "de_anubis"]
        seen = set()
        for _ in range(100):
            seen.add(choose_map(maps, use_history=True))
        # Should eventually pick all of them
        assert len(seen) >= 2  # at least 2 out of 3 in 100 tries

    def test_history_returns_string(self, seeded_db, monkeypatch_db):
        result = choose_map(["de_dust2", "de_inferno"], use_history=True)
        assert isinstance(result, str)
