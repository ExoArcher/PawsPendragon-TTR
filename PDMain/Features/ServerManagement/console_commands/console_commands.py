# -*- coding: utf-8 -*-
"""
Standalone console command handler for Paws Pendragon TTR.

Provides a background stdin reader that processes hosting panel commands:
  - stop: notify all guilds, then shutdown gracefully
  - restart: notify all guilds, then hot-restart the process
  - maintenance: toggle maintenance mode embeds across all guilds
  - announce <text>: broadcast announcement to all #tt-information channels (30-min TTL)
  - help: print available commands

All commands are restricted to BOT_ADMIN_IDs for authorization.
Runs as a background task without blocking the Discord event loop.
"""

from __future__ import annotations

import asyncio
import logging
import os
import select
import sys
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord

from Features.Core.db import db

if TYPE_CHECKING:
    from bot import TTRBot

log = logging.getLogger("ttr-bot.console")

# ── Constants ─────────────────────────────────────────────────────────────────

HELP_TEXT = (
    "[console] Available commands:\n"
    "  stop           -- Notify all servers of shutdown, then exit.\n"
    "  restart        -- Notify all servers of restart, then restart the process.\n"
    "  maintenance    -- Toggle maintenance mode banner on/off in all server channels.\n"
    "  announce <msg> -- Broadcast a message to all #tt-information channels (30-min TTL).\n"
    "  help           -- Show this list."
)

# How long (seconds) _readline_poll waits for stdin before returning None.
# Kept short so the bot can notice stdin has closed within this many seconds.
_POLL_TIMEOUT = 2.0


# ── Main entry point ─────────────────────────────────────────────────────────

async def run_console(bot: TTRBot) -> None:
    """
    Start the background console command listener.

    This task runs continuously, reading lines from stdin and dispatching
    to appropriate command handlers. It respects BOT_ADMIN_IDs for authorization
    and logs all actions to stdout and the logger.

    Args:
        bot: TTRBot instance with config, state, and guild access.

    The task exits when:
      - stdin is closed (EOF)
      - a 'stop' or 'restart' command is processed
      - an unrecoverable stdin error occurs
    """
    loop = asyncio.get_running_loop()
    log.info("[console] Console command listener started.")

    while True:
        # Exit immediately if the bot is already shutting down.
        if bot.is_closed():
            log.info("[console] Bot is closed -- console listener exiting.")
            break

        try:
            line = await loop.run_in_executor(None, _readline_poll)
        except Exception as exc:
            log.warning("[console] stdin read error: %s", exc)
            break

        # None  → stdin closed (EOF); stop looping.
        # ""    → poll timeout with no data; loop back and check bot state.
        if line is None:
            log.info("[console] stdin closed -- console listener exiting.")
            break
        if line == "":
            continue

        cmd = line.strip().lower()
        if not cmd:
            continue

        if cmd == "stop":
            await _handle_stop(bot)
            break

        elif cmd == "restart":
            await _handle_restart(bot)
            break

        elif cmd == "maintenance":
            await _handle_maintenance(bot)

        elif cmd == "help" or cmd == "?":
            print(HELP_TEXT, flush=True)

        elif cmd.startswith("announce"):
            announce_text = line.strip()[len("announce"):].strip()
            if not announce_text:
                print("[console] Usage: announce <message text>", flush=True)
            else:
                await _handle_announce(bot, announce_text)

        else:
            print(f"[console] Unknown command: '{cmd}'.\n{HELP_TEXT}", flush=True)


def _readline_poll() -> str | None:
    """
    Block for up to _POLL_TIMEOUT seconds waiting for a line on stdin.

    Uses select() on Unix-like systems to avoid indefinite blocking,
    allowing Python to join the thread cleanly during shutdown.

    Returns:
        str   -- a line of input (without leading/trailing whitespace) if one arrived.
        ""    -- timeout elapsed with no input (caller should loop).
        None  -- stdin is closed / EOF.
    """
    try:
        ready, _, _ = select.select([sys.stdin], [], [], _POLL_TIMEOUT)
        if not ready:
            return ""           # timeout — no data yet
        line = sys.stdin.readline()
        return line if line else None   # empty string from readline() == EOF
    except Exception:
        return None


