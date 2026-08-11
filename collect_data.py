import requests
import os

SEASONS = ["2023-24", "2024-25", "2025-26"]
BASE_URL = "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/refs/heads/master/data"

def download_season(season):
    os.makedirs(f"data/raw/{season}", exist_ok=True)
    files = {
        "merged_gw.csv": f"{BASE_URL}/{season}/gws/merged_gw.csv",
        "teams.csv": f"{BASE_URL}/{season}/teams.csv",
        "fixtures.csv": f"{BASE_URL}/{season}/fixtures.csv",
    }

    for fname, url in files.items():
        r = requests.get(url)
        r.raise_for_status()
        with open(f"data/raw/{season}/{fname}", "wb") as f:
            f.write(r.content)
        print(f"saved {season}/{fname}")

if __name__ == "__main__":
    for season in SEASONS:
        download_season(season)

