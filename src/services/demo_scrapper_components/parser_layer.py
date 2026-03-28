from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from queue import Queue
from threading import Lock

from awpy.demo import Demo
import numpy as np
import pandas as pd
import polars as pl
from db.connection_db import get_conn
from db.matches_db import set_match_has_demo
from services import demo_cache
from services.IO_manager import IOManager
import services.logger as logger

try:
    from awpy import stats as awpy_stats
except Exception:
    awpy_stats = None


@dataclass
class LoadedDemoEntry:
    file: Path
    match_id: int
    map_number: int
    demo: Demo


class DemoScrapperParserLayer:
    """Dedicated parsing layer for demo files and cache generation."""

    _RESTORE_STAT_NETPROPS = {
        "cash_earned": "CCSPlayerController.CCSPlayerController_ActionTrackingServices.CSPerRoundStats_t.m_iCashEarned",
        "equipment_value": "CCSPlayerController.CCSPlayerController_ActionTrackingServices.CSPerRoundStats_t.m_iEquipmentValue",
        "money_saved": "CCSPlayerController.CCSPlayerController_ActionTrackingServices.CSPerRoundStats_t.m_iMoneySaved",
        "kill_reward": "CCSPlayerController.CCSPlayerController_ActionTrackingServices.CSPerRoundStats_t.m_iKillReward",
        "live_time": "CCSPlayerController.CCSPlayerController_ActionTrackingServices.CSPerRoundStats_t.m_iLiveTime",
        "enemies_flashed": "CCSPlayerController.CCSPlayerController_ActionTrackingServices.CSPerRoundStats_t.m_iEnemiesFlashed",
    }

    def __init__(self, host):
        # host is DemoScrapperIntegration and provides shared helpers/state.
        self.host = host

    def parse_awpy_demo(self, file_path):
        """Convert local .dem file into awpy Demo object."""
        demo = Demo(str(file_path))
        demo.parse()
        return demo

    def _extract_restore_stats_from_parser_ticks(self, demo):
        """
        Build exact per-player restore stats from low-level parser tick netprops.

        This path is preferred over heuristic derivation when parser netprops exist.
        """
        parser = getattr(demo, "parser", None)
        rounds = getattr(demo, "rounds", None)
        if parser is None or rounds is None:
            return {}

        round_nums = None
        starts = None
        ends_raw = None

        if isinstance(rounds, pl.DataFrame):
            if rounds.is_empty():
                return {}

            pl_cols = [c for c in ["round_num", "start", "end", "official_end"] if c in rounds.columns]
            if "round_num" not in pl_cols or "start" not in pl_cols:
                return {}

            round_rows_pl = (
                rounds
                .select(pl_cols)
                .with_columns([
                    pl.col("round_num").cast(pl.Int64, strict=False),
                    pl.col("start").cast(pl.Int64, strict=False),
                    pl.col("end").cast(pl.Int64, strict=False) if "end" in pl_cols else pl.lit(None),
                    pl.col("official_end").cast(pl.Int64, strict=False) if "official_end" in pl_cols else pl.lit(None),
                ])
                .drop_nulls(["round_num", "start"])
                .sort("start")
            )

            if round_rows_pl.is_empty():
                return {}

            round_nums = round_rows_pl["round_num"].to_numpy().astype("int64")
            starts = round_rows_pl["start"].to_numpy().astype("int64")
            if "official_end" in round_rows_pl.columns:
                ends_raw = round_rows_pl["official_end"].to_numpy()
            elif "end" in round_rows_pl.columns:
                ends_raw = round_rows_pl["end"].to_numpy()

        elif isinstance(rounds, pd.DataFrame):
            round_rows = rounds.copy()
            if round_rows.empty:
                return {}

            for col in ["round_num", "start", "end", "official_end"]:
                if col in round_rows.columns:
                    round_rows[col] = pd.to_numeric(round_rows[col], errors="coerce")

            required = [c for c in ["round_num", "start"] if c in round_rows.columns]
            if len(required) < 2:
                return {}

            round_rows = round_rows.dropna(subset=["round_num", "start"]).sort_values("start")
            if round_rows.empty:
                return {}

            round_nums = round_rows["round_num"].astype("int64").to_numpy()
            starts = round_rows["start"].astype("int64").to_numpy()
            if "official_end" in round_rows.columns:
                ends_raw = round_rows["official_end"].to_numpy()
            elif "end" in round_rows.columns:
                ends_raw = round_rows["end"].to_numpy()

        else:
            return {}

        if round_nums is None or starts is None or len(starts) == 0:
            return {}

        wanted_props = list(self._RESTORE_STAT_NETPROPS.values())
        try:
            ticks_df = parser.parse_ticks(wanted_props=wanted_props)
        except Exception:
            return {}

        if not isinstance(ticks_df, pd.DataFrame) or ticks_df.empty:
            return {}
        if "steamid" not in ticks_df.columns or "tick" not in ticks_df.columns:
            return {}

        work = ticks_df.copy()
        work = work.dropna(subset=["steamid", "tick"])
        if work.empty:
            return {}

        work["steamid64"] = pd.to_numeric(work["steamid"], errors="coerce")
        work["tick"] = pd.to_numeric(work["tick"], errors="coerce")
        work = work.dropna(subset=["steamid64", "tick"])
        if work.empty:
            return {}

        work["steamid64"] = work["steamid64"].astype("int64")
        work = work[work["steamid64"] >= 10_000_000_000_000_000]
        if work.empty:
            return {}

        # Resolve round windows from parsed rounds table and map each tick to round.

        if ends_raw is None:
            ends = np.full_like(starts, fill_value=np.iinfo(np.int64).max)
        else:
            ends = pd.to_numeric(pd.Series(ends_raw), errors="coerce").fillna(np.nan).to_numpy()
            if len(starts) > 1:
                next_starts = np.append(starts[1:] - 1, np.iinfo(np.int64).max)
                ends = np.where(np.isnan(ends), next_starts, ends)
            else:
                ends = np.where(np.isnan(ends), np.iinfo(np.int64).max, ends)
            ends = ends.astype("int64")

        tick_values = work["tick"].astype("int64").to_numpy()
        idx = np.searchsorted(starts, tick_values, side="right") - 1
        valid = idx >= 0
        if not valid.any():
            return {}

        work = work.iloc[valid].copy()
        idx = idx[valid]
        tick_values = tick_values[valid]

        round_for_tick = round_nums[idx]
        end_for_tick = ends[idx]
        inside_round = tick_values <= end_for_tick
        if not inside_round.any():
            return {}

        work = work.iloc[inside_round].copy()
        round_for_tick = round_for_tick[inside_round]
        if work.empty:
            return {}

        work["round_num"] = round_for_tick

        selected_cols = ["steamid64", "round_num"]
        alias_to_col = {}
        for alias, col in self._RESTORE_STAT_NETPROPS.items():
            if col in work.columns:
                work[col] = pd.to_numeric(work[col], errors="coerce").fillna(0)
                selected_cols.append(col)
                alias_to_col[alias] = col

        if not alias_to_col:
            return {}

        grouped = work[selected_cols].groupby(["steamid64", "round_num"], as_index=False).max()
        if grouped.empty:
            return {}

        per_player = grouped.groupby("steamid64", as_index=False).sum(numeric_only=True)
        result = {}
        for row in per_player.to_dict("records"):
            steamid64 = str(int(row.get("steamid64") or 0))
            if not steamid64 or steamid64 == "0":
                continue

            result[steamid64] = {
                "equipment_value": int(row.get(alias_to_col.get("equipment_value"), 0) or 0),
                "money_saved": int(row.get(alias_to_col.get("money_saved"), 0) or 0),
                "kill_reward": int(row.get(alias_to_col.get("kill_reward"), 0) or 0),
                "cash_earned": int(row.get(alias_to_col.get("cash_earned"), 0) or 0),
                # Parser live time is usually in ticks; convert to seconds.
                "live_time": int((row.get(alias_to_col.get("live_time"), 0) or 0) / 128),
                "enemies_flashed": int(row.get(alias_to_col.get("enemies_flashed"), 0) or 0),
            }

        return result

    @staticmethod
    def _merge_restore_stats(preferred_stats, fallback_stats):
        merged = {}
        for source in [fallback_stats, preferred_stats]:
            if not isinstance(source, dict):
                continue
            for steamid64, row in source.items():
                sid = str(steamid64)
                if sid not in merged:
                    merged[sid] = {
                        "equipment_value": 0,
                        "money_saved": 0,
                        "kill_reward": 0,
                        "cash_earned": 0,
                        "live_time": 0,
                        "enemies_flashed": 0,
                    }
                if not isinstance(row, dict):
                    continue
                for key in [
                    "equipment_value",
                    "money_saved",
                    "kill_reward",
                    "cash_earned",
                    "live_time",
                    "enemies_flashed",
                ]:
                    try:
                        merged[sid][key] = max(int(merged[sid].get(key, 0) or 0), int(row.get(key, 0) or 0))
                    except Exception:
                        continue
        return merged

    def _inject_exact_restore_stats(self, demo, parsed_payload):
        payload = parsed_payload if isinstance(parsed_payload, dict) else {}
        fallback_stats = payload.get("derived_restore_stats") if isinstance(payload.get("derived_restore_stats"), dict) else {}
        exact_stats = self._extract_restore_stats_from_parser_ticks(demo)
        payload["derived_restore_stats"] = self._merge_restore_stats(exact_stats, fallback_stats)
        payload["derived_restore_stats_meta"] = {
            "source": "parser_ticks" if exact_stats else "heuristic_fallback",
            "players": len(payload.get("derived_restore_stats") or {}),
        }
        return payload

    @staticmethod
    def _is_parser_output_table(value):
        if value is None:
            return True
        if isinstance(value, (pd.DataFrame, pl.DataFrame, dict, list, tuple)):
            return True
        return False

    def _inject_awpy_parser_outputs(self, demo, parsed_payload):
        """
        Capture all parser outputs available on awpy Demo after parse().

        We preserve legacy top-level keys and also expose a dedicated namespace
        so downstream logic can iterate parser outputs generically.
        """
        payload = parsed_payload if isinstance(parsed_payload, dict) else {}
        parser_output = {}

        for attr in dir(demo):
            if attr.startswith("_"):
                continue
            if attr in {"parser"}:
                continue

            try:
                value = getattr(demo, attr)
            except Exception:
                continue

            if callable(value):
                continue

            if not self._is_parser_output_table(value):
                continue

            parser_output[attr] = value

            # Keep compatibility with existing payload consumers that read top-level keys.
            if attr not in payload:
                payload[attr] = value

        payload["awpy_parser_output"] = parser_output
        payload["awpy_parser_output_meta"] = {
            "count": len(parser_output),
            "keys": sorted(parser_output.keys()),
        }

        return payload

    def _extract_awpy_stats_bundle(self, demo):
        """
        Compute a stable stats bundle from awpy.stats.

        Targets requested: adr, trades, impact, kast, rating.
        """
        bundle = {
            "adr": None,
            "trades": None,
            "impact": None,
            "kast": None,
            "rating": None,
        }

        if awpy_stats is None:
            return bundle

        stat_candidates = {
            "adr": ["adr"],
            "trades": ["trades", "calculate_trades"],
            "impact": ["impact"],
            "kast": ["kast"],
            "rating": ["rating"],
        }

        for stat_name, fn_names in stat_candidates.items():
            for fn_name in fn_names:
                fn = getattr(awpy_stats, fn_name, None)
                if not callable(fn):
                    continue
                try:
                    bundle[stat_name] = fn(demo)
                    break
                except Exception:
                    # Try fallback function name when available.
                    continue

        return bundle

    def _inject_awpy_stats(self, demo, parsed_payload):
        payload = parsed_payload if isinstance(parsed_payload, dict) else {}
        stats_bundle = self._extract_awpy_stats_bundle(demo)

        payload["awpy_stats"] = stats_bundle
        payload["awpy_stats_meta"] = {
            "available": [k for k, v in stats_bundle.items() if v is not None],
            "missing": [k for k, v in stats_bundle.items() if v is None],
        }

        # Keep legacy flat keys aligned with existing stats naming conventions.
        payload["stats_adr"] = stats_bundle.get("adr")
        payload["stats_trades"] = stats_bundle.get("trades")
        payload["stats_impact"] = stats_bundle.get("impact")
        payload["stats_kast"] = stats_bundle.get("kast")
        payload["stats_rating"] = stats_bundle.get("rating")

        return payload

    @staticmethod
    def _compact_table_shape(value):
        if value is None:
            return "-"
        if isinstance(value, pd.DataFrame):
            return f"pd:{len(value)}x{len(value.columns)}"
        if isinstance(value, pl.DataFrame):
            return f"pl:{value.height}x{len(value.columns)}"
        if isinstance(value, list):
            return f"list:{len(value)}"
        if isinstance(value, dict):
            return f"dict:{len(value)}"
        return type(value).__name__

    def _log_compact_payload_summary(self, filename, match_id, map_number, payload):
        """Emit one compact debug line per parsed demo, without table dumps."""
        if not isinstance(payload, dict):
            logger.log_debug(
                f"[PARSER][SUMMARY] file={filename} match={match_id} map={map_number} payload=invalid"
            )
            return

        core_tables = [
            "rounds",
            "kills",
            "damages",
            "shots",
            "grenades",
            "ticks",
            "player_round_totals",
            "smokes",
            "infernos",
            "bomb",
            "server_cvars",
        ]

        parts = []
        present = 0
        for key in core_tables:
            shape = self._compact_table_shape(payload.get(key))
            if shape != "-":
                present += 1
            parts.append(f"{key}={shape}")

        parser_meta = payload.get("awpy_parser_output_meta") or {}
        extras_meta = payload.get("awpy_extras_meta") or {}
        stats_meta = payload.get("awpy_stats_meta") or {}

        parser_count = int(parser_meta.get("count") or 0)
        extras_count = int(extras_meta.get("count") or 0)
        stats_available = ",".join(stats_meta.get("available") or [])
        stats_missing = ",".join(stats_meta.get("missing") or [])

        logger.log_debug(
            "[PARSER][SUMMARY] "
            f"file={filename} match={match_id} map={map_number} "
            f"core_present={present}/{len(core_tables)} "
            f"parser_tables={parser_count} extras={extras_count} "
            f"stats_ok=[{stats_available}] stats_missing=[{stats_missing}] "
            f"tables={' | '.join(parts)}"
        )

    @staticmethod
    def _is_awpy_payload_candidate(value):
        if value is None:
            return True
        if isinstance(value, (pd.DataFrame, pl.DataFrame, dict, list, tuple)):
            return True
        if isinstance(value, (str, int, float, bool)):
            return True
        return False

    def _enrich_with_awpy_extras(self, demo, parsed_payload):
        """
        Capture additional awpy surface area for cache portability.

        We store extras under one namespace so existing consumers remain stable.
        """
        payload = parsed_payload if isinstance(parsed_payload, dict) else {}
        extras = {}

        for attr in dir(demo):
            if attr.startswith("_"):
                continue

            # Skip attributes already mapped at top-level payload keys.
            if attr in payload:
                continue

            try:
                value = getattr(demo, attr)
            except Exception:
                continue

            if callable(value):
                continue

            if not self._is_awpy_payload_candidate(value):
                continue

            # Avoid duplicating parser internals with huge object graphs.
            if attr in {"parser"}:
                continue

            extras[attr] = value

        payload["awpy_extras"] = extras
        payload["awpy_extras_meta"] = {
            "count": len(extras),
            "keys": sorted(extras.keys()),
        }
        logger.log_debug(
            "[PARSER][EXTRAS] "
            f"count={payload['awpy_extras_meta']['count']}"
        )
        return payload

    def _matcher_worker(self, file, match_id, map_number):
        """Worker task for parallel awpy demo parsing."""
        try:
            demo = self.parse_awpy_demo(file)
            return {
                "status": "ok",
                "file": file,
                "match_id": match_id,
                "map_number": map_number,
                "demo": demo,
            }
        except Exception as e:
            return {
                "status": "failed",
                "file": file,
                "filename": file.name,
                "error": str(e),
            }

    def match_and_load_demos(self, progress_start=None, progress_end=None):
        self.host._ensure_not_cancelled(stage="matcher")

        demo_files = IOManager.list_files(self.host.demo_dir, ".dem")
        parsed_sources = IOManager.list_parsed_demo_sources(self.host.parsed_demo_dir)

        self.host._log_stage(
            "MATCHER",
            f"Found normalized_demos={len(demo_files)} cached_entries={len(parsed_sources)}",
        )

        results = []
        failed = []
        skipped_parsed = 0
        skipped_parsed_entries = []
        total_files = max(1, len(demo_files))

        # Separate work items into to-load and to-skip
        work_items = []  # (idx, file, match_id, map_number) for parsing
        idx_offset = 0

        for idx, file in enumerate(demo_files, start=1):
            match_id, map_number = self.host.extract_ids_from_normalized(file.name)
            if match_id is None or map_number is None:
                self.host._log_stage("MATCHER", f"Invalid normalized file {file.name}", level="ERROR")
                continue

            if file.name in parsed_sources:
                self.host._log_stage("MATCHER", f"SKIP parsed {file.name}", level="DEBUG")
                skipped_parsed += 1
                skipped_parsed_entries.append(
                    {
                        "match_id": match_id,
                        "map_number": map_number,
                        "filename": f"{Path(file.name).stem}.pkl",
                        "source_file": file.name,
                    }
                )
                continue

            self.host._log_stage("MATCHER", f"LOAD {file.name} match={match_id} map={map_number}")
            work_items.append((idx, file, match_id, map_number))

        # Process work items in parallel
        num_workers = min(8, max(1, len(work_items)))
        completed_count = [0]  # Mutable counter for progress tracking
        lock = Lock()

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {
                executor.submit(self._matcher_worker, file, match_id, map_number): (idx, file)
                for idx, file, match_id, map_number in work_items
            }

            for future in as_completed(futures):
                self.host._ensure_not_cancelled(stage="matcher")

                idx, file = futures[future]
                completed_count[0] += 1

                if progress_start is not None and progress_end is not None:
                    span = max(0, int(progress_end) - int(progress_start))
                    progress_pct = int((completed_count[0] / max(1, len(work_items))) * 100)
                    progress_val = int(progress_start) + int((completed_count[0] / max(1, len(work_items))) * span)
                    self.host._emit_progress(
                        progress_val,
                        f"Matcher {completed_count[0]}/{len(work_items)}: {file.name} ({progress_pct}%)",
                        stage="matcher",
                    )

                try:
                    result = future.result()
                    if result["status"] == "ok":
                        results.append(result)
                    else:
                        self.host._log_stage("MATCHER", f"FAILED {result['filename']}: {result['error']}", level="ERROR")
                        failed.append(result["filename"])
                except Exception as e:
                    self.host._log_stage("MATCHER", f"FAILED {file.name}: {e}", level="ERROR")
                    failed.append(file.name)

        self.host._log_stage(
            "MATCHER",
            f"Summary loaded={len(results)} failed={len(failed)} skipped_parsed={skipped_parsed}",
        )

        if failed:
            self.host._log_stage("MATCHER", "Failed demos list follows", level="ERROR")
            for failed_demo in failed:
                self.host._log_stage("MATCHER", failed_demo, level="ERROR")

        if progress_start is not None and progress_end is not None:
            self.host._emit_progress(int(progress_end), "Matcher completed", stage="matcher")

        return results, {
            "loaded": len(results),
            "failed": len(failed),
            "failed_files": failed,
            "skipped_parsed": skipped_parsed,
            "skipped_parsed_entries": skipped_parsed_entries,
            "normalized_files": len(demo_files),
            "cached_entries": len(parsed_sources),
        }

    def _parse_single_entry(self, entry, conn):
        match_id = entry["match_id"]
        map_number = entry["map_number"]
        demo = entry["demo"]
        filename = entry["file"].name

        key = (match_id, map_number)

        self.host._log_stage("PARSER", f"PARSE {filename} match={match_id} map={map_number}")

        data = self.host.parse_demo_full(demo)
        data = self._inject_exact_restore_stats(demo, data)
        data = self._inject_awpy_parser_outputs(demo, data)
        data = self._inject_awpy_stats(demo, data)
        data = self._enrich_with_awpy_extras(demo, data)
        self._log_compact_payload_summary(filename, match_id, map_number, data)

        if not self.host.validate_demo_players(match_id, map_number, data, conn=conn):
            logger.log_warning(
                f"[REJECTED] {filename} failed player validation for match={match_id}, map={map_number}"
            )
            return "rejected", key, filename

        manifest = demo_cache.save_parsed_demo(
            cache_dir=self.host.parsed_demo_dir,
            match_id=match_id,
            map_number=map_number,
            data=data,
            source_file=entry["file"],
        )

        cached_data = demo_cache.load_parsed_demo(
            cache_dir=self.host.parsed_demo_dir,
            match_id=match_id,
            map_number=map_number,
        )
        self.host._verify_cached_roundtrip(match_id, map_number, data, cached_data)

        set_match_has_demo(match_id=match_id, has_demo=True, conn=conn)

        return "ok", key, manifest

    def _parser_worker(self, entry, conn_factory):
        """Worker task for parallel payload enrichment."""
        try:
            with conn_factory() as conn:
                status, key, value = self._parse_single_entry(entry, conn)
                return {
                    "status": status,
                    "key": key,
                    "value": value,
                    "filename": entry["file"].name,
                }
        except Exception as e:
            return {
                "status": "error",
                "filename": entry["file"].name,
                "error": str(e),
            }

    def build_demo_data(self, matched, progress_start=None, progress_end=None):
        """
        Parse matched awpy demo entries, validate, and cache payloads.

        This is the app-layer parsing stage and is intentionally isolated from
        the sync/download flow so it can later be reused without demo files.
        """
        self.host._ensure_not_cancelled(stage="parser")

        cache_manifest = {}
        failed = 0
        rejected = 0

        self.host._log_stage("PARSER", "Building structured datasets")

        total_entries = max(1, len(matched))

        # Factory for per-worker connections (each thread gets its own conn)
        def conn_factory():
            return get_conn(db_file=self.host.db_file)

        # Process entries in parallel
        num_workers = min(8, max(1, len(matched)))
        completed_count = [0]
        lock = Lock()

        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = {
                executor.submit(self._parser_worker, entry, conn_factory): entry
                for entry in matched
            }

            for future in as_completed(futures):
                self.host._ensure_not_cancelled(stage="parser")

                entry = futures[future]
                completed_count[0] += 1

                if progress_start is not None and progress_end is not None:
                    span = max(0, int(progress_end) - int(progress_start))
                    progress_pct = int((completed_count[0] / max(1, total_entries)) * 100)
                    progress_val = int(progress_start) + int((completed_count[0] / max(1, total_entries)) * span)
                    self.host._emit_progress(
                        progress_val,
                        f"Parser {completed_count[0]}/{total_entries}: {entry['file'].name} ({progress_pct}%)",
                        stage="parser",
                    )

                try:
                    result = future.result()
                    if result["status"] == "rejected":
                        rejected += 1
                        self.host._log_stage(
                            "PARSER",
                            f"REJECTED {result['filename']}",
                            level="DEBUG",
                        )
                    elif result["status"] == "ok":
                        cache_manifest[result["key"]] = result["value"]
                    else:  # error
                        failed += 1
                        self.host._log_stage(
                            "PARSER",
                            f"FAILED {result['filename']}: {result.get('error', 'unknown')}",
                            level="ERROR",
                        )
                except Exception as e:
                    failed += 1
                    self.host._log_stage("PARSER", f"FAILED {entry['file'].name}: {e}", level="ERROR")

        self.host._log_stage(
            "PARSER",
            f"Summary parsed_cached={len(cache_manifest)} rejected={rejected} failed={failed}",
        )

        if progress_start is not None and progress_end is not None:
            self.host._emit_progress(int(progress_end), "Parser completed", stage="parser")

        return cache_manifest, {
            "parsed_cached": len(cache_manifest),
            "rejected": rejected,
            "failed": failed,
        }
