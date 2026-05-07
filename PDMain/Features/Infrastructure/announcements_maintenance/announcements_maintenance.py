"""Infrastructure/announcements-maintenance feature for Paws Pendragon TTR Discord bot.

Manages temporary announcement messages broadcast to all tracked guilds with automatic
expiry cleanup. Announcements auto-delete after 30 minutes.

Core responsibilities:
  - broadcast_announcement(text) - Send announcement to all guilds' tracked channels
  - _create_announcement_record(guild_id, channel_id, message_id, expires_at) - Store in DB
  - _sweep_expired_announcements() - Delete expired announcements
  - _delete_announcement_record(record) - Clean up single announcement
  - console command support via announce <text>

Announcement Flow:
  1. Console command or internal call with text
  2. Send to all tracked guild channels (info, doodles, suit_calculator)
  3. Store message ID + expiry timestamp (now + 1800 seconds = 30 minutes)
  4. Sweep loop deletes expired messages (called from _refresh_loop every 90 seconds)

Design Patterns:
  - All-or-nothing broadcast (try to send to all guilds, log failures gracefully)
  - Expiry-based cleanup (check expires_at timestamp against current time)
  - Graceful failure handling for missing channels/permissions
  - Stale message ID handling (skip deleted messages in sweep)
"""
from __future__ import annotations

import logging
import time
from typing import Any

import discord

log = logging.getLogger("ttr-bot.announcements-maintenance")

# Constants
ANNOUNCEMENT_TITLE = "<:Lav:1499503216084390019> Paws Pendragon Dev Notice <:Lav:1499503216084390019>"
ANNOUNCEMENT_TTL_SECONDS = 30 * 60  # 30 minutes in seconds (1800 seconds)


