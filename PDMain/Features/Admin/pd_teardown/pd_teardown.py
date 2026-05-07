# -*- coding: utf-8 -*-
"""Admin/pd-teardown command handler for Paws Pendragon TTR Discord bot.

Provides the /pd-teardown slash command which stops tracking a guild's live feeds.
Channels are NOT deleted; they remain for manual cleanup by the guild admin.
Logs all teardown events to an append-only audit trail for compliance.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands

if TYPE_CHECKING:
    from typing import Callable

# ── Logging ───────────────────────────────────────────────────────────────────

log = logging.getLogger(__name__)


def _is_guild_admin(user: discord.Member) -> bool:
    """Return True if user has Administrator, Manage Guild, or is the guild owner."""
    return (
        user.guild_permissions.administrator
        or user.guild_permissions.manage_guild
        or user.id == user.guild.owner_id
    )


# ── Constants & paths ─────────────────────────────────────────────────────────

TEARDOWN_LOG: Path = Path(__file__).resolve().parent.parent.parent.parent / "teardown_log.txt"

# ── Type aliases ──────────────────────────────────────────────────────────────

# Function signature for logging teardown events
LogTeardownFn = Callable[[discord.Guild, discord.abc.User], Any]


# ── Teardown logging ──────────────────────────────────────────────────────────

async def log_teardown(guild: discord.Guild, invoker: discord.abc.User) -> None:
    """Append one line to teardown_log.txt for every /pd-teardown invocation.

    Logs guild ID, guild name, owner info, invoker info, and timestamp in
    a structured, parseable format. The log is append-only and never truncated.
    Errors are logged as warnings but do not raise exceptions.

    Args:
        guild: Discord guild being torn down (has id, name, owner_id)
        invoker: User who invoked the /pd-teardown command (has id)
    """
    try:
        owner_id: int = guild.owner_id
        owner_name: str = "unknown"

        # Try to fetch the owner's username; fail gracefully if not found
        try:
            owner = guild.owner or await guild.fetch_member(owner_id)
            owner_name = str(owner)
        except Exception:
            pass

        # Format timestamp in UTC
        ts: str = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        # Build the log entry (multi-line for readability)
        entry: str = (
            f"[{ts}]\n"
            f"  Guild ID    : {guild.id}\n"
            f"  Server Name : {guild.name}\n"
            f"  Owner Name  : {owner_name}\n"
            f"  Owner ID    : {owner_id}\n"
            f"  Invoked by  : {invoker} (id={invoker.id})\n"
            f"{'=' * 48}\n"
        )

        # Write to the log file in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            _write_teardown_log,
            entry,
        )

        log.info("Teardown logged for guild %s (%s)", guild.id, guild.name)

    except Exception as exc:
        log.warning("Could not write teardown log: %s", exc)


def _write_teardown_log(entry: str) -> None:
    """Write teardown entry to log file (blocking operation in executor).

    Args:
        entry: Formatted log entry string to append
    """
    try:
        # Ensure parent directory exists
        TEARDOWN_LOG.parent.mkdir(parents=True, exist_ok=True)

        # Append to file (create if missing)
        with open(TEARDOWN_LOG, "a", encoding="utf-8") as fh:
            fh.write(entry)
    except Exception as exc:
        log.warning("Failed to write teardown log file: %s", exc)


# ── Slash command registration ────────────────────────────────────────────────

def register_pd_teardown(
    bot: Any,
    db: Any,
) -> None:
    """Register the /pd-teardown slash command with the bot.

    This function is called once at bot startup to register the command.
    The command handler removes the guild from state["guilds"], saves state
    to the database, logs the teardown event, and sends an ephemeral response.

    Args:
        bot: Discord bot instance (TTRBot). Must have:
            - self.tree (CommandTree for slash command registration)
            - self.state (dict with "guilds" block for tracking)
            - self._save_state() async method
            - self._guilds_block() method returning state["guilds"]
        db: Database module. Must provide:
            - save_state(state) async function to persist state
    """

    @bot.tree.command(
        name="pd-teardown",
        description="[Server Admin Command] Stop TTR feed tracking. Channels are kept; delete them manually if needed.",
    )
    @app_commands.default_permissions(manage_channels=True, manage_messages=True)
    @app_commands.guild_only()
    async def pd_teardown(interaction: discord.Interaction) -> None:
        """Handle /pd-teardown command invocation.

        Removes the invoking guild from the tracked guilds state, saves the
        updated state to the database, logs the teardown event, and sends
        an ephemeral response to the invoker.

        Permission Requirements:
        - Manage Channels: Required by Discord permissions system
        - Manage Messages: Required by Discord permissions system

        Response:
        - If guild was being tracked: "Stopped tracking this server..."
        - If guild was not tracked: "Nothing to tear down..."

        Args:
            interaction: Discord interaction object from the slash command
        """
        # Verify we're in a guild (should always be true due to @app_commands.guild_only())
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Must be used inside a server.",
                ephemeral=True,
            )
            return

        if not isinstance(interaction.user, discord.Member) or not _is_guild_admin(interaction.user):
            await interaction.response.send_message(
                "Only server administrators can run `/pd-teardown`.",
                ephemeral=True,
            )
            return

        # Remove the guild from tracking state
        guilds_block: dict[str, dict[str, dict[str, Any]]] = bot._guilds_block()
        existed: bool = guilds_block.pop(str(guild.id), None) is not None

        # Save the updated state to database atomically
        try:
            await bot._save_state()
        except Exception as exc:
            log.exception("Failed to save state after teardown: %s", exc)
            await interaction.response.send_message(
                "An error occurred while saving state. Please try again.",
                ephemeral=True,
            )
            return

        # Log the teardown event if the guild was actually tracked
        if existed:
            try:
                await log_teardown(guild, interaction.user)
            except Exception as exc:
                # Log the error but don't fail the command
                log.warning("Failed to log teardown event: %s", exc)

        # Send response to the invoker
        msg: str = (
            "Stopped tracking this server. Channels still exist; delete them manually if you'd like."
            if existed
            else "Nothing to tear down -- this server isn't being tracked."
        )
        await interaction.response.send_message(msg, ephemeral=True)

    # Register completion
    log.info("Registered /pd-teardown command")
