from services.settings import settings
import services.logger as logger

from .balancer import find_best_teams


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

    best_score, candidates, acceptable = find_best_teams(
        players,
        tolerance,
        settings.dist_weight
    )

    import random
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