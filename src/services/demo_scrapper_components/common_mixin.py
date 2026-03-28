import math
import zlib

import pandas as pd
import polars as pl
from analytics import demo_payload_analysis

from db.demo_db import get_expected_demo_players, resolve_map_number
from services import demo_cache
import services.logger as logger

try:
    from awpy import stats as awpy_stats
except ImportError:
    awpy_stats = None


class DemoScrapperCommonMixin:
    def extract_match_id(self, filename):
        try:
            return int(filename.split("_")[2])
        except Exception:
            return None

    @staticmethod
    def extract_parts(filename):
        # 2026-03-20_22-48-10_4_cs_office_team_...vs_...
        parts = filename.replace(".dem", "").split("_")

        try:
            date = parts[0]
            time = parts[1]
            match_id = str(parts[2])
            map_name = f"{parts[3]}_{parts[4]}"
            return date, time, match_id, map_name
        except Exception:
            return None, None, None, None

    @staticmethod
    def _to_int_or_none(value):
        try:
            if value is None:
                return None
            return int(str(value).strip())
        except Exception:
            return None

    @staticmethod
    def _build_recovery_match_id(date, time, raw_match_id, filename):
        seed = f"{date}_{time}_{raw_match_id}_{filename}"
        # Keep recovered ids negative to avoid collisions with MatchZy ids.
        return -1 - (zlib.crc32(seed.encode("utf-8")) & 0x7FFFFFFF)

    @staticmethod
    def _build_recovery_map_number(match_id, map_name, filename):
        # Use map 0 as canonical fallback when the source map id is missing/unreliable.
        return 0

    @staticmethod
    def _normalize_map_number(value, default=0):
        number = DemoScrapperCommonMixin._to_int_or_none(value)
        if number is None:
            return int(default)

        # Real map numbers in this app are small (0,1,2,...) and random hash-like
        # ids can leak in from fallback naming. Treat outliers as unknown map 0.
        if number < 0:
            return int(default)
        if number > 100:
            return int(default)

        return int(number)

    def _normalize_demo_identity(self, remote_filename):
        date, time, raw_match_id, map_name = self.extract_parts(remote_filename)
        if not date or not time or not map_name:
            return None

        parsed_match_id = self._to_int_or_none(raw_match_id)
        normalized_match_id = (
            parsed_match_id
            if parsed_match_id is not None and parsed_match_id > 0
            else self._build_recovery_match_id(date, time, raw_match_id, remote_filename)
        )

        map_number = None
        if parsed_match_id is not None and str(parsed_match_id) in self.valid_match_ids:
            map_number = resolve_map_number(self.match_catalog, str(parsed_match_id), map_name)

        recovered_from_catalog_miss = False
        if map_number is None:
            map_number = self._build_recovery_map_number(
                match_id=normalized_match_id,
                map_name=map_name,
                filename=remote_filename,
            )
            recovered_from_catalog_miss = True

        map_number = self._normalize_map_number(map_number, default=0)

        normalized_name = (
            f"{date}_{time}_match_{normalized_match_id}_map_{map_number}_{map_name}.dem"
        )
        return {
            "date": date,
            "time": time,
            "raw_match_id": raw_match_id,
            "match_id": normalized_match_id,
            "map_name": map_name,
            "map_number": int(map_number),
            "normalized_name": normalized_name,
            "recovered_from_catalog_miss": recovered_from_catalog_miss,
        }

    @staticmethod
    def _iter_rows(table):
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

    @staticmethod
    def _pick_value(row, keys):
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

    @staticmethod
    def _to_int(value, default=0):
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

    @staticmethod
    def _iso_from_filename_bits(date, time):
        try:
            if not date or not time:
                return None
            parts = time.split("-")
            if len(parts) != 3:
                return None
            return f"{date}T{parts[0]}:{parts[1]}:{parts[2]}"
        except Exception:
            return None

    @staticmethod
    def _normalize_side_label(value):
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

    @staticmethod
    def _to_steamid64_string(value):
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

        # Ignore non-player ids like 0 or tiny integers.
        if number < 10_000_000_000_000_000:
            return None

        return str(number)

    @staticmethod
    def _steamid_like_column(col_name):
        normalized = str(col_name).lower().replace("-", "_")
        return "steamid" in normalized or "steam_id" in normalized

    @staticmethod
    def _get_table_columns(table):
        if isinstance(table, pd.DataFrame):
            return [str(c) for c in table.columns]
        if isinstance(table, pl.DataFrame):
            return [str(c) for c in table.columns]
        return []

    def extract_demo_steamids(self, data):
        steamids = set()

        table_candidates = [
            data.get("player_round_totals"),
            data.get("kills"),
            data.get("damages"),
            data.get("shots"),
            data.get("grenades"),
            data.get("footsteps"),
        ]

        scanned_columns = []

        for table in table_candidates:
            if isinstance(table, pd.DataFrame):
                if table.empty:
                    continue

                for col in table.columns:
                    col_name = str(col)
                    scanned_columns.append(col_name)
                    if not self._steamid_like_column(col_name):
                        continue

                    for value in table[col].dropna().tolist():
                        sid = self._to_steamid64_string(value)
                        if sid:
                            steamids.add(sid)

                continue

            if isinstance(table, pl.DataFrame):
                if table.height == 0:
                    continue

                for col in table.columns:
                    col_name = str(col)
                    scanned_columns.append(col_name)
                    if not self._steamid_like_column(col_name):
                        continue

                    for value in table.get_column(col).drop_nulls().to_list():
                        sid = self._to_steamid64_string(value)
                        if sid:
                            steamids.add(sid)

        if not steamids and scanned_columns:
            logger.log_debug(f"[Validator] Scanned columns without steamid hit: {sorted(set(scanned_columns))}")

        return steamids

    def validate_demo_players(self, match_id, map_number, data, conn=None):
        expected_players = get_expected_demo_players(
            match_id=match_id,
            map_number=map_number,
            conn=conn,
        )

        if not expected_players:
            logger.log_warning(
                f"[Validator] No expected players in DB for match={match_id}, map={map_number}; accepting demo"
            )
            return True

        parsed_players = self.extract_demo_steamids(data)

        if not parsed_players:
            logger.log_warning(
                f"[Validator] No parsed steamids for match={match_id}, map={map_number}; rejecting demo"
            )
            return False

        is_valid = expected_players == parsed_players

        if not is_valid:
            missing = sorted(expected_players - parsed_players)
            extra = sorted(parsed_players - expected_players)
            logger.log_debug(
                "[Validator] "
                f"match={match_id} map={map_number} missing={missing} extra={extra}"
            )

        logger.log_info(
            "[Validator] "
            f"match={match_id} map={map_number} "
            f"expected={len(expected_players)} parsed={len(parsed_players)} valid={is_valid}"
        )

        return is_valid

    @staticmethod
    def extract_ids_from_normalized(filename):
        # 2026-03-20_22-48-10_match_4_map_1_cs_office.dem
        parts = filename.replace(".dem", "").split("_")

        try:
            # find dynamic positions (safer than fixed indices)
            match_idx = parts.index("match")
            map_idx = parts.index("map")

            match_id = int(parts[match_idx + 1])
            map_number = DemoScrapperCommonMixin._normalize_map_number(parts[map_idx + 1], default=0)

            return match_id, map_number
        except Exception:
            return None, None

    @staticmethod
    def parse_demo_full(demo):
        data = {"header": demo.header}

        for raw_key in ["events", "game_events", "ticks_df"]:
            try:
                raw_value = getattr(demo, raw_key, None)
                if raw_value is not None:
                    data[raw_key] = raw_value
            except Exception:
                data[raw_key] = None

        table_map = {
            "rounds": "rounds",
            "rounds_stats": "rounds_stats",
            "kills": "kills",
            "damages": "damages",
            "grenades": "grenades",
            "shots": "shots",
            "footsteps": "footsteps",
            "smokes": "smokes",
            "infernos": "infernos",
            "bomb": "bomb",
            "bomb_plants": "bomb_plants",
            "bomb_defuses": "bomb_defuses",
            "ticks": "ticks",
            "frames": "frames",
            "player_frames": "player_frames",
            "player_round_totals": "player_round_totals",
            "weapon_fires": "weapon_fires",
            "flashes": "flashes",
            "hegrenades": "hegrenades",
            "server_cvars": "server_cvars",
            # Try to capture economy-related tables if available
            "player_economy": "player_economy",
            "player_round_economy": "player_round_economy",
            "team_rounds_stats": "team_rounds_stats",
            "team_round_purchase": "team_round_purchase",
        }

        for key, attr in table_map.items():
            try:
                value = getattr(demo, attr, None)

                if value is None:
                    data[key] = None
                    continue

                if isinstance(value, pd.DataFrame):
                    df = value
                elif isinstance(value, list):
                    df = pd.DataFrame(value)
                else:
                    df = value

                data[key] = df

            except Exception:
                data[key] = None

        # Store lightweight derived artifacts in cache so downstream stats/timeline
        # can work without recomputing fragile heuristics from raw tables.
        try:
            data["derived_player_stats"] = demo_payload_analysis.build_derived_player_stats(data)
            data["derived_round_timeline"] = demo_payload_analysis.build_derived_round_timeline(data)
            data["derived_restore_stats"] = demo_payload_analysis.build_derived_restore_stats(data)
            data["derived_weapon_stats"] = demo_payload_analysis.build_derived_weapon_stats(data)
        except Exception:
            data["derived_player_stats"] = {}
            data["derived_round_timeline"] = []
            data["derived_restore_stats"] = {}
            data["derived_weapon_stats"] = {}

        # Compute advanced awpy stats functions if available
        # These provide precomputed aggregates (ADR, KAST, Impact, Rating, etc.)
        # that avoid re-derivation downstream
        if awpy_stats is not None:
            try:
                # ADR: Average Damage Per Round
                try:
                    adr_result = awpy_stats.adr(demo)
                    data["stats_adr"] = adr_result if adr_result is not None else None
                except (AttributeError, ValueError, KeyError, Exception) as e:
                    data["stats_adr"] = None

                # KAST: Kill-Assist-Survival-Trade %
                try:
                    kast_result = awpy_stats.kast(demo)
                    data["stats_kast"] = kast_result if kast_result is not None else None
                except (AttributeError, ValueError, KeyError, Exception) as e:
                    data["stats_kast"] = None

                # Impact rating
                try:
                    impact_result = awpy_stats.impact(demo)
                    data["stats_impact"] = impact_result if impact_result is not None else None
                except (AttributeError, ValueError, KeyError, Exception) as e:
                    data["stats_impact"] = None

                # Rating (HLTV-like)
                try:
                    rating_result = awpy_stats.rating(demo)
                    data["stats_rating"] = rating_result if rating_result is not None else None
                except (AttributeError, ValueError, KeyError, Exception) as e:
                    data["stats_rating"] = None

                # Trades
                try:
                    if data.get("kills") is not None:
                        trades_result = awpy_stats.calculate_trades(demo)
                        data["stats_trades"] = trades_result if trades_result is not None else None
                    else:
                        data["stats_trades"] = None
                except (AttributeError, ValueError, KeyError, Exception) as e:
                    data["stats_trades"] = None

            except Exception as e:
                # Silently fail - stats are optional enhancements
                data["stats_adr"] = None
                data["stats_kast"] = None
                data["stats_impact"] = None
                data["stats_rating"] = None
                data["stats_trades"] = None
        else:
            # awpy.stats not imported
            data["stats_adr"] = None
            data["stats_kast"] = None
            data["stats_impact"] = None
            data["stats_rating"] = None
            data["stats_trades"] = None

        return data

    @staticmethod
    def _round_winner_side_map(parsed_payload):
        return demo_payload_analysis.round_winner_side_map(parsed_payload)

    @staticmethod
    def _build_derived_round_timeline(parsed_payload):
        return demo_payload_analysis.build_derived_round_timeline(parsed_payload)

    @staticmethod
    def _build_derived_player_stats(parsed_payload):
        return demo_payload_analysis.build_derived_player_stats(parsed_payload)

    @staticmethod
    def _verify_cached_roundtrip(match_id, map_number, data, cached_data):
        source_stats = demo_cache.payload_table_stats(data)
        cached_stats = demo_cache.payload_table_stats(cached_data)

        source_keys = set(source_stats.keys())
        cached_keys = set(cached_stats.keys())

        if source_keys != cached_keys:
            missing = sorted(source_keys - cached_keys)
            extra = sorted(cached_keys - source_keys)
            logger.log_warning(
                "[CACHE] Roundtrip key mismatch "
                f"match={match_id} map={map_number} missing={missing} extra={extra}"
            )
            return

        diffs = []
        for key in sorted(source_keys):
            if source_stats[key] != cached_stats[key]:
                diffs.append(key)

        if diffs:
            logger.log_warning(
                "[CACHE] Roundtrip table stats mismatch "
                f"match={match_id} map={map_number} keys={diffs}"
            )
            return

        logger.log_debug(
            f"[CACHE] Roundtrip verified match={match_id} map={map_number} tables={len(source_keys)}"
        )

    @staticmethod
    def print_headers(data, preview=False):
        logger.log_info("=== TABLE HEADERS ===")

        for key, value in data.items():
            logger.log_info(f"[TABLE] {key}")

            if value is None:
                logger.log_info("  -> None")
                continue

            if isinstance(value, pd.DataFrame):
                logger.log_info(f"  Rows: {len(value)}")
                logger.log_info(f"  Columns ({len(value.columns)}):")
                for col in value.columns:
                    logger.log_info(f"    - {col}")

                if preview:
                    logger.log_info("  Preview:")
                    logger.log_info(f"{value.head(3)}")

            elif isinstance(value, pl.DataFrame):
                logger.log_info(f"  Rows: {value.height}")
                logger.log_info(f"  Columns ({len(value.columns)}):")
                for col in value.columns:
                    logger.log_info(f"    - {col}")

            else:
                logger.log_info(f"  Type: {type(value).__name__}")

    @staticmethod
    def get_cvars(data):
        cvars = data.get("server_cvars")
        if cvars is None:
            logger.log_warning("No CVARs")
        return cvars

    def load_cached_demo(self, match_id, map_number):
        return demo_cache.load_parsed_demo(
            cache_dir=self.parsed_demo_dir,
            match_id=match_id,
            map_number=map_number,
        )

    def list_cached_demos(self):
        return demo_cache.list_cached_demos(self.parsed_demo_dir)

    @staticmethod
    def print_compact_demo_headers(demo_data):
        if demo_data:
            logger.log_info("=== DEMO HEADERS (COMPACT) ===")
            for (match_id, map_number), sample_data in sorted(demo_data.items()):
                header = sample_data.get("header", {}) if isinstance(sample_data, dict) else {}
                map_name = header.get("map_name", "?")
                tick_count = header.get("tick_count", "?")
                logger.log_info(f"[M{match_id}|Map{map_number}] {map_name:15} | Ticks: {tick_count}")
