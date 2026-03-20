import os
import sys
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

import db
import services.logger as logger


# ENV & CONFIG

def resource_path(relative_path):
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


env_path = resource_path(".env")
load_dotenv(env_path)


required_env_vars = [
    "MATCHZY_DB_HOST",
    "MATCHZY_DB_USER",
    "MATCHZY_DB_PASSWORD",
    "MATCHZY_DB_NAME"
]

missing_vars = [var for var in required_env_vars if not os.getenv(var)]

if missing_vars:
    logger.log_error(f"Missing required environment variables: {', '.join(missing_vars)}")
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")


class MatchZyDB:
    def __init__(self):
        self.conn = None

    # --- MYSQL CONNECTION ---
    def connect(self):
        if self.conn and self.conn.is_connected():
            return self.conn

        try:
            logger.log("[MYSQL] Connecting", level="INFO")

            self.conn = mysql.connector.connect(
                host=os.getenv("MATCHZY_DB_HOST"),
                user=os.getenv("MATCHZY_DB_USER"),
                password=os.getenv("MATCHZY_DB_PASSWORD"),
                database=os.getenv("MATCHZY_DB_NAME"),
                autocommit=True,
                connection_timeout=10,
                use_pure=True,
                charset="utf8mb4",
                collation="utf8mb4_general_ci"
            )

            logger.log("[MYSQL] Connected", level="INFO")

            return self.conn

        except Error as e:
            logger.log_error(f"MySQL connection failed: {e}")
            raise RuntimeError(f"MatchZy DB connection failed: {e}")

    # --- QUERY ---
    def _query(self, query):
        conn = self.connect()
        cursor = conn.cursor()

        try:
            cursor.execute(query)
            return cursor.fetchall()
        finally:
            cursor.close()

    def get_match_tables(self):

        tables_raw = self._query("SHOW TABLES")
        tables = [t[0] for t in tables_raw]

        logger.log(f"[MYSQL] Tables found={len(tables)}", level="DEBUG")

        for t in tables:
            logger.log(f"[MYSQL] Table: {t}", level="DEBUG")

        # --- identify matchzy tables ---
        matchzy_stats_maps = [t for t in tables if t.startswith("matchzy_stats_maps")]
        matchzy_stats_players = [t for t in tables if t.startswith("matchzy_stats_players")]
        matchzy_stats_matches = [t for t in tables if t.startswith("matchzy_stats_matches")]

        # --- debug each table ---
        def debug_table(table_name):

            try:
                logger.log(f"[MYSQL] Inspecting table={table_name}", level="DEBUG")

                # --- row count ---
                count = self._query(f"SELECT COUNT(*) FROM {table_name}")[0][0]
                logger.log(f"[MYSQL] {table_name} rows={count}", level="DEBUG")

                # --- columns ---
                columns_raw = self._query(f"SHOW COLUMNS FROM {table_name}")
                columns = [c[0] for c in columns_raw]
                logger.log(f"[MYSQL] {table_name} columns={columns}", level="DEBUG")

                # --- sample rows (limited!) ---
                sample_rows = self._query(f"SELECT * FROM {table_name} LIMIT 3")

                for i, row in enumerate(sample_rows):
                    preview = {
                        columns[idx]: str(value)[:50]  # truncate to avoid spam
                        for idx, value in enumerate(row)
                    }
                    logger.log(f"[MYSQL] {table_name} sample[{i}]={preview}", level="DEBUG")

            except Exception as e:
                logger.log_error(f"[MYSQL] Failed inspecting {table_name}: {e}")

        # inspect all 3 tables
        for t in matchzy_stats_maps:
            debug_table(t)

        for t in matchzy_stats_players:
            debug_table(t)

        for t in matchzy_stats_matches:
            debug_table(t)

        # --- keep legacy match_data_map support ---
        match_tables = [t for t in tables if t.startswith("match_data_map")]

        logger.log(f"[MATCHZY] Match tables={len(match_tables)}", level="INFO")

        if not match_tables:
            logger.log_warning("No match_data_map tables found")

        return match_tables

    # --- PARSE TABLE ---
    def parse_table(self, table_name):

        logger.log(f"[MATCHZY] Parsing table {table_name}", level="DEBUG")

        rows = self._query(f"SELECT * FROM {table_name}")

        if not rows:
            logger.log_warning(f"Empty table: {table_name}")
            return []

        header = [str(col) for col in rows[0]]

        parsed_rows = []

        for raw_row in rows[1:]:
            row_dict = {}

            for i, value in enumerate(raw_row):
                key = header[i]
                row_dict[key] = value if value is not None else None

            parsed_rows.append(row_dict)

        logger.log(f"[MATCHZY] Parsed rows={len(parsed_rows)} table={table_name}", level="DEBUG")

        return parsed_rows

    # --- SAFE INT ---
    def _to_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    # --- MAIN SYNC ---
    def sync_to_local(self):

        logger.log("[MATCHZY] Sync start", level="INFO")

        tables = self.get_match_tables()

        total_rows = 0
        total_tables = len(tables)

        for idx, table in enumerate(tables, start=1):

            logger.log(
                f"[MATCHZY] Processing table {idx}/{total_tables}: {table}",
                level="INFO"
            )

            try:
                parsed_rows = self.parse_table(table)

                for row in parsed_rows:

                    match_id = str(row.get("matchid"))
                    steamid = str(row.get("steamid64"))

                    db.insert_match(match_id)

                    db.insert_match_player_stats({
                        "steamid64": steamid,
                        "match_id": match_id,
                        "map_number": self._to_int(row.get("mapnumber")),

                        "name": row.get("name"),
                        "team": row.get("team"),

                        "kills": self._to_int(row.get("kills")),
                        "deaths": self._to_int(row.get("deaths")),
                        "assists": self._to_int(row.get("assists")),
                        "damage": self._to_int(row.get("damage")),

                        "headshots": self._to_int(row.get("head_shot_kills")),
                        "flash_successes": self._to_int(row.get("flash_successes")),
                        "enemies_flashed": self._to_int(row.get("enemies_flashed")),

                        "entry_wins": self._to_int(row.get("entry_wins")),
                        "entry_count": self._to_int(row.get("entry_count")),

                        "v1_wins": self._to_int(row.get("v1_wins")),
                        "v1_count": self._to_int(row.get("v1_count")),
                        "v2_wins": self._to_int(row.get("v2_wins")),
                        "v2_count": self._to_int(row.get("v2_count")),

                        "cash_earned": self._to_int(row.get("cash_earned")),
                    })

                    total_rows += 1

            except Exception as e:
                logger.log_error(f"Failed processing table {table}: {e}")

        logger.log(
            f"[MATCHZY] Sync done tables={total_tables} rows={total_rows}",
            level="INFO"
        )


# ENTRY POINT

def sync():
    logger.log("[USER] MatchZy sync triggered", level="INFO")
    MatchZyDB().sync_to_local()