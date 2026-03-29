"""Tests for services.demo_cache — parsed demo caching with real tmp directories."""

import json
import pickle

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_index(cache_dir, index_data):
    """Write an index.json into cache_dir."""
    index_file = cache_dir / "index.json"
    index_file.write_text(json.dumps(index_data), encoding="utf-8")


def _write_pickle(cache_dir, filename, data):
    """Write a pickle file into cache_dir."""
    path = cache_dir / filename
    with open(path, "wb") as f:
        pickle.dump(data, f)


# ---------------------------------------------------------------------------
# Tests: list_cached_demos
# ---------------------------------------------------------------------------

class TestListCachedDemos:

    def test_returns_entries_from_index(self, tmp_path):
        from services.demo_cache import list_cached_demos

        index_data = {
            "match_1_map_0": {
                "match_id": 1,
                "map_number": 0,
                "cache_key": "match_1_map_0",
                "filename": "match_1_map_0.pkl",
                "compression": "none",
                "updated_at": "2026-01-10T20:00:00",
            },
            "match_2_map_0": {
                "match_id": 2,
                "map_number": 0,
                "cache_key": "match_2_map_0",
                "filename": "match_2_map_0.pkl",
                "compression": "none",
                "updated_at": "2026-01-11T20:00:00",
            },
        }
        _write_index(tmp_path, index_data)

        rows = list_cached_demos(tmp_path)
        assert len(rows) == 2
        # Sorted by updated_at descending
        assert rows[0]["match_id"] == 2
        assert rows[1]["match_id"] == 1

    def test_empty_index_returns_empty(self, tmp_path):
        from services.demo_cache import list_cached_demos

        _write_index(tmp_path, {})
        rows = list_cached_demos(tmp_path)
        assert rows == []

    def test_missing_index_returns_empty(self, tmp_path):
        from services.demo_cache import list_cached_demos

        rows = list_cached_demos(tmp_path)
        assert rows == []


# ---------------------------------------------------------------------------
# Tests: save_parsed_demo / load_parsed_demo
# ---------------------------------------------------------------------------

class TestSaveAndLoadParsedDemo:

    def test_save_and_load_roundtrip(self, tmp_path):
        from services.demo_cache import save_parsed_demo, load_parsed_demo

        payload = {
            "header": {"map": "de_dust2", "ticks": 128000},
            "kills": [{"tick": 100, "attacker": "Alice"}],
        }

        save_parsed_demo(tmp_path, match_id=1, map_number=0, data=payload)
        result = load_parsed_demo(tmp_path, match_id=1, map_number=0)

        assert result == payload

    def test_save_updates_index(self, tmp_path):
        from services.demo_cache import save_parsed_demo, load_index

        save_parsed_demo(tmp_path, match_id=5, map_number=1, data={"header": {}})

        index = load_index(tmp_path)
        assert "match_5_map_1" in index
        entry = index["match_5_map_1"]
        assert entry["match_id"] == 5
        assert entry["map_number"] == 1

    def test_save_with_source_file(self, tmp_path):
        from services.demo_cache import save_parsed_demo, load_index

        save_parsed_demo(
            tmp_path,
            match_id=3,
            map_number=0,
            data={"header": {}},
            source_file="2026-01-10_match_3_map_0_de_dust2.dem",
        )

        index = load_index(tmp_path)
        entry = index["match_3_map_0"]
        assert entry["filename"] == "2026-01-10_match_3_map_0_de_dust2.pkl"

    def test_load_nonexistent_returns_none(self, tmp_path):
        from services.demo_cache import load_parsed_demo

        result = load_parsed_demo(tmp_path, match_id=999, map_number=0)
        assert result is None


# ---------------------------------------------------------------------------
# Tests: load_parsed_demo with pre-existing pickle
# ---------------------------------------------------------------------------

class TestLoadParsedDemo:

    def test_load_from_existing_pickle(self, tmp_path):
        from services.demo_cache import load_parsed_demo

        payload = {"header": {"map": "de_inferno"}, "rounds": []}
        _write_pickle(tmp_path, "match_10_map_0.pkl", payload)
        # No index needed — resolve_payload_path will find the file

        result = load_parsed_demo(tmp_path, match_id=10, map_number=0)
        assert result == payload

    def test_load_with_index_filename(self, tmp_path):
        from services.demo_cache import load_parsed_demo

        payload = {"header": {"map": "de_nuke"}}
        custom_name = "custom_demo_name.pkl"
        _write_pickle(tmp_path, custom_name, payload)
        _write_index(tmp_path, {
            "match_7_map_0": {
                "match_id": 7,
                "map_number": 0,
                "filename": custom_name,
            }
        })

        result = load_parsed_demo(tmp_path, match_id=7, map_number=0)
        assert result == payload


# ---------------------------------------------------------------------------
# Tests: list_existing_cached_demos
# ---------------------------------------------------------------------------

