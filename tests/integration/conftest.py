"""Integration-layer test fixtures.

Provides a fully-seeded test DB with realistic data spanning all key tables:
players, matches, match_maps, match_player_stats, player_map_weapon_stats,
and settings.  The ``monkeypatch_db`` fixture is **autouse** for the entire
``tests/integration/`` directory so every ``get_conn()`` call reaches the
temporary database.
"""

import pytest

from db.connection_db import get_conn
from db.matches_db import insert_match, insert_match_map, insert_match_player_stats
from db.players_db import insert_player
from db.settings_db import set as settings_set
from db.stattracker_db import upsert_player_map_weapon_stats_many


# ---------------------------------------------------------------------------
# Base DB plumbing
# ---------------------------------------------------------------------------

@pytest.fixture
def db_conn(tmp_db):
    """Function-scoped SQLite connection with full Internomat schema."""
    return tmp_db


@pytest.fixture
def db_file(db_conn):
    """Return the file-system path of the test database."""
    row = db_conn.execute("PRAGMA database_list").fetchone()
    return row[2]


@pytest.fixture(autouse=True)
def monkeypatch_db(monkeypatch, db_file):
    """Redirect every ``get_conn()`` call (no-arg) to the temp test DB.

    Autouse for the entire integration directory so cross-layer tests
    that import DB modules hit the temporary database instead of prod.
    """
    monkeypatch.setattr("db.connection_db.DB_FILE", db_file)


# ---------------------------------------------------------------------------
# Seed data definitions
# ---------------------------------------------------------------------------

PLAYERS = [
    ("76561198000000001", "Alice",   16000, 1.10, 42, 0.58),
    ("76561198000000002", "Bob",     14000, 1.00, 35, 0.51),
    ("76561198000000003", "Charlie", 12000, 0.90, 28, 0.46),
    ("76561198000000004", "Diana",   18000, 1.20, 50, 0.62),
    ("76561198000000005", "Eve",     10000, 0.80, 20, 0.40),
    ("76561198000000006", "Frank",   15000, 1.05, 38, 0.55),
    ("76561198000000007", "Grace",   13000, 0.95, 30, 0.50),
    ("76561198000000008", "Hank",    11000, 0.85, 22, 0.44),
]

MATCHES = [
    {
        "match": {
            "match_id": "200",
            "start_time": "2026-02-10T20:00:00",
            "end_time": "2026-02-10T21:00:00",
            "winner": "team_alpha",
            "series_type": "bo1",
            "team1_name": "team_alpha",
            "team1_score": 13,
            "team2_name": "team_bravo",
            "team2_score": 9,
            "server_ip": "10.0.0.1",
        },
        "map": {
            "match_id": "200",
            "map_number": 0,
            "map_name": "de_dust2",
            "start_time": "2026-02-10T20:00:00",
            "end_time": "2026-02-10T21:00:00",
            "winner": "team_alpha",
            "team1_score": 13,
            "team2_score": 9,
        },
    },
    {
        "match": {
            "match_id": "201",
            "start_time": "2026-02-17T20:00:00",
            "end_time": "2026-02-17T21:30:00",
            "winner": "team_bravo",
            "series_type": "bo1",
            "team1_name": "team_alpha",
            "team1_score": 10,
            "team2_name": "team_bravo",
            "team2_score": 13,
            "server_ip": "10.0.0.1",
        },
        "map": {
            "match_id": "201",
            "map_number": 0,
            "map_name": "de_inferno",
            "start_time": "2026-02-17T20:00:00",
            "end_time": "2026-02-17T21:30:00",
            "winner": "team_bravo",
            "team1_score": 10,
            "team2_score": 13,
        },
    },
    {
        "match": {
            "match_id": "202",
            "start_time": "2026-02-24T19:30:00",
            "end_time": "2026-02-24T21:00:00",
            "winner": "team_alpha",
            "series_type": "bo1",
            "team1_name": "team_alpha",
            "team1_score": 13,
            "team2_name": "team_bravo",
            "team2_score": 11,
            "server_ip": "10.0.0.1",
        },
        "map": {
            "match_id": "202",
            "map_number": 0,
            "map_name": "de_mirage",
            "start_time": "2026-02-24T19:30:00",
            "end_time": "2026-02-24T21:00:00",
            "winner": "team_alpha",
            "team1_score": 13,
            "team2_score": 11,
        },
    },
]


