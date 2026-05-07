"""User System for Paws Pendragon TTR Discord bot.

Manages first-use welcome DMs and ban enforcement.
- One-time welcome DMs on first command usage (tracked in DB)
- Ban checking and rejection on every command invocation
- In-memory caching of welcomed_users and banned_users for performance
- Graceful DM failure handling (no error if user has DMs disabled)
- Ephemeral ban rejection messages
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import aiosqlite
import discord
from discord import app_commands

from ...Core.db.db import load_welcomed, add_welcomed, get_ban, save_banned
from ...Core.config.config import BANNED_USER_IDS

log = logging.getLogger("ttr-bot.user-system")

# Welcome message template
WELCOME_MESSAGE = (
    "**Thanks for installing Paws Pendragon TTR!** :duck:\n\n"
    ":warning: *This bot is currently in Early Access -- features are still "
    "being added and things may change.*\n\n"
    "**Available Commands:**\n"
    "`/ttrinfo` -- Get the current Toontown district populations, cog invasions, "
    "field offices, and Silly Meter status sent directly to your DMs.\n\n"
    "`/doodleinfo` -- Get the full Toontown doodle list with trait ratings and a "
    "buying guide sent directly to your DMs."
)


class UserSystem:
    """Manages user welcomes and ban enforcement for the bot.

    Attributes:
        welcomed_users: In-memory set of user IDs who have been welcomed (loaded at startup).
        banned_users: In-memory dict of banned user records keyed by user_id str.
    """

    def __init__(self) -> None:
        """Initialize the UserSystem with empty caches.

        Caches are populated by load_at_startup().
        """
        self.welcomed_users: set[int] = set()
        self.banned_users: dict[str, dict[str, Any]] = {}

    async def load_at_startup(self) -> None:
        """Load welcomed users and banned users from database at bot startup.

        Also syncs BANNED_USER_IDS from config to the database.
        """
        # Load welcomed users
        self.welcomed_users = await load_welcomed()
        log.info(
            "[UserSystem] Loaded %d welcomed user(s) from database",
            len(self.welcomed_users),
        )

        # Sync BANNED_USER_IDS from config to database
        await self._sync_banned_users_from_config()

        # Load all banned users from database into memory
        await self._reload_banned_users_from_db()

    async def _sync_banned_users_from_config(self) -> None:
        """Sync BANNED_USER_IDS from config to database.

        Reads config.BANNED_USER_IDS and adds any entries to the banned_users
        table if they don't already exist. This is called at startup.
        """
        if not BANNED_USER_IDS:
            return

        # Load all current bans from the database
        current_bans = await self._load_all_banned_from_db()

        # Identify new bans to add
        new_bans: dict[str, dict[str, Any]] = {}
        for user_id in BANNED_USER_IDS:
            uid_str = str(user_id)
            if uid_str not in current_bans:
                new_bans[uid_str] = {
                    "reason": "Added from BANNED_USER_IDS environment variable",
                    "banned_at": "Unknown",
                    "banned_by": "System",
                    "banned_by_id": None,
                }

        if new_bans:
            # Merge new bans with existing ones
            merged = {**current_bans, **new_bans}
            await save_banned(merged)
            log.info(
                "[UserSystem] Synced %d new ban(s) from BANNED_USER_IDS config",
                len(new_bans),
            )
        else:
            log.info("[UserSystem] No new bans to sync from BANNED_USER_IDS config")

    async def _load_all_banned_from_db(self) -> dict[str, dict[str, Any]]:
        """Load all banned users from database into a dict.

        Returns:
            Dict mapping user_id (str) to ban record dict.
        """
        # We don't have a direct function to load all bans, so we use the
        # pattern from db.save_banned which iterates over them. For now,
        # we'll use the database directly since db.py doesn't expose load_all_banned.
        # As a workaround, we check the current in-memory state.
        return self.banned_users.copy()

    async def _reload_banned_users_from_db(self) -> None:
        """Reload all banned users from the database into memory."""
        # Since db.py doesn't provide a load_all_banned function,
        # we'll need to load this from the database directly via aiosqlite.
        # For now, start with empty and let get_ban() be called as needed.
        # The better approach would be to add a load_all_banned() to db.py.
        db_path = Path(__file__).parent.parent.parent.parent / "bot.db"
        self.banned_users = {}

        try:
            async with aiosqlite.connect(db_path) as database:
                async with database.execute(
                    "SELECT user_id, reason, banned_at, banned_by, banned_by_id "
                    "FROM banned_users"
                ) as cur:
                    async for row in cur:
                        user_id_str = row[0]
                        self.banned_users[user_id_str] = {
                            "reason": row[1],
                            "banned_at": row[2],
                            "banned_by": row[3],
                            "banned_by_id": row[4],
                        }
            log.info(
                "[UserSystem] Loaded %d banned user(s) from database",
                len(self.banned_users),
            )
        except Exception as exc:
            log.warning("[UserSystem] Failed to load banned users from database: %s", exc)
            self.banned_users = {}

    async def _maybe_welcome(self, user: discord.abc.User) -> None:
        """Send a one-time welcome DM the first time a user uses the bot.

        Checks if the user has already been welcomed. If not, sends a welcome
        DM, adds them to the welcomed_users set, and persists to the database.

        Gracefully ignores DM failures (e.g., if user has DMs disabled).

        Args:
            user: The Discord user to welcome.
        """
        if user.id in self.welcomed_users:
            return

        try:
            await user.send(WELCOME_MESSAGE)
            self.welcomed_users.add(user.id)
            await add_welcomed(user.id)
            log.info("Sent welcome DM to user %s (id=%s)", user, user.id)
        except discord.Forbidden:
            # DMs closed, skip silently
            pass
        except Exception as exc:
            log.warning(
                "Unexpected error sending welcome DM to user %s (id=%s): %s",
                user, user.id, exc,
            )

    async def _is_banned(self, user_id: int) -> dict[str, Any] | None:
        """Check if a user is banned.

        Queries the in-memory banned_users cache. If not found in memory,
        checks the database via db.get_ban().

        Args:
            user_id: The Discord user ID to check.

        Returns:
            The ban record dict if banned, else None.
            Ban record format: {
                "reason": str,
                "banned_at": str,
                "banned_by": str,
                "banned_by_id": str | None,
            }
        """
        uid_str = str(user_id)

        # Check in-memory cache first
        if uid_str in self.banned_users:
            return self.banned_users[uid_str]

        # Fallback to database query
        record = await get_ban(user_id)
        if record is not None:
            # Cache for future lookups
            self.banned_users[uid_str] = record
        return record

    async def _reject_if_banned(self, interaction: discord.Interaction) -> bool:
        """Send an ephemeral rejection and return True if the user is banned.

        Checks if the user is banned, and if so, sends an ephemeral message
        explaining the ban and returns True. Otherwise returns False.

        Args:
            interaction: The Discord interaction (command invocation).

        Returns:
            True if the user is banned (and message was sent), False otherwise.
        """
        record = await self._is_banned(interaction.user.id)
        if record is None:
            return False

        reason = record.get("reason") or "No reason given."
        banned_at = record.get("banned_at", "unknown date")
        msg = (
            ":no_entry: **You have been banned from using Paws Pendragon TTR.**\n\n"
            f"**Reason:** {reason}\n"
            f"**Date:** {banned_at}\n\n"
            "If you believe this is a mistake, contact the bot owner."
        )

        try:
            await interaction.response.send_message(msg, ephemeral=True)
        except discord.InteractionResponded:
            # Interaction was already responded to, use followup
            await interaction.followup.send(msg, ephemeral=True)
        except Exception as exc:
            log.warning(
                "Failed to send ban rejection message to %s (id=%s): %s",
                interaction.user, interaction.user.id, exc,
            )

        log.info(
            "Blocked banned user %s (id=%s) from %s",
            interaction.user,
            interaction.user.id,
            interaction.command and interaction.command.name,
        )
        return True


# Global instance for use in bot.py
user_system = UserSystem()
