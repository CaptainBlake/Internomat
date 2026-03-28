class DemoScrapperMetricsMixin:
    def _analyze_multi_kills(self, parsed_payload, metrics):
        """Group kills by (round, attacker) to track multi-kill stats."""
        kills_per_round_attacker = {}

        for row in self._iter_rows((parsed_payload or {}).get("kills")):
            attacker = self._to_steamid64_string(
                self._pick_value(row, ["attacker_steamid", "attacker_steamid64", "attacker"])
            )
            round_num = self._pick_value(row, ["round_num", "round", "round_number"])

            if not attacker or round_num is None:
                continue

            # Ensure attacker is in metrics before continuing
            if attacker not in metrics:
                continue

            key = (self._to_int(round_num), attacker)
            kills_per_round_attacker[key] = kills_per_round_attacker.get(key, 0) + 1

        # Assign multi-kill stats
        for (round_num, attacker), kill_count in kills_per_round_attacker.items():
            if attacker in metrics:
                if kill_count >= 2:
                    metrics[attacker]["enemy2ks"] += 1
                if kill_count >= 3:
                    metrics[attacker]["enemy3ks"] += 1
                if kill_count >= 4:
                    metrics[attacker]["enemy4ks"] += 1
                if kill_count >= 5:
                    metrics[attacker]["enemy5ks"] += 1

    def _analyze_grenades_and_flashes(self, parsed_payload, metrics):
        """Track grenade throws, flashes, and detonation impact."""
        # Count unique grenade entities per thrower (trajectory tables contain many rows per grenade).
        grenade_counts = {}
        seen_entities = set()

        def _ensure_thrower(thrower_id):
            if thrower_id not in grenade_counts:
                grenade_counts[thrower_id] = {"flash": 0, "he": 0, "smoke": 0, "molotov": 0}

        for row in self._iter_rows((parsed_payload or {}).get("grenades")):
            thrower = self._to_steamid64_string(
                self._pick_value(row, ["thrower_steamid", "thrower_steamid64"])
            )
            grenade_type = str(self._pick_value(row, ["grenade_type", "type"]) or "unknown").lower()
            entity_id = self._pick_value(row, ["entity_id", "grenade_entity", "id"])

            if not thrower or thrower not in metrics:
                continue

            if entity_id is not None:
                unique_key = (thrower, str(entity_id))
                if unique_key in seen_entities:
                    continue
                seen_entities.add(unique_key)

            _ensure_thrower(thrower)

            if "flash" in grenade_type:
                grenade_counts[thrower]["flash"] += 1
            elif "he" in grenade_type or "grenade" in grenade_type:
                grenade_counts[thrower]["he"] += 1
            elif "smoke" in grenade_type:
                grenade_counts[thrower]["smoke"] += 1
            elif "molotov" in grenade_type or "incendiary" in grenade_type:
                grenade_counts[thrower]["molotov"] += 1

        # Assign grenade counts to metrics
        for attacker, grenade_type_counts in grenade_counts.items():
            if attacker in metrics:
                metrics[attacker]["flash_count"] += grenade_type_counts["flash"]
                metrics[attacker]["utility_count"] += grenade_type_counts["he"] + grenade_type_counts["molotov"]

        # Track utility successes via events if available
        events = (parsed_payload or {}).get("events", {})
        if isinstance(events, dict):
            # Count flashbang detonations
            flash_detonations = events.get("flashbang_detonate", [])
            for event in self._iter_rows(flash_detonations):
                thrower = self._to_steamid64_string(
                    self._pick_value(event, ["thrower_steamid", "thrower_steamid64", "player_steamid"])
                )
                if thrower and thrower in metrics:
                    metrics[thrower]["flash_successes"] += 1

            # Count HE grenade detonations as utility successes
            he_detonations = events.get("hegrenade_detonate", [])
            for event in self._iter_rows(he_detonations):
                thrower = self._to_steamid64_string(
                    self._pick_value(event, ["thrower_steamid", "thrower_steamid64", "player_steamid"])
                )
                if thrower and thrower in metrics:
                    metrics[thrower]["utility_successes"] += 1
                    # Count enemies flashed if damage was dealt
                    if "hit_data" in event or "hurt" in str(event).lower():
                        metrics[thrower]["enemies_flashed"] += 1

    @staticmethod
    def _extract_damage_value(row):
        for key in ["dmg_health_real", "dmg_health", "health_damage", "hp_damage", "damage"]:
            if key in row and row.get(key) is not None:
                try:
                    return int(float(row.get(key)))
                except Exception:
                    return 0
        return 0

    @staticmethod
    def _is_utility_weapon(weapon_value):
        text = str(weapon_value or "").strip().lower()
        if not text:
            return False
        utility_tokens = ["hegrenade", "flash", "molotov", "incgrenade", "inferno", "smoke", "decoy"]
        return any(token in text for token in utility_tokens)

    def _fix_shots_accuracy(self, parsed_payload, metrics):
        """Populate shots_on_target from damages table (fix for accuracy calculation)."""
        damages_per_attacker = {}

        for row in self._iter_rows((parsed_payload or {}).get("damages")):
            attacker = self._to_steamid64_string(
                self._pick_value(row, ["attacker_steamid", "attacker_steamid64", "attacker"])
            )
            weapon = str(self._pick_value(row, ["weapon", "weapon_type"]) or "").lower()
            damage = self._to_int(self._pick_value(row, ["damage", "hp_damage", "health_damage"]), default=0)

            if not attacker or damage <= 0:
                continue

            # Only count non-grenade weapon damage as on-target
            if any(x in weapon for x in ["grenade", "molotov", "incendiary", "smoke", "he", "flash"]):
                continue

            if attacker not in damages_per_attacker:
                damages_per_attacker[attacker] = 0
            damages_per_attacker[attacker] += 1

        # Assign to metrics, but don't overwrite if already set
        for attacker, on_target_count in damages_per_attacker.items():
            if attacker in metrics and metrics[attacker].get("shots_on_target_total", 0) == 0:
                metrics[attacker]["shots_on_target_total"] = on_target_count

    def _analyze_health_points(self, parsed_payload, metrics):
        """Track health points dealt and removed from damages."""
        for row in self._iter_rows((parsed_payload or {}).get("damages")):
            attacker = self._to_steamid64_string(
                self._pick_value(row, ["attacker_steamid", "attacker_steamid64", "attacker"])
            )
            victim = self._to_steamid64_string(
                self._pick_value(row, ["victim_steamid", "victim_steamid64", "victim"])
            )
            health_damage = self._to_int(self._pick_value(row, ["health_damage", "hp_damage", "damage"]), default=0)

            if attacker and attacker in metrics:
                metrics[attacker]["health_points_dealt_total"] += health_damage
            if victim and victim in metrics:
                metrics[victim]["health_points_removed_total"] += health_damage

    def _analyze_live_time(self, parsed_payload, metrics):
        """Calculate player alive duration from ticks table."""
        # Map of (steamid, round) -> list of ticks when alive
        ticks_alive_per_player_round = {}

        for row in self._iter_rows((parsed_payload or {}).get("ticks")):
            steamid = self._to_steamid64_string(
                self._pick_value(row, ["steamid", "steamid64", "player_steamid"])
            )
            tick = self._to_int(self._pick_value(row, ["tick", "game_tick"]), default=0)
            round_num = self._pick_value(row, ["round_num", "round", "round_number"])
            health = self._to_int(self._pick_value(row, ["health", "hp"]), default=0)

            if steamid and tick and steamid in metrics and health > 0:
                key = (steamid, self._to_int(round_num))
                if key not in ticks_alive_per_player_round:
                    ticks_alive_per_player_round[key] = 0
                ticks_alive_per_player_round[key] += 1

        # Sum live time (approximate: each tick = duration, default 1 unit per tick)
        for (steamid, round_num), tick_count in ticks_alive_per_player_round.items():
            if steamid in metrics:
                metrics[steamid]["live_time"] += int(tick_count / 128)  # ~128 ticks/sec

    def _apply_parser_derived_restore_stats(self, parsed_payload, metrics):
        """Apply parser-stage derived economy/live/flash stats when available."""
        payload = parsed_payload or {}
        derived = payload.get("derived_restore_stats") if isinstance(payload, dict) else None
        if not isinstance(derived, dict) or not derived:
            return

        field_keys = {
            "equipment_value",
            "money_saved",
            "kill_reward",
            "cash_earned",
            "live_time",
            "enemies_flashed",
        }

        for steamid64, values in derived.items():
            sid = self._to_steamid64_string(steamid64)
            if not sid or sid not in metrics:
                continue

            row = values if isinstance(values, dict) else {}
            item = metrics[sid]
            for key in field_keys:
                if key not in row:
                    continue
                item[key] = max(self._to_int(item.get(key), default=0), self._to_int(row.get(key), default=0))

    def _analyze_economy_data(self, parsed_payload, metrics):
        """Extract economy data from events and aggregate sources if available."""
        events = (parsed_payload or {}).get("events", {})
        if not isinstance(events, dict):
            return
        
        # Try to extract kill rewards from player_death events
        player_deaths = events.get("player_death", [])
        kill_rewards_per_player = {}
        for event in self._iter_rows(player_deaths):
            attacker = self._to_steamid64_string(
                self._pick_value(event, ["attacker_steamid", "attacker_steamid64", "killer_steamid"])
            )
            kill_reward = self._to_int(self._pick_value(event, ["kill_reward", "reward"]), default=0)

            if attacker and kill_reward > 0:
                kill_rewards_per_player[attacker] = kill_rewards_per_player.get(attacker, 0) + kill_reward

        # Assign accumulated kill rewards to metrics
        for attacker, total_reward in kill_rewards_per_player.items():
            if attacker in metrics and total_reward > 0:
                metrics[attacker]["kill_reward"] = max(metrics[attacker]["kill_reward"], total_reward)

    def _analyze_clutch_situations(self, parsed_payload, metrics):
        """Detect v1 and v2 clutch situations from rounds and kills."""
        # Get round outcomes
        rounds_data = self._iter_rows((parsed_payload or {}).get("rounds"))
        if not rounds_data:
            return

        # For each round, try to detect clutch by analyzing kills in that round
        for round_info in rounds_data:
            round_num = self._to_int(self._pick_value(round_info, ["round_num", "round", "round_number"]))
            round_winner = str(self._pick_value(round_info, ["winner", "winner_side"]) or "").upper()

            if not round_num or not round_winner:
                continue

            # Count players who got kills in this round per team
            kills_in_round = {}  # team_side -> dict of (attacker -> kill_count)

            for kill_row in self._iter_rows((parsed_payload or {}).get("kills")):
                if self._to_int(self._pick_value(kill_row, ["round_num", "round"])) != round_num:
                    continue

                attacker = self._to_steamid64_string(
                    self._pick_value(kill_row, ["attacker_steamid", "attacker_steamid64"])
                )
                attacker_side = str(self._pick_value(kill_row, ["attacker_side", "attacker_team"]) or "?").upper()

                if attacker and attacker in metrics:
                    if attacker_side not in kills_in_round:
                        kills_in_round[attacker_side] = {}
                    kills_in_round[attacker_side][attacker] = kills_in_round[attacker_side].get(attacker, 0) + 1

            # Simple heuristic: if winner has 1-2 players with kills and opponent has many
            # it's likely a clutch situation
            for winning_team, killers in kills_in_round.items():
                if winning_team == round_winner:
                    num_killers = len(killers)
                    if num_killers == 1:
                        # Solo kill round (likely 1v5 or similar)
                        solo_killer = list(killers.keys())[0]
                        if solo_killer in metrics:
                            metrics[solo_killer]["v1_wins"] += 1

    def _analyze_entries_and_clutches(self, parsed_payload, metrics):
        payload = parsed_payload or {}

        # Entry: first non-teamkill attacker in each round.
        kills_rows = self._iter_rows(payload.get("kills"))
        first_entry_by_round = {}

        for row in kills_rows:
            round_num = self._to_int(self._pick_value(row, ["round_num", "round", "round_number"]), default=0)
            if round_num <= 0:
                continue

            attacker = self._to_steamid64_string(
                self._pick_value(row, ["attacker_steamid", "attacker_steamid64", "attacker"])
            )
            victim = self._to_steamid64_string(
                self._pick_value(row, ["victim_steamid", "victim_steamid64", "victim"])
            )
            attacker_side = self._normalize_side_label(
                self._pick_value(row, ["attacker_side", "attacker_team", "attacker_team_name"])
            )
            victim_side = self._normalize_side_label(
                self._pick_value(row, ["victim_side", "victim_team", "victim_team_name"])
            )

            if not attacker or attacker not in metrics:
                continue

            if attacker_side and victim_side and attacker_side == victim_side and victim:
                continue

            tick = self._to_int(self._pick_value(row, ["tick", "game_tick", "event_tick"]), default=0)
            prev = first_entry_by_round.get(round_num)
            if prev is None or (tick > 0 and tick < prev["tick"]):
                first_entry_by_round[round_num] = {
                    "attacker": attacker,
                    "side": attacker_side,
                    "tick": tick if tick > 0 else 10**12,
                }

        winner_by_round = self._round_winner_side_map(payload)
        for round_num, item in first_entry_by_round.items():
            attacker = item["attacker"]
            if attacker not in metrics:
                continue
            metrics[attacker]["entry_count"] += 1
            if item.get("side") and winner_by_round.get(round_num) == item.get("side"):
                metrics[attacker]["entry_wins"] += 1

        # Clutch: detect rounds where a player is last alive on side vs >=1 enemies.
        ticks_rows = self._iter_rows(payload.get("ticks"))
        if not ticks_rows:
            return

        alive_state = {}
        for row in ticks_rows:
            round_num = self._to_int(self._pick_value(row, ["round_num", "round", "round_number"]), default=0)
            tick = self._to_int(self._pick_value(row, ["tick", "game_tick", "event_tick"]), default=0)
            steamid64 = self._to_steamid64_string(
                self._pick_value(row, ["steamid", "steamid64", "player_steamid"])
            )
            side = self._normalize_side_label(self._pick_value(row, ["side", "team", "player_side"]))
            health = self._to_int(self._pick_value(row, ["health", "hp"]), default=0)

            if round_num <= 0 or tick <= 0 or not steamid64 or not side:
                continue
            if health <= 0:
                continue

            key = (round_num, tick)
            if key not in alive_state:
                alive_state[key] = {"CT": set(), "T": set()}
            alive_state[key][side].add(steamid64)

        clutch_attempts = {}
        for (round_num, tick) in sorted(alive_state.keys()):
            ct_alive = alive_state[(round_num, tick)]["CT"]
            t_alive = alive_state[(round_num, tick)]["T"]

            if len(ct_alive) == 1 and len(t_alive) >= 1:
                sid = next(iter(ct_alive))
                clutch_attempts.setdefault((round_num, sid, "CT"), True)

            if len(t_alive) == 1 and len(ct_alive) >= 1:
                sid = next(iter(t_alive))
                clutch_attempts.setdefault((round_num, sid, "T"), True)

        for round_num, sid, side in clutch_attempts.keys():
            if sid not in metrics:
                continue
            enemy_count = 0
            for (rn, tk) in sorted(alive_state.keys()):
                if rn != round_num:
                    continue
                if side == "CT":
                    enemy_count = max(enemy_count, len(alive_state[(rn, tk)]["T"]))
                else:
                    enemy_count = max(enemy_count, len(alive_state[(rn, tk)]["CT"]))

            if enemy_count <= 1:
                metrics[sid]["v1_count"] += 1
            elif enemy_count == 2:
                metrics[sid]["v2_count"] += 1

            if winner_by_round.get(round_num) == side:
                if enemy_count <= 1:
                    metrics[sid]["v1_wins"] += 1
                elif enemy_count == 2:
                    metrics[sid]["v2_wins"] += 1

    def _enhance_metrics_with_awpy_stats(self, parsed_payload, metrics):
        """
        Enhance metrics with awpy's precomputed stats (ADR, KAST, Impact, Rating, Trades).
        This provides additional analytics without re-deriving from raw tables.
        """
        payload = parsed_payload or {}

        # Try to use ADR stats if available
        adr_stats = payload.get("stats_adr")
        if adr_stats is not None:
            try:
                for row_dict in self._iter_rows(adr_stats):
                    steamid = self._pick_value(row_dict, ["steamid", "steamid64"])
                    steamid64 = self._to_steamid64_string(steamid)
                    if steamid64 and steamid64 in metrics:
                        # Store ADR for potential UI use (not in current schema but available for extension)
                        pass
            except Exception:
                pass

        # Try to use KAST stats if available
        kast_stats = payload.get("stats_kast")
        if kast_stats is not None:
            try:
                for row_dict in self._iter_rows(kast_stats):
                    steamid = self._pick_value(row_dict, ["steamid", "steamid64"])
                    steamid64 = self._to_steamid64_string(steamid)
                    if steamid64 and steamid64 in metrics:
                        # Store KAST for potential UI use
                        pass
            except Exception:
                pass

        # Try to use Impact stats if available
        impact_stats = payload.get("stats_impact")
        if impact_stats is not None:
            try:
                for row_dict in self._iter_rows(impact_stats):
                    steamid = self._pick_value(row_dict, ["steamid", "steamid64"])
                    steamid64 = self._to_steamid64_string(steamid)
                    if steamid64 and steamid64 in metrics:
                        # Store Impact for potential UI use
                        pass
            except Exception:
                pass

        # Try to use Rating stats if available
        rating_stats = payload.get("stats_rating")
        if rating_stats is not None:
            try:
                for row_dict in self._iter_rows(rating_stats):
                    steamid = self._pick_value(row_dict, ["steamid", "steamid64"])
                    steamid64 = self._to_steamid64_string(steamid)
                    if steamid64 and steamid64 in metrics:
                        # Store Rating for potential UI use
                        pass
            except Exception:
                pass

    def _build_player_stats_rows(
        self,
        match_id,
        map_number,
        parsed_payload,
        stable_player_teams=None,
        default_team1_name=None,
        default_team2_name=None,
    ):
        metrics = {}
        payload = parsed_payload or {}
        stable_player_teams = stable_player_teams or {}
        kills_rows = self._iter_rows(payload.get("kills"))
        damages_rows = self._iter_rows(payload.get("damages"))
        shots_rows = self._iter_rows(payload.get("shots"))

        has_kill_events = len(kills_rows) > 0
        has_damage_events = len(damages_rows) > 0

        # Resolve team names from latest-round scoreboard-style fields when available.
        ct_team_name, t_team_name = self._extract_team_names(payload)
        if default_team1_name:
            ct_team_name = str(default_team1_name)
        if default_team2_name:
            t_team_name = str(default_team2_name)

        def _normalize_team_side(side, steamid64=None):
            """Convert side identifier to team name."""
            if steamid64 and steamid64 in stable_player_teams:
                return str(stable_player_teams[steamid64])
            if not side:
                return "?"
            side_upper = str(side).upper().replace(" ", "")
            if side_upper in {"CT", "CT_SIDE"} or "COUNTER" in side_upper:
                return ct_team_name
            elif side_upper in {"T", "T_SIDE"} or "TERRORIST" in side_upper:
                return t_team_name
            elif side_upper in {"TEAMA", "A", "TEAM_A"}:
                return ct_team_name
            elif side_upper in {"TEAMB", "B", "TEAM_B"}:
                return t_team_name
            return str(side)

        def _ensure_player(steamid64, name=None, team=None):
            if not steamid64:
                return None
            if steamid64 not in metrics:
                # Normalize team to actual team name if it's a side identifier
                normalized_team = _normalize_team_side(team, steamid64=steamid64) if team else "?"
                metrics[steamid64] = {
                    "steamid64": steamid64,
                    "name": name or steamid64,
                    "team": normalized_team,
                    "kills": 0,
                    "deaths": 0,
                    "assists": 0,
                    "damage": 0,
                    "head_shot_kills": 0,
                    "shots_fired_total": 0,
                    "shots_on_target_total": 0,
                    "utility_damage": 0,
                    "entry_count": 0,
                    "entry_wins": 0,
                    "utility_count": 0,
                    "round_count": 0,
                    "enemy2ks": 0,
                    "enemy3ks": 0,
                    "enemy4ks": 0,
                    "enemy5ks": 0,
                    "utility_successes": 0,
                    "utility_enemies": 0,
                    "flash_count": 0,
                    "flash_successes": 0,
                    "health_points_removed_total": 0,
                    "health_points_dealt_total": 0,
                    "v1_count": 0,
                    "v1_wins": 0,
                    "v2_count": 0,
                    "v2_wins": 0,
                    "equipment_value": 0,
                    "money_saved": 0,
                    "kill_reward": 0,
                    "live_time": 0,
                    "cash_earned": 0,
                    "enemies_flashed": 0,
                }
            else:
                if name:
                    metrics[steamid64]["name"] = name
                if team:
                    normalized_team = _normalize_team_side(team, steamid64=steamid64)
                    # Update team if we don't have a good one yet, or if we found a real team name
                    if metrics[steamid64].get("team") in {None, "", "?", "CT", "T"}:
                        metrics[steamid64]["team"] = normalized_team
                elif steamid64 in stable_player_teams:
                    metrics[steamid64]["team"] = str(stable_player_teams[steamid64])
            return metrics[steamid64]

        # === PRIMARY SOURCE: player_round_totals ===
        # This table represents aggregated stats per player per round
        player_round_totals_rows = self._iter_rows(payload.get("player_round_totals"))
        if player_round_totals_rows:
            # Keep this lightweight and schema-aware: event tables remain authoritative
            # for combat stats, while aggregated parsed fields are used as fallback hints.
            aggregate_field_candidates = {
                "kills": ["kills", "k"],
                "deaths": ["deaths", "d"],
                "assists": ["assists", "a"],
                "damage": ["damage", "damage_total", "total_damage", "dmg"],
                "head_shot_kills": ["head_shot_kills", "hs_kills", "headshots"],
                "utility_damage": ["utility_damage", "grenade_damage", "utility_dmg", "he_damage"],
                "entry_count": ["entry_count", "entry_frags"],
                "entry_wins": ["entry_wins", "entry_frag_wins"],
                "utility_count": ["utility_count", "grenade_count", "utility_grenades"],
                "equipment_value": ["equipment_value", "equipment", "eq_value"],
                "money_saved": ["money_saved", "money_save", "saved_money"],
                "cash_earned": ["cash_earned", "money_earned", "earned_money"],
            }

            for row in player_round_totals_rows:
                steamid64 = self._to_steamid64_string(
                    self._pick_value(row, ["steamid", "steamid64", "player_steamid", "player_steamid64"])
                )
                if not steamid64:
                    continue

                name = self._pick_value(row, ["name", "player_name"])
                team = self._pick_value(row, ["team", "side", "team_name", "player_side"])
                item = _ensure_player(steamid64, name=str(name or steamid64), team=team)
                if not item:
                    continue

                for metric_key, candidates in aggregate_field_candidates.items():
                    raw_value = self._pick_value(row, candidates)
                    if raw_value is None:
                        continue

                    # Combat totals should only fallback to aggregate values when no raw events exist.
                    if metric_key in {"kills", "deaths", "assists"} and has_kill_events:
                        continue
                    if metric_key == "damage" and has_damage_events:
                        continue

                    item[metric_key] = max(item.get(metric_key, 0), self._to_int(raw_value, default=0))

                round_count = self._to_int(
                    self._pick_value(row, ["n_rounds", "round_count", "rounds_played"]),
                    default=1,
                )
                item["round_count"] = max(item["round_count"], round_count)
        else:
            # FALLBACK: Use kills table to derive round count
            kills_rows = self._iter_rows(payload.get("kills"))
            for row in kills_rows:
                attacker = self._to_steamid64_string(
                    self._pick_value(row, ["attacker_steamid", "attacker_steamid64"])
                )
                if attacker:
                    name = str(self._pick_value(row, ["attacker_name"]) or attacker)
                    team = self._pick_value(row, ["attacker_side", "attacker_team"])
                    _ensure_player(attacker, name=name, team=team)

        # === SECONDARY SOURCE: kills table (for detailed kill tracking) ===
        for row in kills_rows:
            attacker = self._to_steamid64_string(
                self._pick_value(row, ["attacker_steamid", "attacker_steamid64", "attacker"])
            )
            victim = self._to_steamid64_string(
                self._pick_value(row, ["victim_steamid", "victim_steamid64", "victim"])
            )
            assister = self._to_steamid64_string(
                self._pick_value(row, ["assister_steamid", "assister_steamid64", "assister"])
            )

            if attacker:
                item = _ensure_player(
                    attacker,
                    name=str(self._pick_value(row, ["attacker_name"]) or attacker),
                    team=self._pick_value(row, ["attacker_side", "attacker_team"]),
                )
                if item:
                    item["kills"] += 1
                    is_hs = self._pick_value(row, ["is_headshot", "headshot", "isheadshot"])
                    if is_hs in {True, 1, "1", "true", "True"}:
                        item["head_shot_kills"] += 1

            if victim:
                item = _ensure_player(
                    victim,
                    name=str(self._pick_value(row, ["victim_name"]) or victim),
                    team=self._pick_value(row, ["victim_side", "victim_team"]),
                )
                if item:
                    item["deaths"] += 1

            if assister:
                item = _ensure_player(
                    assister,
                    name=str(self._pick_value(row, ["assister_name"]) or assister),
                    team=self._pick_value(row, ["assister_side", "assister_team"]),
                )
                if item:
                    item["assists"] += 1

        # === TERTIARY SOURCE: damages table (for health and accuracy) ===
        for row in damages_rows:
            attacker = self._to_steamid64_string(
                self._pick_value(row, ["attacker_steamid", "attacker_steamid64", "attacker"])
            )
            victim = self._to_steamid64_string(
                self._pick_value(row, ["victim_steamid", "victim_steamid64", "victim"])
            )
            health_damage = self._extract_damage_value(row)
            weapon = self._pick_value(row, ["weapon", "weapon_name", "weapon_class", "weapon_type", "weapon_item"])

            attacker_side = self._normalize_side_label(
                self._pick_value(row, ["attacker_side", "attacker_team", "attacker_team_name"])
            )
            victim_side = self._normalize_side_label(
                self._pick_value(row, ["victim_side", "victim_team", "victim_team_name"])
            )
            is_team_damage = attacker_side and victim_side and attacker_side == victim_side

            if health_damage <= 0 or is_team_damage:
                continue

            if attacker and attacker in metrics:
                item = metrics[attacker]
                item["damage"] += health_damage
                item["health_points_dealt_total"] += health_damage
                if self._is_utility_weapon(weapon):
                    item["utility_damage"] += health_damage
                else:
                    item["shots_on_target_total"] += 1

            if victim and victim in metrics:
                item = metrics[victim]
                item["health_points_removed_total"] += health_damage

        # === QUATERNARY SOURCE: shots table (for accuracy) ===
        for row in shots_rows:
            shooter = self._to_steamid64_string(
                self._pick_value(row, ["steamid", "steamid64", "player_steamid", "shooter_steamid"])
            )
            if shooter and shooter in metrics:
                metrics[shooter]["shots_fired_total"] += 1

        # === COMPREHENSIVE DATA EXTRACTION (Phase 2) ===
        self._analyze_multi_kills(payload, metrics)
        self._analyze_grenades_and_flashes(payload, metrics)
        self._fix_shots_accuracy(payload, metrics)
        self._analyze_live_time(payload, metrics)
        self._analyze_economy_data(payload, metrics)
        self._apply_parser_derived_restore_stats(payload, metrics)

        # Prefer parse-time derived clutch/entry stats when available.
        derived_player_stats = payload.get("derived_player_stats") if isinstance(payload, dict) else None
        used_derived_clutch_entry = False
        if isinstance(derived_player_stats, dict) and derived_player_stats:
            used_derived_clutch_entry = True
            for steamid64, derived in derived_player_stats.items():
                sid = self._to_steamid64_string(steamid64)
                if not sid:
                    continue

                if sid not in metrics:
                    _ensure_player(
                        sid,
                        name=str(sid),
                        team=stable_player_teams.get(sid) if isinstance(stable_player_teams, dict) else None,
                    )

                if sid not in metrics:
                    continue

                item = metrics[sid]
                item["entry_count"] = max(item.get("entry_count", 0), self._to_int((derived or {}).get("entry_count"), default=0))
                item["entry_wins"] = max(item.get("entry_wins", 0), self._to_int((derived or {}).get("entry_wins"), default=0))
                item["v1_count"] = max(item.get("v1_count", 0), self._to_int((derived or {}).get("v1_count"), default=0))
                item["v1_wins"] = max(item.get("v1_wins", 0), self._to_int((derived or {}).get("v1_wins"), default=0))
                item["v2_count"] = max(item.get("v2_count", 0), self._to_int((derived or {}).get("v2_count"), default=0))
                item["v2_wins"] = max(item.get("v2_wins", 0), self._to_int((derived or {}).get("v2_wins"), default=0))

        if not used_derived_clutch_entry:
            self._analyze_clutch_situations(payload, metrics)
            self._analyze_entries_and_clutches(payload, metrics)

        # === ENHANCE WITH AWPY PRECOMPUTED STATS ===
        # Try to use awpy's precomputed ADR, KAST, Impact, Rating, and trades if available
        self._enhance_metrics_with_awpy_stats(payload, metrics)

        db_rows = []
        for steamid64, item in metrics.items():
            db_rows.append(
                {
                    "steamid64": steamid64,
                    "match_id": str(match_id),
                    "map_number": int(map_number),
                    "name": str(item.get("name") or steamid64),
                    "team": str(item.get("team") or "?"),
                    "kills": self._to_int(item.get("kills")),
                    "deaths": self._to_int(item.get("deaths")),
                    "assists": self._to_int(item.get("assists")),
                    "damage": self._to_int(item.get("damage")),
                    "enemy5ks": self._to_int(item.get("enemy5ks")),
                    "enemy4ks": self._to_int(item.get("enemy4ks")),
                    "enemy3ks": self._to_int(item.get("enemy3ks")),
                    "enemy2ks": self._to_int(item.get("enemy2ks")),
                    "utility_count": self._to_int(item.get("utility_count")),
                    "utility_damage": self._to_int(item.get("utility_damage")),
                    "utility_successes": self._to_int(item.get("utility_successes")),
                    "utility_enemies": self._to_int(item.get("utility_enemies")),
                    "flash_count": self._to_int(item.get("flash_count")),
                    "flash_successes": self._to_int(item.get("flash_successes")),
                    "health_points_removed_total": self._to_int(item.get("health_points_removed_total")),
                    "health_points_dealt_total": self._to_int(item.get("health_points_dealt_total")),
                    "shots_fired_total": self._to_int(item.get("shots_fired_total")),
                    "shots_on_target_total": self._to_int(item.get("shots_on_target_total")),
                    "v1_count": self._to_int(item.get("v1_count")),
                    "v1_wins": self._to_int(item.get("v1_wins")),
                    "v2_count": self._to_int(item.get("v2_count")),
                    "v2_wins": self._to_int(item.get("v2_wins")),
                    "entry_count": self._to_int(item.get("entry_count")),
                    "entry_wins": self._to_int(item.get("entry_wins")),
                    "equipment_value": self._to_int(item.get("equipment_value")),
                    "money_saved": self._to_int(item.get("money_saved")),
                    "kill_reward": self._to_int(item.get("kill_reward")),
                    "live_time": self._to_int(item.get("live_time")),
                    "head_shot_kills": self._to_int(item.get("head_shot_kills")),
                    "cash_earned": self._to_int(item.get("cash_earned")),
                    "enemies_flashed": self._to_int(item.get("enemies_flashed")),
                }
            )

        return db_rows
