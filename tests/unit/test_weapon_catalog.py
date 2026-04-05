"""Tests for db.weapon_catalog — normalize, seed rows, alias rows."""

from db.weapon_catalog import (
    CS2_CANONICAL_WEAPONS,
    CS2_KNIFE_VARIANT_ALIASES,
    CS2_WEAPON_ALIASES,
    iter_seed_alias_rows,
    iter_seed_weapon_rows,
    normalize_weapon_name,
)


# -- normalize_weapon_name: alias resolution --

def test_normalize_m4a1():
    assert normalize_weapon_name("m4a1") == "m4a4"


def test_normalize_weapon_m4a1():
    assert normalize_weapon_name("weapon_m4a1") == "m4a4"


def test_normalize_tec9():
    assert normalize_weapon_name("tec9") == "tec-9"


def test_normalize_weapon_tec9():
    assert normalize_weapon_name("weapon_tec9") == "tec-9"


def test_normalize_bayonet():
    assert normalize_weapon_name("bayonet") == "knife"


def test_normalize_weapon_bayonet():
    assert normalize_weapon_name("weapon_bayonet") == "knife"


def test_normalize_deagle():
    assert normalize_weapon_name("deagle") == "desert-eagle"


def test_normalize_weapon_deagle():
    assert normalize_weapon_name("weapon_deagle") == "desert-eagle"


def test_normalize_glock():
    assert normalize_weapon_name("glock") == "glock-18"


# -- normalize_weapon_name: passthrough / unrecognized --
# The function returns None for tokens not found in any alias dict or knife list.

def test_normalize_awp_passthrough():
    """'awp' is already canonical — passes through unchanged."""
    assert normalize_weapon_name("awp") == "awp"


def test_normalize_unknown_weapon_passthrough():
    """Unrecognized tokens pass through with underscores replaced by hyphens."""
    assert normalize_weapon_name("unknown_weapon") == "unknown-weapon"


# -- normalize_weapon_name: empty / None --

def test_normalize_empty_string():
    assert normalize_weapon_name("") == ""


def test_normalize_none():
    assert normalize_weapon_name(None) == ""


def test_normalize_whitespace_only():
    assert normalize_weapon_name("   ") == ""


# -- normalize_weapon_name: case insensitivity --

def test_normalize_uppercase_m4a1():
    """Input is lowered internally, so 'M4A1' should resolve."""
    assert normalize_weapon_name("M4A1") == "m4a4"


# -- CS2_KNIFE_VARIANT_ALIASES all map to knife --

def test_knife_variants_all_normalize_to_knife():
    for variant in CS2_KNIFE_VARIANT_ALIASES:
        result = normalize_weapon_name(variant)
        assert result == "knife", f"{variant!r} → {result!r}, expected 'knife'"


def test_knife_prefix_pattern_normalizes_to_knife():
    """Any token whose base starts with 'knife_' maps to knife."""
    assert normalize_weapon_name("weapon_knife_unknown_future_skin") == "knife"


# -- iter_seed_weapon_rows --

def test_seed_weapon_rows_non_empty():
    rows = list(iter_seed_weapon_rows())
    assert len(rows) > 0


def test_seed_weapon_rows_match_canonical_count():
    rows = list(iter_seed_weapon_rows())
    assert len(rows) == len(CS2_CANONICAL_WEAPONS)


def test_seed_weapon_rows_tuple_shape():
    """Each row is (weapon, display_name, category, source)."""
    for row in iter_seed_weapon_rows():
        assert len(row) == 4
        weapon, display_name, category, source = row
        assert isinstance(weapon, str)
        assert isinstance(display_name, str)
        assert category in {"pistol", "smg", "heavy", "rifle", "melee", "utility"}
        assert source == "seed-cs2"


def test_seed_weapon_rows_weapons_are_canonical():
    weapons = {row[0] for row in iter_seed_weapon_rows()}
    assert weapons == set(CS2_CANONICAL_WEAPONS)


# -- iter_seed_alias_rows --

def test_seed_alias_rows_non_empty():
    rows = list(iter_seed_alias_rows())
    assert len(rows) > 0


def test_seed_alias_rows_tuple_shape():
    """Each row is (raw_weapon, canonical_weapon, source)."""
    for row in iter_seed_alias_rows():
        assert len(row) == 3
        raw, canonical, source = row
        assert isinstance(raw, str)
        assert isinstance(canonical, str)
        assert source == "seed-cs2"


def test_seed_alias_rows_canonical_values_valid():
    """Every canonical target in alias rows is a known canonical weapon."""
    canonical_set = set(CS2_CANONICAL_WEAPONS)
    for raw, canonical, _source in iter_seed_alias_rows():
        assert canonical in canonical_set, f"Alias {raw!r}→{canonical!r} targets unknown weapon"


def test_seed_alias_rows_include_knife_variants():
    """Knife variant aliases should appear in alias rows."""
    alias_raws = {row[0] for row in iter_seed_alias_rows()}
    for variant in CS2_KNIFE_VARIANT_ALIASES:
        assert variant in alias_raws, f"Knife variant {variant!r} missing from alias rows"


def test_seed_alias_rows_count():
    """Total alias rows = weapon aliases + knife variant aliases."""
    rows = list(iter_seed_alias_rows())
    expected = len(CS2_WEAPON_ALIASES) + len(CS2_KNIFE_VARIANT_ALIASES)
    assert len(rows) == expected
