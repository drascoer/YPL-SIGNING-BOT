import os

from dotenv import load_dotenv

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
DEFAULT_GUILD_ID = os.getenv("DEFAULT_GUILD_ID")

if DEFAULT_GUILD_ID and DEFAULT_GUILD_ID.isdigit():
    DEFAULT_GUILD_ID = int(DEFAULT_GUILD_ID)
else:
    DEFAULT_GUILD_ID = None
