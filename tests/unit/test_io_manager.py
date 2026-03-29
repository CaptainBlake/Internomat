"""Tests for services.IO_manager — JSON, CFG, filesystem helpers."""

import json
import pytest
from services.IO_manager import IOManager


# -- read_json / write_json round-trip --

def test_json_round_trip(tmp_path):
    filepath = str(tmp_path / "data.json")
    data = {"key": "value", "nested": {"a": 1, "b": [2, 3]}}
    IOManager.write_json(filepath, data)
    loaded = IOManager.read_json(filepath)
    assert loaded == data


def test_write_json_creates_parent_dirs(tmp_path):
    filepath = str(tmp_path / "sub" / "deep" / "data.json")
    IOManager.write_json(filepath, {"x": 1})
    assert IOManager.read_json(filepath) == {"x": 1}


def test_read_json_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        IOManager.read_json(str(tmp_path / "nonexistent.json"))


def test_write_json_overwrite(tmp_path):
    filepath = str(tmp_path / "data.json")
    IOManager.write_json(filepath, {"v": 1})
    IOManager.write_json(filepath, {"v": 2})
    assert IOManager.read_json(filepath) == {"v": 2}


# -- read_cfg --

def test_read_cfg_basic(tmp_path):
    cfg_file = tmp_path / "test.cfg"
    cfg_file.write_text("host=localhost\nport=8080\n", encoding="utf-8")
    result = IOManager.read_cfg(str(cfg_file))
    assert result == {"host": "localhost", "port": "8080"}


def test_read_cfg_skips_comments(tmp_path):
    cfg_file = tmp_path / "test.cfg"
    cfg_file.write_text("# comment\n; another\nkey=val\n", encoding="utf-8")
    result = IOManager.read_cfg(str(cfg_file))
    assert result == {"key": "val"}


def test_read_cfg_skips_blank_lines(tmp_path):
    cfg_file = tmp_path / "test.cfg"
    cfg_file.write_text("\n\nkey=val\n\n", encoding="utf-8")
    result = IOManager.read_cfg(str(cfg_file))
    assert result == {"key": "val"}


def test_read_cfg_value_with_equals(tmp_path):
    """Values containing '=' should be preserved (split on first '=' only)."""
    cfg_file = tmp_path / "test.cfg"
    cfg_file.write_text("url=http://host?a=1&b=2\n", encoding="utf-8")
    result = IOManager.read_cfg(str(cfg_file))
    assert result == {"url": "http://host?a=1&b=2"}


def test_read_cfg_strips_whitespace(tmp_path):
    cfg_file = tmp_path / "test.cfg"
    cfg_file.write_text("  key  =  value  \n", encoding="utf-8")
    result = IOManager.read_cfg(str(cfg_file))
    assert result == {"key": "value"}


def test_read_cfg_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        IOManager.read_cfg(str(tmp_path / "missing.cfg"))


def test_read_cfg_line_without_equals_skipped(tmp_path):
    cfg_file = tmp_path / "test.cfg"
    cfg_file.write_text("no_equals_here\nkey=val\n", encoding="utf-8")
    result = IOManager.read_cfg(str(cfg_file))
    assert result == {"key": "val"}


# -- ensure_dir --

def test_ensure_dir_creates_nested(tmp_path):
    target = str(tmp_path / "a" / "b" / "c")
    IOManager.ensure_dir(target)
    import os
    assert os.path.isdir(target)


def test_ensure_dir_idempotent(tmp_path):
    target = str(tmp_path / "existing")
    IOManager.ensure_dir(target)
    IOManager.ensure_dir(target)  # should not raise
    import os
    assert os.path.isdir(target)


# -- file_exists --

def test_file_exists_true(tmp_path):
    f = tmp_path / "exists.txt"
    f.write_text("hi")
    assert IOManager.file_exists(str(f)) is True


def test_file_exists_false(tmp_path):
    assert IOManager.file_exists(str(tmp_path / "nope.txt")) is False


# -- write_cfg / read_cfg round-trip --

def test_cfg_round_trip(tmp_path):
    filepath = str(tmp_path / "out.cfg")
    data = {"alpha": "one", "beta": "two"}
    IOManager.write_cfg(filepath, data)
    loaded = IOManager.read_cfg(filepath)
    assert loaded["alpha"] == "one"
    assert loaded["beta"] == "two"
