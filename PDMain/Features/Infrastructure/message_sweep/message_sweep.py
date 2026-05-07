# -*- coding: utf-8 -*-
"""Message sweep feature: periodically clean up stale bot messages.

Runs every 15 minutes to delete orphaned bot messages that are no longer
being tracked by the state. Handles missing channels and permission errors
gracefully, ensuring the sweep is safe to run across multiple guilds.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import discord
from discord.ext import tasks

from Features.Core.config.constants import MESSAGE_SWEEP_INTERVAL_MINUTES

if TYPE_CHECKING:
    from bot import TTRBot

log = logging.getLogger("message-sweep")


class MessageSweep:
    """Background task for sweeping stale bot messages."""

    def __init__(self, bot: TTRBot) -> None:
        """Initialize the message sweep task.

        Args:
            bot: TTRBot instance with state and configuration.
        """
        self.bot = bot

    def start_sweep_loop(self) -> None:
        """Start the sweep loop if not already running."""
        if not self._sweep_loop.is_running():
            self._sweep_loop.start()
            log.info("Message sweep loop started")

    def stop_sweep_loop(self) -> None:
        """Stop the sweep loop if running."""
        if self._sweep_loop.is_running():
            self._sweep_loop.stop()
            log.info("Message sweep loop stopped")

    @tasks.loop(minutes=MESSAGE_SWEEP_INTERVAL_MINUTES)
    async def _sweep_loop(self) -> None:
        """Sweep stale bot messages from all tracked channels every MESSAGE_SWEEP_INTERVAL_MINUTES minutes.

        For each guild in the state, iterate through tracked channels and delete
        any bot messages that are not in the known message ID set.
        """
        await self._sweep_once()

    @_sweep_loop.before_loop
    async def _before_sweep_loop(self) -> None:
        """Wait for the bot to be ready before starting the sweep loop."""
        await self.bot.wait_until_ready()

    async def _sweep_once(self) -> None:
        """Perform a single sweep iteration across all tracked guilds."""
        guilds_block = self._guilds_block()
        total_swept = 0

        for guild_id_str in list(guilds_block.keys()):
            try:
                guild_id = int(guild_id_str)
            except ValueError:
                continue

            if not self.bot.is_guild_allowed(guild_id) or self.bot.get_guild(guild_id) is None:
                continue

            guild = self.bot.get_guild(guild_id)
            guild_name = guild.name if guild else guild_id_str

            try:
                swept = await self._sweep_guild(guild_id)
                total_swept += swept
                if swept:
                    log.info(
                        "[sweep][%s][%d] Removed %d stale message(s)",
                        guild_name, guild_id, swept,
                    )
            except discord.Forbidden:
                log.warning(
                    "[sweep][%s][%d] Missing permissions; skipping guild sweep",
                    guild_name, guild_id,
                )
            except discord.HTTPException as exc:
                log.warning(
                    "[sweep][%s][%d] HTTP %s during sweep; will retry next cycle",
                    guild_name, guild_id, exc.status,
                )
            except Exception:
                log.exception("[sweep][%s][%d] Unexpected error during sweep", guild_name, guild_id)

    async def _sweep_guild(self, guild_id: int) -> int:
        """Sweep messages in a single guild across all tracked channels.

        Args:
            guild_id: The Discord guild ID to sweep.

        Returns:
            Total number of messages deleted in this guild.
        """
        total = 0
        seen: set[int] = set()
        guild_state = self._guild_state(guild_id)
        guild = self.bot.get_guild(guild_id)
        guild_name = guild.name if guild else str(guild_id)

        # Iterate through all feed entries (information, doodles, suit_calculator)
        for entry in guild_state.values():
            if not isinstance(entry, dict):
                continue

            channel_id = int(entry.get("channel_id", 0))
            if channel_id in seen or channel_id == 0:
                continue

            seen.add(channel_id)

            # Get the channel from the bot's cache
            channel = self.bot.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                log.debug(
                    "[sweep][%s][%d] Channel %d not found or not TextChannel",
                    guild_name, guild_id, channel_id
                )
                continue

            # Get the set of message IDs to keep in this channel
            keep_ids = self._channel_keep_ids(guild_id, channel_id)

            # Sweep this channel
            swept = await self._sweep_channel(channel, keep_ids=keep_ids)
            total += swept

        return total

    async def _sweep_channel(
        self,
        channel: discord.TextChannel,
        *,
        keep_ids: set[int],
        history_limit: int = 200,
    ) -> int:
        """Sweep stale messages from a single channel.

        Deletes bot messages that are NOT in the keep_ids set. Only deletes
        messages posted by the bot itself. Handles missing channels and
        permission errors gracefully.

        Args:
            channel: The Discord text channel to sweep.
            keep_ids: Set of message IDs that should NOT be deleted.
            history_limit: Maximum number of messages to examine (default 200).

        Returns:
            Number of messages deleted.
        """
        if self.bot.user is None:
            return 0

        bot_id = self.bot.user.id
        deleted = 0

        try:
            async for msg in channel.history(limit=history_limit):
                # Only consider messages posted by the bot
                if msg.author.id != bot_id or msg.id in keep_ids:
                    continue

                # Delete the stale message
                try:
                    await msg.delete()
                    deleted += 1
                except discord.NotFound:
                    # Message was already deleted by someone else
                    pass
                except discord.Forbidden:
                    # Bot doesn't have Delete permission
                    log.debug(
                        "No Delete permission in #%s (%d); stopping sweep of channel",
                        channel.name, channel.id
                    )
                    break
                except discord.HTTPException as exc:
                    # Rate limit or other transient error; log and continue
                    log.debug(
                        "HTTPException while deleting in #%s: %s",
                        channel.name, exc
                    )
                    continue

        except discord.Forbidden:
            # Can't read message history
            log.debug(
                "No Read Message History permission in #%s (%d); skipping sweep",
                channel.name, channel.id
            )
        except discord.HTTPException as exc:
            log.debug(
                "HTTPException while reading history in #%s: %s",
                channel.name, exc
            )

        return deleted

    # ── State access helpers ──────────────────────────────────────────────────

    def _guilds_block(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Return the guilds block from the bot's state."""
        return self.bot.state.setdefault("guilds", {})

    def _guild_state(self, guild_id: int) -> dict[str, dict[str, Any]]:
        """Return the state dict for a specific guild."""
        return self._guilds_block().setdefault(str(guild_id), {})

    def _channel_keep_ids(self, guild_id: int, channel_id: int) -> set[int]:
        """Return the set of message IDs that should NOT be deleted in a channel.

        Builds a set of known message IDs by iterating through the guild state
        and collecting all message IDs for this channel. Also includes announcement
        message IDs that expire later.

        Args:
            guild_id: The guild ID.
            channel_id: The channel ID.

        Returns:
            Set of message IDs to keep (known IDs).
        """
        keep: set[int] = set()
        guild_state = self._guild_state(guild_id)

        # Collect message IDs from feed entries in this guild
        for entry in guild_state.values():
            if not isinstance(entry, dict):
                continue

            if int(entry.get("channel_id", 0)) != channel_id:
                continue

            # Add all message IDs from this feed entry
            for mid in entry.get("message_ids", []) or []:
                try:
                    keep.add(int(mid))
                except (TypeError, ValueError):
                    pass

        # Protect suit-thread starter messages in #suit-calc
        suit_calc = guild_state.get("suit_calculator", {})
        if isinstance(suit_calc, dict) and int(suit_calc.get("channel_id", 0)) == channel_id:
            suit_threads = guild_state.get("suit_threads", {})
            if isinstance(suit_threads, dict):
                for faction_data in suit_threads.values():
                    if isinstance(faction_data, dict):
                        tid = faction_data.get("thread_id")
                        if tid:
                            try:
                                keep.add(int(tid))
                            except (TypeError, ValueError):
                                pass

        # Also keep announcement messages in this channel
        for record in self._announcements():
            if int(record.get("channel_id", 0)) == channel_id:
                try:
                    keep.add(int(record.get("message_id", 0)))
                except (TypeError, ValueError):
                    pass

        return keep

    def _announcements(self) -> list[dict[str, Any]]:
        """Return the announcements list from the bot's state."""
        return self.bot.state.setdefault("announcements", [])


async def register_message_sweep(bot: TTRBot) -> None:
    """Register the message sweep feature with the bot.

    This function is called from bot.py to set up the message sweep task.

    Args:
        bot: The TTRBot instance to register with.
    """
    sweep = MessageSweep(bot)
    sweep.start_sweep_loop()
    log.info("Message sweep feature registered")
