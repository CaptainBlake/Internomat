import random


def choose_random_map(maps):
    if not maps:
        raise ValueError("No maps in pool")

    return random.choice(maps)