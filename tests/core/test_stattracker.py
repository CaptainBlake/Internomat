"""Tests for core.stats.stattracker."""

import pytest

from core.stats.stattracker import (
    get_map_match_series,
    get_movement_match_series,
    get_movement_plot_metric_options,
    get_movement_round_series,
    get_overview,
    get_player_dashboard,
    get_player_options,
    get_player_samples,
    get_player_weapon_categories,
    get_weapon_round_series,
)


class TestStattrackerOverview:
    def test_with_seeded_data(self, seeded_db, monkeypatch_db):
        result = get_overview()
        assert result["tracked_players"] == 6
        assert result["player_stat_rows"] == 14  # total rows in match_player_stats
        assert result["unique_player_maps"] == 14

    def test_empty_db(self, db_conn, monkeypatch_db):
        result = get_overview()
        assert result["tracked_players"] == 0
        assert result["player_stat_rows"] == 0


class TestGetPlayerSamples:
    def test_returns_players(self, seeded_db, monkeypatch_db):
        result = get_player_samples(limit=10)
        assert len(result) == 6
        # First entry should be the player with most kills (Alice: 25+15+20=60)
        assert result[0]["steamid64"] == "76561198000000001"
        assert result[0]["total_kills"] == 60

    def test_limit(self, seeded_db, monkeypatch_db):
        result = get_player_samples(limit=3)
        assert len(result) == 3

    def test_empty_db(self, db_conn, monkeypatch_db):
        result = get_player_samples(limit=10)
        assert result == []

    def test_row_structure(self, seeded_db, monkeypatch_db):
        result = get_player_samples(limit=1)
        row = result[0]
        assert "player_name" in row
        assert "steamid64" in row
        assert "map_entries" in row
        assert "total_kills" in row
        assert "total_deaths" in row


class TestGetPlayerOptions:
    def test_returns_all_players(self, seeded_db, monkeypatch_db):
        result = get_player_options()
        assert len(result) == 6
        ids = {r["steamid64"] for r in result}
        assert "76561198000000001" in ids

    def test_empty_db(self, db_conn, monkeypatch_db):
        result = get_player_options()
        assert result == []

    def test_row_structure(self, seeded_db, monkeypatch_db):
        result = get_player_options()
        for r in result:
            assert "steamid64" in r
            assert "player_name" in r
            assert "map_entries" in r


class TestGetPlayerWeaponCategories:
    def test_with_weapon_data(self, seeded_db, monkeypatch_db):
        # Alice has weapon stats seeded
        result = get_player_weapon_categories("76561198000000001")
        assert "all" in result
        assert len(result) >= 2  # "all" + at least one category

    def test_unknown_player(self, seeded_db, monkeypatch_db):
        result = get_player_weapon_categories("76561198099999999")
        assert result == ["all"]

    def test_empty_steamid(self, seeded_db, monkeypatch_db):
        result = get_player_weapon_categories("")
        assert result == ["all"]


