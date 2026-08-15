import joblib
import pandas as pd
import requests

FEATURES = [
    "total_points_roll3", "minutes_roll3", "ict_index_roll3",
    "now_cost", "was_home", "opponent_fdr",
    "team_strength_attack", "team_strength_defence",
    "position_GK", "position_DEF", "position_MID", "position_FWD",
]
POSITION_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

# loaded once at import time, not on every call
try:
    _MODEL = joblib.load("models/points_predictor.pkl")
except FileNotFoundError:
    raise RuntimeError(
        "models/points_predictor.pkl not found — run train_model.py first."
    )


def predict_score(player_features_df):
    """player_features_df must already contain the FEATURES columns."""
    return _MODEL.predict(player_features_df[FEATURES])


def _get_bootstrap_data():
    response = requests.get(
        "https://fantasy.premierleague.com/api/bootstrap-static/", timeout=10
    )
    response.raise_for_status()
    return response.json()


def _get_live_fixtures():
    response = requests.get(
        "https://fantasy.premierleague.com/api/fixtures/", timeout=10
    )
    response.raise_for_status()
    return response.json()


def build_live_features(gameweek, historical_rolling_averages):
    """
    Builds the 12 FEATURES columns for every current player, for the given
    gameweek. Returns one row per player who has a fixture that gameweek
    (players with a blank gameweek are skipped), keyed by `id`.

    historical_rolling_averages: the Stage 2 output (data/processed/
    training_data.csv) — used as the pre-season fallback for
    total_points_roll3/minutes_roll3/ict_index_roll3 until this season has
    3+ gameweeks played. Matched on `element` (last season's player id),
    which lines up with this season's `id` from bootstrap-static.
    """
    data = _get_bootstrap_data()
    players = pd.DataFrame(data["elements"])
    teams = pd.DataFrame(data["teams"])
    fixtures = pd.DataFrame(_get_live_fixtures())

    players["position"] = players["element_type"].map(POSITION_MAP)

    gw_fixtures = fixtures[fixtures["event"] == gameweek]

    rows = []
    for _, player in players.iterrows():
        fixture = gw_fixtures[
            (gw_fixtures["team_h"] == player["team"]) |
            (gw_fixtures["team_a"] == player["team"])
        ]
        if fixture.empty:
            continue  # blank gameweek for this player's team
        fixture = fixture.iloc[0]

        was_home = fixture["team_h"] == player["team"]
        opponent_id = fixture["team_a"] if was_home else fixture["team_h"]
        opponent = teams[teams["id"] == opponent_id].iloc[0]
        own_team = teams[teams["id"] == player["team"]].iloc[0]
        opponent_fdr = opponent["strength_overall_away"] if was_home else opponent["strength_overall_home"]

        hist = historical_rolling_averages[historical_rolling_averages["element"] == player["id"]]
        if not hist.empty:
            total_points_roll3 = hist["total_points_roll3"].iloc[-1]
            minutes_roll3 = hist["minutes_roll3"].iloc[-1]
            ict_index_roll3 = hist["ict_index_roll3"].iloc[-1]
        else:
            # new signing / promoted-team player with no last-season history:
            # fall back to the league-wide average for their position
            pos_avg = historical_rolling_averages[historical_rolling_averages["position"] == player["position"]]
            total_points_roll3 = pos_avg["total_points_roll3"].mean()
            minutes_roll3 = pos_avg["minutes_roll3"].mean()
            ict_index_roll3 = pos_avg["ict_index_roll3"].mean()

        rows.append({
            "id": player["id"],
            "now_cost": player["now_cost"],
            "was_home": was_home,
            "opponent_fdr": opponent_fdr,
            "team_strength_attack": own_team["strength_attack_home"],
            "team_strength_defence": own_team["strength_defence_home"],
            "position": player["position"],
            "total_points_roll3": total_points_roll3,
            "minutes_roll3": minutes_roll3,
            "ict_index_roll3": ict_index_roll3,
        })

    live_df = pd.DataFrame(rows)
    live_df = pd.get_dummies(live_df, columns=["position"], prefix="position")
    for col in ["position_GK", "position_DEF", "position_MID", "position_FWD"]:
        if col not in live_df.columns:
            live_df[col] = 0
    return live_df