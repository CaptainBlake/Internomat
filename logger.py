from core import _distribution_score_raw

# --- team analysis ---
def _team_sum(team):
    return sum(p[2] for p in team)

def _format_team(team):
    sorted_team = sorted(team, key=lambda p: p[2], reverse=True)
    return [(p[1], p[2]) for p in sorted_team]

# --- logging ---
def log_team_roll(
    chosen,
    team_a,
    team_b,
    tolerance,
    best_score,
    candidate_count,
    acceptable_count,
    diverse_count
):
    sum_a = _team_sum(team_a)
    sum_b = _team_sum(team_b)

    total_diff = abs(sum_a - sum_b)
    dist_diff = _distribution_score_raw(team_a, team_b)

    print("\n=== TEAM ROLL ===")
    print(f"Score: {chosen[0]:.2f} (best: {best_score:.2f})")
    print(f"Total diff: {total_diff}")
    print(f"Distribution diff: {dist_diff}")
    print(f"Sum A: {sum_a} | Sum B: {sum_b}")

    print("\nParameters:")
    print(f"  Tolerance: {tolerance}")

    print("\nSearch space:")
    print(f"  Candidates: {candidate_count}")
    print(f"  Acceptable: {acceptable_count}")
    print(f"  Diverse pool: {diverse_count}")

    print("\nTeam A:")
    for name, rating in _format_team(team_a):
        print(f"  {name:<20} {rating}")

    print("\nTeam B:")
    for name, rating in _format_team(team_b):
        print(f"  {name:<20} {rating}")

    print("=================\n")

def log_team_roll_compact(
    chosen,
    team_a,
    team_b,
    tolerance,
    best_score,
    candidate_count,
    acceptable_count,
    diverse_count
):
    def short_team(team):
        ratings = sorted([p[2] for p in team], reverse=True)
        return ",".join(str(r // 1000) + "k" for r in ratings[:3])

    sum_a = _team_sum(team_a)
    sum_b = _team_sum(team_b)

    total_diff = abs(sum_a - sum_b)
    dist_diff = _distribution_score_raw(team_a, team_b)

    top_a = sum(sorted([p[2] for p in team_a], reverse=True)[:2])
    top_b = sum(sorted([p[2] for p in team_b], reverse=True)[:2])
    top_diff = abs(top_a - top_b)

    print(
        f"[S:{chosen[0]:.0f}/{best_score:.0f} "
        f"| Δ:{total_diff} "
        f"| D:{dist_diff} "
        f"| TopΔ:{top_diff} "
        f"| C:{candidate_count} A:{acceptable_count} Dv:{diverse_count} "
        f"| A:{sum_a//1000}k B:{sum_b//1000}k] "
        f"A[{short_team(team_a)}] vs B[{short_team(team_b)}]"
    )

