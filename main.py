from api.data_fetcher import get_players_dataframe, get_fixtures
from analysis.team_analyzer import get_squad_player_ids, build_squad_from_ids, get_team_summary, flag_injuries
from analysis.transfer_engine import suggest_transfers, suggest_captain
from dotenv import load_dotenv
import os

load_dotenv()
MY_TEAM_ID = int(os.getenv("MY_TEAM_ID"))
GAMEWEEK = 1
BANK = 0.5

def run_analysis():
    print("--Team Summary--")
    print(get_team_summary(MY_TEAM_ID))

    player_ids = get_squad_player_ids(MY_TEAM_ID, GAMEWEEK)
    squad = build_squad_from_ids(player_ids)
    print("\n---Squad---")
    print(squad)

    print("\n---Injury Check---")
    flag_injuries(squad)

    all_players = get_players_dataframe()
    print("\n---Transfer Suggestions---")
    print(suggest_transfers(squad, all_players, player_ids, bank=BANK))

    fixtures_df = get_fixtures()
    print("\n---Captain Suggestion---")
    captain = suggest_captain(squad, fixtures_df)
    print(f"Captain: {captain['web_name']}")

if __name__ == "__main__":
    run_analysis()
