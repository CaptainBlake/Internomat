import sqlite3
from datetime import datetime, timedelta
import json
import services.logger as logger
from services.settings import settings

# INIT

DB_FILE = "internomat.db"

def get_conn():
    conn = sqlite3.connect(DB_FILE, timeout=10, check_same_thread=False)
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn

def init_db():

    logger.log("[DB] Initializing database", level="INFO")

    with get_conn() as conn:

        conn.execute("PRAGMA journal_mode=WAL")

        # --- PLAYERS ---
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

        # --- MATCH META ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            match_id TEXT PRIMARY KEY,

            start_time TEXT,
            end_time TEXT,

            winner TEXT,
            series_type TEXT,

            team1_name TEXT,
            team1_score INTEGER,

            team2_name TEXT,
            team2_score INTEGER,

            server_ip TEXT,

            created_at TEXT
        )
        """)

        # --- MAPS PER MATCH ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS match_maps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            match_id TEXT,
            map_number INTEGER,
            map_name TEXT,

            start_time TEXT,
            end_time TEXT,

            winner TEXT,

            team1_score INTEGER,
            team2_score INTEGER,

            UNIQUE(match_id, map_number)
        )
        """)

        # --- PLAYER STATS (FULL MATCHZY COVERAGE) ---
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

            enemy5ks INTEGER,
            enemy4ks INTEGER,
            enemy3ks INTEGER,
            enemy2ks INTEGER,

            utility_count INTEGER,
            utility_damage INTEGER,
            utility_successes INTEGER,
            utility_enemies INTEGER,

            flash_count INTEGER,
            flash_successes INTEGER,

            health_points_removed_total INTEGER,
            health_points_dealt_total INTEGER,

            shots_fired_total INTEGER,
            shots_on_target_total INTEGER,

            v1_count INTEGER,
            v1_wins INTEGER,
            v2_count INTEGER,
            v2_wins INTEGER,

            entry_count INTEGER,
            entry_wins INTEGER,

            equipment_value INTEGER,
            money_saved INTEGER,
            kill_reward INTEGER,
            live_time INTEGER,

            head_shot_kills INTEGER,
            cash_earned INTEGER,
            enemies_flashed INTEGER,

            PRIMARY KEY (steamid64, match_id, map_number)
        )
        """)

        # --- GLOBAL MAP POOL ---
        conn.execute("""
        CREATE TABLE IF NOT EXISTS maps(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE
        )
        """)

        # --- INDEXES ---
        conn.execute("CREATE INDEX IF NOT EXISTS idx_match_player_match ON match_player_stats(match_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_match_maps_match ON match_maps(match_id)")

        # --- DEFAULT MAPS ---
        cur = conn.execute("SELECT COUNT(*) FROM maps")
        if cur.fetchone()[0] == 0:
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

def insert_player(player, conn=None):
    own_conn = conn is None
    conn = conn or get_conn()

    now = datetime.utcnow().isoformat()
    steam_id = logger.redact(player["steam64_id"])

    conn.execute("""
        INSERT INTO players VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        player["steam64_id"],
        player.get("leetify_id"),
        player["name"],
        player.get("premier_rating"),
        player.get("leetify_rating"),
        player.get("total_matches"),
        player.get("winrate"),
        now,
        now
    ))

    if own_conn:
        conn.commit()
        conn.close()

    logger.log(f"[DB] Insert player {steam_id}", level="INFO")


def update_player(player, conn=None):
    own_conn = conn is None
    conn = conn or get_conn()

    now = datetime.utcnow().isoformat()
    steam_id = logger.redact(player["steam64_id"])

    conn.execute("""
        UPDATE players SET
            leetify_id = ?,
            name = ?,
            premier_rating = ?,
            leetify_rating = ?,
            total_matches = ?,
            winrate = ?,
            last_updated = ?
        WHERE steam64_id = ?
    """, (
        player.get("leetify_id"),
        player["name"],
        player.get("premier_rating"),
        player.get("leetify_rating"),
        player.get("total_matches"),
        player.get("winrate"),
        now,
        player["steam64_id"]
    ))

    if own_conn:
        conn.commit()
        conn.close()

    logger.log(f"[DB] Update player {steam_id}", level="INFO")


def delete_player(steam_id):
    redacted = logger.redact(steam_id)

    with get_conn() as conn:
        conn.execute("DELETE FROM players WHERE steam64_id = ?", (steam_id,))

    logger.log(f"[DB] Delete player {redacted}", level="INFO")


