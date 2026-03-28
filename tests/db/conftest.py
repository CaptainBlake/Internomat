"""DB-layer test fixtures.

Every fixture here yields a connection that has had init_db() called, so all
tables (including weapon_dim / weapon_alias seeds) exist.
"""

import pytest


# ---------------------------------------------------------------------------
# Alias: db_conn → tmp_db from the root conftest
# ---------------------------------------------------------------------------

@pytest.fixture
def db_conn(tmp_db):
    """Function-scoped SQLite connection with full Internomat schema.

    Delegates to the root ``tmp_db`` fixture so schema setup is centralised.
    """
    return tmp_db


@pytest.fixture
def db_file(db_conn):
    """Return the file path of the test database.

    Useful for patching ``get_conn`` in modules that open (and close) their
    own connection via ``with get_conn() as conn:``.
    """
    row = db_conn.execute("PRAGMA database_list").fetchone()
    return row[2]


# ---------------------------------------------------------------------------
# Seeder helpers
# ---------------------------------------------------------------------------

def _make_player(
    steam64_id="76561198000000001",
    name="TestPlayer",
    premier_rating=15000,
    leetify_rating=None,
    total_matches=10,
    winrate=0.55,
    leetify_id=None,
):
    return {
        "steam64_id": steam64_id,
        "name": name,
        "premier_rating": premier_rating,
        "leetify_rating": leetify_rating,
        "total_matches": total_matches,
        "winrate": winrate,
        "leetify_id": leetify_id,
    }


def _make_match(
    match_id="100",
    start_time="2026-01-01T20:00:00",
    end_time="2026-01-01T21:00:00",
    winner="team_alpha",
    series_type="bo1",
    team1_name="team_alpha",
    team1_score=13,
    team2_name="team_bravo",
    team2_score=7,
    server_ip="127.0.0.1",
):
    return {
        "match_id": match_id,
        "start_time": start_time,
        "end_time": end_time,
        "winner": winner,
        "series_type": series_type,
        "team1_name": team1_name,
        "team1_score": team1_score,
        "team2_name": team2_name,
        "team2_score": team2_score,
        "server_ip": server_ip,
    }


def _make_match_map(
    match_id="100",
    map_number=0,
    map_name="de_dust2",
    start_time="2026-01-01T20:00:00",
    end_time="2026-01-01T21:00:00",
    winner="team_alpha",
    team1_score=13,
    team2_score=7,
):
    return {
        "match_id": match_id,
        "map_number": map_number,
        "map_name": map_name,
        "start_time": start_time,
        "end_time": end_time,
        "winner": winner,
        "team1_score": team1_score,
        "team2_score": team2_score,
    }


def _make_player_stats(
    steamid64="76561198000000001",
    match_id="100",
    map_number=0,
    name="TestPlayer",
    team="team_alpha",
    kills=20,
    deaths=10,
    assists=5,
    damage=2500,
    **overrides,
):
    base = {
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
        "enemy3ks": 1,
        "enemy2ks": 2,
        "utility_count": 5,
        "utility_damage": 100,
        "utility_successes": 3,
        "utility_enemies": 2,
        "flash_count": 4,
        "flash_successes": 2,
        "health_points_removed_total": 2000,
        "health_points_dealt_total": 2500,
        "shots_fired_total": 300,
        "shots_on_target_total": 120,
        "v1_count": 3,
        "v1_wins": 1,
        "v2_count": 1,
        "v2_wins": 0,
        "entry_count": 5,
        "entry_wins": 3,
        "equipment_value": 30000,
        "money_saved": 5000,
        "kill_reward": 6000,
        "live_time": 12000,
        "head_shot_kills": 8,
        "cash_earned": 40000,
        "enemies_flashed": 10,
    }
    base.update(overrides)
    return base


@pytest.fixture
def seed_player(db_conn):
    """Return a callable that inserts a player and returns the dict."""

    from db.players_db import insert_player

    def _seed(**kwargs):
        p = _make_player(**kwargs)
        insert_player(p, conn=db_conn)
        db_conn.commit()
        return p

    return _seed


@pytest.fixture
def seed_match(db_conn):
    """Return a callable that inserts a match + optional map row."""

    from db.matches_db import insert_match, insert_match_map

    def _seed(match_kwargs=None, map_kwargs=None):
        m = _make_match(**(match_kwargs or {}))
        insert_match(m, conn=db_conn)
        mm = None
        if map_kwargs is not None:
            mm = _make_match_map(**{"match_id": m["match_id"], **map_kwargs})
            insert_match_map(mm, conn=db_conn)
        db_conn.commit()
        return m, mm

    return _seed


@pytest.fixture
def seed_player_stats(db_conn):
    """Return a callable that inserts match_player_stats."""

    from db.matches_db import insert_match_player_stats

    def _seed(**kwargs):
        ps = _make_player_stats(**kwargs)
        insert_match_player_stats(ps, conn=db_conn)
        db_conn.commit()
        return ps

    return _seed