class TestListExistingCachedDemos:

    def test_filters_to_existing_files(self, tmp_path):
        from services.demo_cache import list_existing_cached_demos

        _write_index(tmp_path, {
            "match_1_map_0": {
                "match_id": 1,
                "map_number": 0,
                "filename": "match_1_map_0.pkl",
            },
            "match_2_map_0": {
                "match_id": 2,
                "map_number": 0,
                "filename": "match_2_map_0.pkl",
            },
        })
        # Only create one pickle file
        _write_pickle(tmp_path, "match_1_map_0.pkl", {"data": True})

        rows = list_existing_cached_demos(tmp_path)
        assert len(rows) == 1
        assert rows[0]["match_id"] == 1

    def test_empty_when_no_files_exist(self, tmp_path):
        from services.demo_cache import list_existing_cached_demos

        _write_index(tmp_path, {
            "match_1_map_0": {
                "match_id": 1,
                "map_number": 0,
                "filename": "match_1_map_0.pkl",
            },
        })

        rows = list_existing_cached_demos(tmp_path)
        assert len(rows) == 0


# ---------------------------------------------------------------------------
# Tests: get_cached_manifest
# ---------------------------------------------------------------------------

class TestGetCachedManifest:

    def test_returns_entry(self, tmp_path):
        from services.demo_cache import get_cached_manifest

        _write_index(tmp_path, {
            "match_1_map_0": {"match_id": 1, "map_number": 0, "filename": "f.pkl"},
        })

        entry = get_cached_manifest(tmp_path, match_id=1, map_number=0)
        assert entry is not None
        assert entry["match_id"] == 1

    def test_missing_key_returns_none(self, tmp_path):
        from services.demo_cache import get_cached_manifest

        _write_index(tmp_path, {})
        assert get_cached_manifest(tmp_path, match_id=99, map_number=0) is None


# ---------------------------------------------------------------------------
# Tests: clear_cache
# ---------------------------------------------------------------------------

class TestClearCache:

    def test_deletes_files_and_dirs(self, tmp_path):
        from services.demo_cache import clear_cache

        (tmp_path / "file1.pkl").write_bytes(b"data")
        sub = tmp_path / "subdir"
        sub.mkdir()
        (sub / "nested.pkl").write_bytes(b"data")

        deleted = clear_cache(tmp_path)
        assert deleted == 2  # file1.pkl + subdir
        assert list(tmp_path.iterdir()) == []

    def test_nonexistent_dir_returns_zero(self, tmp_path):
        from services.demo_cache import clear_cache

        result = clear_cache(tmp_path / "no_such_dir")
        assert result == 0


# ---------------------------------------------------------------------------
# Tests: _cache_key / _cache_filename
# ---------------------------------------------------------------------------

class TestCacheKeyAndFilename:

    def test_cache_key(self):
        from services.demo_cache import _cache_key
        assert _cache_key(1, 0) == "match_1_map_0"
        assert _cache_key(99, 2) == "match_99_map_2"

    def test_cache_filename_default(self):
        from services.demo_cache import _cache_filename
        assert _cache_filename(1, 0) == "match_1_map_0.pkl"

    def test_cache_filename_with_source(self):
        from services.demo_cache import _cache_filename
        result = _cache_filename(1, 0, source_file="2026-01-10_match.dem")
        assert result == "2026-01-10_match.pkl"


# ---------------------------------------------------------------------------
# Tests: compute_payload_sha256
# ---------------------------------------------------------------------------

class TestComputeSha256:

    def test_sha256_of_known_file(self, tmp_path):
        from services.demo_cache import compute_payload_sha256_from_path
        import hashlib

        data = b"hello world"
        path = tmp_path / "test.pkl"
        path.write_bytes(data)

        expected = hashlib.sha256(data).hexdigest()
        result = compute_payload_sha256_from_path(path)
        assert result == expected

    def test_sha256_missing_file_returns_none(self, tmp_path):
        from services.demo_cache import compute_payload_sha256_from_path

        result = compute_payload_sha256_from_path(tmp_path / "nope.pkl")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: payload_table_stats
# ---------------------------------------------------------------------------

class TestPayloadTableStats:

    def test_dict_payload(self):
        from services.demo_cache import payload_table_stats

        data = {
            "header": {"map": "de_dust2"},
            "kills": [1, 2, 3],
        }

        stats = payload_table_stats(data)
        assert stats["header"]["type"] == "dict"
        assert stats["header"]["keys"] == 1
        assert stats["kills"]["type"] == "list"
        assert stats["kills"]["items"] == 3

    def test_none_value(self):
        from services.demo_cache import payload_table_stats

        stats = payload_table_stats({"empty": None})
        assert stats["empty"]["type"] == "none"

    def test_non_dict_payload(self):
        from services.demo_cache import payload_table_stats

        assert payload_table_stats("not a dict") == {}
        assert payload_table_stats(None) == {}
