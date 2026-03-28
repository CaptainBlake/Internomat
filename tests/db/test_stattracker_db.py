"""Tests for db.stattracker_db — player dashboard, weapon stats, filter options."""

from unittest.mock import patch

import pytest

from tests.db.conftest import _make_match, _make_match_map, _make_player_stats


def _patch_conn(module_path, db_file):
    from db.connection_db import get_conn as _get_conn
    return patch(module_path, lambda: _get_conn(db_file))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _insert_weapon_stat(conn, steamid64, match_id, map_number, weapon,
                        shots_fired=100, shots_hit=50, kills=5,
                        headshot_kills=2, damage=500, rounds_with_weapon=10):
    """Insert a row into player_map_weapon_stats via raw SQL for test seeding."""
    conn.execute(
        """
        INSERT OR REPLACE INTO player_map_weapon_stats
            (steamid64, match_id, map_number, weapon,
             shots_fired, shots_hit, kills, headshot_kills, damage, rounds_with_weapon,
             first_seen_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        """,
        (steamid64, match_id, map_number, weapon,
         shots_fired, shots_hit, kills, headshot_kills, damage, rounds_with_weapon),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# fetch_player_filter_options
# ---------------------------------------------------------------------------

class TestFetchPlayerFilterOptions:

    def test_returns_distinct_players(self, db_conn, db_file, seed_match, seed_player_stats):
        from db.stattracker_db import fetch_player_filter_options

        seed_match(
            match_kwargs={"match_id": "100"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        seed_player_stats(steamid64="76561198000000001", match_id="100", map_number=0, name="Alice")
        seed_player_stats(steamid64="76561198000000002", match_id="100", map_number=0, name="Bob")

        with _patch_conn("db.stattracker_db.get_conn", db_file):
            rows = fetch_player_filter_options()

        steamids = {row["steamid64"] for row in rows}
        assert "76561198000000001" in steamids
        assert "76561198000000002" in steamids

    def test_empty_db(self, db_conn, db_file):
        from db.stattracker_db import fetch_player_filter_options

        with _patch_conn("db.stattracker_db.get_conn", db_file):
            rows = fetch_player_filter_options()

        assert rows == []


# ---------------------------------------------------------------------------
# fetch_player_overall_metrics
# ---------------------------------------------------------------------------

class TestFetchPlayerOverallMetrics:

    def test_single_map_metrics(self, db_conn, db_file, seed_match, seed_player_stats):
        from db.stattracker_db import fetch_player_overall_metrics

        seed_match(
            match_kwargs={"match_id": "200", "winner": "team_alpha"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2",
                        "winner": "team_alpha", "team1_score": 13, "team2_score": 7},
        )
        seed_player_stats(
            steamid64="76561198000000001", match_id="200", map_number=0,
            team="team_alpha", kills=20, deaths=10, assists=5, damage=2500,
            head_shot_kills=8,
        )

        with _patch_conn("db.stattracker_db.get_conn", db_file):
            row = fetch_player_overall_metrics("76561198000000001")

        assert row["maps_played"] == 1
        assert row["total_kills"] == 20
        assert row["total_deaths"] == 10
        assert row["total_assists"] == 5
        assert row["total_damage"] == 2500
        assert row["total_headshot_kills"] == 8
        assert row["map_wins"] == 1  # team matched winner

    def test_multi_map_aggregation(self, db_conn, db_file, seed_match, seed_player_stats):
        from db.stattracker_db import fetch_player_overall_metrics

        seed_match(
            match_kwargs={"match_id": "210"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2",
                        "winner": "team_alpha", "team1_score": 13, "team2_score": 7},
        )
        seed_player_stats(
            steamid64="76561198000000001", match_id="210", map_number=0,
            team="team_alpha", kills=15, deaths=8,
        )

        from db.matches_db import insert_match_map
        insert_match_map(
            _make_match_map(match_id="210", map_number=1, map_name="de_nuke",
                            winner="team_bravo", team1_score=7, team2_score=13),
            conn=db_conn,
        )
        db_conn.commit()
        seed_player_stats(
            steamid64="76561198000000001", match_id="210", map_number=1,
            team="team_alpha", kills=10, deaths=12,
        )

        with _patch_conn("db.stattracker_db.get_conn", db_file):
            row = fetch_player_overall_metrics("76561198000000001")

        assert row["maps_played"] == 2
        assert row["total_kills"] == 25
        assert row["map_wins"] == 1  # won dust2, lost nuke

    def test_nonexistent_player_returns_zeros(self, db_conn, db_file):
        from db.stattracker_db import fetch_player_overall_metrics

        with _patch_conn("db.stattracker_db.get_conn", db_file):
            row = fetch_player_overall_metrics("76561198099999999")

        assert row["maps_played"] == 0
        # SUM() returns None when no rows match
        assert row["total_kills"] is None or row["total_kills"] == 0


# ---------------------------------------------------------------------------
# fetch_player_weapon_stats  (alias JOIN)
# ---------------------------------------------------------------------------

class TestFetchPlayerWeaponStats:

    def test_canonical_aggregation_via_alias(self, db_conn, db_file):
        """Raw weapon 'm4a1' should resolve via weapon_alias to 'm4a1-s' canonical."""
        from db.stattracker_db import fetch_player_weapon_stats

        # Verify alias exists from init_db seed
        alias_row = db_conn.execute(
            "SELECT canonical_weapon FROM weapon_alias WHERE raw_weapon = 'm4a1'"
        ).fetchone()
        assert alias_row is not None, "Expected m4a1 alias to exist from seed"
        canonical = alias_row["canonical_weapon"]

        # Insert weapon stats using the RAW name (m4a1)
        _insert_weapon_stat(db_conn, "76561198000000001", "100", 0, "m4a1",
                            shots_fired=200, kills=10)
        # Also insert stats for the CANONICAL name directly
        _insert_weapon_stat(db_conn, "76561198000000001", "101", 0, canonical,
                            shots_fired=100, kills=5)

        with _patch_conn("db.stattracker_db.get_conn", db_file):
            rows = fetch_player_weapon_stats("76561198000000001", min_shots=1)

        # Should be aggregated under the canonical name
        weapon_map = {row["weapon"]: row for row in rows}
        assert canonical in weapon_map
        assert weapon_map[canonical]["shots_fired"] == 300
        assert weapon_map[canonical]["kills"] == 15

    def test_weapon_without_alias_passes_through(self, db_conn, db_file):
        from db.stattracker_db import fetch_player_weapon_stats

        _insert_weapon_stat(db_conn, "76561198000000001", "100", 0, "ak-47",
                            shots_fired=150, kills=8)

        with _patch_conn("db.stattracker_db.get_conn", db_file):
            rows = fetch_player_weapon_stats("76561198000000001", min_shots=1)

        weapon_names = [row["weapon"] for row in rows]
        assert "ak-47" in weapon_names

    def test_min_shots_filter(self, db_conn, db_file):
        from db.stattracker_db import fetch_player_weapon_stats

        _insert_weapon_stat(db_conn, "76561198000000001", "100", 0, "ak-47",
                            shots_fired=5, kills=1)

        with _patch_conn("db.stattracker_db.get_conn", db_file):
            rows = fetch_player_weapon_stats("76561198000000001", min_shots=10)

        assert len(rows) == 0

    def test_empty_db_returns_empty(self, db_conn, db_file):
        from db.stattracker_db import fetch_player_weapon_stats

        with _patch_conn("db.stattracker_db.get_conn", db_file):
            rows = fetch_player_weapon_stats("76561198099999999", min_shots=1)

        assert rows == []

    def test_category_filter(self, db_conn, db_file):
        from db.stattracker_db import fetch_player_weapon_stats

        # Insert weapon stats for ak-47 (should be in 'rifle' category from seed)
        _insert_weapon_stat(db_conn, "76561198000000001", "100", 0, "ak-47",
                            shots_fired=200, kills=10)
        # Insert for a different category weapon
        _insert_weapon_stat(db_conn, "76561198000000001", "100", 0, "glock-18",
                            shots_fired=100, kills=3)

        # Determine ak-47 category from seed
        cat_row = db_conn.execute(
            "SELECT category FROM weapon_dim WHERE weapon = 'ak-47'"
        ).fetchone()

        if cat_row:
            ak_category = cat_row["category"]
            with _patch_conn("db.stattracker_db.get_conn", db_file):
                rows = fetch_player_weapon_stats(
                    "76561198000000001", min_shots=1, weapon_category=ak_category
                )

            weapons = [r["weapon"] for r in rows]
            assert "ak-47" in weapons


# ---------------------------------------------------------------------------
# fetch_player_map_stats
# ---------------------------------------------------------------------------

class TestFetchPlayerMapStats:

    def test_map_breakdown(self, db_conn, db_file, seed_match, seed_player_stats):
        from db.stattracker_db import fetch_player_map_stats

        seed_match(
            match_kwargs={"match_id": "300"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2",
                        "winner": "team_alpha", "team1_score": 13, "team2_score": 7},
        )
        seed_player_stats(
            steamid64="76561198000000001", match_id="300", map_number=0,
            team="team_alpha", kills=20,
        )

        with _patch_conn("db.stattracker_db.get_conn", db_file):
            rows = fetch_player_map_stats("76561198000000001")

        assert len(rows) == 1
        assert rows[0]["map_name"] == "de_dust2"
        assert rows[0]["kills"] == 20
        assert rows[0]["map_wins"] == 1


# ---------------------------------------------------------------------------
# fetch_player_overview
# ---------------------------------------------------------------------------

class TestFetchPlayerOverview:

    def test_overview_counts(self, db_conn, db_file, seed_player, seed_match, seed_player_stats):
        from db.stattracker_db import fetch_player_overview

        seed_player(steam64_id="76561198000000001", name="Alice")
        seed_match(
            match_kwargs={"match_id": "400"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        seed_player_stats(
            steamid64="76561198000000001", match_id="400", map_number=0,
        )

        with _patch_conn("db.stattracker_db.get_conn", db_file):
            row = fetch_player_overview()

        assert row["tracked_players"] >= 1
        assert row["player_stat_rows"] >= 1


# ---------------------------------------------------------------------------
# upsert_player_map_weapon_stats_many
# ---------------------------------------------------------------------------

class TestUpsertWeaponStatsMany:

    def test_bulk_insert(self, db_conn):
        from db.stattracker_db import upsert_player_map_weapon_stats_many

        rows = [
            {
                "steamid64": "76561198000000001",
                "match_id": "500",
                "map_number": 0,
                "weapon": "ak-47",
                "shots_fired": 200,
                "shots_hit": 80,
                "kills": 10,
                "headshot_kills": 4,
                "damage": 1200,
                "rounds_with_weapon": 15,
                "first_seen_at": "2026-01-01",
                "updated_at": "2026-01-01",
            },
            {
                "steamid64": "76561198000000001",
                "match_id": "500",
                "map_number": 0,
                "weapon": "awp",
                "shots_fired": 50,
                "shots_hit": 30,
                "kills": 8,
                "headshot_kills": 6,
                "damage": 900,
                "rounds_with_weapon": 10,
                "first_seen_at": "2026-01-01",
                "updated_at": "2026-01-01",
            },
        ]

        upsert_player_map_weapon_stats_many(rows, conn=db_conn)
        db_conn.commit()

        count = db_conn.execute(
            "SELECT COUNT(*) AS c FROM player_map_weapon_stats WHERE steamid64 = ?",
            ("76561198000000001",),
        ).fetchone()["c"]
        assert count == 2

    def test_bulk_insert_empty_list(self, db_conn):
        from db.stattracker_db import upsert_player_map_weapon_stats_many

        # Should not raise
        upsert_player_map_weapon_stats_many([], conn=db_conn)

    def test_bulk_insert_discovers_weapons_in_weapon_dim(self, db_conn):
        from db.stattracker_db import upsert_player_map_weapon_stats_many

        rows = [
            {
                "steamid64": "76561198000000001",
                "match_id": "600",
                "map_number": 0,
                "weapon": "new_exotic_gun",
                "shots_fired": 10,
                "shots_hit": 5,
                "kills": 1,
                "headshot_kills": 0,
                "damage": 100,
                "rounds_with_weapon": 2,
                "first_seen_at": "2026-01-01",
                "updated_at": "2026-01-01",
            },
        ]

        upsert_player_map_weapon_stats_many(rows, conn=db_conn)
        db_conn.commit()

        # The weapon should now exist in weapon_dim with source='observed'
        dim_row = db_conn.execute(
            "SELECT source FROM weapon_dim WHERE weapon = 'new_exotic_gun'"
        ).fetchone()
        assert dim_row is not None
        assert dim_row["source"] == "observed"