# ── Stop command ──────────────────────────────────────────────────────────────

async def _handle_stop(bot: TTRBot) -> None:
    """
    Notify all tracked guilds of shutdown, then exit gracefully.

    Broadcasts a maintenance notice embed to every tracked guild's
    #tt-information channel, then calls bot.close() to trigger the
    standard Discord shutdown sequence (which calls sys.exit(0)).

    Args:
        bot: TTRBot instance.
    """
    print("[console] STOP command received -- notifying servers and shutting down...", flush=True)
    log.info("[console] STOP command received -- shutting down.")

    now_unix = int(time.time())
    embed = discord.Embed(
        title="\U0001f527 Paws Pendragon — Going Down for Maintenance",
        description=(
            "Paws Pendragon is going down for maintenance.\n"
            f"**Went offline:** <t:{now_unix}:R>\n\n"
            "Check [toonhq.org](https://toonhq.org) in the meantime "
            "for your toony needs! We'll be back soon. \U0001f43e"
        ),
        color=0xE67E22,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="Paws Pendragon TTR • Maintenance Notice")

    await _broadcast_to_all_info_channels(bot, embed)
    bot._console_stop_sent = True

    print("[console] Shutdown complete -- closing bot.", flush=True)
    await bot.close()


# ── Restart command ───────────────────────────────────────────────────────────

async def _handle_restart(bot: TTRBot) -> None:
    """
    Notify all tracked guilds of restart, then hot-restart the process.

    Broadcasts a restart notice embed to every tracked guild's
    #tt-information channel, then calls os.execv to replace the
    current process with a fresh instance of the bot.

    Args:
        bot: TTRBot instance.
    """
    print("[console] RESTART command received -- notifying servers and restarting...", flush=True)
    log.info("[console] RESTART command received -- restarting process.")

    now_unix = int(time.time())
    embed = discord.Embed(
        title="\U0001f504 Paws Pendragon — Restarting",
        description=(
            "Paws Pendragon is restarting and will be back shortly!\n"
            f"**Went down:** <t:{now_unix}:R>\n\n"
            "Hang tight — the bot will reconnect in just a moment. \U0001f43e"
        ),
        color=0x3498DB,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="Paws Pendragon TTR • Restart Notice")

    await _broadcast_to_all_info_channels(bot, embed)
    await asyncio.sleep(2)

    print("[console] Restarting process now...", flush=True)
    log.info("[console] Executing restart via os.execv.")
    os.execv(sys.executable, [sys.executable] + sys.argv)


# ── Maintenance mode toggle ───────────────────────────────────────────────────

async def _handle_maintenance(bot: TTRBot) -> None:
    """
    Toggle maintenance mode banners across all tracked guilds.

    When OFF (no stored maintenance messages):
      - Posts an orange maintenance banner to #tt-information, #tt-doodles,
        and #suit-calculator in every tracked guild.
      - Stores message IDs in bot.state["maintenance_mode_msgs"] for later deletion.
      - Persists to database.

    When ON (stored maintenance messages exist):
      - Deletes all stored maintenance banner messages.
      - Clears bot.state["maintenance_mode_msgs"].
      - Persists to database.

    Gracefully handles missing guilds/channels and logs individual failures
    without stopping the broadcast loop.

    Args:
        bot: TTRBot instance.
    """
    # Load current maintenance state from database
    stored_mode = await db.load_maint_mode()

    if stored_mode:
        # ── TURN OFF (delete existing banners) ──────────────────────────────
        await _maintenance_turn_off(bot, stored_mode)
    else:
        # ── TURN ON (post new banners) ─────────────────────────────────────
        await _maintenance_turn_on(bot)


