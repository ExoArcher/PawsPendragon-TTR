# -*- coding: utf-8 -*-
"""
Paws Pendragon pd-setup admin command.

Initializes a guild for live feed tracking. Creates the "PendragonTTR"
category + 3 channels (#tt-info, #tt-doodles, #suit-calc),
posts placeholder embeds, and stores message IDs in the database for later
in-place editing by the refresh loop.

Exported:
    register_pd_setup(bot) -- Register the /pd-setup command.
"""
from __future__ import annotations

import logging
from typing import Any

import discord
from discord import app_commands

from ...Core.config.config import Config
from ...Core.db.db import save_state
from ...User.calculate.calculate import build_faction_thread_embeds, build_suit_calculator_embeds
from ...User.doodlesearch.doodlesearch import cleanup_doodle_search_threads

log = logging.getLogger("ttr-bot.pd-setup")


def _is_guild_admin(user: discord.Member) -> bool:
    """Return True if user has Administrator, Manage Guild, or is the guild owner."""
    return (
        user.guild_permissions.administrator
        or user.guild_permissions.manage_guild
        or user.id == user.guild.owner_id
    )


# Faction order and thread names
_FACTION_ORDER = ("sellbot", "cashbot", "lawbot", "bossbot")
_FACTION_THREAD_NAMES = {
    "sellbot": "Sellbot Promo Chart",
    "cashbot": "Cashbot Promo Chart",
    "lawbot":  "Lawbot Promo Chart",
    "bossbot": "Bossbot Promo Chart",
}


async def _ensure_category(
    guild: discord.Guild,
    category_name: str,
) -> discord.CategoryChannel:
    """Find or create the category. Returns the category object."""
    category = discord.utils.get(guild.categories, name=category_name)
    if category is None:
        log.info("Creating category %r in %s", category_name, guild.name)
        category = await guild.create_category(category_name)
    return category


async def _ensure_channels(
    guild: discord.Guild,
    category: discord.CategoryChannel,
    feeds: dict[str, str],
    suit_calculator_name: str,
) -> dict[str, discord.TextChannel]:
    """Find or create the 3 main channels. Returns a dict: feed_key -> channel."""
    channels: dict[str, discord.TextChannel] = {}

    # Create feed channels (information, doodles)
    for key, channel_name in feeds.items():
        channel = discord.utils.get(guild.text_channels, name=channel_name)
        if channel is None:
            log.info("Creating channel #%s in %s", channel_name, guild.name)
            channel = await guild.create_text_channel(
                channel_name,
                category=category,
                topic=f"Live TTR {key} feed -- auto-updated by bot.",
            )
        channels[key] = channel

    # Create suit-calc channel
    calc_channel = discord.utils.get(guild.text_channels, name=suit_calculator_name)
    if calc_channel is None:
        log.info("Creating channel #%s in %s", suit_calculator_name, guild.name)
        calc_channel = await guild.create_text_channel(
            suit_calculator_name,
            category=category,
            topic="Cog suit disguise calculator — use /calculate here.",
        )
    channels["suit_calculator"] = calc_channel

    return channels


async def _send_placeholder(
    key: str,
    channel: discord.TextChannel,
) -> discord.Message:
    """Post a placeholder embed and pin it."""
    msg = await channel.send(embed=discord.Embed(
        title=f"Loading {key}...",
        description="Fetching the latest data from TTR.",
        color=0x9124F2,
    ))
    try:
        await msg.pin(reason="Live TTR feed pin")
    except (discord.Forbidden, discord.HTTPException) as e:
        log.debug("Could not pin in #%s: %s", channel.name, e)
    return msg


async def _ensure_placeholders(
    guild_id: int,
    channels: dict[str, discord.TextChannel],
    state: dict[str, Any],
) -> None:
    """Post placeholder embeds in each feed channel and update state."""
    guild_state = state.setdefault("guilds", {}).setdefault(str(guild_id), {})

    for key, channel in channels.items():
        if key == "suit_calculator":
            continue  # Handled separately

        entry = guild_state.get(key, {}) or {}
        message_ids: list[int] = []

        # Verify stored message IDs
        if isinstance(entry, dict):
            raw_ids = entry.get("message_ids", [])
            if isinstance(raw_ids, list):
                for mid in raw_ids:
                    try:
                        await channel.fetch_message(int(mid))
                        message_ids.append(int(mid))
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        pass

        # Post placeholder if no valid messages exist
        while len(message_ids) < 1:
            msg = await _send_placeholder(key, channel)
            message_ids.append(msg.id)

        guild_state[key] = {"channel_id": channel.id, "message_ids": message_ids}


