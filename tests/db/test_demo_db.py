"""Tests for db.demo_db — demo catalog, restore signatures, map resolution."""

from unittest.mock import patch

import pytest

from tests.db.conftest import _make_match, _make_match_map, _make_player_stats


# ---------------------------------------------------------------------------
# load_demo_match_catalog
# ---------------------------------------------------------------------------

class TestLoadDemoMatchCatalog:

    def test_catalog_with_seeded_data(self, db_conn, seed_match):
        from db.demo_db import load_demo_match_catalog

        seed_match(
            match_kwargs={"match_id": "100", "team1_name": "alpha", "team2_name": "bravo"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )

        catalog = load_demo_match_catalog(conn=db_conn)

        assert "100" in catalog
        assert catalog["100"]["maps_by_name"]["de_dust2"] == 0
        assert catalog["100"]["team1"] == "alpha"

    def test_catalog_empty_db(self, db_conn):
        from db.demo_db import load_demo_match_catalog

        catalog = load_demo_match_catalog(conn=db_conn)
        assert catalog == {}

    def test_catalog_multiple_maps(self, db_conn, seed_match):
        from db.demo_db import load_demo_match_catalog
        from db.matches_db import insert_match_map

        seed_match(
            match_kwargs={"match_id": "110"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        insert_match_map(
            _make_match_map(match_id="110", map_number=1, map_name="de_inferno"),
            conn=db_conn,
        )
        db_conn.commit()

        catalog = load_demo_match_catalog(conn=db_conn)

        assert len(catalog["110"]["maps_by_name"]) == 2


# ---------------------------------------------------------------------------
# resolve_map_number
# ---------------------------------------------------------------------------

class TestResolveMapNumber:

    def test_resolve_existing_map(self, db_conn, seed_match):
        from db.demo_db import load_demo_match_catalog, resolve_map_number

        seed_match(
            match_kwargs={"match_id": "200"},
            map_kwargs={"map_number": 0, "map_name": "de_nuke"},
        )

        catalog = load_demo_match_catalog(conn=db_conn)
        result = resolve_map_number(catalog, "200", "de_nuke")
        assert result == 0

    def test_resolve_missing_match(self):
        from db.demo_db import resolve_map_number

        result = resolve_map_number({}, "999", "de_nuke")
        assert result is None

    def test_resolve_missing_map_name(self, db_conn, seed_match):
        from db.demo_db import load_demo_match_catalog, resolve_map_number

        seed_match(
            match_kwargs={"match_id": "210"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )

        catalog = load_demo_match_catalog(conn=db_conn)
        result = resolve_map_number(catalog, "210", "de_nonexistent")
        assert result is None


# ---------------------------------------------------------------------------
# is_restore_signature_current / upsert_restore_signature
# ---------------------------------------------------------------------------

class TestRestoreSignature:

    def test_upsert_and_check_current(self, db_conn):
        from db.demo_db import is_restore_signature_current, upsert_restore_signature

        upsert_restore_signature(
            source_match_id="300",
            source_map_number=0,
            payload_sha256="abc123",
            conn=db_conn,
        )
        db_conn.commit()

        assert is_restore_signature_current("300", 0, "abc123", conn=db_conn) is True

    def test_signature_mismatch(self, db_conn):
        from db.demo_db import is_restore_signature_current, upsert_restore_signature

        upsert_restore_signature(
            source_match_id="310",
            source_map_number=0,
            payload_sha256="old_hash",
            conn=db_conn,
        )
        db_conn.commit()

        assert is_restore_signature_current("310", 0, "new_hash", conn=db_conn) is False

    def test_no_signature_exists(self, db_conn):
        from db.demo_db import is_restore_signature_current

        assert is_restore_signature_current("999", 0, "any_hash", conn=db_conn) is False

    def test_empty_hash_returns_false(self, db_conn):
        from db.demo_db import is_restore_signature_current

        assert is_restore_signature_current("999", 0, "", conn=db_conn) is False
        assert is_restore_signature_current("999", 0, None, conn=db_conn) is False

    def test_upsert_overwrites_signature(self, db_conn):
        from db.demo_db import is_restore_signature_current, upsert_restore_signature

        upsert_restore_signature("320", 0, "hash_v1", conn=db_conn)
        db_conn.commit()
        upsert_restore_signature("320", 0, "hash_v2", conn=db_conn)
        db_conn.commit()

        assert is_restore_signature_current("320", 0, "hash_v2", conn=db_conn) is True
        assert is_restore_signature_current("320", 0, "hash_v1", conn=db_conn) is False

    def test_upsert_with_canonical_fields(self, db_conn):
        from db.demo_db import upsert_restore_signature

        upsert_restore_signature(
            source_match_id="330",
            source_map_number=0,
            payload_sha256="hashC",
            canonical_match_id="330_canon",
            canonical_map_number=1,
            source_file="demo.dem",
            conn=db_conn,
        )
        db_conn.commit()

        row = db_conn.execute(
            "SELECT * FROM cache_restore_state WHERE source_match_id = ? AND source_map_number = ?",
            ("330", 0),
        ).fetchone()

        assert row["canonical_match_id"] == "330_canon"
        assert row["canonical_map_number"] == 1
        assert row["source_file"] == "demo.dem"


# ---------------------------------------------------------------------------
# get_expected_demo_players
# ---------------------------------------------------------------------------

class TestGetExpectedDemoPlayers:

    def test_returns_steamids(self, db_conn, seed_match, seed_player_stats):
        from db.demo_db import get_expected_demo_players

        seed_match(
            match_kwargs={"match_id": "400"},
            map_kwargs={"map_number": 0, "map_name": "de_dust2"},
        )
        seed_player_stats(steamid64="76561198000000001", match_id="400", map_number=0)
        seed_player_stats(steamid64="76561198000000002", match_id="400", map_number=0)

        result = get_expected_demo_players("400", 0, conn=db_conn)
        assert result == {"76561198000000001", "76561198000000002"}

    def test_empty_returns_empty_set(self, db_conn):
        from db.demo_db import get_expected_demo_players

        result = get_expected_demo_players("999", 0, conn=db_conn)
        assert result == set()


# ---------------------------------------------------------------------------
# resolve_equivalent_match_map
# ---------------------------------------------------------------------------

class TestResolveEquivalentMatchMap:

    def test_resolve_by_team_and_score(self, db_conn, seed_match, seed_player_stats):
        from db.demo_db import resolve_equivalent_match_map

        seed_match(
            match_kwargs={
                "match_id": "500",
                "team1_name": "alpha",
                "team2_name": "bravo",
                "team1_score": 13,
                "team2_score": 7,
                "start_time": "2026-01-01T20:00:00",
            },
            map_kwargs={
                "map_number": 0,
                "map_name": "de_dust2",
                "team1_score": 13,
                "team2_score": 7,
            },
        )

        result = resolve_equivalent_match_map(
            map_name="de_dust2",
            team1_name="alpha",
            team2_name="bravo",
            team1_score=13,
            team2_score=7,
            played_at="2026-01-01T20:05:00",
            conn=db_conn,
        )

        assert result is not None
        assert result["match_id"] == "500"
        assert result["map_number"] == 0

    def test_resolve_no_match_found(self, db_conn):
        from db.demo_db import resolve_equivalent_match_map

        result = resolve_equivalent_match_map(
            map_name="de_nonexistent",
            conn=db_conn,
        )

        assert result is None
