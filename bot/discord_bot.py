import os
import sys
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.data_fetcher import get_current_gameweek
from bot.user_registry import get_registered_team, register_user
from typing import Optional


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

# MY_TEAM_ID = int(os.getenv("MY_TEAM_ID"))
GAMEWEEK = get_current_gameweek()

@tree.command(name="team", description="Show your FPL squad summary")
@app_commands.describe(team_id="Your FPL team ID (find it in your FPL team URL)")
async def team_command(interaction: discord.Interaction, team_id: Optional[int] = None):
    await interaction.response.defer()

    if team_id is None:
        team_id = get_registered_team(interaction.user.id)

    if team_id is None:
        await interaction.followup.send("⚠️ No team ID provided or registered. Use `/register team_id:<your id>` first, or pass one directly.")
        return

    gameweek = get_current_gameweek()
    player_ids = get_squad_player_ids(team_id, gameweek)

    if player_ids is None:
        await interaction.followup.send(
            "⚠️ Your squad isn't available yet — this usually means the season hasn't "
            "started, or your team ID is incorrect."
        )
        return
    
    summary = get_team_summary(team_id)
    
    squad = build_squad_from_ids(player_ids)

    lines = [f"**{summary['team_name']}** - {summary['overall_points']} pts"]
    for _, player in squad.iterrows():
        lines.append(f"{player['web_name']} ({player['position']}) - {player['total_points']} pts")
    await interaction.response.send_message("\n".join(lines))

from analysis.transfer_engine import suggest_transfers, suggest_captain
from api.data_fetcher import get_players_dataframe, get_fixtures

@tree.command(name="transfers", description="Get transfer suggestions")
async def transfers_command(interaction: discord.Interaction, team_id: Optional[int] = None):
    await interaction.response.defer()
    if team_id is None:
        team_id = get_registered_team(interaction.user.id)

    if team_id is None:
        await interaction.followup.send("⚠️ No team ID provided or registered. Use `/register team_id:<your id>` first, or pass one directly.")
        return

    gameweek = get_current_gameweek()
    player_ids = get_squad_player_ids(team_id, gameweek)

    if player_ids is None:
            await interaction.followup.send(
                "⚠️ Your squad isn't available yet — this usually means the season hasn't "
                "started, or your team ID is incorrect."
            )
            return

    squad = build_squad_from_ids(player_ids)
    all_players = get_players_dataframe()
    suggestions = suggest_transfers(squad, all_players, player_ids, bank=0.5)

    lines = ["**Transfer Suggestions:**"]
    for _,row in suggestions.iterrows():
        lines.append(f"OUT: {row['sell']} -> IN: {row['buy']}")

    await interaction.followup.send("\n".join(lines))

@tree.command(name="captain", description="Get captain suggestion")
async def captain_command(interaction: discord.Interaction, team_id: Optional[int] = None):
    await interaction.response.defer()
    if team_id is None:
        team_id = get_registered_team(interaction.user.id)

    if team_id is None:
        await interaction.followup.send("⚠️ No team ID provided or registered. Use `/register team_id:<your id>` first, or pass one directly.")
        return

    gameweek = get_current_gameweek()
    player_ids = get_squad_player_ids(team_id, gameweek)
    if player_ids is None:
        await interaction.followup.send(
            "⚠️ Your squad isn't available yet — this usually means the season hasn't "
            "started, or your team ID is incorrect."
        )
        return
    squad = build_squad_from_ids(player_ids)
    fixtures_df = get_fixtures()
    captain = suggest_captain(squad, fixtures_df)

    await interaction.followup.send(f"Captain pick: **{captain['web_name']}**")

@tree.command(name="register", description="Save your FPL team ID so you don't need to enter it every time")
@app_commands.describe(team_id="Your FPL team ID (find it in your FPL team URL)")
async def register_command(interaction: discord.Interaction, team_id: int):
    register_user(interaction.user.id, team_id)
    await interaction.response.send_message(f"✅ Registered team ID {team_id}. You can now use /team, /transfers, and /captain without entering it again.")
    


client.run(TOKEN)