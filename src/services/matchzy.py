import mysql.connector
from mysql.connector import Error

from db.connection_db import write_transaction
import db.matches_db as match_db
import db.players_db as players_db
import services.logger as logger
from core.settings.settings import settings


# --- MATCHZY SERVICE ---
class MatchZy:

    def __init__(self):
        self.conn = None

    def _validate_config(self):
        missing = []

        if not settings.matchzy_host:
            missing.append("host")
        if not settings.matchzy_port:
            missing.append("port")
        if not settings.matchzy_user:
            missing.append("user")
        if not settings.matchzy_database:
            missing.append("database")


        if missing:
            msg = f"Missing MatchZy config: {', '.join(missing)}"
            logger.log_error(msg)
            raise RuntimeError(msg)

    def connect(self):
        if self.conn and self.conn.is_connected():
            return self.conn

        self._validate_config()

        try:
            logger.log(
                f"[MYSQL] Connecting to {settings.matchzy_host}:{settings.matchzy_port}",
                level="DEBUG"
            )

            self.conn = mysql.connector.connect(
                host=settings.matchzy_host,
                port=settings.matchzy_port,
                user=settings.matchzy_user,
                password=settings.matchzy_password,
                database=settings.matchzy_database,
                autocommit=True,
                connection_timeout=10,
                use_pure=True,
                charset="utf8mb4",
                collation="utf8mb4_general_ci"
            )

            logger.log("[MYSQL] Connected", level="INFO")
            return self.conn

        except Exception as e:
            logger.log_error(f"MySQL connection failed: {e}", exc=e)
            raise RuntimeError(f"MySQL connection failed: {e}") from e

    def _query(self, query):
        conn = self.connect()
        if conn is None:
            raise RuntimeError("MySQL connection failed: no connection object returned")

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

    def close(self):
        if self.conn and self.conn.is_connected():
            self.conn.close()
            logger.log("[MYSQL] Connection closed", level="DEBUG")
        self.conn = None

    # --- MAIN SYNC ---
    def sync_to_local(self):
        logger.log("[MATCHZY] Sync start", level="INFO")

        try:
            maps = self._query("SELECT * FROM matchzy_stats_maps")
            players = self._query("SELECT * FROM matchzy_stats_players")
            matches = self._query("SELECT * FROM matchzy_stats_matches")

            logger.log(
                f"[MATCHZY] maps={len(maps)} players={len(players)} matches={len(matches)}",
                level="DEBUG"
            )

            players_by_match_map = {}
            for row in players:
                key = (str(row[0]), self._to_int(row[1]))
                players_by_match_map.setdefault(key, []).append(row)

            matches_by_id = {str(m[0]): m for m in matches}

            total_maps = 0
            total_players = 0
            imported_players = 0
            players_for_pool_import = []

            with write_transaction() as local_conn:
                for map_row in maps:

                    matchid = str(map_row[0])
                    mapnumber = self._to_int(map_row[1])

                    start_time = map_row[2]
                    end_time = map_row[3]

                    if match_db.match_exists(matchid):
                        logger.log(f"[MATCHZY] Skipping existing match {matchid}", level="DEBUG")
                        continue

                    if not end_time:
                        logger.log(f"[MATCHZY] Skipping unfinished match {matchid}", level="DEBUG")
                        continue

                    winner = map_row[4]
                    mapname = map_row[5]
                    team1_score = self._to_int(map_row[6])
                    team2_score = self._to_int(map_row[7])

                    logger.log(f"[MATCHZY] Processing match={matchid} map={mapname}", level="INFO")

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
                        }, conn=local_conn)
                    else:
                        match_db.insert_match({"match_id": matchid}, conn=local_conn)

                    match_db.insert_match_map({
                        "match_id": matchid,
                        "map_number": mapnumber,
                        "map_name": mapname,
                        "start_time": start_time,
                        "end_time": end_time,
                        "winner": winner,
                        "team1_score": team1_score,
                        "team2_score": team2_score,
                    }, conn=local_conn)

                    total_maps += 1

                    key = (matchid, mapnumber)
                    for p in players_by_match_map.get(key, []):
                        player_payload = {
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
                        }

                        match_db.insert_match_player_stats(player_payload, conn=local_conn)

                        if settings.auto_import_match_players:
                            players_for_pool_import.append(
                                {
                                    "steam64_id": player_payload["steamid64"],
                                    "name": player_payload["name"],
                                }
                            )

                        total_players += 1

                if settings.auto_import_match_players and players_for_pool_import:
                    imported_players = players_db.upsert_players_from_match_stats(
                        players_for_pool_import,
                        conn=local_conn,
                    )

            logger.log(
                f"[MATCHZY] Sync done maps={total_maps} players={total_players} imported_pool={imported_players}",
                level="INFO"
            )
        finally:
            self.close()


def sync():
    logger.log("[USER] MatchZy sync triggered", level="INFO")
    MatchZy().sync_to_local()