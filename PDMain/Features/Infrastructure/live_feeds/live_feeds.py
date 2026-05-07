"""Infrastructure/live-feeds feature for Paws Pendragon TTR Discord bot.

Background task that periodically fetches live TTR data and updates Discord
embeds in tracked guilds. Runs every 90 seconds (configurable).

Core responsibilities:
  - _refresh_loop() - Background task decorator, runs every ~90 seconds
  - _fetch_all() - Fetch all 4 enabled TTR endpoints in parallel
  - _refresh_once() - Main refresh logic for all tracked guilds
  - _update_feed() - Edit pinned messages with new embed data
  - _check_panel_announce() - Read and broadcast panel_announce.txt

Features:
  - Rate limiting (3-second delays between consecutive edits)
  - Doodle throttle (only refresh every 12 hours unless forced)
  - Graceful handling of stale message IDs
  - Parallel endpoint fetching via asyncio.gather()
  - TTR API 503 error handling
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any

import discord
from discord.ext import tasks

from Features.Admin.pd_refresh.pd_refresh import _validate_api_response
from Features.Core.config.constants import (
    DOODLE_REFRESH_INTERVAL_SECONDS,
    API_FETCH_TIMEOUT_SECONDS,
    PER_FEED_UPDATE_TIMEOUT_SECONDS,
    ANNOUNCEMENT_TTL_SECONDS,
)
from Features.Infrastructure import cache_manager

log = logging.getLogger("ttr-bot.live-feeds")

# Constants
ANNOUNCE_FILE = Path(__file__).parents[3] / "panel_announce.txt"
ANNOUNCEMENT_TITLE = "<:Lav:1499503216084390019> Paws Pendragon Dev Notice <:Lav:1499503216084390019>"


class LiveFeedsFeature:
    """Mixin providing live-feeds functionality to TTRBot.

    Expected to be mixed into a class that has:
      - self.config: Config instance with feeds() method
      - self._api: TTRApiClient instance (or None)
      - self._refresh_lock: asyncio.Lock
      - self._state_lock: asyncio.Lock
      - self._guilds_block() -> dict[str, dict[str, dict[str, Any]]]
      - self._guild_state(guild_id) -> dict[str, dict[str, Any]]
      - self._state_message_ids(guild_id, key) -> list[int]
      - self._set_state(guild_id, key, channel_id, message_ids)
      - self.get_guild(guild_id) -> discord.Guild | None
      - self.get_channel(channel_id) -> discord.abc.GuildChannel | None
      - self.is_guild_allowed(guild_id) -> bool
      - self._save_state() -> Coroutine
      - self._broadcast_announcement(text) -> Coroutine returning (sent, failed, guilds)
      - self.wait_until_ready() -> Coroutine
    """

    def __init__(self, **kwargs) -> None:
        # Timestamp of the last time doodle embeds were pushed to Discord.
        # 0.0 = never, which triggers an immediate doodle refresh on first run.
        self._last_doodle_refresh: float = 0.0
        super().__init__(**kwargs)

    # ── FEED REFRESH ──────────────────────────────────────────────────────────

    async def _fetch_all(self) -> dict[str, dict | None]:
        """Fetch all 4 enabled TTR endpoints in parallel.

        Returns a mapping of feed key to API response (or None on error).
        Does NOT fetch invasions (per user constraint: no building data).

        Note: Doodles are fetched every cycle but the embeds are only
        updated if the 12-hour throttle window has elapsed.
        """
        if self._api is None:
            return {"population": None, "fieldoffices": None, "doodles": None, "sillymeter": None}

        # Fetch the 4 enabled endpoints in parallel
        results = await asyncio.gather(
            self._api.fetch("population"),
            self._api.fetch("fieldoffices"),
            self._api.fetch("doodles"),
            self._api.fetch("sillymeter"),
            return_exceptions=True,
        )

        return {
            "population": None if isinstance(results[0], BaseException) else results[0],
            "fieldoffices": None if isinstance(results[1], BaseException) else results[1],
            "doodles": None if isinstance(results[2], BaseException) else results[2],
            "sillymeter": None if isinstance(results[3], BaseException) else results[3],
        }

    def _get_guild_channel(
        self, guild_id: int, ch_id: int | None
    ) -> discord.TextChannel | None:
        """Safely get a text channel, returning None with debug log if not found.

        Checks: ch_id is non-zero, channel exists in cache, channel is a TextChannel.
        """
        if not ch_id:
            return None
        channel = self.get_channel(ch_id)
        if channel is None:
            log.debug("[%d] Channel %d not in cache (may be deleted)", guild_id, ch_id)
            return None
        if not isinstance(channel, discord.TextChannel):
            log.debug("[%d] Channel %d is not a TextChannel (type=%s)", guild_id, ch_id, type(channel).__name__)
            return None
        return channel

    async def _refresh_once(self, *, force_doodles: bool = False) -> None:
        """Refresh all live feed embeds across tracked guilds.

        Doodle embeds are throttled to once every 12 hours unless
        *force_doodles* is True (set by /pd-refresh).

        For each tracked guild, calls _update_feed() to edit pinned messages.
        Respects 3-second delays between consecutive edits (rate limiting).
        Outputs hierarchical logs at the end: Server -> Channels.

        The TTR API fetch and per-guild updates run OUTSIDE _refresh_lock so
        user commands (/ttrinfo etc.) are never blocked during slow fetches.
        The lock is held only for the fast final state save.
        """
        if self._api is None:
            return

        now = time.time()
        refresh_doodles = force_doodles or (
            (now - self._last_doodle_refresh) >= DOODLE_REFRESH_INTERVAL_SECONDS
        )

        # Fetch API data OUTSIDE the lock (can take 3-10s; must not block commands)
        try:
            api_data = await asyncio.wait_for(self._fetch_all(), timeout=API_FETCH_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            log.error("TTR API fetch timed out after 10s; skipping this refresh cycle")
            return
        except Exception:
            log.exception("TTR API fetch failed; skipping this refresh cycle")
            return

        if not _validate_api_response(api_data):
            log.warning("[live-feeds] API response validation failed — skipping refresh cycle")
            return

        # Structure: {guild_id: {channel_name: {channel_id: {msg_add, msg_remove, msg_update}}}}
        guild_stats: dict[int, dict[str, dict[int, dict[str, int]]]] = {}

        for guild_id_str in list(self._guilds_block().keys()):
            try:
                guild_id = int(guild_id_str)
            except ValueError:
                continue

            if not self.is_guild_allowed(guild_id) or self.get_guild(guild_id) is None:
                continue

            guild_stats[guild_id] = {}

            for feed_key in self.config.feeds():
                # Skip doodle embeds unless the 12-hour interval has elapsed
                # (or this is a forced refresh from /pd-refresh).
                if feed_key == "doodles" and not refresh_doodles:
                    continue

                try:
                    stats = await asyncio.wait_for(
                        self._update_feed(guild_id, feed_key, api_data),
                        timeout=PER_FEED_UPDATE_TIMEOUT_SECONDS,
                    )
                    if any(stats.values()):
                        # Get channel info from state
                        entry = self._guild_state(guild_id).get(feed_key)
                        if entry and isinstance(entry, dict):
                            channel_id = int(entry.get("channel_id", 0))
                            channel = self.get_channel(channel_id)
                            if channel:
                                ch_name = channel.name
                                guild_stats[guild_id][ch_name] = {channel_id: stats}
                except asyncio.TimeoutError:
                    log.warning("Guild %d feed %s update timed out; skipping", guild_id, feed_key)
                    continue
                except Exception:
                    log.exception("Failed updating %s/%s", guild_id, feed_key)
                    continue

        # Output hierarchical logs
        for guild_id in sorted(guild_stats.keys()):
            guild = self.get_guild(guild_id)
            guild_name = guild.name if guild else "unknown"
            channels = guild_stats[guild_id]

            if channels:
                # Server log: [ServerName][ServerID][# Channels][# Threads]
                log.info("[%s][%d][%d Channels][0 Threads]", guild_name, guild_id, len(channels))

                # Channel logs
                for ch_name in sorted(channels.keys()):
                    ch_data = channels[ch_name]  # {channel_id: {msg_add, msg_remove, msg_update}}
                    for ch_id, stats in ch_data.items():
                        # [ChannelName][ChannelID][# ThreadAdd][# ThreadRemove][# MsgAdd][# MsgRemove][# MsgUpdated]
                        log.info("[%s][%d][0 ThreadAdd][0 ThreadRemove][%d MsgAdd][%d MsgRemove][%d MsgUpdated]",
                                 ch_name, ch_id, stats["msg_add"], stats["msg_remove"], stats["msg_update"])

        # Hold lock ONLY for the fast final state save
        async with self._refresh_lock:
            if refresh_doodles:
                self._last_doodle_refresh = now
                log.info("Doodle embeds refreshed (next automatic refresh in 12 hours).")
            try:
                await self._save_state()
            except Exception:
                log.exception("Failed to save state after refresh; message IDs may not persist")

    async def _update_feed(self, guild_id: int, feed_key: str, api_data: dict[str, dict | None]) -> dict:
        """Update a single feed for a guild. Returns stats dict: {msg_add, msg_remove, msg_update}.

        - Looks up the stored message IDs for this guild/feed combination
        - Fetches the Discord channel
        - Calls the appropriate formatter to build embed(s)
        - Edits pinned messages in place using discord.Message.edit()
        - Handles stale message IDs gracefully (message not found = resend)
        - Respects 3-second delays between consecutive edits (rate limiting)
        - Updates stored message IDs if messages are recreated
        """
        from Features.Core.formatters.formatters import FORMATTERS

        entry = self._guild_state(guild_id).get(feed_key)
        if not entry:
            return {"msg_add": 0, "msg_remove": 0, "msg_update": 0}

        try:
            channel_id = int(entry.get("channel_id", 0))
            if channel_id == 0:
                return {"msg_add": 0, "msg_remove": 0, "msg_update": 0}
        except (ValueError, TypeError):
            log.warning("Invalid channel_id in guild_state %s/%s", guild_id, feed_key)
            return {"msg_add": 0, "msg_remove": 0, "msg_update": 0}

        channel = self._get_guild_channel(guild_id, channel_id)
        if channel is None:
            return {"msg_add": 0, "msg_remove": 0, "msg_update": 0}

        formatter = FORMATTERS.get(feed_key)
        if formatter is None:
            return {"msg_add": 0, "msg_remove": 0, "msg_update": 0}

        embeds = formatter(api_data)
        if not isinstance(embeds, list):
            embeds = [embeds]
        if not embeds:
            # Send error embed to show feed is live but no data available
            embeds = [discord.Embed(
                title="Live Feed Error",
                description="No data available from TTR API. Feed will update when data returns.",
                color=0xFF0000
            )]

        ids = self._state_message_ids(guild_id, feed_key)
        # Ensure we have at least as many message IDs as embeds
        if len(ids) < len(embeds):
            ids.extend([0] * (len(embeds) - len(ids)))

        kept_ids: list[int] = []
        msg_add = msg_remove = msg_update = 0
        retry_needed = False

        # Edit or recreate messages for each embed
        for mid, embed in zip(ids, embeds):
            try:
                if mid > 0:
                    try:
                        msg = await asyncio.wait_for(channel.fetch_message(mid), timeout=5.0)
                        await msg.edit(embed=embed)
                    except asyncio.TimeoutError:
                        log.warning("Timeout fetching message %s (%s/%s) -- will retry.", mid, guild_id, feed_key)
                        retry_needed = True
                    else:
                        kept_ids.append(mid)
                        msg_update += 1
                        await asyncio.sleep(3.0)
                else:
                    # No stored message ID, send a new one
                    new_msg = await channel.send(embed=embed)
                    try:
                        await new_msg.pin(reason="Live TTR feed pin")
                    except (discord.Forbidden, discord.HTTPException):
                        pass
                    kept_ids.append(new_msg.id)
                    msg_add += 1
                    await asyncio.sleep(3.0)
            except discord.NotFound:
                # Message is stale (deleted), send a new one
                msg_remove += 1
                new_msg = await channel.send(embed=embed)
                try:
                    await new_msg.pin(reason="Live TTR feed pin")
                except (discord.Forbidden, discord.HTTPException):
                    pass
                kept_ids.append(new_msg.id)
                msg_add += 1
                await asyncio.sleep(3.0)
            except discord.HTTPException as e:
                log.warning(
                    "Transient HTTP %s editing message %s (%s/%s) -- will retry.",
                    e.status,
                    mid,
                    guild_id,
                    feed_key,
                )
                retry_needed = True

        # Handle extra slots (clear with placeholder if they have stale IDs)
        for mid in ids[len(embeds):]:
            if mid == 0:
                continue
            try:
                try:
                    msg = await asyncio.wait_for(channel.fetch_message(mid), timeout=5.0)
                    await msg.edit(
                        embed=discord.Embed(
                            description="*(no data for this tier right now)*",
                            color=0x9124F2
                        )
                    )
                    kept_ids.append(mid)
                    msg_update += 1
                    await asyncio.sleep(3.0)
                except asyncio.TimeoutError:
                    log.warning("Timeout fetching stale-slot message %s (%s/%s) -- will retry.", mid, guild_id, feed_key)
                    retry_needed = True
            except discord.NotFound:
                msg_remove += 1
            except discord.HTTPException as e:
                log.warning("Transient HTTP %s on stale-slot message %s -- will retry.", e.status, mid)
                retry_needed = True

        # Only save state if all updates succeeded; retry next cycle if any HTTPException occurred
        if not retry_needed:
            self._set_state(guild_id, feed_key, channel.id, kept_ids)
        return {"msg_add": msg_add, "msg_remove": msg_remove, "msg_update": msg_update}

    @tasks.loop(seconds=90)
    async def _refresh_loop(self) -> None:
        """Main background task running every ~90 seconds (or REFRESH_INTERVAL from config).

        Responsibilities:
          1. Sweep expired announcements
          2. Check for panel_announce.txt and broadcast it
          3. Call _refresh_once() to update all live feeds
        """
        try:
            await self._sweep_expired_announcements()
        except Exception:
            log.exception("Announcement sweep failed")

        try:
            await self._check_panel_announce()
        except Exception:
            log.exception("Panel announce check failed")

        await self._refresh_once()

    @_refresh_loop.before_loop
    async def _before_refresh_loop(self) -> None:
        """Wait until the bot is ready before starting the refresh loop."""
        await self.wait_until_ready()

    async def _check_panel_announce(self) -> None:
        """Check for panel_announce.txt, broadcast it, then delete the file.

        If the file exists, reads its contents, broadcasts to all tracked
        guilds via _broadcast_announcement(), then deletes the file.

        Useful for emergency announcements from hosting panels that support
        file uploads.
        """
        if not ANNOUNCE_FILE.exists():
            return

        try:
            # Read max 10KB to prevent memory exhaustion
            with open(ANNOUNCE_FILE, 'r', encoding='utf-8') as f:
                text = f.read(10240).strip()
            ANNOUNCE_FILE.unlink()
        except Exception as e:
            log.warning("Could not read/delete panel_announce.txt: %s", e)
            return

        if not text:
            return

        log.info("Panel announcement detected -- broadcasting: %s", text[:80])
        sent, failed, guilds = await self._broadcast_announcement(text)
        log.info("Panel announcement: %d msg(s) across %d guild(s), %d failed.", sent, guilds, failed)

    # ── ANNOUNCEMENT SUPPORT ──────────────────────────────────────────────────

    async def _sweep_expired_announcements(self) -> None:
        """Remove expired announcement records and delete their Discord messages.

        Called every 90 seconds from _refresh_loop().
        """
        now = time.time()
        expired = [
            r for r in list(self._announcements())
            if float(r.get("expires_at", 0)) <= now
        ]
        for record in expired:
            await self._delete_announcement_record(record)

        if expired:
            await self._save_state()

    async def _broadcast_announcement(self, text: str) -> tuple[int, int, int]:
        """Broadcast an announcement to all tracked guilds.

        Returns (sent, failed, guilds_touched) counts.
        Used by both console commands and panel announcements.
        """
        embed = discord.Embed(
            title=ANNOUNCEMENT_TITLE,
            description=text,
            color=0x9124F2
        )
        embed.set_footer(
            text=f"This message will auto-delete in {ANNOUNCEMENT_TTL_SECONDS // 60} minutes."
        )
        expires_at = time.time() + ANNOUNCEMENT_TTL_SECONDS
        sent = failed = 0
        guilds_touched: set[int] = set()

        for guild_id_str, gs in list(self._guilds_block().items()):
            try:
                guild_id = int(guild_id_str)
            except ValueError:
                continue

            # Broadcast to all feed channels
            for feed_key in ("information", "doodles", "suit_calculator"):
                entry = gs.get(feed_key)
                if not entry:
                    continue

                channel = self.get_channel(int(entry.get("channel_id", 0)))
                if not isinstance(channel, discord.TextChannel):
                    continue

                try:
                    msg = await channel.send(embed=embed)
                    await self._record_announcement(guild_id, channel.id, msg.id, expires_at)
                    sent += 1
                    guilds_touched.add(guild_id)
                except (discord.Forbidden, discord.HTTPException) as e:
                    log.warning(
                        "Broadcast failed for %s/#%s: %s",
                        guild_id,
                        channel.name,
                        e,
                    )
                    failed += 1

        return sent, failed, len(guilds_touched)

    async def _delete_announcement_record(self, record: dict[str, Any]) -> None:
        """Delete an announcement message and remove its record."""
        channel_id = int(record.get("channel_id", 0))
        message_id = int(record.get("message_id", 0))

        try:
            channel = self.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    await (await channel.fetch_message(message_id)).delete()
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    log.warning("No permission to delete announcement %s", message_id)
        except Exception:
            log.exception("Failed deleting announcement %s", message_id)

        self._announcements()[:] = [
            r for r in self._announcements()
            if int(r.get("message_id", -1)) != message_id
        ]
        await self._save_state()

    # ── REQUIRED STUB METHODS (expected to be implemented by TTRBot) ────────────

    def _announcements(self) -> list[dict[str, Any]]:
        """Return the announcements list from state. Must be implemented by subclass."""
        raise NotImplementedError("Must be implemented by subclass")

    async def _record_announcement(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        expires_at: float,
    ) -> None:
        """Record an announcement in state. Must be implemented by subclass."""
        raise NotImplementedError("Must be implemented by subclass")
