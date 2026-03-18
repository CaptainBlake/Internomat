import os
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

import db

load_dotenv()


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
                autocommit=True
            )
            return self.conn

        except Error as e:
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

        print("\n[MYSQL] All tables:")
        for t in tables:
            print(" -", t)

        match_tables = [t for t in tables if t.startswith("match_data_map")]

        print("\n[MATCHZY] Detected match tables:")
        for t in match_tables:
            print(" -", t)

        if not match_tables:
            print("⚠️ No match_data_map tables found!")

        return match_tables

    # --- PARSE TABLE (NO PANDAS) ---
    def parse_table(self, table_name):
        rows = self._query(f"SELECT * FROM {table_name}")

        if not rows:
            return []

        # first row = header
        header = [str(col) for col in rows[0]]

        parsed_rows = []

        for raw_row in rows[1:]:
            row_dict = {}

            for i, value in enumerate(raw_row):
                key = header[i]

                # basic cleanup
                if value is None:
                    row_dict[key] = None
                else:
                    row_dict[key] = value

            parsed_rows.append(row_dict)

        return parsed_rows

    # --- SAFE INT ---
    def _to_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    # --- MAIN SYNC ---
    def sync_to_local(self):
        
        print("Fetching MatchZy data...")
        tables = self.get_match_tables()

        total_rows = 0

        for table in tables:
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
                print(f"[SKIP TABLE] {table}: {e}")

        print(f"Synced {total_rows} rows to local SQLite")


# --- ENTRY POINT FOR GUI ---
def sync():
    MatchZyDB().sync_to_local()