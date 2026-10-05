import sys
import pathlib

_PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import pandas as pd
from scoring import predict_score, build_live_features

HISTORICAL_ROLLING_AVERAGES = pd.read_csv("data/processed/training_data.csv", low_memory=False)

def add_scores(players_df, live_features):
    live_features = live_features.copy()
    live_features["score"] = predict_score(live_features)
    players_df = players_df.merge(live_features[["id", "score"]], on="id", how="left")
    players_df["score"] = players_df["score"].fillna(-999)  # blank GW / no data this week
    return players_df

def find_weak_links(squad_df, n=3):
    injured = squad_df[squad_df["status"] != "a"]
    healthy = squad_df[(squad_df["status"] == "a") & (squad_df["score"] != -999)].sort_values("score")
    remaining_slots = max(n - len(injured), 0)
    weaklinks = pd.concat([injured, healthy.head(remaining_slots)])
    return weaklinks.head(n)

def get_squad_concerns(scored_squad, bottom_percentile=0.35):
    """
    Returns a DataFrame of every squad concern — injured/doubtful/suspended
    players, plus healthy players in the bottom `bottom_percentile` of this
    squad's own score range — sorted worst-first (injured before low-scorers,
    then by ascending score within each group).

    This is now the SINGLE source of truth for "which players need
    attention" — both the concern count/names shown in the Wildcard nudge,
    and the transfer suggestions table, are built from this same list, so
    the two numbers can never silently disagree again.
    """
    injured = scored_squad[scored_squad["status"] != "a"]
    healthy = scored_squad[(scored_squad["status"] == "a") & (scored_squad["score"] != -999)]

    if len(healthy) > 0:
        cutoff = healthy["score"].quantile(bottom_percentile)
        weak = healthy[healthy["score"] <= cutoff]
    else:
        weak = healthy

    concerns = pd.concat([injured, weak]).drop_duplicates(subset="id").copy()
    concerns["is_injured"] = concerns["status"] != "a"
    concerns = concerns.sort_values(["is_injured", "score"], ascending=[False, True])
    return concerns.drop(columns="is_injured")


def find_best_replacement(player_to_replace, all_players_df, squad_ids, budget):
    position = player_to_replace["position"]
    max_price = player_to_replace["now_cost"] + budget

    candidates = all_players_df[
        (all_players_df["position"] == position) &
        (~all_players_df["id"].isin(squad_ids)) &
        (all_players_df["now_cost"] <= max_price) &
        (all_players_df["status"] == "a") &
        (all_players_df["score"] != -999)   # never suggest a blank-GW / no-data player
    ]

    if candidates.empty:
        return None
    return candidates.sort_values("score", ascending=False).iloc[0]

def suggest_transfers(squad_df, all_players_df, squad_ids, gameweek, bank,
                       free_transfers=None, active_chip=None, hit_threshold=4.0):
    """
    Evaluates a transfer for EVERY squad concern (not an arbitrary top-3
    subset) — so the concern count and the number of suggestions shown
    always match. Each concern gets a labeled suggestion: Free, a hit
    that's worth it, explicitly "not worth it" with the point swing shown,
    or "no upgrade available" if the best candidate found is actually worse
    — rather than any of these being silently dropped or mislabeled.
    """
    live_features = build_live_features(gameweek, HISTORICAL_ROLLING_AVERAGES)
    scored_squad = add_scores(squad_df, live_features)
    scored_all = add_scores(all_players_df, live_features)

    concerns = get_squad_concerns(scored_squad)
    chip_makes_transfers_free = active_chip in ("wildcard", "freehit")

    remaining_budget = bank
    already_suggested_ids = []
    suggestions = []

    for i, (_, player) in enumerate(concerns.iterrows()):
        replacement = find_best_replacement(
            player, scored_all, squad_ids + already_suggested_ids, budget=remaining_budget
        )
        reason = "Injured/Doubtful" if player["status"] != "a" else "Low score"

        if replacement is None:
            suggestions.append({
                "sell": player["web_name"], "sell_price": player["now_cost"],
                "sell_score": player["score"], "reason": reason,
                "buy": "No suitable replacement found", "buy_price": None,
                "buy_score": None, "cost": None,
                "remaining_budget": round(remaining_budget, 1),
            })
            continue

        net_gain = replacement["score"] - player["score"]

        if net_gain < 0:
            # Best available candidate is actually worse than the player
            # being sold — don't suggest a downgrade, be honest that
            # nothing better was found instead.
            suggestions.append({
                "sell": player["web_name"], "sell_price": player["now_cost"],
                "sell_score": player["score"], "reason": reason,
                "buy": "No upgrade available within budget", "buy_price": None,
                "buy_score": None, "cost": None,
                "remaining_budget": round(remaining_budget, 1),
            })
            continue

        already_suggested_ids.append(replacement["id"])  # never suggest the same replacement twice
        is_actionable = False

        if chip_makes_transfers_free:
            cost_label = "Free (chip active)"
            is_actionable = True
        elif free_transfers is None:
            cost_label = "Cost unknown"
        elif i < free_transfers:
            cost_label = "Free"
            is_actionable = True
        elif net_gain > hit_threshold:
            cost_label = "-4 (hit) — worth it"
            is_actionable = True
        else:
            cost_label = f"-4 (hit) — not worth it (+{net_gain:.1f} pts)"

        # Only reserve budget for moves we're actually recommending — a
        # "not worth it" or "cost unknown" suggestion is shown for
        # transparency but the user isn't expected to act on it.
        if is_actionable:
            cost_change = replacement["now_cost"] - player["now_cost"]
            remaining_budget -= cost_change

        suggestions.append({
            "sell": player["web_name"], "sell_price": player["now_cost"],
            "sell_score": player["score"], "reason": reason,
            "buy": replacement["web_name"], "buy_price": replacement["now_cost"],
            "buy_score": replacement["score"], "cost": cost_label,
            "remaining_budget": round(remaining_budget, 1),
        })

    concern_count = len(concerns)
    concern_players = concerns["web_name"].tolist()

    return pd.DataFrame(suggestions), concern_count, concern_players

