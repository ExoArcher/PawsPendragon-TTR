# -*- coding: utf-8 -*-
"""Paws Pendragon TTR /ttrinfo user command.

Slash command: /ttrinfo
Description: DM current TTR game state (districts, invasions, field offices, Silly Meter).

Features:
- Fetches population, fieldoffices, and sillymeter endpoints from TTR API
- Calls format_information() to build embeds
- Sends embeds to user via DM
- Sends ephemeral response in channel
- Handles DM failures gracefully
- Checks ban status before processing
- Sends welcome DM on first use
- Works as User App (no guild context required)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import discord
from discord import app_commands

from ...Core.formatters.formatters import format_information, format_sillymeter
from ...Core.ttr_api.ttr_api import TTRApiClient

log = logging.getLogger("ttr-bot.ttrinfo")


async def ttrinfo_command(
    bot: Any,
    interaction: discord.Interaction,
) -> None:
    """Slash command handler for /ttrinfo.

    Fetches TTR API data (population, fieldoffices, sillymeter) and sends
    formatted embeds to user's DM. Works in servers, DMs, group chats, and User App.

    Args:
        bot: TTRBot instance with API client and ban/welcome system
        interaction: Discord interaction object

    Returns:
        None (sends response via interaction)
    """
    # Check if user is banned
    if await bot._reject_if_banned(interaction):
        return

    # Defer the response with ephemeral flag (thinking state)
    await interaction.response.defer(ephemeral=True, thinking=True)

    # Send welcome DM if first-time user
    await bot._maybe_welcome(interaction.user)

    # Verify API client is ready
    if bot._api is None:
        await interaction.followup.send(
            "API client not ready yet -- try again in a moment.",
            ephemeral=True,
        )
        log.warning("ttrinfo invoked but API client is None")
        return

    # Fetch all required endpoints in parallel
    log.info("Fetching TTR data for /ttrinfo user=%s (id=%s)", interaction.user, interaction.user.id)
    results = await asyncio.gather(
        bot._api.fetch("population"),
        bot._api.fetch("fieldoffices"),
        bot._api.fetch("sillymeter"),
        return_exceptions=True,
    )

    population = None if isinstance(results[0], BaseException) else results[0]
    fieldoffices = None if isinstance(results[1], BaseException) else results[1]
    sillymeter = None if isinstance(results[2], BaseException) else results[2]

    # Check for API failures (503 Maintenance, timeouts, etc)
    if all(x is None for x in [population, fieldoffices, sillymeter]):
        await interaction.followup.send(
            "TTR API is currently under maintenance. Try again in a few minutes.",
            ephemeral=True,
        )
        log.warning("ttrinfo: all endpoints failed for user=%s", interaction.user.id)
        return

    # Build embeds using the formatter
    info_embeds: list[discord.Embed] = format_information(
        invasions=None,  # not needed for /ttrinfo
        population=population,
        fieldoffices=fieldoffices,
    )
    silly_embed = format_sillymeter(sillymeter)

    # Send embeds to user's DM
    dm_success: bool = True
    try:
        for embed in info_embeds:
            await interaction.user.send(embed=embed)
        await interaction.user.send(embed=silly_embed)
        log.info("Sent ttrinfo DM to user=%s (id=%s)", interaction.user, interaction.user.id)
    except discord.Forbidden:
        dm_success = False
        log.info("ttrinfo: user=%s (id=%s) has DMs closed", interaction.user, interaction.user.id)
    except discord.HTTPException as exc:
        dm_success = False
        log.warning("ttrinfo: failed to send DM to user=%s: %s", interaction.user.id, exc)

    # Send ephemeral response in channel
    if dm_success:
        await interaction.followup.send(
            "Sent info about districts, invasions, and silly meter status to your DMs!",
            ephemeral=True,
        )
    else:
        await interaction.followup.send(
            "I tried to send to your DMs, but they appear to be closed. Try enabling DMs.",
            ephemeral=True,
        )


def register_ttrinfo(bot: Any) -> None:
    """Register the /ttrinfo command with the bot's command tree.

    Args:
        bot: TTRBot instance with command tree
    """
    @bot.tree.command(
        name="ttrinfo",
        description="[User Command] See current Toontown district, invasion, field office, and Silly Meter info.",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def ttrinfo(interaction: discord.Interaction) -> None:
        """Slash command: /ttrinfo

        Fetches and DMs current TTR game state to the user.
        - Population of all districts
        - Active field office invasions
        - Silly Meter status and upcoming rewards

        Works anywhere: servers, DMs, group chats, and User App personal account.
        """
        await ttrinfo_command(bot, interaction)

    log.info("Registered /ttrinfo command")
