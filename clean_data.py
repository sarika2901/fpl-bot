import pandas as pd

POSITION_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}

def normalize_position_and_price(df, season):
    needs_position = "position" not in df.columns
    needs_price = "now_cost" not in df.columns

    if needs_price and "value" in df.columns:
        df["now_cost"] = df["value"]
        needs_price = False

    if needs_position or needs_price:
        players = pd.read_csv(f"data/raw/{season}/players_raw.csv")
        players = players.rename(columns={"id": "element"})
        players["position"] = players["element_type"].map(POSITION_MAP)
        lookup_cols = ["element"]
        if needs_position:
            lookup_cols.append("position")
        if needs_price:
            lookup_cols.append("now_cost")
        df = df.merge(players[lookup_cols], on="element", how="left")

    return df

def load_and_clean(season):
    df = pd.read_csv(f"data/raw/{season}/merged_gw.csv")
    df = df[df["minutes"] > 0].copy()
    df = df.sort_values(["element", "GW"])
    df = normalize_position_and_price(df, season)

    for col in ["total_points", "minutes", "ict_index"]:
        df[f"{col}_roll3"] = (
            df.groupby("element")[col]
            .transform(lambda s : s.shift(1).rolling(3, min_periods=1).mean())  #why shift(1) is the important bit. It shifts the whole column down by one row — so gameweek 5's row now shows gameweek 4's value, gameweek 4's row shows gameweek 3's value, and so on. Row 1 (their first-ever game) becomes empty/blank, since there's no "previous" game to shift in.
        )

    df["season"] = season
    return df

def build_dataset(seasons):
    frames = [load_and_clean(s) for s in seasons]
    full = pd.concat(frames, ignore_index=True)
    full = full.dropna(subset=["total_points_roll3"])
    full.to_csv("data/processed/training_data.csv", index=False)
    print(f"final dataset: {len(full)} rows")
    print(full[["position", "now_cost"]].isna().sum())
    return full

if __name__ == "__main__":
    SEASONS = ["2023-24", "2024-25", "2025-26"]
    build_dataset(SEASONS)