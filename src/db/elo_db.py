"""Database operations for the Elo rating system."""

from __future__ import annotations

from .connection_db import execute_write, executemany_write, optional_conn


#  Schema 

def init_elo_tables(conn):
    """Create Elo tables. Called once from init_db."""

    conn.execute("""
        CREATE TABLE IF NOT EXISTS elo_history (
            steamid64       TEXT NOT NULL,
            match_id        TEXT NOT NULL,
            season          INTEGER NOT NULL DEFAULT 0,
            elo_before      REAL NOT NULL,
            elo_after       REAL NOT NULL,
            elo_delta       REAL NOT NULL,
            result          TEXT NOT NULL,
            team_name       TEXT,
            team_elo_before REAL,
            opp_team_elo_before REAL,
            adr             REAL,
            adr_expected    REAL,
            adr_multiplier  REAL,
            global_anchor_used REAL,
            updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (steamid64, match_id)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS elo_ratings (
            steamid64       TEXT PRIMARY KEY,
            elo             REAL NOT NULL DEFAULT 1500.0,
            season          INTEGER NOT NULL DEFAULT 0,
            matches_played  INTEGER NOT NULL DEFAULT 0,
            wins            INTEGER NOT NULL DEFAULT 0,
            losses          INTEGER NOT NULL DEFAULT 0,
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS elo_state (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS elo_seasons (
            season          INTEGER PRIMARY KEY,
            start_at        TEXT,
            end_at          TEXT,
            is_open_ended   INTEGER NOT NULL DEFAULT 0,
            source          TEXT NOT NULL DEFAULT 'settings',
            updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS elo_ratings_season (
            season          INTEGER NOT NULL,
            steamid64       TEXT NOT NULL,
            elo             REAL NOT NULL DEFAULT 1500.0,
            matches_played  INTEGER NOT NULL DEFAULT 0,
            wins            INTEGER NOT NULL DEFAULT 0,
            losses          INTEGER NOT NULL DEFAULT 0,
            updated_at      TEXT NOT NULL DEFAULT (datetime('now')),
            PRIMARY KEY (season, steamid64)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS elo_match_season (
            match_id         TEXT PRIMARY KEY,
            season           INTEGER NOT NULL,
            played_at        TEXT,
            source           TEXT NOT NULL DEFAULT 'elo_recalc',
            updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS elo_season_tuning (
            season                  INTEGER PRIMARY KEY,
            k_factor                REAL NOT NULL,
            base_rating             REAL NOT NULL,
            adr_alpha               REAL NOT NULL,
            adr_spread              REAL NOT NULL,
            adr_min_mult            REAL NOT NULL,
            adr_max_mult            REAL NOT NULL,
            adr_prior_matches       REAL NOT NULL,
            initial_global_anchor   REAL NOT NULL,
            source                  TEXT NOT NULL DEFAULT 'settings',
            updated_at              TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)

    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_elo_history_match "
        "ON elo_history(match_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_elo_history_season "
        "ON elo_history(season)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_elo_ratings_elo "
        "ON elo_ratings(elo DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_elo_ratings_season_elo "
        "ON elo_ratings_season(season, elo DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_elo_match_season_season "
        "ON elo_match_season(season)"
    )


#  Write SQL 

_UPSERT_HISTORY = """
    INSERT INTO elo_history (
        steamid64, match_id, season,
        elo_before, elo_after, elo_delta, result,
        team_name, team_elo_before, opp_team_elo_before,
        adr, adr_expected, adr_multiplier, global_anchor_used,
        updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    ON CONFLICT(steamid64, match_id) DO UPDATE SET
        season              = excluded.season,
        elo_before          = excluded.elo_before,
        elo_after           = excluded.elo_after,
        elo_delta           = excluded.elo_delta,
        result              = excluded.result,
        team_name           = excluded.team_name,
        team_elo_before     = excluded.team_elo_before,
        opp_team_elo_before = excluded.opp_team_elo_before,
        adr                 = excluded.adr,
        adr_expected        = excluded.adr_expected,
        adr_multiplier      = excluded.adr_multiplier,
        global_anchor_used  = excluded.global_anchor_used,
        updated_at          = excluded.updated_at
"""

_UPSERT_RATING = """
    INSERT INTO elo_ratings (
        steamid64, elo, season, matches_played, wins, losses, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
    ON CONFLICT(steamid64) DO UPDATE SET
        elo             = excluded.elo,
        season          = excluded.season,
        matches_played  = excluded.matches_played,
        wins            = excluded.wins,
        losses          = excluded.losses,
        updated_at      = excluded.updated_at
"""

_UPSERT_STATE = """
    INSERT INTO elo_state (key, value, updated_at)
    VALUES (?, ?, datetime('now'))
    ON CONFLICT(key) DO UPDATE SET
        value      = excluded.value,
        updated_at = excluded.updated_at
"""

_UPSERT_SEASON = """
    INSERT INTO elo_seasons (season, start_at, end_at, is_open_ended, source, updated_at)
    VALUES (?, ?, ?, ?, ?, datetime('now'))
    ON CONFLICT(season) DO UPDATE SET
        start_at      = excluded.start_at,
        end_at        = excluded.end_at,
        is_open_ended = excluded.is_open_ended,
        source        = excluded.source,
        updated_at    = excluded.updated_at
"""

_UPSERT_RATING_SEASON = """
    INSERT INTO elo_ratings_season (
        season, steamid64, elo, matches_played, wins, losses, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
    ON CONFLICT(season, steamid64) DO UPDATE SET
        elo             = excluded.elo,
        matches_played  = excluded.matches_played,
        wins            = excluded.wins,
        losses          = excluded.losses,
        updated_at      = excluded.updated_at
"""

_UPSERT_MATCH_SEASON = """
    INSERT INTO elo_match_season (match_id, season, played_at, source, updated_at)
    VALUES (?, ?, ?, ?, datetime('now'))
    ON CONFLICT(match_id) DO UPDATE SET
        season     = excluded.season,
        played_at  = excluded.played_at,
        source     = excluded.source,
        updated_at = excluded.updated_at
"""

_UPSERT_SEASON_TUNING = """
    INSERT INTO elo_season_tuning (
        season, k_factor, base_rating,
        adr_alpha, adr_spread, adr_min_mult, adr_max_mult,
        adr_prior_matches, initial_global_anchor,
        source, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    ON CONFLICT(season) DO UPDATE SET
        k_factor              = excluded.k_factor,
        base_rating           = excluded.base_rating,
        adr_alpha             = excluded.adr_alpha,
        adr_spread            = excluded.adr_spread,
        adr_min_mult          = excluded.adr_min_mult,
        adr_max_mult          = excluded.adr_max_mult,
        adr_prior_matches     = excluded.adr_prior_matches,
        initial_global_anchor = excluded.initial_global_anchor,
        source                = excluded.source,
        updated_at            = excluded.updated_at
"""


#  Writes 

def upsert_elo_history_many(rows, *, season=0, conn=None):
    with optional_conn(conn) as c:
        params = [
            (
                r["steamid64"], r["match_id"], int(r.get("season", season)),
                r["elo_before"], r["elo_after"], r["elo_delta"], r["result"],
                r.get("team_name"),
                r.get("team_elo_before"),
                r.get("opp_team_elo_before"),
                r.get("adr"),
                r.get("adr_expected"),
                r.get("adr_multiplier"),
                r.get("global_anchor_used"),
            )
            for r in rows
        ]
        executemany_write(c, _UPSERT_HISTORY, params)


def upsert_elo_ratings_many(rows, *, season=0, conn=None):
    with optional_conn(conn) as c:
        params = [
            (
                r["steamid64"], r["elo"], int(r.get("season", season)),
                r["matches_played"], r["wins"], r["losses"],
            )
            for r in rows
        ]
        executemany_write(c, _UPSERT_RATING, params)


def upsert_elo_seasons_many(rows, *, source="settings", conn=None):
    with optional_conn(conn) as c:
        params = [
            (
                int(r["season"]),
                r.get("start_at"),
                r.get("end_at"),
                1 if r.get("is_open_ended") else 0,
                str(r.get("source", source) or source),
            )
            for r in rows
        ]
        executemany_write(c, _UPSERT_SEASON, params)


def upsert_elo_ratings_season_many(rows, conn=None):
    with optional_conn(conn) as c:
        params = [
            (
                int(r.get("season", 0)),
                r["steamid64"],
                r["elo"],
                r["matches_played"],
                r["wins"],
                r["losses"],
            )
            for r in rows
        ]
        executemany_write(c, _UPSERT_RATING_SEASON, params)


def upsert_elo_match_season_many(rows, *, source="elo_recalc", conn=None):
    with optional_conn(conn) as c:
        params = [
            (
                r["match_id"],
                int(r.get("season", 0)),
                r.get("played_at"),
                str(r.get("source", source) or source),
            )
            for r in rows
        ]
        executemany_write(c, _UPSERT_MATCH_SEASON, params)


def upsert_elo_season_tuning(season, tune, *, source="settings", conn=None):
    with optional_conn(conn) as c:
        execute_write(
            c,
            _UPSERT_SEASON_TUNING,
            (
                int(season),
                float(tune["K_FACTOR"]),
                float(tune["BASE_RATING"]),
                float(tune["ADR_ALPHA"]),
                float(tune["ADR_SPREAD"]),
                float(tune["ADR_MIN_MULT"]),
                float(tune["ADR_MAX_MULT"]),
                float(tune["ADR_PRIOR_MATCHES"]),
                float(tune["INITIAL_GLOBAL_ANCHOR"]),
                str(source or "settings"),
            ),
        )


def clear_elo_tables(conn=None):
    """Delete all Elo rows before a full recomputation."""
    with optional_conn(conn) as c:
        execute_write(c, "DELETE FROM elo_history")
        execute_write(c, "DELETE FROM elo_ratings")
        execute_write(c, "DELETE FROM elo_ratings_season")
        execute_write(c, "DELETE FROM elo_match_season")


def clear_elo_seasons(conn=None):
    """Delete season dimension rows before rewriting from settings."""
    with optional_conn(conn) as c:
        execute_write(c, "DELETE FROM elo_seasons")


def upsert_elo_state(key, value, conn=None):
    with optional_conn(conn) as c:
        execute_write(c, _UPSERT_STATE, (key, value))


#  Reads 

def get_elo_rating(steamid64, conn=None):
    """Current Elo for a single player, or *None* if not yet rated."""
    with optional_conn(conn) as c:
        row = c.execute(
            "SELECT elo FROM elo_ratings WHERE steamid64 = ?",
            (steamid64,),
        ).fetchone()
        return float(row["elo"]) if row else None


def get_all_elo_ratings(conn=None):
    """All current ratings, ordered by Elo descending."""
    with optional_conn(conn) as c:
        return c.execute(
            "SELECT * FROM elo_ratings ORDER BY elo DESC"
        ).fetchall()


def get_elo_history_for_player(steamid64, conn=None):
    """Full match-by-match Elo history for one player."""
    with optional_conn(conn) as c:
        return c.execute(
            "SELECT * FROM elo_history WHERE steamid64 = ? ORDER BY match_id",
            (steamid64,),
        ).fetchall()


def get_elo_state(key, conn=None):
    """Read a value from the elo_state key-value store."""
    with optional_conn(conn) as c:
        row = c.execute(
            "SELECT value FROM elo_state WHERE key = ?",
            (key,),
        ).fetchone()
        return row["value"] if row else None


def get_elo_seasons(conn=None):
    with optional_conn(conn) as c:
        return c.execute(
            "SELECT * FROM elo_seasons ORDER BY season ASC"
        ).fetchall()


def get_elo_ratings_for_season(season, conn=None):
    with optional_conn(conn) as c:
        return c.execute(
            "SELECT * FROM elo_ratings_season WHERE season = ? ORDER BY elo DESC",
            (int(season),),
        ).fetchall()


def get_match_ids_for_season(season, conn=None):
    with optional_conn(conn) as c:
        rows = c.execute(
            "SELECT match_id FROM elo_match_season WHERE season = ? ORDER BY played_at ASC, match_id ASC",
            (int(season),),
        ).fetchall()
        return [str(r["match_id"]) for r in rows]


def get_elo_season_tunings(conn=None):
    with optional_conn(conn) as c:
        return c.execute(
            "SELECT * FROM elo_season_tuning ORDER BY season ASC"
        ).fetchall()
