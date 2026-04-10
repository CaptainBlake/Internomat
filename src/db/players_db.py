from datetime import datetime, timedelta
from .connection_db import execute_write, executemany_write, get_conn, optional_conn
import services.logger as logger


def insert_player(player, conn=None):
    now = datetime.utcnow().isoformat()

    with optional_conn(conn, commit=True) as c:
        execute_write(c, """
            INSERT INTO players (steamid64, leetify_id, name, added_at, last_updated)
            VALUES (?, ?, ?, ?, ?)
        """, (
            player["steamid64"],
            player.get("leetify_id"),
            player["name"],
            now,
            now,
        ))

    logger.log(f"[DB] Insert player {logger.redact(player['steamid64'])}", level="INFO")

def update_player(player, conn=None):
    now = datetime.utcnow().isoformat()

    with optional_conn(conn, commit=True) as c:
        execute_write(c, """
            UPDATE players SET
                leetify_id = ?,
                name = ?,
                last_updated = ?
            WHERE steamid64 = ?
        """, (
            player.get("leetify_id"),
            player["name"],
            now,
            player["steamid64"]
        ))

    logger.log(f"[DB] Update player {logger.redact(player['steamid64'])}", level="INFO")


def delete_player(steam_id):
    with get_conn() as conn:
        execute_write(conn, "DELETE FROM players WHERE steamid64 = ?", (steam_id,))

    logger.log(f"[DB] Delete player {logger.redact(steam_id)}", level="INFO")

def upsert_player(player, mode="full", conn=None):
    now = datetime.utcnow().isoformat()

    with optional_conn(conn, commit=True) as c:
        if mode == "import":
            execute_write(c, """
                INSERT INTO players (steamid64, name, added_at)
                VALUES (?, ?, ?)
                ON CONFLICT(steamid64) DO UPDATE SET
                    name=excluded.name
            """, (
                player["steamid64"],
                player["name"],
                now,
            ))
        else:
            execute_write(c, """
                INSERT INTO players (steamid64, leetify_id, name, added_at, last_updated)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(steamid64) DO UPDATE SET
                    leetify_id=excluded.leetify_id,
                    name=excluded.name,
                    last_updated=excluded.last_updated
            """, (
                player["steamid64"],
                player.get("leetify_id"),
                player["name"],
                now,
                now,
            ))

    logger.log(f"[DB] Upsert player {logger.redact(player['steamid64'])}", level="DEBUG")


def upsert_players_from_match_stats(rows, conn=None):
    imported = 0
    seen = set()

    with optional_conn(conn, commit=True) as c:
        for row in rows or []:
            sid = str(
                (row or {}).get("steamid64")
                or (row or {}).get("steam64_id")
                or ""
            ).strip()
            if not sid or sid in seen:
                continue

            seen.add(sid)
            name = str((row or {}).get("name") or sid)

            upsert_player(
                {
                    "steamid64": sid,
                    "name": name,
                },
                mode="import",
                conn=c,
            )
            imported += 1

    logger.log(f"[DB] Imported/updated players from match stats count={imported}", level="INFO")
    return imported

def get_players():
    with get_conn() as conn:
        return conn.execute("""
        SELECT p.steamid64, p.name,
            COALESCE(pr.premier_rating, CAST(pr.leetify_rating * 10000 AS INTEGER), 0) AS rating
        FROM players p
        LEFT JOIN prime_ratings pr ON pr.steamid64 = p.steamid64
        ORDER BY rating DESC
        """).fetchall()


def get_players_by_rating_source(source="prime"):
    source_key = str(source or "prime").strip().lower()
    with get_conn() as conn:
        if source_key == "elo":
            return conn.execute(
                """
                SELECT
                    p.steamid64,
                    COALESCE(NULLIF(p.name, ''), p.steamid64) AS name,
                    CAST(ROUND(COALESCE(er.elo, 1500.0), 0) AS INTEGER) AS rating
                FROM players p
                LEFT JOIN elo_ratings er ON er.steamid64 = p.steamid64
                ORDER BY rating DESC, name COLLATE NOCASE ASC
                """
            ).fetchall()

        return conn.execute(
            """
            SELECT
                p.steamid64,
                p.name,
                COALESCE(pr.premier_rating, CAST(pr.leetify_rating * 10000 AS INTEGER), 0) AS rating
            FROM players p
            LEFT JOIN prime_ratings pr ON pr.steamid64 = p.steamid64
            ORDER BY rating DESC, name COLLATE NOCASE ASC
            """
        ).fetchall()

def update_player_name(player):
    now = datetime.utcnow().isoformat()

    with get_conn() as conn:
        execute_write(conn, """
            UPDATE players SET
                name = ?,
                last_updated = ?
            WHERE steamid64 = ?
        """, (
            player["name"],
            now,
            player["steamid64"]
        ))
    logger.log(f"[DB] Update player name {logger.redact(player['steamid64'])}", level="INFO")

def get_players_to_update(max_age_minutes=0):
    
    logger.log(
        f"[DB] Cooldown used = {max_age_minutes} minutes",
        level="DEBUG"
    )
    cutoff = (datetime.utcnow() - timedelta(minutes=max_age_minutes)).isoformat()

    with get_conn() as conn:
        cur = conn.execute("""
            SELECT steamid64 FROM players
            WHERE last_updated IS NULL OR last_updated < ?
        """, (cutoff,))
        cooldown_ids = {str(r[0]) for r in cur.fetchall() if r and r[0] is not None}

        newer_stats_cur = conn.execute(
            """
            SELECT
                p.steamid64
            FROM players p
            JOIN match_player_stats mps
              ON mps.steamid64 = p.steamid64
            LEFT JOIN match_maps mm
              ON mm.match_id = mps.match_id
             AND mm.map_number = mps.map_number
            LEFT JOIN matches m
              ON m.match_id = mps.match_id
            GROUP BY p.steamid64
            HAVING p.last_updated IS NULL OR MAX(COALESCE(mm.end_time, mm.start_time, m.end_time, m.start_time)) > p.last_updated
            """
        )
        newer_stats_ids = {str(r[0]) for r in newer_stats_cur.fetchall() if r and r[0] is not None}

        result = sorted(cooldown_ids | newer_stats_ids)

    logger.log(
        (
            "[DB] Players to update "
            f"cooldown={len(cooldown_ids)} newer_stats={len(newer_stats_ids)} "
            f"combined={len(result)}"
        ),
        level="DEBUG",
    )
    return result