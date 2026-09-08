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

from api.data_fetcher import (
    get_current_gameweek, get_planning_gameweek, is_deadline_passed,
    get_players_dataframe, get_fixtures,
)
from analysis.transfer_engine import suggest_transfers, suggest_captain
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

from analysis.team_analyzer import (
    get_team_summary, get_squad_player_ids, build_squad_from_ids,
    load_mock_squad, flag_injuries, suggest_starting_xi, get_free_transfers, get_chip_status,
)
# MY_TEAM_ID = int(os.getenv("MY_TEAM_ID"))
GAMEWEEK = get_current_gameweek()

CHIP_LABELS = {
    "wildcard": "🃏 Wildcard is active — all transfers this week are free.",
    "freehit": "🎯 Free Hit is active — this week's changes revert automatically next GW.",
    "bboost": "🚀 Bench Boost is active — your bench points count this week!",
    "3xc": "🔥 Triple Captain is active — your captain scores 3x this week!",
}

def get_staleness_notice(current_gw):
    """Returns a caveat string if the current gameweek's squad snapshot might
    already be out of date (deadline passed, so the FPL API's locked picks for
    this GW no longer reflect any transfers the manager has since made for
    next week). Returns None if no caveat is needed."""
    if is_deadline_passed(current_gw):
        return (f"ℹ️ This shows your squad as it was locked at GW{current_gw}'s deadline. "
                f"If you've made transfers since, they won't appear here until GW{current_gw + 1}'s "
                f"deadline passes — that's a limitation of the public FPL API, not a bug.\n")
    return None


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
    status, player_ids, bank, active_chip = get_squad_player_ids(team_id, gameweek)

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

    lines = [f"**{summary['team_name']}** - {summary['overall_points']} pts"]

    notice = get_staleness_notice(gameweek)
    if notice:
        lines.append(notice)

    if active_chip in CHIP_LABELS:
        lines.append(CHIP_LABELS[active_chip])

    chip_status = get_chip_status(team_id, gameweek)
    available_chips = [c for c, status in chip_status.items() if status == "available"]
    if available_chips and active_chip is None:
        chip_names = {"wildcard": "Wildcard", "freehit": "Free Hit", "bboost": "Bench Boost", "3xc": "Triple Captain"}
        readable = ", ".join(chip_names[c] for c in available_chips)
        lines.append(f"🃏 _Chips available this half: {readable}_")

    lines += ["", "**Starting XI:**"]
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




@tree.command(name="transfers", description="Get transfer suggestions")
async def transfers_command(interaction: discord.Interaction, team_id: Optional[int] = None):
    await interaction.response.defer()
    if team_id is None:
        team_id = get_registered_team(interaction.user.id)
    if team_id is None:
        await interaction.followup.send("⚠️ No team ID provided or registered. Use `/register team_id:<your id>` first.")
        return

    current_gw = get_current_gameweek()
    status, player_ids, bank, active_chip = get_squad_player_ids(team_id, current_gw)

    if status == "invalid_team_id":
        await interaction.followup.send("❌ That team ID doesn't exist on the FPL site. Double-check it and try again.")
        return
    elif status == "season_not_started":
        await interaction.followup.send("🗓️ The season hasn't started for this team yet.")
        return
    elif status == "picks_unavailable":
        await interaction.followup.send("⚠️ This gameweek's picks aren't available yet. Try again closer to kickoff.")
        return

    planning_gw = get_planning_gameweek()
    free_transfers = get_free_transfers(team_id, planning_gw)
    chip_status = get_chip_status(team_id, planning_gw)
    wildcard_available = chip_status.get("wildcard") == "available"

    try:
        squad = build_squad_from_ids(player_ids)
        all_players = get_players_dataframe()
        suggestions = suggest_transfers(
            squad, all_players, player_ids, planning_gw, bank=bank,
            free_transfers=free_transfers, active_chip=active_chip,
        )
    except Exception as e:
        print(f"[transfers_command] error: {e}")
        await interaction.followup.send("⚠️ Couldn't fetch live data right now — try again in a minute.")
        return

    lines = [f"**Transfer Suggestions (for GW{planning_gw}):**"]
    notice = get_staleness_notice(current_gw)
    if notice:
        lines.insert(0, notice)
    if active_chip in CHIP_LABELS:
        lines.insert(0, CHIP_LABELS[active_chip] + "\n")
    if free_transfers is not None and not (active_chip in ("wildcard", "freehit")):
        lines.append(f"_You have {free_transfers} free transfer{'s' if free_transfers != 1 else ''} banked._\n")
    if wildcard_available and active_chip is None and len(suggestions) >=2:
        lines.append("💡 _You still have a Wildcard available this half. If your squad needs "
                      "several changes, a Wildcard (unlimited free transfers, all at once) may "
                      "be more efficient than taking -4 hits one at a time._\n")

    for _, row in suggestions.iterrows():
        cost_str = f" [{row['cost']}]" if row.get("cost") else ""
        lines.append(f"OUT: {row['sell']} ({row['reason']}) -> IN: {row['buy']}{cost_str}")

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
        await interaction.followup.send("⚠️ No team ID provided or registered. Use `/register team_id:<your id>` first.")
        return

    current_gw = get_current_gameweek()
    status, player_ids, bank, active_chip = get_squad_player_ids(team_id, current_gw)

    if status == "invalid_team_id":
        await interaction.followup.send("❌ That team ID doesn't exist on the FPL site.")
        return
    elif status == "season_not_started":
        await interaction.followup.send("🗓️ The season hasn't started for this team yet.")
        return
    elif status == "picks_unavailable":
        await interaction.followup.send("⚠️ This gameweek's picks aren't available yet.")
        return

    planning_gw = get_planning_gameweek()

    try:
        squad = build_squad_from_ids(player_ids)
        fixtures_df = get_fixtures()
        captain, vice_captain = suggest_captain(squad, fixtures_df, planning_gw)
    except Exception as e:
        print(f"[captain_command] error: {e}")
        await interaction.followup.send("⚠️ Couldn't fetch live data right now — try again in a minute.")
        return

    prefix = CHIP_LABELS.get(active_chip, "") + "\n" if active_chip in CHIP_LABELS else ""
    vc_line = f"\nVice-captain: **{vice_captain['web_name']}**" if vice_captain is not None else ""
    await interaction.followup.send(f"{prefix}Captain pick for GW{planning_gw}: **{captain['web_name']}**{vc_line}")



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