class TestGetPlayerDashboard:
    def test_alice_kpis(self, seeded_db, monkeypatch_db):
        result = get_player_dashboard("76561198000000001")
        kpis = result["kpis"]

        # Alice played 3 maps
        assert kpis["maps_played"] == 3
        # Alice won match 100 (team_alpha) and match 102 (team_alpha)
        # Lost match 101 (team_alpha lost) → 2/3 wins
        assert 60 < kpis["win_rate"] < 70  # ~66.7%
        # KDR should be positive
        assert kpis["kdr"] > 0
        # ADR should be positive
        assert kpis["adr"] > 0

    def test_dashboard_has_required_keys(self, seeded_db, monkeypatch_db):
        result = get_player_dashboard("76561198000000001")
        assert "kpis" in result
        assert "map_rows" in result
        assert "weapon_rows" in result
        assert "best_map" in result
        assert "worst_map" in result

    def test_kpi_keys(self, seeded_db, monkeypatch_db):
        kpis = get_player_dashboard("76561198000000001")["kpis"]
        expected_keys = {
            "maps_played", "win_rate", "kdr", "adr",
            "avg_kills", "avg_deaths", "avg_assists",
            "hs_pct", "avg_kast", "avg_impact", "avg_rating",
            "performance_index",
            "avg_speed_m_s", "strafe_ratio", "camp_time_s",
        }
        assert expected_keys.issubset(set(kpis.keys()))

    def test_map_rows(self, seeded_db, monkeypatch_db):
        result = get_player_dashboard("76561198000000001")
        map_rows = result["map_rows"]
        # Alice played on de_dust2 (2x) and de_inferno (1x)
        map_names = {r["map_name"] for r in map_rows}
        assert "de_dust2" in map_names
        assert "de_inferno" in map_names

        for row in map_rows:
            assert "maps_played" in row
            assert "wins" in row
            assert "win_rate" in row
            assert "kdr" in row
            assert "adr" in row

    def test_weapon_rows(self, seeded_db, monkeypatch_db):
        result = get_player_dashboard("76561198000000001")
        weapon_rows = result["weapon_rows"]
        # Alice has ak-47 and usp-s weapon stats
        weapons = {r["weapon"] for r in weapon_rows}
        assert len(weapons) >= 2

        for row in weapon_rows:
            assert "weapon" in row
            assert "category" in row
            assert "shots_fired" in row
            assert "accuracy" in row
            assert "kills" in row
            assert "headshot_pct" in row

    def test_best_worst_map(self, seeded_db, monkeypatch_db):
        result = get_player_dashboard("76561198000000001")
        assert result["best_map"] != "-"
        assert result["worst_map"] != "-"
        assert isinstance(result["best_map"], str)

    def test_nonexistent_player_returns_defaults(self, seeded_db, monkeypatch_db):
        result = get_player_dashboard("76561198099999999")
        assert result["kpis"]["maps_played"] == 0
        assert result["kpis"]["win_rate"] == 0.0
        assert result["kpis"]["kdr"] == 0.0
        assert result["kpis"]["adr"] == 0.0
        assert result["map_rows"] == []
        assert result["weapon_rows"] == []

    def test_empty_steamid_returns_defaults(self, seeded_db, monkeypatch_db):
        result = get_player_dashboard("")
        assert result["kpis"]["maps_played"] == 0
        assert result["map_rows"] == []
        assert result["weapon_rows"] == []
        assert result["best_map"] == "-"
        assert result["worst_map"] == "-"

    def test_none_steamid_returns_defaults(self, seeded_db, monkeypatch_db):
        result = get_player_dashboard(None)
        assert result["kpis"]["maps_played"] == 0

    def test_weapon_category_filter(self, seeded_db, monkeypatch_db):
        # "all" should return all weapons
        result_all = get_player_dashboard("76561198000000001", weapon_category="all")
        # A non-matching category should return fewer (or zero) weapons
        result_none = get_player_dashboard("76561198000000001", weapon_category="smg")
        assert len(result_all["weapon_rows"]) >= len(result_none["weapon_rows"])

    def test_bob_dashboard(self, seeded_db, monkeypatch_db):
        """Bob has weapon stats too (m4a4 in match 100)."""
        result = get_player_dashboard("76561198000000002")
        assert result["kpis"]["maps_played"] == 3
        # Bob has at least m4a4 in weapon rows
        weapons = {r["weapon"] for r in result["weapon_rows"]}
        assert "m4a4" in weapons

    def test_global_kpis_use_full_totals_when_weapon_attribution_is_partial(self, monkeypatch):
        import core.stats.stattracker as stattracker_module

        monkeypatch.setattr(
            stattracker_module.stattracker_repo,
            "fetch_player_overall_metrics",
            lambda _sid, seasons=None: {
                "maps_played": 2,
                "map_wins": 1,
                "total_kills": 20,
                "total_deaths": 10,
                "total_assists": 4,
                "total_damage": 2000,
                "total_headshot_kills": 8,
                "total_rounds": 40,
                "avg_kast": 0.7,
                "avg_impact": 1.0,
                "avg_rating": 1.1,
            },
        )
        monkeypatch.setattr(
            stattracker_module.stattracker_repo,
            "fetch_player_overall_movement_metrics",
            lambda _sid, seasons=None: {
                "total_distance_units": 0.0,
                "strafe_distance_units": 0.0,
                "strafe_time_s": 0.0,
                "alive_seconds": 0.0,
                "camp_time_s": 0.0,
            },
        )
        monkeypatch.setattr(stattracker_module.stattracker_repo, "fetch_player_map_stats", lambda _sid, seasons=None: [])
        monkeypatch.setattr(
            stattracker_module.stattracker_repo,
            "fetch_player_weapon_stats",
            lambda _sid, min_shots, weapon_category, seasons=None: [
                {
                    "weapon": "ak-47",
                    "category": "rifles",
                    "shots_fired": 100,
                    "shots_hit": 30,
                    "kills": 10,
                    "headshot_kills": 4,
                    "damage": 1000,
                    "rounds_with_weapon": 20,
                }
            ],
        )
        monkeypatch.setattr(
            stattracker_module.stattracker_repo,
            "fetch_player_weapon_kill_attribution_deltas",
            lambda _sid, seasons=None: [],
        )

        result = stattracker_module.get_player_dashboard("76561198000000001")
        kpis = result["kpis"]

        # Global KPIs must remain tied to full match totals, not weapon-attributed subsets.
        assert kpis["kdr"] == pytest.approx(2.0)
        assert kpis["avg_kills"] == pytest.approx(10.0)
        assert kpis["hs_pct"] == pytest.approx(40.0)

    def test_camp_time_kpi_is_averaged_per_played_map(self, monkeypatch):
        import core.stats.stattracker as stattracker_module

        monkeypatch.setattr(
            stattracker_module.stattracker_repo,
            "fetch_player_overall_metrics",
            lambda _sid, seasons=None: {
                "maps_played": 4,
                "map_wins": 2,
                "total_kills": 40,
                "total_deaths": 20,
                "total_assists": 10,
                "total_damage": 4000,
                "total_headshot_kills": 16,
                "total_rounds": 80,
                "avg_kast": 0.7,
                "avg_impact": 1.0,
                "avg_rating": 1.1,
            },
        )
        monkeypatch.setattr(
            stattracker_module.stattracker_repo,
            "fetch_player_overall_movement_metrics",
            lambda _sid, seasons=None: {
                "total_distance_units": 0.0,
                "strafe_distance_units": 0.0,
                "strafe_time_s": 0.0,
                "alive_seconds": 0.0,
                "camp_time_s": 200.0,
            },
        )
        monkeypatch.setattr(stattracker_module.stattracker_repo, "fetch_player_map_stats", lambda _sid, seasons=None: [])
        monkeypatch.setattr(stattracker_module.stattracker_repo, "fetch_player_weapon_stats", lambda _sid, min_shots, weapon_category, seasons=None: [])
        monkeypatch.setattr(stattracker_module.stattracker_repo, "fetch_player_weapon_kill_attribution_deltas", lambda _sid, seasons=None: [])

        result = stattracker_module.get_player_dashboard("76561198000000001")
        kpis = result["kpis"]

        # 200 total camp seconds over 4 maps -> 50.0 shown in global KPI row.
        assert kpis["camp_time_s"] == pytest.approx(50.0)


