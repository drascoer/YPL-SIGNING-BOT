
import os
import asyncio
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("DEFAULT_GUILD_ID", "0"))
VERIFY_URL = "https://website2-umber-zeta.vercel.app/"

if not TOKEN:
    raise RuntimeError("Missing DISCORD_TOKEN in your .env file.")

if not GUILD_ID:
    raise RuntimeError("Missing DEFAULT_GUILD_ID in your .env file.")

intents = discord.Intents.default()

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")


@bot.tree.command(
    name="verify",
    description="Send the verification embed to this channel."
)
@app_commands.guild_only()
@app_commands.default_permissions(administrator=True)
async def verify(interaction: discord.Interaction):
    # Extra permission check for security
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ You need Administrator permissions to use this command.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="✦  Verification Required",
        description=(
            "Welcome to our community.\n\n"
            "To gain access, please complete the verification process "
            "using the official website below.\n\n"
            "Click **Verify Now** to continue."
        ),
        color=discord.Color.from_rgb(88, 101, 242)
    )

    embed.add_field(
        name="🔐 Secure Verification",
        value=(
            "Use the button below to open the verification page. "
            "Only continue if you trust this website."
        ),
        inline=False
    )

    embed.set_footer(
        text="Verification System • Secure Access"
    )

    view = discord.ui.View(timeout=None)

    view.add_item(
        discord.ui.Button(
            label="Verify Now",
            emoji="🔗",
            style=discord.ButtonStyle.link,
            url=VERIFY_URL
        )
    )

    await interaction.response.send_message(
        embed=embed,
        view=view
    )


async def main():
    async with bot:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
        print(f"Slash commands synced to guild {GUILD_ID}")
        await bot.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
