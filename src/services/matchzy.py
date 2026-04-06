import mysql.connector
from mysql.connector import Error

from db.connection_db import write_transaction
import db.matches_db as match_db
import db.maps_db as maps_db
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

        cursor = conn.cursor(dictionary=True)
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

    @staticmethod
    def _clean_team_token(value):
        return str(value or "").strip().lower().replace("_", "").replace("-", "").replace(" ", "")

    @staticmethod
    def _row_get(row, idx=None, keys=None, default=None):
        if isinstance(row, dict):
            keys = keys or []
            lowered = {str(k).lower(): v for k, v in row.items()}

            for key in keys:
                val = row.get(key)
                if val not in (None, ""):
                    return val
                val = lowered.get(str(key).lower())
                if val not in (None, ""):
                    return val

            if idx is not None:
                values = list(row.values())
                if 0 <= idx < len(values):
                    return values[idx]
            return default

        if isinstance(row, (tuple, list)):
            if idx is not None and 0 <= idx < len(row):
                return row[idx]
            return default

        return default

    def _build_team_name_map(self, team1_name=None, team2_name=None, player_rows=None):
        """Build a per-match mapping from raw labels to canonical TeamA / TeamB."""
        mapping = {}

        def _register(raw, canonical):
            txt = str(raw or "").strip()
            if not txt:
                return
            mapping[txt] = canonical
            mapping[txt.lower()] = canonical

        # Canonical aliases always supported.
        for alias in ["TeamA", "teama", "A", "CT", "CT_SIDE", "CounterTerrorist", "Counter-Terrorist"]:
            _register(alias, "TeamA")
        for alias in ["TeamB", "teamb", "B", "T", "T_SIDE", "Terrorist", "Terrorists"]:
            _register(alias, "TeamB")

        t1 = str(team1_name or "").strip()
        t2 = str(team2_name or "").strip()
        if t1:
            _register(t1, "TeamA")
        if t2:
            _register(t2, "TeamB")

        # Fallback: infer from first-seen distinct team labels in player rows.
        if (not t1 or not t2) and player_rows:
            ordered = []
            for p in player_rows:
                raw_team = str(self._row_get(p, idx=3, keys=["team", "team_name"], default="") or "").strip()
                if not raw_team:
                    continue
                token = self._clean_team_token(raw_team)
                if token in {"", "all"}:
                    continue
                if raw_team not in ordered:
                    ordered.append(raw_team)

            if ordered:
                _register(ordered[0], "TeamA")
            if len(ordered) > 1:
                _register(ordered[1], "TeamB")

        return mapping

    def _canonical_team_label(self, raw_value, team_name_map):
        txt = str(raw_value or "").strip()
        if not txt:
            return txt

        token = self._clean_team_token(txt)
        if token in {"teama", "a", "ct", "ctside", "counter", "counterterrorist", "counterterrorists"}:
            return "TeamA"
        if token in {"teamb", "b", "t", "tside", "terrorist", "terrorists"}:
            return "TeamB"

        return team_name_map.get(txt) or team_name_map.get(txt.lower()) or txt

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
                key = (
                    str(self._row_get(row, idx=0, keys=["match_id", "matchid", "id"], default="")),
                    self._to_int(self._row_get(row, idx=1, keys=["map_number", "mapnumber", "map_no"], default=0)),
                )
                players_by_match_map.setdefault(key, []).append(row)

            matches_by_id = {}
            for m in matches:
                match_key = str(self._row_get(m, idx=0, keys=["match_id", "matchid", "id"], default=""))
                if match_key:
                    matches_by_id[match_key] = m

            total_maps = 0
            total_players = 0
            imported_players = 0
            imported_maps = 0
            players_for_pool_import = []

            with write_transaction() as local_conn:
                for map_row in maps:

                    matchid = str(self._row_get(map_row, idx=0, keys=["match_id", "matchid", "id"], default=""))
                    mapnumber = self._to_int(self._row_get(map_row, idx=1, keys=["map_number", "mapnumber", "map_no"], default=0))

                    start_time = self._row_get(map_row, idx=2, keys=["start_time", "started_at"], default=None)
                    end_time = self._row_get(map_row, idx=3, keys=["end_time", "ended_at", "finished_at"], default=None)

                    if not end_time:
                        logger.log(f"[MATCHZY] Skipping unfinished match {matchid}", level="DEBUG")
                        continue

                    winner = self._row_get(
                        map_row,
                        idx=4,
                        keys=["winner", "winner_team", "winning_team", "winner_team_name", "winning_team_name"],
                        default="",
                    )
                    mapname = self._row_get(map_row, idx=5, keys=["map_name", "map", "mapname"], default="")
                    team1_score = self._to_int(self._row_get(map_row, idx=6, keys=["team1_score", "score_team1", "team_a_score"], default=0))
                    team2_score = self._to_int(self._row_get(map_row, idx=7, keys=["team2_score", "score_team2", "team_b_score"], default=0))

                    logger.log(f"[MATCHZY] Processing match={matchid} map={mapname}", level="INFO")

                    match_data = matches_by_id.get(matchid)
                    player_rows_for_map = players_by_match_map.get((matchid, mapnumber), [])

                    team_name_map = self._build_team_name_map(
                        team1_name=self._row_get(match_data, idx=5, keys=["team1_name", "team_a_name", "team1"], default=None),
                        team2_name=self._row_get(match_data, idx=7, keys=["team2_name", "team_b_name", "team2"], default=None),
                        player_rows=player_rows_for_map,
                    )

                    canonical_map_winner = self._canonical_team_label(winner, team_name_map)

                    if match_db.match_exists(matchid):
                        # Existing rows are skipped for map/player insert, but we still backfill
                        # matches.winner when it's missing.
                        match_db.set_match_winner_if_missing(
                            matchid,
                            canonical_map_winner,
                            conn=local_conn,
                        )
                        logger.log(f"[MATCHZY] Skipping existing match {matchid}", level="DEBUG")
                        continue

                    canonical_match_winner = self._canonical_team_label(
                        self._row_get(
                            match_data,
                            idx=3,
                            keys=["winner", "winner_team", "winning_team", "winner_team_name", "winning_team_name"],
                            default="",
                        ),
                        team_name_map,
                    )

                    if not str(canonical_match_winner or "").strip():
                        canonical_match_winner = canonical_map_winner

                    if match_data:
                        match_db.insert_match({
                            "match_id": matchid,
                            "start_time": self._row_get(match_data, idx=1, keys=["start_time", "started_at"], default=None),
                            "end_time": self._row_get(match_data, idx=2, keys=["end_time", "ended_at", "finished_at"], default=None),
                            "winner": canonical_match_winner,
                            "series_type": self._row_get(match_data, idx=4, keys=["series_type", "series"], default=None),
                            "team1_name": "TeamA",
                            "team1_score": self._to_int(self._row_get(match_data, idx=6, keys=["team1_score", "score_team1", "team_a_score"], default=0)),
                            "team2_name": "TeamB",
                            "team2_score": self._to_int(self._row_get(match_data, idx=8, keys=["team2_score", "score_team2", "team_b_score"], default=0)),
                            "server_ip": self._row_get(match_data, idx=9, keys=["server_ip", "server", "server_address"], default=None),
                        }, conn=local_conn)
                    else:
                        match_db.insert_match({"match_id": matchid}, conn=local_conn)

                    match_db.insert_match_map({
                        "match_id": matchid,
                        "map_number": mapnumber,
                        "map_name": mapname,
                        "start_time": start_time,
                        "end_time": end_time,
                        "winner": canonical_map_winner,
                        "team1_score": team1_score,
                        "team2_score": team2_score,
                    }, conn=local_conn)

                    total_maps += 1

                    map_player_payloads = []
                    for p in player_rows_for_map:
                        player_payload = {
                            "steamid64": str(self._row_get(p, idx=2, keys=["steamid64", "steamid", "steam_id"], default="")),
                            "match_id": matchid,
                            "map_number": mapnumber,
                            "team": self._canonical_team_label(
                                self._row_get(p, idx=3, keys=["team", "team_name"], default=""),
                                team_name_map,
                            ),
                            "name": self._row_get(p, idx=4, keys=["name", "player_name"], default=""),
                            "kills": self._to_int(self._row_get(p, idx=5, keys=["kills"], default=0)),
                            "deaths": self._to_int(self._row_get(p, idx=6, keys=["deaths"], default=0)),
                            "damage": self._to_int(self._row_get(p, idx=7, keys=["damage"], default=0)),
                            "assists": self._to_int(self._row_get(p, idx=8, keys=["assists"], default=0)),
                            "enemy5ks": self._to_int(self._row_get(p, idx=9, keys=["enemy5ks"], default=0)),
                            "enemy4ks": self._to_int(self._row_get(p, idx=10, keys=["enemy4ks"], default=0)),
                            "enemy3ks": self._to_int(self._row_get(p, idx=11, keys=["enemy3ks"], default=0)),
                            "enemy2ks": self._to_int(self._row_get(p, idx=12, keys=["enemy2ks"], default=0)),
                            "utility_count": self._to_int(self._row_get(p, idx=13, keys=["utility_count"], default=0)),
                            "utility_damage": self._to_int(self._row_get(p, idx=14, keys=["utility_damage"], default=0)),
                            "utility_successes": self._to_int(self._row_get(p, idx=15, keys=["utility_successes"], default=0)),
                            "utility_enemies": self._to_int(self._row_get(p, idx=16, keys=["utility_enemies"], default=0)),
                            "flash_count": self._to_int(self._row_get(p, idx=17, keys=["flash_count"], default=0)),
                            "flash_successes": self._to_int(self._row_get(p, idx=18, keys=["flash_successes"], default=0)),
                            "health_points_removed_total": self._to_int(self._row_get(p, idx=19, keys=["health_points_removed_total"], default=0)),
                            "health_points_dealt_total": self._to_int(self._row_get(p, idx=20, keys=["health_points_dealt_total"], default=0)),
                            "shots_fired_total": self._to_int(self._row_get(p, idx=21, keys=["shots_fired_total"], default=0)),
                            "shots_on_target_total": self._to_int(self._row_get(p, idx=22, keys=["shots_on_target_total"], default=0)),
                            "v1_count": self._to_int(self._row_get(p, idx=23, keys=["v1_count"], default=0)),
                            "v1_wins": self._to_int(self._row_get(p, idx=24, keys=["v1_wins"], default=0)),
                            "v2_count": self._to_int(self._row_get(p, idx=25, keys=["v2_count"], default=0)),
                            "v2_wins": self._to_int(self._row_get(p, idx=26, keys=["v2_wins"], default=0)),
                            "entry_count": self._to_int(self._row_get(p, idx=27, keys=["entry_count"], default=0)),
                            "entry_wins": self._to_int(self._row_get(p, idx=28, keys=["entry_wins"], default=0)),
                            "equipment_value": self._to_int(self._row_get(p, idx=29, keys=["equipment_value"], default=0)),
                            "money_saved": self._to_int(self._row_get(p, idx=30, keys=["money_saved"], default=0)),
                            "kill_reward": self._to_int(self._row_get(p, idx=31, keys=["kill_reward"], default=0)),
                            "live_time": self._to_int(self._row_get(p, idx=32, keys=["live_time"], default=0)),
                            "head_shot_kills": self._to_int(self._row_get(p, idx=33, keys=["head_shot_kills"], default=0)),
                            "cash_earned": self._to_int(self._row_get(p, idx=34, keys=["cash_earned"], default=0)),
                            "enemies_flashed": self._to_int(self._row_get(p, idx=35, keys=["enemies_flashed"], default=0)),
                        }
                        map_player_payloads.append(player_payload)

                        if settings.auto_import_players_from_history:
                            players_for_pool_import.append(
                                {
                                    "steam64_id": player_payload["steamid64"],
                                    "name": player_payload["name"],
                                }
                            )

                    match_db.insert_match_player_stats_many(map_player_payloads, conn=local_conn)
                    total_players += len(map_player_payloads)

                if settings.auto_import_players_from_history and players_for_pool_import:
                    imported_players = players_db.upsert_players_from_match_stats(
                        players_for_pool_import,
                        conn=local_conn,
                    )

                if settings.auto_import_maps_from_history:
                    imported_maps = maps_db.import_maps_from_match_history(conn=local_conn)

            logger.log(
                f"[MATCHZY] Sync done maps={total_maps} players={total_players} imported_pool_players={imported_players} imported_pool_maps={imported_maps}",
                level="INFO"
            )
        finally:
            self.close()


def sync():
    logger.log("[USER] MatchZy sync triggered", level="INFO")
    MatchZy().sync_to_local()