def _make_player_stats(steamid64, name, team, match_id, map_number, kills, deaths, assists, damage, hs_kills):
    return {
        "steamid64": steamid64,
        "match_id": match_id,
        "map_number": map_number,
        "name": name,
        "team": team,
        "kills": kills,
        "deaths": deaths,
        "assists": assists,
        "damage": damage,
        "enemy5ks": 0,
        "enemy4ks": 0,
        "enemy3ks": 0,
        "enemy2ks": 1,
        "utility_count": 5,
        "utility_damage": 100,
        "utility_successes": 3,
        "utility_enemies": 2,
        "flash_count": 4,
        "flash_successes": 2,
        "health_points_removed_total": 2000,
        "health_points_dealt_total": damage,
        "shots_fired_total": 300,
        "shots_on_target_total": 120,
        "v1_count": 2,
        "v1_wins": 1,
        "v2_count": 1,
        "v2_wins": 0,
        "entry_count": 4,
        "entry_wins": 2,
        "equipment_value": 30000,
        "money_saved": 5000,
        "kill_reward": 6000,
        "live_time": 12000,
        "head_shot_kills": hs_kills,
        "cash_earned": 40000,
        "enemies_flashed": 8,
        "kast": 72.5,
        "impact": 1.1,
        "rating": 1.05,
    }


# Match 200  — 6 players
# Match 201  — 6 players
# Match 202  — 8 players
PLAYER_STATS = [
    # Match 200 (de_dust2)
    _make_player_stats("76561198000000001", "Alice",   "team_alpha", "200", 0, 25, 12, 5, 3200, 10),
    _make_player_stats("76561198000000002", "Bob",     "team_alpha", "200", 0, 18, 15, 7, 2400, 6),
    _make_player_stats("76561198000000003", "Charlie", "team_alpha", "200", 0, 14, 20, 3, 1800, 4),
    _make_player_stats("76561198000000004", "Diana",   "team_bravo", "200", 0, 10, 18, 4, 1500, 3),
    _make_player_stats("76561198000000005", "Eve",     "team_bravo", "200", 0, 12, 16, 6, 1600, 5),
    _make_player_stats("76561198000000006", "Frank",   "team_bravo", "200", 0, 16, 13, 5, 2000, 7),
    # Match 201 (de_inferno)
    _make_player_stats("76561198000000001", "Alice",   "team_alpha", "201", 0, 15, 18, 6, 2200, 5),
    _make_player_stats("76561198000000002", "Bob",     "team_alpha", "201", 0, 12, 16, 4, 1900, 4),
    _make_player_stats("76561198000000003", "Charlie", "team_alpha", "201", 0, 10, 14, 2, 1400, 3),
    _make_player_stats("76561198000000004", "Diana",   "team_bravo", "201", 0, 22, 10, 8, 3000, 9),
    _make_player_stats("76561198000000005", "Eve",     "team_bravo", "201", 0, 18, 12, 5, 2500, 6),
    _make_player_stats("76561198000000006", "Frank",   "team_bravo", "201", 0, 20, 14, 5, 2800, 7),
    # Match 202 (de_mirage) — all 8 players
    _make_player_stats("76561198000000001", "Alice",   "team_alpha", "202", 0, 20, 14, 4, 2800, 8),
    _make_player_stats("76561198000000002", "Bob",     "team_alpha", "202", 0, 16, 13, 6, 2100, 5),
    _make_player_stats("76561198000000003", "Charlie", "team_alpha", "202", 0, 13, 15, 3, 1700, 4),
    _make_player_stats("76561198000000004", "Diana",   "team_bravo", "202", 0, 13, 15, 5, 1900, 4),
    _make_player_stats("76561198000000005", "Eve",     "team_alpha", "202", 0,  9, 19, 2, 1200, 2),
    _make_player_stats("76561198000000006", "Frank",   "team_bravo", "202", 0, 17, 12, 7, 2500, 6),
    _make_player_stats("76561198000000007", "Grace",   "team_bravo", "202", 0, 11, 17, 3, 1500, 3),
    _make_player_stats("76561198000000008", "Hank",    "team_bravo", "202", 0, 14, 16, 4, 1800, 5),
]

