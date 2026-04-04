from analytics.demo_payload_analysis import build_derived_movement_stats


def test_build_derived_movement_stats_preserves_join_key_types():
    payload = {
        "header": {"tickrate": 128},
        "rounds": [
            {
                "round_num": 1,
                "start": 90,
                "freeze_end": 95,
                "end": 130,
            }
        ],
        "ticks": [
            {
                "round_num": 1,
                "tick": 100,
                "steamid": 76561198000000001,
                "health": 100,
                "X": 0.0,
                "Y": 0.0,
                "Z": 0.0,
                "side": "CT",
            },
            {
                "round_num": 1,
                "tick": 101,
                "steamid": 76561198000000001,
                "health": 100,
                "X": 10.0,
                "Y": 0.0,
                "Z": 0.0,
                "side": "CT",
            },
        ],
    }

    derived = build_derived_movement_stats(payload)

    assert isinstance(derived, dict)
    assert len(derived.get("map_rows") or []) == 1
    assert len(derived.get("round_rows") or []) == 1
    assert (derived.get("round_rows") or [])[0].get("side") == "CT"