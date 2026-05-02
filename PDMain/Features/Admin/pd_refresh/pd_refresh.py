# -*- coding: utf-8 -*-
"""Admin/pd-refresh feature for Paws Pendragon TTR Discord bot.

Force an immediate data refresh, update all embeds, refresh suit calculator,
and sweep stale messages. Useful for testing or manual updates without waiting
for the scheduled 90-second refresh cycle.

Responsibilities:
  - /pd-refresh slash command handler
  - Call _refresh_once(force_doodles=True) immediately (iterates ALL formatter keys via config.feeds())
  - Call _sweep_guild_stale() for caller's guild only
  - Call _ensure_suit_calculator_pin() for caller's guild
  - Send ephemeral response to user
  - Enforce permission checks: Manage Channels + Manage Messages

Refresh Flow:
  1. User invokes /pd-refresh with Manage Channels + Manage Messages
  2. Send ephemeral response "Refreshing..." (deferred)
  3. Force _refresh_once(force_doodles=True)
     - Fetch all TTR endpoints immediately
     - Iterate over ALL feed keys from config.feeds() (not just information)
     - Update all embeds for all configured feeds
     - Force doodle update even if within 12-hour window
  4. Sweep this guild immediately
     - Delete stale messages
  5. Update suit calculator embeds for this guild
  6. Edit ephemeral response "Complete! All embeds updated."

Force Doodles:
  When force_doodles=True is passed to _refresh_once():
  - Bypass the 12-hour doodle throttle
  - Force fetch and update doodles even if recently updated
  - Purpose: Allow admins to manually refresh doodles without waiting for the scheduled window

Dependencies:
  - Infrastructure/live-feeds (_refresh_once with force_doodles flag)
  - Infrastructure/message-sweep (_sweep_guild_stale)
  - Admin/pd-setup (_ensure_suit_calculator_pin)
  - discord.py library
"""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import discord
from discord import app_commands

if TYPE_CHECKING:
    from bot import TTRBot

log = logging.getLogger("ttr-bot.pd-refresh")

# Cooldown for regular users (bypass if user has Manage Messages permission)
_REFRESH_COOLDOWN = 600  # 10 minutes in seconds