def upsert_player(player, mode="full", conn=None):
    own_conn = conn is None
    conn = conn or get_conn()

    now = datetime.utcnow().isoformat()
    steam_id = logger.redact(player["steam64_id"])

    if mode == "import":
        conn.execute("""
            INSERT INTO players (steam64_id, name, added_at, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(steam64_id) DO UPDATE SET
                name=excluded.name,
                last_updated=excluded.last_updated
        """, (
            player["steam64_id"],
            player["name"],
            now,
            now
        ))
    else:
        conn.execute("""
            INSERT INTO players VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(steam64_id) DO UPDATE SET
                leetify_id=excluded.leetify_id,
                name=excluded.name,
                premier_rating=excluded.premier_rating,
                leetify_rating=excluded.leetify_rating,
                total_matches=excluded.total_matches,
                winrate=excluded.winrate,
                last_updated=excluded.last_updated
        """, (
            player["steam64_id"],
            player.get("leetify_id"),
            player["name"],
            player.get("premier_rating"),
            player.get("leetify_rating"),
            player.get("total_matches"),
            player.get("winrate"),
            now,
            now
        ))

    if own_conn:
        conn.commit()
        conn.close()

    logger.log(f"[DB] Upsert player {steam_id}", level="DEBUG")


def get_players():
    with get_conn() as conn:
        cur = conn.execute("""
        SELECT steam64_id, name,
        COALESCE(premier_rating, CAST(leetify_rating * 10000 AS INTEGER), 0)
        FROM players
        ORDER BY 3 DESC
        """)
        result = cur.fetchall()

    logger.log(f"[DB] Loaded players count={len(result)}", level="DEBUG")
    return result


def update_player_name(player):
    now = datetime.utcnow().isoformat()
    steam_id = logger.redact(player["steam64_id"])

    with get_conn() as conn:
        conn.execute("""
            UPDATE players SET
                name = ?,
                last_updated = ?
            WHERE steam64_id = ?
        """, (
            player["name"],
            now,
            player["steam64_id"]
        ))

    logger.log(f"[DB] Update player name {steam_id}", level="INFO")


def get_players_to_update(max_age_minutes=None):
    if max_age_minutes is None:
        max_age_minutes = settings.update_cooldown_minutes
    
    logger.log(
        f"[DB] Cooldown used = {max_age_minutes} minutes",
        level="DEBUG"
    )
    cutoff = (datetime.utcnow() - timedelta(minutes=max_age_minutes)).isoformat()

    with get_conn() as conn:
        cur = conn.execute("""
            SELECT steam64_id FROM players
            WHERE last_updated IS NULL OR last_updated < ?
        """, (cutoff,))
        result = [r[0] for r in cur.fetchall()]

    logger.log(f"[DB] Players to update count={len(result)}", level="DEBUG")
    return result


# MATCH PIPELINE

def insert_match(data, conn=None):
    own_conn = conn is None
    conn = conn or get_conn()

    conn.execute("""
    INSERT INTO matches (
        match_id,
        start_time,
        end_time,
        winner,
        series_type,
        team1_name,
        team1_score,
        team2_name,
        team2_score,
        server_ip,
        created_at
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    ON CONFLICT(match_id) DO UPDATE SET
        end_time=excluded.end_time,
        winner=excluded.winner,
        team1_score=excluded.team1_score,
        team2_score=excluded.team2_score
    """, (
        data["match_id"],
        data.get("start_time"),
        data.get("end_time"),
        data.get("winner"),
        data.get("series_type"),
        data.get("team1_name"),
        data.get("team1_score"),
        data.get("team2_name"),
        data.get("team2_score"),
        data.get("server_ip"),
    ))

    if own_conn:
        conn.commit()
        conn.close()

    logger.log(f"[DB] Upsert match {data['match_id']}", level="DEBUG")


def insert_match_map(data, conn=None):
    own_conn = conn is None
    conn = conn or get_conn()

    conn.execute("""
    INSERT INTO match_maps (
        match_id,
        map_number,
        map_name,
        start_time,
        end_time,
        winner,
        team1_score,
        team2_score
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(match_id, map_number) DO UPDATE SET
        end_time=excluded.end_time,
        winner=excluded.winner,
        team1_score=excluded.team1_score,
        team2_score=excluded.team2_score
    """, (
        data["match_id"],
        data["map_number"],
        data["map_name"],
        data.get("start_time"),
        data.get("end_time"),
        data.get("winner"),
        data.get("team1_score"),
        data.get("team2_score"),
    ))

    if own_conn:
        conn.commit()
        conn.close()

    logger.log(f"[DB] Upsert map match={data['match_id']} map={data['map_number']}", level="DEBUG")


