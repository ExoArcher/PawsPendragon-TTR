# -*- coding: utf-8 -*-
"""Unquarantine detection for Paws Pendragon.

Monitors quarantined guilds to see if they've remediated (fewer than 5 banned
users with dangerous permissions). When remediated, automatically unquarantines
the server and notifies the owner.

Key functions:
  - check_unquarantine_candidates(): Find quarantined guilds ready to be unquarantined
  - trigger_unquarantine(): Remove quarantine status and notify owner
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord

from Features.Core.db import db
from Features.Infrastructure.quarantine_checks import DANGEROUS_PERMS

if TYPE_CHECKING:
    from bot import TTRBot

log = logging.getLogger("ttr-bot.unquarantine")


async def check_unquarantine_candidates(bot: TTRBot) -> list[int]:
    """
    Check all quarantined guilds to see if they've remediated.

    A guild is ready to unquarantine if it now has < 5 banned users with
    dangerous permissions.

    Returns:
        List of guild IDs ready to be unquarantined.
    """
    candidates: list[int] = []

    # Get all quarantined guilds
    quarantined = await db.load_quarantined_guilds()
    if not quarantined:
        return candidates

    # Get all banned users
    all_banned = await db.load_all_banned()
    if not all_banned:
        return candidates

    banned_user_ids = {int(uid) for uid in all_banned.keys()}

    for gid_str in quarantined.keys():
        try:
            guild_id = int(gid_str)
        except (ValueError, TypeError):
            continue

        guild = bot.get_guild(guild_id)
        if not guild:
            log.warning("[unquarantine] Guild %s not found; skipping check", guild_id)
            continue

        dangerous_banned_count = 0

        # Count banned users with dangerous permissions
        try:
            for member in guild.members:
                if member.id not in banned_user_ids:
                    continue

                # Check if this member has ANY dangerous permissions
                perms = member.guild_permissions
                has_dangerous = (
                    perms.administrator
                    or perms.manage_threads
                    or perms.manage_messages
                    or perms.manage_channels
                )

                if has_dangerous:
                    dangerous_banned_count += 1

        except Exception as exc:
            log.warning(
                "[unquarantine] Failed to scan guild %s (%s): %s",
                guild_id, guild.name, exc
            )
            continue

        # If < 5 dangerous banned users, flag for unquarantine
        if dangerous_banned_count < 5:
            candidates.append(guild_id)
            log.info(
                "[unquarantine] Guild %s (%s) is ready to unquarantine "
                "(%d dangerous banned users, < 5)",
                guild_id, guild.name, dangerous_banned_count
            )

    return candidates


async def trigger_unquarantine(bot: TTRBot, guild_id: int, owner_id: int) -> None:
    """
    Remove a guild from quarantine status.

    Does NOT remove from blacklist (permanent record; 7-day removal timer still active).

    Args:
        bot: TTRBot instance.
        guild_id: Discord guild ID.
        owner_id: Discord user ID of guild owner.
    """
    # Delete from quarantined_guilds
    removed = await db.remove_quarantined_guild(str(guild_id))

    if not removed:
        log.warning("[unquarantine] Guild %s was not in quarantine; skipping", guild_id)
        return

    # Update QuarantinedServerid cache
    if hasattr(bot, "QuarantinedServerid"):
        bot.QuarantinedServerid.discard(guild_id)

    # Log to audit_log
    await db.audit_log_event(
        guild_id=guild_id,
        event_type="guild_un_quarantined",
        details=json.dumps({"guild_id": guild_id}),
        triggered_by_user_id=0,
    )

    log.info("[unquarantine] Guild %s unquarantined", guild_id)

    # Send DM to owner
    try:
        owner = await bot.fetch_user(owner_id)
        embed = discord.Embed(
            title="✅ Your Server Has Been Un-Quarantined",
            description="Your server has been un-quarantined. Feeds will resume on next refresh.",
            color=discord.Color.green(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="Paws Pendragon • Quarantine Removal")

        await owner.send(embed=embed)
        log.info("[unquarantine] Sent unquarantine DM to owner %s", owner_id)

    except discord.Forbidden:
        log.warning("[unquarantine] Owner %s has DMs disabled", owner_id)

    except Exception as exc:
        log.error("[unquarantine] Failed to send DM to owner %s: %s", owner_id, exc)
