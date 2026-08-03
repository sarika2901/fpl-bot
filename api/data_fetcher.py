import requests
import pandas as pd
import os
from datetime import datetime

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
    response.raise_for_status()
    return response.json()

def get_manager_picks(team_id, gameweek):
    """Returns a dict with manager picks for a given team_id and gameweek"""
    url = f"https://fantasy.premierleague.com/api/entry/{team_id}/event/{gameweek}/picks/"
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

def get_fixtures():
    url = "https://fantasy.premierleague.com/api/fixtures/"
    response = requests.get(url)
    response.raise_for_status()
    return pd.DataFrame(response.json())




if __name__ == "__main__":
    df = get_players_dataframe()
    # print(df[["web_name", "total_points", "position", "now_cost", "form"]].head(10))
    # mf_df = df[df["element_type"] == 3]
    # mf_df["ppm"] = mf_df["total_points"]/ mf_df["now_cost"]
    # mf_df = mf_df.sort_values("ppm", ascending=False)
    # print(mf_df[["web_name", "position", "total_points", "now_cost", "ppm"]].head(10))

    print(df.groupby("position")["total_points"].mean())

