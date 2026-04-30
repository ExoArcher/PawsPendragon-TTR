# console.py
"""
Server hosting console command handler for LanceAQuack TTR.

Reads commands from stdin (the Cybrancee hosting panel console).

Available commands:
    stop        -- Broadcasts a maintenance notice to all servers, then shuts the bot down.
    restart     -- Broadcasts a restarting notice to all servers, then hot-restarts the process.
    maintenance -- Toggles maintenance mode on/off. Posts a banner in both
                   #tt-information and #tt-doodles in every tracked server when on.
    help        -- List available console commands.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import logging
from datetime import datetime, timezone
from pathlib import Path

import discord

log = logging.getLogger("ttr-bot.console")

COMMANDS = ("stop", "restart", "maintenance", "announce")

HELP_TEXT = (
    "[console] Available commands:\n"
    "  stop           -- Notify all servers of maintenance, then shut down.\n"
    "  restart        -- Notify all servers of a restart, then restart the process.\n"
    "  maintenance    -- Toggle maintenance mode banner on/off in all server channels.\n"
    "  announce <msg> -- Broadcast a message to every tracked server (auto-deletes in 30 min)."
)

_MAINT_MODE_FILE = Path(__file__).with_name("maintenance_mode.json")


# ---------------------------------------------------------------------------
# Console loop
# ---------------------------------------------------------------------------

async def run_console(bot) -> None:
    loop = asyncio.get_running_loop()
    log.info("[console] Console command listener started. Type 'stop', 'restart', or 'maintenance'.")

    while True:
        try:
            line = await loop.run_in_executor(None, _readline_safe)
        except Exception as exc:
            log.warning("[console] stdin read error: %s", exc)
            break

        if line is None:
            log.info("[console] stdin closed -- console listener exiting.")
            break

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

        elif cmd in ("help", "?"):
            print(HELP_TEXT, flush=True)

        elif cmd.startswith("announce"):
            announce_text = line.strip()[len("announce"):].strip()
            if not announce_text:
                print("[console] Usage: announce <message text>", flush=True)
            else:
                await _handle_announce(bot, announce_text)

        else:
            print(f"[console] Unknown command: '{cmd}'.\n{HELP_TEXT}", flush=True)


def _readline_safe():
    try:
        line = sys.stdin.readline()
        return line if line else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------

async def _handle_stop(bot) -> None:
    print("[console] STOP command received -- notifying servers and shutting down...", flush=True)
    log.info("[console] STOP command received.")

    now_unix = int(time.time())
    embed = discord.Embed(
        title="\U0001f527 LanceAQuack — Going Down for Maintenance",
        description=(
            "LanceAQuack is going down for maintenance.\n"
            f"**Went offline:** <t:{now_unix}:R>\n\n"
            "Check [toonhq.org](https://toonhq.org) in the meantime "
            "for your toony needs! We'll be back soon. \U0001f43e"
        ),
        color=0xE67E22,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="LanceAQuack TTR • Maintenance Notice")

    await _broadcast_to_all_info_channels(bot, embed)
    bot._console_stop_sent = True
    await bot.close()


# ---------------------------------------------------------------------------
# Restart
# ---------------------------------------------------------------------------

async def _handle_restart(bot) -> None:
    print("[console] RESTART command received -- notifying servers and restarting...", flush=True)
    log.info("[console] RESTART command received.")

    now_unix = int(time.time())
    embed = discord.Embed(
        title="\U0001f504 LanceAQuack — Restarting",
        description=(
            "LanceAQuack is restarting and will be back shortly!\n"
            f"**Went down:** <t:{now_unix}:R>\n\n"
            "Hang tight — the bot will reconnect in just a moment. \U0001f43e"
        ),
        color=0x3498DB,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="LanceAQuack TTR • Restart Notice")

    await _broadcast_to_all_info_channels(bot, embed)
    await asyncio.sleep(2)

    print("[console] Restarting process now...", flush=True)
    log.info("[console] Executing restart via os.execv.")
    os.execv(sys.executable, [sys.executable] + sys.argv)


# ---------------------------------------------------------------------------
# Maintenance mode toggle
# ---------------------------------------------------------------------------

async def _handle_maintenance(bot) -> None:
    """
    Toggle a persistent maintenance banner in BOTH #tt-information and #tt-doodles
    for every tracked guild.

    ON  -- sends the embed to both channels, stores message IDs in maintenance_mode.json.
    OFF -- deletes all stored banner messages and clears the file.
    """
    stored = _load_maint_mode()

    if stored:
        # --- TURN OFF ---
        print("[console] Maintenance mode OFF -- removing banners...", flush=True)
        log.info("[console] Maintenance mode disabling.")
        removed = 0
        failed = 0

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
                    removed += 1
                except Exception as exc:
                    log.warning("[console] Could not delete maintenance banner %s: %s", msg_id, exc)
                    failed += 1

        _save_maint_mode({})
        print(
            f"[console] Maintenance mode OFF -- {removed} banner(s) removed, {failed} failed.",
            flush=True,
        )

    else:
        # --- TURN ON ---
        print("[console] Maintenance mode ON -- posting banners...", flush=True)
        log.info("[console] Maintenance mode enabling.")

        embed = discord.Embed(
            title="\U0001f527 Maintenance Mode",
            description=(
                "LanceAQuack TTR is currently being worked on and "
                "**may go down temporarily**.\n\n"
                "Live data updates will continue as normal in the meantime.\n"
                "We appreciate your patience! \U0001f43e"
            ),
            color=0xE67E22,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="LanceAQuack TTR • Maintenance Mode Active")

        guilds_block = bot.state.get("guilds", {})
        new_stored = {}
        sent = 0
        failed = 0

        for guild_id_str, gs in list(guilds_block.items()):
            guild_msgs = {}
            for feed_key in ("information", "doodles"):
                entry = gs.get(feed_key)
                if not entry:
                    continue
                channel = bot.get_channel(int(entry.get("channel_id", 0)))
                if not isinstance(channel, discord.TextChannel):
                    continue
                try:
                    msg = await channel.send(embed=embed)
                    guild_msgs[feed_key] = msg.id
                    sent += 1
                    log.info(
                        "[console] Maintenance banner posted in %s/#%s",
                        guild_id_str, channel.name,
                    )
                except Exception as exc:
                    log.warning(
                        "[console] Failed to post banner in %s/%s: %s",
                        guild_id_str, feed_key, exc,
                    )
                    failed += 1

            if guild_msgs:
                new_stored[guild_id_str] = guild_msgs

        _save_maint_mode(new_stored)
        print(
            f"[console] Maintenance mode ON -- {sent} banner(s) posted, {failed} failed.",
            flush=True,
        )


# ---------------------------------------------------------------------------
# Announce
# ---------------------------------------------------------------------------

async def _handle_announce(bot, text: str) -> None:
    """
    Broadcast an announcement to every tracked guild's #tt-information channel.
    Delegates to bot._broadcast_announcement() which posts a yellow embed that
    auto-deletes after 30 minutes.
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
    except Exception as exc:
        log.exception("[console] Announce broadcast failed: %s", exc)
        print(f"[console] Announce failed: {exc}", flush=True)


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _load_maint_mode() -> dict:
    try:
        if _MAINT_MODE_FILE.exists():
            data = json.loads(_MAINT_MODE_FILE.read_text())
            if isinstance(data, dict) and data:
                return data
    except Exception:
        pass
    return {}


