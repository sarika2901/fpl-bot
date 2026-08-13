import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error
import joblib

FEATURES = [
    "total_points_roll3", "minutes_roll3", "ict_index_roll3",
    "now_cost", "was_home", "opponent_fdr",
    "team_strength_attack", "team_strength_defence",
    "position_GK", "position_DEF", "position_MID", "position_FWD",
]
TARGET = "total_points"

def load_dataset():
    return pd.read_csv("data/processed/model_ready.csv")

def split_data(df):
    train_df = df[df["season_split"] == "train"]
    test_df = df[df["season_split"] == "test"]
    X_train, y_train = train_df[FEATURES], train_df[TARGET]
    X_test, y_test = test_df[FEATURES], test_df[TARGET]
    return X_train, y_train, X_test, y_test

def train_baseline(X_train, y_train):
    return LinearRegression().fit(X_train, y_train)

def train_random_forest(X_train, y_train):
    model = RandomForestRegressor(
        n_estimators=300, max_depth=8, min_samples_leaf=5, random_state=42
    )
    model.fit(X_train, y_train)
    return model

def evaluate(model, X_test, y_test, label):
    mae = mean_absolute_error(y_test, model.predict(X_test))
    print(f"{label} MAE: {mae:.3f}")
    return mae

def save_model(model, path="models/points_predictor.pkl"):
    joblib.dump(model, path)
    print(f"saved model to {path}")

def train():
    df = load_dataset()
    X_train, y_train, X_test, y_test = split_data(df)

    candidates = {
        "Linear Regression": train_baseline(X_train, y_train),
        "Random Forest": train_random_forest(X_train, y_train),
    }

    results = {
        name: evaluate(model, X_test, y_test, name)
        for name, model in candidates.items()
    }

    best_name = min(results, key=results.get)
    best_model = candidates[best_name]
    print(f"\nBest model: {best_name} (MAE {results[best_name]:.3f}) — saving this one")

    save_model(best_model)
    return best_model

if __name__ == "__main__":
    train()