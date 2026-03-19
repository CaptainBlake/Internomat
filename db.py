import sqlite3
from datetime import datetime, timedelta

import services.logger as logger


# INIT

DB_FILE = "internomat.db"
UPDATE_COOLDOWN_MINUTES = 0  # normal: 10 , debug: 0


def get_conn():
    return sqlite3.connect(DB_FILE)


def init_db():

    logger.log("[DB] Initializing database", level="INFO")

    with get_conn() as conn:

        conn.execute("PRAGMA journal_mode=WAL")

        conn.execute("""
        CREATE TABLE IF NOT EXISTS players(
            steam64_id TEXT PRIMARY KEY,
            leetify_id TEXT,
            name TEXT,
            premier_rating INTEGER,
            leetify_rating REAL,
            total_matches INTEGER,
            winrate REAL,
            added_at TEXT,
            last_updated TEXT
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS maps(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            match_id TEXT PRIMARY KEY,
            created_at TEXT
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS match_player_stats (
            steamid64 TEXT,
            match_id TEXT,
            map_number INTEGER,
            name TEXT,
            team TEXT,
            kills INTEGER,
            deaths INTEGER,
            assists INTEGER,
            damage INTEGER,
            headshots INTEGER,
            flash_successes INTEGER,
            enemies_flashed INTEGER,
            entry_wins INTEGER,
            entry_count INTEGER,
            v1_wins INTEGER,
            v1_count INTEGER,
            v2_wins INTEGER,
            v2_count INTEGER,
            cash_earned INTEGER,
            PRIMARY KEY (steamid64, match_id, map_number)
        )
        """)

        cur = conn.execute("SELECT COUNT(*) FROM maps")
        count = cur.fetchone()[0]

        if count == 0:
            default_maps = [
                "de_mirage",
                "de_inferno",
                "de_nuke",
                "de_ancient",
                "de_anubis",
                "de_dust2",
                "de_overpass"
            ]

            conn.executemany(
                "INSERT INTO maps(name) VALUES(?)",
                [(m,) for m in default_maps]
            )

            logger.log(f"[DB] Inserted default maps count={len(default_maps)}", level="INFO")

    logger.log("[DB] Initialization complete", level="INFO")


# PLAYER TABLE

