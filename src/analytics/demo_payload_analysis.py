import math
from bisect import bisect_right

import pandas as pd
import polars as pl
from db.weapon_catalog import normalize_weapon_name
import services.logger as logger


KILL_REWARD_BY_WEAPON_TOKEN = {
    "knife": 1500,
    "taser": 0,
    "zeus": 0,
    "awp": 100,
    "ssg08": 300,
    "g3sg1": 300,
    "scar20": 300,
    "xm1014": 900,
    "nova": 900,
    "mag7": 900,
    "sawedoff": 900,
    "mac10": 600,
    "mp9": 600,
    "mp7": 600,
    "ump45": 600,
    "bizon": 600,
    "p90": 300,
}


ITEM_COST_HINTS = {
    "vest": 650,
    "vesthelm": 1000,
    "defuser": 400,
    "flashbang": 200,
    "hegrenade": 300,
    "smokegrenade": 300,
    "incgrenade": 600,
    "molotov": 400,
    "decoy": 50,
    "awp": 4750,
    "ssg08": 1700,
    "scar20": 5000,
    "g3sg1": 5000,
    "ak47": 2700,
    "m4a1": 3100,
    "m4a1_silencer": 2900,
    "famas": 2050,
    "galilar": 1800,
    "aug": 3300,
    "sg556": 3000,
    "mp9": 1250,
    "mac10": 1050,
    "mp7": 1500,
    "ump45": 1200,
    "bizon": 1400,
    "p90": 2350,
    "nova": 1050,
    "mag7": 1300,
    "sawedoff": 1100,
    "xm1014": 2000,
    "deagle": 700,
    "elite": 300,
    "fiveseven": 500,
    "glock": 200,
    "hkp2000": 200,
    "p250": 300,
    "tec9": 500,
    "usp_silencer": 200,
}


def iter_rows(table):
    if isinstance(table, pd.DataFrame):
        if table.empty:
            return []
        return table.to_dict("records")

    if isinstance(table, pl.DataFrame):
        if table.height == 0:
            return []
        return table.to_dicts()

    if isinstance(table, list):
        return [r for r in table if isinstance(r, dict)]

    return []


def pick_value(row, keys):
    row = row or {}
    for key in keys:
        if key not in row:
            continue
        value = row.get(key)
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def to_int(value, default=0):
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return default
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return default
        return int(float(value))
    except Exception:
        return default


def normalize_side_label(value):
    if value is None:
        return None

    txt = str(value).strip().upper()
    if not txt:
        return None

    if txt in {"CT", "CT_SIDE"} or "COUNTER" in txt:
        return "CT"
    if txt in {"T", "T_SIDE"} or "TERROR" in txt:
        return "T"
    return None


def to_steamid64_string(value):
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    try:
        if isinstance(value, int):
            number = value
        elif isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return None
            number = int(value)
        else:
            text = str(value).strip()
            if not text or text.lower() in {"nan", "none"}:
                return None

            if text.endswith(".0"):
                text = text[:-2]

            if not text.isdigit():
                return None

            number = int(text)
    except Exception:
        return None

    if number < 10_000_000_000_000_000:
        return None

    return str(number)


def round_winner_side_map(parsed_payload):
    winner_by_round = {}
    rounds_rows = iter_rows((parsed_payload or {}).get("rounds"))
    if not rounds_rows:
        rounds_rows = iter_rows((parsed_payload or {}).get("rounds_stats"))

    for row in rounds_rows:
        round_num = to_int(
            pick_value(row, ["round_num", "round", "round_number"]),
            default=0,
        )
        winner_raw = pick_value(
            row,
            ["winner_side", "winner", "round_winner", "winning_side"],
        )
        winner_side = normalize_side_label(winner_raw)
        if round_num > 0 and winner_side:
            winner_by_round[round_num] = winner_side

    return winner_by_round


def build_derived_round_timeline(parsed_payload):
    rows = iter_rows((parsed_payload or {}).get("rounds"))
    if not rows:
        rows = iter_rows((parsed_payload or {}).get("rounds_stats"))

    if not rows:
        return []

    timeline_rows = []
    for idx, row in enumerate(rows, start=1):
        round_num = to_int(
            pick_value(row, ["round_num", "round", "round_number"]),
            default=idx,
        )
        winner_side = normalize_side_label(
            pick_value(row, ["winner_side", "winner", "round_winner", "winning_side"])
        )
        winner_team_name = pick_value(
            row,
            ["winner_team_name", "winning_team_name", "winner_team", "winning_team"],
        )

        timeline_rows.append(
            {
                "round_no": int(round_num),
                "winner_side": str(winner_side or ""),
                "winner_team_name": str(winner_team_name) if winner_team_name is not None else None,
            }
        )

    timeline_rows.sort(key=lambda r: int(r.get("round_no") or 0))
    return timeline_rows