def suggest_captain(squad_df, fixtures_df, gameweek):
    """
    Suggests both captain AND vice-captain: the top two players by
    captain_score. This matters because if your captain gets 0 minutes,
    FPL automatically hands the armband to your vice-captain — so the VC
    pick uses the exact same eligibility/scoring logic as captain, not a
    weaker fallback.
    """
    live_features = build_live_features(gameweek, HISTORICAL_ROLLING_AVERAGES)
    scored_squad = add_scores(squad_df, live_features).copy()

    eligible = scored_squad[(scored_squad["status"] == "a") & (scored_squad["score"] != -999)]
    if eligible.empty:
        eligible = scored_squad  # rare fallback: whole squad blank this GW

    from analysis.team_analyzer import get_upcoming_difficulty
    eligible = eligible.copy()
    eligible["fixture_ease"] = eligible["team"].apply(
        lambda team_id: 6 - (get_upcoming_difficulty(team_id, fixtures_df, next_n=1) or 3)
    )
    eligible["captain_score"] = eligible["score"] + (0.5 * eligible["fixture_ease"])

    ranked = eligible.sort_values("captain_score", ascending=False)

    captain = ranked.iloc[0]
    vice_captain = ranked.iloc[1] if len(ranked) > 1 else None

    return captain, vice_captain

def suggest_triple_captain(captain_row, fixtures_df, gameweek, all_team_ids, chip_status, active_chip):
    """
    Returns a suggestion string if Triple Captain is available, not already
    active, and the suggested captain's real-world team has a double
    gameweek. Triple Captain multiplies captain points by 3 — most valuable
    when that player has two matches to score in, not one.

    Unlike Bench Boost's threshold, this is a simple yes/no: either your
    specific captain doubles or they don't — there's no "how many" scale
    to tune here.
    """
    if chip_status.get("3xc") != "available" or active_chip is not None:
        return None

    from analysis.team_analyzer import get_fixtures_counts
    fixture_counts = get_fixtures_counts(fixtures_df, gameweek, all_team_ids)
    captain_fixture_count = fixture_counts.get(captain_row["team"], 0)

    if captain_fixture_count >= 2:
        return (f"🔥 _Your captain pick, {captain_row['web_name']}, has a double gameweek in GW{gameweek} "
                f"— Triple Captain (still available this half) could be especially valuable here._\n")
    return None

if __name__ == "__main__":
    from api.data_fetcher import get_players_dataframe, get_fixtures, get_current_gameweek, get_planning_gameweek
    from analysis.team_analyzer import get_squad_player_ids, build_squad_from_ids, get_free_transfers

    MY_TEAM_ID = 2093872
    GAMEWEEK = get_current_gameweek()       # for fetching the actual locked squad
    planning_gw = get_planning_gameweek()   # the GW to plan transfers/captain for
    BANK = 0.5

    status, player_ids, bank, active_chip = get_squad_player_ids(MY_TEAM_ID, GAMEWEEK)
    if status != "ok":
        print(f"⚠️  Squad unavailable ({status}) — using mock squad from config/my_squad.json")
        player_ids = load_mock_squad()
        bank = BANK
        active_chip = None

    free_transfers = get_free_transfers(MY_TEAM_ID, planning_gw)

    squad = build_squad_from_ids(player_ids)
    all_players = get_players_dataframe()

    print("\n--- Transfer Suggestions ---")
    transfers, concern_count, concern_players = suggest_transfers(
        squad, all_players, player_ids, planning_gw, bank=bank,
        free_transfers=free_transfers, active_chip=active_chip
    )
    print(transfers)
    print(f"\nSquad concern count: {concern_count}")
    print(f"Concerning players: {concern_players}")

    print("\n--- Captain / Vice-Captain Suggestion ---")
    fixtures_df = get_fixtures()
    captain, vice_captain = suggest_captain(squad, fixtures_df, planning_gw)
    print(f"Captain: {captain['web_name']} (score: {captain['captain_score']:.2f})")
    if vice_captain is not None:
        print(f"Vice-captain: {vice_captain['web_name']} (score: {vice_captain['captain_score']:.2f})")
    from api.data_fetcher import get_teams
    from analysis.team_analyzer import get_chip_status, suggest_bench_boost

    all_team_ids = get_teams()
    chip_status = get_chip_status(MY_TEAM_ID, planning_gw)

    print("\n--- Bench Boost Suggestion ---")
    bb = suggest_bench_boost(squad, fixtures_df, planning_gw, all_team_ids, chip_status, active_chip)
    print(bb if bb else "(no nudge — not enough doubles, or chip unavailable/active)")

    print("\n--- Triple Captain Suggestion ---")
    tc = suggest_triple_captain(captain, fixtures_df, planning_gw, all_team_ids, chip_status, active_chip)
    print(tc if tc else "(no nudge — captain doesn't double, or chip unavailable/active)")
    from analysis.team_analyzer import suggest_free_hit

    print("\n--- Free Hit Suggestion ---")
    fh = suggest_free_hit(squad, fixtures_df, planning_gw, all_team_ids, chip_status, active_chip)
    print(fh if fh else "(no nudge — not enough blanks, or chip unavailable/active)")



