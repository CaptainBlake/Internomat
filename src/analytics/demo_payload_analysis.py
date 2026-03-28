import math
from bisect import bisect_right

import pandas as pd
import polars as pl


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
