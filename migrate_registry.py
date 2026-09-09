"""
One-time migration script: copies existing user_teams.json data into
Postgres via the registry API. Run this ONCE after your Flask API
(api/registry_api.py) is up and running. Safe to re-run if it fails
partway — /register overwrites on conflict, so re-running just
re-sends the same data.
"""

import json
import requests

REGISTRY_API = "http://localhost:5000"
JSON_FILE = "bot/user_teams.json"

def migrate():
    with open(JSON_FILE) as f:
        existing_users = json.load(f)

    print(f"Found {len(existing_users)} users in {JSON_FILE}. Migrating...\n")

    success_count = 0
    fail_count = 0

    for discord_id_str, team_id in existing_users.items():
        try:
            response = requests.post(f"{REGISTRY_API}/register", json={
                "discord_id": int(discord_id_str),
                "team_id": int(team_id)
            })
            if response.status_code == 200:
                print(f"✅ {discord_id_str} -> team {team_id}")
                success_count += 1
            else:
                print(f"❌ {discord_id_str} failed: {response.status_code} {response.text}")
                fail_count += 1
        except requests.exceptions.ConnectionError:
            print("❌ Could not reach the API — is api/registry_api.py running?")
            return

    print(f"\nDone. {success_count} migrated, {fail_count} failed.")

if __name__ == "__main__":
    migrate()