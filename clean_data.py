import pandas as pd

def load_and_clean(season):
    df = pd.read_csv(f"data/raw/{season}/merged_gw.csv")
    df = df[df["minutes"] > 0].copy()
    df = df.sort_values(["element", "GW"])

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
    return full

if __name__ == "__main__":
    SEASONS = ["2023-24", "2024-25", "2025-26"]
    build_dataset(SEASONS)