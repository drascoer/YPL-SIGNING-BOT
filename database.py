import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).with_name("ypl_signing_bot.db")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                budget INTEGER NOT NULL DEFAULT 0,
                team_role_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(guild_id, name)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS team_managers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                team_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                UNIQUE(guild_id, team_id, role_id),
                FOREIGN KEY(team_id) REFERENCES teams(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                team_id INTEGER,
                salary INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active',
                UNIQUE(guild_id, name),
                FOREIGN KEY(team_id) REFERENCES teams(id)
            )
            """
        )

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                command_name TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                UNIQUE(guild_id, command_name)
            )
            """
        )


def get_command_status(guild_id: int, command_name: str) -> bool:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT enabled FROM guild_settings WHERE guild_id = ? AND command_name = ?",
            (guild_id, command_name.lower()),
        ).fetchone()
        if row is None:
            return True
        return bool(row["enabled"])


def set_command_enabled(guild_id: int, command_name: str, enabled: bool) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO guild_settings (guild_id, command_name, enabled)
            VALUES (?, ?, ?)
            ON CONFLICT(guild_id, command_name)
            DO UPDATE SET enabled = excluded.enabled
            """,
            (guild_id, command_name.lower(), 1 if enabled else 0),
        )
        conn.commit()


def get_all_command_statuses(guild_id: int):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT command_name, enabled FROM guild_settings WHERE guild_id = ? ORDER BY command_name ASC",
            (guild_id,),
        ).fetchall()

    result = {}
    for row in rows:
        result[row["command_name"]] = bool(row["enabled"])
    return result


def get_team_by_name(guild_id: int, team_name: str):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM teams WHERE guild_id = ? AND LOWER(name) = LOWER(?)",
            (guild_id, team_name),
        ).fetchone()


def get_team_by_id(team_id: int):
    with get_connection() as conn:
        return conn.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()


def list_teams(guild_id: int):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM teams WHERE guild_id = ? ORDER BY name ASC",
            (guild_id,),
        ).fetchall()


def add_team(guild_id: int, team_name: str, team_role_id: int | None = None):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO teams (guild_id, name, team_role_id, budget) VALUES (?, ?, ?, 0)",
            (guild_id, team_name, team_role_id),
        )
        conn.commit()
        return get_team_by_name(guild_id, team_name)


def remove_team(guild_id: int, team_name: str):
    with get_connection() as conn:
        team = get_team_by_name(guild_id, team_name)
        if not team:
            return False
        conn.execute("DELETE FROM players WHERE guild_id = ? AND team_id = ?", (guild_id, team["id"]))
        conn.execute("DELETE FROM team_managers WHERE guild_id = ? AND team_id = ?", (guild_id, team["id"]))
        conn.execute("DELETE FROM teams WHERE guild_id = ? AND id = ?", (guild_id, team["id"]))
        conn.commit()
        return True


def add_budget(guild_id: int, team_name: str, amount: int):
    if amount < 0:
        raise ValueError("Budget amount cannot be negative.")

    with get_connection() as conn:
        team = get_team_by_name(guild_id, team_name)
        if not team:
            return None
        conn.execute(
            "UPDATE teams SET budget = budget + ? WHERE guild_id = ? AND id = ?",
            (amount, guild_id, team["id"]),
        )
        conn.commit()
        return get_team_by_id(team["id"])


def add_manager_role(guild_id: int, team_name: str, role_id: int):
    with get_connection() as conn:
        team = get_team_by_name(guild_id, team_name)
        if not team:
            return None
        conn.execute(
            "INSERT OR IGNORE INTO team_managers (guild_id, team_id, role_id) VALUES (?, ?, ?)",
            (guild_id, team["id"], role_id),
        )
        conn.commit()
        return team


def list_manager_roles(guild_id: int, team_id: int):
    with get_connection() as conn:
        return conn.execute(
            "SELECT role_id FROM team_managers WHERE guild_id = ? AND team_id = ? ORDER BY role_id ASC",
            (guild_id, team_id),
        ).fetchall()


def get_player(guild_id: int, player_name: str):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM players WHERE guild_id = ? AND LOWER(name) = LOWER(?)",
            (guild_id, player_name),
        ).fetchone()


def get_player_for_team(guild_id: int, player_name: str, team_id: int):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM players WHERE guild_id = ? AND LOWER(name) = LOWER(?) AND team_id = ?",
            (guild_id, player_name, team_id),
        ).fetchone()


def sign_player(guild_id: int, player_name: str, team_name: str, salary: int):
    if salary < 0:
        raise ValueError("Salary cannot be negative.")

    with get_connection() as conn:
        team = get_team_by_name(guild_id, team_name)
        if not team:
            return None

        if team["budget"] < salary:
            return "insufficient_budget"

        conn.execute(
            "UPDATE teams SET budget = budget - ? WHERE guild_id = ? AND id = ?",
            (salary, guild_id, team["id"]),
        )

        conn.execute(
            """
            INSERT INTO players (guild_id, name, team_id, salary, status)
            VALUES (?, ?, ?, ?, 'active')
            ON CONFLICT(guild_id, name)
            DO UPDATE SET team_id = excluded.team_id, salary = excluded.salary, status = 'active'
            """,
            (guild_id, player_name, team["id"], salary),
        )
        conn.commit()
        return get_team_by_id(team["id"])


def release_player(guild_id: int, player_name: str, team_name: str | None = None):
    with get_connection() as conn:
        if team_name:
            team = get_team_by_name(guild_id, team_name)
            if not team:
                return False
            player = get_player_for_team(guild_id, player_name, team["id"])
        else:
            player = get_player(guild_id, player_name)

        if not player:
            return False

        conn.execute(
            "UPDATE players SET team_id = NULL, salary = 0, status = 'released' WHERE guild_id = ? AND id = ?",
            (guild_id, player["id"]),
        )
        conn.commit()
        return True


def transfer_player(guild_id: int, player_name: str, current_team_name: str, target_team_name: str):
    with get_connection() as conn:
        source_team = get_team_by_name(guild_id, current_team_name)
        if not source_team:
            return False

        target_team = get_team_by_name(guild_id, target_team_name)
        if not target_team:
            return False

        player = get_player_for_team(guild_id, player_name, source_team["id"])
        if not player:
            return False

        conn.execute(
            "UPDATE players SET team_id = ?, status = 'active' WHERE guild_id = ? AND id = ?",
            (target_team["id"], guild_id, player["id"]),
        )
        conn.commit()
        return True


def list_players_for_team(guild_id: int, team_name: str):
    with get_connection() as conn:
        team = get_team_by_name(guild_id, team_name)
        if not team:
            return []
        return conn.execute(
            "SELECT * FROM players WHERE guild_id = ? AND team_id = ? AND status = 'active' ORDER BY name ASC",
            (guild_id, team["id"]),
        ).fetchall()


def can_manage_team(member, team_id: int) -> bool:
    if member.guild_permissions.administrator:
        return True

    team = get_team_by_id(team_id)
    if not team:
        return False

    role_ids = {team["team_role_id"]} if team["team_role_id"] else set()
    for row in list_manager_roles(member.guild.id, team_id):
        role_ids.add(row["role_id"])

    return any(role.id in role_ids for role in member.roles)