def build_derived_player_stats(parsed_payload):
    payload = parsed_payload or {}
    kills_rows = iter_rows(payload.get("kills"))
    if not kills_rows:
        return {}

    winner_by_round = round_winner_side_map(payload)
    by_round = {}

    for index, row in enumerate(kills_rows):
        round_num = to_int(
            pick_value(row, ["round_num", "round", "round_number"]),
            default=0,
        )
        if round_num <= 0:
            continue

        tick = to_int(
            pick_value(row, ["tick", "game_tick", "event_tick"]),
            default=(index + 1) * 100,
        )
        attacker = to_steamid64_string(
            pick_value(row, ["attacker_steamid", "attacker_steamid64", "attacker"])
        )
        victim = to_steamid64_string(
            pick_value(row, ["victim_steamid", "victim_steamid64", "victim"])
        )
        attacker_side = normalize_side_label(
            pick_value(row, ["attacker_side", "attacker_team", "attacker_team_name"])
        )
        victim_side = normalize_side_label(
            pick_value(row, ["victim_side", "victim_team", "victim_team_name"])
        )

        if round_num not in by_round:
            by_round[round_num] = {
                "kills": [],
                "alive": {"CT": set(), "T": set()},
            }

        if attacker and attacker_side in {"CT", "T"}:
            by_round[round_num]["alive"][attacker_side].add(attacker)
        if victim and victim_side in {"CT", "T"}:
            by_round[round_num]["alive"][victim_side].add(victim)

        by_round[round_num]["kills"].append(
            {
                "tick": tick,
                "attacker": attacker,
                "victim": victim,
                "attacker_side": attacker_side,
                "victim_side": victim_side,
            }
        )

    if not by_round:
        return {}

    derived = {}

    def ensure_player(steamid64):
        if not steamid64:
            return None
        if steamid64 not in derived:
            derived[steamid64] = {
                "entry_count": 0,
                "entry_wins": 0,
                "v1_count": 0,
                "v1_wins": 0,
                "v2_count": 0,
                "v2_wins": 0,
            }
        return derived[steamid64]

    for round_num, round_state in by_round.items():
        kills = sorted(round_state["kills"], key=lambda k: int(k.get("tick") or 0))
        if not kills:
            continue

        first_entry = None
        for kill in kills:
            if not kill.get("attacker") or not kill.get("victim"):
                continue
            if kill.get("attacker_side") and kill.get("victim_side") and kill.get("attacker_side") == kill.get("victim_side"):
                continue
            first_entry = kill
            break

        if first_entry:
            item = ensure_player(first_entry.get("attacker"))
            if item is not None:
                item["entry_count"] += 1
                if winner_by_round.get(round_num) == first_entry.get("attacker_side"):
                    item["entry_wins"] += 1

        alive_ct = set(round_state["alive"]["CT"])
        alive_t = set(round_state["alive"]["T"])
        first_attempt = {}

        for kill in kills:
            victim = kill.get("victim")
            victim_side = kill.get("victim_side")

            if victim and victim_side == "CT":
                alive_ct.discard(victim)
            elif victim and victim_side == "T":
                alive_t.discard(victim)

            if len(alive_ct) == 1 and len(alive_t) >= 1:
                sid = next(iter(alive_ct))
                first_attempt.setdefault((sid, "CT"), len(alive_t))
            if len(alive_t) == 1 and len(alive_ct) >= 1:
                sid = next(iter(alive_t))
                first_attempt.setdefault((sid, "T"), len(alive_ct))

        for (sid, side), enemy_count in first_attempt.items():
            item = ensure_player(sid)
            if item is None:
                continue

            if enemy_count <= 1:
                item["v1_count"] += 1
                if winner_by_round.get(round_num) == side:
                    item["v1_wins"] += 1
            elif enemy_count == 2:
                item["v2_count"] += 1
                if winner_by_round.get(round_num) == side:
                    item["v2_wins"] += 1

    return derived


def _default_restore_stats_row():
    return {
        "equipment_value": 0,
        "money_saved": 0,
        "kill_reward": 0,
        "cash_earned": 0,
        "live_time": 0,
        "enemies_flashed": 0,
    }


def _ensure_restore_player(store, steamid64):
    if not steamid64:
        return None
    if steamid64 not in store:
        store[steamid64] = _default_restore_stats_row()
    return store[steamid64]


def _weapon_reward_hint(weapon_value):
    text = str(weapon_value or "").strip().lower()
    if not text:
        return 300

    for token, reward in KILL_REWARD_BY_WEAPON_TOKEN.items():
        if token in text:
            return int(reward)
    return 300


def _item_cost_hint(item_name):
    text = str(item_name or "").strip().lower()
    if not text:
        return 0
    return int(ITEM_COST_HINTS.get(text, 0))


def _build_round_windows(payload):
    rounds_rows = iter_rows((payload or {}).get("rounds"))
    if not rounds_rows:
        rounds_rows = iter_rows((payload or {}).get("rounds_stats"))

    windows = []
    for index, row in enumerate(rounds_rows, start=1):
        round_num = to_int(pick_value(row, ["round_num", "round", "round_number"]), default=index)
        start_tick = to_int(pick_value(row, ["start", "start_tick", "freeze_start", "round_start_tick"]), default=0)
        freeze_end = to_int(pick_value(row, ["freeze_end", "freeze_end_tick"]), default=start_tick)
        end_tick = to_int(pick_value(row, ["end", "official_end", "end_tick", "round_end_tick"]), default=0)
        if round_num <= 0:
            continue
        windows.append((round_num, start_tick, freeze_end, end_tick if end_tick > 0 else None))

    windows.sort(key=lambda x: (x[1], x[0]))
    return windows


def _round_for_tick(tick, windows):
    if tick <= 0 or not windows:
        return None

    starts = [w[1] for w in windows]
    pos = bisect_right(starts, tick) - 1
    if pos < 0:
        return None

    round_num, start_tick, freeze_end, end_tick = windows[pos]
    if end_tick is not None and tick > end_tick:
        if pos + 1 < len(windows):
            next_round, next_start, _, _ = windows[pos + 1]
            if tick >= next_start:
                return int(next_round)
        return None

    return int(round_num)


def _calc_live_time_seconds(payload, derived):
    for row in iter_rows((payload or {}).get("ticks")):
        sid = to_steamid64_string(pick_value(row, ["steamid", "steamid64", "player_steamid"]))
        if not sid:
            continue

        health = to_int(pick_value(row, ["health", "hp"]), default=0)
        if health <= 0:
            continue

        item = _ensure_restore_player(derived, sid)
        if item is None:
            continue

        item["live_time"] += 1

    for sid, item in derived.items():
        item["live_time"] = int(item.get("live_time", 0) / 128)


