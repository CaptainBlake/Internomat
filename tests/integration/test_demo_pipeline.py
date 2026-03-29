"""Integration: Demo restore pipeline → DB verification.

Tests the restore_mixin._restore_db_entities_from_payload path with canned
parsed-payload data (i.e. what awpy.demo.Demo would produce after parsing),
then verifies that matches, match_maps, match_player_stats, and
player_map_weapon_stats rows appear in the DB — including weapon alias
normalization through weapon_dim / weapon_alias.

No real FTP, no real demo files, no real awpy parsing.
"""

import hashlib
import pickle
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from db.connection_db import get_conn
from services.demo_scrapper_components import (
    DemoScrapperCommonMixin,
    DemoScrapperMetricsMixin,
    DemoScrapperRestoreMixin,
)
import services.logger as logger


# ---------------------------------------------------------------------------
# A lightweight class that combines the three mixins used during restore
# ---------------------------------------------------------------------------

class _RestorableStub(
    DemoScrapperCommonMixin,
    DemoScrapperMetricsMixin,
    DemoScrapperRestoreMixin,
):
    """Minimal stand-in for DemoScrapperIntegration — just the mixins."""

    @staticmethod
    def _log_stage(stage, message, level="INFO"):
        logger.log(f"[{stage}] {message}", level=level)

    def __init__(self, parsed_demo_dir):
        self.parsed_demo_dir = Path(parsed_demo_dir)
        self.parsed_demo_dir.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Canned parsed payload that mimics awpy output (list-of-dict tables)
# ---------------------------------------------------------------------------

# 6 players, 2 teams, 3 rounds played
STEAMIDS = {
    "alice":   "76561198100000001",
    "bob":     "76561198100000002",
    "charlie": "76561198100000003",
    "diana":   "76561198100000004",
    "eve":     "76561198100000005",
    "frank":   "76561198100000006",
}

