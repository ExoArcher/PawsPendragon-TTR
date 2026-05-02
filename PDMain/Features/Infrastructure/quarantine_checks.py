# -*- coding: utf-8 -*-
"""Quarantine detection and enforcement for Paws Pendragon.

Monitors tracked guilds for 5+ banned users with dangerous permissions and
automatically quarantines/unquarantines servers based on this detection.

Key functions:
  - detect_quarantine_candidates(): Find guilds with 5+ banned users with dangerous perms
  - trigger_quarantine(): Quarantine a guild and notify the owner
  - send_quarantine_dm_to_owner(): Send quarantine notice to guild owner
  - build_quarantine_embed(): Build the quarantine notice embed
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import aiosqlite
import discord

from Features.Core.db import db
from Features.Infrastructure import cache_manager

if TYPE_CHECKING:
    from bot import TTRBot

log = logging.getLogger("ttr-bot.quarantine")

# Dangerous permissions that trigger quarantine checks
DANGEROUS_PERMS = {
    "administrator",
    "manage_threads",
    "manage_messages",
    "manage_channels",
}


async def detect_quarantine_candidates(bot: TTRBot) -> list[tuple[int, int, list[int]]]:
    """
    Scan all tracked guilds for 5+ banned users with dangerous permissions.

    Returns:
        List of (guild_id, owner_id, banned_user_ids_list) tuples for candidates.
    """
    candidates: list[tuple[int, int, list[int]]] = []

    # Get all banned users from database
    all_banned = await db.load_all_banned()
    if not all_banned:
        return candidates

    banned_user_ids = {int(uid) for uid in all_banned.keys()}

    # Check each guild the bot is in
    for guild in bot.guilds:
        dangerous_banned: list[int] = []

        # Check each member in the guild
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
                    dangerous_banned.append(member.id)

        except Exception as exc:
            log.warning(
                "[quarantine] Failed to scan guild %s (%s): %s",
                guild.id, guild.name, exc
            )
            continue

        # If 5+ dangerous banned users found, flag for quarantine
        if len(dangerous_banned) >= 5:
            candidates.append((guild.id, guild.owner_id or 0, dangerous_banned))
            log.info(
                "[quarantine] Detected %d dangerous banned users in guild %s (%s)",
                len(dangerous_banned), guild.id, guild.name
            )

    return candidates


async def trigger_quarantine(
    bot: TTRBot,
    guild_id: int,
    owner_id: int,
    banned_user_ids_list: list[int],
) -> None:
    """
    Quarantine a guild: insert into DB, update caches, notify owner, and post embeds.

    Args:
        bot: TTRBot instance for accessing caches and Discord API.
        guild_id: Discord guild ID.
        owner_id: Discord user ID of guild owner.
        banned_user_ids_list: List of banned user IDs with dangerous perms.
    """
    # Check if already quarantined
    existing = await db.load_quarantined_guilds()
    if str(guild_id) in existing:
        log.info("[quarantine] Guild %s already quarantined; skipping.", guild_id)
        return

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Insert into quarantined_guilds table (using old schema for compatibility)
    await db.add_quarantined_guild(
        guild_id=str(guild_id),
        guild_name=bot.get_guild(guild_id).name if bot.get_guild(guild_id) else "unknown",
        owner_id=str(owner_id),
        flagged_at=now,
        flag_reason="5+ banned users with dangerous permissions detected",
        flagged_by_user_id="0",  # System-triggered
    )

    # Insert into blacklist
    reason = "5+ banned users with dangerous permissions detected"
    flagged_ids_json = json.dumps(["0"])  # System-triggered
    async with aiosqlite.connect(db.DB_PATH) as database:
        await database.execute(
            "INSERT OR REPLACE INTO blacklist "
            "(guild_id, owner_id, reason, flagged_by_user_ids) VALUES (?, ?, ?, ?)",
            (guild_id, owner_id, reason, flagged_ids_json),
        )
        await database.commit()

    # Update in-memory caches immediately (don't wait for 6-hour refresh)
    cache_manager.QuarantinedServerid.add(guild_id)
    cache_manager.BlacklistedServerid.add(guild_id)

    log.info("[quarantine] Quarantined guild %s, blacklisted owner %s", guild_id, owner_id)

    # Log to audit_log
    details_json = json.dumps({
        "guild_id": guild_id,
        "banned_user_ids": banned_user_ids_list,
    })
    await db.log_audit_event(
        event_type="guild_quarantined",
        details=details_json,
        guild_id=guild_id,
        triggered_by_user_id=0,
    )

    await db.log_audit_event(
        event_type="guild_blacklisted",
        details=json.dumps({"guild_id": guild_id, "owner_id": owner_id}),
        guild_id=guild_id,
        triggered_by_user_id=0,
    )

    # Send DM to owner
    await send_quarantine_dm_to_owner(bot, guild_id, owner_id, banned_user_ids_list)

    # Post quarantine embeds to all tracked channels in the guild
    await _post_quarantine_embeds_to_guild(bot, guild_id)


async def send_quarantine_dm_to_owner(
    bot: TTRBot,
    guild_id: int,
    owner_id: int,
    banned_user_ids_list: list[int],
) -> None:
    """
    Send quarantine notice DM to guild owner with list of banned users.

    Args:
        bot: TTRBot instance.
        guild_id: Discord guild ID.
        owner_id: Discord user ID of guild owner.
        banned_user_ids_list: List of banned user IDs.
    """
    # Build banned users field text
    all_banned = await db.load_all_banned()

    banned_lines = []
    for uid in banned_user_ids_list:
        uid_str = str(uid)
        if uid_str in all_banned:
            reason = all_banned[uid_str].get("reason", "No reason provided")
            banned_lines.append(f"{uid}: {reason}")
        else:
            banned_lines.append(f"{uid}: (no reason)")

    banned_field = "\n".join(banned_lines) if banned_lines else "(No banned users found)"

    embed = discord.Embed(
        title="⚠️ Your Server Has Been Quarantined",
        description=(
            "Due to 5+ members with dangerous permissions being on the ban list, "
            "your server has been quarantined."
        ),
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc),
    )

    embed.add_field(
        name="Banned Users",
        value=banned_field[:1024],  # Discord field limit
        inline=False,
    )

    embed.add_field(
        name="Next Steps",
        value=(
            "1) Remove these users from your server\n"
            "2) Wait for automatic re-check (6 hours)\n"
            "3) Server will auto-unquarantine when safe\n"
            "4) Or contact bot admin if this is a mistake"
        ),
        inline=False,
    )

    embed.set_footer(text="Paws Pendragon • Quarantine Notice")

    try:
        owner = await bot.fetch_user(owner_id)
        await owner.send(embed=embed)

        # Update quarantined_guilds.owner_notified = 'Y'
        async with aiosqlite.connect(db.DB_PATH) as database:
            await database.execute(
                "UPDATE quarantined_guilds SET owner_notified = 'Y' WHERE guild_id = ?",
                (str(guild_id),),
            )
            await database.commit()

        log.info("[quarantine] Sent quarantine DM to owner %s (guild %s)", owner_id, guild_id)

    except discord.Forbidden:
        log.warning("[quarantine] Owner %s has DMs disabled; posting fallback to guild channels", owner_id)

        # Post fallback message to guild channels
        guild = bot.get_guild(guild_id)
        if guild:
            fallback_embed = discord.Embed(
                title="🚨 Server Admin is Out of Reach",
                description=(
                    "The quarantine notice could not be delivered to the server owner "
                    "(DMs disabled or user not found). "
                    "Please contact the server admin to take action."
                ),
                color=discord.Color.red(),
            )

            # Try to post to tracked channels
            from Features.Core.db import db as db_module
            state = await db_module.load_state()
            guild_data = state.get("guilds", {}).get(str(guild_id), {})

            for feed_key, feed_data in guild_data.items():
                if feed_key.startswith("suit_threads"):
                    continue
                ch_id = feed_data.get("channel_id", 0)
                if ch_id:
                    try:
                        ch = bot.get_channel(ch_id)
                        if ch and ch.permissions_for(guild.me).send_messages:
                            await ch.send(embed=fallback_embed)
                    except Exception as exc:
                        log.warning("[quarantine] Failed to post fallback to channel %s: %s", ch_id, exc)

        await db.log_audit_event(
            event_type="quarantine_dm_failed",
            details=json.dumps({"owner_id": owner_id}),
            guild_id=guild_id,
            triggered_by_user_id=0,
        )

    except Exception as exc:
        log.error("[quarantine] Failed to send DM to owner %s: %s", owner_id, exc)
        await db.log_audit_event(
            event_type="quarantine_dm_failed",
            details=json.dumps({"owner_id": owner_id, "error": str(exc)}),
            guild_id=guild_id,
            triggered_by_user_id=0,
        )


def build_quarantine_embed() -> discord.Embed:
    """Build the quarantine notice embed to post in guild channels."""
    embed = discord.Embed(
        title="🛑 SERVER QUARANTINED",
        description=(
            "This server is quarantined due to security concerns "
            "(multiple banned users with dangerous permissions). Feeds are paused."
        ),
        color=discord.Color.red(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="Contact bot admin if this is a mistake")
    return embed


async def _post_quarantine_embeds_to_guild(bot: TTRBot, guild_id: int) -> None:
    """Post quarantine embeds to all 3 tracked channels in guild."""
    from Features.Core.db import db as db_module

    guild = bot.get_guild(guild_id)
    if not guild:
        log.warning("[quarantine] Guild %s not found; skipping embed posting", guild_id)
        return

    state = await db_module.load_state()
    guild_data = state.get("guilds", {}).get(str(guild_id), {})

    embed = build_quarantine_embed()
    posted = 0

    for feed_key, feed_data in guild_data.items():
        if feed_key.startswith("suit_threads"):
            continue

        ch_id = feed_data.get("channel_id", 0)
        if not ch_id:
            continue

        try:
            ch = bot.get_channel(ch_id)
            if not ch:
                log.warning("[quarantine] Channel %s not found", ch_id)
                continue

            if not ch.permissions_for(guild.me).send_messages:
                log.warning("[quarantine] No perms to send to channel %s", ch_id)
                continue

            await ch.send(embed=embed)
            posted += 1

        except Exception as exc:
            log.warning("[quarantine] Failed to post to channel %s: %s", ch_id, exc)

    log.info("[quarantine] Posted quarantine embed to %d channel(s) in guild %s", posted, guild_id)
