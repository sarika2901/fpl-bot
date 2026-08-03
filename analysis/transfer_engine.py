import pandas as pd

def calculate_player_score(player):
    """Combines form, points-per-cost, and availability into one score."""
    form_score = player["form"]
    value_score = player["total_points"] / player["now_cost"] if player["now_cost"] > 0 else 0
    availability_penalty = 0 if player["status"] == "a" else -5

    score = (0.5 * form_score) + (0.3 * value_score) + availability_penalty
    return round(score,2)

def add_scores(players_df):
    """Adds a 'score' column to the players DataFrame."""
    players_df = players_df.copy()
    players_df["score"] = players_df.apply(calculate_player_score, axis=1)
    return players_df

def find_weak_links(squad_df, n=3):
    """Returns the n lowest-scoring players in your squad — transfer-out candidates."""
    return squad_df.sort_values("score").head(n)

def find_best_replacement(player_to_replace, all_players_df, squad_ids, budget):
    """
    Finds the highest-scoring player NOT already in your squad, in the same position, within budget.
    """
    position = player_to_replace["position"]
    max_price = player_to_replace["now_cost"] + budget

    candidates = all_players_df[
        (all_players_df["position"] == position) &
        (~all_players_df["id"].isin(squad_ids)) &
        (all_players_df["now_cost"] <= max_price) &
        (all_players_df["status"] == "a")
    ]

    if candidates.empty:
        return None

    best = candidates.sort_values("score", ascending=False).iloc[0]
    return best

def suggest_transfers(squad_df, all_players_df, squad_ids, bank=0.0, n=3):
    """Suggests n transfers: who to sell and who to buy instead."""
    scored_squad = add_scores(squad_df)
    scored_all = add_scores(all_players_df)

    weaklinks = find_weak_links(scored_squad, n=n)

    suggestions = []
    for _, player in weaklinks.iterrows():
        replacement = find_best_replacement(player, scored_all, squad_ids, budget=bank)
        suggestions.append({
            "sell" : player["web_name"],
            "sell_score" : player["score"],
            "buy": replacement["web_name"] if replacement is not None else "No suitable replacement found",
            "buy_score": replacement["score"] if replacement is not None else None,
        })

    return pd.DataFrame(suggestions)

def suggest_captain(squad_df, fixtures_df):
    """Suggests the best captain pick — highest score, adjusted for fixture ease."""
    scored_squad = add_scores(squad_df).copy()

    from analysis.team_analyzer import get_upcoming_difficulty
    scored_squad["fixture_ease"] = scored_squad["team"].apply(
        lambda team_id: 6 - (get_upcoming_difficulty(team_id, fixtures_df, next_n=1 ) or 3)
    )

    scored_squad["captain_score"] = scored_squad["score"] + (0.5 * scored_squad["fixture_ease"]) 
    return scored_squad.sort_values("captain_score", ascending=False).iloc[0]

if __name__ == "__main__":
    from api.data_fetcher import get_players_dataframe, get_fixtures
    from analysis.team_analyzer import get_squad_player_ids, build_squad_from_ids

    MY_TEAM_ID = 2093872
    GAMEWEEK = 1
    BANK = 0.5 

    player_ids = get_squad_player_ids(MY_TEAM_ID, GAMEWEEK)
    squad = build_squad_from_ids(player_ids)
    all_players = get_players_dataframe()

    print("\n--- Transfer Suggestions ---")
    transfers = suggest_transfers(squad, all_players, player_ids, bank=BANK, n=3)
    print(transfers)

    print("\n--- Captain Suggestion ---")
    fixtures_df = get_fixtures()
    captain = suggest_captain(squad, fixtures_df)
    print(f"Captain pick: {captain['web_name']} (score: {captain['captain_score']:.2f})")
    