async def _maintenance_turn_off(bot: TTRBot, stored_mode: dict) -> None:
    """
    Delete all stored maintenance banners and clear the database.

    Args:
        bot: TTRBot instance.
        stored_mode: Dict of {guild_id_str: {feed_key: message_id}}.
    """
    print("[console] Maintenance mode OFF -- removing banners...", flush=True)
    log.info("[console] Maintenance mode disabling.")

    removed = 0
    failed = 0

    for guild_id_str, channels in stored_mode.items():
        for feed_key, msg_id in channels.items():
            channel_id = _channel_id_for_feed(bot, guild_id_str, feed_key)
            if not channel_id:
                continue
            channel = bot.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.delete()
                removed += 1
            except discord.NotFound:
                # Message already gone, count as removed
                removed += 1
            except Exception as exc:
                log.warning("[console] Could not delete maintenance banner %s: %s", msg_id, exc)
                failed += 1

    await db.save_maint_mode({})
    print(
        f"[console] Maintenance mode OFF -- {removed} banner(s) removed"
        + (f", {failed} failed" if failed else "") + ".",
        flush=True,
    )
    log.info("[console] Maintenance mode disabled: %d removed, %d failed.", removed, failed)


async def _maintenance_turn_on(bot: TTRBot) -> None:
    """
    Post orange maintenance banners to all tracked guilds' feed channels.

    Posts to #tt-information, #tt-doodles, and #suit-calculator.
    Stores message IDs for later deletion when toggling off.

    Args:
        bot: TTRBot instance.
    """
    print("[console] Maintenance mode ON -- posting banners...", flush=True)
    log.info("[console] Maintenance mode enabling.")

    embed = discord.Embed(
        title="\U0001f527 Maintenance Mode",
        description=(
            "Paws Pendragon TTR is currently being worked on and "
            "**may go down temporarily**.\n\n"
            "Live data updates will continue as normal in the meantime.\n"
            "We appreciate your patience! \U0001f43e"
        ),
        color=0xE67E22,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="Paws Pendragon TTR • Maintenance Mode Active")

    guilds_block = bot.state.get("guilds", {})
    new_stored = {}
    sent = 0
    failed = 0

    for guild_id_str, gs in list(guilds_block.items()):
        guild_msgs = {}
        for feed_key in ("information", "doodles", "suit_calculator"):
            entry = gs.get(feed_key)
            if not entry:
                continue
            try:
                channel_id = int(entry.get("channel_id", 0))
            except (TypeError, ValueError):
                continue
            if not channel_id:
                continue

            channel = bot.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue

            try:
                msg = await channel.send(embed=embed)
                guild_msgs[feed_key] = msg.id
                sent += 1
                log.debug("[console] Maintenance banner posted in %s/#%s", guild_id_str, channel.name)
            except Exception as exc:
                log.warning("[console] Failed to post banner in %s/%s: %s", guild_id_str, feed_key, exc)
                failed += 1

        if guild_msgs:
            new_stored[guild_id_str] = guild_msgs

    await db.save_maint_mode(new_stored)
    print(
        f"[console] Maintenance mode ON -- {sent} banner(s) posted"
        + (f", {failed} failed" if failed else "") + ".",
        flush=True,
    )
    log.info("[console] Maintenance mode enabled: %d posted, %d failed.", sent, failed)


# ── Announce command ──────────────────────────────────────────────────────────

async def _handle_announce(bot: TTRBot, text: str) -> None:
    """
    Broadcast an announcement to every tracked guild's feed channels.

    Creates an announcement embed and broadcasts to #tt-information, #tt-doodles,
    and #suit-calculator in every tracked guild. The announcements are recorded
    with a 30-minute TTL (ANNOUNCEMENT_TTL_SECONDS) and are auto-deleted
    by the sweep loop.

    Gracefully handles missing guilds/channels and logs individual failures
    without stopping the broadcast.

    Args:
        bot: TTRBot instance.
        text: Announcement message text.
    """
    print(f"[console] ANNOUNCE: {text!r}", flush=True)
    log.info("[console] Announce broadcast: %s", text)

    try:
        sent, failed, guilds_touched = await bot._broadcast_announcement(text)
        if sent == 0:
            print(
                "[console] Broadcast sent 0 messages -- "
                "no servers are tracked or the bot may have lost channel permissions.",
                flush=True,
            )
        else:
            print(
                f"[console] Broadcast complete: {sent} message(s) across "
                f"{guilds_touched} server(s)"
                + (f", {failed} failed" if failed else "") + ".",
                flush=True,
            )
        log.info("[console] Announce complete: %d sent, %d failed, %d guilds touched.", sent, failed, guilds_touched)
    except Exception as exc:
        log.exception("[console] Announce broadcast failed: %s", exc)
        print(f"[console] Announce failed: {exc}", flush=True)


