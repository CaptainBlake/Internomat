from db import statistics_scoreboard_db as scoreboard_repo
from core.stats import statistics_round_timeline
from core.stats.metrics import kd_ratio as _kdr, adr as _adr, hs_pct as _hs, accuracy_pct as _acc, success_pct as _spct
import services.logger as logger


def get_map_scoreboard(match_id, map_number):
    summary_row = scoreboard_repo.fetch_map_summary(match_id, map_number)
    scoreboard_rows = scoreboard_repo.fetch_map_scoreboard(match_id, map_number)

    summary = {
        "match_id": str(match_id),
        "map_number": int(map_number),
        "map_name": "?",
        "winner": "?",
        "team1_name": "",
        "team2_name": "",
        "team1_score": 0,
        "team2_score": 0,
        "played_at": "",
    }

    if summary_row is not None:
        summary = {
            "match_id": str(summary_row["match_id"] or match_id),
            "map_number": int(summary_row["map_number"] or map_number),
            "map_name": str(summary_row["map_name"] or "?"),
            "winner": str(summary_row["winner"] or "?"),
            "team1_name": str(summary_row["team1_name"] or ""),
            "team2_name": str(summary_row["team2_name"] or ""),
            "team1_score": int(summary_row["team1_score"] or 0),
            "team2_score": int(summary_row["team2_score"] or 0),
            "played_at": str(summary_row["played_at"] or ""),
        }

    total_rounds = int(summary.get("team1_score") or 0) + int(summary.get("team2_score") or 0)
    rounds_for_adr = total_rounds if total_rounds > 0 else None

    rows = []
    for r in scoreboard_rows:
        kills = int(r["kills"] or 0)
        deaths = int(r["deaths"] or 0)
        assists = int(r["assists"] or 0)
        damage = int(r["damage"] or 0)
        head_shot_kills = int(r["head_shot_kills"] or 0)
        shots_fired_total = int(r["shots_fired_total"] or 0)
        shots_on_target_total = int(r["shots_on_target_total"] or 0)
        entry_count = int(r["entry_count"] or 0)
        entry_wins = int(r["entry_wins"] or 0)
        v1_count = int(r["v1_count"] or 0)
        v1_wins = int(r["v1_wins"] or 0)
        v2_count = int(r["v2_count"] or 0)
        v2_wins = int(r["v2_wins"] or 0)
        utility_damage = int(r["utility_damage"] or 0)

        kd_ratio = _kdr(kills, deaths)
        adr = _adr(damage, rounds_for_adr)
        hs_pct = _hs(head_shot_kills, kills)
        acc_pct = _acc(shots_on_target_total, shots_fired_total)

        clutch_count = v1_count + v2_count
        clutch_wins = v1_wins + v2_wins
        entry_pct = _spct(entry_wins, entry_count)
        clutch_pct = _spct(clutch_wins, clutch_count)

        rows.append(
            {
                "team": str(r["team"] or "?"),
                "player_name": str(r["player_name"] or "?"),
                "steamid64": str(r["steamid64"] or ""),
                "kills": kills,
                "deaths": deaths,
                "assists": assists,
                "damage": damage,
                "kd_ratio": kd_ratio,
                "adr": adr,
                "hs_pct": hs_pct,
                "acc_pct": acc_pct,
                "entry_count": entry_count,
                "entry_wins": entry_wins,
                "entry_pct": entry_pct,
                "clutch_count": clutch_count,
                "clutch_wins": clutch_wins,
                "clutch_pct": clutch_pct,
                "utility_damage": utility_damage,
            }
        )

    logger.log(
        "[STATISTICS] "
        f"scoreboard match={summary['match_id']} map={summary['map_number']} "
        f"rows={len(rows)}",
        level="DEBUG",
    )

    timeline = statistics_round_timeline.build_round_timeline(summary)

    return {
        "summary": summary,
        "rows": rows,
        "timeline": timeline,
    }
