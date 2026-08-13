import pandas as pd

FEATURES = [
    "total_points_roll3", "minutes_roll3", "ict_index_roll3",
    "now_cost", "was_home", "opponent_fdr",
    "team_strength_attack", "team_strength_defence",
    "position_GK", "position_DEF", "position_MID", "position_FWD",
]

# df = pd.read_csv("data/processed/training_data.csv")

def add_team_strength(df, season):
    teams = pd.read_csv(f"data/raw/{season}/teams.csv")
    teams = teams.rename(columns={"id": "team_id"})

    # Different seasons in this dataset format `team` differently: some
    # store the team NAME ("Arsenal"), others store the numeric team id.
    # After Stage 2 concatenates seasons and saves/reloads as CSV, the
    # column's reported .dtype is no longer reliable — so check the actual
    # values for THIS season's slice instead of trusting dtype.

    looks_numeric = pd.to_numeric(df["team"], errors="coerce").notna().all()

    if looks_numeric:
        team_lookup_col = "team_id"
        df["team"] = pd.to_numeric(df["team"]).astype(int)
        teams[team_lookup_col] = teams[team_lookup_col].astype(int)
    else:
        team_lookup_col = "name"
        df["team"] = df["team"].astype(str)
        teams[team_lookup_col] = teams[team_lookup_col].astype(str)

    # player's own team strength (attack/defence)
    df = df.merge(
        teams[[team_lookup_col, "strength_attack_home", "strength_defence_home"]],
        left_on="team", right_on=team_lookup_col, how="left"
    ).rename(columns={
        "strength_attack_home": "team_strength_attack",
        "strength_defence_home": "team_strength_defence"
    })

    # opponent's strength (harder opponent = fewer expected points)
    df["opponent_team"] = pd.to_numeric(df["opponent_team"]).astype(int)
    teams["team_id"] = teams["team_id"].astype(int)
    df = df.merge(
        teams[["team_id", "strength_overall_home", "strength_overall_away"]],
        left_on="opponent_team", right_on="team_id", how="left",
        suffixes=("", "_opp")
    )
    df["opponent_fdr"] = df.apply(
        lambda r: r["strength_overall_away"] if r["was_home"] else r["strength_overall_home"], 
        axis=1
    )
    return df.drop(columns=["team_id", "team_id_opp", "name", "name_opp"], errors="ignore")

def encode_position(df):
    return pd.get_dummies(df, columns=["position"], prefix="position")

def assign_train_test_split(df, test_season="2025-26", test_after_gw=19):
    df["season_split"] = df.apply(
        lambda r: "test" if (r["season"] == test_season and r["GW"] > test_after_gw) else "train",
        axis=1
    )
    return df

def build_features(seasons):
    df = pd.read_csv("data/processed/training_data.csv")

    processed = []

    for season in seasons:
        season_df = df[df["season"] == season].copy()
        season_df = add_team_strength(season_df, season)
        processed.append(season_df)

    df = pd.concat(processed, ignore_index=True)

    df = encode_position(df)
    df = assign_train_test_split(df)

    # safety net: if a position category or feature never appeared in the
    # data, add it as all-zero rather than crashing on the column selection
    for col in FEATURES:
        if col not in df.columns:
            df[col] = 0

    keep_cols = FEATURES + ["total_points", "element", "GW", "season", "season_split"]
    df = df[keep_cols]

    df.to_csv("data/processed/model_ready.csv", index=False)
    print(f"model_ready.csv: {len(df)} rows, {len(FEATURES)} features")
    print(df["season_split"].value_counts())
    return df

if __name__ == "__main__":
    SEASONS = ["2023-24", "2024-25", "2025-26"]
    build_features(SEASONS)

    