async def _ensure_suit_calculator_pin(
    guild_id: int,
    channel: discord.TextChannel,
    state: dict[str, Any],
) -> None:
    """Post (or edit in place) the 4 static info embeds in #suit-calc."""
    embeds = build_suit_calculator_embeds()
    guild_state = state.setdefault("guilds", {}).setdefault(str(guild_id), {})
    entry = guild_state.get("suit_calculator", {})
    stored_ids: list[int] = []

    if isinstance(entry, dict):
        raw_ids = entry.get("message_ids", [])
        if isinstance(raw_ids, list):
            stored_ids = [int(i) for i in raw_ids if i]

    verified_ids: list[int] = []
    added_count = 0
    edited_count = 0

    for i, embed in enumerate(embeds):
        mid = stored_ids[i] if i < len(stored_ids) else None
        if mid:
            try:
                msg = await channel.fetch_message(mid)
                await msg.edit(embed=embed)
                verified_ids.append(msg.id)
                edited_count += 1
                continue
            except discord.NotFound:
                log.debug("[suit-calc] Embed %d gone for guild %s -- reposting.",
                         i + 1, guild_id)
            except discord.HTTPException as exc:
                log.debug("[suit-calc] Could not edit embed %d: %s", i + 1, exc)

        # Post new embed
        try:
            new_msg = await channel.send(embed=embed)
            if i == 0:
                try:
                    await new_msg.pin(reason="Suit Calculator -- Paws Pendragon TTR")
                except (discord.Forbidden, discord.HTTPException) as exc:
                    log.debug("[suit-calc] Could not pin: %s", exc)
            verified_ids.append(new_msg.id)
            added_count += 1
        except Exception as exc:
            log.warning("[suit-calc] Failed to post embed %d in guild %s: %s",
                        i + 1, guild_id, exc)

    if verified_ids:
        guild_state["suit_calculator"] = {
            "channel_id": channel.id,
            "message_ids": verified_ids,
        }

    if added_count or edited_count:
        log.info("[%d][%d][%s][%d added][%d updated]",
                 guild_id, channel.id, channel.name, added_count, edited_count)


async def _ensure_suit_threads(
    guild_id: int,
    channel: discord.TextChannel,
    state: dict[str, Any],
) -> dict[str, dict]:
    """Post or edit the 3 static embeds inside each of the 4 faction threads. Returns thread stats."""
    guild_state = state.setdefault("guilds", {}).setdefault(str(guild_id), {})
    suit_threads: dict = guild_state.setdefault("suit_threads", {})
    thread_stats: dict[str, dict] = {}

    guild = channel.guild
    guild_name = guild.name if guild else "Unknown"
    channel_name = channel.name

    for faction_key in _FACTION_ORDER:
        thread_name = _FACTION_THREAD_NAMES[faction_key]
        embeds = build_faction_thread_embeds(faction_key)
        entry = suit_threads.get(faction_key, {})
        thread_id = int(entry.get("thread_id", 0)) if isinstance(entry, dict) else 0
        msg_ids: list[int] = entry.get("message_ids", []) if isinstance(entry, dict) else []

        # Locate existing thread
        thread: discord.Thread | None = None
        if thread_id:
            thread = channel.guild.get_thread(thread_id)
            if thread is None:
                try:
                    thread = await channel.guild.fetch_channel(thread_id)  # type: ignore[assignment]
                except (discord.NotFound, discord.HTTPException):
                    thread = None

        if thread is None:
            for t in channel.threads:
                if t.name == thread_name:
                    thread = t
                    break

        # Create thread if missing
        if thread is None:
            try:
                thread = await channel.create_thread(
                    name=thread_name,
                    auto_archive_duration=10080,
                    type=discord.ChannelType.public_thread,
                )
                log.debug("[suit-threads] Created thread '%s' guild=%s",
                         thread_name, guild_id)
            except discord.Forbidden:
                log.warning("[suit-threads] No permission to create thread '%s' guild=%s",
                            thread_name, guild_id)
                continue
            except discord.HTTPException as exc:
                log.warning("[suit-threads] Failed to create thread '%s': %s",
                            thread_name, exc)
                continue

        # Unarchive if needed
        if getattr(thread, "archived", False):
            try:
                await thread.edit(archived=False)
            except (discord.Forbidden, discord.HTTPException):
                pass

        # Post or edit the 3 embeds
        verified_ids: list[int] = []
        msg_add = 0
        msg_remove = 0
        msg_update = 0

        for i, embed in enumerate(embeds):
            mid = msg_ids[i] if i < len(msg_ids) else None
            if mid:
                try:
                    msg = await thread.fetch_message(mid)
                    await msg.edit(embed=embed)
                    verified_ids.append(msg.id)
                    msg_update += 1
                    continue
                except discord.NotFound:
                    msg_remove += 1
                except discord.HTTPException as exc:
                    log.debug("[suit-threads] Could not edit embed %d in '%s': %s",
                                i + 1, thread_name, exc)

            # Post new embed
            try:
                new_msg = await thread.send(embed=embed)
                verified_ids.append(new_msg.id)
                msg_add += 1
            except discord.Forbidden:
                log.warning("[suit-threads] No send permission in thread '%s' guild=%s",
                            thread_name, guild_id)
                break
            except discord.HTTPException as exc:
                log.debug("[suit-threads] Failed to post embed %d in '%s': %s",
                            i + 1, thread_name, exc)

        # Lock thread so only the bot can post
        try:
            await thread.edit(locked=True, archived=False)
        except (discord.Forbidden, discord.HTTPException) as exc:
            log.debug("[suit-threads] Could not lock '%s': %s", thread_name, exc)

        suit_threads[faction_key] = {"thread_id": thread.id, "message_ids": verified_ids}

        thread_stats[faction_key] = {
            "thread_name": thread_name,
            "thread_id": thread.id,
            "msg_add": msg_add,
            "msg_remove": msg_remove,
            "msg_update": msg_update,
        }

        if msg_add or msg_remove or msg_update:
            log.info("[%s][%s][%s][%d][%d MsgAdd][%d MsgRemove][%d MsgUpdated]",
                     guild_name, channel_name, thread_name, thread.id, msg_add, msg_remove, msg_update)

    guild_state["suit_threads"] = suit_threads
    return thread_stats