WEAPON_STATS = [
    # Alice — match 200
    {"steamid64": "76561198000000001", "match_id": "200", "map_number": 0,
     "weapon": "ak-47", "shots_fired": 200, "shots_hit": 80, "kills": 15,
     "headshot_kills": 6, "damage": 2000, "rounds_with_weapon": 10,
     "first_seen_at": "2026-02-10T20:00:00", "updated_at": "2026-02-10T21:00:00"},
    {"steamid64": "76561198000000001", "match_id": "200", "map_number": 0,
     "weapon": "usp-s", "shots_fired": 50, "shots_hit": 25, "kills": 5,
     "headshot_kills": 3, "damage": 600, "rounds_with_weapon": 8,
     "first_seen_at": "2026-02-10T20:00:00", "updated_at": "2026-02-10T21:00:00"},
    # Bob — match 200
    {"steamid64": "76561198000000002", "match_id": "200", "map_number": 0,
     "weapon": "m4a4", "shots_fired": 250, "shots_hit": 90, "kills": 12,
     "headshot_kills": 4, "damage": 1800, "rounds_with_weapon": 11,
     "first_seen_at": "2026-02-10T20:00:00", "updated_at": "2026-02-10T21:00:00"},
    # Alice — match 201
    {"steamid64": "76561198000000001", "match_id": "201", "map_number": 0,
     "weapon": "ak-47", "shots_fired": 180, "shots_hit": 60, "kills": 10,
     "headshot_kills": 3, "damage": 1500, "rounds_with_weapon": 12,
     "first_seen_at": "2026-02-17T20:00:00", "updated_at": "2026-02-17T21:00:00"},
    # Diana — match 202
    {"steamid64": "76561198000000004", "match_id": "202", "map_number": 0,
     "weapon": "awp", "shots_fired": 60, "shots_hit": 30, "kills": 8,
     "headshot_kills": 2, "damage": 1200, "rounds_with_weapon": 9,
     "first_seen_at": "2026-02-24T19:30:00", "updated_at": "2026-02-24T21:00:00"},
]

SETTINGS_SEED = {
    "update_cooldown_minutes": "10",
    "max_demos_per_update": "5",
    "log_level": "DEBUG",
    "dist_weight": "0.3",
    "default_rating": "12000",
    "allow_uneven_teams": "True",
    "maproulette_use_history": "True",
    "matchzy_host": "192.168.1.100",
    "matchzy_port": "3307",
    "matchzy_user": "test_user",
    "matchzy_password": "test_pass",
    "matchzy_database": "matchzy_test",
    "auto_import_match_players": "False",
    "demo_ftp_host": "ftp.example.com",
    "demo_ftp_port": "2121",
    "demo_ftp_user": "ftp_user",
    "demo_ftp_password": "ftp_pass",
    "demo_remote_path": "/demos/cs2",
}


# ---------------------------------------------------------------------------
# Seeding fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def full_db(db_conn, db_file):
    """Seed the test DB with players, matches, maps, stats, weapon stats, and settings.

    Returns ``(db_conn, db_file)`` for callers that need both.
    """
    # Players
    for steam64, name, rating, leetify, matches, winrate in PLAYERS:
        insert_player(
            {
                "steam64_id": steam64,
                "name": name,
                "premier_rating": rating,
                "leetify_rating": leetify,
                "total_matches": matches,
                "winrate": winrate,
                "leetify_id": None,
            },
            conn=db_conn,
        )

    # Matches + maps
    for entry in MATCHES:
        insert_match(entry["match"], conn=db_conn)
        insert_match_map(entry["map"], conn=db_conn)

    # Player stats
    for ps in PLAYER_STATS:
        insert_match_player_stats(ps, conn=db_conn)

    # Weapon stats
    upsert_player_map_weapon_stats_many(WEAPON_STATS, conn=db_conn)

    # Settings
    for key, value in SETTINGS_SEED.items():
        db_conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value),
        )

    db_conn.commit()
    return db_conn, db_file
