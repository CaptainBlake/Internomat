import services.logger as logger

from .slot_mashine import choose_random_map as _choose_random_map


def choose_map(maps):

    if not maps:
        logger.log_error("Map selection failed: empty pool")
        raise ValueError("No maps in pool")

    choice = _choose_random_map(maps)

    logger.log_event("MAP_SELECTED", {
        "pool_size": len(maps),
        "selected": choice
    }, level="INFO")

    return choice