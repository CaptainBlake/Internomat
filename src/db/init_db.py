from .connection_db import get_conn
from .weapon_catalog import iter_seed_alias_rows, iter_seed_weapon_rows
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

                kast REAL,
                impact REAL,
                rating REAL,

                PRIMARY KEY (steamid64, match_id, map_number)
            )
        """)

        # Backward-compatible migration for existing databases.
        mps_columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(match_player_stats)").fetchall()
        }
        for col, col_type in [("kast", "REAL"), ("impact", "REAL"), ("rating", "REAL")]:
            if col not in mps_columns:
                conn.execute(f"ALTER TABLE match_player_stats ADD COLUMN {col} {col_type}")
                logger.log(f"[DB] Added match_player_stats.{col} column", level="INFO")

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

        # --- CACHE RESTORE SIGNATURES ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache_restore_state (
                source_match_id TEXT NOT NULL,
                source_map_number INTEGER NOT NULL,
                payload_sha256 TEXT NOT NULL,
                canonical_match_id TEXT,
                canonical_map_number INTEGER,
                source_file TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (source_match_id, source_map_number)
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_cache_restore_sha ON cache_restore_state(payload_sha256)"
        )

        # --- WEAPON CATALOG ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS weapon_dim (
                weapon TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                category TEXT,
                source TEXT NOT NULL DEFAULT 'seed-cs2',
                is_active INTEGER NOT NULL DEFAULT 1,
                first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS weapon_alias (
                raw_weapon TEXT PRIMARY KEY,
                canonical_weapon TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'seed-cs2',
                first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (canonical_weapon) REFERENCES weapon_dim(weapon)
            )
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_weapon_alias_canonical ON weapon_alias(canonical_weapon)")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS player_map_weapon_stats (
                steamid64 TEXT NOT NULL,
                match_id TEXT NOT NULL,
                map_number INTEGER NOT NULL,
                weapon TEXT NOT NULL,
                shots_fired INTEGER NOT NULL DEFAULT 0,
                shots_hit INTEGER NOT NULL DEFAULT 0,
                kills INTEGER NOT NULL DEFAULT 0,
                headshot_kills INTEGER NOT NULL DEFAULT 0,
                damage INTEGER NOT NULL DEFAULT 0,
                rounds_with_weapon INTEGER NOT NULL DEFAULT 0,
                first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (steamid64, match_id, map_number, weapon),
                FOREIGN KEY (weapon) REFERENCES weapon_dim(weapon)
            )
        """)

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_player_weapon_player ON player_map_weapon_stats(steamid64)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_player_weapon_weapon ON player_map_weapon_stats(weapon)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_player_weapon_match_map ON player_map_weapon_stats(match_id, map_number)"
        )

        # --- PHASE 4: MOVEMENT + TIMELINE ANALYTICS ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS player_map_movement_stats (
                steamid64 TEXT NOT NULL,
                match_id TEXT NOT NULL,
                map_number INTEGER NOT NULL,
                total_distance_units REAL NOT NULL DEFAULT 0,
                total_distance_m REAL NOT NULL DEFAULT 0,
                avg_speed_units_s REAL NOT NULL DEFAULT 0,
                avg_speed_m_s REAL NOT NULL DEFAULT 0,
                max_speed_units_s REAL NOT NULL DEFAULT 0,
                ticks_alive INTEGER NOT NULL DEFAULT 0,
                alive_seconds REAL NOT NULL DEFAULT 0,
                distance_per_round_units REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (steamid64, match_id, map_number)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS player_round_movement_stats (
                steamid64 TEXT NOT NULL,
                match_id TEXT NOT NULL,
                map_number INTEGER NOT NULL,
                round_num INTEGER NOT NULL,
                side TEXT,
                distance_units REAL NOT NULL DEFAULT 0,
                avg_speed_units_s REAL NOT NULL DEFAULT 0,
                max_speed_units_s REAL NOT NULL DEFAULT 0,
                ticks_alive INTEGER NOT NULL DEFAULT 0,
                alive_seconds REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (steamid64, match_id, map_number, round_num)
            )
        """)

        conn.execute("""
            CREATE TABLE IF NOT EXISTS player_round_timeline_bins (
                steamid64 TEXT NOT NULL,
                match_id TEXT NOT NULL,
                map_number INTEGER NOT NULL,
                round_num INTEGER NOT NULL,
                bin_index INTEGER NOT NULL,
                bin_start_sec REAL NOT NULL DEFAULT 0,
                median_speed_m_s REAL NOT NULL DEFAULT 0,
                samples INTEGER NOT NULL DEFAULT 0,
                side TEXT,
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (steamid64, match_id, map_number, round_num, bin_index)
            )
        """)

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_player_map_move_player ON player_map_movement_stats(steamid64)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_player_map_move_match_map ON player_map_movement_stats(match_id, map_number)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_player_round_move_player ON player_round_movement_stats(steamid64)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_player_round_move_match_map ON player_round_movement_stats(match_id, map_number, round_num)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_player_round_bins_player ON player_round_timeline_bins(steamid64)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_player_round_bins_match_map ON player_round_timeline_bins(match_id, map_number, round_num, bin_index)"
        )

        weapon_seed_rows = list(iter_seed_weapon_rows())
        conn.executemany(
            """
            INSERT INTO weapon_dim (weapon, display_name, category, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(weapon) DO UPDATE SET
                display_name = excluded.display_name,
                category = excluded.category,
                source = excluded.source,
                is_active = 1,
                updated_at = datetime('now')
            """,
            weapon_seed_rows,
        )

        alias_seed_rows = list(iter_seed_alias_rows())
        conn.executemany(
            """
            INSERT INTO weapon_alias (raw_weapon, canonical_weapon, source)
            VALUES (?, ?, ?)
            ON CONFLICT(raw_weapon) DO UPDATE SET
                canonical_weapon = excluded.canonical_weapon,
                source = excluded.source,
                updated_at = datetime('now')
            """,
            alias_seed_rows,
        )

        logger.log(
            f"[DB] Seeded CS2 weapon catalog weapons={len(weapon_seed_rows)} aliases={len(alias_seed_rows)}",
            level="INFO",
        )

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
