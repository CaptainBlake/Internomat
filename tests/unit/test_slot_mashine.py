"""Tests for core.maps.slot_mashine — random and weighted map selection."""

import pytest
from core.maps.slot_mashine import choose_random_map, choose_weighted_map


# -- choose_random_map --

def test_choose_random_map_returns_element_from_list():
    maps = ["de_dust2", "de_mirage", "de_inferno"]
    result = choose_random_map(maps)
    assert result in maps


def test_choose_random_map_single_element():
    maps = ["de_dust2"]
    assert choose_random_map(maps) == "de_dust2"


def test_choose_random_map_empty_raises():
    with pytest.raises(ValueError, match="No maps in pool"):
        choose_random_map([])


# -- choose_weighted_map --

def test_choose_weighted_map_returns_element_from_list():
    maps = ["de_dust2", "de_mirage", "de_inferno"]
    weights = {"de_dust2": 1.0, "de_mirage": 2.0, "de_inferno": 3.0}
    result = choose_weighted_map(maps, weights)
    assert result in maps


def test_choose_weighted_map_single_element():
    maps = ["de_dust2"]
    weights = {"de_dust2": 5.0}
    assert choose_weighted_map(maps, weights) == "de_dust2"


def test_choose_weighted_map_zero_weights_falls_back():
    """When all weights are zero, falls back to choose_random_map."""
    maps = ["de_dust2", "de_mirage"]
    weights = {"de_dust2": 0.0, "de_mirage": 0.0}
    result = choose_weighted_map(maps, weights)
    assert result in maps


def test_choose_weighted_map_missing_weights_treated_as_zero():
    """Maps not in weights_by_map get weight 0.0."""
    maps = ["de_dust2", "de_mirage"]
    weights = {}  # all missing → all zero → fallback to random
    result = choose_weighted_map(maps, weights)
    assert result in maps


def test_choose_weighted_map_empty_raises():
    with pytest.raises(ValueError, match="No maps in pool"):
        choose_weighted_map([], {"de_dust2": 1.0})


def test_choose_weighted_map_heavily_weighted():
    """With one map having much higher weight, it should be chosen most of the time."""
    maps = ["de_dust2", "de_mirage"]
    weights = {"de_dust2": 1000.0, "de_mirage": 0.001}
    results = [choose_weighted_map(maps, weights) for _ in range(100)]
    assert results.count("de_dust2") > 80
