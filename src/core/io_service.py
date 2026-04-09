"""Core-level facades for data import/export and cache management.

GUI should use these instead of importing db modules directly.
"""
from pathlib import Path

from db import IO_db
from db import matches_db
from db.connection_db import DB_FILE, get_conn
from db.init_db import init_db
import db.settings_db as settings_db
import services.logger as logger


def get_players_payload():
    return IO_db.get_players_payload()


def import_players_payload(players):
    return IO_db.import_players_payload(players)


def get_maps_payload():
    return IO_db.get_maps_payload()


def import_maps_payload(maps_data):
    return IO_db.import_maps_payload(maps_data)


def clear_demo_flags():
    matches_db.set_demo_flags_by_match_ids(set())


def get_db_file_paths():
    """Return the list of DB file paths (main + WAL + SHM)."""
    base = Path(DB_FILE)
    return [base, Path(str(base) + "-wal"), Path(str(base) + "-shm")]


def reset_database(keep_settings=True, keep_players=True):
    """Delete and re-create the database, optionally preserving settings and players.

    Returns a dict with ``settings_restored`` and ``players_restored`` counts.
    """
    settings_snapshot = []
    players_snapshot = []

    if keep_settings:
        try:
            with get_conn() as conn:
                rows = conn.execute("SELECT key, value FROM settings").fetchall()
                settings_snapshot = [(str(r["key"]), str(r["value"])) for r in rows]
        except Exception as exc:
            logger.log_error(f"[IO] Failed to snapshot settings before DB reset: {exc}")

    if keep_players:
        try:
            players_snapshot = get_players_payload()
        except Exception as exc:
            logger.log_error(f"[IO] Failed to snapshot players before DB reset: {exc}")

    db_deleted = 0
    for db_path in get_db_file_paths():
        try:
            if db_path.exists():
                db_path.unlink()
                db_deleted += 1
        except Exception as exc:
            logger.log_error(f"[IO] Failed to delete database file {db_path}: {exc}")

    settings_restored = 0
    players_restored = 0

    try:
        init_db()

        if keep_settings and settings_snapshot:
            for key, value in settings_snapshot:
                settings_db.set(key, value)
            settings_restored = len(settings_snapshot)
            logger.log_info(f"[IO] Restored settings entries={settings_restored}")

        if keep_players and players_snapshot:
            players_restored = import_players_payload(players_snapshot)
            logger.log_info(f"[IO] Restored player-list entries={players_restored}")

        logger.log_info("[IO] Reinitialized database after reset")
    except Exception as exc:
        logger.log_error(f"[IO] Database reinitialize failed: {exc}")

    return {
        "db_files_deleted": db_deleted,
        "settings_restored": settings_restored,
        "players_restored": players_restored,
    }