def register_pd_setup(bot) -> None:
    """Register the /pd-setup slash command."""

    @bot.tree.command(
        name="pd-setup",
        description="[Server Admin Command] Create the TTR feed channels in this server and start tracking them.",
    )
    @app_commands.default_permissions(manage_channels=True, manage_messages=True)
    @app_commands.guild_only()
    async def pd_setup(interaction: discord.Interaction) -> None:
        """Initialize guild for live feed tracking."""
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message(
                "Must be used inside a server.",
                ephemeral=True,
            )
            return

        if not isinstance(interaction.user, discord.Member) or not _is_guild_admin(interaction.user):
            await interaction.response.send_message(
                "Only server administrators can run `/pd-setup`.",
                ephemeral=True,
            )
            return

        config: Config = bot.config

        # Check if guild is allowed
        if not bot.is_guild_allowed(guild.id):
            await interaction.response.send_message(
                f"This server isn't on the allowlist. Contact the bot owner to add `{guild.id}`.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            # Step 1: Create/find category
            category = await _ensure_category(guild, config.category_name)

            # Step 2: Create/find channels
            channels = await _ensure_channels(
                guild,
                category,
                config.feeds(),
                config.channel_suit_calculator,
            )

            # Step 3: Clean up orphaned doodle-search threads before posting
            await cleanup_doodle_search_threads(bot, guild)

            # Step 4: Post placeholder embeds
            await _ensure_placeholders(guild.id, channels, bot.state)

            # Step 5: Post suit calculator embeds
            await _ensure_suit_calculator_pin(
                guild.id,
                channels["suit_calculator"],
                bot.state,
            )

            # Step 6: Create suit threads and post embeds
            thread_stats = await _ensure_suit_threads(
                guild.id,
                channels["suit_calculator"],
                bot.state,
            )
            if thread_stats:
                log.info("[%s][%d][%d Threads]",
                         guild.name, guild.id, len(thread_stats))

            # Step 7: Save state atomically
            await bot._save_state()

            # Step 8: Send success message
            channels_msg = ", ".join(f"#{n}" for n in config.feeds().values())
            await interaction.followup.send(
                f"All set! Tracking **{channels_msg}** and `#{config.channel_suit_calculator}`. "
                f"Refreshes every {config.refresh_interval}s.",
                ephemeral=True,
            )

            log.info("pd-setup completed successfully for guild %s (%s)",
                     guild.id, guild.name)

        except discord.Forbidden:
            await interaction.followup.send(
                "I'm missing permissions. Make sure I have **Manage Channels**, "
                "**Send Messages**, and **Embed Links**, then try again.",
                ephemeral=True,
            )
            log.warning("pd-setup failed: permission denied for guild %s", guild.id)
        except Exception as exc:
            await interaction.followup.send(
                "An error occurred during setup. Check the bot logs for details.",
                ephemeral=True,
            )
            log.exception("pd-setup failed for guild %s: %s", guild.id, exc)
