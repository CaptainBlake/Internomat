import os
import sqlite3
from ftplib import FTP
from pathlib import Path
from threading import Lock

import pandas as pd
import polars as pl
from awpy.demo import Demo
from dotenv import load_dotenv
from services.IO_manager import IOManager
from services import executor
import services.logger as logger



class DemoScrapperIntegration:
    """Unified integration flow for downloading, parsing, and structuring demos."""

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
    ):
        self.base_dir = base_dir or Path(__file__).parent.parent.parent
        self.db_file = db_file or (self.base_dir / "internomat.db")
        self.demo_dir = demo_dir or (self.base_dir / "demos")
        self.remote_dir = remote_dir
        self._run_lock = Lock()

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

        assert self.ftp_host and self.ftp_user and self.ftp_password, "Missing FTP env vars"

        self.matches = self.get_all_matches_with_maps_local()
        self.valid_match_ids = self.build_match_id_set(self.matches)

        logger.log_info(f"Loaded {len(self.matches)} matches")
        logger.log_debug(f"Valid match_ids: {sorted(self.valid_match_ids)}")

    # --- DB ---

    def get_conn_local(self):
        conn = sqlite3.connect(self.db_file, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    def get_all_matches_with_maps_local(self):
        with self.get_conn_local() as conn:
            rows = conn.execute(
                """
                SELECT
                    m.match_id,
                    m.team1_name,
                    m.team2_name,
                    mm.map_number,
                    mm.map_name
                FROM matches m
                LEFT JOIN match_maps mm
                    ON m.match_id = mm.match_id
                ORDER BY m.match_id, mm.map_number
                """
            ).fetchall()

        matches = {}

        for row in rows:
            match_id = int(row["match_id"])

            if match_id not in matches:
                matches[match_id] = {
                    "match_id": match_id,
                    "team1": row["team1_name"],
                    "team2": row["team2_name"],
                    "maps": [],
                }

            if row["map_number"] is not None:
                matches[match_id]["maps"].append(
                    {
                        "map_number": int(row["map_number"]),
                        "map_name": row["map_name"],
                    }
                )

        return list(matches.values())

    # --- SHARED UTILS ---

    def extract_match_id(self, filename):
        try:
            return int(filename.split("_")[2])
        except Exception:
            return None

    @staticmethod
    def build_match_id_set(matches):
        return {m["match_id"] for m in matches}

    @staticmethod
    def extract_parts(filename):
        # 2026-03-20_22-48-10_4_cs_office_team_...vs_...
        parts = filename.replace(".dem", "").split("_")

        try:
            date = parts[0]
            time = parts[1]
            match_id = int(parts[2])
            map_name = f"{parts[3]}_{parts[4]}"
            return date, time, match_id, map_name
        except Exception:
            return None, None, None, None

    @staticmethod
    def get_map_number(match, map_name):
        for match_map in match["maps"]:
            if match_map["map_name"] == map_name:
                return match_map["map_number"]
        return None

    @staticmethod
    def build_match_lookup(matches):
        return {m["match_id"]: m for m in matches}

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
        logger.log_info(f"[FTP] Connecting to {self.ftp_host}:{self.ftp_port}...")

        ftp = FTP()

        try:
            ftp.connect(self.ftp_host, self.ftp_port, timeout=10)
            ftp.login(self.ftp_user, self.ftp_password)
            ftp.set_pasv(True)

            logger.log_info("[FTP] Connected")

            ftp.cwd(self.remote_dir)
            files = ftp.nlst()

            downloaded, skipped, ignored = 0, 0, 0

            match_lookup = self.build_match_lookup(self.matches)

            logger.log_info(f"[FTP] Found {len(files)} files")

            for file in files:
                if not file.endswith(".dem"):
                    continue

                date, time, match_id, map_name = self.extract_parts(file)

                if match_id is None or match_id <= 0:
                    ignored += 1
                    continue

                if match_id not in self.valid_match_ids:
                    ignored += 1
                    continue

                match = match_lookup[match_id]
                map_number = self.get_map_number(match, map_name)

                normalized_name = f"{date}_{time}_match_{match_id}_map_{map_number}_{map_name}.dem"
                local_file = self.demo_dir / normalized_name

                if IOManager.file_exists(local_file):
                    logger.log_debug(f"[SKIP] {normalized_name}")
                    skipped += 1
                    continue

                logger.log_info(f"[DOWNLOAD] {file}")
                logger.log_info(f"           -> {normalized_name}")

                try:
                    filesize = ftp.size(file)

                    IOManager.stream_to_file(
                        local_file,
                        lambda cb: ftp.retrbinary(f"RETR {file}", cb),
                        total_size=filesize,
                        desc=normalized_name,
                    )

                    downloaded += 1

                except Exception as e:
                    logger.log_error(f"[FTP] {file}: {e}")

            logger.log_info("[FTP] Done")
            logger.log_info(f"Downloaded: {downloaded}")
            logger.log_info(f"Skipped: {skipped}")
            logger.log_info(f"Ignored: {ignored}")

        finally:
            try:
                ftp.quit()
            except Exception:
                pass
    # --- DEMO MATCH + LOAD ---

    def match_and_load_demos(self):
        demo_files = IOManager.list_files(self.demo_dir, ".dem")

        logger.log_info(f"[Matcher] Found {len(demo_files)} normalized demos")

        results = []
        failed = []

        for file in demo_files:
            match_id, map_number = self.extract_ids_from_normalized(file.name)

            if match_id is None or map_number is None:
                logger.log_warning(f"[Matcher] Invalid normalized file: {file.name}")
                continue

            logger.log_info(f"[LOAD] {file.name} (match={match_id}, map={map_number})")

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

            except Exception as e:
                logger.log_error(f"[FAILED] {file.name}: {e}")
                failed.append(file.name)

        logger.log_info(f"[Matcher] Loaded {len(results)} demos successfully")
        logger.log_info(f"[Matcher] Failed: {len(failed)}")

        if failed:
            logger.log_warning("Failed demos:")
            for failed_demo in failed:
                logger.log_warning(failed_demo)

        return results

    # --- PARSER ---

    @staticmethod
    def parse_demo_full(demo):
        data = {"header": demo.header}

        table_map = {
            "rounds": "rounds",
            "kills": "kills",
            "damages": "damages",
            "grenades": "grenades",
            "shots": "shots",
            "footsteps": "footsteps",
            "smokes": "smokes",
            "infernos": "infernos",
            "bomb": "bomb",
            "ticks": "ticks",
            "player_round_totals": "player_round_totals",
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

    def build_demo_data(self, matched):
        demo_dict = {}
        failed = 0

        logger.log_info("[Parser] Building structured datasets...")

        for entry in matched:
            match_id = entry["match_id"]
            map_number = entry["map_number"]
            demo = entry["demo"]
            filename = entry["file"].name

            key = (match_id, map_number)

            logger.log_info(f"[PARSE] {filename} -> match={match_id}, map={map_number}")

            try:
                data = self.parse_demo_full(demo)
                demo_dict[key] = data

            except Exception as e:
                logger.log_error(f"[FAILED] {filename}: {e}")
                failed += 1

        logger.log_info("[Parser] Done")
        logger.log_info(f"Parsed: {len(demo_dict)}")
        logger.log_info(f"Failed: {failed}")

        return demo_dict

    @staticmethod
    def print_compact_demo_headers(demo_data):
        if demo_data:
            logger.log_info("=== DEMO HEADERS (COMPACT) ===")
            for (match_id, map_number), sample_data in sorted(demo_data.items()):
                header = sample_data.get("header", {})
                map_name = header.get("map_name", "?")
                tick_count = header.get("tick_count", "?")
                logger.log_info(f"[M{match_id}|Map{map_number}] {map_name:15} | Ticks: {tick_count}")

    def _run_pipeline(self):
        self.download_demo()
        matched = self.match_and_load_demos()
        demo_data = self.build_demo_data(matched)
        self.print_compact_demo_headers(demo_data)
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
