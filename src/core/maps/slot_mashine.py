import random


def choose_random_map(maps):
    if not maps:
        raise ValueError("No maps in pool")

    return random.choice(maps)


def choose_weighted_map(maps, weights_by_map):
    if not maps:
        raise ValueError("No maps in pool")

    weights = [float(weights_by_map.get(m, 0.0)) for m in maps]
    total_weight = sum(weights)

    if total_weight <= 0:
        return choose_random_map(maps)

    return random.choices(maps, weights=weights, k=1)[0]