def register_pd_refresh(bot: TTRBot) -> None:
    """Register the /pd-refresh command with the bot's command tree.

    This function sets up the slash command handler that users can invoke
    to force an immediate refresh of TTR feeds, update suit calculators,
    and sweep stale messages from their guild.

    Performs startup assertion: Verifies that FORMATTERS.keys() matches
    config.feeds().keys(). If they diverge, logs a warning (formatter keys
    may be missing or stale).

    Args:
        bot: The TTRBot instance to register the command with.
    """
    # Import here to avoid circular imports
    from Features.Core.formatters.formatters import FORMATTERS

    # Startup assertion: verify formatter keys align with config feed keys
    formatter_keys = set(FORMATTERS.keys())
    config_feed_keys = set(bot.config.feeds().keys())
    if formatter_keys != config_feed_keys:
        log.warning(
            "[pd_refresh] Formatter keys diverged from config.feeds() keys. "
            "Formatters: %s, Config feeds: %s. "
            "This may indicate missing or stale formatter definitions.",
            sorted(formatter_keys),
            sorted(config_feed_keys),
        )

    @bot.tree.command(
        name="pd-refresh",
        description="[Admin Command] Force an immediate refresh of TTR feeds and suit calculator.",
    )
    @app_commands.guild_only()
    async def pd_refresh(interaction: discord.Interaction) -> None:
        """Force an immediate refresh of TTR feeds in this server.

        This command:
          1. Immediately calls _refresh_once(force_doodles=True) to fetch all TTR endpoints
          2. Iterates over ALL feed keys from config.feeds() and updates embeds (not just information)
          3. Bypasses the 12-hour doodle throttle window (force_doodles=True)
          4. Sweeps stale messages from the caller's guild
          5. Refreshes the suit calculator embeds for the caller's guild
          6. Sends an ephemeral response with results

        Permission Requirements:
          - Manage Messages permission recommended (bypasses 10-minute cooldown)
          - Any user can use the command, but non-admin users have a 10-minute cooldown

        Args:
            interaction: The Discord interaction object from the slash command invocation.

        Returns:
            None. Sends an ephemeral response to the user.
        """
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Must be used inside a server.",
                ephemeral=True,
            )
            return

        # Check manage_messages permission to bypass cooldown.
        member = interaction.user
        can_bypass: bool = (
            isinstance(member, discord.Member)
            and member.guild_permissions.manage_messages
        )

        # Enforce cooldown for regular users (not admins)
        if not can_bypass:
            last_used: float = bot._refresh_cooldowns.get(member.id, 0.0)
            remaining: float = _REFRESH_COOLDOWN - (time.time() - last_used)
            if remaining > 0:
                mins, secs = divmod(int(remaining), 60)
                wait: str = f"{mins}m {secs}s" if mins else f"{secs}s"
                await interaction.response.send_message(
                    f"You can use `/pd-refresh` again in **{wait}**.",
                    ephemeral=True,
                )
                return

        # Defer the response so we can edit it later with results
        await interaction.response.defer(ephemeral=True, thinking=True)

        # Record cooldown for this user (only if they don't have bypass permission)
        if not can_bypass:
            bot._refresh_cooldowns[member.id] = time.time()

        refreshed_count: int = 0
        swept_count: int = 0
        suit_calc_updated: bool = False
        error_occurred: bool = False

        try:
            # Step 1: Force _refresh_once(force_doodles=True) for all guilds
            # This updates all embeds and forces doodle update even if within 12-hour window
            log.info(
                "[pd-refresh] User %s (id=%s) requested refresh in guild %s (id=%s)",
                interaction.user,
                interaction.user.id,
                guild.name,
                guild.id,
            )
            try:
                await bot._refresh_once(force_doodles=True)
                refreshed_count = 1  # Flag that refresh was successful
                log.info("[pd-refresh] Forced refresh completed (force_doodles=True)")
            except Exception as exc:
                log.exception(
                    "[pd-refresh] Forced refresh failed for guild %s: %s",
                    guild.id,
                    exc,
                )
                error_occurred = True

            # Step 2: Sweep stale messages for this guild only (not all guilds)
            try:
                swept_count = await bot._sweep_guild_stale(guild.id)
                if swept_count:
                    log.info(
                        "[pd-refresh] Swept %d stale message(s) in guild %s",
                        swept_count,
                        guild.id,
                    )
            except Exception as exc:
                log.exception(
                    "[pd-refresh] Sweep failed for guild %s: %s",
                    guild.id,
                    exc,
                )
                error_occurred = True

            # Step 3: Update suit calculator embeds for this guild
            try:
                calc_name: str = bot.config.channel_suit_calculator
                gs = bot._guild_state(guild.id)
                entry = gs.get("suit_calculator", {})
                channel_id: int = (
                    int(entry.get("channel_id", 0))
                    if isinstance(entry, dict)
                    else 0
                )
                channel: discord.abc.GuildChannel | None = (
                    bot.get_channel(channel_id) if channel_id else None
                )

                # If we can't find the channel by stored ID, search by name
                if not isinstance(channel, discord.TextChannel):
                    channel = discord.utils.get(guild.text_channels, name=calc_name)

                if isinstance(channel, discord.TextChannel):
                    await bot._ensure_suit_calculator_pin(guild.id, channel)
                    await bot._ensure_suit_threads(guild.id, channel)
                    suit_calc_updated = True
                    log.info(
                        "[pd-refresh] Updated suit calculator for guild %s",
                        guild.id,
                    )
                else:
                    log.warning(
                        "[pd-refresh] Suit calculator channel not found in guild %s",
                        guild.id,
                    )
            except Exception as exc:
                log.exception(
                    "[pd-refresh] Suit calculator update failed for guild %s: %s",
                    guild.id,
                    exc,
                )
                error_occurred = True

            # Save state after all updates
            try:
                if refreshed_count or swept_count or suit_calc_updated:
                    await bot._save_state()
            except Exception as exc:
                log.exception("[pd-refresh] Failed to save state: %s", exc)
                error_occurred = True

        except Exception as exc:
            log.exception("[pd-refresh] Unexpected error during refresh: %s", exc)
            error_occurred = True

        # Step 4: Send response to user with results
        response_parts: list[str] = []

        if refreshed_count:
            response_parts.append(
                "Refreshed all live feed embeds with latest TTR data."
            )
        else:
            response_parts.append("Failed to refresh live feeds.")

        if swept_count > 0:
            response_parts.append(f"Cleaned up {swept_count} old message(s).")

        if suit_calc_updated:
            response_parts.append("Updated suit calculator embeds.")

        if error_occurred:
            response_parts.append(
                "\n:warning: Some operations encountered errors -- check console logs."
            )

        response_text: str = " ".join(response_parts)
        try:
            await interaction.followup.send(response_text, ephemeral=True)
        except Exception as exc:
            log.exception(
                "[pd-refresh] Failed to send response to user: %s", exc
            )
            try:
                await interaction.followup.send(
                    "Refresh completed, but failed to send response. Check console logs.",
                    ephemeral=True,
                )
            except Exception:
                pass
