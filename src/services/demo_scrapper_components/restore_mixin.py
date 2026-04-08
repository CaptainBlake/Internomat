from datetime import datetime
from pathlib import Path

from db.connection_db import get_conn, write_transaction
from db.demo_db import (
    is_restore_signature_current,
    resolve_equivalent_match_map,
    upsert_restore_signature,
)
from db.matches_db import (
    get_next_local_match_id,
    get_next_map_number_for_match,
    insert_match,
    insert_match_map,
    insert_match_player_stats_many,
    match_map_has_player_stats,
    set_match_has_demo,
)
from db.stattracker_db import (
    upsert_player_map_weapon_stats_many,
    upsert_player_round_weapon_stats_many,
    upsert_player_map_movement_stats_many,
    upsert_player_round_movement_stats_many,
    upsert_player_round_timeline_bins_many,
    upsert_player_round_events_many,
)
from analytics import demo_payload_analysis
from services import demo_cache
import services.logger as logger


class DemoScrapperRestoreMixin:
    def _ensure_not_cancelled(self, stage="pipeline"):
        """Fallback no-op for tests using lightweight restore stubs.

        DemoScrapperIntegration provides the real cancellation behavior.
        """
        return

    @staticmethod
    def _parse_cache_row_played_at(row):
        """Best-effort timestamp used to order restores from oldest to newest."""
        if not isinstance(row, dict):
            return ""

        source_name = str(row.get("source_file") or row.get("filename") or "")
        if source_name:
            base_name = Path(source_name).name
            if base_name.endswith(".pkl"):
                base_name = base_name[:-4]
            if base_name.endswith(".dem"):
                base_name = base_name[:-4]

            parts = base_name.split("_")
            if len(parts) >= 2:
                date = str(parts[0] or "")
                time = str(parts[1] or "")
                time_parts = time.split("-")
                if len(time_parts) == 3 and date:
                    return f"{date}T{time_parts[0]}:{time_parts[1]}:{time_parts[2]}"

        # Fallback to manifest update time when source filename is missing or malformed.
        return str(row.get("updated_at") or "")

    def _resolve_map_number_conflict(self, *, match_id, map_number, map_name, conn):
        row = conn.execute(
            """
            SELECT map_name
            FROM match_maps
            WHERE match_id = ?
              AND map_number = ?
            LIMIT 1
            """,
            (str(match_id), int(map_number)),
        ).fetchone()

        if not row:
            return int(map_number)

        existing_map_name = str(row["map_name"] or "")
        if existing_map_name == str(map_name):
            return int(map_number)

        next_map_number = get_next_map_number_for_match(match_id=match_id, conn=conn, start_from=0)
        self._log_stage(
            "RESTORE",
            (
                "Resolved map_number conflict "
                f"match={match_id} incoming_map={map_number} ({map_name}) "
                f"existing_map={existing_map_name} remapped_to={next_map_number}"
            ),
            level="INFO",
        )
        return int(next_map_number)

    def _ensure_canonical_cache_alias(
        self,
        *,
        source_match_id,
        source_map_number,
        canonical_match_id,
        canonical_map_number,
        parsed_payload,
        source_file,
    ):
        try:
            src_mid = int(source_match_id)
            src_map = int(source_map_number)
            dst_mid = int(canonical_match_id)
            dst_map = int(canonical_map_number)
        except Exception:
            return

        if src_mid == dst_mid and src_map == dst_map:
            return

        if not isinstance(parsed_payload, dict):
            return

        demo_cache.save_parsed_demo(
            cache_dir=self.parsed_demo_dir,
            match_id=dst_mid,
            map_number=dst_map,
            data=parsed_payload,
            source_file=source_file,
        )
        self._log_stage(
            "RESTORE",
            (
                "Cached canonical alias "
                f"source=({src_mid},{src_map}) target=({dst_mid},{dst_map})"
            ),
            level="DEBUG",
        )

    @staticmethod
    def _is_generic_side_label(value):
        txt = str(value or "").strip().upper().replace(" ", "")
        generic = {
            "",
            "CT",
            "CT_SIDE",
            "T",
            "T_SIDE",
            "COUNTER",
            "COUNTERTERRORIST",
            "COUNTER-TERRORIST",
            "COUNTER-TERRORISTS",
            "COUNTER_TERRORIST",
            "COUNTER_TERRORISTS",
            "TERRORIST",
            "TERRORISTS",
        }
        return txt in generic

    def _collect_round_side_members(self, payload):
        round_side = {}

        def ensure_round(round_num):
            if round_num not in round_side:
                round_side[round_num] = {"CT": set(), "T": set()}

        def add_player(round_num, side_value, steamid_value):
            side = self._normalize_side_label(side_value)
            steamid64 = self._to_steamid64_string(steamid_value)
            rn = self._to_int(round_num, default=0)

            if side is None or steamid64 is None or rn <= 0:
                return

            ensure_round(rn)
            round_side[rn][side].add(steamid64)

        table_specs = [
            (
                "kills",
                [
                    ("round_num", "attacker_side", "attacker_steamid"),
                    ("round_num", "victim_side", "victim_steamid"),
                    ("round_num", "assister_side", "assister_steamid"),
                ],
            ),
            (
                "damages",
                [
                    ("round_num", "attacker_side", "attacker_steamid"),
                    ("round_num", "victim_side", "victim_steamid"),
                ],
            ),
            ("shots", [("round_num", "player_side", "player_steamid")]),
            ("ticks", [("round_num", "side", "steamid")]),
        ]

        for table_name, mappings in table_specs:
            rows = self._iter_rows((payload or {}).get(table_name))
            for row in rows:
                for round_key, side_key, player_key in mappings:
                    add_player(
                        self._pick_value(row, [round_key, "round", "round_number"]),
                        self._pick_value(row, [side_key]),
                        self._pick_value(row, [player_key]),
                    )

        return round_side

    def _collect_explicit_round_side_names(self, payload):
        names = {}

        def ensure_round(round_num):
            if round_num not in names:
                names[round_num] = {"CT": [], "T": []}

        for table_key in ["kills", "damages", "shots", "footsteps", "ticks", "rounds", "rounds_stats"]:
            rows = self._iter_rows((payload or {}).get(table_key))
            for row in rows:
                round_num = self._to_int(
                    self._pick_value(row, ["round_num", "round", "round_number"]),
                    default=0,
                )
                if round_num <= 0:
                    continue

                ensure_round(round_num)

                ct_val = self._pick_value(row, ["ct_side", "ct_team", "team_ct"])
                t_val = self._pick_value(row, ["t_side", "t_team", "team_t"])

                if ct_val is not None and not self._is_generic_side_label(ct_val):
                    names[round_num]["CT"].append(str(ct_val).strip())
                if t_val is not None and not self._is_generic_side_label(t_val):
                    names[round_num]["T"].append(str(t_val).strip())

        return names

    @staticmethod
    def _infer_team_assignment(round_side):
        rounds = sorted(round_side.keys())
        if not rounds:
            return {}

        team_member_counts = {"TeamA": {}, "TeamB": {}}
        assignment = {}

        first = rounds[0]
        assignment[first] = {"CT": "TeamA", "T": "TeamB"}
        for sid in round_side[first]["CT"]:
            team_member_counts["TeamA"][sid] = team_member_counts["TeamA"].get(sid, 0) + 1
        for sid in round_side[first]["T"]:
            team_member_counts["TeamB"][sid] = team_member_counts["TeamB"].get(sid, 0) + 1

        for r in rounds[1:]:
            ct_set = round_side[r]["CT"]
            t_set = round_side[r]["T"]

            score_normal = sum(team_member_counts["TeamA"].get(sid, 0) for sid in ct_set) + sum(
                team_member_counts["TeamB"].get(sid, 0) for sid in t_set
            )
            score_swapped = sum(team_member_counts["TeamB"].get(sid, 0) for sid in ct_set) + sum(
                team_member_counts["TeamA"].get(sid, 0) for sid in t_set
            )

            if score_swapped > score_normal:
                assignment[r] = {"CT": "TeamB", "T": "TeamA"}
                ct_team, t_team = "TeamB", "TeamA"
            else:
                assignment[r] = {"CT": "TeamA", "T": "TeamB"}
                ct_team, t_team = "TeamA", "TeamB"

            for sid in ct_set:
                team_member_counts[ct_team][sid] = team_member_counts[ct_team].get(sid, 0) + 1
            for sid in t_set:
                team_member_counts[t_team][sid] = team_member_counts[t_team].get(sid, 0) + 1

        return assignment

    @staticmethod
    def _infer_team_display_names(round_assignment, explicit_round_side_names):
        votes = {"TeamA": {}, "TeamB": {}}

        for round_num, side_to_team in round_assignment.items():
            round_names = explicit_round_side_names.get(round_num, {"CT": [], "T": []})
            for side in ["CT", "T"]:
                team_key = side_to_team[side]
                for name in round_names.get(side, []):
                    votes[team_key][name] = votes[team_key].get(name, 0) + 1

        team_labels = {}
        for team_key in ["TeamA", "TeamB"]:
            if votes[team_key]:
                team_labels[team_key] = max(votes[team_key].items(), key=lambda x: x[1])[0]
            else:
                team_labels[team_key] = team_key

        return team_labels

    @staticmethod
    def _build_player_stable_team_map(round_side, round_assignment, team_labels):
        counts = {}

        for round_num, sides in round_side.items():
            if round_num not in round_assignment:
                continue

            ct_team = round_assignment[round_num]["CT"]
            t_team = round_assignment[round_num]["T"]

            for sid in sides["CT"]:
                if sid not in counts:
                    counts[sid] = {}
                counts[sid][ct_team] = counts[sid].get(ct_team, 0) + 1

            for sid in sides["T"]:
                if sid not in counts:
                    counts[sid] = {}
                counts[sid][t_team] = counts[sid].get(t_team, 0) + 1

        player_teams = {}
        for sid, team_count in counts.items():
            team_key = max(team_count.items(), key=lambda x: x[1])[0]
            player_teams[sid] = team_labels.get(team_key, team_key)

        return player_teams

    def _build_clustered_match_result(self, parsed_payload):
        payload = parsed_payload or {}
        round_side = self._collect_round_side_members(payload)

        def _resolve_winner_name(raw_winner, team1_name, team2_name):
            txt = str(raw_winner or "").strip().upper().replace(" ", "")
            if not txt:
                return None

            if txt in {"TEAMA", "A", "CT", "CT_SIDE", "COUNTER", "COUNTERTERRORIST", "COUNTER-TERRORIST", "COUNTER_TERRORIST"}:
                return str(team1_name)
            if txt in {"TEAMB", "B", "T", "T_SIDE", "TERRORIST", "TERRORISTS"}:
                return str(team2_name)
            return str(raw_winner)

        if not round_side:
            ct_name, t_name = self._extract_team_names(payload)
            ct_score, t_score, winner = self._extract_scoreboard(payload)
            winner_name = _resolve_winner_name(winner, ct_name, t_name)
            return {
                "team1_name": ct_name,
                "team2_name": t_name,
                "team1_score": ct_score,
                "team2_score": t_score,
                "winner": winner_name,
                "player_team_map": {},
            }

        round_assignment = self._infer_team_assignment(round_side)
        explicit_names = self._collect_explicit_round_side_names(payload)
        team_labels = self._infer_team_display_names(round_assignment, explicit_names)

        # If explicit names are unavailable, fallback to header/side-derived names.
        fallback_team1, fallback_team2 = self._extract_team_names(payload)
        if team_labels.get("TeamA") == "TeamA" and fallback_team1 and not self._is_generic_side_label(fallback_team1):
            team_labels["TeamA"] = str(fallback_team1)
        if team_labels.get("TeamB") == "TeamB" and fallback_team2 and not self._is_generic_side_label(fallback_team2):
            team_labels["TeamB"] = str(fallback_team2)

        team_scores = {"TeamA": 0, "TeamB": 0}
        rounds_rows = self._iter_rows(payload.get("rounds"))
        if not rounds_rows:
            rounds_rows = self._iter_rows(payload.get("rounds_stats"))

        for row in rounds_rows:
            round_num = self._to_int(
                self._pick_value(row, ["round_num", "round", "round_number"]),
                default=0,
            )
            if round_num <= 0 or round_num not in round_assignment:
                continue

            winner_raw = self._pick_value(
                row,
                ["winner_side", "winner", "round_winner", "winning_side", "winning_team"],
            )
            winner_side = self._normalize_side_label(winner_raw)
            if not winner_side:
                continue

            team_key = round_assignment[round_num][winner_side]
            team_scores[team_key] += 1

        team1_name = team_labels.get("TeamA", "TeamA")
        team2_name = team_labels.get("TeamB", "TeamB")
        team1_score = team_scores["TeamA"]
        team2_score = team_scores["TeamB"]

        winner = None
        if team1_score > team2_score:
            winner = team1_name
        elif team2_score > team1_score:
            winner = team2_name

        # Safety net: if winner ever comes through as TeamA/TeamB/CT/T label, map it.
        winner = _resolve_winner_name(winner, team1_name, team2_name)

        player_team_map = self._build_player_stable_team_map(round_side, round_assignment, team_labels)

        return {
            "team1_name": team1_name,
            "team2_name": team2_name,
            "team1_score": team1_score,
            "team2_score": team2_score,
            "winner": winner,
            "player_team_map": player_team_map,
        }

    def _round_winner_side_map(self, parsed_payload):
        winner_by_round = {}
        rounds_rows = self._iter_rows((parsed_payload or {}).get("rounds"))
        if not rounds_rows:
            rounds_rows = self._iter_rows((parsed_payload or {}).get("rounds_stats"))

        for row in rounds_rows:
            round_num = self._to_int(self._pick_value(row, ["round_num", "round", "round_number"]), default=0)
            winner_raw = self._pick_value(row, ["winner_side", "winner", "round_winner", "winning_side"])
            winner_side = self._normalize_side_label(winner_raw)
            if round_num > 0 and winner_side:
                winner_by_round[round_num] = winner_side

        return winner_by_round

    def _resolve_restore_target(
        self,
        *,
        parsed_match_id,
        parsed_map_number,
        parsed_payload,
        played_at,
        map_name,
        team1_name,
        team2_name,
        team1_score,
        team2_score,
        preferred_match_id,
        next_local_match_id,
        conn,
    ):
        parsed_map_number_normalized = self._normalize_map_number(parsed_map_number, default=0)
        target_match_id = str(preferred_match_id) if preferred_match_id is not None else str(parsed_match_id)
        target_map_number = int(parsed_map_number_normalized)

        # Fast-path: if parsed id already points to an existing canonical map, avoid expensive
        # equivalence scoring and keep the original target as-is.
        try:
            parsed_mid = int(parsed_match_id)
            if parsed_mid > 0:
                existing_map = conn.execute(
                    """
                    SELECT map_name
                    FROM match_maps
                    WHERE match_id = ?
                      AND map_number = ?
                    LIMIT 1
                    """,
                    (str(parsed_mid), int(parsed_map_number_normalized)),
                ).fetchone()
                if existing_map:
                    existing_map_name = str(existing_map["map_name"] or "")
                    if not existing_map_name or existing_map_name == str(map_name):
                        return str(parsed_mid), int(parsed_map_number_normalized)

                    # Source cache row uses an existing positive id/map slot but points to a
                    # different map payload (legacy alias drift). Never remap this by fuzzy
                    # equivalence onto another existing match, otherwise unrelated matches can
                    # collapse (e.g. parsed 11 -> canonical 16).
                    target_match_id = str(next_local_match_id)
                    target_map_number = self._resolve_map_number_conflict(
                        match_id=target_match_id,
                        map_number=parsed_map_number_normalized,
                        map_name=map_name,
                        conn=conn,
                    )
                    self._log_stage(
                        "RESTORE",
                        (
                            "Detected source id collision; assigned fresh canonical id "
                            f"parsed=({parsed_match_id},{parsed_map_number_normalized}) "
                            f"existing_map={existing_map_name} incoming_map={map_name} "
                            f"target=({target_match_id},{target_map_number})"
                        ),
                        level="WARNING",
                    )
                    return target_match_id, int(target_map_number)
        except Exception:
            pass

        parsed_players = self.extract_demo_steamids(parsed_payload or {})

        equivalent = resolve_equivalent_match_map(
            map_name=map_name,
            played_at=played_at,
            team1_name=team1_name,
            team2_name=team2_name,
            team1_score=team1_score,
            team2_score=team2_score,
            parsed_players=parsed_players,
            include_non_positive=False,
            conn=conn,
        )

        if equivalent:
            target_match_id = str(equivalent["match_id"])
            target_map_number = int(equivalent["map_number"])
            if (
                str(parsed_match_id) != target_match_id
                or int(parsed_map_number_normalized) != target_map_number
            ):
                self._log_stage(
                    "RESTORE",
                    (
                        "Remapped parsed payload to canonical match/map "
                        f"parsed=({parsed_match_id},{parsed_map_number_normalized}) "
                        f"target=({target_match_id},{target_map_number}) "
                        f"score={equivalent.get('score')}"
                    ),
                    level="INFO",
                )
            return target_match_id, target_map_number

        # No equivalent candidate: allocate/use Internomat-owned canonical match ids.
        if preferred_match_id is not None:
            target_match_id = str(preferred_match_id)
        else:
            target_match_id = str(next_local_match_id)
            self._log_stage(
                "RESTORE",
                (
                    "Assigned new canonical match_id "
                    f"parsed_match={parsed_match_id} canonical_match={target_match_id}"
                ),
                level="INFO",
            )

        target_map_number = self._resolve_map_number_conflict(
            match_id=target_match_id,
            map_number=target_map_number,
            map_name=map_name,
            conn=conn,
        )

        return target_match_id, target_map_number

    def _extract_scoreboard(self, parsed_payload):
        """Extract match scoreboard from awpy rounds table.

        Accurately computes final scores by counting round winners rather than
        relying on potentially-missing or misnamed fields.
        """
        rounds_rows = self._iter_rows((parsed_payload or {}).get("rounds"))
        if not rounds_rows:
            # Fallback: try rounds_stats
            rounds_rows = self._iter_rows((parsed_payload or {}).get("rounds_stats"))

        if not rounds_rows:
            return None, None, None

        # Count round wins by each team from all rounds
        ct_rounds_won = 0
        t_rounds_won = 0
        final_winner = None

        for round_info in rounds_rows:
            winner = self._pick_value(
                round_info,
                ["winner", "winner_side", "round_winner"],
            )

            if winner is None:
                continue

            winner_normalized = str(winner).upper().strip()

            # Track only the last winner as potential match winner
            if not final_winner:
                final_winner = winner_normalized

            # Count wins for each team (accept both "CT"/"T" and "ct"/"t" formats)
            if winner_normalized in {"CT", "CT_SIDE"}:
                ct_rounds_won += 1
            elif winner_normalized in {"T", "T_SIDE"}:
                t_rounds_won += 1

        # Validate scores
        total_rounds = ct_rounds_won + t_rounds_won
        if total_rounds == 0:
            return None, None, None

        # Determine match winner (first team to reach 13 wins, or higher score)
        match_winner = None
        if ct_rounds_won > t_rounds_won:
            match_winner = "CT"
        elif t_rounds_won > ct_rounds_won:
            match_winner = "T"
        else:
            match_winner = final_winner  # Tie, use last round winner

        self._log_stage(
            "SCOREBOARD",
            f"Extracted scores: CT={ct_rounds_won} T={t_rounds_won} winner={match_winner} total_rounds={total_rounds}",
            level="DEBUG",
        )

        return ct_rounds_won, t_rounds_won, match_winner

    def _extract_team_names(self, parsed_payload):
        """Resolve CT/T team names using latest round scoreboard-style side fields."""
        payload = parsed_payload or {}
        header = payload.get("header") or {}

        default_ct = str(header.get("ct_team") or header.get("team_ct") or "CT")
        default_t = str(header.get("t_team") or header.get("team_t") or "T")

        generic_ct = {
            "CT",
            "CT_SIDE",
            "COUNTER",
            "COUNTERTERRORIST",
            "COUNTER-TERRORIST",
            "COUNTER-TERRORISTS",
            "COUNTER_TERRORIST",
            "COUNTER_TERRORISTS",
        }
        generic_t = {
            "T",
            "T_SIDE",
            "TERRORIST",
            "TERRORISTS",
        }

        candidate_tables = [
            "rounds_stats",
            "rounds",
            "kills",
            "damages",
            "shots",
            "footsteps",
            "smokes",
            "infernos",
            "bomb",
        ]

        rows = []
        for table_name in candidate_tables:
            table_rows = self._iter_rows(payload.get(table_name))
            if table_rows:
                rows.extend(table_rows)

        if not rows:
            return default_ct, default_t

        max_round = None
        for row in rows:
            round_num = self._to_int(self._pick_value(row, ["round_num", "round", "round_number"]), default=0)
            if round_num > 0 and (max_round is None or round_num > max_round):
                max_round = round_num

        latest_rows = rows
        if max_round is not None:
            latest_rows = []
            for row in rows:
                round_num = self._to_int(self._pick_value(row, ["round_num", "round", "round_number"]), default=0)
                if round_num == max_round:
                    latest_rows.append(row)

        ct_counts = {}
        t_counts = {}

        for row in latest_rows:
            ct_value = self._pick_value(row, ["ct_side", "ct_team", "team_ct"])
            t_value = self._pick_value(row, ["t_side", "t_team", "team_t"])

            if ct_value is not None:
                ct_str = str(ct_value).strip()
                if ct_str:
                    ct_norm = ct_str.upper().replace(" ", "")
                    if ct_norm not in generic_ct:
                        ct_counts[ct_str] = ct_counts.get(ct_str, 0) + 1

            if t_value is not None:
                t_str = str(t_value).strip()
                if t_str:
                    t_norm = t_str.upper().replace(" ", "")
                    if t_norm not in generic_t:
                        t_counts[t_str] = t_counts.get(t_str, 0) + 1

        ct_team_name = default_ct
        t_team_name = default_t
        if ct_counts:
            ct_team_name = max(ct_counts.items(), key=lambda x: x[1])[0]
        if t_counts:
            t_team_name = max(t_counts.items(), key=lambda x: x[1])[0]

        return ct_team_name, t_team_name

    def _resolve_player_team_defaults(self, *, match_id, fallback_team1, fallback_team2, conn):
        team1 = str(fallback_team1 or "CT")
        team2 = str(fallback_team2 or "T")

        row = conn.execute(
            """
            SELECT team1_name, team2_name
            FROM matches
            WHERE match_id = ?
            LIMIT 1
            """,
            (str(match_id),),
        ).fetchone()

        if not row:
            return team1, team2

        existing_team1 = str(row["team1_name"] or "").strip()
        existing_team2 = str(row["team2_name"] or "").strip()

        if existing_team1:
            team1 = existing_team1
        if existing_team2:
            team2 = existing_team2

        return team1, team2

    def _build_weapon_stats_rows(self, *, match_id, map_number, parsed_payload):
        derived = (parsed_payload or {}).get("derived_weapon_stats")
        if not isinstance(derived, dict) or not derived:
            try:
                derived = demo_payload_analysis.build_derived_weapon_stats(parsed_payload or {})
                if isinstance(parsed_payload, dict):
                    parsed_payload["derived_weapon_stats"] = derived
                self._log_stage(
                    "RESTORE",
                    f"Rebuilt missing derived_weapon_stats match={match_id} map={map_number}",
                    level="DEBUG",
                )
            except Exception as e:
                self._log_stage(
                    "RESTORE",
                    f"Failed to rebuild derived_weapon_stats match={match_id} map={map_number}: {e}",
                    level="WARNING",
                )
                return [], []

        now = datetime.utcnow().isoformat()
        map_rows = []
        round_rows = []

        # Backward-compatible: older payloads stored {steamid -> {weapon -> metrics}} directly.
        map_payload = derived.get("map_rows") if isinstance(derived.get("map_rows"), dict) else derived
        round_payload = list(derived.get("round_rows") or [])

        if not round_payload:
            try:
                rebuilt = demo_payload_analysis.build_derived_weapon_stats(parsed_payload or {})
                if isinstance(rebuilt, dict):
                    round_payload = list(rebuilt.get("round_rows") or [])
                    if isinstance(parsed_payload, dict):
                        parsed_payload["derived_weapon_stats"] = {
                            "map_rows": map_payload,
                            "round_rows": round_payload,
                        }
                    self._log_stage(
                        "RESTORE",
                        f"Rebuilt missing weapon round rows match={match_id} map={map_number}",
                        level="DEBUG",
                    )
            except Exception as e:
                self._log_stage(
                    "RESTORE",
                    f"Failed to rebuild weapon round rows match={match_id} map={map_number}: {e}",
                    level="WARNING",
                )

        for steamid64, weapon_map in map_payload.items():
            sid = self._to_steamid64_string(steamid64)
            if sid is None:
                continue
            if not isinstance(weapon_map, dict):
                continue

            for weapon, metrics in weapon_map.items():
                weapon_name = str(weapon or "").strip().lower()
                if not weapon_name:
                    continue

                values = metrics if isinstance(metrics, dict) else {}
                map_rows.append(
                    {
                        "steamid64": str(sid),
                        "match_id": str(match_id),
                        "map_number": int(map_number),
                        "weapon": weapon_name,
                        "shots_fired": int(values.get("shots_fired") or 0),
                        "shots_hit": int(values.get("shots_hit") or 0),
                        "kills": int(values.get("kills") or 0),
                        "headshot_kills": int(values.get("headshot_kills") or 0),
                        "damage": int(values.get("damage") or 0),
                        "rounds_with_weapon": int(values.get("rounds_with_weapon") or 0),
                        "first_seen_at": now,
                        "updated_at": now,
                    }
                )

        for row in round_payload:
            sid = self._to_steamid64_string(row.get("steamid"))
            if sid is None:
                continue
            round_num = self._to_int(row.get("round_num"), default=0)
            if round_num <= 0:
                continue
            weapon_name = str(row.get("weapon") or "").strip().lower()
            if not weapon_name:
                continue

            round_rows.append(
                {
                    "steamid64": str(sid),
                    "match_id": str(match_id),
                    "map_number": int(map_number),
                    "round_num": int(round_num),
                    "weapon": weapon_name,
                    "shots_fired": int(row.get("shots_fired") or 0),
                    "shots_hit": int(row.get("shots_hit") or 0),
                    "kills": int(row.get("kills") or 0),
                    "headshot_kills": int(row.get("headshot_kills") or 0),
                    "damage": int(row.get("damage") or 0),
                    "updated_at": now,
                }
            )

        return map_rows, round_rows

    def _build_movement_stats_rows(self, *, match_id, map_number, parsed_payload):
        derived = (parsed_payload or {}).get("derived_movement_stats")
        if not isinstance(derived, dict) or not derived:
            try:
                derived = demo_payload_analysis.build_derived_movement_stats(parsed_payload or {})
                if isinstance(parsed_payload, dict):
                    parsed_payload["derived_movement_stats"] = derived
                self._log_stage(
                    "RESTORE",
                    f"Rebuilt missing derived_movement_stats match={match_id} map={map_number}",
                    level="DEBUG",
                )
            except Exception as e:
                self._log_stage(
                    "RESTORE",
                    f"Failed to rebuild derived_movement_stats match={match_id} map={map_number}: {e}",
                    level="WARNING",
                )
                return [], [], []

        now = datetime.utcnow().isoformat()
        map_rows = []
        round_rows = []
        bin_rows = []

        for row in (derived.get("map_rows") or []):
            sid = self._to_steamid64_string(row.get("steamid"))
            if sid is None:
                continue
            map_rows.append(
                {
                    "steamid64": str(sid),
                    "match_id": str(match_id),
                    "map_number": int(map_number),
                    "total_distance_units": float(row.get("total_distance_units") or 0.0),
                    "total_distance_m": float(row.get("total_distance_m") or 0.0),
                    "avg_speed_units_s": float(row.get("avg_speed_units_s") or 0.0),
                    "avg_speed_m_s": float(row.get("avg_speed_m_s") or 0.0),
                    "max_speed_units_s": float(row.get("max_speed_units_s") or 0.0),
                    "ticks_alive": int(row.get("ticks_alive") or 0),
                    "alive_seconds": float(row.get("alive_seconds") or 0.0),
                    "distance_per_round_units": float(row.get("distance_per_round_units") or 0.0),
                    "freeze_distance_units": float(row.get("freeze_distance_units") or 0.0),
                    "strafe_distance_units": float(row.get("strafe_distance_units") or 0.0),
                    "strafe_ratio": float(row.get("strafe_ratio") or 0.0),
                    "stationary_ticks": int(row.get("stationary_ticks") or 0),
                    "camp_time_s": float(row.get("camp_time_s") or 0.0),
                    "sprint_ticks": int(row.get("sprint_ticks") or 0),
                    "sprint_time_s": float(row.get("sprint_time_s") or 0.0),
                    "stationary_ratio": float(row.get("stationary_ratio") or 0.0),
                    "sprint_ratio": float(row.get("sprint_ratio") or 0.0),
                    "strafe_ticks": int(row.get("strafe_ticks") or 0),
                    "strafe_time_s": float(row.get("strafe_time_s") or 0.0),
                    "updated_at": now,
                }
            )

        for row in (derived.get("round_rows") or []):
            sid = self._to_steamid64_string(row.get("steamid"))
            round_num = self._to_int(row.get("round_num"), default=0)
            if sid is None or round_num <= 0:
                continue
            round_rows.append(
                {
                    "steamid64": str(sid),
                    "match_id": str(match_id),
                    "map_number": int(map_number),
                    "round_num": int(round_num),
                    "side": str(row.get("side") or ""),
                    "distance_units": float(row.get("distance_units") or 0.0),
                    "live_distance_units": float(row.get("live_distance_units") or 0.0),
                    "freeze_distance_units": float(row.get("freeze_distance_units") or 0.0),
                    "strafe_distance_units": float(row.get("strafe_distance_units") or 0.0),
                    "strafe_ratio": float(row.get("strafe_ratio") or 0.0),
                    "avg_speed_units_s": float(row.get("avg_speed_units_s") or 0.0),
                    "max_speed_units_s": float(row.get("max_speed_units_s") or 0.0),
                    "ticks_alive": int(row.get("ticks_alive") or 0),
                    "alive_seconds": float(row.get("alive_seconds") or 0.0),
                    "stationary_ticks": int(row.get("stationary_ticks") or 0),
                    "camp_time_s": float(row.get("camp_time_s") or 0.0),
                    "sprint_ticks": int(row.get("sprint_ticks") or 0),
                    "sprint_time_s": float(row.get("sprint_time_s") or 0.0),
                    "strafe_ticks": int(row.get("strafe_ticks") or 0),
                    "strafe_time_s": float(row.get("strafe_time_s") or 0.0),
                    "updated_at": now,
                }
            )

        for row in (derived.get("timeline_bins") or []):
            sid = self._to_steamid64_string(row.get("steamid"))
            round_num = self._to_int(row.get("round_num"), default=0)
            if sid is None or round_num <= 0:
                continue
            bin_rows.append(
                {
                    "steamid64": str(sid),
                    "match_id": str(match_id),
                    "map_number": int(map_number),
                    "round_num": int(round_num),
                    "bin_index": int(row.get("bin_index") or 0),
                    "bin_start_sec": float(row.get("bin_start_sec") or 0.0),
                    "median_speed_m_s": float(row.get("median_speed_m_s") or 0.0),
                    "mean_speed_m_s": float(row.get("mean_speed_m_s") or 0.0),
                    "p25_speed_m_s": float(row.get("p25_speed_m_s") or 0.0),
                    "p75_speed_m_s": float(row.get("p75_speed_m_s") or 0.0),
                    "max_speed_m_s": float(row.get("max_speed_m_s") or 0.0),
                    "alive_ratio": float(row.get("alive_ratio") or 0.0),
                    "samples": int(row.get("samples") or 0),
                    "speed_samples": int(row.get("speed_samples") or 0),
                    "side": str(row.get("side") or ""),
                    "updated_at": now,
                }
            )

        return map_rows, round_rows, bin_rows

    def _build_round_events_rows(self, *, match_id, map_number, parsed_payload):
        derived = (parsed_payload or {}).get("derived_round_events")
        if not isinstance(derived, dict) or not derived:
            try:
                derived = demo_payload_analysis.build_derived_round_events(parsed_payload or {})
                if isinstance(parsed_payload, dict):
                    parsed_payload["derived_round_events"] = derived
                self._log_stage(
                    "RESTORE",
                    f"Rebuilt missing derived_round_events match={match_id} map={map_number}",
                    level="DEBUG",
                )
            except Exception as e:
                self._log_stage(
                    "RESTORE",
                    f"Failed to rebuild derived_round_events match={match_id} map={map_number}: {e}",
                    level="WARNING",
                )
                return []

        now = datetime.utcnow().isoformat()
        rows = []
        for row in (derived.get("round_rows") or []):
            sid = self._to_steamid64_string(row.get("steamid"))
            round_num = self._to_int(row.get("round_num"), default=0)
            if sid is None or round_num <= 0:
                continue
            rows.append(
                {
                    "steamid64": str(sid),
                    "match_id": str(match_id),
                    "map_number": int(map_number),
                    "round_num": int(round_num),
                    "side": str(row.get("side") or ""),
                    "opening_attempt": int(row.get("opening_attempt") or 0),
                    "opening_win": int(row.get("opening_win") or 0),
                    "trade_kill_count": int(row.get("trade_kill_count") or 0),
                    "traded_death_count": int(row.get("traded_death_count") or 0),
                    "clutch_enemy_count": int(row.get("clutch_enemy_count") or 0),
                    "clutch_win": int(row.get("clutch_win") or 0),
                    "won_round": int(row.get("won_round") or 0),
                    "updated_at": now,
                }
            )

        return rows

    def _restore_db_entities_from_payload(
        self,
        match_id,
        map_number,
        parsed_payload,
        source_file,
        payload_sha256,
        conn,
        source_match_to_canonical,
        next_local_match_id_state,
    ):
        self._ensure_not_cancelled(stage="restore")

        if not isinstance(parsed_payload, dict):
            return False, 0, None, None

        header = parsed_payload.get("header") or {}
        map_name = str(header.get("map_name") or "unknown")
        clustered = self._build_clustered_match_result(parsed_payload)
        team1_name = clustered.get("team1_name")
        team2_name = clustered.get("team2_name")
        team1_score = clustered.get("team1_score")
        team2_score = clustered.get("team2_score")
        winner = clustered.get("winner")
        stable_player_teams = clustered.get("player_team_map") or {}

        source_name = Path(str(source_file or "")).name
        date = None
        time = None
        try:
            base_name = source_name
            if base_name.endswith(".pkl"):
                base_name = base_name[:-4]
            if base_name.endswith(".dem"):
                base_name = base_name[:-4]

            parts = base_name.split("_")
            if len(parts) >= 2:
                date = parts[0]
                time = parts[1]
        except Exception:
            pass

        played_at = self._iso_from_filename_bits(date, time)

        parsed_match_key = str(match_id)
        preferred_match_id = source_match_to_canonical.get(parsed_match_key)
        next_local_match_id = int(next_local_match_id_state["value"])

        target_match_id, target_map_number = self._resolve_restore_target(
            parsed_match_id=match_id,
            parsed_map_number=map_number,
            parsed_payload=parsed_payload,
            played_at=played_at,
            map_name=map_name,
            team1_name=team1_name,
            team2_name=team2_name,
            team1_score=team1_score,
            team2_score=team2_score,
            preferred_match_id=preferred_match_id,
            next_local_match_id=next_local_match_id,
            conn=conn,
        )

        self._ensure_not_cancelled(stage="restore")

        if parsed_match_key not in source_match_to_canonical:
            source_match_to_canonical[parsed_match_key] = str(target_match_id)

        try:
            target_match_id_int = int(target_match_id)
            if int(next_local_match_id_state["value"]) <= target_match_id_int:
                next_local_match_id_state["value"] = target_match_id_int + 1
        except Exception:
            pass

        # Keep restoration idempotent by upserting into canonical rows, even if they already exist.
        if match_map_has_player_stats(target_match_id, target_map_number, conn=conn):
            self._log_stage(
                "RESTORE",
                (
                    "UPSERT existing canonical payload "
                    f"source=({match_id},{map_number}) target=({target_match_id},{target_map_number})"
                ),
                level="INFO",
            )

        player_team1_name, player_team2_name = self._resolve_player_team_defaults(
            match_id=target_match_id,
            fallback_team1=team1_name,
            fallback_team2=team2_name,
            conn=conn,
        )

        self._ensure_not_cancelled(stage="restore")

        player_rows = self._build_player_stats_rows(
            match_id=target_match_id,
            map_number=target_map_number,
            parsed_payload=parsed_payload,
            stable_player_teams=stable_player_teams,
            default_team1_name=player_team1_name,
            default_team2_name=player_team2_name,
        )
        weapon_rows, weapon_round_rows = self._build_weapon_stats_rows(
            match_id=target_match_id,
            map_number=target_map_number,
            parsed_payload=parsed_payload,
        )
        movement_map_rows, movement_round_rows, movement_bin_rows = self._build_movement_stats_rows(
            match_id=target_match_id,
            map_number=target_map_number,
            parsed_payload=parsed_payload,
        )
        round_event_rows = self._build_round_events_rows(
            match_id=target_match_id,
            map_number=target_map_number,
            parsed_payload=parsed_payload,
        )

        self._ensure_not_cancelled(stage="restore")

        # Batch all inserts for this match into a single transaction to reduce lock acquisitions
        with write_transaction(conn):
            self._ensure_not_cancelled(stage="restore")
            insert_match(
                {
                    "match_id": str(target_match_id),
                    "start_time": played_at,
                    "end_time": played_at,
                    "winner": winner,
                    "series_type": None,
                    "team1_name": str(team1_name),
                    "team1_score": team1_score,
                    "team2_name": str(team2_name),
                    "team2_score": team2_score,
                    "server_ip": None,
                },
                conn=conn,
            )

            insert_match_map(
                {
                    "match_id": str(target_match_id),
                    "map_number": int(target_map_number),
                    "map_name": map_name,
                    "start_time": played_at,
                    "end_time": played_at,
                    "winner": winner,
                    "team1_score": team1_score,
                    "team2_score": team2_score,
                },
                conn=conn,
            )

            insert_match_player_stats_many(player_rows, conn=conn)
            upsert_player_map_weapon_stats_many(weapon_rows, conn=conn)
            upsert_player_round_weapon_stats_many(weapon_round_rows, conn=conn)
            upsert_player_map_movement_stats_many(movement_map_rows, conn=conn)
            upsert_player_round_movement_stats_many(movement_round_rows, conn=conn)
            upsert_player_round_timeline_bins_many(movement_bin_rows, conn=conn)
            upsert_player_round_events_many(round_event_rows, conn=conn)

            set_match_has_demo(match_id=target_match_id, has_demo=True, conn=conn)

            self._ensure_not_cancelled(stage="restore")

        self._ensure_canonical_cache_alias(
            source_match_id=match_id,
            source_map_number=map_number,
            canonical_match_id=target_match_id,
            canonical_map_number=target_map_number,
            parsed_payload=parsed_payload,
            source_file=source_file,
        )

        upsert_restore_signature(
            source_match_id=match_id,
            source_map_number=map_number,
            payload_sha256=payload_sha256,
            canonical_match_id=target_match_id,
            canonical_map_number=target_map_number,
            source_file=source_file,
            conn=conn,
        )
        return True, len(player_rows), str(target_match_id), int(target_map_number)

    def _discover_orphaned_cache_files(self):
        """Scan for .pkl files that exist on disk but not in index.json."""
        orphaned = []
        try:
            cache_dir = Path(self.parsed_demo_dir)
            if not cache_dir.exists():
                return orphaned

            index = demo_cache.load_index(self.parsed_demo_dir)
            indexed_files = {
                row.get("filename")
                for row in index.values()
                if isinstance(row, dict) and row.get("filename")
            }

            for pkl_file in cache_dir.glob("*.pkl"):
                filename = pkl_file.name
                if filename in indexed_files:
                    continue

                try:
                    parts = filename.replace(".pkl", "").split("_")
                    match_idx = -1
                    map_idx = -1

                    for i, part in enumerate(parts):
                        if part == "match" and i + 1 < len(parts):
                            match_idx = i + 1
                        if part == "map" and i + 1 < len(parts):
                            map_idx = i + 1

                    if match_idx > 0 and map_idx > match_idx:
                        match_id = int(parts[match_idx])
                        map_number = int(parts[map_idx])
                        orphaned.append(
                            {
                                "filename": filename,
                                "match_id": match_id,
                                "map_number": map_number,
                                "filepath": pkl_file,
                            }
                        )
                except Exception:
                    pass
        except Exception as e:
            logger.log_warning(f"[RESTORE] Error discovering orphaned cache files: {e}")

        return orphaned

    def restore_db_from_parsed_cache(self, progress_start=None, progress_end=None, rows=None, include_orphaned=True):
        self._ensure_not_cancelled(stage="restore")

        if rows is None:
            rows = demo_cache.list_existing_cached_demos(self.parsed_demo_dir)
        else:
            rows = [r for r in rows if isinstance(r, dict)]

        rows = sorted(rows, key=self._parse_cache_row_played_at)
        orphaned_files = self._discover_orphaned_cache_files() if include_orphaned else []
        total = max(1, len(rows) + len(orphaned_files))

        restored_maps = 0
        restored_players = 0
        skipped = 0
        failed = 0
        canonical_match_ids = set()
        canonical_match_maps = set()

        self._log_stage(
            "RESTORE",
            f"Rebuilding DB from cache rows={len(rows)} orphaned_files={len(orphaned_files)}",
        )

        with get_conn(db_file=self.db_file) as conn:
            source_match_to_canonical = {}
            next_local_match_id_state = {
                "value": int(get_next_local_match_id(conn=conn, start_from=1))
            }

            for idx, row in enumerate(rows, start=1):
                self._ensure_not_cancelled(stage="restore")

                match_id = row.get("match_id") if isinstance(row, dict) else None
                map_number = row.get("map_number") if isinstance(row, dict) else None
                if match_id is None or map_number is None:
                    continue

                if progress_start is not None and progress_end is not None:
                    span = max(0, int(progress_end) - int(progress_start))
                    percent = int(progress_start) + int((idx - 1) / total * span)
                    self._emit_progress(
                        percent,
                        f"Writing demo {idx}/{total}",
                        stage="database",
                    )

                try:
                    self._ensure_not_cancelled(stage="restore")
                    payload_sha256 = demo_cache.compute_payload_sha256(
                        cache_dir=self.parsed_demo_dir,
                        match_id=match_id,
                        map_number=map_number,
                        filename=row.get("filename"),
                    )

                    if is_restore_signature_current(
                        source_match_id=match_id,
                        source_map_number=map_number,
                        payload_sha256=payload_sha256,
                        conn=conn,
                    ):
                        skipped += 1
                        self._log_stage(
                            "RESTORE",
                            (
                                "SKIP unchanged payload "
                                f"match={match_id} map={map_number} sha256={str(payload_sha256)[:12]}"
                            ),
                            level="INFO",
                        )
                        continue

                    payload = demo_cache.load_parsed_demo(
                        cache_dir=self.parsed_demo_dir,
                        match_id=match_id,
                        map_number=map_number,
                    )
                    self._ensure_not_cancelled(stage="restore")
                    restored, inserted, canonical_match_id, canonical_map_number = self._restore_db_entities_from_payload(
                        match_id=match_id,
                        map_number=map_number,
                        parsed_payload=payload,
                        source_file=row.get("source_file") or row.get("filename"),
                        payload_sha256=payload_sha256,
                        conn=conn,
                        source_match_to_canonical=source_match_to_canonical,
                        next_local_match_id_state=next_local_match_id_state,
                    )
                    if restored:
                        restored_maps += 1
                        restored_players += inserted
                        canonical_match_ids.add(str(canonical_match_id))
                        canonical_match_maps.add((str(canonical_match_id), int(canonical_map_number)))
                except Exception as e:
                    failed += 1
                    self._log_stage(
                        "RESTORE",
                        f"FAILED match={match_id} map={map_number}: {e}",
                        level="ERROR",
                    )

            for idx, orphan in enumerate(orphaned_files, start=len(rows) + 1):
                self._ensure_not_cancelled(stage="restore")

                match_id = orphan.get("match_id")
                map_number = orphan.get("map_number")
                filename = orphan.get("filename")

                if progress_start is not None and progress_end is not None:
                    span = max(0, int(progress_end) - int(progress_start))
                    percent = int(progress_start) + int((idx - 1) / total * span)
                    self._emit_progress(
                        percent,
                        f"Writing demo {idx}/{total}",
                        stage="database",
                    )

                try:
                    self._ensure_not_cancelled(stage="restore")
                    payload_sha256 = demo_cache.compute_payload_sha256(
                        cache_dir=self.parsed_demo_dir,
                        match_id=match_id,
                        map_number=map_number,
                        filename=filename,
                    )

                    if is_restore_signature_current(
                        source_match_id=match_id,
                        source_map_number=map_number,
                        payload_sha256=payload_sha256,
                        conn=conn,
                    ):
                        skipped += 1
                        self._log_stage(
                            "RESTORE",
                            (
                                "SKIP unchanged orphaned payload "
                                f"match={match_id} map={map_number} sha256={str(payload_sha256)[:12]}"
                            ),
                            level="INFO",
                        )
                        continue

                    payload = demo_cache.load_parsed_demo(
                        cache_dir=self.parsed_demo_dir,
                        match_id=match_id,
                        map_number=map_number,
                    )
                    self._ensure_not_cancelled(stage="restore")
                    self._log_stage(
                        "RESTORE",
                        f"Restoring orphaned cache match={match_id} map={map_number} file={filename}",
                        level="DEBUG",
                    )
                    restored, inserted, canonical_match_id, canonical_map_number = self._restore_db_entities_from_payload(
                        match_id=match_id,
                        map_number=map_number,
                        parsed_payload=payload,
                        source_file=filename,
                        payload_sha256=payload_sha256,
                        conn=conn,
                        source_match_to_canonical=source_match_to_canonical,
                        next_local_match_id_state=next_local_match_id_state,
                    )
                    if restored:
                        restored_maps += 1
                        restored_players += inserted
                        canonical_match_ids.add(str(canonical_match_id))
                        canonical_match_maps.add((str(canonical_match_id), int(canonical_map_number)))

                        manifest_entry = {
                            "match_id": int(match_id),
                            "map_number": int(map_number),
                            "cache_key": f"match_{match_id}_map_{map_number}",
                            "filename": filename,
                            "compression": "none",
                            "source_file": str(filename),
                            "updated_at": datetime.utcnow().isoformat(),
                            "header": (payload or {}).get("header", {}) if isinstance(payload, dict) else {},
                        }
                        index = demo_cache.load_index(self.parsed_demo_dir)
                        index[f"match_{match_id}_map_{map_number}"] = manifest_entry
                        demo_cache.save_index(self.parsed_demo_dir, index)
                        self._log_stage(
                            "RESTORE",
                            f"Updated cache index for orphaned match={match_id} map={map_number}",
                            level="DEBUG",
                        )
                except Exception as e:
                    failed += 1
                    self._log_stage(
                        "RESTORE",
                        f"FAILED orphaned match={match_id} map={map_number}: {e}",
                        level="ERROR",
                    )

            # Do not rewrite canonical match ids after restore.
            # Reindexing numeric IDs can mutate upstream MatchZy ids (e.g. 10/11/12)
            # and make subsequent sync runs re-import already known matches.

        if progress_start is not None and progress_end is not None:
            self._emit_progress(int(progress_end), "Database updated", stage="database")

        self._log_stage(
            "RESTORE",
            f"Summary restored_maps={restored_maps} restored_players={restored_players} skipped={skipped} failed={failed}",
        )
        return {
            "restored_maps": restored_maps,
            "restored_players": restored_players,
            "skipped": skipped,
            "failed": failed,
            "cache_rows": len(rows),
            "orphaned_files": len(orphaned_files),
            "canonical_match_ids": sorted(canonical_match_ids, key=lambda v: int(v) if str(v).isdigit() else 10**12),
            "canonical_match_maps": [
                {"match_id": mid, "map_number": mnum}
                for mid, mnum in sorted(canonical_match_maps, key=lambda p: (int(p[0]) if str(p[0]).isdigit() else 10**12, int(p[1])))
            ],
        }
