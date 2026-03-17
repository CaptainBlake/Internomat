import random

ITERATIONS = 1000
DEFAULT_RATING = 10000
# "balancer"
def balance_teams(players):

    best = None
    best_diff = float("inf")

    for _ in range(ITERATIONS):

        shuffled = players[:]
        random.shuffle(shuffled)

        half = len(players) // 2

        team_a = shuffled[:half]
        team_b = shuffled[half:]

        sum_a = sum(p[2] for p in team_a)
        sum_b = sum(p[2] for p in team_b)

        diff = abs(sum_a - sum_b)

        if diff < best_diff:

            best_diff = diff
            best = (team_a.copy(), team_b.copy())

    return best, best_diff

# MAP MANAGEMENT
def choose_random_map(maps):

    if not maps:
        raise ValueError("No maps in pool")

    return random.choice(maps)