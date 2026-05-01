# -*- coding: utf-8 -*-
"""Helpme command handler for Paws Pendragon TTR.

This module provides the `/helpme` slash command, which sends users
a comprehensive list of available commands via DM or falls back to
an ephemeral channel message if DMs are blocked.

Features
--------
- DM-first approach: attempts to send embed to user DMs
- Graceful fallback: if DM blocked, sends ephemeral message in channel
- Ban-aware: checks user ban status before processing
- Admin-aware: shows admin commands only to admin users
- User App compatible: works anywhere (DM, server, group chat)
- No network I/O: instant response with static data
- Comprehensive logging: logs all operations

Exports
-------
    register_helpme(bot) -> None
        Register the /helpme slash command with the bot.

Usage
-----
In bot.py:

    from Features.User.helpme.helpme import register_helpme

    class TTRBot(...):
        def _register_commands(self) -> None:
            # ... other commands ...
            register_helpme(self)
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import discord
from discord import app_commands

if TYPE_CHECKING:
    from bot import TTRBot

log = logging.getLogger("ttr-bot.helpme")


def _build_command_list_embed(is_admin: bool) -> discord.Embed:
    """Build the command list embed with user commands and optional admin commands.

    Args
    ----
    is_admin : bool
        If True, includes admin commands (/pd-setup, /pd-refresh, /pd-teardown).

    Returns
    -------
    discord.Embed
        Formatted embed with command descriptions.
    """
    embed = discord.Embed(
        title="Paws Pendragon TTR — Commands",
        description=(
            ":warning: *This bot is currently in Early Access — features are still "
            "being added and things may change.*"
        ),
        color=0x9124F2,
    )

    # User commands (all users)
    embed.add_field(
        name="/ttrinfo",
        value="Current district populations, cog invasions, field offices, and Silly Meter status — sent to your DMs.",
        inline=False,
    )
    embed.add_field(
        name="/doodleinfo",
        value="Current doodle list with trait ratings and a buying guide — sent to your DMs.",
        inline=False,
    )
    embed.add_field(
        name="/calculate",
        value="Cog suit merit/stock options/jury notices calculator — interactive dropdown flow.",
        inline=False,
    )
    embed.add_field(
        name="/beanfest",
        value="Weekly Beanfest event schedule — sent to your DMs.",
        inline=False,
    )
    embed.add_field(
        name="/invite",
        value="Get links to add the bot to a server or your personal account.",
        inline=False,
    )
    embed.add_field(
        name="/helpme",
        value="Show this message.",
        inline=False,
    )

    # Admin commands (only if user is admin)
    if is_admin:
        embed.add_field(
            name="​",  # Zero-width space separator
            value="",
            inline=False,
        )
        embed.add_field(
            name="/pd-setup",
            value="**[Admin]** Create the TTR feed channels in this server and start tracking them.",
            inline=False,
        )
        embed.add_field(
            name="/pd-refresh",
            value="**[Admin]** Force an immediate refresh of TTR feeds in this server.",
            inline=False,
        )
        embed.add_field(
            name="/pd-teardown",
            value="**[Admin]** Stop TTR feed tracking in this server. Channels are kept; delete them manually if needed.",
            inline=False,
        )

    return embed


async def _send_help_dm(
    user: discord.abc.User,
    interaction: discord.Interaction,
    is_admin: bool,
) -> bool:
    """Attempt to send help embed via DM to user.

    Args
    ----
    user : discord.abc.User
        The user to send the DM to.
    interaction : discord.Interaction
        The interaction context (used for followup if DM succeeds).
    is_admin : bool
        Whether to show admin commands in the embed.

    Returns
    -------
    bool
        True if DM was sent successfully, False if blocked or failed.
    """
    embed = _build_command_list_embed(is_admin)
    try:
        await user.send(embed=embed)
        log.info("Sent /helpme DM to user %s (id=%s)", user, user.id)
        return True
    except discord.Forbidden:
        log.info("DM blocked for /helpme user %s (id=%s) -- will use ephemeral fallback", user, user.id)
        return False
    except Exception as exc:
        log.warning("Failed to send /helpme DM to user %s: %s", user, exc)
        return False


def register_helpme(bot: TTRBot) -> None:
    """Register the /helpme slash command with the bot.

    This function should be called during bot initialization in the
    _register_commands() method. It registers a slash command that:

    1. Checks if the user is banned (rejects if so)
    2. Determines if user is admin (to show admin commands)
    3. Attempts to send help embed via DM
    4. Falls back to ephemeral channel message if DM blocked
    5. Sends user-facing response ("Check your DMs!" or "See below")

    Args
    ----
    bot : TTRBot
        The bot instance to register the command with.
    """

    @bot.tree.command(
        name="helpme",
        description="[User Command] Show available commands for the Paws Pendragon app.",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def helpme(interaction: discord.Interaction) -> None:
        """Show help embed with available commands.

        Flow:
        1. Check ban status (reject if banned)
        2. Determine admin status (check manage_messages permission if in guild)
        3. Try to send help via DM
        4. If DM blocked, send ephemeral message in channel
        5. Respond to interaction (deferred or immediate)
        """
        # Check ban status
        if await bot._reject_if_banned(interaction):
            return

        # Determine if user is admin
        is_admin = False
        if isinstance(interaction.user, discord.Member) and interaction.guild:
            is_admin = interaction.user.guild_permissions.manage_messages

        # Try DM-first approach
        dm_sent = await _send_help_dm(interaction.user, interaction, is_admin)

        # Send user-facing response
        if dm_sent:
            try:
                await interaction.response.send_message(
                    "Check your DMs! 📬",
                    ephemeral=True,
                )
            except discord.InteractionResponded:
                # Response already sent (shouldn't happen, but handle gracefully)
                pass
            except Exception as exc:
                log.warning("Could not send /helpme confirmation to user %s: %s", interaction.user, exc)
        else:
            # DM blocked or failed -- send ephemeral embed in channel
            embed = _build_command_list_embed(is_admin)
            try:
                await interaction.response.send_message(
                    embed=embed,
                    ephemeral=True,
                )
                log.info("Sent /helpme ephemeral embed to user %s (id=%s) in channel", interaction.user, interaction.user.id)
            except Exception as exc:
                log.warning("Could not send /helpme ephemeral embed to user %s: %s", interaction.user, exc)
                # Last resort: send plain text error
                try:
                    await interaction.response.send_message(
                        "Could not display help message. Please enable DMs from server members and try again.",
                        ephemeral=True,
                    )
                except Exception:
                    pass
