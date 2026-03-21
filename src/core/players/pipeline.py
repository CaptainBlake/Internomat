import services.logger as logger
import services.crawler as crawler
import services.matchzy_db as matchzy

# UPDATE PIPELINE
def update_players_pipeline(
    steam_ids,
    on_progress=None,
    on_player=None,
    on_error=None,
    on_finish=None
):
    """
    Core update pipeline.
    UI should pass callbacks, NOT signals directly.

    Keeps logic centralized and UI-independent.
    """
    
    try:
        # --- MATCHZY SYNC ---
        try:
            logger.log("[UPDATE] Starting MatchZy sync", level="INFO")
            matchzy.sync()
        except Exception as e:
            if on_error:
                on_error(e)

        logger.log(f"[UPDATE] Players to update={len(steam_ids)}", level="INFO")

        if not steam_ids:
            if on_finish:
                on_finish()
            return
        
        total = len(steam_ids)
        seen = set()

        for i, steam_id in enumerate(steam_ids, start=1):

            # --- DUPLICATE GUARD ---
            if steam_id in seen:
                continue
            seen.add(steam_id)

            try:
                player = crawler.get_leetify_player(steam_id)

                if on_player:
                    on_player(player)

            except Exception as e:
                if on_error:
                    on_error(e)
                return

            if on_progress:
                on_progress(i, total)

        if on_finish:
            on_finish()

    except Exception as e:
        if on_error:
            on_error(e)

    finally:
        # --- ALWAYS CLEANUP ---
        logger.log("[UPDATE] Cleaning up crawler", level="DEBUG")
        crawler.close_driver()
