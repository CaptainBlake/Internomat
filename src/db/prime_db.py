"""Database operations for Prime (Leetify) ratings.

Mirrors the pattern of elo_db.py — a dedicated module for the prime_ratings
table and the premier_rating_history table.
"""

from datetime import datetime

from .connection_db import execute_write, executemany_write, get_conn, optional_conn
import services.logger as logger


# ---------------------------------------------------------------------------
#  Upsert / read prime_ratings
# ---------------------------------------------------------------------------

def upsert_prime_rating(player, conn=None):
    """Insert or update the prime_ratings row for a player."""
    sid = str(player.get("steamid64") or player.get("steam64_id") or "").strip()
    if not sid:
        return

    with optional_conn(conn, commit=True) as c:
        execute_write(c, """
            INSERT INTO prime_ratings (
                steamid64, premier_rating, leetify_rating,
                total_matches, winrate, rating_source, rating_season
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(steamid64) DO UPDATE SET
                premier_rating = excluded.premier_rating,
                leetify_rating = excluded.leetify_rating,
                total_matches  = excluded.total_matches,
                winrate        = excluded.winrate,
                rating_source  = excluded.rating_source,
                rating_season  = excluded.rating_season,
                updated_at     = datetime('now')
        """, (
            sid,
            player.get("premier_rating"),
            player.get("leetify_rating"),
            player.get("total_matches"),
            player.get("winrate"),
            player.get("rating_source"),
            player.get("rating_season"),
        ))

    logger.log(
        f"[DB] Upsert prime rating player={logger.redact(sid)} "
        f"source={player.get('rating_source')}",
        level="DEBUG",
    )


# ---------------------------------------------------------------------------
#  Premier rating history
# ---------------------------------------------------------------------------

def record_premier_rating_history(player):
    """Persist premier rating snapshots from a player update.

    Handles two kinds of entries:
    1. Per-match entries from ``rating_history`` (API ``recent_matches``).
       Deduped by the unique index ``(steamid64, leetify_match_id)``.
    2. A profile-level snapshot (current ``premier_rating``).
       Skipped when the latest profile snapshot already has the same rating.
    """
    now = datetime.utcnow().isoformat()
    sid = str(player.get("steamid64") or "").strip()
    rating = player.get("premier_rating")
    source = player.get("rating_source") or "unknown"

    if not sid or rating is None:
        return

    with get_conn() as conn:
        # --- 1) match-level entries from API recent_matches ---
        match_rows = player.get("rating_history") or []
        if match_rows:
            params = []
            for mr in match_rows:
                params.append((
                    sid,
                    int(mr["premier_rating"]),
                    "api_match",
                    player.get("rating_season"),
                    mr.get("leetify_match_id"),
                    mr.get("map_name"),
                    mr.get("outcome"),
                    mr.get("game_played_at"),
                    now,
                ))
            executemany_write(conn, """
                INSERT INTO premier_rating_history
                    (steamid64, premier_rating, rating_source, rating_season,
                     leetify_match_id, map_name, outcome, game_played_at, recorded_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(steamid64, leetify_match_id) DO NOTHING
            """, params)
            logger.log(
                f"[DB] Premier history match entries player={logger.redact(sid)} "
                f"attempted={len(params)}",
                level="DEBUG",
            )

        # --- 2) profile-level snapshot ---
        latest = conn.execute(
            """
            SELECT premier_rating FROM premier_rating_history
            WHERE steamid64 = ? AND leetify_match_id IS NULL
            ORDER BY recorded_at DESC LIMIT 1
            """,
            (sid,),
        ).fetchone()

        if latest is None or int(latest[0]) != int(rating):
            execute_write(conn, """
                INSERT INTO premier_rating_history
                    (steamid64, premier_rating, rating_source, rating_season,
                     leetify_match_id, map_name, outcome, game_played_at, recorded_at)
                VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL, ?)
            """, (
                sid,
                int(rating),
                source,
                player.get("rating_season"),
                now,
            ))
            logger.log(
                f"[DB] Premier history profile snapshot player={logger.redact(sid)} "
                f"rating={rating} source={source}",
                level="DEBUG",
            )
