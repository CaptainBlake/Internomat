"""Integration: Settings model ↔ settings_db ↔ SQLite round-trip."""

from core.settings.settings import Settings
from tests.integration.conftest import SETTINGS_SEED


# ---------------------------------------------------------------------------
# Load from seeded DB
# ---------------------------------------------------------------------------

def test_load_matches_seeds(full_db):
    """Settings.load() should populate fields from the seeded DB rows."""
    s = Settings()
    s.load()

    assert s.update_cooldown_minutes == int(SETTINGS_SEED["update_cooldown_minutes"])
    assert s.max_demos_per_update == int(SETTINGS_SEED["max_demos_per_update"])
    assert s.log_level == SETTINGS_SEED["log_level"]
    assert s.dist_weight == float(SETTINGS_SEED["dist_weight"])
    assert s.default_rating == int(SETTINGS_SEED["default_rating"])
    assert s.allow_uneven_teams is True
    assert s.maproulette_use_history is True
    # Matchzy
    assert s.matchzy_host == SETTINGS_SEED["matchzy_host"]
    assert s.matchzy_port == int(SETTINGS_SEED["matchzy_port"])
    assert s.matchzy_user == SETTINGS_SEED["matchzy_user"]
    assert s.matchzy_password == SETTINGS_SEED["matchzy_password"]
    assert s.matchzy_database == SETTINGS_SEED["matchzy_database"]
    assert s.auto_import_players_from_history is False
    assert s.auto_import_maps_from_history is False
    # FTP
    assert s.demo_ftp_host == SETTINGS_SEED["demo_ftp_host"]
    assert s.demo_ftp_port == int(SETTINGS_SEED["demo_ftp_port"])
    assert s.demo_ftp_user == SETTINGS_SEED["demo_ftp_user"]
    assert s.demo_ftp_password == SETTINGS_SEED["demo_ftp_password"]
    assert s.demo_remote_path == SETTINGS_SEED["demo_remote_path"]


# ---------------------------------------------------------------------------
# Modify → save → reload
# ---------------------------------------------------------------------------

def test_save_then_reload(full_db):
    """After modifying and saving, a fresh load should reflect the changes."""
    s1 = Settings()
    s1.load()

    # Mutate several fields
    s1.update_cooldown_minutes = 99
    s1.log_level = "WARNING"
    s1.allow_uneven_teams = False
    s1.matchzy_host = "newhost.local"
    s1.demo_ftp_port = 9999
    s1.save()

    # Fresh instance, fresh load
    s2 = Settings()
    s2.load()

    assert s2.update_cooldown_minutes == 99
    assert s2.log_level == "WARNING"
    assert s2.allow_uneven_teams is False
    assert s2.matchzy_host == "newhost.local"
    assert s2.demo_ftp_port == 9999
    # Unchanged fields stay intact
    assert s2.default_rating == int(SETTINGS_SEED["default_rating"])


# ---------------------------------------------------------------------------
# Multiple save/load cycles
# ---------------------------------------------------------------------------

def test_multiple_save_load_cycles(full_db):
    """Repeated save→load cycles should remain consistent."""
    s = Settings()
    s.load()

    for i in range(5):
        s.max_demos_per_update = 100 + i
        s.dist_weight = 0.1 * (i + 1)
        s.save()

        s2 = Settings()
        s2.load()
        assert s2.max_demos_per_update == 100 + i
        assert abs(s2.dist_weight - 0.1 * (i + 1)) < 1e-9


# ---------------------------------------------------------------------------
# Defaults when key is absent
# ---------------------------------------------------------------------------

def test_defaults_for_absent_keys(db_conn, db_file):
    """When the DB has no settings rows, load() should use defaults."""
    # db_conn has schema but no settings rows (full_db fixture NOT used)
    s = Settings()
    s.load()

    assert s.update_cooldown_minutes == 10
    assert s.log_level == "INFO"
    assert s.dist_weight == 0.25
    assert s.default_rating == 10000
    assert s.allow_uneven_teams is False
    assert s.maproulette_use_history is True
    assert s.matchzy_host == ""
    assert s.matchzy_port == 3306
    assert s.demo_ftp_host == ""
    assert s.demo_ftp_port == 21
    assert s.demo_remote_path == "/cs2/game/csgo/MatchZy"


# ---------------------------------------------------------------------------
# Save from default → load  (empty DB)
# ---------------------------------------------------------------------------

def test_save_defaults_then_load(db_conn, db_file):
    """Saving a default Settings object and reloading should round-trip."""
    s = Settings()
    s.save()

    s2 = Settings()
    s2.update_cooldown_minutes = 999  # dirty the instance
    s2.load()

    assert s2.update_cooldown_minutes == 10
    assert s2.log_level == "INFO"
    assert s2.allow_uneven_teams is False


# ---------------------------------------------------------------------------
# Partial seeds — only some keys present
# ---------------------------------------------------------------------------

def test_partial_settings_seed(db_conn, db_file):
    """When only some keys are in the DB, missing keys use defaults."""
    db_conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        ("log_level", "ERROR"),
    )
    db_conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
        ("default_rating", "8000"),
    )
    db_conn.commit()

    s = Settings()
    s.load()

    assert s.log_level == "ERROR"
    assert s.default_rating == 8000
    # Rest should be default
    assert s.update_cooldown_minutes == 10
    assert s.matchzy_host == ""
