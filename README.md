# YPL SIGNING BOT

A lightweight Discord bot for managing a league roster, player signings, releases, transfers, budgets, and team administration.

## Features
- /addteam - create a new team and assign a signing role
- /removeteam - remove a team and its players
- /roster - list all players on a team
- /sign - sign a player to a team
- /release - remove a player from a team
- /transfer - move a player from one team to another
- /addbudget - add salary or budget funds to a team
- /addmanager - grant a role permission to manage a team

## Quick start

1. Create a Discord bot in the developer portal.
2. Copy `.env.example` to `.env` and populate the values.
3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

4. Run the bot:

   ```bash
   python bot.py
   ```

## Environment variables

- DISCORD_TOKEN - your Discord bot token
- DEFAULT_GUILD_ID - optional guild ID to sync slash commands to a specific server

## Notes

This project uses SQLite so it can run locally without extra database setup.
