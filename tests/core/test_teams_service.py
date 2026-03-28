"""Tests for core.teams.service.balance_teams and core.teams.balancer.find_best_teams."""

import pytest
from unittest.mock import patch

from core.teams.balancer import find_best_teams, team_sum, distribution_score, normalize_teams
from core.teams.service import balance_teams


# ---------------------------------------------------------------------------
# Helper: build a player tuple  (id, name, rating)
# ---------------------------------------------------------------------------

def _p(pid, rating, name=None):
    return (str(pid), name or f"Player{pid}", rating)


# ===================================================================
# balancer.py — pure functions
# ===================================================================

class TestTeamSum:
    def test_basic(self):
        assert team_sum([_p(1, 100), _p(2, 200)]) == 300

    def test_empty(self):
        assert team_sum([]) == 0

    def test_single(self):
        assert team_sum([_p(1, 42)]) == 42


class TestDistributionScore:
    def test_identical_ratings(self):
        a = [_p(1, 100), _p(2, 100)]
        b = [_p(3, 100), _p(4, 100)]
        assert distribution_score(a, b) == 0

    def test_known_diff(self):
        a = [_p(1, 100), _p(2, 50)]
        b = [_p(3, 80), _p(4, 70)]
        # sorted desc a=[100,50] b=[80,70] → |100-80|+|50-70| = 20+20 = 40
        assert distribution_score(a, b) == 40


class TestNormalizeTeams:
    def test_order_independent(self):
        a = [_p(1, 100), _p(2, 200)]
        b = [_p(3, 300), _p(4, 400)]
        assert normalize_teams(a, b) == normalize_teams(b, a)


# ===================================================================
# balancer.find_best_teams
# ===================================================================

class TestFindBestTeams:
    def test_four_players_structure(self):
        players = [_p(i, 100 * i) for i in range(1, 5)]
        best_score, candidates, acceptable = find_best_teams(players, tolerance=0.0, dist_weight=0.25)

        assert isinstance(best_score, (int, float))
        assert len(candidates) > 0
        assert len(acceptable) > 0

        for entry in acceptable:
            score, team_a, team_b, diff, dist = entry
            assert len(team_a) == 2
            assert len(team_b) == 2
            assert score <= best_score + 0.0

    def test_two_players(self):
        players = [_p(1, 100), _p(2, 200)]
        best_score, candidates, acceptable = find_best_teams(players, tolerance=0.0, dist_weight=0.25)
        assert len(candidates) == 1
        score, team_a, team_b, diff, dist = candidates[0]
        assert len(team_a) == 1
        assert len(team_b) == 1

    def test_ten_players(self):
        players = [_p(i, 100 * i) for i in range(1, 11)]
        best_score, candidates, acceptable = find_best_teams(players, tolerance=5.0, dist_weight=0.25)

        for entry in acceptable:
            score, team_a, team_b, diff, dist = entry
            assert len(team_a) == 5
            assert len(team_b) == 5

    def test_identical_ratings(self):
        players = [_p(i, 100) for i in range(1, 7)]
        best_score, candidates, acceptable = find_best_teams(players, tolerance=0.0, dist_weight=0.25)
        # All splits have diff=0: best_score should be 0
        assert best_score == 0.0

    def test_score_computation(self):
        """Verify score = diff + dist * dist_weight."""
        players = [_p(1, 300), _p(2, 100), _p(3, 200), _p(4, 150)]
        _, candidates, _ = find_best_teams(players, tolerance=999, dist_weight=0.5)

        for score, team_a, team_b, diff, dist in candidates:
            expected = diff + dist * 0.5
            assert abs(score - expected) < 1e-9

    def test_tolerance_widens_acceptable(self):
        players = [_p(i, 100 * i) for i in range(1, 5)]
        _, _, tight = find_best_teams(players, tolerance=0.0, dist_weight=0.25)
        _, _, wide = find_best_teams(players, tolerance=9999, dist_weight=0.25)
        assert len(wide) >= len(tight)

    def test_no_duplicate_candidates(self):
        players = [_p(i, 100) for i in range(1, 5)]
        _, candidates, _ = find_best_teams(players, tolerance=0.0, dist_weight=0.25)
        keys = set()
        for _, ta, tb, _, _ in candidates:
            key = normalize_teams(ta, tb)
            assert key not in keys
            keys.add(key)


