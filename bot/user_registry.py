import json
import os

REGISTRY_FILE = "bot/user_teams.json"

def load_registry():
    if not os.path.exists(REGISTRY_FILE):
        return {}
    with open(REGISTRY_FILE) as f:
        return json.load(f)

def save_registry(registry):
    with open(REGISTRY_FILE, "w") as f:
        json.dump(registry,f)

def register_user(discord_user_id, team_id):
    registry = load_registry()
    registry[str(discord_user_id)] = team_id
    save_registry(registry)

def get_registered_team(discord_user_id):
    registry = load_registry()
    return registry.get(str(discord_user_id))


