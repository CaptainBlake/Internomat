"""Core-layer test fixtures.

Provides a seeded test DB with realistic data (matches, maps, player stats,
weapon stats) and a monkeypatch that redirects ``db.connection_db.get_conn``
to the temporary test database.
"""

import pytest

from db.connection_db import get_conn
from db.matches_db import insert_match, insert_match_map, insert_match_player_stats
from db.players_db import insert_player
from db.prime_db import upsert_prime_rating
from db.stattracker_db import upsert_player_map_weapon_stats_many


# ---------------------------------------------------------------------------
# Base DB plumbing (reuses root tmp_db)
# ---------------------------------------------------------------------------

@pytest.fixture
def db_conn(tmp_db):
    """Function-scoped SQLite connection with full Internomat schema."""
    return tmp_db


@pytest.fixture
def db_file(db_conn):
    """Return the file path of the test database."""
    row = db_conn.execute("PRAGMA database_list").fetchone()
    return row[2]


@pytest.fixture
def monkeypatch_db(monkeypatch, db_file):
    """Redirect every ``get_conn()`` call (no-arg) to the temp test DB.

    Patching ``DB_FILE`` works because ``get_conn()`` reads it at call-time
    (``db_path = db_file or DB_FILE``).  This affects all modules that
    imported ``get_conn`` via ``from .connection_db import get_conn``.
    """
    monkeypatch.setattr("db.connection_db.DB_FILE", db_file)


# ---------------------------------------------------------------------------
# Player identities
# ---------------------------------------------------------------------------

PLAYERS = [
    ("76561198000000001", "Alice",   16000, 1.10),
    ("76561198000000002", "Bob",     14000, 1.00),
    ("76561198000000003", "Charlie", 12000, 0.90),
    ("76561198000000004", "Diana",   18000, 1.20),
    ("76561198000000005", "Eve",     10000, 0.80),
    ("76561198000000006", "Frank",   15000, 1.05),
]

# ---------------------------------------------------------------------------
# Match definitions
# ---------------------------------------------------------------------------

