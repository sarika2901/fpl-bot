import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
import pandas as pd
from api.data_fetcher import get_players_dataframe, get_manager_info, get_manager_picks, get_fixtures


def load_mock_squad():
    with open("config/my_squad.json") as f:
        data = json.load(f)
    return data["player_ids"]

def get_squad_player_ids(team_id, gameweek):
    """
    Returns (status, player_ids) where status is one of:
      "ok"                - picks retrieved successfully
      "invalid_team_id"   - team_id doesn't exist on FPL
      "season_not_started"- team exists but hasn't entered any gameweek yet
      "picks_unavailable"  - team has entered events, but this gameweek's picks aren't ready
    """
    info = get_manager_info(team_id)

    if info is None:
        return "invalid_team_id", None, None  # Team ID is invalid

    if len(info["entered_events"]) == 0:
        # print("⚠️  Season hasn't started for this team yet — using mock squad instead.")
        # return load_mock_squad()
        return "season_not_started", None, None

    try:
        picks_data = get_manager_picks(team_id, gameweek)
        player_ids = [p["element"] for p in picks_data["picks"]]
        bank = picks_data["entry_history"]["bank"]/10
        return "ok", player_ids, bank
    except requests.exceptions.HTTPError:
        return "picks_unavailable", None, None

def build_squad_from_ids(player_ids):
    """Given a list of player IDs, return their full stats as a DataFrame."""
    players_df = get_players_dataframe()
    squad = players_df[players_df["id"].isin(player_ids)]
    return squad[["id", "web_name", "position", "now_cost", "total_points", "form", "status", "news", "chance_of_playing_next_round", "team"]]

def suggest_starting_xi(squad_df, fixtures_df, next_n=1):
    """
    Splits a 15-man squad into a formation-legal Starting XI and Bench.
    Ranks players by effective_score = form, discounted by chance_of_playing_next_round
    (fully fit players, where that field is blank, get no discount), and adjusted for
    upcoming fixture ease (easier fixture = higher score).
    Tries every valid FPL formation (DEF 3-5, MID 2-5, FWD 1-3, GK always 1)
    and picks whichever maximizes total effective_score.
    """
    squad_df = squad_df.copy()
    squad_df["chance_of_playing_next_round"] = squad_df["chance_of_playing_next_round"].fillna(100)

    squad_df["fixture_difficulty"] = squad_df["team"].apply(
        lambda team_id: get_upcoming_difficulty(team_id, fixtures_df, next_n=next_n) or 3
    )
    squad_df["fixture_ease"] = 6 - squad_df["fixture_difficulty"]  # 1 (hard) -> 5, 5 (hard) -> 1

    squad_df["effective_score"] = (
        squad_df["form"]
        * (squad_df["chance_of_playing_next_round"] / 100)
        * (squad_df["fixture_ease"] / 3)  # 3 = "average" difficulty, so this is neutral (x1) by default
    )

    gks = squad_df[squad_df["position"] == "GK"].sort_values("effective_score", ascending=False)
    defs = squad_df[squad_df["position"] == "DEF"].sort_values("effective_score", ascending=False)
    mids = squad_df[squad_df["position"] == "MID"].sort_values("effective_score", ascending=False)
    fwds = squad_df[squad_df["position"] == "FWD"].sort_values("effective_score", ascending=False)

    best = None
    for d in range(3, 6):
        for m in range(2, 6):
            f = 10 - d - m
            if f < 1 or f > 3:
                continue
            if len(defs) < d or len(mids) < m or len(fwds) < f:
                continue
            total = (
                gks["effective_score"].iloc[0]
                + defs["effective_score"].head(d).sum()
                + mids["effective_score"].head(m).sum()
                + fwds["effective_score"].head(f).sum()
            )
            if best is None or total > best[0]:
                best = (total, d, m, f)

    _, d, m, f = best

    starting_ids = (
        set(gks["id"].head(1))
        | set(defs["id"].head(d))
        | set(mids["id"].head(m))
        | set(fwds["id"].head(f))
    )

    squad_df["role"] = squad_df["id"].apply(lambda i: "Starting XI" if i in starting_ids else "Bench")
    return squad_df.sort_values(["role", "position", "effective_score"], ascending=[True, True, False])


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

    status, player_ids, bank = get_squad_player_ids(MY_TEAM_ID, GAMEWEEK)
    if status != "ok":
        print(f"Squad unavailable: {status}")
    else:
        squad = build_squad_from_ids(player_ids)
        print("\n--- Your Squad ---")
        print(squad)
        print(f"Bank: £{bank}m")

        print("\n--- Injury Check ---")
        flag_injuries(squad)

        print("\n--- Chance of Playing Next Round ---")
        print(squad[["web_name", "status", "chance_of_playing_next_round"]])

        print("\n --- Fixture Difficulty (next 3) ---")
        fixtures_df = get_fixtures()
        for _, player in squad.iterrows():
            difficulty = get_upcoming_difficulty(player["team"], fixtures_df)
            print(f"{player['web_name']} : avg difficulty = {difficulty}")

