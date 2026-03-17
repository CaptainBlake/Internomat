from core import _distribution_score_raw

# --- config ---

LOG_ENABLED = True
LOG_LEVEL = "DEBUG"  # DEBUG, INFO, OFF

LOG_HISTORY = []  # optional: can be used by GUI later
MAX_HISTORY = 200

# --- core helpers ---

def _should_log(level):
    if not LOG_ENABLED or LOG_LEVEL == "OFF":
        return False

    if LOG_LEVEL == "DEBUG":
        return True

    if LOG_LEVEL == "INFO":
        return level != "DEBUG"

    return True

def _store_log(entry):
    LOG_HISTORY.append(entry)
    if len(LOG_HISTORY) > MAX_HISTORY:
        LOG_HISTORY.pop(0)

def get_log_history():
    return LOG_HISTORY

def clear_log_history():
    LOG_HISTORY.clear()

# --- team analysis ---

def _team_sum(team):
    return sum(p[2] for p in team)

def _format_team(team):
    sorted_team = sorted(team, key=lambda p: p[2], reverse=True)
    return [(p[1], p[2]) for p in sorted_team]

def _top_diff(team_a, team_b):
    top_a = sum(sorted([p[2] for p in team_a], reverse=True)[:2])
    top_b = sum(sorted([p[2] for p in team_b], reverse=True)[:2])
    return abs(top_a - top_b)

# --- generic log ---

def log(message, level="INFO"):
    if not _should_log(level):
        return

    print(message, flush=True)
    _store_log(message)

# --- structured event logging ---

def log_event(name, data=None, level="DEBUG"):
    if not _should_log(level):
        return

    entry = f"[{name}] {data}" if data else f"[{name}]"
    print(entry, flush=True)
    _store_log(entry)

# --- team logging ---

def log_team_roll(
    chosen,
    team_a,
    team_b,
    tolerance,
    best_score,
    candidate_count,
    acceptable_count,
    diverse_count
):
    if not _should_log("DEBUG"):
        return

    sum_a = _team_sum(team_a)
    sum_b = _team_sum(team_b)

    total_diff = abs(sum_a - sum_b)
    dist_diff = _distribution_score_raw(team_a, team_b)

    lines = []
    lines.append("\n=== TEAM ROLL ===")
    lines.append(f"Score: {chosen[0]:.2f} (best: {best_score:.2f})")
    lines.append(f"Total diff: {total_diff}")
    lines.append(f"Distribution diff: {dist_diff}")
    lines.append(f"Sum A: {sum_a} | Sum B: {sum_b}")

    lines.append("\nParameters:")
    lines.append(f"  Tolerance: {tolerance}")

    lines.append("\nSearch space:")
    lines.append(f"  Candidates: {candidate_count}")
    lines.append(f"  Acceptable: {acceptable_count}")
    lines.append(f"  Diverse pool: {diverse_count}")

    lines.append("\nTeam A:")
    for name, rating in _format_team(team_a):
        lines.append(f"  {name:<20} {rating}")

    lines.append("\nTeam B:")
    for name, rating in _format_team(team_b):
        lines.append(f"  {name:<20} {rating}")

    lines.append("=================\n")

    output = "\n".join(lines)
    print(output, flush=True)
    _store_log(output)

def log_team_roll_compact(
    chosen,
    team_a,
    team_b,
    tolerance,
    best_score,
    candidate_count,
    acceptable_count,
    diverse_count
):
    if not _should_log("INFO"):
        return

    def short_team(team):
        ratings = sorted([p[2] for p in team], reverse=True)
        return ",".join(str(r // 1000) + "k" for r in ratings[:3])

    sum_a = _team_sum(team_a)
    sum_b = _team_sum(team_b)

    total_diff = abs(sum_a - sum_b)
    dist_diff = _distribution_score_raw(team_a, team_b)
    top_diff = _top_diff(team_a, team_b)

    line = (
        f"[S:{chosen[0]:.0f}/{best_score:.0f} "
        f"| Δ:{total_diff} "
        f"| D:{dist_diff} "
        f"| T:{tolerance} "
        f"| TopΔ:{top_diff} "
        f"| C:{candidate_count} A:{acceptable_count} Dv:{diverse_count} "
        f"| A:{sum_a//1000}k B:{sum_b//1000}k] "
        f"A[{short_team(team_a)}] vs B[{short_team(team_b)}]"
    )

    print(line, flush=True)
    _store_log(line)

# --- quick insights ---

def log_balance_summary(team_a, team_b):
    sum_a = _team_sum(team_a)
    sum_b = _team_sum(team_b)

    total_diff = abs(sum_a - sum_b)
    dist_diff = _distribution_score_raw(team_a, team_b)
    top_diff = _top_diff(team_a, team_b)

    log_event(
        "BALANCE_SUMMARY",
        {
            "total_diff": total_diff,
            "distribution": dist_diff,
            "top_diff": top_diff
        },
        level="INFO"
    )

def log_warning(message):
    log(f"[WARNING] {message}", level="INFO")

def log_error(message):
    log(f"[ERROR] {message}", level="INFO")