def _calc_enemies_flashed(payload, derived):
    entity_thrower = {}
    for row in iter_rows((payload or {}).get("grenades")):
        grenade_type = str(pick_value(row, ["grenade_type", "type"]) or "").lower()
        if "flash" not in grenade_type:
            continue
        entity_id = pick_value(row, ["entity_id", "entityid", "grenade_entity", "id"])
        thrower = to_steamid64_string(pick_value(row, ["thrower_steamid", "thrower_steamid64", "thrower"]))
        if entity_id is None or not thrower:
            continue
        entity_thrower[str(entity_id)] = thrower

    events = (payload or {}).get("events")
    if not isinstance(events, dict):
        return

    for row in iter_rows(events.get("flashbang_detonate")):
        entity_id = pick_value(row, ["entityid", "entity_id", "entity"])
        victim = to_steamid64_string(pick_value(row, ["user_steamid", "player_steamid", "steamid"]))
        if entity_id is None:
            continue

        thrower = entity_thrower.get(str(entity_id))
        if not thrower:
            continue
        if victim and victim == thrower:
            continue

        item = _ensure_restore_player(derived, thrower)
        if item is None:
            continue
        item["enemies_flashed"] += 1


def _calc_kill_reward_and_cash(payload, derived):
    kills = iter_rows((payload or {}).get("kills"))
    for row in kills:
        attacker = to_steamid64_string(
            pick_value(row, ["attacker_steamid", "attacker_steamid64", "attacker"])
        )
        victim = to_steamid64_string(
            pick_value(row, ["victim_steamid", "victim_steamid64", "victim"])
        )
        if not attacker:
            continue

        attacker_side = normalize_side_label(
            pick_value(row, ["attacker_side", "attacker_team", "attacker_team_name"])
        )
        victim_side = normalize_side_label(
            pick_value(row, ["victim_side", "victim_team", "victim_team_name"])
        )
        if attacker_side and victim_side and attacker_side == victim_side and victim:
            continue

        reward = _weapon_reward_hint(pick_value(row, ["weapon", "weapon_name", "weapon_class", "weapon_type"]))
        item = _ensure_restore_player(derived, attacker)
        if item is None:
            continue
        item["kill_reward"] += int(reward)
        item["cash_earned"] += int(reward)

    events = (payload or {}).get("events")
    if not isinstance(events, dict):
        return

    for row in iter_rows(events.get("bomb_planted")):
        sid = to_steamid64_string(pick_value(row, ["user_steamid", "player_steamid", "steamid"]))
        if not sid:
            continue
        item = _ensure_restore_player(derived, sid)
        if item:
            item["cash_earned"] += 300

    for row in iter_rows(events.get("bomb_defused")):
        sid = to_steamid64_string(pick_value(row, ["user_steamid", "player_steamid", "steamid"]))
        if not sid:
            continue
        item = _ensure_restore_player(derived, sid)
        if item:
            item["cash_earned"] += 300


def _calc_equipment_value_and_saved_money(payload, derived):
    windows = _build_round_windows(payload)
    if not windows:
        return

    pickup_rows = []
    events = (payload or {}).get("events")
    if isinstance(events, dict):
        pickup_rows = iter_rows(events.get("item_pickup"))

    buy_cost_by_player_round = {}
    picked_item_set = {}
    round_meta = {int(rn): {"freeze_end": int(freeze_end), "end_tick": end_tick} for rn, _, freeze_end, end_tick in windows}

    for row in pickup_rows:
        sid = to_steamid64_string(pick_value(row, ["user_steamid", "player_steamid", "steamid"]))
        if not sid:
            continue

        tick = to_int(pick_value(row, ["tick", "game_tick", "event_tick"]), default=0)
        round_num = _round_for_tick(tick, windows)
        if round_num is None:
            continue

        freeze_end = int((round_meta.get(round_num) or {}).get("freeze_end") or 0)
        if freeze_end > 0 and tick > freeze_end:
            continue

        item_name = str(pick_value(row, ["item", "weapon", "name"]) or "").strip().lower()
        if not item_name or item_name in {"knife", "c4"}:
            continue

        key = (sid, int(round_num))
        sig = (key, item_name)
        if sig in picked_item_set:
            continue
        picked_item_set[sig] = True

        cost = _item_cost_hint(item_name)
        if cost <= 0:
            continue

        buy_cost_by_player_round[key] = buy_cost_by_player_round.get(key, 0) + int(cost)

    for (sid, round_num), value in buy_cost_by_player_round.items():
        item = _ensure_restore_player(derived, sid)
        if item is None:
            continue
        item["equipment_value"] += int(value)

    # Estimate money_saved as value carried into surviving round end.
    # We classify survivors using final alive tick snapshots per round.
    alive_at_end = {}
    for row in iter_rows((payload or {}).get("ticks")):
        sid = to_steamid64_string(pick_value(row, ["steamid", "steamid64", "player_steamid"]))
        if not sid:
            continue
        tick = to_int(pick_value(row, ["tick", "game_tick", "event_tick"]), default=0)
        if tick <= 0:
            continue
        round_num = to_int(pick_value(row, ["round_num", "round", "round_number"]), default=0)
        if round_num <= 0:
            continue
        health = to_int(pick_value(row, ["health", "hp"]), default=0)

        key = (sid, round_num)
        prev = alive_at_end.get(key)
        if prev is None or tick >= prev[0]:
            alive_at_end[key] = (tick, health)

    for (sid, round_num), value in buy_cost_by_player_round.items():
        final = alive_at_end.get((sid, round_num))
        if not final:
            continue
        final_health = int(final[1])
        if final_health <= 0:
            continue

        item = _ensure_restore_player(derived, sid)
        if item is None:
            continue
        item["money_saved"] += int(value)


