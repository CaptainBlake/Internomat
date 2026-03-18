import random
import services.logger as logger
from itertools import combinations

# TEAM BALANCING

def _normalize_teams(team_a, team_b):
    a = tuple(sorted(p[0] for p in team_a))
    b = tuple(sorted(p[0] for p in team_b))
    return tuple(sorted([a, b]))

def _team_sum(team):
    return sum(p[2] for p in team)

def _team_sum(team):
    return sum(p[2] for p in team)

def _distribution_score_raw(team_a, team_b):
    a_sorted = sorted([p[2] for p in team_a], reverse=True)
    b_sorted = sorted([p[2] for p in team_b], reverse=True)
    return sum(abs(a - b) for a, b in zip(a_sorted, b_sorted))

def balance_teams(players, tolerance):

    if len(players) < 2:
        raise ValueError("Not enough players")

    if len(players) % 2 != 0:
        raise ValueError("Player count must be even")

    # prevent order bias
    players = players[:]
    random.shuffle(players)

    half = len(players) // 2

    best_score = None
    candidates = []
    seen = set()

    DIST_WEIGHT = 0.25  # tune this 

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

        # combined score
        score = diff + dist * DIST_WEIGHT

        if best_score is None or score < best_score:
            best_score = score

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
    logger.log_balance_summary(team_a, team_b)
    logger.log_team_roll_compact(
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

