import sqlite3
import os
from pathlib import Path
from datetime import datetime, timedelta

DB_FILE = "internomat.db"
# db functions
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

# player database
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

def get_players_to_update(max_age_minutes=10):

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
    
# map database
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