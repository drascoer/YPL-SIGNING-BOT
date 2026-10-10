import os
import threading
import discord
from flask import Flask
from discord import app_commands

import config
from database import (
    add_budget,
    add_team,
    get_all_command_statuses,
    get_team_by_name,
    get_command_status,
    init_db,
    list_players_for_team,
    list_teams,
    release_player,
    remove_team,
    set_command_enabled,
    sign_player,
    transfer_player,
)

LOG_CHANNEL_ID = 1464578481575825472
MANAGER_ROLE_ID = 1464578480237707327

app = Flask(__name__)

COMMAND_NAMES = [
    "help",
    "teams",
    "roster",
    "addteam",
    "removeteam",
    "sign",
    "release",
    "transfer",
    "addbudget",
    "turnoncommand",
    "turnoffcommand",
    "dashboard",
    "togglecommand",
]


@app.route("/")
def healthcheck():
    return {"status": "ok", "service": "YPL Signing Bot"}, 200


def run_flask():
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)


def has_manager_role(member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(role.id == MANAGER_ROLE_ID for role in member.roles)


async def ensure_command_enabled(interaction: discord.Interaction, command_name: str):
    if command_name in {"turnoncommand", "turnoffcommand", "togglecommand", "dashboard"}:
        return True

    if interaction.user.guild_permissions.administrator:
        return True

    if not get_command_status(interaction.guild_id, command_name):
        await send_error(interaction, f"/{command_name} is currently disabled by an admin.")
        return False

    return True


class YPLSigningBot(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        if config.DEFAULT_GUILD_ID:
            guild = discord.Object(id=config.DEFAULT_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

client = YPLSigningBot(intents=intents)


@client.event
async def on_ready():
    print(f"Logged in as {client.user} ({client.user.id})")
    print("YPL signing bot is online and ready.")


async def send_error(interaction: discord.Interaction, message: str):
    if interaction.response.is_done():
        await interaction.followup.send(message, ephemeral=True)
    else:
        await interaction.response.send_message(message, ephemeral=True)


async def log_to_channel(guild: discord.Guild, message: str, embed: discord.Embed = None):
    try:
        channel = guild.get_channel(LOG_CHANNEL_ID)
        if channel and isinstance(channel, discord.TextChannel):
            if embed:
                await channel.send(message, embed=embed)
            else:
                await channel.send(message)
    except Exception as e:
        print(f"Failed to log to channel: {e}")


@client.tree.command(name="help", description="Show all YPL bot commands")
async def help_command(interaction: discord.Interaction):
    if not await ensure_command_enabled(interaction, "help"):
        return

    commands = [
        "/teams — list all teams",
        "/roster <team> — show team roster",
        "/addteam <name> <role> — create a team (ADMIN)",
        "/removeteam <team> — remove a team (ADMIN)",
        "/sign <team> <user> — sign a player to team (MANAGER)",
        "/release <team> <user> — release a player from team (MANAGER)",
        "/transfer <team> <user> <target_team> — move a player (MANAGER, costs 1 budget)",
        "/addbudget <team> <amount> — add team budget (ADMIN)",
        "/dashboard — view command status (ADMIN)",
        "/turnoncommand <command> — enable a command (ADMIN)",
        "/turnoffcommand <command> — disable a command (ADMIN)",
    ]
    embed = discord.Embed(title="YPL Signing Bot Help", color=discord.Color.gold())
    embed.add_field(name="Commands", value="\n".join(commands), inline=False)
    await interaction.response.send_message(embed=embed)


@client.tree.command(name="dashboard", description="View whether commands are enabled or disabled")
async def dashboard(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await send_error(interaction, "Only admins can view the dashboard.")
        return

    statuses = get_all_command_statuses(interaction.guild_id)
    lines = []
    for command in COMMAND_NAMES:
        enabled = statuses.get(command, True)
        lines.append(f"- {command}: {'ON' if enabled else 'OFF'}")

    embed = discord.Embed(title="Command Dashboard", color=discord.Color.purple())
    embed.add_field(name="Status", value="\n".join(lines), inline=False)
    await interaction.response.send_message(embed=embed)


@client.tree.command(name="turnoncommand", description="Turn a command back on (ADMIN)")
@app_commands.describe(command="Command to enable")
async def turnoncommand(interaction: discord.Interaction, command: str):
    if not interaction.user.guild_permissions.administrator:
        await send_error(interaction, "Only admins can toggle commands.")
        return

    normalized = command.lower().strip()
    if normalized == "all":
        for name in COMMAND_NAMES:
            set_command_enabled(interaction.guild_id, name, True)
        await interaction.response.send_message("All commands have been turned on.")
        return

    if normalized not in COMMAND_NAMES:
        await send_error(interaction, f"Unknown command '{command}'.")
        return

    set_command_enabled(interaction.guild_id, normalized, True)
    await interaction.response.send_message(f"/{normalized} has been enabled.")


@client.tree.command(name="turnoffcommand", description="Turn a command off (ADMIN)")
@app_commands.describe(command="Command to disable")
async def turnoffcommand(interaction: discord.Interaction, command: str):
    if not interaction.user.guild_permissions.administrator:
        await send_error(interaction, "Only admins can toggle commands.")
        return

    normalized = command.lower().strip()
    if normalized == "all":
        for name in COMMAND_NAMES:
            set_command_enabled(interaction.guild_id, name, False)
        await interaction.response.send_message("All commands have been turned off.")
        return

    if normalized not in COMMAND_NAMES:
        await send_error(interaction, f"Unknown command '{command}'.")
        return

    set_command_enabled(interaction.guild_id, normalized, False)
    await interaction.response.send_message(f"/{normalized} has been disabled.")


@client.tree.command(name="togglecommand", description="Toggle command status (ADMIN)")
@app_commands.describe(command="Command to toggle", enabled="On or off")
async def togglecommand(interaction: discord.Interaction, command: str, enabled: bool):
    if not interaction.user.guild_permissions.administrator:
        await send_error(interaction, "Only admins can toggle commands.")
        return

    normalized = command.lower().strip()
    if normalized == "all":
        for name in COMMAND_NAMES:
            set_command_enabled(interaction.guild_id, name, enabled)
        await interaction.response.send_message(f"All commands have been set to {'ON' if enabled else 'OFF'}.")
        return

    if normalized not in COMMAND_NAMES:
        await send_error(interaction, f"Unknown command '{command}'.")
        return

    set_command_enabled(interaction.guild_id, normalized, enabled)
    await interaction.response.send_message(f"/{normalized} has been set to {'ON' if enabled else 'OFF'}.")


@client.tree.command(name="teams", description="List all teams in the league")
async def teams(interaction: discord.Interaction):
    if not await ensure_command_enabled(interaction, "teams"):
        return

    rows = list_teams(interaction.guild_id)
    if not rows:
        await interaction.response.send_message("No teams have been created yet.")
        return

    total_budget = sum(row["budget"] for row in rows)
    team_names = [f"- {row['name']} (${row['budget']})" for row in rows]
    embed = discord.Embed(title="League Teams", color=discord.Color.green())
    embed.add_field(name="Teams", value="\n".join(team_names), inline=False)
    embed.set_footer(text=f"Total league budget: ${total_budget}")
    await interaction.response.send_message(embed=embed)


@client.tree.command(name="roster", description="Show the roster for a team")
@app_commands.describe(team="The name of the team")
async def roster(interaction: discord.Interaction, team: str):
    if not await ensure_command_enabled(interaction, "roster"):
        return

    team_row = get_team_by_name(interaction.guild_id, team)
    if not team_row:
        await send_error(interaction, f"Team '{team}' does not exist.")
        return

    players = list_players_for_team(interaction.guild_id, team)
    if not players:
        await interaction.response.send_message(f"{team} currently has no active players.")
        return

    roster_lines = [f"{player['name']}" for player in players]
    embed = discord.Embed(title=f"{team} roster", color=discord.Color.blue())
    embed.add_field(name="Players", value="\n".join(roster_lines), inline=False)
    embed.add_field(name="Budget", value=f"${team_row['budget']}", inline=False)
    await interaction.response.send_message(embed=embed)


@client.tree.command(name="addteam", description="Create a team and attach a team role")
@app_commands.describe(name="The team name", role="The Discord role assigned to the team")
async def addteam(interaction: discord.Interaction, name: str, role: discord.Role):
    if not await ensure_command_enabled(interaction, "addteam"):
        return

    if not interaction.user.guild_permissions.administrator:
        await send_error(interaction, "Only admins can create teams.")
        return

    clean_name = name.strip()
    if not clean_name:
        await send_error(interaction, "Team name cannot be empty.")
        return

    if get_team_by_name(interaction.guild_id, clean_name):
        await send_error(interaction, f"Team '{clean_name}' already exists.")
        return

    add_team(interaction.guild_id, clean_name, role.id)

    embed = discord.Embed(
        title="Team Created",
        description=f"Team '{clean_name}' has been created and assigned to role {role.mention}.",
        color=discord.Color.green(),
    )
    embed.set_footer(text=f"Created by {interaction.user.name}")

    await interaction.response.send_message(f"Team '{clean_name}' created and assigned to role {role.mention}.")
    await log_to_channel(interaction.guild, "", embed)


@client.tree.command(name="removeteam", description="Remove a team and all its player records")
@app_commands.describe(team="Team to remove")
async def removeteam(interaction: discord.Interaction, team: str):
    if not await ensure_command_enabled(interaction, "removeteam"):
        return

    if not interaction.user.guild_permissions.administrator:
        await send_error(interaction, "Only admins can remove teams.")
        return

    removed = remove_team(interaction.guild_id, team)
    if not removed:
        await send_error(interaction, f"Team '{team}' does not exist.")
        return

    embed = discord.Embed(
        title="Team Removed",
        description=f"Team '{team}' and all roster records have been removed.",
        color=discord.Color.red(),
    )
    embed.set_footer(text=f"Removed by {interaction.user.name}")

    await interaction.response.send_message(f"Team '{team}' and all roster records were removed.")
    await log_to_channel(interaction.guild, "", embed)


@client.tree.command(name="sign", description="Sign a player to a team")
@app_commands.describe(team="Team to sign the player to", user="Discord user to sign")
async def sign(interaction: discord.Interaction, team: str, user: discord.User):
    if not await ensure_command_enabled(interaction, "sign"):
        return

    if not has_manager_role(interaction.user):
        await send_error(interaction, "You do not have permission to use this command.")
        return

    team_row = get_team_by_name(interaction.guild_id, team)
    if not team_row:
        await send_error(interaction, f"Team '{team}' does not exist.")
        return

    player_name = user.name
    result = sign_player(interaction.guild_id, player_name, team, 0)
    if result == "insufficient_budget":
        await send_error(interaction, f"{team} does not have enough budget for the signing.")
        return

    try:
        guild = interaction.guild
        member = await guild.fetch_member(user.id)
        if team_row["team_role_id"]:
            role = guild.get_role(team_row["team_role_id"])
            if role:
                await member.add_roles(role)
    except Exception as e:
        print(f"Could not add role to member: {e}")

    embed = discord.Embed(
        title="Player Signed",
        description=f"{user.mention} has been signed to {team}.",
        color=discord.Color.blue(),
    )
    embed.set_footer(text=f"Signed by {interaction.user.name}")

    await interaction.response.send_message(f"{user.mention} has been signed to {team}.")
    await log_to_channel(interaction.guild, "", embed)


@client.tree.command(name="release", description="Release a player from a team")
@app_commands.describe(team="Team the player is on", user="Discord user to release")
async def release(interaction: discord.Interaction, team: str, user: discord.User):
    if not await ensure_command_enabled(interaction, "release"):
        return

    if not has_manager_role(interaction.user):
        await send_error(interaction, "You do not have permission to use this command.")
        return

    team_row = get_team_by_name(interaction.guild_id, team)
    if not team_row:
        await send_error(interaction, f"Team '{team}' does not exist.")
        return

    player_name = user.name
    success = release_player(interaction.guild_id, player_name, team_name=team)
    if not success:
        await send_error(interaction, f"{user.mention} was not found on {team}.")
        return

    try:
        guild = interaction.guild
        member = await guild.fetch_member(user.id)
        if team_row["team_role_id"]:
            role = guild.get_role(team_row["team_role_id"])
            if role:
                await member.remove_roles(role)
    except Exception as e:
        print(f"Could not remove role from member: {e}")

    embed = discord.Embed(
        title="Player Released",
        description=f"{user.mention} has been released from {team}.",
        color=discord.Color.orange(),
    )
    embed.set_footer(text=f"Released by {interaction.user.name}")

    await interaction.response.send_message(f"{user.mention} has been released from {team}.")
    await log_to_channel(interaction.guild, "", embed)


@client.tree.command(name="transfer", description="Transfer a player from one team to another (costs 1 budget)")
@app_commands.describe(team="Current team", user="Discord user to transfer", target_team="Destination team")
async def transfer(interaction: discord.Interaction, team: str, user: discord.User, target_team: str):
    if not await ensure_command_enabled(interaction, "transfer"):
        return

    if not has_manager_role(interaction.user):
        await send_error(interaction, "You do not have permission to use this command.")
        return

    source_team = get_team_by_name(interaction.guild_id, team)
    if not source_team:
        await send_error(interaction, f"Team '{team}' does not exist.")
        return

    target_row = get_team_by_name(interaction.guild_id, target_team)
    if not target_row:
        await send_error(interaction, f"Target team '{target_team}' does not exist.")
        return

    if target_row["budget"] < 1:
        await send_error(interaction, f"{target_team} does not have enough budget for the transfer.")
        return

    player_name = user.name
    success = transfer_player(interaction.guild_id, player_name, team, target_team)
    if not success:
        await send_error(interaction, f"{user.mention} was not found on {team}.")
        return

    add_budget(interaction.guild_id, target_team, -1)

    try:
        guild = interaction.guild
        member = await guild.fetch_member(user.id)
        if source_team["team_role_id"]:
            source_role = guild.get_role(source_team["team_role_id"])
            if source_role:
                await member.remove_roles(source_role)
        if target_row["team_role_id"]:
            target_role = guild.get_role(target_row["team_role_id"])
            if target_role:
                await member.add_roles(target_role)
    except Exception as e:
        print(f"Could not update roles for member: {e}")

    embed = discord.Embed(
        title="Player Transferred",
        description=f"{user.mention} has been transferred from {team} to {target_team}.",
        color=discord.Color.purple(),
    )
    embed.set_footer(text=f"Transferred by {interaction.user.name}")

    await interaction.response.send_message(f"{user.mention} has been transferred from {team} to {target_team}.")
    await log_to_channel(interaction.guild, "", embed)


@client.tree.command(name="addbudget", description="Add budget to a team")
@app_commands.describe(team="Team name", amount="Cash to add")
async def addbudget(interaction: discord.Interaction, team: str, amount: int):
    if not await ensure_command_enabled(interaction, "addbudget"):
        return

    if not interaction.user.guild_permissions.administrator:
        await send_error(interaction, "Only admins can add budget to teams.")
        return

    team_row = get_team_by_name(interaction.guild_id, team)
    if not team_row:
        await send_error(interaction, f"Team '{team}' does not exist.")
        return

    if amount <= 0:
        await send_error(interaction, "Budget increase must be greater than zero.")
        return

    updated_team = add_budget(interaction.guild_id, team, amount)
    if updated_team is None:
        await send_error(interaction, f"Team '{team}' does not exist.")
        return

    embed = discord.Embed(
        title="Budget Added",
        description=f"${amount} has been added to {team}. New budget: ${updated_team['budget']}.",
        color=discord.Color.green(),
    )
    embed.set_footer(text=f"Added by {interaction.user.name}")

    await interaction.response.send_message(f"Added ${amount} to {team}. New budget: ${updated_team['budget']}.")
    await log_to_channel(interaction.guild, "", embed)


if __name__ == "__main__":
    init_db()
    if not config.DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing. Add it to your .env file.")

    threading.Thread(target=run_flask, daemon=True).start()
    client.run(config.DISCORD_TOKEN)
