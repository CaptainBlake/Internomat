import random
from itertools import combinations


def _normalize_teams(team_a, team_b):
    a = tuple(sorted(p[0] for p in team_a))
    b = tuple(sorted(p[0] for p in team_b))
    return tuple(sorted([a, b]))


def _team_sum(team):
    return sum(p[2] for p in team)


def balance_teams(players, tolerance):

    if len(players) < 2:
        raise ValueError("Not enough players")

    if len(players) % 2 != 0:
        raise ValueError("Player count must be even")

    # 🔑 prevent order bias
    players = players[:]
    random.shuffle(players)

    half = len(players) // 2

    best_score = None
    best_diff = None  # keep for logging
    candidates = []
    seen = set()

    DIST_WEIGHT = 0.25  # 🔥 tune this (0.05–0.2 recommended)

    # --- generate all unique team splits ---
    for combo in combinations(players, half):

        team_a = list(combo)

        team_a_ids = set(p[0] for p in team_a)
        team_b = [p for p in players if p[0] not in team_a_ids]

        key = _normalize_teams(team_a, team_b)
        if key in seen:
            continue
        seen.add(key)

        sum_a = _team_sum(team_a)
        sum_b = _team_sum(team_b)

        diff = abs(sum_a - sum_b)
        dist = _distribution_score_raw(team_a, team_b)

        # 🔥 NEW: combined score
        score = diff + dist * DIST_WEIGHT

        if best_score is None or score < best_score:
            best_score = score
            best_diff = diff  # track pure diff of best

        candidates.append((score, team_a, team_b, diff, dist))

    if not candidates:
        raise Exception("No valid combinations")

    # --- filter by tolerance (now based on score!) ---
    acceptable = [
        c for c in candidates
        if c[0] <= best_score + tolerance
    ]

    if not acceptable:
        acceptable = [min(candidates, key=lambda x: x[0])]

    # --- random pick among acceptable ---
    chosen = random.choice(acceptable)

    # unpack
    score, team_a, team_b, diff, dist = chosen

    # --- logging ---
    log_team_roll_compact(
        chosen=(score, team_a, team_b),
        team_a=team_a,
        team_b=team_b,
        tolerance=tolerance,
        best_score=best_score,
        candidate_count=len(candidates),
        acceptable_count=len(acceptable),
        diverse_count=len(acceptable)
    )

    return (team_a, team_b), diff  # keep returning pure diff for UI

# MAP MANAGEMENT
def choose_random_map(maps):

    if not maps:
        raise ValueError("No maps in pool")

    return random.choice(maps)

# debug helpers

def _format_team(team):
    # sort by rating desc for readability
    sorted_team = sorted(team, key=lambda p: p[2], reverse=True)
    return [(p[1], p[2]) for p in sorted_team]

def _team_sum(team):
    return sum(p[2] for p in team)

def _distribution_score_raw(team_a, team_b):
    a_sorted = sorted([p[2] for p in team_a], reverse=True)
    b_sorted = sorted([p[2] for p in team_b], reverse=True)
    return sum(abs(a - b) for a, b in zip(a_sorted, b_sorted))

# Loggers
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
    sum_a = _team_sum(team_a)
    sum_b = _team_sum(team_b)

    total_diff = abs(sum_a - sum_b)
    dist_diff = _distribution_score_raw(team_a, team_b)

    print("\n=== TEAM ROLL ===")
    print(f"Score: {chosen[0]:.2f} (best: {best_score:.2f})")
    print(f"Total diff: {total_diff}")
    print(f"Distribution diff: {dist_diff}")
    print(f"Sum A: {sum_a} | Sum B: {sum_b}")

    print("\nParameters:")
    print(f"  Tolerance: {tolerance}")

    print("\nSearch space:")
    print(f"  Candidates: {candidate_count}")
    print(f"  Acceptable: {acceptable_count}")
    print(f"  Diverse pool: {diverse_count}")

    print("\nTeam A:")
    for name, rating in _format_team(team_a):
        print(f"  {name:<20} {rating}")

    print("\nTeam B:")
    for name, rating in _format_team(team_b):
        print(f"  {name:<20} {rating}")

    print("=================\n")

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
    def short_team(team):
        ratings = sorted([p[2] for p in team], reverse=True)
        return ",".join(str(r // 1000) + "k" for r in ratings[:3])

    sum_a = _team_sum(team_a)
    sum_b = _team_sum(team_b)

    total_diff = abs(sum_a - sum_b)
    dist_diff = _distribution_score_raw(team_a, team_b)

    top_a = sum(sorted([p[2] for p in team_a], reverse=True)[:2])
    top_b = sum(sorted([p[2] for p in team_b], reverse=True)[:2])
    top_diff = abs(top_a - top_b)

    print(
        f"[S:{chosen[0]:.0f}/{best_score:.0f} "
        f"| Δ:{total_diff} "
        f"| D:{dist_diff} "
        f"| TopΔ:{top_diff} "
        f"| C:{candidate_count} A:{acceptable_count} Dv:{diverse_count} "
        f"| A:{sum_a//1000}k B:{sum_b//1000}k] "
        f"A[{short_team(team_a)}] vs B[{short_team(team_b)}]"
    )