def build_derived_weapon_stats(parsed_payload):
    """Build per-player per-weapon stats for one match-map payload.

        Returns:
            {
                "map_rows": {steamid: {weapon: metrics}},
                "round_rows": [
                    {"steamid": ..., "round_num": ..., "weapon": ..., ...},
                ],
            }
    """
    payload = parsed_payload or {}
    stats = {}
    round_stats = {}
    kill_drop_events = []

    def ensure_entry(steamid64, weapon):
        if not steamid64 or not weapon:
            return None
        if steamid64 not in stats:
            stats[steamid64] = {}
        if weapon not in stats[steamid64]:
            stats[steamid64][weapon] = {
                "shots_fired": 0,
                "shots_hit": 0,
                "kills": 0,
                "headshot_kills": 0,
                "damage": 0,
                "rounds_with_weapon": 0,
                "_round_set": set(),
            }
        return stats[steamid64][weapon]

    def ensure_round_entry(steamid64, round_num, weapon):
        if not steamid64 or int(round_num or 0) <= 0 or not weapon:
            return None
        key = (str(steamid64), int(round_num), str(weapon))
        if key not in round_stats:
            round_stats[key] = {
                "shots_fired": 0,
                "shots_hit": 0,
                "kills": 0,
                "headshot_kills": 0,
                "damage": 0,
            }
        return round_stats[key]

    # Shots fired per weapon
    for row in iter_rows(payload.get("shots")):
        sid = to_steamid64_string(
            pick_value(row, ["steamid", "steamid64", "player_steamid", "shooter_steamid"])
        )
        weapon = normalize_weapon_name(
            pick_value(row, ["weapon", "weapon_name", "weapon_class", "weapon_type", "weapon_item"])
        )
        if not sid or not weapon:
            continue

        item = ensure_entry(sid, weapon)
        if item is None:
            continue
        item["shots_fired"] += 1

        round_num = to_int(pick_value(row, ["round_num", "round", "round_number"]), default=0)
        if round_num > 0:
            item["_round_set"].add(round_num)
            round_item = ensure_round_entry(sid, round_num, weapon)
            if round_item is not None:
                round_item["shots_fired"] += 1

    # Hits and damage per weapon from damages table
    for row in iter_rows(payload.get("damages")):
        sid = to_steamid64_string(
            pick_value(row, ["attacker_steamid", "attacker_steamid64", "attacker"])
        )
        weapon = normalize_weapon_name(
            pick_value(row, ["weapon", "weapon_name", "weapon_class", "weapon_type", "weapon_item"])
        )
        if not sid or not weapon:
            continue

        attacker_side = normalize_side_label(
            pick_value(row, ["attacker_side", "attacker_team", "attacker_team_name"])
        )
        victim_side = normalize_side_label(
            pick_value(row, ["victim_side", "victim_team", "victim_team_name"])
        )
        if attacker_side and victim_side and attacker_side == victim_side:
            continue

        item = ensure_entry(sid, weapon)
        if item is None:
            continue

        item["shots_hit"] += 1
        item["damage"] += to_int(
            pick_value(
                row,
                [
                    "dmg_health_real",
                    "health_damage",
                    "health_damage_taken",
                    "hp_damage",
                    "dmg_health",
                    "damage_health",
                    "damage",
                ],
            ),
            default=0,
        )

        round_num = to_int(pick_value(row, ["round_num", "round", "round_number"]), default=0)
        if round_num > 0:
            item["_round_set"].add(round_num)
            round_item = ensure_round_entry(sid, round_num, weapon)
            if round_item is not None:
                round_item["shots_hit"] += 1
                round_item["damage"] += to_int(
                    pick_value(
                        row,
                        [
                            "dmg_health_real",
                            "health_damage",
                            "health_damage_taken",
                            "hp_damage",
                            "dmg_health",
                            "damage_health",
                            "damage",
                        ],
                    ),
                    default=0,
                )

    # Kills/headshots per weapon
    for row in iter_rows(payload.get("kills")):
        sid = to_steamid64_string(
            pick_value(row, ["attacker_steamid", "attacker_steamid64", "attacker"])
        )
        weapon_raw = pick_value(row, ["weapon", "weapon_name", "weapon_class", "weapon_type", "weapon_item"])
        weapon = normalize_weapon_name(
            weapon_raw
        )
        round_num = to_int(pick_value(row, ["round_num", "round", "round_number"]), default=0)
        tick = to_int(pick_value(row, ["tick", "event_tick", "game_tick"]), default=0)

        if not sid:
            kill_drop_events.append(
                {
                    "reason": "missing_attacker_steamid",
                    "round_num": round_num,
                    "tick": tick,
                    "weapon_raw": str(weapon_raw or ""),
                }
            )
            continue

        if not weapon:
            kill_drop_events.append(
                {
                    "reason": "missing_or_unmapped_weapon",
                    "round_num": round_num,
                    "tick": tick,
                    "weapon_raw": str(weapon_raw or ""),
                }
            )
            continue

        attacker_side = normalize_side_label(
            pick_value(row, ["attacker_side", "attacker_team", "attacker_team_name"])
        )
        victim_side = normalize_side_label(
            pick_value(row, ["victim_side", "victim_team", "victim_team_name"])
        )
        if attacker_side and victim_side and attacker_side == victim_side:
            kill_drop_events.append(
                {
                    "reason": "teamkill_ignored",
                    "round_num": round_num,
                    "tick": tick,
                    "weapon_raw": str(weapon_raw or ""),
                    "attacker_side": str(attacker_side),
                }
            )
            continue

        item = ensure_entry(sid, weapon)
        if item is None:
            continue

        item["kills"] += 1
        is_hs = pick_value(row, ["is_headshot", "headshot", "isheadshot"])
        if is_hs in {True, 1, "1", "true", "True"}:
            item["headshot_kills"] += 1

        if round_num > 0:
            item["_round_set"].add(round_num)
            round_item = ensure_round_entry(sid, round_num, weapon)
            if round_item is not None:
                round_item["kills"] += 1
                if is_hs in {True, 1, "1", "true", "True"}:
                    round_item["headshot_kills"] += 1

    if kill_drop_events:
        by_reason = {}
        for ev in kill_drop_events:
            reason = str(ev.get("reason") or "unknown")
            by_reason[reason] = by_reason.get(reason, 0) + 1

        logger.log(
            "[WEAPON_PARSE] "
            f"kill events filtered total={len(kill_drop_events)} reasons={by_reason}",
            level="DEBUG",
        )

        for ev in kill_drop_events[:8]:
            logger.log(
                "[WEAPON_PARSE][DROP] "
                f"reason={ev.get('reason')} round={ev.get('round_num')} tick={ev.get('tick')} "
                f"weapon_raw={ev.get('weapon_raw')} attacker_side={ev.get('attacker_side')}",
                level="DEBUG",
            )

    # Finalize rounds_with_weapon and strip internal fields.
    for sid, weapons in list(stats.items()):
        for weapon, item in list(weapons.items()):
            item["rounds_with_weapon"] = int(len(item.get("_round_set") or set()))
            item.pop("_round_set", None)

            if (
                item["shots_fired"] <= 0
                and item["shots_hit"] <= 0
                and item["kills"] <= 0
                and item["damage"] <= 0
            ):
                weapons.pop(weapon, None)

        if not weapons:
            stats.pop(sid, None)

    round_rows = []
    for (sid, round_num, weapon), metrics in sorted(round_stats.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2])):
        if (
            int(metrics.get("shots_fired") or 0) <= 0
            and int(metrics.get("shots_hit") or 0) <= 0
            and int(metrics.get("kills") or 0) <= 0
            and int(metrics.get("damage") or 0) <= 0
        ):
            continue
        round_rows.append(
            {
                "steamid": str(sid),
                "round_num": int(round_num),
                "weapon": str(weapon),
                "shots_fired": int(metrics.get("shots_fired") or 0),
                "shots_hit": int(metrics.get("shots_hit") or 0),
                "kills": int(metrics.get("kills") or 0),
                "headshot_kills": int(metrics.get("headshot_kills") or 0),
                "damage": int(metrics.get("damage") or 0),
            }
        )

    return {
        "map_rows": stats,
        "round_rows": round_rows,
    }