def _build_payload():
    """Return a synthetic parsed payload dict."""
    kills = [
        # Round 1 — CT wins
        {"round_num": 1, "attacker_steamid": STEAMIDS["alice"],   "attacker_side": "CT",
         "victim_steamid": STEAMIDS["diana"],   "victim_side": "T",
         "weapon": "ak-47", "headshot": True,
         "assister_steamid": STEAMIDS["bob"], "assister_side": "CT"},
        {"round_num": 1, "attacker_steamid": STEAMIDS["bob"],     "attacker_side": "CT",
         "victim_steamid": STEAMIDS["eve"],     "victim_side": "T",
         "weapon": "m4a1-s", "headshot": False,
         "assister_steamid": None, "assister_side": None},
        # Round 2 — T wins
        {"round_num": 2, "attacker_steamid": STEAMIDS["diana"],   "attacker_side": "T",
         "victim_steamid": STEAMIDS["alice"],   "victim_side": "CT",
         "weapon": "awp", "headshot": False,
         "assister_steamid": STEAMIDS["frank"], "assister_side": "T"},
        {"round_num": 2, "attacker_steamid": STEAMIDS["eve"],     "attacker_side": "T",
         "victim_steamid": STEAMIDS["charlie"], "victim_side": "CT",
         "weapon": "ak-47", "headshot": True,
         "assister_steamid": None, "assister_side": None},
        # Round 3 — CT wins
        {"round_num": 3, "attacker_steamid": STEAMIDS["alice"],   "attacker_side": "CT",
         "victim_steamid": STEAMIDS["frank"],   "victim_side": "T",
         "weapon": "usp-s", "headshot": True,
         "assister_steamid": None, "assister_side": None},
    ]

    damages = [
        {"round_num": 1, "attacker_steamid": STEAMIDS["alice"],   "attacker_side": "CT",
         "victim_steamid": STEAMIDS["diana"],   "victim_side": "T",
         "weapon": "ak-47", "damage": 100, "health_damage": 100},
        {"round_num": 1, "attacker_steamid": STEAMIDS["bob"],     "attacker_side": "CT",
         "victim_steamid": STEAMIDS["eve"],     "victim_side": "T",
         "weapon": "m4a1-s", "damage": 100, "health_damage": 100},
        {"round_num": 2, "attacker_steamid": STEAMIDS["diana"],   "attacker_side": "T",
         "victim_steamid": STEAMIDS["alice"],   "victim_side": "CT",
         "weapon": "awp", "damage": 100, "health_damage": 100},
        {"round_num": 2, "attacker_steamid": STEAMIDS["eve"],     "attacker_side": "T",
         "victim_steamid": STEAMIDS["charlie"], "victim_side": "CT",
         "weapon": "ak-47", "damage": 100, "health_damage": 100},
        {"round_num": 3, "attacker_steamid": STEAMIDS["alice"],   "attacker_side": "CT",
         "victim_steamid": STEAMIDS["frank"],   "victim_side": "T",
         "weapon": "usp-s", "damage": 100, "health_damage": 100},
    ]

    rounds = [
        {"round_num": 1, "winner_side": "CT", "ct_side": "TeamAlpha", "t_side": "TeamBravo"},
        {"round_num": 2, "winner_side": "T",  "ct_side": "TeamAlpha", "t_side": "TeamBravo"},
        {"round_num": 3, "winner_side": "CT", "ct_side": "TeamAlpha", "t_side": "TeamBravo"},
    ]

    # Shots rows used to seed per-player weapon stats via derived_weapon_stats
    shots = [
        {"round_num": 1, "player_steamid": STEAMIDS["alice"],   "player_side": "CT",
         "weapon": "ak-47"},
        {"round_num": 1, "player_steamid": STEAMIDS["bob"],     "player_side": "CT",
         "weapon": "m4a1-s"},
        {"round_num": 2, "player_steamid": STEAMIDS["diana"],   "player_side": "T",
         "weapon": "awp"},
        {"round_num": 3, "player_steamid": STEAMIDS["alice"],   "player_side": "CT",
         "weapon": "usp-s"},
    ]

    # derived_weapon_stats is pre-built by the parser layer before restore
    derived_weapon_stats = {
        STEAMIDS["alice"]: {
            "ak-47": {"shots_fired": 50, "shots_hit": 20, "kills": 1,
                       "headshot_kills": 1, "damage": 100, "rounds_with_weapon": 2},
            "usp-s":  {"shots_fired": 15, "shots_hit": 8,  "kills": 1,
                       "headshot_kills": 1, "damage": 100, "rounds_with_weapon": 1},
        },
        STEAMIDS["bob"]: {
            "m4a1-s": {"shots_fired": 40, "shots_hit": 18, "kills": 1,
                       "headshot_kills": 0, "damage": 100, "rounds_with_weapon": 2},
        },
        STEAMIDS["diana"]: {
            "awp":    {"shots_fired": 10, "shots_hit": 5,  "kills": 1,
                       "headshot_kills": 0, "damage": 100, "rounds_with_weapon": 1},
        },
        STEAMIDS["eve"]: {
            "ak-47":  {"shots_fired": 30, "shots_hit": 12, "kills": 1,
                       "headshot_kills": 1, "damage": 100, "rounds_with_weapon": 1},
        },
    }

    return {
        "header": {"map_name": "de_dust2"},
        "kills": kills,
        "damages": damages,
        "rounds": rounds,
        "shots": shots,
        "derived_weapon_stats": derived_weapon_stats,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha256(data_bytes):
    return hashlib.sha256(data_bytes).hexdigest()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRestorePayloadToDB:
    """Verify that _restore_db_entities_from_payload writes correct rows."""

    @pytest.fixture
    def stub(self, tmp_path):
        return _RestorableStub(parsed_demo_dir=tmp_path / "parsed")

    @pytest.fixture
    def payload(self):
        return _build_payload()

    @pytest.fixture
    def restored(self, full_db, stub, payload, tmp_path):
        """Run the restore and return (conn, target_match_id, target_map_number)."""
        conn, db_file = full_db

        # Persist a fake cache file so the canonical-alias helper doesn't break
        cache_dir = tmp_path / "parsed"
        cache_dir.mkdir(parents=True, exist_ok=True)
        pkl_bytes = pickle.dumps(payload)
        sha = _sha256(pkl_bytes)

        source_file = "2026-03-01_20-00-00_match_500_map_0_de_dust2.dem"

        ok, n_players, target_mid, target_map = stub._restore_db_entities_from_payload(
            match_id=500,
            map_number=0,
            parsed_payload=payload,
            source_file=source_file,
            payload_sha256=sha,
            conn=conn,
            source_match_to_canonical={},
            next_local_match_id_state={"value": 1000},
        )
        conn.commit()

        assert ok is True
        assert n_players > 0
        return conn, target_mid, target_map

    # -- match row --
    def test_match_inserted(self, restored):
        conn, mid, _ = restored
        row = conn.execute(
            "SELECT * FROM matches WHERE match_id = ?", (mid,)
        ).fetchone()
        assert row is not None
        assert row["team1_score"] is not None

    # -- match_map row --
    def test_match_map_inserted(self, restored):
        conn, mid, mnum = restored
        row = conn.execute(
            "SELECT * FROM match_maps WHERE match_id = ? AND map_number = ?",
            (mid, mnum),
        ).fetchone()
        assert row is not None
        assert row["map_name"] == "de_dust2"

    # -- player stats rows --
    def test_player_stats_inserted(self, restored):
        conn, mid, mnum = restored
        rows = conn.execute(
            "SELECT * FROM match_player_stats WHERE match_id = ? AND map_number = ?",
            (mid, mnum),
        ).fetchall()
        steamids_in_db = {row["steamid64"] for row in rows}
        # At least the players from kills/damages should appear
        for sid in [STEAMIDS["alice"], STEAMIDS["bob"], STEAMIDS["diana"], STEAMIDS["eve"]]:
            assert sid in steamids_in_db, f"{sid} missing from match_player_stats"

    def test_player_stats_kill_counts(self, restored):
        conn, mid, mnum = restored
        # Alice had 2 kills in the payload (round 1 + round 3)
        row = conn.execute(
            "SELECT kills FROM match_player_stats WHERE match_id = ? AND map_number = ? AND steamid64 = ?",
            (mid, mnum, STEAMIDS["alice"]),
        ).fetchone()
        assert row is not None
        assert row["kills"] >= 2

    # -- weapon stats rows --
    def test_weapon_stats_inserted(self, restored):
        conn, mid, mnum = restored
        rows = conn.execute(
            "SELECT * FROM player_map_weapon_stats WHERE match_id = ? AND map_number = ?",
            (mid, mnum),
        ).fetchall()
        assert len(rows) >= 4  # at least 4 weapon entries from derived_weapon_stats

    def test_weapon_stats_alice_ak47(self, restored):
        conn, mid, mnum = restored
        row = conn.execute(
            """SELECT kills, headshot_kills, shots_fired
               FROM player_map_weapon_stats
               WHERE match_id = ? AND map_number = ? AND steamid64 = ? AND weapon = ?""",
            (mid, mnum, STEAMIDS["alice"], "ak-47"),
        ).fetchone()
        assert row is not None
        assert row["kills"] == 1
        assert row["headshot_kills"] == 1
        assert row["shots_fired"] == 50

    # -- demo flag --
    def test_match_demo_flag_set(self, restored):
        conn, mid, _ = restored
        row = conn.execute(
            "SELECT demo FROM matches WHERE match_id = ?", (mid,)
        ).fetchone()
        assert row["demo"] == 1

    # -- team names --
    def test_team_names_populated(self, restored):
        conn, mid, _ = restored
        row = conn.execute(
            "SELECT team1_name, team2_name FROM matches WHERE match_id = ?",
            (mid,),
        ).fetchone()
        # The clustered result should resolve team names from rounds' ct_side/t_side
        assert row["team1_name"] is not None
        assert row["team2_name"] is not None
        assert row["team1_name"] != ""
        assert row["team2_name"] != ""

    # -- scores --
    def test_scores_computed(self, restored):
        conn, mid, mnum = restored
        row = conn.execute(
            "SELECT team1_score, team2_score FROM match_maps WHERE match_id = ? AND map_number = ?",
            (mid, mnum),
        ).fetchone()
        # CT won rounds 1 & 3, T won round 2 → 2-1
        total = (row["team1_score"] or 0) + (row["team2_score"] or 0)
        assert total == 3  # 3 rounds total

    # -- restore signature --
    def test_restore_signature_written(self, restored):
        conn, _, _ = restored
        row = conn.execute(
            "SELECT * FROM cache_restore_state WHERE source_match_id = '500' AND source_map_number = 0"
        ).fetchone()
        assert row is not None
        assert row["payload_sha256"] is not None


class TestRestoreIdempotency:
    """Running the same restore twice should not duplicate rows."""

    def test_double_restore_no_duplicates(self, full_db, tmp_path):
        conn, db_file = full_db
        stub = _RestorableStub(parsed_demo_dir=tmp_path / "parsed")
        payload = _build_payload()
        pkl_bytes = pickle.dumps(payload)
        sha = _sha256(pkl_bytes)
        source_file = "2026-03-01_20-00-00_match_600_map_0_de_dust2.dem"
        state = {"value": 2000}
        canonical_map = {}

        for _ in range(2):
            ok, _, mid, mnum = stub._restore_db_entities_from_payload(
                match_id=600,
                map_number=0,
                parsed_payload=payload,
                source_file=source_file,
                payload_sha256=sha,
                conn=conn,
                source_match_to_canonical=canonical_map,
                next_local_match_id_state=state,
            )
            conn.commit()
            assert ok is True

        # Player stats should not be doubled — PRIMARY KEY constraint upserts
        rows = conn.execute(
            "SELECT COUNT(*) as cnt FROM match_player_stats WHERE match_id = ?",
            (mid,),
        ).fetchone()
        # Each unique (steamid64, match_id, map_number) should appear once
        assert rows["cnt"] <= 10  # payload has ≤6 unique players


class TestWeaponAliasNormalization:
    """Weapon stats should be queryable via weapon_alias JOINs."""

    def test_alias_join_resolves(self, full_db, tmp_path):
        conn, _ = full_db
        stub = _RestorableStub(parsed_demo_dir=tmp_path / "parsed")
        payload = _build_payload()
        sha = _sha256(pickle.dumps(payload))
        source_file = "2026-03-02_19-00-00_match_700_map_0_de_dust2.dem"

        ok, _, target_mid, target_mnum = stub._restore_db_entities_from_payload(
            match_id=700,
            map_number=0,
            parsed_payload=payload,
            source_file=source_file,
            payload_sha256=sha,
            conn=conn,
            source_match_to_canonical={},
            next_local_match_id_state={"value": 3000},
        )
        conn.commit()
        assert ok is True

        # Query weapon stats via alias JOIN (the same pattern stattracker uses)
        rows = conn.execute(
            """
            SELECT
                pmws.steamid64,
                COALESCE(wa.canonical_weapon, pmws.weapon) AS canonical,
                pmws.kills
            FROM player_map_weapon_stats pmws
            LEFT JOIN weapon_alias wa ON wa.raw_weapon = pmws.weapon
            WHERE pmws.match_id = ?
            ORDER BY pmws.kills DESC
            """,
            (target_mid,),
        ).fetchall()
        assert len(rows) >= 4
        # All canonical weapons should exist in weapon_dim
        for row in rows:
            dim_row = conn.execute(
                "SELECT 1 FROM weapon_dim WHERE weapon = ?",
                (row["canonical"],),
            ).fetchone()
            # Weapons from seed or observed should be present
            assert dim_row is not None, f"weapon_dim missing {row['canonical']}"