class TestMovementSeries:
    def test_map_series_x_labels_use_timestamps(self, seeded_db, monkeypatch_db):
        series = get_map_match_series("76561198000000001", metric="kills")
        labels = list(series.get("x_labels") or [])

        assert labels
        assert labels[0] == "de_dust2\n01-10 20:00"
        assert all("de_" in str(label) for label in labels)

    def test_metric_options_include_avg_speed(self):
        opts = get_movement_plot_metric_options()
        keys = {o["key"] for o in opts}
        assert "avg_speed_m_s" in keys
        assert "max_speed_units_s" in keys
        assert "camp_time_s" in keys
        assert "freeze_distance_m" not in keys

    def test_get_movement_match_series(self, db_conn, monkeypatch_db):
        from db.stattracker_db import upsert_player_map_movement_stats_many

        upsert_player_map_movement_stats_many(
            [
                {
                    "steamid64": "76561198000000001",
                    "match_id": "100",
                    "map_number": 0,
                    "total_distance_units": 1000,
                    "total_distance_m": 25.4,
                    "avg_speed_units_s": 200,
                    "avg_speed_m_s": 5.08,
                    "max_speed_units_s": 300,
                    "ticks_alive": 1000,
                    "alive_seconds": 7.8,
                    "distance_per_round_units": 250,
                    "updated_at": "2026-04-05T00:00:00",
                },
            ],
            conn=db_conn,
        )
        db_conn.commit()

        series = get_movement_match_series("76561198000000001", metric="avg_speed_m_s")

        assert series["metric_label"] == "Avg Speed (m/s)"
        assert len(series["x_labels"]) >= 1
        assert "Movement" in (series["series"] or {})

    def test_get_movement_round_series(self, db_conn, monkeypatch_db):
        from db.stattracker_db import upsert_player_round_movement_stats_many

        upsert_player_round_movement_stats_many(
            [
                {
                    "steamid64": "76561198000000001",
                    "match_id": "100",
                    "map_number": 0,
                    "round_num": 1,
                    "distance_units": 500,
                    "live_distance_units": 450,
                    "strafe_distance_units": 120,
                    "strafe_ratio": 0.2,
                    "avg_speed_units_s": 190,
                    "max_speed_units_s": 280,
                    "ticks_alive": 300,
                    "alive_seconds": 2.34,
                    "stationary_ticks": 60,
                    "sprint_ticks": 120,
                    "strafe_ticks": 45,
                    "updated_at": "2026-04-05T00:00:00",
                },
            ],
            conn=db_conn,
        )
        db_conn.commit()

        series = get_movement_round_series("76561198000000001", metric="avg_speed_m_s")

        assert series["metric_label"] == "Avg Speed (m/s)"
        assert len(series["x_labels"]) >= 1
        assert "R01" in str(series["x_labels"][0])
        assert "Movement" in (series["series"] or {})

    def test_get_weapon_round_series(self, db_conn, monkeypatch_db):
        from db.stattracker_db import upsert_player_round_weapon_stats_many

        upsert_player_round_weapon_stats_many(
            [
                {
                    "steamid64": "76561198000000001",
                    "match_id": "100",
                    "map_number": 0,
                    "round_num": 1,
                    "weapon": "ak-47",
                    "shots_fired": 12,
                    "shots_hit": 5,
                    "kills": 1,
                    "headshot_kills": 1,
                    "damage": 100,
                    "updated_at": "2026-04-05T00:00:00",
                },
            ],
            conn=db_conn,
        )
        db_conn.commit()

        series = get_weapon_round_series("76561198000000001", metric="accuracy")

        assert series["metric_label"] == "Accuracy %"
        assert len(series["x_labels"]) >= 1
        assert "R01" in str(series["x_labels"][0])
        assert "ak-47" in (series["series"] or {})