def _save_maint_mode(data: dict) -> None:
    try:
        _MAINT_MODE_FILE.write_text(json.dumps(data, indent=2))
    except Exception as exc:
        log.warning("[console] Could not save maintenance_mode.json: %s", exc)


def _channel_id_for_feed(bot, guild_id_str: str, feed_key: str):
    gs = bot.state.get("guilds", {}).get(guild_id_str, {})
    entry = gs.get(feed_key)
    if not entry:
        return None
    try:
        return int(entry.get("channel_id", 0)) or None
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Shared broadcast helper (info channel only -- used by stop/restart)
# ---------------------------------------------------------------------------

async def _broadcast_to_all_info_channels(bot, embed: discord.Embed) -> None:
    guilds_block = bot.state.get("guilds", {})
    sent = 0
    failed = 0

    for guild_id_str, gs in list(guilds_block.items()):
        info_entry = gs.get("information")
        if not info_entry:
            continue
        channel = bot.get_channel(int(info_entry.get("channel_id", 0)))
        if not isinstance(channel, discord.TextChannel):
            continue
        try:
            await channel.send(embed=embed)
            sent += 1
            log.info("[console] Broadcast sent to guild %s", guild_id_str)
        except Exception as exc:
            log.warning("[console] Broadcast failed for guild %s: %s", guild_id_str, exc)
            failed += 1

    print(
        f"[console] Broadcast complete -- {sent} server(s) notified, {failed} failed.",
        flush=True,
    )
