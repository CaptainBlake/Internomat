"""Integration: Player update pipeline → profile_scrapper (mocked) → DB verification.

Tests the cross-layer flow:
  core.players.service.update_players()
    → core.players.pipeline.run_full_update()
      → services.profile_scrapper.get_leetify_player() [MOCKED]
      → services.matchzy.sync() [MOCKED]
    → db.players_db.update_player()
    → verify DB state
"""

from unittest.mock import patch, MagicMock

import pytest

from db.players_db import insert_player


# ---------------------------------------------------------------------------
# Canned Leetify API responses
# ---------------------------------------------------------------------------

def _leetify_response(steam_id, name, premier, leetify_rating, total_matches, winrate):
    return {
        "steam64_id": steam_id,
        "leetify_id": f"leetify-{steam_id[-4:]}",
        "name": name,
        "premier_rating": premier,
        "leetify_rating": leetify_rating,
        "total_matches": total_matches,
        "winrate": winrate,
    }


ALICE_ID = "76561198000000001"
BOB_ID = "76561198000000002"

LEETIFY_ALICE = _leetify_response(ALICE_ID, "Alice_Updated", 18000, 1.25, 55, 0.62)
LEETIFY_BOB = _leetify_response(BOB_ID, "Bob_Updated", 16000, 1.15, 40, 0.56)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPlayerUpdatePipeline:
    """update_players → mocked Leetify → DB round-trip."""

    def test_single_player_update(self, full_db):
        """Updating one player should persist the new rating and name."""
        conn, _ = full_db

        # Pre-state: Alice has premier_rating=16000
        pre = conn.execute(
            "SELECT premier_rating, name FROM players WHERE steam64_id = ?",
            (ALICE_ID,),
        ).fetchone()
        assert pre["premier_rating"] == 16000
        assert pre["name"] == "Alice"

        with patch("services.matchzy.sync"), \
             patch("services.profile_scrapper.get_leetify_player", return_value=LEETIFY_ALICE):

            from core.players.service import update_players

            errors = []
            finished = []
            update_players(
                [ALICE_ID],
                on_error=lambda e: errors.append(e),
                on_finish=lambda: finished.append(True),
            )

        assert not errors, f"Pipeline errors: {errors}"
        assert finished == [True]

        post = conn.execute(
            "SELECT premier_rating, name, leetify_rating, leetify_id FROM players WHERE steam64_id = ?",
            (ALICE_ID,),
        ).fetchone()
        assert post["premier_rating"] == 18000
        assert post["name"] == "Alice_Updated"
        assert post["leetify_rating"] == 1.25
        assert post["leetify_id"] == f"leetify-{ALICE_ID[-4:]}"

    def test_multiple_players_update(self, full_db):
        """Updating multiple players should update each one."""
        conn, _ = full_db

        def mock_leetify(steam_id, auto_close=False):
            if steam_id == ALICE_ID:
                return LEETIFY_ALICE
            if steam_id == BOB_ID:
                return LEETIFY_BOB
            raise ValueError(f"Unexpected steam_id: {steam_id}")

        with patch("services.matchzy.sync"), \
             patch("services.profile_scrapper.get_leetify_player", side_effect=mock_leetify):

            from core.players.service import update_players

            progress_calls = []
            update_players(
                [ALICE_ID, BOB_ID],
                on_progress=lambda i, t: progress_calls.append((i, t)),
            )

        # Both updated
        alice = conn.execute(
            "SELECT premier_rating FROM players WHERE steam64_id = ?", (ALICE_ID,),
        ).fetchone()
        bob = conn.execute(
            "SELECT premier_rating FROM players WHERE steam64_id = ?", (BOB_ID,),
        ).fetchone()

        assert alice["premier_rating"] == 18000
        assert bob["premier_rating"] == 16000
        # Progress called twice
        assert len(progress_calls) == 2
        assert progress_calls[-1] == (2, 2)

    def test_duplicate_steam_ids_deduplicated(self, full_db):
        """Pipeline should skip duplicate steam IDs."""
        conn, _ = full_db
        call_count = []

        def mock_leetify(steam_id, auto_close=False):
            call_count.append(steam_id)
            return LEETIFY_ALICE

        with patch("services.matchzy.sync"), \
             patch("services.profile_scrapper.get_leetify_player", side_effect=mock_leetify):

            from core.players.service import update_players
            update_players([ALICE_ID, ALICE_ID, ALICE_ID])

        # Should only call get_leetify_player once
        assert len(call_count) == 1

    def test_empty_steam_ids_calls_finish(self, full_db):
        """Empty list should immediately call on_finish."""
        finished = []

        with patch("services.matchzy.sync"), \
             patch("services.profile_scrapper.get_leetify_player") as mock:

            from core.players.service import update_players
            update_players([], on_finish=lambda: finished.append(True))

        mock.assert_not_called()
        assert finished == [True]

    def test_matchzy_sync_called(self, full_db):
        """The pipeline should call matchzy.sync() before updating players."""
        sync_mock = MagicMock()

        with patch("services.matchzy.sync", sync_mock), \
             patch("services.profile_scrapper.get_leetify_player", return_value=LEETIFY_ALICE):

            from core.players.service import update_players
            update_players([ALICE_ID])

        sync_mock.assert_called_once()

    def test_leetify_error_calls_on_error(self, full_db):
        """If get_leetify_player raises, on_error should be called."""
        errors = []

        with patch("services.matchzy.sync"), \
             patch("services.profile_scrapper.get_leetify_player",
                   side_effect=RuntimeError("API down")):

            from core.players.service import update_players
            update_players(
                [ALICE_ID],
                on_error=lambda e: errors.append(e),
            )

        assert len(errors) == 1
        assert "API down" in str(errors[0])

        # Original data should remain unchanged
        conn, _ = full_db
        row = conn.execute(
            "SELECT premier_rating FROM players WHERE steam64_id = ?", (ALICE_ID,),
        ).fetchone()
        assert row["premier_rating"] == 16000  # unchanged


class TestAddPlayerFromUrl:
    """service.add_player_from_url → mocked fetch → DB insert."""

    def test_add_new_player(self, full_db):
        """Adding a player not in DB should insert them."""
        conn, _ = full_db
        new_steam_id = "76561198099999999"

        canned = _leetify_response(new_steam_id, "NewPlayer", 20000, 1.30, 60, 0.65)

        with patch("services.profile_scrapper.fetch_player", return_value=canned):
            from core.players.service import add_player_from_url
            result = add_player_from_url("https://steamcommunity.com/profiles/" + new_steam_id)

        assert result["steam64_id"] == new_steam_id

        row = conn.execute(
            "SELECT name, premier_rating FROM players WHERE steam64_id = ?",
            (new_steam_id,),
        ).fetchone()
        assert row is not None
        assert row["name"] == "NewPlayer"
        assert row["premier_rating"] == 20000

    def test_add_existing_player_upserts(self, full_db):
        """Adding an existing player should upsert, not fail."""
        conn, _ = full_db

        canned = _leetify_response(ALICE_ID, "Alice_Refreshed", 19000, 1.28, 60, 0.64)

        with patch("services.profile_scrapper.fetch_player", return_value=canned):
            from core.players.service import add_player_from_url
            result = add_player_from_url("https://steamcommunity.com/profiles/" + ALICE_ID)

        assert result["name"] == "Alice_Refreshed"

        row = conn.execute(
            "SELECT premier_rating FROM players WHERE steam64_id = ?", (ALICE_ID,),
        ).fetchone()
        assert row["premier_rating"] == 19000
