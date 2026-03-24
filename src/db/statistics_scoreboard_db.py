from .connection_db import get_conn


def fetch_map_summary(match_id, map_number):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT
                mm.match_id,
                mm.map_number,
                mm.map_name,
                COALESCE(mm.winner, m.winner) AS winner,
                m.team1_name,
                m.team2_name,
                COALESCE(mm.team1_score, m.team1_score) AS team1_score,
                COALESCE(mm.team2_score, m.team2_score) AS team2_score,
                COALESCE(mm.end_time, mm.start_time, m.end_time, m.start_time) AS played_at
            FROM match_maps mm
            LEFT JOIN matches m ON mm.match_id = m.match_id
            WHERE mm.match_id = ?
              AND mm.map_number = ?
            LIMIT 1
            """,
            (str(match_id), int(map_number)),
        ).fetchone()


def fetch_map_scoreboard(match_id, map_number):
    with get_conn() as conn:
        return conn.execute(
            """
            SELECT
                COALESCE(team, '?') AS team,
                COALESCE(name, steamid64) AS player_name,
                steamid64,
                COALESCE(kills, 0) AS kills,
                COALESCE(deaths, 0) AS deaths,
                COALESCE(assists, 0) AS assists,
                COALESCE(damage, 0) AS damage,
                COALESCE(head_shot_kills, 0) AS head_shot_kills,
                COALESCE(shots_fired_total, 0) AS shots_fired_total,
                COALESCE(shots_on_target_total, 0) AS shots_on_target_total,
                COALESCE(entry_count, 0) AS entry_count,
                COALESCE(entry_wins, 0) AS entry_wins,
                COALESCE(v1_count, 0) AS v1_count,
                COALESCE(v1_wins, 0) AS v1_wins,
                COALESCE(v2_count, 0) AS v2_count,
                COALESCE(v2_wins, 0) AS v2_wins,
                COALESCE(utility_damage, 0) AS utility_damage
            FROM match_player_stats
            WHERE match_id = ?
              AND map_number = ?
            ORDER BY
                COALESCE(team, '?') ASC,
                COALESCE(kills, 0) DESC,
                COALESCE(assists, 0) DESC,
                COALESCE(deaths, 0) ASC,
                COALESCE(name, steamid64) ASC
            """,
            (str(match_id), int(map_number)),
        ).fetchall()
