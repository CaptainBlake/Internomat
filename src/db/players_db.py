from datetime import datetime, timedelta
from .connection_db import execute_write, get_conn, optional_conn
import services.logger as logger


def insert_player(player, conn=None):
    now = datetime.utcnow().isoformat()

    with optional_conn(conn, commit=True) as c:
        execute_write(c, """
            INSERT INTO players VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            player["steam64_id"],
            player.get("leetify_id"),
            player["name"],
            player.get("premier_rating"),
            player.get("leetify_rating"),
            player.get("total_matches"),
            player.get("winrate"),
            now,
            now,
            player.get("rating_source"),
            player.get("rating_season"),
        ))

    logger.log(f"[DB] Insert player {logger.redact(player['steam64_id'])}", level="INFO")

def update_player(player, conn=None):
    now = datetime.utcnow().isoformat()

    with optional_conn(conn, commit=True) as c:
        execute_write(c, """
            UPDATE players SET
                leetify_id = ?,
                name = ?,
                premier_rating = ?,
                leetify_rating = ?,
                total_matches = ?,
                winrate = ?,
                last_updated = ?,
                rating_source = ?,
                rating_season = ?
            WHERE steam64_id = ?
        """, (
            player.get("leetify_id"),
            player["name"],
            player.get("premier_rating"),
            player.get("leetify_rating"),
            player.get("total_matches"),
            player.get("winrate"),
            now,
            player.get("rating_source"),
            player.get("rating_season"),
            player["steam64_id"]
        ))

    logger.log(f"[DB] Update player {logger.redact(player['steam64_id'])} source={player.get('rating_source')}", level="INFO")

def delete_player(steam_id):
    with get_conn() as conn:
        execute_write(conn, "DELETE FROM players WHERE steam64_id = ?", (steam_id,))

    logger.log(f"[DB] Delete player {logger.redact(steam_id)}", level="INFO")

def upsert_player(player, mode="full", conn=None):
    now = datetime.utcnow().isoformat()

    with optional_conn(conn, commit=True) as c:
        if mode == "import":
            execute_write(c, """
                INSERT INTO players (steam64_id, name, added_at)
                VALUES (?, ?, ?)
                ON CONFLICT(steam64_id) DO UPDATE SET
                    name=excluded.name
            """, (
                player["steam64_id"],
                player["name"],
                now,
            ))
        else:
            execute_write(c, """
                INSERT INTO players VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(steam64_id) DO UPDATE SET
                    leetify_id=excluded.leetify_id,
                    name=excluded.name,
                    premier_rating=excluded.premier_rating,
                    leetify_rating=excluded.leetify_rating,
                    total_matches=excluded.total_matches,
                    winrate=excluded.winrate,
                    last_updated=excluded.last_updated,
                    rating_source=excluded.rating_source,
                    rating_season=excluded.rating_season
            """, (
                player["steam64_id"],
                player.get("leetify_id"),
                player["name"],
                player.get("premier_rating"),
                player.get("leetify_rating"),
                player.get("total_matches"),
                player.get("winrate"),
                now,
                now,
                player.get("rating_source"),
                player.get("rating_season"),
            ))

    logger.log(f"[DB] Upsert player {logger.redact(player['steam64_id'])}", level="DEBUG")


def upsert_players_from_match_stats(rows, conn=None):
    imported = 0
    seen = set()

    with optional_conn(conn, commit=True) as c:
        for row in rows or []:
            steam64_id = str(
                (row or {}).get("steam64_id")
                or (row or {}).get("steamid64")
                or ""
            ).strip()
            if not steam64_id or steam64_id in seen:
                continue

            seen.add(steam64_id)
            name = str((row or {}).get("name") or steam64_id)

            upsert_player(
                {
                    "steam64_id": steam64_id,
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
        SELECT steam64_id, name,
        COALESCE(premier_rating, CAST(leetify_rating * 10000 AS INTEGER), 0)
        FROM players
        ORDER BY 3 DESC
        """).fetchall()


def get_players_by_rating_source(source="prime"):
    source_key = str(source or "prime").strip().lower()
    with get_conn() as conn:
        if source_key == "elo":
            return conn.execute(
                """
                SELECT
                    p.steam64_id,
                    COALESCE(NULLIF(p.name, ''), p.steam64_id) AS name,
                    CAST(ROUND(COALESCE(er.elo, 1500.0), 0) AS INTEGER) AS rating
                FROM players p
                LEFT JOIN elo_ratings er ON er.steamid64 = p.steam64_id
                ORDER BY rating DESC, name COLLATE NOCASE ASC
                """
            ).fetchall()

        return conn.execute(
            """
            SELECT
                steam64_id,
                name,
                COALESCE(premier_rating, CAST(leetify_rating * 10000 AS INTEGER), 0) AS rating
            FROM players
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
            WHERE steam64_id = ?
        """, (
            player["name"],
            now,
            player["steam64_id"]
        ))
    logger.log(f"[DB] Update player name {logger.redact(player['steam64_id'])}", level="INFO")

def get_players_to_update(max_age_minutes=0):
    
    logger.log(
        f"[DB] Cooldown used = {max_age_minutes} minutes",
        level="DEBUG"
    )
    cutoff = (datetime.utcnow() - timedelta(minutes=max_age_minutes)).isoformat()

    with get_conn() as conn:
        cur = conn.execute("""
            SELECT steam64_id FROM players
            WHERE last_updated IS NULL OR last_updated < ?
        """, (cutoff,))
        cooldown_ids = {str(r[0]) for r in cur.fetchall() if r and r[0] is not None}

        newer_stats_cur = conn.execute(
            """
            SELECT
                p.steam64_id
            FROM players p
            JOIN match_player_stats mps
              ON mps.steamid64 = p.steam64_id
            LEFT JOIN match_maps mm
              ON mm.match_id = mps.match_id
             AND mm.map_number = mps.map_number
            LEFT JOIN matches m
              ON m.match_id = mps.match_id
            GROUP BY p.steam64_id
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