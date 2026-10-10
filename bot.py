import discord
from discord import app_commands

import config
from database import (
    add_budget,
    add_manager_role,
    add_team,
    can_manage_team,
    get_team_by_name,
    init_db,
    list_players_for_team,
    list_teams,
    release_player,
    remove_team,
    sign_player,
    transfer_player,
)


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
intents.members = True
intents.message_content = True

client = YPLSigningBot(intents=intents)


@client.event
async def on_ready():
    print(f"Logged in as {client.user} ({client.user.id})")
    print("Ready to manage YPL roster operations.")


async def send_error(interaction: discord.Interaction, message: str):
    await interaction.response.send_message(message, ephemeral=True)


@client.tree.command(name="teams", description="List all teams in the league")
async def teams(interaction: discord.Interaction):
    rows = list_teams(interaction.guild_id)
    if not rows:
        await interaction.response.send_message("No teams have been created yet.")
        return

    team_names = [f"- {row['name']} (${row['budget']})" for row in rows]
    embed = discord.Embed(title="League Teams", color=discord.Color.green())
    embed.add_field(name="Teams", value="\n".join(team_names), inline=False)
    await interaction.response.send_message(embed=embed)


@client.tree.command(name="roster", description="Show the roster for a team")
@app_commands.describe(team="The name of the team")
async def roster(interaction: discord.Interaction, team: str):
    team_row = get_team_by_name(interaction.guild_id, team)
    if not team_row:
        await send_error(interaction, f"Team '{team}' does not exist.")
        return

    players = list_players_for_team(interaction.guild_id, team)
    if not players:
        await interaction.response.send_message(f"{team} currently has no active players.")
        return

    roster_lines = [f"{player['name']} - ${player['salary']}" for player in players]
    embed = discord.Embed(title=f"{team} roster", color=discord.Color.blue())
    embed.add_field(name="Players", value="\n".join(roster_lines), inline=False)
    embed.add_field(name="Budget", value=f"${team_row['budget']}", inline=False)
    await interaction.response.send_message(embed=embed)


@client.tree.command(name="addteam", description="Create a team and attach a team role")
@app_commands.describe(name="The team name", role="The Discord role assigned to the team")
async def addteam(interaction: discord.Interaction, name: str, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await send_error(interaction, "Only admins can create teams.")
        return

    if get_team_by_name(interaction.guild_id, name):
        await send_error(interaction, f"Team '{name}' already exists.")
        return

    add_team(interaction.guild_id, name, role.id)
    await interaction.response.send_message(f"Team '{name}' created and assigned to role {role.mention}.")


@client.tree.command(name="removeteam", description="Remove a team and all its player records")
@app_commands.describe(team="Team to remove")
async def removeteam(interaction: discord.Interaction, team: str):
    if not interaction.user.guild_permissions.administrator:
        await send_error(interaction, "Only admins can remove teams.")
        return

    removed = remove_team(interaction.guild_id, team)
    if not removed:
        await send_error(interaction, f"Team '{team}' does not exist.")
        return

    await interaction.response.send_message(f"Team '{team}' and all roster records were removed.")


@client.tree.command(name="sign", description="Sign a player to a team")
@app_commands.describe(team="Team to sign the player to", player="Player name", salary="Contract salary")
async def sign(interaction: discord.Interaction, team: str, player: str, salary: int):
    team_row = get_team_by_name(interaction.guild_id, team)
    if not team_row:
        await send_error(interaction, f"Team '{team}' does not exist.")
        return

    if not can_manage_team(interaction.user, team_row["id"]):
        await send_error(interaction, "You do not have permission to sign players for this team.")
        return

    if salary < 0:
        await send_error(interaction, "Salary cannot be negative.")
        return

    result = sign_player(interaction.guild_id, player, team, salary)
    if result == "insufficient_budget":
        await send_error(interaction, f"{team} does not have enough budget for a ${salary} signing.")
        return

    await interaction.response.send_message(f"{player} has been signed to {team} for ${salary}.")


@client.tree.command(name="release", description="Release a player from a team")
@app_commands.describe(team="Team the player is on", player="Player name")
async def release(interaction: discord.Interaction, team: str, player: str):
    team_row = get_team_by_name(interaction.guild_id, team)
    if not team_row:
        await send_error(interaction, f"Team '{team}' does not exist.")
        return

    if not can_manage_team(interaction.user, team_row["id"]):
        await send_error(interaction, "You do not have permission to release players for this team.")
        return

    success = release_player(interaction.guild_id, player, team_name=team)
    if not success:
        await send_error(interaction, f"Player '{player}' was not found on {team}.")
        return

    await interaction.response.send_message(f"{player} has been released from {team}.")


@client.tree.command(name="transfer", description="Transfer a player from one team to another")
@app_commands.describe(team="Current team", player="Player name", target_team="Destination team")
async def transfer(interaction: discord.Interaction, team: str, player: str, target_team: str):
    source_team = get_team_by_name(interaction.guild_id, team)
    if not source_team:
        await send_error(interaction, f"Team '{team}' does not exist.")
        return

    target_row = get_team_by_name(interaction.guild_id, target_team)
    if not target_row:
        await send_error(interaction, f"Target team '{target_team}' does not exist.")
        return

    if not can_manage_team(interaction.user, source_team["id"]):
        await send_error(interaction, "You do not have permission to transfer players from this team.")
        return

    success = transfer_player(interaction.guild_id, player, team, target_team)
    if not success:
        await send_error(interaction, f"Player '{player}' was not found on {team}.")
        return

    await interaction.response.send_message(f"{player} has been transferred from {team} to {target_team}.")


@client.tree.command(name="addbudget", description="Add budget to a team")
@app_commands.describe(team="Team name", amount="Cash to add")
async def addbudget(interaction: discord.Interaction, team: str, amount: int):
    team_row = get_team_by_name(interaction.guild_id, team)
    if not team_row:
        await send_error(interaction, f"Team '{team}' does not exist.")
        return

    if not can_manage_team(interaction.user, team_row["id"]):
        await send_error(interaction, "You do not have permission to edit this team's budget.")
        return

    if amount < 0:
        await send_error(interaction, "Budget amount cannot be negative.")
        return

    updated_team = add_budget(interaction.guild_id, team, amount)
    if updated_team is None:
        await send_error(interaction, f"Team '{team}' does not exist.")
        return

    await interaction.response.send_message(f"Added ${amount} to {team}. New budget: ${updated_team['budget']}.")


@client.tree.command(name="addmanager", description="Grant a Discord role access to manage a team")
@app_commands.describe(team="Team name", role="Role that should be allowed to sign and release")
async def addmanager(interaction: discord.Interaction, team: str, role: discord.Role):
    if not interaction.user.guild_permissions.administrator:
        await send_error(interaction, "Only admins can assign team managers.")
        return

    team_row = get_team_by_name(interaction.guild_id, team)
    if not team_row:
        await send_error(interaction, f"Team '{team}' does not exist.")
        return

    add_manager_role(interaction.guild_id, team, role.id)
    await interaction.response.send_message(f"Role {role.mention} was added as a manager for {team}.")


if __name__ == "__main__":
    init_db()
    if not config.DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing. Add it to your .env file.")
    client.run(config.DISCORD_TOKEN)
