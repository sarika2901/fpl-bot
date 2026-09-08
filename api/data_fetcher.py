import requests
import pandas as pd
import os
from datetime import datetime, timezone

BASE_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"

def fetch_raw_data():
    """Calls the FPL API and returns the raw JSON response"""
    response = requests.get(BASE_URL)
    response.raise_for_status()
    return response.json()

CACHE_FILE = "players_cache.csv"

def get_players_dataframe(force_refresh=False):
    """Returns all players as a clean pandas df"""
    if not force_refresh and os.path.exists(CACHE_FILE):
        print("Loading players from cache...")
        return pd.read_csv(CACHE_FILE)
    
    print("Fetching players from FPL API...")
    data = fetch_raw_data()
    df = pd.DataFrame(data["elements"])

    df["form"] = df["form"].astype(float)
    df["now_cost"] = df["now_cost"] / 10

    position_map = {1:"GK", 2:"DEF", 3:"MID", 4:"FWD"}
    df["position"] = df["element_type"].map(position_map)

    df.to_csv(CACHE_FILE, index=False)
    return df

def get_manager_info(team_id):
    """Returns a dict with manager info for a given team_id"""
    url = f"https://fantasy.premierleague.com/api/entry/{team_id}/"
    response = requests.get(url)
    if response.status_code == 404:
        return None
    response.raise_for_status()
    return response.json()

def get_manager_picks(team_id, gameweek):
    """Returns a dict with manager picks for a given team_id and gameweek"""
    url = f"https://fantasy.premierleague.com/api/entry/{team_id}/event/{gameweek}/picks/"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def get_manager_history(team_id):
     """Full-season history for a manager: per-GW transfers/points/bank/value,
    plus which chips were played and when. Needed to reconstruct free transfers."""
     url = f"https://fantasy.premierleague.com/api/entry/{team_id}/history/"
     response = requests.get(url)
     if response.status_code == 404:
         return None
     response.raise_for_status()
     return response.json()
   

def get_fixtures():
    url = "https://fantasy.premierleague.com/api/fixtures/"
    response = requests.get(url)
    response.raise_for_status()
    return pd.DataFrame(response.json())

def get_events():
    """Raw list of gameweek/event dicts from bootstrap-static (deadlines, flags)."""
    return fetch_raw_data()["events"]


def get_current_gameweek():
    """Returns the id of the currently active gameweek, or the next upcoming one."""
    data = fetch_raw_data()
    events = data["events"]

    current = [e for e in events if e["is_current"]]
    if current:
        return current[0]["id"]

    upcoming = [e for e in events if e["is_next"]]
    if upcoming:
        return upcoming[0]["id"]

    return 1

def get_planning_gameweek():
     """The gameweek transfer/captain SUGGESTIONS should target — the next
    gameweek whose deadline hasn't passed yet. This is almost always
    different from get_current_gameweek() once a GW kicks off, since you
    can't act on a locked gameweek anymore."""
     events = get_events()
     upcoming = [e for e in events if e["is_next"]]
     if upcoming:
         return upcoming[0]["id"]
     current = [e for e in events if e["is_current"]]
     return current[0]["id"] if current else 1

def get_gameweek_deadline(gameweek):
    events = get_events()
    match = next((e for e in events if e["id"] == gameweek), None)
    if not match:
        return None
    return datetime.strptime(match["deadline_time"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

def is_deadline_passed(gameweek):
    deadline = get_gameweek_deadline(gameweek)
    if deadline is None:
        return None
    return datetime.now(timezone.utc) > deadline



if __name__ == "__main__":
    df = get_players_dataframe()
    print(df[["web_name", "total_points", "position", "now_cost", "form"]].head(10))
    mf_df = df[df["element_type"] == 3]
    mf_df["ppm"] = mf_df["total_points"]/ mf_df["now_cost"]
    mf_df = mf_df.sort_values("ppm", ascending=False)
    print(mf_df[["web_name", "position", "total_points", "now_cost", "ppm"]].head(10))
    print(get_manager_info(2093872))
    print(get_manager_history(2093872))
    print(get_planning_gameweek())
    print(df.groupby("position")["total_points"].mean())
    print(get_gameweek_deadline(1))
    print(is_deadline_passed(1))
