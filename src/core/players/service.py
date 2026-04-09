import db.players_db as player_db
import services.profile_scrapper as profile_scrapper
import services.logger as logger
import core.players.pipeline as pipeline
from core.settings.settings import settings



# --- READ ---

def get_players():
    return player_db.get_players()


def get_players_for_teambuilder(rating_source="prime"):
    return player_db.get_players_by_rating_source(rating_source)


def get_players_to_update():
    return player_db.get_players_to_update(settings.update_cooldown_minutes)


# --- CREATE / UPDATE ---

def add_player_from_url(url):
    """
    Full flow:
    - fetch player
    - upsert into DB
    - return player
    """
    player = profile_scrapper.fetch_player(url)
    
    if not player:
        raise ValueError("Failed to fetch player")

    player_db.upsert_player(player)

    logger.log(f"[PLAYERS] Added {player.get('name')}", level="INFO")

    return player


def update_single_player(player):
    """
    Called during update pipeline
    """
    if not player:
        return

    player_db.update_player(player)
    player_db.record_premier_rating_history(player)


# --- DELETE ---

def delete_player(steam_id):
    player_db.delete_player(steam_id)
    logger.log(f"[PLAYERS] Deleted {steam_id}", level="INFO")


# --- BULK UPDATE (pipeline wrapper) ---

def update_players(
    steam_ids,
    on_progress=None,
    on_player=None,
    on_error=None,
    on_finish=None
):

    def _on_player(player): 
        update_single_player(player)

        if on_player:
            on_player(player)  

    return pipeline.run_full_update(
        steam_ids,
        run_matchzy_sync=True,
        on_progress=on_progress,
        on_player=_on_player,  
        on_error=on_error,
        on_finish=on_finish
    )