MATCHES = [
    {
        "match": {
            "match_id": "100",
            "start_time": "2026-01-10T20:00:00",
            "end_time": "2026-01-10T21:00:00",
            "winner": "team_alpha",
            "series_type": "bo1",
            "team1_name": "team_alpha",
            "team1_score": 13,
            "team2_name": "team_bravo",
            "team2_score": 7,
            "server_ip": "127.0.0.1",
        },
        "map": {
            "match_id": "100",
            "map_number": 0,
            "map_name": "de_dust2",
            "start_time": "2026-01-10T20:00:00",
            "end_time": "2026-01-10T21:00:00",
            "winner": "team_alpha",
            "team1_score": 13,
            "team2_score": 7,
        },
    },
    {
        "match": {
            "match_id": "101",
            "start_time": "2026-01-17T20:00:00",
            "end_time": "2026-01-17T21:00:00",
            "winner": "team_bravo",
            "series_type": "bo1",
            "team1_name": "team_alpha",
            "team1_score": 8,
            "team2_name": "team_bravo",
            "team2_score": 13,
            "server_ip": "127.0.0.1",
        },
        "map": {
            "match_id": "101",
            "map_number": 0,
            "map_name": "de_inferno",
            "start_time": "2026-01-17T20:00:00",
            "end_time": "2026-01-17T21:00:00",
            "winner": "team_bravo",
            "team1_score": 8,
            "team2_score": 13,
        },
    },
    {
        "match": {
            "match_id": "102",
            "start_time": "2026-01-24T20:00:00",
            "end_time": "2026-01-24T21:00:00",
            "winner": "team_alpha",
            "series_type": "bo1",
            "team1_name": "team_alpha",
            "team1_score": 13,
            "team2_name": "team_bravo",
            "team2_score": 11,
            "server_ip": "127.0.0.1",
        },
        "map": {
            "match_id": "102",
            "map_number": 0,
            "map_name": "de_dust2",
            "start_time": "2026-01-24T20:00:00",
            "end_time": "2026-01-24T21:00:00",
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


# Per-match player stat rows:
#   Match 100 (de_dust2)  — 4 players (Alice, Bob on alpha; Charlie, Diana on bravo)
#   Match 101 (de_inferno) — 4 players (Alice, Bob on alpha; Charlie, Diana on bravo)
#   Match 102 (de_dust2)  — 6 players (all six)
PLAYER_STATS = [
    # Match 100
    _make_player_stats("76561198000000001", "Alice",   "team_alpha", "100", 0, 25, 12, 5, 3200, 10),
    _make_player_stats("76561198000000002", "Bob",     "team_alpha", "100", 0, 18, 15, 7, 2400, 6),
    _make_player_stats("76561198000000003", "Charlie", "team_bravo", "100", 0, 14, 20, 3, 1800, 4),
    _make_player_stats("76561198000000004", "Diana",   "team_bravo", "100", 0, 10, 18, 4, 1500, 3),
    # Match 101
    _make_player_stats("76561198000000001", "Alice",   "team_alpha", "101", 0, 15, 18, 6, 2200, 5),
    _make_player_stats("76561198000000002", "Bob",     "team_alpha", "101", 0, 12, 16, 4, 1900, 4),
    _make_player_stats("76561198000000003", "Charlie", "team_bravo", "101", 0, 22, 10, 8, 3000, 9),
    _make_player_stats("76561198000000004", "Diana",   "team_bravo", "101", 0, 20, 14, 5, 2800, 7),
    # Match 102
    _make_player_stats("76561198000000001", "Alice",   "team_alpha", "102", 0, 20, 14, 4, 2800, 8),
    _make_player_stats("76561198000000002", "Bob",     "team_alpha", "102", 0, 16, 13, 6, 2100, 5),
    _make_player_stats("76561198000000003", "Charlie", "team_bravo", "102", 0, 11, 17, 3, 1600, 3),
    _make_player_stats("76561198000000004", "Diana",   "team_bravo", "102", 0, 13, 15, 5, 1900, 4),
    _make_player_stats("76561198000000005", "Eve",     "team_alpha", "102", 0,  9, 19, 2, 1200, 2),
    _make_player_stats("76561198000000006", "Frank",   "team_bravo", "102", 0, 17, 12, 7, 2500, 6),
]


WEAPON_STATS = [
    # Alice — match 100
    {"steamid64": "76561198000000001", "match_id": "100", "map_number": 0,
     "weapon": "ak-47", "shots_fired": 200, "shots_hit": 80, "kills": 15,
     "headshot_kills": 6, "damage": 2000, "rounds_with_weapon": 10,
     "first_seen_at": "2026-01-10T20:00:00", "updated_at": "2026-01-10T21:00:00"},
    {"steamid64": "76561198000000001", "match_id": "100", "map_number": 0,
     "weapon": "usp-s", "shots_fired": 50, "shots_hit": 25, "kills": 5,
     "headshot_kills": 3, "damage": 600, "rounds_with_weapon": 8,
     "first_seen_at": "2026-01-10T20:00:00", "updated_at": "2026-01-10T21:00:00"},
    # Alice — match 101
    {"steamid64": "76561198000000001", "match_id": "101", "map_number": 0,
     "weapon": "ak-47", "shots_fired": 180, "shots_hit": 60, "kills": 10,
     "headshot_kills": 3, "damage": 1500, "rounds_with_weapon": 12,
     "first_seen_at": "2026-01-17T20:00:00", "updated_at": "2026-01-17T21:00:00"},
    {"steamid64": "76561198000000001", "match_id": "101", "map_number": 0,
     "weapon": "usp-s", "shots_fired": 40, "shots_hit": 18, "kills": 3,
     "headshot_kills": 1, "damage": 400, "rounds_with_weapon": 6,
     "first_seen_at": "2026-01-17T20:00:00", "updated_at": "2026-01-17T21:00:00"},
    # Bob — match 100
    {"steamid64": "76561198000000002", "match_id": "100", "map_number": 0,
     "weapon": "m4a4", "shots_fired": 250, "shots_hit": 90, "kills": 12,
     "headshot_kills": 4, "damage": 1800, "rounds_with_weapon": 11,
     "first_seen_at": "2026-01-10T20:00:00", "updated_at": "2026-01-10T21:00:00"},
]


# ---------------------------------------------------------------------------
# Fixture: fully seeded test DB
# ---------------------------------------------------------------------------

@pytest.fixture
def seeded_db(db_conn, db_file):
    """Seed the test DB with players, matches, maps, player stats, and weapon stats.

    Returns ``(db_conn, db_file)`` so callers have both.
    """
    # Players
    for steam64, name, rating, leetify in PLAYERS:
        player = {
            "steamid64": steam64,
            "name": name,
            "premier_rating": rating,
            "leetify_rating": leetify,
            "total_matches": 10,
            "winrate": 0.55,
            "leetify_id": None,
        }
        insert_player(player, conn=db_conn)
        upsert_prime_rating(player, conn=db_conn)

    # Matches + maps
    for entry in MATCHES:
        insert_match(entry["match"], conn=db_conn)
        insert_match_map(entry["map"], conn=db_conn)

    # Player stats
    for ps in PLAYER_STATS:
        insert_match_player_stats(ps, conn=db_conn)

    # Weapon stats
    upsert_player_map_weapon_stats_many(WEAPON_STATS, conn=db_conn)

    db_conn.commit()
    return db_conn, db_file
