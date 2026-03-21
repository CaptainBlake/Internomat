"""
file will be refactored into smaller modules which wil be in analytics / logic folder. 
For now, it serves as a core for main logic that is used by GUI
""" 

import random
from itertools import combinations

from services.settings import settings
import services.logger as logger
import services.crawler as crawler
import services.matchzy_db as matchzy

# UPDATE PIPELINE
def update_players_pipeline(
    steam_ids,
    on_progress=None,
    on_player=None,
    on_error=None,
    on_finish=None
):
    """
    Core update pipeline.
    UI should pass callbacks, NOT signals directly.

    Keeps logic centralized and UI-independent.
    """
    
    try:
        # --- MATCHZY SYNC ---
        try:
            logger.log("[UPDATE] Starting MatchZy sync", level="INFO")
            matchzy.sync()
        except Exception as e:
            if on_error:
                on_error(e)

        logger.log(f"[UPDATE] Players to update={len(steam_ids)}", level="INFO")

        if not steam_ids:
            if on_finish:
                on_finish()
            return
        
        total = len(steam_ids)
        seen = set()

        for i, steam_id in enumerate(steam_ids, start=1):

            # --- DUPLICATE GUARD ---
            if steam_id in seen:
                continue
            seen.add(steam_id)

            try:
                player = crawler.get_leetify_player(steam_id)

                if on_player:
                    on_player(player)

            except Exception as e:
                if on_error:
                    on_error(e)
                return

            if on_progress:
                on_progress(i, total)

        if on_finish:
            on_finish()

    except Exception as e:
        if on_error:
            on_error(e)

    finally:
        # --- ALWAYS CLEANUP ---
        logger.log("[UPDATE] Cleaning up crawler", level="DEBUG")
        crawler.close_driver()


# TEAM BALANCING

def _normalize_teams(team_a, team_b):
    a = tuple(sorted(p[0] for p in team_a))
    b = tuple(sorted(p[0] for p in team_b))
    return tuple(sorted([a, b]))


def _team_sum(team):
    return sum(p[2] for p in team)


def _distribution_score_raw(team_a, team_b):
    a_sorted = sorted([p[2] for p in team_a], reverse=True)
    b_sorted = sorted([p[2] for p in team_b], reverse=True)
    return sum(abs(a - b) for a, b in zip(a_sorted, b_sorted))


def balance_teams(players, tolerance):

    logger.log_event("BALANCE_START", {
        "player_count": len(players),
        "tolerance": tolerance
    }, level="INFO")

    if len(players) < 2:
        logger.log_error("Balance failed: not enough players")
        raise ValueError("Not enough players")

    if len(players) % 2 != 0:
        if not settings.allow_uneven_teams:
            logger.log_error("Balance failed: uneven player count")
            raise ValueError("Player count must be even")

        logger.log("[BALANCE] Uneven player count allowed", level="INFO")

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

        key = _normalize_teams(team_a, team_b)
        if key in seen:
            continue
        seen.add(key)

        sum_a = _team_sum(team_a)
        sum_b = _team_sum(team_b)

        diff = abs(sum_a - sum_b)
        dist = _distribution_score_raw(team_a, team_b)

        score = diff + dist * settings.dist_weight

        if best_score is None or score < best_score:
            best_score = score

        candidates.append((score, team_a, team_b, diff, dist))

    if not candidates:
        logger.log_error("Balance failed: no valid combinations")
        raise Exception("No valid combinations")

    acceptable = [
        c for c in candidates
        if c[0] <= best_score + tolerance
    ]

    if not acceptable:
        acceptable = [min(candidates, key=lambda x: x[0])]

    chosen = random.choice(acceptable)

    score, team_a, team_b, diff, dist = chosen

    logger.log_event("BALANCE_RESULT", {
        "best_score": best_score,
        "chosen_score": score,
        "diff": diff,
        "candidate_count": len(candidates),
        "acceptable_count": len(acceptable)
    }, level="INFO")

    logger.log_balance_summary(team_a, team_b)

    return (team_a, team_b), diff

# MAP MANAGEMENT

def choose_random_map(maps):

    if not maps:
        logger.log_error("Map selection failed: empty pool")
        raise ValueError("No maps in pool")

    choice = random.choice(maps)

    logger.log_event("MAP_SELECTED", {
        "pool_size": len(maps),
        "selected": choice
    }, level="INFO")

    return choice