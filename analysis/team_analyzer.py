import json
import requests
import pandas as pd
from api.data_fetcher import get_players_dataframe, get_manager_info, get_manager_picks, get_fixtures

def load_mock_squad():
    with open("config/my_squad.json") as f:
        data = json.load(f)
    return data["player_ids"]

def get_squad_player_ids(team_id, gameweek):
    """Returns real picks if the season has started, otherwise the mock squad."""
    info = get_manager_info(team_id)

    if info is None:
        return None  # Team ID is invalid

    if len(info["entered_events"]) == 0:
        # print("⚠️  Season hasn't started for this team yet — using mock squad instead.")
        # return load_mock_squad()
        return None

    try:
        picks_data = get_manager_picks(team_id, gameweek)
        return [p["element"] for p in picks_data["picks"]]
    except requests.exceptions.HTTPError:
        # print("⚠️  Picks data unavailable — using mock squad instead.")
        # return load_mock_squad()
        return None

def build_squad_from_ids(player_ids):
    """Given a list of player IDs, return their full stats as a DataFrame."""
    players_df = get_players_dataframe()
    squad = players_df[players_df["id"].isin(player_ids)]
    return squad[["id", "web_name", "position", "now_cost", "total_points", "form", "status", "news", "team"]]


def get_team_summary(team_id):
    """Returns manager name, points, rank, and whether the season has started."""
    info = get_manager_info(team_id)
    points = info["summary_overall_points"]
    rank = info["summary_overall_rank"]

    return {
        "manager_name": f"{info['player_first_name']} {info['player_last_name']}",
        "team_name": info["name"],
        "overall_points": points if points is not None else "Season hasn't started",
        "overall_rank": rank if rank is not None else "Season hasn't started",
        "season_started": len(info["entered_events"]) > 0
    }

def flag_injuries(squad_df):
    """Prints and returns any squad players who are injured/doubtful/suspended."""
    status_map = {"i": "Injured", "d": "Doubtful", "s": "Suspended", "u": "Unavailable"}
    flagged = squad_df[squad_df["status"] != "a"]

    for _, player in flagged.iterrows():
        status = status_map.get(player["status"], "Unknown")
        print(f"⚠️  {player['web_name']}: {status} — {player['news']}")

    return flagged 


def get_upcoming_difficulty(team_id_in_fpl, fixtures_df, next_n=3):
    """Average fixture difficulty for a real-world team over the next N unplayed fixtures."""
    upcoming = fixtures_df[
        ((fixtures_df["team_h"] == team_id_in_fpl) | (fixtures_df["team_a"] == team_id_in_fpl)
        ) & (fixtures_df["finished"] == False)
    ].head(next_n)

    difficulties = []

    for _, fixture in upcoming.iterrows():
        if fixture["team_h"] == team_id_in_fpl:
            difficulties.append(fixture["team_h_difficulty"])
        else:
            difficulties.append(fixture["team_a_difficulty"])

    return sum(difficulties) / len(difficulties) if difficulties else None

if __name__ == "__main__":
    MY_TEAM_ID = 2093872
    GAMEWEEK = 1

    summary = get_team_summary(MY_TEAM_ID)
    print("\n--- Team Summary ---")
    print(summary)

    player_ids = get_squad_player_ids(MY_TEAM_ID, GAMEWEEK)
    squad = build_squad_from_ids(player_ids)
    print("\n--- Your Squad ---")
    print(squad)

    print("\n--- Injury Check ---")
    flagged = flag_injuries(squad)

    print("\n --- Fixture Difficulty (next 3) ---")
    fixtures_df = get_fixtures()
    for _,player in squad.iterrows():
        difficulty = get_upcoming_difficulty(player["team"], fixtures_df)
        print(f"{player['web_name']} : avg difficulty = {difficulty}")

