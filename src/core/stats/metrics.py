"""Shared metric formulas — single source of truth for KDR, ADR, HS%, accuracy, etc."""


def kd_ratio(kills, deaths):
    if deaths <= 0:
        return float(kills)
    return kills / deaths


def adr(damage, rounds):
    if not rounds or rounds <= 0:
        return None
    return float(damage) / float(rounds)


def hs_pct(headshot_kills, kills):
    if kills <= 0:
        return 0.0
    return 100.0 * float(headshot_kills) / float(kills)


def accuracy_pct(shots_hit, shots_fired):
    if shots_fired <= 0:
        return 0.0
    return 100.0 * float(shots_hit) / float(shots_fired)


def win_rate(wins, played):
    if played <= 0:
        return 0.0
    return 100.0 * float(wins) / float(played)


def success_pct(successes, attempts):
    if attempts <= 0:
        return 0.0
    return 100.0 * float(successes) / float(attempts)


def performance_index(kills, assists, deaths):
    if deaths <= 0:
        return float(kills + 0.5 * assists)
    return (kills + 0.5 * assists) / float(deaths)


def safe_avg(total, count):
    if count <= 0:
        return 0.0
    return float(total) / float(count)
