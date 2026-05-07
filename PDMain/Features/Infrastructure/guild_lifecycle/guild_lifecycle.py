"""Guild lifecycle management for Paws Pendragon TTR bot.

Handles:
- Guild join/leave events with allowlist enforcement
- Per-guild command syncing to prevent Discord UI duplication
- State cleanup for departed guilds
- Closed-access messaging for non-allowlisted guilds
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import discord
from discord import app_commands

from ...Core.config.config import Config
from ...Core.db import db
from .. import cache_manager

log = logging.getLogger("ttr-bot.guild-lifecycle")

# Shown to any guild owner whose server fails the allowlist check.
CLOSED_ACCESS_MSG = (
    "Hello! Thank you for your enthusiasm to have me join your community! "
    "At this time I am only in closed access -- please DM **ExoArcher** on "
    "Discord (user ID `310233741354336257`) to request access."
)


class GuildLifecycleManager:
    """Manages bot guild lifecycle: join, leave, state cleanup, and command syncing."""

    def __init__(self, bot: discord.AutoShardedClient, config: Config) -> None:
        self.bot = bot
        self.config = config

    def _runtime_allowlist(self) -> set[int]:
        """Return the runtime allowlist from bot state."""
        if not hasattr(self.bot, 'state'):
            return set()
        return {int(x) for x in self.bot.state.get("allowlist", [])}

    def effective_allowlist(self) -> set[int]:
        """Return the effective allowlist (env + runtime union)."""
        return set(self.config.guild_allowlist) | self._runtime_allowlist()

    def is_guild_allowed(self, guild_id: int) -> bool:
        """Check if a guild is on the effective allowlist.

        Returns True if guild_id is in either the environment
        GUILD_ALLOWLIST or the runtime allowlist from the database.
        """
        return guild_id in self.effective_allowlist()

    def _guilds_block(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Return the guilds block from bot state, creating if needed."""
        if not hasattr(self.bot, 'state'):
            return {}
        return self.bot.state.setdefault("guilds", {})

    async def _sync_commands_to_guild(self, guild: discord.Guild) -> None:
        """Deprecated: Commands are now synced globally in setup_hook."""
        pass

    async def _notify_and_leave(self, guild: discord.Guild) -> None:
        """Send closed-access DM to guild owner, then leave the guild.

        Called when the bot joins a non-allowlisted guild or is already
        in one when on_ready runs.
        """
        try:
            owner = guild.owner or await guild.fetch_member(guild.owner_id)
            if owner is not None:
                await owner.send(CLOSED_ACCESS_MSG)
        except Exception as e:
            log.debug("Could not DM owner of %s: %s", guild.name, e)
        try:
            await guild.leave()
        except Exception as e:
            log.warning("Failed to leave guild %s: %s", guild.id, e)

    async def _add_guild_to_allowlist_atomic(
        self, guild_id: int, db_path: Path | None = None
    ) -> bool:
        """Atomically add guild to allowlist (DB first, then cache).

        Writes to database first (source of truth), then updates cache only
        if DB write succeeds. This prevents cache/DB divergence if the DB
        write fails partway through.

        Args:
            guild_id: Discord guild ID to add.
            db_path: Optional path to SQLite database. If None, uses default.

        Returns:
            True if both DB and cache updated successfully, False otherwise.
        """
        try:
            # Write to DB first (source of truth)
            await db.add_guild_to_allowlist(guild_id, db_path or db.DB_PATH)

            # Only update cache if DB write succeeds
            cache_manager.GUILD_ALLOWLIST.add(guild_id)

            log.info("Added guild %s to allowlist (DB + cache)", guild_id)
            return True

        except Exception as e:
            log.error(
                "Failed to add guild %s to allowlist: %s. Cache NOT updated.",
                guild_id, e,
            )
            return False

    async def on_ready(self) -> None:
        """Sync commands per-guild, enforce allowlist, and cleanup departed guilds.

        This is called when the bot connects to Discord (on startup or reconnect).
        It ensures:
        1. Non-allowlisted guilds are left with owner notification
        2. Guild state for departed guilds is pruned
        3. Commands are synced per-guild for all remaining guilds
        """
        log.info(
            "Guild lifecycle on_ready: %d live guild(s); env-allowlist=%d; runtime-allowlist=%d",
            len(self.bot.guilds), len(self.config.guild_allowlist),
            len(self._runtime_allowlist()),
        )

        # First pass: leave non-allowlisted guilds and notify owners
        for guild in list(self.bot.guilds):
            if not self.is_guild_allowed(guild.id):
                log.warning("Leaving non-allowlisted guild %s (id=%s)", guild.name, guild.id)
                await self._notify_and_leave(guild)

        # Second pass: prune state for departed guilds
        live_ids = {str(g.id) for g in self.bot.guilds}
        for gid in list(self._guilds_block().keys()):
            if gid not in live_ids:
                log.info("Pruning state for departed guild %s", gid)
                self._guilds_block().pop(gid, None)

        # Third pass: sync commands for all remaining allowlisted guilds
        for guild in list(self.bot.guilds):
            if not self.is_guild_allowed(guild.id):
                continue
            await self._sync_commands_to_guild(guild)
            log.info("Guild %s (%s) ready for service", guild.name, guild.id)

        # Persist state changes (pruned guilds, etc.)
        if hasattr(self.bot, '_save_state'):
            await self.bot._save_state()

    async def on_guild_join(self, guild: discord.Guild) -> None:
        """Handle bot being added to a guild.

        Checks the allowlist:
        - If allowed: atomically add to DB+cache, then sync commands
        - If not allowed: send owner DM and leave immediately

        Uses _add_guild_to_allowlist_atomic() to prevent race conditions
        where cache diverges from DB if write fails.
        """
        if not self.is_guild_allowed(guild.id):
            log.warning("Refusing to join non-allowlisted guild %s (id=%s)", guild.name, guild.id)
            await self._notify_and_leave(guild)
            return

        # Guild is in allowlist. Atomically add to DB+cache (if not already there).
        # This prevents cache/DB divergence if either write fails.
        success = await self._add_guild_to_allowlist_atomic(guild.id)
        if not success:
            log.warning(
                "Failed to add guild %s to allowlist atomically. Sending error and leaving.",
                guild.id,
            )
            try:
                owner = guild.owner or await guild.fetch_member(guild.owner_id)
                if owner is not None:
                    await owner.send(
                        "Unable to add your guild to the allowlist due to a database error. "
                        "Please contact the bot administrator."
                    )
            except Exception as e:
                log.debug("Could not DM owner of %s: %s", guild.name, e)
            try:
                await guild.leave()
            except Exception as e:
                log.warning("Failed to leave guild %s: %s", guild.id, e)
            return

        log.info("Joined and allowlisted guild %s (id=%s)", guild.name, guild.id)
        await self._sync_commands_to_guild(guild)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        """Handle bot being removed from a guild.

        Atomically removes all guild data from DB and clears in-memory state.
        """
        log.info(
            "[lifecycle] Removed from guild '%s' (id=%d); cleaning DB + state",
            guild.name, guild.id,
        )
        try:
            await db.delete_guild_completely(guild.id)
            log.info(
                "[lifecycle] DB cleanup complete for guild '%s' (id=%d)",
                guild.name, guild.id,
            )
        except Exception as exc:
            log.error(
                "[lifecycle] Failed to delete DB data for guild '%s' (id=%d): %s",
                guild.name, guild.id, exc
            )

        # Clear in-memory state
        self._guilds_block().pop(str(guild.id), None)
        if hasattr(self.bot, 'state'):
            runtime = self.bot.state.setdefault("allowlist", [])
            if guild.id in runtime:
                runtime.remove(guild.id)

        if hasattr(self.bot, '_save_state'):
            await self.bot._save_state()


def setup_guild_lifecycle(bot: discord.AutoShardedClient, config: Config) -> GuildLifecycleManager:
    """Initialize and return a GuildLifecycleManager instance.

    This should be called during bot setup to install guild lifecycle handlers.
    Returns the manager instance for testing or direct method access.
    """
    manager = GuildLifecycleManager(bot, config)

    # Bind event handlers to the bot
    @bot.event
    async def on_ready() -> None:
        await manager.on_ready()

    @bot.event
    async def on_guild_join(guild: discord.Guild) -> None:
        await manager.on_guild_join(guild)

    @bot.event
    async def on_guild_remove(guild: discord.Guild) -> None:
        await manager.on_guild_remove(guild)

    return manager
