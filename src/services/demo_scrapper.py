import os
from ftplib import FTP
from pathlib import Path
from threading import Lock

from db.connection_db import get_conn
from db.demo_db import load_demo_match_catalog
from db.matches_db import get_match_map_players
from db.players_db import upsert_players_from_match_stats
from core.settings.settings import settings
from dotenv import load_dotenv
from services.IO_manager import IOManager
from services import demo_cache
from services import executor
import services.logger as logger
from services.demo_scrapper_components import (
    DemoScrapperCommonMixin,
    DemoScrapperMetricsMixin,
    DemoScrapperParserLayer,
    DemoScrapperRestoreMixin,
)


class DemoSyncCancelled(Exception):
    """Raised when the user cancels an in-flight demo sync."""


class DemoScrapperIntegration(
    DemoScrapperCommonMixin,
    DemoScrapperMetricsMixin,
    DemoScrapperRestoreMixin,
):
    """Flow for downloading, parsing, and structuring demos."""

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
        cancel_requested=None,
    ):
        self.base_dir = base_dir or Path(__file__).parent.parent.parent
        self.db_file = db_file or (self.base_dir / "internomat.db")
        self.demo_dir = demo_dir or (self.base_dir / "demos")
        self.parsed_demo_dir = self.demo_dir / "parsed"
        self.remote_dir = remote_dir
        self._run_lock = Lock()
        self.progress_callback = progress_callback
        self.cancel_requested = cancel_requested

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

        # Keep parser concerns in a dedicated layer so awpy usage stays isolated.
        self.parser_layer = DemoScrapperParserLayer(self)

    def _is_cancel_requested(self):
        try:
            return bool(self.cancel_requested and self.cancel_requested())
        except Exception:
            return False

    def _ensure_not_cancelled(self, stage="pipeline"):
        if not self._is_cancel_requested():
            return

        self._emit_progress(0, "Sync cancelled by user.", stage=stage)
        raise DemoSyncCancelled("Sync cancelled by user")

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

    # --- FTP ---

    def download_demo(self):
        self._ensure_not_cancelled(stage="ftp")

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

            downloaded, skipped, skipped_parsed, ignored, recovered = 0, 0, 0, 0, 0

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
                    self._ensure_not_cancelled(stage="ftp")

                    self._emit_progress(
                        8 + int((processed_demo_files / total_demo_files) * 62),
                        f"Scanning {processed_demo_files + 1}/{total_demo_files}: {file}",
                        stage="ftp",
                    )

                    normalized = self._normalize_demo_identity(file)
                    if not normalized:
                        ignored += 1
                        continue

                    normalized_name = normalized["normalized_name"]
                    local_file = self.demo_dir / normalized_name
                    temp_local_file = self.demo_dir / f"{normalized_name}.part"

                    if normalized.get("recovered_from_catalog_miss"):
                        recovered += 1
                        self._log_stage(
                            "FTP",
                            (
                                f"RECOVERED mapping for {file} "
                                f"-> match={normalized['match_id']} map={normalized['map_number']}"
                            ),
                            level="DEBUG",
                        )

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
                            if self._is_cancel_requested():
                                raise DemoSyncCancelled("Sync cancelled by user")

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
                            temp_local_file,
                            lambda cb: ftp.retrbinary(f"RETR {file}", cb),
                            total_size=filesize,
                            desc=normalized_name,
                            progress_callback=_on_file_progress,
                        )

                        # Promote to final name only when download completed successfully.
                        temp_local_file.replace(local_file)

                        downloaded += 1

                    except DemoSyncCancelled:
                        if IOManager.file_exists(temp_local_file):
                            try:
                                Path(temp_local_file).unlink()
                            except Exception:
                                pass
                        raise
                    except Exception as e:
                        if IOManager.file_exists(temp_local_file):
                            try:
                                Path(temp_local_file).unlink()
                            except Exception:
                                pass
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
                (
                    f"Summary downloaded={downloaded} skipped_local={skipped} "
                    f"skipped_parsed={skipped_parsed} ignored={ignored} recovered={recovered}"
                ),
            )
            self._emit_progress(
                70,
                (
                    f"FTP done: downloaded={downloaded}, skipped={skipped}, "
                    f"skipped_parsed={skipped_parsed}, ignored={ignored}, recovered={recovered}"
                ),
                stage="ftp",
            )

            return {
                "downloaded": downloaded,
                "skipped": skipped,
                "skipped_parsed": skipped_parsed,
                "ignored": ignored,
                "recovered": recovered,
                "remote_files": len(files),
            }

        finally:
            try:
                ftp.quit()
            except Exception:
                pass

    # --- DEMO MATCH + LOAD ---

    def match_and_load_demos(self, progress_start=None, progress_end=None):
        return self.parser_layer.match_and_load_demos(
            progress_start=progress_start,
            progress_end=progress_end,
        )

    # --- PARSER ---

    def build_demo_data(self, matched, progress_start=None, progress_end=None):
        return self.parser_layer.build_demo_data(
            matched=matched,
            progress_start=progress_start,
            progress_end=progress_end,
        )

    def import_players_from_parsed_cache(self, canonical_entries=None):
        self._ensure_not_cancelled(stage="player_import")
        import_rows = []

        if canonical_entries:
            for item in canonical_entries:
                if not isinstance(item, dict):
                    continue
                match_id = item.get("match_id")
                map_number = item.get("map_number")
                if match_id is None or map_number is None:
                    continue
                import_rows.extend(get_match_map_players(match_id=match_id, map_number=map_number))
            cache_entry_count = len(canonical_entries)
        else:
            rows = demo_cache.list_existing_cached_demos(self.parsed_demo_dir)
            cache_entry_count = len(rows)
            for row in rows:
                if not isinstance(row, dict):
                    continue

                match_id = row.get("match_id")
                map_number = row.get("map_number")
                if match_id is None or map_number is None:
                    continue

                import_rows.extend(get_match_map_players(match_id=match_id, map_number=map_number))

        imported = upsert_players_from_match_stats(import_rows)
        self._log_stage(
            "PLAYER_IMPORT",
            f"Imported/updated players from parsed cache entries={cache_entry_count} players={imported}",
        )
        return imported

    def _run_pipeline(self):
        self._ensure_not_cancelled(stage="pipeline")

        self._log_stage("PIPELINE", "Start")
        self._emit_progress(0, "Pipeline started", stage="pipeline")

        self._emit_progress(3, "Stage 1/3: FTP sync", stage="pipeline")
        ftp_stats = self.download_demo()

        self._ensure_not_cancelled(stage="pipeline")

        self._emit_progress(71, "Stage 2/3: Parse and match demos", stage="pipeline")
        matched, matcher_stats = self.match_and_load_demos(progress_start=71, progress_end=88)

        self._ensure_not_cancelled(stage="pipeline")

        self._emit_progress(89, "Stage 3/4: Validate and cache parsed demos", stage="pipeline")
        demo_data, parser_stats = self.build_demo_data(matched, progress_start=89, progress_end=99)

        self._ensure_not_cancelled(stage="pipeline")

        parsed_entries = list((demo_data or {}).values())
        skipped_cached_entries = list((matcher_stats or {}).get("skipped_parsed_entries") or [])

        restore_rows = []
        seen_restore_keys = set()
        for row in parsed_entries + skipped_cached_entries:
            if not isinstance(row, dict):
                continue
            match_id = row.get("match_id")
            map_number = row.get("map_number")
            if match_id is None or map_number is None:
                continue
            key = (str(match_id), int(map_number))
            if key in seen_restore_keys:
                continue
            seen_restore_keys.add(key)
            restore_rows.append(row)

        if restore_rows:
            self._emit_progress(95, "Stage 4/4: Restore database from parsed cache", stage="pipeline")
            restore_stats = self.restore_db_from_parsed_cache(
                progress_start=95,
                progress_end=99,
                rows=restore_rows,
                include_orphaned=False,
            )
        else:
            restore_stats = {
                "restored_maps": 0,
                "restored_players": 0,
                "failed": 0,
                "cache_rows": 0,
                "orphaned_files": 0,
                "canonical_match_ids": [],
                "canonical_match_maps": [],
            }
            self._log_stage(
                "RESTORE",
                "Skip restore: no parsed or cache-skipped demos in this sync run",
                level="INFO",
            )

        self._ensure_not_cancelled(stage="pipeline")

        cached_matches = {
            str(mid)
            for mid in (restore_stats.get("canonical_match_ids") or [])
            if mid is not None
        }
        if not cached_matches:
            cached_matches = {
                str(row.get("match_id"))
                for row in demo_cache.list_existing_cached_demos(self.parsed_demo_dir)
                if isinstance(row, dict) and row.get("match_id") is not None
            }
        from db.matches_db import set_demo_flags_by_match_ids

        set_demo_flags_by_match_ids(cached_matches)

        imported_players = 0
        if settings.auto_import_match_players:
            canonical_entries = restore_stats.get("canonical_match_maps") or []
            if canonical_entries:
                self._emit_progress(99, "Importing players from parsed cache", stage="pipeline")
                imported_players = self.import_players_from_parsed_cache(
                    canonical_entries=canonical_entries
                )
            else:
                self._log_stage(
                    "PLAYER_IMPORT",
                    "Skip player import: no restored canonical maps in this sync run",
                    level="INFO",
                )

        summary = (
            f"Summary ftp(downloaded={ftp_stats['downloaded']} skipped_local={ftp_stats['skipped']} "
            f"skipped_parsed={ftp_stats.get('skipped_parsed', 0)} ignored={ftp_stats['ignored']} recovered={ftp_stats.get('recovered', 0)}) "
            f"matcher(loaded={matcher_stats['loaded']} failed={matcher_stats['failed']} skipped_parsed={matcher_stats['skipped_parsed']}) "
            f"parser(parsed_cached={parser_stats['parsed_cached']} rejected={parser_stats['rejected']} failed={parser_stats['failed']}) "
            f"restore(restored_maps={restore_stats['restored_maps']} restored_players={restore_stats['restored_players']} failed={restore_stats['failed']}) "
            f"players(imported={imported_players})"
        )
        self._log_stage("PIPELINE", summary)
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
