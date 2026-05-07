# -*- coding: utf-8 -*-
"""User/doodleinfo feature for Paws Pendragon TTR Discord bot.

Send a one-time welcome DM to first-time users, check ban status, fetch the
complete doodle list from the TTR API with trait ratings and a buying guide,
format it into embeds, and send via DM. Works as a User App (no server
membership required).

Responsibilities:
  - /doodleinfo slash command handler
  - Ban check before any processing (_reject_if_banned)
  - First-time welcome DM (_maybe_welcome)
  - Fetch doodles from TTR API
  - Format doodles via format_doodles(data) → list[discord.Embed]
  - Send embeds to user via DM
  - Handle DM failures gracefully (Forbidden, network errors)
  - Ephemeral response in channel ("Sent to your DMs" or "DMs closed" message)

Command Flow:
  1. User invokes /doodleinfo (anywhere: server, DM, group, User App)
  2. Check ban status via _reject_if_banned(interaction)
  3. Defer ephemeral response
  4. Send welcome DM if first-time via _maybe_welcome(user)
  5. Fetch doodles endpoint from TTR API
  6. Format via format_doodles(data) → list[discord.Embed]
  7. DM embeds to user via user.send(embeds=...)
  8. Send ephemeral response: "Sent doodle info and buying guide to your DMs!"
  9. If DM blocked: "I tried to send the info to your DMs, but they appear
     to be closed. Try enabling DMs and use /helpme for command list."

User App Support:
  - @app_commands.allowed_installs(guilds=True, users=True)
  - @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
  - Works in servers, DMs, group chats, and personal Discord account

Error Handling:
  - TTR API 503 (maintenance) — log warning, skip fetch, inform user
  - DM blocked (Forbidden) — log warning, send ephemeral fallback message
  - Network errors (timeout, connection) — log exception, inform user
  - Ban check — reject before any work, send ephemeral message

Dependencies:
  - Core/formatters (format_doodles)
  - Core/ttr-api (TTRApiClient)
  - Infrastructure/user-system (_reject_if_banned, _maybe_welcome)
  - discord.py library

Key Design Patterns:
  1. **DM-first, fallback to ephemeral** — embeds go to DM; if blocked, ephemeral
  2. **Graceful failure** — DM failure doesn't prevent command success
  3. **Ban check first** — reject before doing any work
  4. **Welcome DM** — one per user, sent on first command use
  5. **Comprehensive logging** — info for success, warning/exception for failures
  6. **Full type hints** — throughout the module for clarity and IDE support
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

if TYPE_CHECKING:
    from bot import TTRBot

log = logging.getLogger("ttr-bot.doodleinfo")


def register_doodleinfo(bot: TTRBot) -> None:
    """Register the /doodleinfo command with the bot's command tree.

    This function sets up the slash command handler that users can invoke
    to fetch and view the complete Toontown doodle list with trait ratings
    and a buying guide sent directly to their DMs. Works as a User App
    (no server membership required).

    Args:
        bot: The TTRBot instance to register the command with.
    """

    @bot.tree.command(
        name="doodleinfo",
        description="[User Command] See the current Toontown doodle list with trait ratings.",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def doodleinfo(interaction: discord.Interaction) -> None:
        """Fetch and send the complete doodle list to the user via DM.

        This command:
          1. Checks if the user is banned (rejects if true)
          2. Defers the response (shows "thinking...")
          3. Sends a welcome DM to first-time users
          4. Fetches the doodles endpoint from the TTR API
          5. Formats the data into embeds via format_doodles()
          6. Sends the embeds to the user's DMs
          7. Sends an ephemeral response: "Check your DMs!"
          8. If DM blocked: sends fallback ephemeral message

        The command is compatible with User App installs (works anywhere:
        servers, DMs, group chats, personal Discord account).

        Args:
            interaction: The Discord interaction object from the slash command
                        invocation. Can occur in servers, DMs, or groups.

        Returns:
            None. Sends embeds to user DM, plus ephemeral response in channel.
        """
        # Step 1: Check ban status before doing any work
        if await bot._reject_if_banned(interaction):
            return

        # Step 2: Defer the response with ephemeral=True and thinking=True
        await interaction.response.defer(ephemeral=True, thinking=True)

        # Step 3: Send welcome DM to first-time users (graceful failure if DMs blocked)
        await bot._maybe_welcome(interaction.user)

        # Step 4: Check API client is ready
        if bot._api is None:
            await interaction.followup.send(
                "API client not ready yet -- try again in a moment.",
                ephemeral=True,
            )
            log.warning(
                "[doodleinfo] API client not ready for user %s (id=%s)",
                interaction.user,
                interaction.user.id,
            )
            return

        # Step 5: Fetch doodles from TTR API
        doodle_data: dict | None = None
        try:
            doodle_data = await bot._api.fetch("doodles")
            log.info(
                "[doodleinfo] Fetched doodles endpoint for user %s (id=%s)",
                interaction.user,
                interaction.user.id,
            )
        except Exception as exc:
            log.exception(
                "[doodleinfo] Failed to fetch doodles for user %s (id=%s): %s",
                interaction.user,
                interaction.user.id,
                exc,
            )
            await interaction.followup.send(
                "Failed to fetch doodle data -- the API may be under maintenance. "
                "Try again in a moment.",
                ephemeral=True,
            )
            return

        # Step 6: Format doodles into embeds
        try:
            from formatters import format_doodles

            embeds: list[discord.Embed] = format_doodles(doodle_data)
            if not embeds:
                await interaction.followup.send(
                    "No doodle data available at this time.",
                    ephemeral=True,
                )
                log.warning(
                    "[doodleinfo] format_doodles returned empty list for user %s (id=%s)",
                    interaction.user,
                    interaction.user.id,
                )
                return
            log.info(
                "[doodleinfo] Formatted %d embed(s) for user %s (id=%s)",
                len(embeds),
                interaction.user,
                interaction.user.id,
            )
        except Exception as exc:
            log.exception(
                "[doodleinfo] Failed to format doodles for user %s (id=%s): %s",
                interaction.user,
                interaction.user.id,
                exc,
            )
            await interaction.followup.send(
                "Failed to format doodle data. Try again later.",
                ephemeral=True,
            )
            return

        # Step 7: Send embeds to user's DM
        dm_sent: bool = False
        try:
            await interaction.user.send(embeds=embeds)
            dm_sent = True
            log.info(
                "[doodleinfo] Sent %d doodle embed(s) to user %s (id=%s) via DM",
                len(embeds),
                interaction.user,
                interaction.user.id,
            )
        except discord.Forbidden:
            log.warning(
                "[doodleinfo] DM blocked for user %s (id=%s) -- user has DMs disabled",
                interaction.user,
                interaction.user.id,
            )
        except discord.HTTPException as exc:
            log.exception(
                "[doodleinfo] HTTP error sending DM to user %s (id=%s): %s",
                interaction.user,
                interaction.user.id,
                exc,
            )
        except Exception as exc:
            log.exception(
                "[doodleinfo] Unexpected error sending DM to user %s (id=%s): %s",
                interaction.user,
                interaction.user.id,
                exc,
            )

        # Step 8: Send ephemeral response (success or fallback)
        if dm_sent:
            await interaction.followup.send(
                "Sent doodle info and buying guide to your DMs!",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "I tried to send the info to your DMs, but they appear to be closed. "
                "Try enabling DMs and use /helpme for command list.",
                ephemeral=True,
            )
