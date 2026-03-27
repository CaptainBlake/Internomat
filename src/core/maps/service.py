import services.logger as logger
import db.matches_db as matches_db

from .slot_mashine import choose_random_map as _choose_random_map
from .slot_mashine import choose_weighted_map as _choose_weighted_map


def _build_history_weights(maps):
    total_matches = matches_db.get_total_matches_count()
    if total_matches <= 0:
        return {}

    map_play_counts = matches_db.get_map_play_counts()
    min_weight = 0.01

    return {
        # More frequently played maps get lower chance: weight = 1 - played_ratio.
        m: max(min_weight, 1.0 - (map_play_counts.get(m, 0) / total_matches))
        for m in maps
    }


def _pct(value):
    return f"{(float(value) * 100.0):6.2f}%"


def _log_chance_table(maps, choice, use_history, history_weights):
    if not use_history:
        chance = 1.0 / len(maps)
        name_w = max(12, max(len(str(m)) for m in maps))
        lines = [
            f"[MAP_CHANCE_TABLE] mode=uniform pool_size={len(maps)}",
            f"{'map':<{name_w}}  {'chance':>10}",
            f"{'-' * name_w}  {'-' * 10}",
        ]

        for m in maps:
            marker = "*" if m == choice else " "
            lines.append(f"{marker}{str(m):<{name_w}}  {_pct(chance):>10}")

        lines.append(f"selected={choice} chance={_pct(chance)}")
        logger.log_lines(lines, level="DEBUG")
        return {
            "played_ratio": 0.0,
            "raw_weight": 1.0,
            "pick_chance": chance,
        }

    total_matches = matches_db.get_total_matches_count()
    map_play_counts = matches_db.get_map_play_counts()

    total_weight = sum(float(history_weights.get(m, 0.0)) for m in maps)
    if total_weight <= 0:
        total_weight = float(len(maps))

    rows = []
    for m in maps:
        played_count = int(map_play_counts.get(m, 0))
        played_ratio = (played_count / total_matches) if total_matches > 0 else 0.0
        raw_weight = float(history_weights.get(m, 0.0))
        pick_chance = raw_weight / total_weight

        rows.append({
            "map": m,
            "played_count": played_count,
            "played_ratio": round(played_ratio, 6),
            "raw_weight": round(raw_weight, 6),
            "pick_chance": round(pick_chance, 6),
        })

    selected_entry = next((row for row in rows if row["map"] == choice), None)
    sorted_rows = sorted(rows, key=lambda r: r["pick_chance"], reverse=True)
    name_w = max(12, max(len(str(row["map"])) for row in sorted_rows))

    lines = [
        (
            "[MAP_CHANCE_TABLE] "
            f"mode=history_inverse pool_size={len(maps)} total_matches={int(total_matches)}"
        ),
        (
            f"{'map':<{name_w}}  {'played':>6}  {'ratio':>8}  {'weight':>8}  {'chance':>10}"
        ),
        f"{'-' * name_w}  {'-' * 6}  {'-' * 8}  {'-' * 8}  {'-' * 10}",
    ]

    for row in sorted_rows:
        marker = "*" if row["map"] == choice else " "
        lines.append(
            (
                f"{marker}{str(row['map']):<{name_w}}"
                f"  {int(row['played_count']):>6}"
                f"  {_pct(row['played_ratio']):>8}"
                f"  {float(row['raw_weight']):>8.4f}"
                f"  {_pct(row['pick_chance']):>10}"
            )
        )

    if selected_entry:
        lines.append(
            (
                f"selected={choice}"
                f" chance={_pct(selected_entry['pick_chance'])}"
                f" weight={float(selected_entry['raw_weight']):.4f}"
                f" played_ratio={_pct(selected_entry['played_ratio'])}"
            )
        )

    logger.log_lines(lines, level="DEBUG")
    return selected_entry


def choose_map(maps, use_history=False):

    if not maps:
        logger.log_error("Map selection failed: empty pool")
        raise ValueError("No maps in pool")

    history_weights = {}
    if use_history:
        history_weights = _build_history_weights(maps)

    choice = _choose_weighted_map(maps, history_weights) if use_history else _choose_random_map(maps)

    selected_entry = _log_chance_table(maps, choice, use_history, history_weights)

    if selected_entry:
        logger.log(
            (
                "[MAP_SELECTED] "
                f"selected={choice} pool_size={len(maps)} mode={'history_inverse' if use_history else 'uniform'} "
                f"chance={_pct(selected_entry['pick_chance'])} "
                f"weight={float(selected_entry['raw_weight']):.4f} "
                f"played_ratio={_pct(selected_entry['played_ratio'])}"
            ),
            level="INFO",
        )
    else:
        logger.log(
            (
                "[MAP_SELECTED] "
                f"selected={choice} pool_size={len(maps)} mode={'history_inverse' if use_history else 'uniform'}"
            ),
            level="INFO",
        )

    return choice
