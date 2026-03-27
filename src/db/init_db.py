from .connection_db import get_conn
import services.logger as logger

def init_db():

    logger.log("[DB] Initializing database", level="INFO")

    with get_conn() as conn:

        conn.execute("PRAGMA journal_mode=WAL")

        # --- SETTINGS ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

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

                demo INTEGER NOT NULL DEFAULT 0,

                created_at TEXT
            )
        """)

        # Backward-compatible migration for existing databases.
        match_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(matches)").fetchall()
        }
        if "demo" not in match_columns:
            conn.execute("ALTER TABLE matches ADD COLUMN demo INTEGER NOT NULL DEFAULT 0")
            logger.log("[DB] Added matches.demo column", level="INFO")

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

        # --- PLAYER STATS ---
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
        conn.execute("CREATE INDEX IF NOT EXISTS idx_match_maps_name ON match_maps(map_name)")

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
