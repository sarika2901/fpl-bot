import os
import sys
from pathlib import Path

import discord
from discord import app_commands
from dotenv import load_dotenv
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from api.data_fetcher import get_current_gameweek, get_players_dataframe, get_fixtures
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

from analysis.team_analyzer import get_team_summary, get_squad_player_ids, build_squad_from_ids, load_mock_squad, flag_injuries, suggest_starting_xi

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
    status, player_ids, bank = get_squad_player_ids(team_id, gameweek)

    if status == "invalid_team_id":
        await interaction.followup.send(
            "❌ That team ID doesn't exist on the FPL site. Double-check it in your "
            "FPL team URL and try again, or re-register with `/register`."
        )
        return
    elif status == "season_not_started":
        await interaction.followup.send(
            "🗓️ The season hasn't started for this team yet — your squad picks aren't "
            "available until after gameweek 1 kicks off (Aug 22)."
        )
        return
    elif status == "picks_unavailable":
        await interaction.followup.send(
            "⚠️ Your team ID is valid, but this gameweek's picks aren't available yet "
            "(they usually lock in shortly after the gameweek deadline). Try again closer "
            "to kickoff."
        )
        return

    # if player_ids is None:
    #     await interaction.followup.send(
    #         "⚠️ Your squad isn't available yet — this usually means the season hasn't "
    #         "started, or your team ID is incorrect."
    #     )
    #     return
    try:
        summary = get_team_summary(team_id)
        squad = build_squad_from_ids(player_ids)
        fixtures_df = get_fixtures()
        squad = suggest_starting_xi(squad, fixtures_df)
    except Exception as e:
        print(f"[team_command] error: {e}")
        await interaction.followup.send("⚠️ Couldn't fetch live data right now — try again in a minute.")
        return

    lines = [f"**{summary['team_name']}** - {summary['overall_points']} pts", "", "**Starting XI:**"]
    starting = squad[squad["role"] == "Starting XI"]
    bench = squad[squad["role"] == "Bench"]

    for _, player in starting.iterrows():
        lines.append(f"{player['web_name']} ({player['position']}) - {player['total_points']} pts")

    lines.append("\n**Bench:**")
    for _, player in bench.iterrows():
        lines.append(f"{player['web_name']} ({player['position']}) - {player['total_points']} pts")

    flagged = flag_injuries(squad)
    if not flagged.empty:
        lines.append("\n**⚠️ Injury/Availability Concerns:**")
        for _, player in flagged.iterrows():
            chance = player["chance_of_playing_next_round"]
            chance_str = f"{int(chance)}% chance to play" if pd.notna(chance) else "status unclear"
            lines.append(f"{player['web_name']}: {player['news']} ({chance_str})")

    await interaction.followup.send("\n".join(lines))

from analysis.transfer_engine import suggest_transfers, suggest_captain


@tree.command(name="transfers", description="Get transfer suggestions")
async def transfers_command(interaction: discord.Interaction, team_id: Optional[int] = None):
    await interaction.response.defer()
    if team_id is None:
        team_id = get_registered_team(interaction.user.id)

    if team_id is None:
        await interaction.followup.send("⚠️ No team ID provided or registered. Use `/register team_id:<your id>` first, or pass one directly.")
        return

    gameweek = get_current_gameweek()
    status, player_ids, bank = get_squad_player_ids(team_id, gameweek)

    if status == "invalid_team_id":
        await interaction.followup.send(
            "❌ That team ID doesn't exist on the FPL site. Double-check it in your "
            "FPL team URL and try again, or re-register with `/register`."
        )
        return
    elif status == "season_not_started":
        await interaction.followup.send(
            "🗓️ The season hasn't started for this team yet — your squad picks aren't "
            "available until after gameweek 1 kicks off (Aug 22)."
        )
        return
    elif status == "picks_unavailable":
        await interaction.followup.send(
            "⚠️ Your team ID is valid, but this gameweek's picks aren't available yet "
            "(they usually lock in shortly after the gameweek deadline). Try again closer "
            "to kickoff."
        )
        return

    # if player_ids is None:
    #         await interaction.followup.send(
    #             "⚠️ Your squad isn't available yet — this usually means the season hasn't "
    #             "started, or your team ID is incorrect."
    #         )
    #         return

    try:
        squad = build_squad_from_ids(player_ids)
        all_players = get_players_dataframe()
        suggestions = suggest_transfers(squad, all_players, player_ids, gameweek, bank=bank)
    except Exception as e:
        print(f"[transfers_command] error: {e}")
        await interaction.followup.send("⚠️ Couldn't fetch live data right now — try again in a minute.")
        return

    lines = ["**Transfer Suggestions:**"]
    for _,row in suggestions.iterrows():
        lines.append(f"OUT: {row['sell']} ({row['reason']}) -> IN: {row['buy']}")

    flagged = flag_injuries(squad)
    if not flagged.empty:
        lines.append("\n**⚠️ Current squad injury/availability concerns:**")
        for _, player in flagged.iterrows():
            chance = player["chance_of_playing_next_round"]
            chance_str = f"{int(chance)}% chance to play" if pd.notna(chance) else "status unclear"
            lines.append(f"{player['web_name']}: {player['news']} ({chance_str})")

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
    status, player_ids, bank = get_squad_player_ids(team_id, gameweek)

    if status == "invalid_team_id":
        await interaction.followup.send(
            "❌ That team ID doesn't exist on the FPL site. Double-check it in your "
            "FPL team URL and try again, or re-register with `/register`."
        )
        return
    elif status == "season_not_started":
        await interaction.followup.send(
            "🗓️ The season hasn't started for this team yet — your squad picks aren't "
            "available until after gameweek 1 kicks off (Aug 22)."
        )
        return
    elif status == "picks_unavailable":
        await interaction.followup.send(
            "⚠️ Your team ID is valid, but this gameweek's picks aren't available yet "
            "(they usually lock in shortly after the gameweek deadline). Try again closer "
            "to kickoff."
        )
        return
    
    # if player_ids is None:
    #     await interaction.followup.send(
    #         "⚠️ Your squad isn't available yet — this usually means the season hasn't "
    #         "started, or your team ID is incorrect."
    #     )
    #     return
    
    try:
        squad = build_squad_from_ids(player_ids)
        fixtures_df = get_fixtures()
        captain = suggest_captain(squad, fixtures_df, gameweek)
    except Exception as e:
        print(f"[captain_command] error: {e}")
        await interaction.followup.send("⚠️ Couldn't fetch live data right now — try again in a minute.")
        return

    await interaction.followup.send(f"Captain pick: **{captain['web_name']}**")

@tree.command(name="register", description="Save your FPL team ID so you don't need to enter it every time")
@app_commands.describe(team_id="Your FPL team ID (find it in your FPL team URL)")
async def register_command(interaction: discord.Interaction, team_id: int):
    register_user(interaction.user.id, team_id)
    await interaction.response.send_message(f"✅ Registered team ID {team_id}. You can now use /team, /transfers, and /captain without entering it again.")


@tree.command(name="testteam", description="[TEST] View a squad using mock data, bypassing live picks")
async def testteam_command(interaction: discord.Interaction):
    await interaction.response.defer()

    player_ids = load_mock_squad()  # from analysis/team_analyzer.py
    squad = build_squad_from_ids(player_ids)

    lines = ["**[TEST MODE] Mock Squad**"]
    for _, player in squad.iterrows():
        lines.append(f"{player['web_name']} ({player['position']}) - {player['total_points']} pts")

    await interaction.followup.send("\n".join(lines))


client.run(TOKEN)