def insert_player(player):

    now = datetime.utcnow().isoformat()
    steam_id = logger.redact(player["steam64_id"])

    with get_conn() as conn:

        conn.execute(
            """
            INSERT INTO players
            (
                steam64_id,
                leetify_id,
                name,
                premier_rating,
                leetify_rating,
                total_matches,
                winrate,
                added_at,
                last_updated
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                player["steam64_id"],
                player["leetify_id"],
                player["name"],
                player["premier_rating"],
                player["leetify_rating"],
                player["total_matches"],
                player["winrate"],
                now,
                now
            )
        )

    logger.log(f"[DB] Insert player {steam_id}", level="INFO")


def delete_player(steam_id):

    redacted = logger.redact(steam_id)

    conn = get_conn()

    conn.execute(
        "DELETE FROM players WHERE steam64_id = ?",
        (steam_id,)
    )

    conn.commit()
    conn.close()

    logger.log(f"[DB] Delete player {redacted}", level="INFO")


def update_player(player):

    now = datetime.utcnow().isoformat()
    steam_id = logger.redact(player["steam64_id"])

    with get_conn() as conn:

        conn.execute(
            """
            UPDATE players
            SET
                leetify_id = ?,
                name = ?,
                premier_rating = ?,
                leetify_rating = ?,
                total_matches = ?,
                winrate = ?,
                last_updated = ?
            WHERE steam64_id = ?
            """,
            (
                player["leetify_id"],
                player["name"],
                player["premier_rating"],
                player["leetify_rating"],
                player["total_matches"],
                player["winrate"],
                now,
                player["steam64_id"]
            )
        )

    logger.log(f"[DB] Update player {steam_id}", level="INFO")


def get_players_to_update(max_age_minutes=UPDATE_COOLDOWN_MINUTES):

    cutoff = (datetime.utcnow() - timedelta(minutes=max_age_minutes)).isoformat()

    with get_conn() as conn:

        cur = conn.execute("""
            SELECT steam64_id
            FROM players
            WHERE last_updated IS NULL
               OR last_updated < ?
        """, (cutoff,))

        result = [r[0] for r in cur.fetchall()]

    logger.log(f"[DB] Players to update count={len(result)}", level="DEBUG")

    return result


def get_players():

    with get_conn() as conn:

        cur = conn.execute("""
        SELECT
            steam64_id,
            name,
            COALESCE(
                premier_rating,
                CAST(leetify_rating * 10000 AS INTEGER),
                0
            ) as rating
        FROM players
        ORDER BY rating DESC
        """)

        result = cur.fetchall()

    logger.log(f"[DB] Load players count={len(result)}", level="DEBUG")

    return result


def player_exists(steam_id):

    with get_conn() as conn:

        cur = conn.execute(
            "SELECT 1 FROM players WHERE steam64_id = ?",
            (steam_id,)
        )

        exists = cur.fetchone() is not None

    return exists


def upsert_player(player):

    steam_id = logger.redact(player["steam64_id"])

    if player_exists(player["steam64_id"]):
        logger.log(f"[DB] Upsert -> update {steam_id}", level="DEBUG")
        update_player(player)
    else:
        logger.log(f"[DB] Upsert -> insert {steam_id}", level="DEBUG")
        insert_player(player)


# MATCH TABLE

def insert_match(match_id):
    with get_conn() as conn:
        conn.execute("""
        INSERT OR IGNORE INTO matches (match_id, created_at)
        VALUES (?, datetime('now'))
        """, (match_id,))

    logger.log(f"[DB] Insert match {match_id[:6]}****", level="DEBUG")


def insert_match_player_stats(data):
    with get_conn() as conn:
        conn.execute("""
        INSERT OR REPLACE INTO match_player_stats (
            steamid64,
            match_id,
            map_number,
            name,
            team,
            kills,
            deaths,
            assists,
            damage,
            headshots,
            flash_successes,
            enemies_flashed,
            entry_wins,
            entry_count,
            v1_wins,
            v1_count,
            v2_wins,
            v2_count,
            cash_earned
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data["steamid64"],
            data["match_id"],
            data["map_number"],
            data["name"],
            data["team"],
            data["kills"],
            data["deaths"],
            data["assists"],
            data["damage"],
            data["headshots"],
            data["flash_successes"],
            data["enemies_flashed"],
            data["entry_wins"],
            data["entry_count"],
            data["v1_wins"],
            data["v1_count"],
            data["v2_wins"],
            data["v2_count"],
            data["cash_earned"],
        ))

    logger.log(f"[DB] Insert match stats match={data['match_id'][:6]}****", level="DEBUG")


# MAP TABLE

def get_maps():

    with get_conn() as conn:

        cur = conn.execute("""
            SELECT name
            FROM maps
            ORDER BY name
        """)

        result = [r[0] for r in cur.fetchall()]

    logger.log(f"[DB] Load maps count={len(result)}", level="DEBUG")

    return result


def add_map(name):

    with get_conn() as conn:

        conn.execute(
            "INSERT OR IGNORE INTO maps(name) VALUES(?)",
            (name.strip(),)
        )

    logger.log(f"[DB] Add map {name}", level="INFO")


def delete_map(name):

    with get_conn() as conn:

        conn.execute(
            "DELETE FROM maps WHERE name = ?",
            (name,)
        )

    logger.log(f"[DB] Delete map {name}", level="INFO")


def map_exists(name):

    with get_conn() as conn:

        cur = conn.execute(
            "SELECT 1 FROM maps WHERE name = ?",
            (name,)
        )

        exists = cur.fetchone() is not None

    return exists