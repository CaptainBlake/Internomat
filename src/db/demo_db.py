from .matches_db import get_all_matches_with_maps, get_match_map_steamids
from .connection_db import get_conn
import services.logger as logger
from datetime import datetime


def load_demo_match_catalog(conn=None):
    matches = get_all_matches_with_maps(conn=conn)

    catalog = {}

    for match in matches:
        match_id = str(match["match_id"])

        maps_by_name = {}
        for match_map in match.get("maps", []):
            map_name = match_map.get("map_name")
            map_number = match_map.get("map_number")

            if map_name is None or map_number is None:
                continue

            maps_by_name[str(map_name)] = int(map_number)

        catalog[match_id] = {
            "match_id": match_id,
            "team1": match.get("team1"),
            "team2": match.get("team2"),
            "maps_by_name": maps_by_name,
        }

    logger.log(f"[DB] Loaded demo catalog matches={len(catalog)}", level="DEBUG")

    return catalog


def resolve_map_number(catalog, match_id, map_name):
    match = catalog.get(str(match_id))
    if not match:
        logger.log(
            f"[DB] Resolve map_number miss match={match_id} map={map_name}",
            level="DEBUG",
        )
        return None

    map_number = match["maps_by_name"].get(map_name)

    if map_number is None:
        logger.log(
            f"[DB] Resolve map_number miss match={match_id} map={map_name}",
            level="DEBUG",
        )

    return map_number


def get_expected_demo_players(match_id, map_number, conn=None):
    players = get_match_map_steamids(
        match_id=match_id,
        map_number=map_number,
        conn=conn
    )

    logger.log(
        f"[DB] Loaded expected demo players match={match_id} map={map_number} count={len(players)}",
        level="DEBUG",
    )

    return players


def _norm_team_name(value):
    if value is None:
        return ""
    return str(value).strip().lower()


def _score_pair(a, b):
    try:
        aa = int(a)
        bb = int(b)
    except Exception:
        return None
    return tuple(sorted((aa, bb)))


def _parse_iso(value):
    if not value:
        return None

    txt = str(value).strip()
    if not txt:
        return None

    txt = txt.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(txt)
    except Exception:
        return None


def resolve_equivalent_match_map(
    map_name,
    played_at=None,
    team1_name=None,
    team2_name=None,
    team1_score=None,
    team2_score=None,
    parsed_players=None,
    include_non_positive=True,
    conn=None,
):
    own_conn = conn is None
    conn = conn or get_conn()

    parsed_team_set = {
        n for n in [_norm_team_name(team1_name), _norm_team_name(team2_name)] if n
    }
    parsed_score_pair = _score_pair(team1_score, team2_score)
    parsed_time = _parse_iso(played_at)
    parsed_players = set(parsed_players or [])

    best = None

    try:
        rows = conn.execute(
            """
            SELECT
                m.match_id,
                mm.map_number,
                mm.map_name,
                m.team1_name,
                m.team2_name,
                m.team1_score,
                m.team2_score,
                m.start_time,
                m.end_time
            FROM match_maps mm
            JOIN matches m ON m.match_id = mm.match_id
            WHERE mm.map_name = ?
            """,
            (str(map_name),),
        ).fetchall()

        for row in rows:
            try:
                candidate_match_id_int = int(str(row["match_id"]))
            except Exception:
                candidate_match_id_int = None

            if include_non_positive is False and (
                candidate_match_id_int is None or candidate_match_id_int <= 0
            ):
                continue

            candidate_team_set = {
                n
                for n in [
                    _norm_team_name(row["team1_name"]),
                    _norm_team_name(row["team2_name"]),
                ]
                if n
            }

            candidate_score_pair = _score_pair(row["team1_score"], row["team2_score"])
            candidate_start = _parse_iso(row["start_time"]) or _parse_iso(row["end_time"])

            score = 0
            reasons = []

            if parsed_team_set and candidate_team_set:
                overlap = len(parsed_team_set & candidate_team_set)
                if overlap == 2:
                    score += 6
                    reasons.append("team_exact")
                elif overlap == 1:
                    score += 2
                    reasons.append("team_partial")

            if parsed_score_pair and candidate_score_pair and parsed_score_pair == candidate_score_pair:
                score += 4
                reasons.append("score_pair")

            if parsed_time and candidate_start:
                diff_seconds = abs((parsed_time - candidate_start).total_seconds())
                if diff_seconds <= 15 * 60:
                    score += 5
                    reasons.append("time_15m")
                elif diff_seconds <= 60 * 60:
                    score += 3
                    reasons.append("time_60m")
                elif diff_seconds <= 6 * 60 * 60:
                    score += 1
                    reasons.append("time_6h")

            if parsed_players:
                existing_players = get_match_map_steamids(
                    match_id=row["match_id"],
                    map_number=row["map_number"],
                    conn=conn,
                )
                if existing_players:
                    if existing_players == parsed_players:
                        score += 8
                        reasons.append("players_exact")
                    else:
                        union = len(existing_players | parsed_players)
                        overlap = len(existing_players & parsed_players)
                        ratio = (overlap / union) if union else 0.0
                        if ratio >= 0.8:
                            score += 4
                            reasons.append("players_80")

            if score <= 0:
                continue

            candidate = {
                "match_id": str(row["match_id"]),
                "map_number": int(row["map_number"]),
                "score": int(score),
                "reasons": reasons,
            }

            if best is None or candidate["score"] > best["score"]:
                best = candidate

    finally:
        if own_conn:
            conn.close()

    # Require a minimum confidence to avoid accidental remapping.
    if not best or best["score"] < 6:
        return None

    logger.log(
        "[DB] Equivalent map resolved "
        f"match={best['match_id']} map={best['map_number']} score={best['score']} reasons={best['reasons']}",
        level="DEBUG",
    )
    return best
