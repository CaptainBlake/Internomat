"""Tests for core.stats.leaderboard."""

import pytest

from core.stats.leaderboard import (
    get_top_kills,
    get_top_deaths,
    get_top_ratings,
    get_top_damage_per_match,
)


class TestGetTopKills:
    def test_ordering(self, seeded_db, monkeypatch_db):
        result = get_top_kills(limit=10)
        assert len(result) == 6  # 6 distinct players
        # Each entry is (name, steamid64, total_kills)
        kills = [r[2] for r in result]
        assert kills == sorted(kills, reverse=True)

    def test_top_player(self, seeded_db, monkeypatch_db):
        result = get_top_kills(limit=1)
        assert len(result) == 1
        name, steamid64, total_kills = result[0]
        # Alice has 25+15+20 = 60 kills (highest)
        assert steamid64 == "76561198000000001"
        assert total_kills == 60

    def test_limit_respected(self, seeded_db, monkeypatch_db):
        result = get_top_kills(limit=3)
        assert len(result) == 3

    def test_empty_db(self, db_conn, monkeypatch_db):
        result = get_top_kills(limit=10)
        assert result == []

    def test_tuple_structure(self, seeded_db, monkeypatch_db):
        result = get_top_kills(limit=1)
        name, steamid, value = result[0]
        assert isinstance(name, str)
        assert isinstance(steamid, str)
        assert isinstance(value, (int, float))


class TestGetTopDeaths:
    def test_ordering(self, seeded_db, monkeypatch_db):
        result = get_top_deaths(limit=10)
        deaths = [r[2] for r in result]
        assert deaths == sorted(deaths, reverse=True)

    def test_top_death_player(self, seeded_db, monkeypatch_db):
        result = get_top_deaths(limit=1)
        name, steamid64, total_deaths = result[0]
        # Charlie: 20+10+17=47, Diana: 18+14+15=47 — tied; order by name ASC
        assert total_deaths == 47

    def test_empty_db(self, db_conn, monkeypatch_db):
        result = get_top_deaths(limit=10)
        assert result == []


class TestGetTopRatings:
    def test_ordering(self, seeded_db, monkeypatch_db):
        result = get_top_ratings(limit=10)
        ratings = [r[2] for r in result]
        assert ratings == sorted(ratings, reverse=True)

    def test_top_rated_player(self, seeded_db, monkeypatch_db):
        result = get_top_ratings(limit=1)
        name, steamid, rating = result[0]
        # Diana has premier_rating=18000 (highest)
        assert steamid == "76561198000000004"
        assert rating == 18000

    def test_limit(self, seeded_db, monkeypatch_db):
        result = get_top_ratings(limit=2)
        assert len(result) == 2

    def test_empty_db(self, db_conn, monkeypatch_db):
        result = get_top_ratings(limit=10)
        assert result == []


class TestGetTopDamagePerMatch:
    def test_ordering(self, seeded_db, monkeypatch_db):
        result = get_top_damage_per_match(limit=10)
        damages = [r[2] for r in result]
        assert damages == sorted(damages, reverse=True)

    def test_non_empty(self, seeded_db, monkeypatch_db):
        result = get_top_damage_per_match(limit=10)
        assert len(result) > 0

    def test_empty_db(self, db_conn, monkeypatch_db):
        result = get_top_damage_per_match(limit=10)
        assert result == []
