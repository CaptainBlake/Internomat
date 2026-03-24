from services import demo_cache
import services.logger as logger


def _norm(value):
    return str(value or "").strip().lower()


def _pick(row, candidates):
    for key in candidates:
        if key in row and row[key] is not None:
            return row[key]
    return None


def _is_switch_after_round(round_no, has_overtime):
    if round_no == 12:
        return True

    # In MR12 overtime, side switches every 3 rounds starting after round 27.
    if has_overtime and round_no >= 27 and (round_no - 27) % 3 == 0:
        return True

    return False


def _side_for_team1(round_no, initial_side, has_overtime):
    side = "CT" if _norm(initial_side) != "t" else "T"

    # Regulation half switch after 12 rounds.
    if round_no > 12:
        side = "T" if side == "CT" else "CT"

    # Overtime (MR12): first OT block is rounds 25-27 on same side as rounds 13-24.
    # Switches happen after rounds 27, 30, 33, ...
    if has_overtime and round_no > 27:
        toggles = (round_no - 28) // 3 + 1
        if toggles % 2 == 1:
            side = "T" if side == "CT" else "CT"

    return side


def _infer_initial_side_team1(rows, team1_name, team2_name):
    t1 = _norm(team1_name)
    t2 = _norm(team2_name)

    for row in rows:
        ct_name = _norm(
            _pick(
                row,
                ["ct_team_name", "ct_team", "team_ct", "team_ct_name", "ct_name"],
            )
        )
        t_name = _norm(
            _pick(
                row,
                ["t_team_name", "t_team", "team_t", "team_t_name", "t_name"],
            )
        )

        if ct_name == t1 or t_name == t2:
            return "CT"
        if ct_name == t2 or t_name == t1:
            return "T"

    return "CT"


def _extract_winner_side(row):
    # Prefer authoritative rounds.winner from awpy docs, then common aliases.
    raw = _pick(row, ["winner", "winner_side", "winning_side", "round_winner_side"])
    side = _norm(raw)
    if side in ("ct", "t"):
        return side, str(raw or "")
    return "", str(raw or "")


def build_round_timeline(summary):
    match_id = summary.get("match_id")
    map_number = summary.get("map_number")
    team1_name = str(summary.get("team1_name") or "")
    team2_name = str(summary.get("team2_name") or "")

    rows = demo_cache.load_round_rows(match_id, map_number)
    if not rows:
        return None

    initial_side_team1 = _infer_initial_side_team1(rows, team1_name, team2_name)
    has_overtime = len(rows) > 24

    timeline_rows = []
    for idx, row in enumerate(rows):
        round_no_raw = _pick(row, ["round_num", "round_number", "round", "number"])
        try:
            round_no = int(round_no_raw)
        except Exception:
            round_no = idx + 1

        side_team1 = _side_for_team1(round_no, initial_side_team1, has_overtime)
        side_team2 = "T" if side_team1 == "CT" else "CT"

        winner_side, winner_side_raw = _extract_winner_side(row)

        winner_team_name = _pick(
            row,
            ["winner_team_name", "winning_team_name", "winner_team", "winning_team"],
        )
        winner_team_name = str(winner_team_name) if winner_team_name is not None else None

        if not winner_team_name:
            if winner_side == "ct":
                winner_team_name = team1_name if side_team1 == "CT" else team2_name
            elif winner_side == "t":
                winner_team_name = team1_name if side_team1 == "T" else team2_name

        timeline_rows.append(
            {
                "round_no": round_no,
                "winner_side_raw": winner_side_raw,
                "winner_team_name": winner_team_name,
                "winner_side": winner_side.upper() if winner_side else "",
                "team1_side": side_team1,
                "team2_side": side_team2,
                "switch_after": _is_switch_after_round(round_no, has_overtime),
            }
        )

    # Debug output to inspect timeline winner/side resolution per round.
    logger.log_debug(
        f"[TIMELINE_DEBUG] match={match_id} map={map_number} "
        f"team1={team1_name or '?'} team2={team2_name or '?'} rounds={len(timeline_rows)}"
    )
    for entry in timeline_rows:
        logger.log_debug(
            "[TIMELINE_DEBUG] "
            f"R{entry['round_no']}: "
            f"{team1_name or '?'}={entry['team1_side']} "
            f"{team2_name or '?'}={entry['team2_side']} "
            f"winner={entry['winner_team_name'] or '?'} "
            f"winner_side={entry['winner_side'] or '?'} "
            f"winner_side_raw={entry.get('winner_side_raw') or '?'}"
        )

    return {
        "rounds": timeline_rows,
        "team1_name": team1_name,
        "team2_name": team2_name,
    }
