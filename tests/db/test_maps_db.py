"""Tests for db.maps_db — global map pool CRUD."""

from unittest.mock import patch

import pytest


def _patch_conn(module_path, db_file):
    from db.connection_db import get_conn as _get_conn
    return patch(module_path, lambda: _get_conn(db_file))


class TestAddMap:

    def test_add_map_and_list(self, db_conn, db_file):
        from db.maps_db import add_map, get_maps

        # clear default maps seeded by init_db
        db_conn.execute("DELETE FROM maps")
        db_conn.commit()

        with _patch_conn("db.maps_db.get_conn", db_file):
            add_map("de_test_map")
            maps = get_maps()

        assert "de_test_map" in maps

    def test_add_duplicate_map_ignored(self, db_conn, db_file):
        from db.maps_db import add_map, get_maps

        db_conn.execute("DELETE FROM maps")
        db_conn.commit()

        with _patch_conn("db.maps_db.get_conn", db_file):
            add_map("de_dup")
            add_map("de_dup")
            maps = get_maps()

        assert maps.count("de_dup") == 1

    def test_add_map_strips_whitespace(self, db_conn, db_file):
        from db.maps_db import add_map

        db_conn.execute("DELETE FROM maps")
        db_conn.commit()

        with _patch_conn("db.maps_db.get_conn", db_file):
            add_map("  de_spaces  ")

        row = db_conn.execute("SELECT name FROM maps").fetchone()
        assert row["name"] == "de_spaces"


class TestDeleteMap:

    def test_delete_map_removes_it(self, db_conn, db_file):
        from db.maps_db import add_map, delete_map, get_maps

        db_conn.execute("DELETE FROM maps")
        db_conn.commit()

        with _patch_conn("db.maps_db.get_conn", db_file):
            add_map("de_removeme")
            delete_map("de_removeme")
            maps = get_maps()

        assert "de_removeme" not in maps

    def test_delete_nonexistent_map_no_error(self, db_conn, db_file):
        from db.maps_db import delete_map

        with _patch_conn("db.maps_db.get_conn", db_file):
            delete_map("de_ghost")  # should not raise


class TestMapExists:

    def test_map_exists_true(self, db_conn, db_file):
        from db.maps_db import add_map, map_exists

        db_conn.execute("DELETE FROM maps")
        db_conn.commit()

        with _patch_conn("db.maps_db.get_conn", db_file):
            add_map("de_found")
            assert map_exists("de_found") is True

    def test_map_exists_false(self, db_conn, db_file):
        from db.maps_db import map_exists

        db_conn.execute("DELETE FROM maps")
        db_conn.commit()

        with _patch_conn("db.maps_db.get_conn", db_file):
            assert map_exists("de_missing") is False


class TestGetMaps:

    def test_get_maps_returns_sorted(self, db_conn, db_file):
        from db.maps_db import add_map, get_maps

        db_conn.execute("DELETE FROM maps")
        db_conn.commit()

        with _patch_conn("db.maps_db.get_conn", db_file):
            add_map("de_zzz")
            add_map("de_aaa")
            add_map("de_mmm")
            maps = get_maps()

        assert maps == sorted(maps)

    def test_get_maps_empty_db(self, db_conn, db_file):
        from db.maps_db import get_maps

        db_conn.execute("DELETE FROM maps")
        db_conn.commit()

        with _patch_conn("db.maps_db.get_conn", db_file):
            assert get_maps() == []


class TestImportMapsFromMatchHistory:

    def test_imports_new_maps(self, db_conn, db_file, seed_match):
        from db.maps_db import get_maps, import_maps_from_match_history

        db_conn.execute("DELETE FROM maps")
        db_conn.commit()

        seed_match(
            match_kwargs={"match_id": "100"},
            map_kwargs={"map_number": 0, "map_name": "de_imported"},
        )

        imported = import_maps_from_match_history(conn=db_conn)
        db_conn.commit()

        assert imported == 1

        with _patch_conn("db.maps_db.get_conn", db_file):
            maps = get_maps()

        assert "de_imported" in maps

    def test_does_not_duplicate_existing_maps(self, db_conn, db_file, seed_match):
        from db.maps_db import add_map, import_maps_from_match_history

        db_conn.execute("DELETE FROM maps")
        db_conn.commit()

        with _patch_conn("db.maps_db.get_conn", db_file):
            add_map("de_already")

        seed_match(
            match_kwargs={"match_id": "101"},
            map_kwargs={"map_number": 0, "map_name": "de_already"},
        )

        imported = import_maps_from_match_history(conn=db_conn)
        assert imported == 0
