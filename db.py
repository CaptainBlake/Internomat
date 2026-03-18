import sqlite3
from datetime import datetime, timedelta

# INIT

DB_FILE = "internomat.db"
UPDATE_COOLDOWN_MINUTES = 0 # normal: 10 , debug: 0
def get_conn():
    return sqlite3.connect(DB_FILE)

def init_db():

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

        

# PLAYER TABLE

def insert_player(player):

    now = datetime.utcnow().isoformat()

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

def delete_player(steam_id):

    conn = get_conn()

    conn.execute(
        "DELETE FROM players WHERE steam64_id = ?",
        (steam_id,)
    )

    conn.commit()
    conn.close()

def update_player(player):
   
    now = datetime.utcnow().isoformat()

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

def get_players_to_update(max_age_minutes=UPDATE_COOLDOWN_MINUTES):

    cutoff = (datetime.utcnow() - timedelta(minutes=max_age_minutes)).isoformat()

    with get_conn() as conn:

        cur = conn.execute("""
            SELECT steam64_id
            FROM players
            WHERE last_updated IS NULL
               OR last_updated < ?
        """, (cutoff,))

        return [r[0] for r in cur.fetchall()]

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

        return cur.fetchall()

def player_exists(steam_id):

    with get_conn() as conn:

        cur = conn.execute(
            "SELECT 1 FROM players WHERE steam64_id = ?",
            (steam_id,)
        )

        return cur.fetchone() is not None
    
def upsert_player(player):
    if player_exists(player["steam64_id"]):
        update_player(player)
    else:
        insert_player(player)

# MATCH TABLE

def insert_match(match_id):
    with get_conn() as conn:
        conn.execute("""
        INSERT OR IGNORE INTO matches (match_id, created_at)
        VALUES (?, datetime('now'))
        """, (match_id,))

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

# MAP TABLE

def get_maps():

    with get_conn() as conn:

        cur = conn.execute("""
            SELECT name
            FROM maps
            ORDER BY name
        """)

        return [r[0] for r in cur.fetchall()]
    
def add_map(name):

    with get_conn() as conn:

        conn.execute(
            "INSERT OR IGNORE INTO maps(name) VALUES(?)",
            (name.strip(),)
        )

def delete_map(name):

    with get_conn() as conn:

        conn.execute(
            "DELETE FROM maps WHERE name = ?",
            (name,)
        )

def map_exists(name):

    with get_conn() as conn:

        cur = conn.execute(
            "SELECT 1 FROM maps WHERE name = ?",
            (name,)
        )

        return cur.fetchone() is not None