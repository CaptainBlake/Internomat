from datetime import datetime, timedelta
from .connection import get_conn
import services.logger as logger
from core.settings.settings import settings


def insert_player(player, conn=None):
    own = conn is None
    conn = conn or get_conn()

    now = datetime.utcnow().isoformat()

    conn.execute("""
        INSERT INTO players VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        player["steam64_id"],
        player.get("leetify_id"),
        player["name"],
        player.get("premier_rating"),
        player.get("leetify_rating"),
        player.get("total_matches"),
        player.get("winrate"),
        now,
        now
    ))

    if own:
        conn.commit()
        conn.close()

    logger.log(f"[DB] Insert player {logger.redact(player['steam64_id'])}", level="INFO")

def update_player(player, conn=None):
    own = conn is None
    conn = conn or get_conn()

    now = datetime.utcnow().isoformat()

    conn.execute("""
        UPDATE players SET
            leetify_id = ?,
            name = ?,
            premier_rating = ?,
            leetify_rating = ?,
            total_matches = ?,
            winrate = ?,
            last_updated = ?
        WHERE steam64_id = ?
    """, (
        player.get("leetify_id"),
        player["name"],
        player.get("premier_rating"),
        player.get("leetify_rating"),
        player.get("total_matches"),
        player.get("winrate"),
        now,
        player["steam64_id"]
    ))

    if own:
        conn.commit()
        conn.close()
    logger.log(f"[DB] Update player {logger.redact(player['steam64_id'])}", level="INFO")

def delete_player(steam_id):
    with get_conn() as conn:
        conn.execute("DELETE FROM players WHERE steam64_id = ?", (steam_id,))

    logger.log(f"[DB] Delete player {logger.redact(steam_id)}", level="INFO")

def upsert_player(player, mode="full", conn=None):
    own = conn is None
    conn = conn or get_conn()

    now = datetime.utcnow().isoformat()

    if mode == "import":
        conn.execute("""
            INSERT INTO players (steam64_id, name, added_at, last_updated)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(steam64_id) DO UPDATE SET
                name=excluded.name,
                last_updated=excluded.last_updated
        """, (
            player["steam64_id"],
            player["name"],
            now,
            now
        ))
    else:
        conn.execute("""
            INSERT INTO players VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(steam64_id) DO UPDATE SET
                leetify_id=excluded.leetify_id,
                name=excluded.name,
                premier_rating=excluded.premier_rating,
                leetify_rating=excluded.leetify_rating,
                total_matches=excluded.total_matches,
                winrate=excluded.winrate,
                last_updated=excluded.last_updated
        """, (
            player["steam64_id"],
            player.get("leetify_id"),
            player["name"],
            player.get("premier_rating"),
            player.get("leetify_rating"),
            player.get("total_matches"),
            player.get("winrate"),
            now,
            now
        ))

    if own:
        conn.commit()
        conn.close()
    logger.log(f"[DB] Upsert player {logger.redact(player['steam64_id'])}", level="DEBUG")

def get_players():
    with get_conn() as conn:
        return conn.execute("""
        SELECT steam64_id, name,
        COALESCE(premier_rating, CAST(leetify_rating * 10000 AS INTEGER), 0)
        FROM players
        ORDER BY 3 DESC
        """).fetchall()

def update_player_name(player):
    now = datetime.utcnow().isoformat()

    with get_conn() as conn:
        conn.execute("""
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

def get_players_to_update(max_age_minutes=None):
    if max_age_minutes is None:
        max_age_minutes = settings.update_cooldown_minutes
    
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
        result = [r[0] for r in cur.fetchall()]

    logger.log(f"[DB] Players to update count={len(result)}", level="DEBUG")
    return result