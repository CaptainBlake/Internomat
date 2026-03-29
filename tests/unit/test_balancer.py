"""Tests for core.teams.balancer — find_best_teams and helpers."""

import pytest
from core.teams.balancer import find_best_teams


def _make_players(ratings):
    """Build player tuples: (id, name, rating)."""
    return [(f"id_{i}", f"Player_{i}", r) for i, r in enumerate(ratings)]


# -- Basic splits --

def test_find_best_teams_4_players():
    players = _make_players([100, 90, 80, 70])
    best_score, candidates, acceptable = find_best_teams(players, tolerance=50, dist_weight=0.25)
    assert len(acceptable) > 0
    # Each acceptable entry: (score, team_a, team_b, diff, dist)
    score, team_a, team_b, diff, dist = acceptable[0]
    assert len(team_a) == 2
    assert len(team_b) == 2
    ids = {p[0] for p in team_a} | {p[0] for p in team_b}
    assert ids == {p[0] for p in players}


def test_find_best_teams_6_players():
    players = _make_players([100, 95, 90, 85, 80, 75])
    best_score, candidates, acceptable = find_best_teams(players, tolerance=50, dist_weight=0.25)
    score, team_a, team_b, *_ = acceptable[0]
    assert len(team_a) == 3
    assert len(team_b) == 3


def test_find_best_teams_10_players():
    players = _make_players([120, 115, 110, 105, 100, 95, 90, 85, 80, 75])
    best_score, candidates, acceptable = find_best_teams(players, tolerance=50, dist_weight=0.25)
    score, team_a, team_b, *_ = acceptable[0]
    assert len(team_a) == 5
    assert len(team_b) == 5


def test_find_best_teams_2_players():
    players = _make_players([100, 90])
    best_score, candidates, acceptable = find_best_teams(players, tolerance=50, dist_weight=0.25)
    score, team_a, team_b, *_ = acceptable[0]
    assert len(team_a) == 1
    assert len(team_b) == 1


# -- Edge cases --

def test_find_best_teams_identical_ratings():
    """All players have the same rating — any split is optimal."""
    players = _make_players([100, 100, 100, 100])
    best_score, candidates, acceptable = find_best_teams(players, tolerance=0, dist_weight=0.25)
    score, team_a, team_b, diff, dist = acceptable[0]
    assert diff == 0
    assert len(team_a) == 2
    assert len(team_b) == 2


def test_find_best_teams_tolerance_zero():
    """With tolerance=0 only the mathematically best splits are acceptable."""
    players = _make_players([100, 80, 60, 40])
    best_score, candidates, acceptable = find_best_teams(players, tolerance=0, dist_weight=0.25)
    for score, *_ in acceptable:
        assert score == best_score


def test_find_best_teams_tolerance_large():
    """With a large tolerance, all candidates should be acceptable."""
    players = _make_players([100, 80, 60, 40])
    best_score, candidates, acceptable = find_best_teams(players, tolerance=1000, dist_weight=0.25)
    assert len(acceptable) == len(candidates)


# -- Return structure --

def test_return_structure():
    players = _make_players([100, 90, 80, 70])
    result = find_best_teams(players, tolerance=50, dist_weight=0.25)
    assert len(result) == 3
    best_score, candidates, acceptable = result
    assert isinstance(best_score, (int, float))
    assert isinstance(candidates, list)
    assert isinstance(acceptable, list)
    # Each candidate is (score, team_a, team_b, diff, dist)
    for c in candidates:
        assert len(c) == 5


def test_no_duplicate_candidates():
    """Normalized deduplication should prevent mirrored team pairs."""
    players = _make_players([100, 90, 80, 70])
    _, candidates, _ = find_best_teams(players, tolerance=50, dist_weight=0.25)
    keys = set()
    for _, team_a, team_b, *_ in candidates:
        a = tuple(sorted(p[0] for p in team_a))
        b = tuple(sorted(p[0] for p in team_b))
        key = tuple(sorted([a, b]))
        assert key not in keys, "Duplicate candidate found"
        keys.add(key)


def test_all_players_assigned():
    """Every player must appear on exactly one team."""
    players = _make_players([100, 90, 80, 70, 60, 50])
    _, _, acceptable = find_best_teams(players, tolerance=50, dist_weight=0.25)
    _, team_a, team_b, *_ = acceptable[0]
    all_ids = [p[0] for p in team_a] + [p[0] for p in team_b]
    assert sorted(all_ids) == sorted(p[0] for p in players)
