import random
from itertools import combinations



def normalize_teams(team_a, team_b):
    a = tuple(sorted(p[0] for p in team_a))
    b = tuple(sorted(p[0] for p in team_b))
    return tuple(sorted([a, b]))


def team_sum(team):
    return sum(p[2] for p in team)


def distribution_score(team_a, team_b):
    a_sorted = sorted([p[2] for p in team_a], reverse=True)
    b_sorted = sorted([p[2] for p in team_b], reverse=True)
    return sum(abs(a - b) for a, b in zip(a_sorted, b_sorted))


def find_best_teams(players, tolerance, dist_weight):
    players = players[:]
    random.shuffle(players)

    half = len(players) // 2

    best_score = None
    candidates = []
    seen = set()

    for combo in combinations(players, half):

        team_a = list(combo)
        team_a_ids = set(p[0] for p in team_a)
        team_b = [p for p in players if p[0] not in team_a_ids]

        key = normalize_teams(team_a, team_b)
        if key in seen:
            continue
        seen.add(key)

        sum_a = team_sum(team_a)
        sum_b = team_sum(team_b)

        diff = abs(sum_a - sum_b)
        dist = distribution_score(team_a, team_b)

        score = diff + dist * dist_weight

        if best_score is None or score < best_score:
            best_score = score

        candidates.append((score, team_a, team_b, diff, dist))

    if not candidates:
        raise Exception("No valid combinations")

    acceptable = [
        c for c in candidates
        if c[0] <= best_score + tolerance
    ]

    if not acceptable:
        acceptable = [min(candidates, key=lambda x: x[0])]

    return best_score, candidates, acceptable