"""Tests for db.settings_db — key/value settings store."""

from unittest.mock import patch

import pytest


def _patch_conn(module_path, db_file):
    """Patch get_conn in a module to return a fresh connection to db_file each call."""
    from db.connection_db import get_conn as _get_conn
    return patch(module_path, lambda: _get_conn(db_file))


class TestSettingsGetSet:
    """Test the get/set interface of settings_db."""

    def test_set_then_get_returns_value(self, db_conn, db_file):
        from db.settings_db import get, set as settings_set

        with _patch_conn("db.settings_db.get_conn", db_file):
            settings_set("theme", "dark")
            assert get("theme") == "dark"

    def test_get_missing_key_returns_none(self, db_conn, db_file):
        from db.settings_db import get

        with _patch_conn("db.settings_db.get_conn", db_file):
            assert get("nonexistent") is None

    def test_get_missing_key_returns_custom_default(self, db_conn, db_file):
        from db.settings_db import get

        with _patch_conn("db.settings_db.get_conn", db_file):
            assert get("nonexistent", default="fallback") == "fallback"

    def test_update_existing_key(self, db_conn, db_file):
        from db.settings_db import get, set as settings_set

        with _patch_conn("db.settings_db.get_conn", db_file):
            settings_set("lang", "en")
            assert get("lang") == "en"

            settings_set("lang", "de")
            assert get("lang") == "de"

    def test_multiple_keys_isolation(self, db_conn, db_file):
        from db.settings_db import get, set as settings_set

        with _patch_conn("db.settings_db.get_conn", db_file):
            settings_set("key_a", "alpha")
            settings_set("key_b", "bravo")

            assert get("key_a") == "alpha"
            assert get("key_b") == "bravo"

    def test_set_stores_value_as_string(self, db_conn, db_file):
        from db.settings_db import get, set as settings_set

        with _patch_conn("db.settings_db.get_conn", db_file):
            settings_set("port", 8080)
            result = get("port")
            assert result == "8080"
            assert isinstance(result, str)

    def test_set_empty_string_value(self, db_conn, db_file):
        from db.settings_db import get, set as settings_set

        with _patch_conn("db.settings_db.get_conn", db_file):
            settings_set("empty", "")
            assert get("empty") == ""

    def test_overwrite_with_different_type(self, db_conn, db_file):
        from db.settings_db import get, set as settings_set

        with _patch_conn("db.settings_db.get_conn", db_file):
            settings_set("val", "text")
            settings_set("val", 42)
            assert get("val") == "42"
