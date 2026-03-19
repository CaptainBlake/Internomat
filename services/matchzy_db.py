import os
import sys
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

import db
from services.logger import log, log_event, log_warning, log_error

## build fix: 
# ENV & CONFIG

os.environ["LANG"] = "en_US.UTF-8"
os.environ["LC_ALL"] = "en_US.UTF-8"

def resource_path(relative_path):
    """Get absolute path to resource for dev and PyInstaller"""
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

env_path = resource_path(".env")

load_dotenv(env_path)

#check if env vars are set
required_env_vars = [
    "MATCHZY_DB_HOST",
    "MATCHZY_DB_USER",
    "MATCHZY_DB_PASSWORD",
    "MATCHZY_DB_NAME"
]
missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    log_error(f"Missing required environment variables: {', '.join(missing_vars)}")
    raise RuntimeError(f"Missing required environment variables: {', '.join(missing_vars)}")

class MatchZyDB:
    def __init__(self):
        self.conn = None

    # --- MYSQL CONNECTION ---
    def connect(self):
        if self.conn and self.conn.is_connected():
            return self.conn

        try:
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

            log_event("MYSQL_CONNECTED", {
                "host": os.getenv("MATCHZY_DB_HOST"),
                "db": os.getenv("MATCHZY_DB_NAME")
            }, level="INFO")

            return self.conn

        except Error as e:
            log_error(f"MySQL connection failed: {e}")
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

    # --- GET TABLES ---
    def get_match_tables(self):
        tables_raw = self._query("SHOW TABLES")
        tables = [t[0] for t in tables_raw]

        log_event("MYSQL_TABLES_FOUND", {"count": len(tables)}, level="DEBUG")

        for t in tables:
            log(f"[MYSQL_TABLE] {t}", level="DEBUG")

        match_tables = [t for t in tables if t.startswith("match_data_map")]

        log_event("MATCHZY_TABLES_FILTERED", {"count": len(match_tables)}, level="INFO")

        if not match_tables:
            log_warning("No match_data_map tables found")

        return match_tables

    # --- PARSE TABLE ---
    def parse_table(self, table_name):
        rows = self._query(f"SELECT * FROM {table_name}")

        if not rows:
            log_warning(f"Empty table: {table_name}")
            return []

        header = [str(col) for col in rows[0]]

        # log_event("TABLE_HEADER", {"table": table_name,"columns": header}, level="DEBUG")

        parsed_rows = []

        for raw_row in rows[1:]:
            row_dict = {}

            for i, value in enumerate(raw_row):
                key = header[i]
                row_dict[key] = value if value is not None else None

            parsed_rows.append(row_dict)

        log_event("TABLE_PARSED", {
            "table": table_name,
            "rows": len(parsed_rows)
        }, level="INFO")

        return parsed_rows

    # --- SAFE INT ---
    def _to_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    # --- MAIN SYNC ---
    def sync_to_local(self):

        log_event("MATCHZY_SYNC_START")

        tables = self.get_match_tables()

        total_rows = 0
        total_tables = len(tables)

        for idx, table in enumerate(tables, start=1):

            log_event("PROCESS_TABLE", {
                "table": table,
                "index": idx,
                "total": total_tables
            }, level="INFO")

            try:
                parsed_rows = self.parse_table(table)

                for row in parsed_rows:

                    match_id = str(row.get("matchid"))
                    steamid = str(row.get("steamid64"))

                    # --- MATCH ---
                    db.insert_match(match_id)

                    # --- PLAYER STATS ---
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
                log_error(f"Failed processing table {table}: {e}")

        log_event("MATCHZY_SYNC_DONE", {
            "tables": total_tables,
            "rows": total_rows
        }, level="INFO")


# --- ENTRY POINT FOR GUI ---
def sync():
    MatchZyDB().sync_to_local()