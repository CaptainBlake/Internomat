#/src/services/demo_scrapper.py

import os
import math
from ftplib import FTP
from pathlib import Path
from threading import Lock

import pandas as pd
import polars as pl
from awpy.demo import Demo
from db.connection_db import get_conn
from db.demo_db import (
    get_expected_demo_players,
    load_demo_match_catalog,
    resolve_map_number,
)
from db.matches_db import set_match_has_demo
from dotenv import load_dotenv
from services.IO_manager import IOManager
from services import demo_cache
from services import executor
import services.logger as logger

class DemoScrapperIntegration:
    """flow for downloading, parsing, and structuring demos."""

    @staticmethod
    def _log_stage(stage, message, level="INFO"):
        logger.log(f"[{stage}] {message}", level=level)

    def __init__(
        self,
        base_dir: Path | None = None,
        db_file: Path | None = None,
        demo_dir: Path | None = None,
        remote_dir: str = "/cs2/game/csgo/MatchZy",
        ftp_host: str | None = None,
        ftp_port: int | None = None,
        ftp_user: str | None = None,
        ftp_password: str | None = None,
        progress_callback=None,
    ):
        self.base_dir = base_dir or Path(__file__).parent.parent.parent
        self.db_file = db_file or (self.base_dir / "internomat.db")
        self.demo_dir = demo_dir or (self.base_dir / "demos")
        self.parsed_demo_dir = self.demo_dir / "parsed"
        self.remote_dir = remote_dir
        self._run_lock = Lock()
        self.progress_callback = progress_callback

        logger.log_info(f"Using DB: {self.db_file}")

        env_path = self.base_dir / ".env"
        load_dotenv(env_path)

        env_ftp_host = os.getenv("SERVER_IP")
        env_ftp_port = int(os.getenv("FTP_PORT", 21))
        env_ftp_user = os.getenv("FTP_USER")
        env_ftp_password = os.getenv("FTP_PASSWORD")

        self.ftp_host = ftp_host or env_ftp_host
        self.ftp_port = ftp_port or env_ftp_port
        self.ftp_user = ftp_user or env_ftp_user
        self.ftp_password = ftp_password or env_ftp_password

        self.demo_dir.mkdir(parents=True, exist_ok=True)
        self.parsed_demo_dir.mkdir(parents=True, exist_ok=True)

        assert self.ftp_host and self.ftp_user and self.ftp_password, "Missing FTP env vars"

        with get_conn(db_file=self.db_file) as conn:
            self.match_catalog = load_demo_match_catalog(conn=conn)
        self.valid_match_ids = set(self.match_catalog.keys())

        logger.log_info(f"Loaded {len(self.match_catalog)} matches")
        logger.log_debug(f"Valid match_ids: {sorted(self.valid_match_ids)}")
        logger.log_info(f"Parsed demo cache dir: {self.parsed_demo_dir}")

    def _emit_progress(self, percent, message, stage="pipeline", file_percent=None):
        if not callable(self.progress_callback):
            return

        try:
            clamped = max(0, min(100, int(percent)))
            self.progress_callback(
                {
                    "percent": clamped,
                    "stage": str(stage),
                    "message": str(message),
                    "file_percent": (
                        None
                        if file_percent is None
                        else max(0, min(100, int(file_percent)))
                    ),
                }
            )
        except Exception:
            pass

    # --- SHARED UTILS ---

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
            map_number = int(parts[map_idx + 1])

            return match_id, map_number
        except Exception:
            return None, None

    # --- FTP ---

    def download_demo(self):
        self._log_stage("FTP", f"Connecting to {self.ftp_host}:{self.ftp_port}...")
        self._emit_progress(5, "Connecting to FTP server...", stage="ftp")

        ftp = FTP()

        try:
            ftp.connect(self.ftp_host, self.ftp_port, timeout=10)
            ftp.login(self.ftp_user, self.ftp_password)
            ftp.set_pasv(True)

            self._log_stage("FTP", "Connected")

            ftp.cwd(self.remote_dir)
            files = ftp.nlst()
            parsed_sources = IOManager.list_parsed_demo_sources(self.parsed_demo_dir)

            demo_files = [f for f in files if str(f).endswith(".dem")]
            total_demo_files = max(1, len(demo_files))
            processed_demo_files = 0

            downloaded, skipped, skipped_parsed, ignored = 0, 0, 0, 0

            self._log_stage("FTP", f"Found {len(files)} remote files")
            self._emit_progress(
                8,
                f"Found {len(demo_files)} demo files on server.",
                stage="ftp",
            )

            for file in files:
                if not file.endswith(".dem"):
                    continue

                try:
                    self._emit_progress(
                        8 + int((processed_demo_files / total_demo_files) * 62),
                        f"Scanning {processed_demo_files + 1}/{total_demo_files}: {file}",
                        stage="ftp",
                    )

                    date, time, match_id, map_name = self.extract_parts(file)

                    if match_id is None:
                        ignored += 1
                        continue

                    if match_id not in self.valid_match_ids:
                        ignored += 1
                        continue

                    map_number = resolve_map_number(self.match_catalog, match_id, map_name)

                    if map_number is None:
                        ignored += 1
                        logger.log_debug(
                            f"[IGNORE] {file} map_name={map_name} does not exist for match={match_id}"
                        )
                        continue

                    normalized_name = f"{date}_{time}_match_{match_id}_map_{map_number}_{map_name}.dem"
                    local_file = self.demo_dir / normalized_name

                    if normalized_name in parsed_sources:
                        self._log_stage("FTP", f"SKIP parsed cache {normalized_name}", level="DEBUG")
                        skipped_parsed += 1
                        continue

                    if IOManager.file_exists(local_file):
                        self._log_stage("FTP", f"SKIP local exists {normalized_name}", level="DEBUG")
                        skipped += 1
                        continue

                    self._log_stage("FTP", f"DOWNLOAD {file} -> {normalized_name}")
                    self._emit_progress(
                        8 + int((processed_demo_files / total_demo_files) * 62),
                        f"Downloading {normalized_name}",
                        stage="ftp",
                    )

                    try:
                        filesize = ftp.size(file)

                        ftp_stage_start = 8 + int((processed_demo_files / total_demo_files) * 62)
                        ftp_stage_end = 8 + int(((processed_demo_files + 1) / total_demo_files) * 62)
                        last_state = {"absolute": -1, "file_percent": -1}

                        def _on_file_progress(bytes_written, total_bytes):
                            if not total_bytes:
                                return

                            ratio = bytes_written / max(1, total_bytes)
                            ratio = max(0.0, min(1.0, ratio))
                            absolute = ftp_stage_start + int((ftp_stage_end - ftp_stage_start) * ratio)
                            file_pct = int(ratio * 100)

                            if (
                                absolute == last_state["absolute"]
                                and file_pct == last_state["file_percent"]
                            ):
                                return
                            last_state["absolute"] = absolute
                            last_state["file_percent"] = file_pct

                            self._emit_progress(
                                absolute,
                                f"Downloading {normalized_name} ({file_pct}%)",
                                stage="ftp",
                                file_percent=file_pct,
                            )

                        IOManager.stream_to_file(
                            local_file,
                            lambda cb: ftp.retrbinary(f"RETR {file}", cb),
                            total_size=filesize,
                            desc=normalized_name,
                            progress_callback=_on_file_progress,
                        )

                        downloaded += 1

                    except Exception as e:
                        self._log_stage("FTP", f"FAILED {file}: {e}", level="ERROR")
                finally:
                    processed_demo_files += 1
                    self._emit_progress(
                        8 + int((processed_demo_files / total_demo_files) * 62),
                        (
                            f"FTP progress {processed_demo_files}/{total_demo_files} "
                            f"(downloaded={downloaded}, skipped={skipped}, ignored={ignored})"
                        ),
                        stage="ftp",
                    )

            self._log_stage("FTP", "Done")
            self._log_stage(
                "FTP",
                f"Summary downloaded={downloaded} skipped_local={skipped} skipped_parsed={skipped_parsed} ignored={ignored}",
            )
            self._emit_progress(
                70,
                (
                    f"FTP done: downloaded={downloaded}, skipped={skipped}, "
                    f"skipped_parsed={skipped_parsed}, ignored={ignored}"
                ),
                stage="ftp",
            )

            return {
                "downloaded": downloaded,
                "skipped": skipped,
                "skipped_parsed": skipped_parsed,
                "ignored": ignored,
                "remote_files": len(files),
            }

        finally:
            try:
                ftp.quit()
            except Exception:
                pass

        return {
            "downloaded": 0,
            "skipped": 0,
            "skipped_parsed": 0,
            "ignored": 0,
            "remote_files": 0,
        }
    # --- DEMO MATCH + LOAD ---

    def match_and_load_demos(self, progress_start=None, progress_end=None):
        demo_files = IOManager.list_files(self.demo_dir, ".dem")
        parsed_sources = IOManager.list_parsed_demo_sources(self.parsed_demo_dir)

        self._log_stage("MATCHER", f"Found normalized_demos={len(demo_files)} cached_entries={len(parsed_sources)}")

        results = []
        failed = []
        skipped_parsed = 0
        total_files = max(1, len(demo_files))

        for idx, file in enumerate(demo_files, start=1):
            entry_start = None
            entry_end = None
            if progress_start is not None and progress_end is not None:
                span = max(0, int(progress_end) - int(progress_start))
                entry_start = int(progress_start) + int((idx - 1) / total_files * span)
                entry_end = int(progress_start) + int(idx / total_files * span)
                self._emit_progress(entry_start, f"Matcher {idx}/{total_files}: {file.name}", stage="matcher")

            if file.name in parsed_sources:
                self._log_stage("MATCHER", f"SKIP parsed {file.name}", level="DEBUG")
                skipped_parsed += 1
                continue

            match_id, map_number = self.extract_ids_from_normalized(file.name)

            if match_id is None or map_number is None:
                self._log_stage("MATCHER", f"Invalid normalized file {file.name}", level="ERROR")
                continue

            self._log_stage("MATCHER", f"LOAD {file.name} match={match_id} map={map_number}")
            if entry_start is not None and entry_end is not None:
                mid = entry_start + int((entry_end - entry_start) * 0.4)
                self._emit_progress(mid, f"Parsing demo {file.name}", stage="matcher")

            try:
                demo = Demo(str(file))
                demo.parse()

                results.append(
                    {
                        "file": file,
                        "match_id": match_id,
                        "map_number": map_number,
                        "demo": demo,
                    }
                )

                if entry_start is not None and entry_end is not None:
                    self._emit_progress(entry_end, f"Matcher done {file.name}", stage="matcher")

            except Exception as e:
                self._log_stage("MATCHER", f"FAILED {file.name}: {e}", level="ERROR")
                failed.append(file.name)

        self._log_stage(
            "MATCHER",
            f"Summary loaded={len(results)} failed={len(failed)} skipped_parsed={skipped_parsed}",
        )

        if failed:
            self._log_stage("MATCHER", "Failed demos list follows", level="ERROR")
            for failed_demo in failed:
                self._log_stage("MATCHER", failed_demo, level="ERROR")

        if progress_start is not None and progress_end is not None:
            self._emit_progress(int(progress_end), "Matcher completed", stage="matcher")

        return results, {
            "loaded": len(results),
            "failed": len(failed),
            "failed_files": failed,
            "skipped_parsed": skipped_parsed,
            "normalized_files": len(demo_files),
            "cached_entries": len(parsed_sources),
        }

    # --- PARSER ---

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

        return data

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

    def build_demo_data(self, matched, progress_start=None, progress_end=None):
        cache_manifest = {}
        failed = 0
        rejected = 0

        self._log_stage("PARSER", "Building structured datasets")

        total_entries = max(1, len(matched))

        with get_conn(db_file=self.db_file) as conn:
            for idx, entry in enumerate(matched, start=1):
                entry_start = None
                entry_end = None
                if progress_start is not None and progress_end is not None:
                    span = max(0, int(progress_end) - int(progress_start))
                    entry_start = int(progress_start) + int((idx - 1) / total_entries * span)
                    entry_end = int(progress_start) + int(idx / total_entries * span)
                    percent = entry_start
                    self._emit_progress(
                        percent,
                        f"Parser {idx}/{total_entries}: {entry['file'].name}",
                        stage="parser",
                    )

                match_id = entry["match_id"]
                map_number = entry["map_number"]
                demo = entry["demo"]
                filename = entry["file"].name

                key = (match_id, map_number)

                self._log_stage("PARSER", f"PARSE {filename} match={match_id} map={map_number}")

                try:
                    data = self.parse_demo_full(demo)
                    if entry_start is not None and entry_end is not None:
                        p = entry_start + int((entry_end - entry_start) * 0.35)
                        self._emit_progress(p, f"Validated structure {filename}", stage="parser")

                    if not self.validate_demo_players(match_id, map_number, data, conn=conn):
                        logger.log_warning(
                            f"[REJECTED] {filename} failed player validation for match={match_id}, map={map_number}"
                        )
                        rejected += 1
                        if entry_end is not None:
                            self._emit_progress(entry_end, f"Rejected {filename}", stage="parser")
                        continue

                    if entry_start is not None and entry_end is not None:
                        p = entry_start + int((entry_end - entry_start) * 0.65)
                        self._emit_progress(p, f"Saving parsed payload {filename}", stage="parser")

                    manifest = demo_cache.save_parsed_demo(
                        cache_dir=self.parsed_demo_dir,
                        match_id=match_id,
                        map_number=map_number,
                        data=data,
                        source_file=entry["file"],
                    )

                    cached_data = demo_cache.load_parsed_demo(
                        cache_dir=self.parsed_demo_dir,
                        match_id=match_id,
                        map_number=map_number,
                    )
                    self._verify_cached_roundtrip(match_id, map_number, data, cached_data)

                    set_match_has_demo(match_id=match_id, has_demo=True, conn=conn)

                    cache_manifest[key] = manifest

                    if entry_end is not None:
                        self._emit_progress(entry_end, f"Parser done {filename}", stage="parser")

                except Exception as e:
                    self._log_stage("PARSER", f"FAILED {filename}: {e}", level="ERROR")
                    failed += 1
                    if entry_end is not None:
                        self._emit_progress(entry_end, f"Parser failed {filename}", stage="parser")

        self._log_stage(
            "PARSER",
            f"Summary parsed_cached={len(cache_manifest)} rejected={rejected} failed={failed}",
        )

        if progress_start is not None and progress_end is not None:
            self._emit_progress(int(progress_end), "Parser completed", stage="parser")

        return cache_manifest, {
            "parsed_cached": len(cache_manifest),
            "rejected": rejected,
            "failed": failed,
        }

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

    def _run_pipeline(self):
        self._log_stage("PIPELINE", "Start")
        self._emit_progress(0, "Pipeline started", stage="pipeline")

        self._emit_progress(3, "Stage 1/3: FTP sync", stage="pipeline")
        ftp_stats = self.download_demo()

        self._emit_progress(71, "Stage 2/3: Parse and match demos", stage="pipeline")
        matched, matcher_stats = self.match_and_load_demos(progress_start=71, progress_end=88)

        self._emit_progress(89, "Stage 3/3: Validate and cache parsed demos", stage="pipeline")
        demo_data, parser_stats = self.build_demo_data(matched, progress_start=89, progress_end=99)

        cached_matches = {
            str(row.get("match_id"))
            for row in demo_cache.list_existing_cached_demos(self.parsed_demo_dir)
            if isinstance(row, dict) and row.get("match_id") is not None
        }
        from db.matches_db import set_demo_flags_by_match_ids
        set_demo_flags_by_match_ids(cached_matches)

        self._log_stage(
            "PIPELINE",
            "Summary "
            f"ftp(downloaded={ftp_stats['downloaded']} skipped_local={ftp_stats['skipped']} skipped_parsed={ftp_stats.get('skipped_parsed', 0)} ignored={ftp_stats['ignored']}) "
            f"matcher(loaded={matcher_stats['loaded']} failed={matcher_stats['failed']} skipped_parsed={matcher_stats['skipped_parsed']}) "
            f"parser(parsed_cached={parser_stats['parsed_cached']} rejected={parser_stats['rejected']} failed={parser_stats['failed']})",
        )
        self.print_compact_demo_headers(demo_data)
        self._log_stage("PIPELINE", "Done")
        self._emit_progress(100, "Pipeline completed", stage="pipeline")
        return demo_data

    def run(self, on_complete=None, on_error=None):
        """Always execute the heavy pipeline on a background worker thread."""

        def task():
            demo_data = self._run_pipeline()
            if on_complete:
                on_complete(demo_data)

        started = executor.run_async(task, lock=self._run_lock, on_error=on_error)

        if not started:
            logger.log_warning("[SCRAPPER] Run already in progress; skipping duplicate request")

        return started

    def run_sync(self):
        """Optional sync entrypoint for scripts/tests that need a direct return value."""
        return self._run_pipeline()
