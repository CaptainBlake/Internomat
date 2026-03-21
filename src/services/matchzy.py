import os
import sys
import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv

import db.matches_db as match_db
import services.logger as logger

# path helper for PyInstaller
def resource_path(relative_path):
    if getattr(sys, "frozen", False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

env_path = resource_path(".env")
load_dotenv(env_path)

# --- MATCHZY SERVICE ---
class MatchZy:

    def __init__(self):
        self.conn = None

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
            logger.log_error(f"MySQL connection failed: {e}", exc=e)
            raise RuntimeError(f"MatchZy DB connection failed: {e}")

    def _query(self, query):
        conn = self.connect()
        cursor = conn.cursor()
        try:
            cursor.execute(query)
            return cursor.fetchall()
        finally:
            cursor.close()

    def _to_int(self, value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    # Main sync function - fetches all data from MatchZy DB and upserts into local DB
    def sync_to_local(self):

        logger.log("[MATCHZY] Sync start", level="INFO")

        # --- LOAD TABLES ---
        maps = self._query("SELECT * FROM matchzy_stats_maps")
        players = self._query("SELECT * FROM matchzy_stats_players")
        matches = self._query("SELECT * FROM matchzy_stats_matches")

        logger.log(f"[MATCHZY] maps={len(maps)} players={len(players)} matches={len(matches)}", level="DEBUG")

        # --- BUILD INDEXES ---
        players_by_match_map = {}

        for row in players:
            matchid = str(row[0])
            mapnumber = self._to_int(row[1])
            key = (matchid, mapnumber)
            players_by_match_map.setdefault(key, []).append(row)

        matches_by_id = {str(m[0]): m for m in matches}

        total_maps = 0
        total_players = 0

        # --- PROCESS MAPS ---
        for map_row in maps:

            matchid = str(map_row[0])  
            mapnumber = self._to_int(map_row[1])

            start_time = map_row[2]
            end_time = map_row[3]

            # look if match id exists in local DB - if yes, skip entire match (maps + players)
            if match_db.match_exists(matchid):
                logger.log(f"[MATCHZY] Skipping match {matchid}. Allready exists in local match_db", level="DEBUG")
                continue
            
            if not end_time:
                logger.log(f"[MATCHZY] Skipping unfinished match {matchid}", level="DEBUG")
                continue

            winner = map_row[4]
            mapname = map_row[5]
            team1_score = self._to_int(map_row[6])
            team2_score = self._to_int(map_row[7])

            logger.log(f"[MATCHZY] Processing match={matchid} map={mapname}", level="INFO")

            # MATCH
         
            match_data = matches_by_id.get(matchid)

            if match_data:
                match_db.insert_match({
                    "match_id": matchid,
                    "start_time": match_data[1],
                    "end_time": match_data[2],
                    "winner": match_data[3],
                    "series_type": match_data[4],
                    "team1_name": match_data[5],
                    "team1_score": self._to_int(match_data[6]),
                    "team2_name": match_data[7],
                    "team2_score": self._to_int(match_data[8]),
                    "server_ip": match_data[9],
                })
            else:
                match_db.insert_match({
                    "match_id": matchid
                })

            
            # MAP
            
            match_db.insert_match_map({
                "match_id": matchid,
                "map_number": mapnumber,
                "map_name": mapname,
                "start_time": start_time,
                "end_time": end_time,
                "winner": winner,
                "team1_score": team1_score,
                "team2_score": team2_score,
            })

            total_maps += 1

            
            # PLAYERS
            
            key = (matchid, mapnumber)
            map_players = players_by_match_map.get(key, [])

            for p in map_players:

                match_db.insert_match_player_stats({
                    "steamid64": str(p[2]),
                    "match_id": matchid,
                    "map_number": mapnumber,

                    "team": p[3],
                    "name": p[4],

                    "kills": self._to_int(p[5]),
                    "deaths": self._to_int(p[6]),
                    "damage": self._to_int(p[7]),
                    "assists": self._to_int(p[8]),

                    "enemy5ks": self._to_int(p[9]),
                    "enemy4ks": self._to_int(p[10]),
                    "enemy3ks": self._to_int(p[11]),
                    "enemy2ks": self._to_int(p[12]),

                    "utility_count": self._to_int(p[13]),
                    "utility_damage": self._to_int(p[14]),
                    "utility_successes": self._to_int(p[15]),
                    "utility_enemies": self._to_int(p[16]),

                    "flash_count": self._to_int(p[17]),
                    "flash_successes": self._to_int(p[18]),

                    "health_points_removed_total": self._to_int(p[19]),
                    "health_points_dealt_total": self._to_int(p[20]),

                    "shots_fired_total": self._to_int(p[21]),
                    "shots_on_target_total": self._to_int(p[22]),

                    "v1_count": self._to_int(p[23]),
                    "v1_wins": self._to_int(p[24]),
                    "v2_count": self._to_int(p[25]),
                    "v2_wins": self._to_int(p[26]),

                    "entry_count": self._to_int(p[27]),
                    "entry_wins": self._to_int(p[28]),

                    "equipment_value": self._to_int(p[29]),
                    "money_saved": self._to_int(p[30]),
                    "kill_reward": self._to_int(p[31]),

                    "live_time": self._to_int(p[32]),
                    "head_shot_kills": self._to_int(p[33]),
                    "cash_earned": self._to_int(p[34]),
                    "enemies_flashed": self._to_int(p[35]),
                })

                total_players += 1

        logger.log(
            f"[MATCHZY] Sync done maps={total_maps} players={total_players}",
            level="INFO"
        )



def sync():
    logger.log("[USER] MatchZy sync triggered", level="INFO")
    MatchZy().sync_to_local()