import joblib
import pandas as pd
import shap

FEATURES = [
    "total_points_roll3", "minutes_roll3", "ict_index_roll3",
    "now_cost", "was_home", "opponent_fdr",
    "team_strength_attack", "team_strength_defence",
    "position_GK", "position_DEF", "position_MID", "position_FWD",
]

def load_model(path="models/points_predictor.pkl"):
    return joblib.load(path)

def global_importance(model, feature_names=FEATURES):
    if hasattr(model, "coef_"):
        importances = pd.Series(model.coef_, index=feature_names)
    else:
        importances = pd.Series(model.feature_importances_, index=feature_names)
    return importances.sort_values(ascending=False)

def explain_prediction(model, X_row, X_train_sample, feature_names=FEATURES):
    if hasattr(model, "coef_"):
        explainer = shap.LinearExplainer(model, X_train_sample)
    else:
        explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_row)
    return pd.Series(shap_values[0], index=feature_names).sort_values(ascending=False)

if __name__ == "__main__":
    model = load_model()

    print("Global feature importance:")
    print(global_importance(model))

    df = pd.read_csv("data/processed/model_ready.csv")
    train_sample = df[df["season_split"] == "train"][FEATURES].sample(100, random_state=42)
    sample_row = df[df["season_split"] == "test"][FEATURES].iloc[[0]]

    print("\nWhy this one prediction:")
    print(explain_prediction(model, sample_row, train_sample))

    