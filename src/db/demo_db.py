from .matches_db import get_all_matches_with_maps, get_match_map_steamids
from .connection_db import execute_write, get_conn, optional_conn
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
    parsed_team_set = {
        n for n in [_norm_team_name(team1_name), _norm_team_name(team2_name)] if n
    }
    parsed_score_pair = _score_pair(team1_score, team2_score)
    parsed_time = _parse_iso(played_at)
    parsed_players = set(parsed_players or [])

    best = None

    with optional_conn(conn) as c:
        rows = c.execute(
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

        # Pre-fetch all steamids in one query to avoid N+1 per-row lookups
        players_by_key: dict[tuple, set] = {}
        if parsed_players and rows:
            match_ids = list({str(r["match_id"]) for r in rows})
            placeholders = ",".join("?" for _ in match_ids)
            sid_rows = c.execute(
                f"""
                SELECT match_id, map_number, steamid64
                FROM match_player_stats
                WHERE match_id IN ({placeholders})
                  AND steamid64 IS NOT NULL AND steamid64 != ''
                """,
                tuple(match_ids),
            ).fetchall()
            for sr in sid_rows:
                key = (str(sr["match_id"]), int(sr["map_number"]))
                players_by_key.setdefault(key, set()).add(str(sr["steamid64"]))

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
                existing_players = players_by_key.get(
                    (str(row["match_id"]), int(row["map_number"])), set()
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

    # Require both minimum score and at least one strong corroborating signal.
    # Team-name overlap alone is too weak and caused accidental cross-era merges.
    strong_reasons = {"players_exact", "players_80", "score_pair", "time_15m", "time_60m"}
    best_reasons = set(best.get("reasons") or []) if best else set()
    has_strong_signal = bool(best_reasons & strong_reasons)

    if not best or best["score"] < 6 or not has_strong_signal:
        if best and best["score"] >= 6 and not has_strong_signal:
            logger.log(
                "[DB] Equivalent map rejected (weak evidence) "
                f"match={best['match_id']} map={best['map_number']} score={best['score']} reasons={best['reasons']}",
                level="DEBUG",
            )
        return None

    logger.log(
        "[DB] Equivalent map resolved "
        f"match={best['match_id']} map={best['map_number']} score={best['score']} reasons={best['reasons']}",
        level="DEBUG",
    )
    return best


def is_restore_signature_current(source_match_id, source_map_number, payload_sha256, conn=None):
    if not str(payload_sha256 or "").strip():
        return False

    with optional_conn(conn) as c:
        row = c.execute(
            """
            SELECT payload_sha256
            FROM cache_restore_state
            WHERE source_match_id = ?
              AND source_map_number = ?
            LIMIT 1
            """,
            (str(source_match_id), int(source_map_number)),
        ).fetchone()

    return row is not None and str(row["payload_sha256"] or "") == str(payload_sha256)


def upsert_restore_signature(
    source_match_id,
    source_map_number,
    payload_sha256,
    canonical_match_id=None,
    canonical_map_number=None,
    source_file=None,
    conn=None,
):
    if not str(payload_sha256 or "").strip():
        return

    with optional_conn(conn, commit=True) as c:
        execute_write(
            c,
            """
            INSERT INTO cache_restore_state (
                source_match_id,
                source_map_number,
                payload_sha256,
                canonical_match_id,
                canonical_map_number,
                source_file,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(source_match_id, source_map_number) DO UPDATE SET
                payload_sha256 = excluded.payload_sha256,
                canonical_match_id = excluded.canonical_match_id,
                canonical_map_number = excluded.canonical_map_number,
                source_file = excluded.source_file,
                updated_at = datetime('now')
            """,
            (
                str(source_match_id),
                int(source_map_number),
                str(payload_sha256),
                str(canonical_match_id) if canonical_match_id is not None else None,
                int(canonical_map_number) if canonical_map_number is not None else None,
                str(source_file) if source_file is not None else None,
            ),
        )


def get_all_restore_canonical_match_ids(conn=None):
    with optional_conn(conn) as c:
        rows = c.execute(
            """
            SELECT DISTINCT canonical_match_id
            FROM cache_restore_state
            WHERE canonical_match_id IS NOT NULL
              AND TRIM(CAST(canonical_match_id AS TEXT)) != ''
            """
        ).fetchall()

    return {
        str(row["canonical_match_id"]).strip()
        for row in rows
        if row is not None and str(row["canonical_match_id"] or "").strip()
    }
