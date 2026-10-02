import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import requests
import pandas as pd
from api.data_fetcher import (
    get_current_gameweek, get_players_dataframe, get_manager_info, get_manager_picks,
    get_fixtures, get_manager_history, get_teams, get_planning_gameweek
)


def load_mock_squad():
    with open("config/my_squad.json") as f:
        data = json.load(f)
    return data["player_ids"]

def get_free_transfers(team_id, gameweek):
    """
    Estimates free transfers available ENTERING `gameweek`, simulating FPL's
    banking rule (starts at 1 for GW2, max stack of 2, chips don't consume
    or reset the count). Returns None if it can't be computed (gameweek <= 1,
    or manager has no history yet).
    """
    if gameweek <= 1:
        return None

    history = get_manager_history(team_id)
    if history is None:
        return None

    by_event = {row["event"]: row for row in history["current"]}
    chip_events = {
        chip["event"] for chip in history.get("chips", [])
        if chip["name"] in ("wildcard", "freehit")
    }

    free_transfers = 1
    for gw in range(2, gameweek):
        row = by_event.get(gw)
        if row is None:
            break
        if gw not in chip_events:
            free_transfers = max(free_transfers - row.get("event_transfers", 0), 0)
        free_transfers = min(free_transfers + 1, 2)

    return free_transfers

GW19_DEADLINE = 19

def get_chip_status(team_id, current_gw):
    """
    Returns a dict {"wildcard": "available"/"used"/"unknown", "freehit": ...,
    "bboost": ..., "3xc": ...} for the CURRENT half of the season.
    FPL gives two full sets of chips (2025/26+): one usable GW1/2 through the
    GW19 deadline, a fresh set from GW20 onward. Unused first-half chips
    expire — they do not carry into the second half, so this only ever
    reports status for whichever half `current_gw` falls into.
    """
    chip_types = ["wildcard", "freehit", "bboost", "3xc"]
    history = get_manager_history(team_id)
    if history is None:
        return {c: "unknown" for c in chip_types}

    half_start, half_end = (1, GW19_DEADLINE) if current_gw <= GW19_DEADLINE else (GW19_DEADLINE + 1, 38)

    played_this_half = {
        chip["name"] for chip in history.get("chips", [])
        if half_start <= chip["event"] <= half_end
    }
    return {c: ("used" if c in played_this_half else "available") for c in chip_types}

def get_squad_player_ids(team_id, gameweek):
    """
    Returns (status, player_ids, bank, active_chip).
    status: "ok" | "invalid_team_id" | "season_not_started" | "picks_unavailable"
    active_chip: None, "wildcard", "freehit", "bboost", or "3xc" (only set when status == "ok")
    """
    info = get_manager_info(team_id)

    if info is None:
        return "invalid_team_id", None, None, None  # Team ID is invalid

    if len(info["entered_events"]) == 0:
        # print("⚠️  Season hasn't started for this team yet — using mock squad instead.")
        # return load_mock_squad()
        return "season_not_started", None, None, None

    try:
        picks_data = get_manager_picks(team_id, gameweek)
        player_ids = [p["element"] for p in picks_data["picks"]]
        bank = picks_data["entry_history"]["bank"]/10
        active_chip = picks_data.get("active_chip")
        return "ok", player_ids, bank, active_chip
    except requests.exceptions.HTTPError:
        return "picks_unavailable", None, None, None

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

def get_fixtures_counts(fixtures_df, gameweek, all_team_ids):
    """
    Returns {team_id: fixture_count} for every PL team in the given gameweek.
    0 = blank gameweek (team not playing), 1 = normal, 2+ = double gameweek.
    `all_team_ids` should come from api.data_fetcher.get_teams() — this is
    what lets us register a 0 for teams that simply don't appear in
    fixtures_df at all for this GW.
    """
    counts = {team_id: 0 for team_id in all_team_ids}

    gw_fixtures = fixtures_df[fixtures_df["event"] == gameweek]
    for _, fixture in gw_fixtures.iterrows():
        counts[fixture["team_h"]] = counts.get(fixture["team_h"], 0) + 1
        counts[fixture["team_a"]] = counts.get(fixture["team_a"], 0) + 1

    return counts

def classify_squad_fixture_impact(squad_df, fixture_counts):
    """
    Given a squad and a {team_id: fixture_count} dict (from get_fixture_counts),
    returns how many squad players are blank (0 fixtures) or double (2+) this GW,
    plus their names. This is your squad 15 specifically, not the whole league.
    """
    squad_df = squad_df.copy()
    squad_df["fixture_count"] = squad_df["team"].map(fixture_counts).fillna(0).astype(int)

    blanks = squad_df[squad_df["fixture_count"] == 0]
    doubles = squad_df[squad_df["fixture_count"] >= 2]

    return {
        "blank_count": len(blanks),
        "blank_players": blanks["web_name"].tolist(),
        "double_count": len(doubles),
        "double_players": doubles["web_name"].tolist(),
    }




if __name__ == "__main__":
    MY_TEAM_ID = 2093872
    GAMEWEEK = get_current_gameweek()  # or set to a specific GW number
    PLANNING_GW = get_planning_gameweek()  # the GW for which you want to plan transfers


    summary = get_team_summary(MY_TEAM_ID)
    print("\n--- Team Summary ---")
    print(summary)

    status, player_ids, bank, active_chip = get_squad_player_ids(MY_TEAM_ID, GAMEWEEK)
    if status != "ok":
        print(f"Squad unavailable: {status}")
    else:
        squad = build_squad_from_ids(player_ids)
        print("\n--- Your Squad ---")
        print(squad)
        print(f"Bank: £{bank}m")
        print(f"Active Chip: {active_chip}")

        print("\n--- Injury Check ---")
        flag_injuries(squad)

        print("\n--- Chance of Playing Next Round ---")
        print(squad[["web_name", "status", "chance_of_playing_next_round"]])

        print("\n --- Fixture Difficulty (next 3) ---")
        fixtures_df = get_fixtures()
        for _, player in squad.iterrows():
            difficulty = get_upcoming_difficulty(player["team"], fixtures_df)
            print(f"{player['web_name']} : avg difficulty = {difficulty}")
        
        print("\n--- Fixture Counts (Blank/Double GW check) ---")
        all_team_ids = get_teams()
        fixture_counts = get_fixtures_counts(fixtures_df, PLANNING_GW, all_team_ids)
        print(f"Fixture counts for GW{PLANNING_GW}:")
        print(fixture_counts)

        impact = classify_squad_fixture_impact(squad, fixture_counts)
        print(f"\nBlank players: {impact['blank_players']}")
        print(f"Double players: {impact['double_players']}")

