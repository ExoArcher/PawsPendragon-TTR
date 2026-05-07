# -*- coding: utf-8 -*-
"""Automatic blacklist removal timer for Paws Pendragon.

After 7 days on the blacklist, a guild owner is banned and the guild is
removed from the bot's allowlist and databases.

Key function:
  - check_blacklist_removal_timers(): Find and remove expired blacklist entries
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone, timedelta
from typing import TYPE_CHECKING

import aiosqlite
import discord

from Features.Core.db import db
from Features.Core.db.db_cache_coherence import atomic_db_cache_update
from Features.Core.config.config import update_env_var
from Features.Infrastructure import cache_manager

if TYPE_CHECKING:
    from bot import TTRBot

log = logging.getLogger("ttr-bot.blacklist-removal")


async def check_blacklist_removal_timers(bot: TTRBot) -> int:
    """
    Check for blacklisted guilds that have expired (7+ days).
    For each expired guild:
      - Ban the owner
      - Remove from guild_feeds and blacklist
      - Post "auto-removed" embed if possible
      - Update caches
      - Log to audit_log

    Returns:
        Number of guilds removed from blacklist.
    """
    removed_count = 0

    # Calculate 7 days ago
    seven_days_ago = datetime.now(timezone.utc) - timedelta(days=7)

    async with aiosqlite.connect(db.DB_PATH) as database:
        async with database.execute(
            "SELECT guild_id, owner_id, reason FROM blacklist WHERE timestamp < ?",
            (seven_days_ago.isoformat(),),
        ) as cur:
            expired = await cur.fetchall()

    for guild_id, owner_id, reason in expired:
        try:
            # Get guild info (may not be accessible if bot was removed)
            guild = bot.get_guild(int(guild_id)) if guild_id else None

            # Ban the owner if not already banned
            owner_ban_reason = f"Served as owner of blacklisted server (Guild ID: {guild_id})"
            existing_ban = await db.get_ban(owner_id)
            if not existing_ban:
                ban_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
                await db.add_ban(owner_id, owner_ban_reason, ban_timestamp)
                log.info("[blacklist-removal] Banned owner %s (server %s)", owner_id, guild_id)

            # Post "auto-removed" embed if guild is still accessible
            if guild:
                await _post_removal_embed_to_guild(bot, guild)

            # Delete from guild_feeds
            async with aiosqlite.connect(db.DB_PATH) as database:
                await database.execute("DELETE FROM guild_feeds WHERE guild_id = ?", (str(guild_id),))
                await database.commit()

            # Delete from blacklist
            await db.remove_from_blacklist(guild_id)

            # Update in-memory caches immediately (don't wait for 6-hour refresh)
            success = await atomic_db_cache_update(
                db.DB_PATH,
                operation="delete",
                table="blacklist",
                where_clause={"guild_id": guild_id},
                cache_set=cache_manager.BlacklistedServerid,
                cache_keys=[guild_id],
            )
            if not success:
                log.error("[blacklist] Failed to remove guild %d from blacklist cache", guild_id)

            # Log to audit_log
            await db.log_audit_event(
                event_type="guild_blacklist_removal_auto",
                details=json.dumps({"guild_id": guild_id, "owner_id": owner_id}),
                guild_id=guild_id,
                triggered_by_user_id=0,
            )

            log.info(
                "[blacklist-removal] Removed guild %s from blacklist "
                "(owner banned); owner_id=%s",
                guild_id, owner_id
            )
            removed_count += 1

        except Exception as exc:
            log.error("[blacklist-removal] Error removing guild %s: %s", guild_id, exc)
            continue

    return removed_count


async def _post_removal_embed_to_guild(bot: TTRBot, guild: discord.Guild) -> None:
    """Post 'auto-removed' embed to all tracked channels in the guild."""
    from Features.Core.db import db as db_module

    state = await db_module.load_state()
    guild_data = state.get("guilds", {}).get(str(guild.id), {})

    embed = discord.Embed(
        title="🗑️ Server Auto-Removed from Blacklist",
        description=(
            "Server owner was banned for failure to remediate. "
            "Server is removed from bot allowlist."
        ),
        color=discord.Color.greyple(),
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="Paws Pendragon • Blacklist Removal")

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
                continue

            if not ch.permissions_for(guild.me).send_messages:
                continue

            await ch.send(embed=embed)
            posted += 1

        except Exception as exc:
            log.warning("[blacklist-removal] Failed to post to channel %s: %s", ch_id, exc)

    log.info("[blacklist-removal] Posted removal embed to %d channel(s) in guild %s", posted, guild.id)
