import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
from analysis.transfer_engine import calculate_player_score, add_scores



def make_fake_player(form = 5.0, cost = 8.0, points = 50, status = "a"):
    return pd.Series({
        "form": form,
        "now_cost": cost,
        "total_points": points,
        "status": status
    })

def test_score_penalize_injured_players():
    healthy = make_fake_player(status="a")
    injured = make_fake_player(status="i")

    healthy_score = calculate_player_score(healthy)
    injured_score = calculate_player_score(injured)

    assert injured_score < healthy_score

def test_score_rewards_better_form():
    low_form = make_fake_player(form=2.0)
    high_form = make_fake_player(form=9.0)

    assert calculate_player_score(high_form) > calculate_player_score(low_form)


