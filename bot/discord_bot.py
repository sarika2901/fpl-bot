import os
import sys
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

@client.event
async def on_ready():
    await tree.sync()
    print(f'Logged in as {client.user}!')

from analysis.team_analyzer import get_team_summary, get_squad_player_ids, build_squad_from_ids

MY_TEAM_ID = int(os.getenv("MY_TEAM_ID"))
GAMEWEEK = 1

@tree.command(name="team", description="Show your FPL squad summary")
async def team_command(interaction: discord.Interaction):
    summary = get_team_summary(MY_TEAM_ID)
    player_ids = get_squad_player_ids(MY_TEAM_ID, GAMEWEEK)
    squad = build_squad_from_ids(player_ids)

    lines = [f"**{summary['team_name']}** - {summary['overall_points']} pts"]
    for _, player in squad.iterrows():
        lines.append(f"{player['web_name']} ({player['position']}) - {player['total_points']} pts")
    await interaction.response.send_message("\n".join(lines))

from analysis.transfer_engine import suggest_transfers, suggest_captain
from api.data_fetcher import get_players_dataframe, get_fixtures

@tree.command(name="transfers", description="Get transfer suggestions")
async def transfers_command(interaction: discord.Interaction):
    await interaction.response.defer()  
    player_ids = get_squad_player_ids(MY_TEAM_ID, GAMEWEEK)
    squad = build_squad_from_ids(player_ids)
    all_players = get_players_dataframe()
    suggestions = suggest_transfers(squad, all_players, player_ids, bank=0.5)

    lines = ["**Transfer Suggestions:**"]
    for _,row in suggestions.iterrows():
        lines.append(f"OUT: {row['sell']} -> IN: {row['buy']}")

    await interaction.followup.send("\n".join(lines))

@tree.command(name="captain", description="Get captain suggestion")
async def captain_command(interaction: discord.Interaction):
    await interaction.response.defer()
    player_ids = get_squad_player_ids(MY_TEAM_ID, GAMEWEEK)
    squad = build_squad_from_ids(player_ids)
    fixtures_df = get_fixtures()
    captain = suggest_captain(squad, fixtures_df)

    await interaction.followup.send(f"Captain pick: **{captain['web_name']}**")
    

client.run(TOKEN)