# ===================================================================
# service.balance_teams (integration with settings)
# ===================================================================

class TestBalanceTeams:
    """Tests for balance_teams which reads settings singleton."""

    @pytest.fixture(autouse=True)
    def _patch_settings(self):
        """Supply a mock settings object for every test in this class."""
        from core.settings.settings import Settings
        mock_settings = Settings()
        mock_settings.allow_uneven_teams = False
        mock_settings.dist_weight = 0.25
        with patch("core.teams.service.settings", mock_settings):
            self._settings = mock_settings
            yield

    def test_four_players_two_teams(self):
        players = [_p(i, 100 * i) for i in range(1, 5)]
        (team_a, team_b), diff = balance_teams(players, tolerance=5.0)
        assert len(team_a) == 2
        assert len(team_b) == 2
        assert isinstance(diff, (int, float))

    def test_ten_players_five_each(self):
        players = [_p(i, 100 * i) for i in range(1, 11)]
        (team_a, team_b), diff = balance_teams(players, tolerance=10.0)
        assert len(team_a) == 5
        assert len(team_b) == 5

    def test_identical_ratings_balanced(self):
        players = [_p(i, 100) for i in range(1, 9)]
        (team_a, team_b), diff = balance_teams(players, tolerance=0.0)
        assert diff == 0.0
        assert len(team_a) == 4
        assert len(team_b) == 4

    def test_uneven_count_raises_without_setting(self):
        players = [_p(i, 100) for i in range(1, 4)]  # 3 players
        with pytest.raises(ValueError, match="even"):
            balance_teams(players, tolerance=5.0)

    def test_uneven_count_allowed(self):
        self._settings.allow_uneven_teams = True
        players = [_p(i, 100) for i in range(1, 4)]  # 3 players
        (team_a, team_b), diff = balance_teams(players, tolerance=5.0)
        assert abs(len(team_a) - len(team_b)) <= 1

    def test_single_player_raises(self):
        with pytest.raises(ValueError, match="Not enough"):
            balance_teams([_p(1, 100)], tolerance=5.0)

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Not enough"):
            balance_teams([], tolerance=5.0)

    def test_very_different_ratings(self):
        # One player has much higher rating
        players = [_p(1, 10000), _p(2, 100), _p(3, 100), _p(4, 100)]
        (team_a, team_b), diff = balance_teams(players, tolerance=0.0)
        # The best balance should put the high-rating player alone in one team bucket
        sums = sorted([team_sum(team_a), team_sum(team_b)])
        # diff should be the absolute difference
        assert diff == abs(sums[1] - sums[0])

    def test_dist_weight_affects_result(self):
        """Changing dist_weight can change choice (stochastic — we just verify no crash)."""
        players = [_p(1, 300), _p(2, 100), _p(3, 200), _p(4, 50)]
        self._settings.dist_weight = 0.0
        (ta1, tb1), _ = balance_teams(players, tolerance=5.0)
        self._settings.dist_weight = 10.0
        (ta2, tb2), _ = balance_teams(players, tolerance=5.0)
        # Just verify both return valid teams
        assert len(ta1) == 2 and len(tb1) == 2
        assert len(ta2) == 2 and len(tb2) == 2

    def test_all_players_accounted_for(self):
        players = [_p(i, 100 * i) for i in range(1, 9)]
        (team_a, team_b), _ = balance_teams(players, tolerance=10.0)
        all_ids = {p[0] for p in team_a} | {p[0] for p in team_b}
        expected_ids = {str(i) for i in range(1, 9)}
        assert all_ids == expected_ids