class AnnouncementsMaintenance:
    """Mixin providing announcements-maintenance functionality to TTRBot.

    Expected to be mixed into a class that has:
      - self.config: Config instance
      - self._guilds_block() -> dict[str, dict[str, dict[str, Any]]]
      - self.get_channel(channel_id) -> discord.abc.GuildChannel | None
      - self._save_state() -> Coroutine
      - self.state: dict[str, Any] with "announcements" key
    """

    # ── ANNOUNCEMENT BROADCAST ────────────────────────────────────────────────

    async def broadcast_announcement(self, text: str) -> tuple[int, int, int]:
        """Broadcast an announcement to all tracked guilds' feed channels.

        Posts the announcement to all available information, doodles, and
        suit_calculator channels across all tracked guilds. Records each
        message with a 30-minute expiry timestamp.

        Args:
            text: The announcement text to broadcast.

        Returns:
            Tuple of (sent, failed, guilds_touched):
              - sent: Number of messages successfully posted
              - failed: Number of messages that failed to post
              - guilds_touched: Number of distinct guilds that received at least one message

        Design:
          - All-or-nothing approach: attempt to send to all guilds
          - Gracefully handles missing channels or permission errors
          - Logs each failure for audit trail
          - Uses consistent embedding format with auto-delete footer
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

            # Broadcast to all feed channels: information, doodles, suit_calculator
            for feed_key in ("information", "doodles", "suit_calculator"):
                entry = gs.get(feed_key)
                if not entry:
                    continue

                channel = self.get_channel(int(entry.get("channel_id", 0)))
                if not isinstance(channel, discord.TextChannel):
                    continue

                try:
                    msg = await channel.send(embed=embed)
                    await self._create_announcement_record(guild_id, channel.id, msg.id, expires_at)
                    sent += 1
                    guilds_touched.add(guild_id)
                    log.debug(
                        "Broadcast announcement to %s/#%s (msg=%s)",
                        guild_id,
                        channel.name,
                        msg.id,
                    )
                except discord.Forbidden:
                    log.warning(
                        "Broadcast failed for %s/#%s: missing Send Messages permission",
                        guild_id,
                        channel.name,
                    )
                    failed += 1
                except discord.HTTPException as e:
                    log.warning(
                        "Broadcast failed for %s/#%s: HTTP %s - %s",
                        guild_id,
                        channel.name,
                        e.status,
                        e,
                    )
                    failed += 1

        log.info(
            "Announcement broadcast: %d msg(s) to %d guild(s), %d failed",
            sent,
            len(guilds_touched),
            failed,
        )
        return sent, failed, len(guilds_touched)

    # ── ANNOUNCEMENT RECORD MANAGEMENT ────────────────────────────────────────

    async def _create_announcement_record(
        self,
        guild_id: int,
        channel_id: int,
        message_id: int,
        expires_at: float,
    ) -> None:
        """Store an announcement record in state with expiry timestamp.

        Called after successfully posting an announcement to a channel.
        Stores the message ID and expiry time so the sweep loop can find
        and delete it when the TTL expires.

        Args:
            guild_id: Discord guild ID where message was posted
            channel_id: Discord channel ID where message was posted
            message_id: Discord message ID to track for deletion
            expires_at: Unix timestamp when message should be deleted

        Implementation:
          - Appends record to state["announcements"] list
          - Persists state to database
          - All values are cast to proper types (int/float)
        """
        self._announcements().append({
            "guild_id": int(guild_id),
            "channel_id": int(channel_id),
            "message_id": int(message_id),
            "expires_at": float(expires_at),
        })
        await self._save_state()

    async def _delete_announcement_record(self, record: dict[str, Any]) -> None:
        """Delete an expired announcement message and remove its record.

        Called by _sweep_expired_announcements() for each expired record.
        Attempts to delete the Discord message, then removes the record from state.

        Args:
            record: Announcement record dict with guild_id, channel_id, message_id, expires_at

        Design:
          - Gracefully handles NotFound (already deleted by user)
          - Logs permission errors for audit trail
          - Always removes record from state, even if message delete failed
          - Handles transient HTTP errors without crashing
        """
        channel_id = int(record.get("channel_id", 0))
        message_id = int(record.get("message_id", 0))

        try:
            channel = self.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    msg = await channel.fetch_message(message_id)
                    await msg.delete()
                    log.debug("Deleted expired announcement message %s", message_id)
                except discord.NotFound:
                    # Message already deleted by user or channel purge, silently skip
                    log.debug("Announcement message %s already deleted", message_id)
                    pass
                except discord.Forbidden:
                    log.warning(
                        "No permission to delete announcement %s in #%s",
                        message_id,
                        channel.name,
                    )
        except Exception:
            log.exception("Failed deleting announcement %s", message_id)

        # Remove record from state regardless of delete outcome
        self._announcements()[:] = [
            r for r in self._announcements()
            if int(r.get("message_id", -1)) != message_id
        ]

    # ── SWEEP CLEANUP ─────────────────────────────────────────────────────────

    async def _sweep_expired_announcements(self) -> None:
        """Remove expired announcement records and delete their Discord messages.

        Called every 90 seconds from _refresh_loop() in live-feeds feature.
        Finds all announcements with expires_at timestamp <= current time and deletes them.

        Implementation:
          - Filters expired announcements by comparing expires_at to time.time()
          - Calls _delete_announcement_record() for each expired record
          - Persists state only if any records were actually removed
          - Logs count of expired announcements for monitoring

        Expiry calculation:
          - Record created with expires_at = now + 1800 (30 minutes)
          - When expires_at <= current time.time(), record is considered expired
        """
        now = time.time()
        expired = [
            r for r in list(self._announcements())
            if float(r.get("expires_at", 0)) <= now
        ]

        if expired:
            log.info("Sweeping %d expired announcement(s)", len(expired))
            for record in expired:
                await self._delete_announcement_record(record)
            await self._save_state()

    # ── STARTUP CLEANUP ───────────────────────────────────────────────────────

    async def _cleanup_announcements_on_startup(self) -> None:
        """Clear all tracked announcements on bot startup.

        Called during on_ready() to clean up any announcements that persisted
        across a restart (their TTL has likely expired or the bot crashed).

        Also scans all tracked channels for orphan announcement messages
        (ones with our announcement title embed that aren't in our tracking
        list) and deletes those too.

        Implementation:
          - Deletes all tracked announcements from state
          - Scans each channel's history for orphan announcements
          - Logs summary of cleared messages

        Design:
          - Graceful failure: orphan scan errors don't crash startup
          - Handles missing permissions (Read Message History)
          - Useful for cleaning up after unexpected bot crashes
        """
        cleared = 0
        failed = 0

        # First, clean up tracked announcements from state
        stale_records = list(self._announcements())
        if stale_records:
            log.info("Startup cleanup: found %d tracked announcement(s) to clear.", len(stale_records))

        for record in stale_records:
            try:
                await self._delete_announcement_record(record)
                cleared += 1
            except Exception:
                failed += 1

        # Second, scan channels for orphan announcements (in state but not tracked)
        for guild_id_str, gs in list(self._guilds_block().items()):
            try:
                guild_id = int(guild_id_str)
            except ValueError:
                continue

            info = gs.get("information")
            if not info:
                continue

            channel = self.get_channel(int(info.get("channel_id", 0)))
            if not isinstance(channel, discord.TextChannel):
                continue

            try:
                async for msg in channel.history(limit=100):
                    # Check if this is an orphan announcement (our embed format, but not tracked)
                    if msg.embeds and ANNOUNCEMENT_TITLE in (msg.embeds[0].title or ""):
                        try:
                            await msg.delete()
                            log.info(
                                "Startup cleanup: deleted orphan announcement %s in guild %s",
                                msg.id,
                                guild_id,
                            )
                            cleared += 1
                        except (discord.Forbidden, discord.NotFound) as e:
                            log.warning(
                                "Startup cleanup: could not delete orphan %s: %s",
                                msg.id,
                                e,
                            )
                            failed += 1
            except discord.Forbidden:
                # No Read Message History permission, skip this channel
                log.debug("No Read Message History in #%s; skipping orphan scan", channel.name)
            except Exception:
                log.exception(
                    "Startup cleanup: orphan scan failed in %s/#%s",
                    guild_id,
                    getattr(channel, "name", "?"),
                )

        # Log summary
        if cleared == 0 and failed == 0:
            log.info("Startup cleanup: no stale announcements found -- channels are clean.")
        elif failed == 0:
            log.info("Startup cleanup: cleared %d stale announcement(s) successfully.", cleared)
        else:
            log.warning(
                "Startup cleanup: cleared %d announcement(s), but %d could not be deleted "
                "(check permissions).",
                cleared,
                failed,
            )

    # ── STATE MANAGEMENT (stubs to be implemented by TTRBot) ──────────────────

    def _announcements(self) -> list[dict[str, Any]]:
        """Return the announcements list from state.

        Must be implemented by subclass. Example:
            return self.state.setdefault("announcements", [])

        Returns:
            List of announcement record dicts with keys:
              - guild_id: int
              - channel_id: int
              - message_id: int
              - expires_at: float (Unix timestamp)
        """
        raise NotImplementedError("Must be implemented by subclass")

    def _guilds_block(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Return the guilds block from state.

        Must be implemented by subclass. Example:
            return self.state.setdefault("guilds", {})

        Returns:
            Dict mapping guild_id (str) to per-guild state dict
        """
        raise NotImplementedError("Must be implemented by subclass")

    async def _save_state(self) -> None:
        """Persist state changes to database.

        Must be implemented by subclass. Should save self.state to persistent storage.
        """
        raise NotImplementedError("Must be implemented by subclass")