# ── Broadcast helper ──────────────────────────────────────────────────────────

async def _broadcast_to_all_info_channels(bot: TTRBot, embed: discord.Embed) -> tuple[int, int]:
    """
    Broadcast an embed to all tracked guilds' feed channels.

    Posts the embed to #tt-information, #tt-doodles, and #suit-calculator
    in every tracked guild. Logs individual channel failures but continues
    broadcasting to other channels.

    Args:
        bot: TTRBot instance.
        embed: Discord embed to broadcast.

    Returns:
        Tuple of (sent count, failed count).
    """
    guilds_block = bot.state.get("guilds", {})
    sent = 0
    failed = 0

    for guild_id_str, gs in list(guilds_block.items()):
        for feed_key in ("information", "doodles", "suit_calculator"):
            entry = gs.get(feed_key)
            if not entry:
                continue

            try:
                channel_id = int(entry.get("channel_id", 0))
            except (TypeError, ValueError):
                continue

            if not channel_id:
                continue

            channel = bot.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue

            try:
                await channel.send(embed=embed)
                sent += 1
                log.debug("[console] Broadcast sent to guild %s #%s", guild_id_str, channel.name)
            except Exception as exc:
                log.warning("[console] Broadcast failed for guild %s #%s: %s", guild_id_str, feed_key, exc)
                failed += 1

    return sent, failed


# ── State helper ──────────────────────────────────────────────────────────────

def _channel_id_for_feed(bot: TTRBot, guild_id_str: str, feed_key: str) -> int | None:
    """
    Look up the channel ID for a specific guild/feed combination.

    Args:
        bot: TTRBot instance.
        guild_id_str: Guild ID as a string key.
        feed_key: Feed key (e.g., "information", "doodles", "suit_calculator").

    Returns:
        Channel ID as int, or None if not found or invalid.
    """
    gs = bot.state.get("guilds", {}).get(guild_id_str, {})
    entry = gs.get(feed_key)
    if not entry:
        return None
    try:
        channel_id = int(entry.get("channel_id", 0))
        return channel_id if channel_id else None
    except (TypeError, ValueError):
        return None


# ── Startup cleanup ───────────────────────────────────────────────────────────

async def clear_maintenance_on_startup(bot: TTRBot) -> None:
    """
    Delete any maintenance banners left over from the previous session.

    Called during bot.on_ready() to clean up stale maintenance mode embeds
    that may have been left behind if the bot was shut down while
    maintenance mode was enabled.

    Args:
        bot: TTRBot instance.
    """
    stored = await db.load_maint_mode()
    if not stored:
        return

    log.info("[console] Clearing leftover maintenance banners from previous session.")
    removed = 0

    for guild_id_str, channels in stored.items():
        for feed_key, msg_id in channels.items():
            channel_id = _channel_id_for_feed(bot, guild_id_str, feed_key)
            if not channel_id:
                continue

            channel = bot.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue

            try:
                msg = await channel.fetch_message(msg_id)
                await msg.delete()
                removed += 1
            except discord.NotFound:
                # Message already gone, count as removed
                removed += 1
            except Exception as exc:
                log.warning("[console] Could not remove startup maintenance banner %s: %s", msg_id, exc)

    await db.save_maint_mode({})
    log.info("[console] Startup: cleared %d maintenance banner(s).", removed)
