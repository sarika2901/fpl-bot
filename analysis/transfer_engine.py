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
                       free_transfers=None, active_chip=None, n=3, hit_threshold=4.0):
    """
    Suggests up to n transfers, respecting FPL's transfer economy:
      - If Wildcard/Free Hit is active this GW, every transfer is free — labeled accordingly.
      - Otherwise, the first `free_transfers` suggestions are free; anything
        beyond that costs -4 and is only kept if the projected score gain
        clears `hit_threshold` (default 4.0, since the model's MAE (~2 pts)
        puts its output roughly on the same scale as actual points).
      - If free_transfers is None (couldn't be determined), every suggestion
        is labeled "cost unknown" rather than silently assuming it's free.
    """
    live_features = build_live_features(gameweek, HISTORICAL_ROLLING_AVERAGES)
    scored_squad = add_scores(squad_df, live_features)
    scored_all = add_scores(all_players_df, live_features)

    weaklinks = find_weak_links(scored_squad, n=n)
    chip_makes_transfers_free = active_chip in ("wildcard", "freehit")

    remaining_budget = bank
    already_suggested_ids = []
    suggestions = []

    for i, (_, player) in enumerate(weaklinks.iterrows()):
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

        if chip_makes_transfers_free:
            cost_label = "Free (chip active)"
        elif free_transfers is None:
            cost_label = "Cost unknown"
        elif i < free_transfers:
            cost_label = "Free"
        elif net_gain > hit_threshold:
            cost_label = "-4 (hit) — worth it"
        else:
            continue  # not worth a -4 hit, drop this suggestion entirely

        cost_change = replacement["now_cost"] - player["now_cost"]
        remaining_budget -= cost_change
        already_suggested_ids.append(replacement["id"])

        suggestions.append({
            "sell": player["web_name"], "sell_price": player["now_cost"],
            "sell_score": player["score"], "reason": reason,
            "buy": replacement["web_name"], "buy_price": replacement["now_cost"],
            "buy_score": replacement["score"], "cost": cost_label,
            "remaining_budget": round(remaining_budget, 1),
        })

    return pd.DataFrame(suggestions)

def suggest_captain(squad_df, fixtures_df, gameweek):
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
    return eligible.sort_values("captain_score", ascending=False).iloc[0]

if __name__ == "__main__":
    from api.data_fetcher import get_players_dataframe, get_fixtures
    from analysis.team_analyzer import get_squad_player_ids, build_squad_from_ids

    MY_TEAM_ID = 2093872
    GAMEWEEK = 1
    BANK = 0.5 

    status, player_ids, bank, active_chip = get_squad_player_ids(MY_TEAM_ID, GAMEWEEK)
    if status != "ok":
        print(f"⚠️  Squad unavailable ({status}) — using mock squad from config/my_squad.json")
        player_ids = load_mock_squad()
        bank = BANK  # mock squad has no live bank value, fall back to manual constant

    squad = build_squad_from_ids(player_ids)
    all_players = get_players_dataframe()

    print("\n--- Transfer Suggestions ---")
    transfers = suggest_transfers(squad, all_players, player_ids, GAMEWEEK, bank=bank, n=3)
    print(transfers)

    print("\n--- Captain Suggestion ---")
    fixtures_df = get_fixtures()
    captain = suggest_captain(squad, fixtures_df, GAMEWEEK)
    print(f"Captain pick: {captain['web_name']} (score: {captain['captain_score']:.2f})")
    