def insert_match_player_stats(data, conn=None):
    own_conn = conn is None
    conn = conn or get_conn()

    conn.execute("""
    INSERT INTO match_player_stats (
        steamid64, match_id, map_number,
        name, team,
        kills, deaths, assists, damage,
        enemy5ks, enemy4ks, enemy3ks, enemy2ks,
        utility_count, utility_damage, utility_successes, utility_enemies,
        flash_count, flash_successes,
        health_points_removed_total, health_points_dealt_total,
        shots_fired_total, shots_on_target_total,
        v1_count, v1_wins, v2_count, v2_wins,
        entry_count, entry_wins,
        equipment_value, money_saved, kill_reward, live_time,
        head_shot_kills, cash_earned, enemies_flashed
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(steamid64, match_id, map_number) DO UPDATE SET
        kills=excluded.kills,
        deaths=excluded.deaths,
        assists=excluded.assists,
        damage=excluded.damage,
        cash_earned=excluded.cash_earned
    """, (
        data["steamid64"], data["match_id"], data["map_number"],
        data["name"], data["team"],
        data["kills"], data["deaths"], data["assists"], data["damage"],
        data["enemy5ks"], data["enemy4ks"], data["enemy3ks"], data["enemy2ks"],
        data["utility_count"], data["utility_damage"], data["utility_successes"], data["utility_enemies"],
        data["flash_count"], data["flash_successes"],
        data["health_points_removed_total"], data["health_points_dealt_total"],
        data["shots_fired_total"], data["shots_on_target_total"],
        data["v1_count"], data["v1_wins"], data["v2_count"], data["v2_wins"],
        data["entry_count"], data["entry_wins"],
        data["equipment_value"], data["money_saved"], data["kill_reward"], data["live_time"],
        data["head_shot_kills"], data["cash_earned"], data["enemies_flashed"]
    ))

    if own_conn:
        conn.commit()
        conn.close()


def match_exists(match_id):
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT 1 FROM matches WHERE match_id = ? LIMIT 1",
            (match_id,)
        )
        exists = cur.fetchone() is not None

    logger.log(f"[DB] Match exists={exists} match={str(match_id)[:6]}", level="DEBUG")

    return exists


# MAP POOL

def get_maps():
    with get_conn() as conn:
        cur = conn.execute("SELECT name FROM maps ORDER BY name")
        result = [r[0] for r in cur.fetchall()]

    logger.log(f"[DB] Loaded map-pool = {len(result)}", level="DEBUG")
    return result


def add_map(name):
    with get_conn() as conn:
        conn.execute("INSERT OR IGNORE INTO maps(name) VALUES(?)", (name.strip(),))

    logger.log(f"[DB] Add map {name}", level="INFO")


def delete_map(name):
    with get_conn() as conn:
        conn.execute("DELETE FROM maps WHERE name = ?", (name,))

    logger.log(f"[DB] Delete map {name}", level="INFO")


def map_exists(name):
    with get_conn() as conn:
        cur = conn.execute("SELECT 1 FROM maps WHERE name = ?", (name,))
        return cur.fetchone() is not None


# IMPORT 
def import_players(filepath):
    
    with open(filepath, "r", encoding="utf-8") as f:
        players = json.load(f)

    count = 0

    with get_conn() as conn:
        for p in players:
            if not isinstance(p, dict):
                continue

            if not p.get("steam64_id") or not p.get("name"):
                continue

            try:
                player = {
                    "steam64_id": p["steam64_id"],
                    "name": p["name"]
                }

                upsert_player(player, mode="import", conn=conn)
                count += 1

            except Exception as e:
                logger.log_error(f"Import error {p.get('steam64_id')}", exc=e)

    logger.log(f"[DB] Import players count={count}", level="INFO")


# EXPORT
def export_players(filepath):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT
                steam64_id,
                name
            FROM players
        """)

        columns = [c[0] for c in cur.description]
        rows = cur.fetchall()

        players = [dict(zip(columns, row)) for row in rows]

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(players, f, indent=2)

    logger.log(f"[DB] Export players count={len(players)} -> {filepath}", level="INFO")


def get_top_kills(limit=10):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT
                COALESCE(name, steamid64) AS player_name,
                steamid64,
                SUM(COALESCE(kills, 0)) AS total_kills
            FROM match_player_stats
            GROUP BY steamid64, player_name
            ORDER BY total_kills DESC, player_name ASC
            LIMIT ?
        """, (limit,))
        return cur.fetchall()


def get_top_deaths(limit=10):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT
                COALESCE(name, steamid64) AS player_name,
                steamid64,
                SUM(COALESCE(deaths, 0)) AS total_deaths
            FROM match_player_stats
            GROUP BY steamid64, player_name
            ORDER BY total_deaths DESC, player_name ASC
            LIMIT ?
        """, (limit,))
        return cur.fetchall()


def get_top_ratings(limit=10):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT
                name,
                steam64_id,
                COALESCE(premier_rating, CAST(leetify_rating * 10000 AS INTEGER), 0) AS rating
            FROM players
            WHERE name IS NOT NULL AND name != ''
            ORDER BY rating DESC, name ASC
            LIMIT ?
        """, (limit,))
        return cur.fetchall()


def get_top_damage_per_match(limit=10):
    with get_conn() as conn:
        cur = conn.execute("""
            SELECT
                COALESCE(name, steamid64) AS player_name,
                steamid64,
                ROUND(AVG(COALESCE(damage, 0)), 1) AS avg_damage
            FROM match_player_stats
            GROUP BY steamid64, player_name
            ORDER BY avg_damage DESC, player_name ASC
            LIMIT ?
        """, (limit,))
        return cur.fetchall()