def build_derived_restore_stats(parsed_payload):
    payload = parsed_payload or {}
    derived = {}

    # Seed all encountered players so consumers can trust key existence.
    for table_key in ["kills", "damages", "shots", "ticks", "player_round_totals"]:
        for row in iter_rows(payload.get(table_key)):
            for sid_key in [
                "steamid", "steamid64", "player_steamid", "attacker_steamid",
                "victim_steamid", "assister_steamid", "user_steamid", "thrower_steamid",
            ]:
                sid = to_steamid64_string(pick_value(row, [sid_key]))
                if sid:
                    _ensure_restore_player(derived, sid)

    _calc_live_time_seconds(payload, derived)
    _calc_enemies_flashed(payload, derived)
    _calc_kill_reward_and_cash(payload, derived)
    _calc_equipment_value_and_saved_money(payload, derived)

    return derived


def _to_polars_df(table):
    if isinstance(table, pl.DataFrame):
        return table
    if isinstance(table, pd.DataFrame):
        if table.empty:
            return None
        return pl.from_pandas(table)
    if isinstance(table, list):
        rows = [r for r in table if isinstance(r, dict)]
        if not rows:
            return None
        return pl.from_dicts(rows)
    return None


def build_derived_movement_stats(parsed_payload, bin_ticks=32):
    """Build movement-derived analytics from tick data.

    Returns dict with three row lists:
      - map_rows
      - round_rows
      - timeline_bins
    """
    payload = parsed_payload or {}

    ticks = _to_polars_df(payload.get("ticks"))
    if ticks is None or ticks.height == 0:
        return {"map_rows": [], "round_rows": [], "timeline_bins": [], "meta": {"tickrate": 128.0, "bin_ticks": int(bin_ticks)}}

    required = {"round_num", "tick", "steamid", "health", "X", "Y", "Z"}
    if not required.issubset(set(ticks.columns)):
        return {"map_rows": [], "round_rows": [], "timeline_bins": [], "meta": {"tickrate": 128.0, "bin_ticks": int(bin_ticks)}}

    windows = _build_round_windows(payload)
    if not windows:
        return {"map_rows": [], "round_rows": [], "timeline_bins": [], "meta": {"tickrate": 128.0, "bin_ticks": int(bin_ticks)}}

    header = payload.get("header") if isinstance(payload, dict) else {}
    tickrate = 128.0
    try:
        candidate = float((header or {}).get("tickrate") or 128)
        if candidate > 0:
            tickrate = candidate
    except Exception:
        tickrate = 128.0

    windows_df = pl.DataFrame(
        {
            "round_num": [int(w[0]) for w in windows],
            "live_start": [int(w[2] if int(w[2] or 0) > 0 else int(w[1] or 0)) for w in windows],
            "live_end": [int(w[3] if w[3] is not None and int(w[3]) > 0 else int(w[2] if int(w[2] or 0) > 0 else int(w[1] or 0))) for w in windows],
        }
    )

    columns = ["round_num", "tick", "steamid", "health", "X", "Y", "Z"]
    if "side" in ticks.columns:
        columns.append("side")

    work = (
        ticks
        .select(columns)
        .with_columns(
            [
                pl.col("round_num").cast(pl.Int64, strict=False).alias("round_num"),
                pl.col("tick").cast(pl.Int64, strict=False).alias("tick"),
                pl.col("steamid").cast(pl.Int64, strict=False).alias("steamid"),
                pl.col("health").cast(pl.Float64, strict=False).alias("health"),
                pl.col("X").cast(pl.Float64, strict=False).alias("X"),
                pl.col("Y").cast(pl.Float64, strict=False).alias("Y"),
                pl.col("Z").cast(pl.Float64, strict=False).alias("Z"),
            ]
        )
        .drop_nulls(["round_num", "tick", "steamid", "X", "Y", "Z"])
        .filter(pl.col("steamid") >= 10_000_000_000_000_000)
        .join(windows_df, on="round_num", how="left")
        .drop_nulls(["live_start", "live_end"])
        .sort(["steamid", "round_num", "tick"])
    )

    if work.height == 0:
        return {"map_rows": [], "round_rows": [], "timeline_bins": [], "meta": {"tickrate": tickrate, "bin_ticks": int(bin_ticks)}}

    work = work.with_columns(
        [
            pl.col("X").diff().over(["steamid", "round_num"]).alias("dx"),
            pl.col("Y").diff().over(["steamid", "round_num"]).alias("dy"),
            pl.col("Z").diff().over(["steamid", "round_num"]).alias("dz"),
            pl.col("tick").diff().over(["steamid", "round_num"]).alias("dt"),
        ]
    )

    work = work.with_columns(
        [
            ((pl.col("dx") ** 2 + pl.col("dy") ** 2 + pl.col("dz") ** 2).sqrt()).alias("distance"),
            ((pl.col("dx") ** 2 + pl.col("dy") ** 2).sqrt()).alias("distance_xy"),
            (pl.col("tick") >= pl.col("live_start")).and_(pl.col("tick") <= pl.col("live_end")).alias("in_live"),
        ]
    )

    work = work.with_columns(
        [
            pl.col("dx").shift(1).over(["steamid", "round_num"]).alias("prev_dx"),
            pl.col("dy").shift(1).over(["steamid", "round_num"]).alias("prev_dy"),
        ]
    )

    work = work.with_columns(
        [
            ((pl.col("prev_dx") ** 2 + pl.col("prev_dy") ** 2).sqrt()).alias("prev_distance_xy"),
        ]
    )

    work = work.with_columns(
        [
            pl.when(
                (pl.col("distance_xy") > 0)
                & (pl.col("prev_distance_xy") > 0)
            )
            .then(
                ((pl.col("dx") * pl.col("prev_dx") + pl.col("dy") * pl.col("prev_dy"))
                 / (pl.col("distance_xy") * pl.col("prev_distance_xy")))
            )
            .otherwise(None)
            .alias("turn_cos"),
        ]
    )

    work = work.with_columns(
        [
            pl.when((pl.col("dt") > 0) & (pl.col("dt") <= 2)).then(pl.col("distance") / pl.col("dt")).otherwise(None).alias("units_per_tick"),
            pl.when((pl.col("health") > 0) & pl.col("in_live") & (pl.col("dt") > 0) & (pl.col("dt") <= 2)).then(pl.col("distance")).otherwise(0.0).alias("distance_alive"),
            pl.when((pl.col("health") > 0) & (~pl.col("in_live")) & (pl.col("dt") > 0) & (pl.col("dt") <= 2)).then(pl.col("distance")).otherwise(0.0).alias("distance_freeze"),
            pl.when(
                (pl.col("health") > 0)
                & pl.col("in_live")
                & (pl.col("dt") > 0)
                & (pl.col("dt") <= 2)
                & (pl.col("distance_xy") > 0)
                & (pl.col("turn_cos").is_not_null())
                & (pl.col("turn_cos") < 0.92)
            )
            .then(pl.col("distance_xy"))
            .otherwise(0.0)
            .alias("distance_strafe"),
            pl.when(
                (pl.col("health") > 0)
                & pl.col("in_live")
                & (pl.col("dt") > 0)
                & (pl.col("dt") <= 2)
                & (pl.col("distance_xy") > 0)
                & (pl.col("turn_cos").is_not_null())
                & (pl.col("turn_cos") < 0.92)
            )
            .then(1)
            .otherwise(0)
            .alias("strafe_tick"),
            pl.when((pl.col("health") > 0) & pl.col("in_live")).then(1).otherwise(0).alias("alive_tick"),
        ]
    )

    work = work.with_columns(
        [
            (pl.col("units_per_tick") * pl.lit(tickrate)).alias("speed_units_s"),
            pl.when(
                (pl.col("health") > 0)
                & pl.col("in_live")
                & pl.col("units_per_tick").is_not_null()
                & ((pl.col("units_per_tick") * pl.lit(tickrate)) < 400)
            )
            .then((pl.col("units_per_tick") * pl.lit(tickrate)) * pl.lit(0.0254))
            .otherwise(None)
            .alias("speed_m_s"),
            pl.when(
                (pl.col("health") > 0)
                & pl.col("in_live")
                & (pl.col("units_per_tick") * pl.lit(tickrate) < 20)
            )
            .then(1)
            .otherwise(0)
            .alias("stationary_tick"),
            pl.when(
                (pl.col("health") > 0)
                & pl.col("in_live")
                & (pl.col("units_per_tick") * pl.lit(tickrate) >= 220)
            )
            .then(1)
            .otherwise(0)
            .alias("sprint_tick"),
        ]
    )

    # Optional stable side per (steamid, round_num)
    side_lookup = None
    if "side" in work.columns:
        try:
            side_lookup = (
                work
                .select(["steamid", "round_num", "side"])
                .filter(pl.col("side").is_not_null())
                .group_by(["steamid", "round_num"])
                .agg(pl.col("side").first().alias("side"))
            )
        except Exception:
            side_lookup = None

    n_rounds = max(1, windows_df.height)

    per_map = (
        work
        .group_by("steamid")
        .agg(
            [
                pl.sum("distance_alive").alias("total_distance_units"),
                pl.sum("distance_freeze").alias("freeze_distance_units"),
                pl.sum("distance_strafe").alias("strafe_distance_units"),
                pl.max("speed_units_s").fill_null(0.0).alias("max_speed_units_s"),
                pl.sum("alive_tick").alias("ticks_alive"),
                pl.sum("stationary_tick").alias("stationary_ticks"),
                pl.sum("sprint_tick").alias("sprint_ticks"),
                pl.sum("strafe_tick").alias("strafe_ticks"),
            ]
        )
        .with_columns(
            [
                (pl.col("ticks_alive") / pl.lit(tickrate)).alias("alive_seconds"),
                pl.when(pl.col("ticks_alive") > 0)
                .then(pl.col("total_distance_units") / (pl.col("ticks_alive") / pl.lit(tickrate)))
                .otherwise(0.0)
                .alias("avg_speed_units_s"),
                (pl.col("total_distance_units") / pl.lit(float(n_rounds))).alias("distance_per_round_units"),
                (pl.col("total_distance_units") * pl.lit(0.0254)).alias("total_distance_m"),
                pl.when(pl.col("ticks_alive") > 0)
                .then((pl.col("total_distance_units") / (pl.col("ticks_alive") / pl.lit(tickrate))) * pl.lit(0.0254))
                .otherwise(0.0)
                .alias("avg_speed_m_s"),
                pl.when(pl.col("total_distance_units") > 0)
                .then(pl.col("strafe_distance_units") / pl.col("total_distance_units"))
                .otherwise(0.0)
                .alias("strafe_ratio"),
                pl.when(pl.col("ticks_alive") > 0)
                .then(pl.col("stationary_ticks") / pl.col("ticks_alive"))
                .otherwise(0.0)
                .alias("stationary_ratio"),
                pl.when(pl.col("ticks_alive") > 0)
                .then(pl.col("sprint_ticks") / pl.col("ticks_alive"))
                .otherwise(0.0)
                .alias("sprint_ratio"),
            ]
        )
    )

    per_round = (
        work
        .group_by(["steamid", "round_num"])
        .agg(
            [
                pl.sum("distance_alive").alias("distance_units"),
                pl.sum("distance_alive").alias("live_distance_units"),
                pl.sum("distance_freeze").alias("freeze_distance_units"),
                pl.sum("distance_strafe").alias("strafe_distance_units"),
                pl.max("speed_units_s").fill_null(0.0).alias("max_speed_units_s"),
                pl.sum("alive_tick").alias("ticks_alive"),
                pl.sum("stationary_tick").alias("stationary_ticks"),
                pl.sum("sprint_tick").alias("sprint_ticks"),
                pl.sum("strafe_tick").alias("strafe_ticks"),
            ]
        )
        .with_columns(
            [
                (pl.col("ticks_alive") / pl.lit(tickrate)).alias("alive_seconds"),
                pl.when(pl.col("ticks_alive") > 0)
                .then(pl.col("distance_units") / (pl.col("ticks_alive") / pl.lit(tickrate)))
                .otherwise(0.0)
                .alias("avg_speed_units_s"),
                pl.when(pl.col("distance_units") > 0)
                .then(pl.col("strafe_distance_units") / pl.col("distance_units"))
                .otherwise(0.0)
                .alias("strafe_ratio"),
            ]
        )
        # Keep join keys as Int64; DataFrame-wide fill_null(0.0) upcasts them to Float64.
        .with_columns(
            [
                pl.col("steamid").cast(pl.Int64, strict=False).alias("steamid"),
                pl.col("round_num").cast(pl.Int64, strict=False).alias("round_num"),
            ]
        )
    )

    if side_lookup is not None and side_lookup.height > 0:
        per_round = per_round.join(side_lookup, on=["steamid", "round_num"], how="left")
    else:
        per_round = per_round.with_columns(pl.lit("").alias("side"))

    bin_size_sec = float(bin_ticks) / float(tickrate)
    bins = (
        work
        .filter(pl.col("in_live"))
        .with_columns(
            [
                ((pl.col("tick") - pl.col("live_start")) // pl.lit(int(bin_ticks))).cast(pl.Int64).alias("bin_index"),
            ]
        )
        .group_by(["steamid", "round_num", "bin_index"])
        .agg(
            [
                pl.median("speed_m_s").alias("median_speed_m_s"),
                pl.mean("speed_m_s").alias("mean_speed_m_s"),
                pl.col("speed_m_s").quantile(0.25).alias("p25_speed_m_s"),
                pl.col("speed_m_s").quantile(0.75).alias("p75_speed_m_s"),
                pl.max("speed_m_s").alias("max_speed_m_s"),
                pl.sum("alive_tick").alias("alive_ticks"),
                pl.len().alias("samples"),
                pl.col("speed_m_s").is_not_null().sum().alias("speed_samples"),
            ]
        )
        .with_columns(
            [
                (pl.col("bin_index") * pl.lit(bin_size_sec)).alias("bin_start_sec"),
                pl.when(pl.col("samples") > 0)
                .then(pl.col("alive_ticks") / pl.col("samples"))
                .otherwise(0.0)
                .alias("alive_ratio"),
            ]
        )
    )

    if side_lookup is not None and side_lookup.height > 0 and bins.height > 0:
        bins = bins.join(side_lookup, on=["steamid", "round_num"], how="left")
    else:
        bins = bins.with_columns(pl.lit("").alias("side"))

    def _sid_str(frame, col="steamid"):
        return frame.with_columns(pl.col(col).cast(pl.Int64).cast(pl.Utf8).alias(col))

    map_rows = _sid_str(per_map).select(
        [
            "steamid",
            "total_distance_units",
            "total_distance_m",
            "avg_speed_units_s",
            "avg_speed_m_s",
            "max_speed_units_s",
            "ticks_alive",
            "alive_seconds",
            "distance_per_round_units",
            "freeze_distance_units",
            "strafe_distance_units",
            "strafe_ratio",
            "stationary_ticks",
            "sprint_ticks",
            "stationary_ratio",
            "sprint_ratio",
            "strafe_ticks",
        ]
    ).to_dicts()

    round_rows = _sid_str(per_round).select(
        [
            "steamid",
            "round_num",
            "side",
            "distance_units",
            "live_distance_units",
            "freeze_distance_units",
            "strafe_distance_units",
            "strafe_ratio",
            "avg_speed_units_s",
            "max_speed_units_s",
            "ticks_alive",
            "alive_seconds",
            "stationary_ticks",
            "sprint_ticks",
            "strafe_ticks",
        ]
    ).to_dicts()

    bin_rows = _sid_str(bins).select(
        [
            "steamid",
            "round_num",
            "bin_index",
            "bin_start_sec",
            "median_speed_m_s",
            "mean_speed_m_s",
            "p25_speed_m_s",
            "p75_speed_m_s",
            "max_speed_m_s",
            "alive_ratio",
            "samples",
            "speed_samples",
            "side",
        ]
    ).to_dicts()

    return {
        "map_rows": map_rows,
        "round_rows": round_rows,
        "timeline_bins": bin_rows,
        "meta": {
            "tickrate": float(tickrate),
            "bin_ticks": int(bin_ticks),
        },
    }


def build_derived_round_events(parsed_payload, trade_window_ticks=640):
    payload = parsed_payload or {}
    rounds = iter_rows(payload.get("rounds")) or iter_rows(payload.get("rounds_stats"))
    kills = iter_rows(payload.get("kills"))
    ticks = iter_rows(payload.get("ticks"))

    if not rounds:
        return {"round_rows": []}

    round_meta = {}
    for idx, row in enumerate(rounds, start=1):
        rn = to_int(pick_value(row, ["round_num", "round", "round_number"]), default=idx)
        if rn <= 0:
            continue
        round_meta[rn] = {
            "winner": normalize_side_label(pick_value(row, ["winner", "winning_side", "winning_team"])),
            "live_start": to_int(pick_value(row, ["freeze_end", "freeze_end_tick", "start", "start_tick"]), default=0),
        }

    participants = {}
    for row in ticks:
        sid = to_steamid64_string(pick_value(row, ["steamid", "steamid64", "player_steamid"]))
        rn = to_int(pick_value(row, ["round_num", "round", "round_number"]), default=0)
        side = normalize_side_label(pick_value(row, ["side", "team", "team_name"]))
        if not sid or rn <= 0 or not side:
            continue
        participants[(rn, sid)] = side

    kills_by_round = {}
    for row in kills:
        rn = to_int(pick_value(row, ["round_num", "round", "round_number"]), default=0)
        tick = to_int(pick_value(row, ["tick", "event_tick", "game_tick"]), default=0)
        attacker = to_steamid64_string(pick_value(row, ["attacker_steamid", "attacker_steamid64", "attacker"]))
        victim = to_steamid64_string(pick_value(row, ["victim_steamid", "victim_steamid64", "victim"]))
        attacker_side = normalize_side_label(pick_value(row, ["attacker_side", "attacker_team", "attacker_team_name"]))
        victim_side = normalize_side_label(pick_value(row, ["victim_side", "victim_team", "victim_team_name"]))
        if rn <= 0 or not attacker or not victim:
            continue
        if attacker_side and victim_side and attacker_side == victim_side:
            continue
        kills_by_round.setdefault(rn, []).append(
            {
                "tick": tick,
                "attacker": attacker,
                "victim": victim,
                "attacker_side": attacker_side,
                "victim_side": victim_side,
            }
        )

    for rn in kills_by_round:
        kills_by_round[rn].sort(key=lambda r: int(r.get("tick") or 0))

    rows = {}

    def _ensure_row(rn, sid, side):
        key = (int(rn), str(sid))
        if key not in rows:
            winner_side = str((round_meta.get(int(rn)) or {}).get("winner") or "")
            rows[key] = {
                "steamid": str(sid),
                "round_num": int(rn),
                "side": str(side or participants.get((int(rn), str(sid))) or ""),
                "opening_attempt": 0,
                "opening_win": 0,
                "trade_kill_count": 0,
                "traded_death_count": 0,
                "clutch_enemy_count": 0,
                "clutch_win": 0,
                "won_round": 0,
            }
            rows[key]["won_round"] = 1 if rows[key]["side"] and winner_side and rows[key]["side"] == winner_side else 0
        return rows[key]

    for (rn, sid), side in participants.items():
        _ensure_row(rn, sid, side)

    for rn, rkills in kills_by_round.items():
        if not rkills:
            continue

        first = rkills[0]
        a = _ensure_row(rn, first["attacker"], first["attacker_side"])
        v = _ensure_row(rn, first["victim"], first["victim_side"])
        a["opening_attempt"] = 1
        a["opening_win"] = 1
        v["opening_attempt"] = 1
        v["opening_win"] = 0

        for i, event in enumerate(rkills):
            death_tick = int(event.get("tick") or 0)
            killer = str(event.get("attacker") or "")
            victim = str(event.get("victim") or "")
            victim_side = str(event.get("victim_side") or "")

            if not killer or not victim or not victim_side:
                continue

            for follow in rkills[i + 1:]:
                t2 = int(follow.get("tick") or 0)
                if t2 - death_tick > int(trade_window_ticks):
                    break
                if str(follow.get("victim") or "") != killer:
                    continue
                if str(follow.get("attacker_side") or "") != victim_side:
                    continue

                trader = _ensure_row(rn, str(follow.get("attacker") or ""), str(follow.get("attacker_side") or ""))
                vd = _ensure_row(rn, victim, victim_side)
                trader["trade_kill_count"] += 1
                vd["traded_death_count"] += 1
                break

        alive_by_side = {"CT": set(), "T": set()}
        for (rrn, sid), side in participants.items():
            if int(rrn) != int(rn):
                continue
            if side in alive_by_side:
                alive_by_side[side].add(str(sid))

        clutch_candidates = {}
        for event in rkills:
            victim = str(event.get("victim") or "")
            victim_side = str(event.get("victim_side") or "")
            if victim and victim_side in alive_by_side:
                alive_by_side[victim_side].discard(victim)

            for side in ("CT", "T"):
                enemy = "T" if side == "CT" else "CT"
                own_alive = alive_by_side.get(side) or set()
                enemy_alive = alive_by_side.get(enemy) or set()
                if len(own_alive) == 1 and len(enemy_alive) >= 2:
                    lone = next(iter(own_alive))
                    clutch_candidates[lone] = max(
                        int(clutch_candidates.get(lone) or 0),
                        int(len(enemy_alive)),
                    )

        winner_side = str((round_meta.get(int(rn)) or {}).get("winner") or "")
        for lone_sid, enemies in clutch_candidates.items():
            side = participants.get((int(rn), str(lone_sid))) or ""
            entry = _ensure_row(rn, lone_sid, side)
            entry["clutch_enemy_count"] = max(int(entry["clutch_enemy_count"]), int(enemies))
            if side and winner_side and side == winner_side:
                entry["clutch_win"] = 1

    return {"round_rows": list(rows.values())}
