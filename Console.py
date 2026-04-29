# console.py
"""
Server hosting console command handler for LanceAQuack TTR.

Reads commands from stdin (the Cybrancee hosting panel console).

Available commands:
    stop     -- Broadcasts a maintenance notice to all servers, then shuts the bot down.
    restart  -- Broadcasts a "restarting" notice to all servers, then hot-restarts the process.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import logging
from datetime import datetime, timezone

import discord

log = logging.getLogger("ttr-bot.console")

COMMANDS = ("stop", "restart")

HELP_TEXT = (
    "[console] Available commands:\n"
    "  stop    -- Notify all servers of maintenance, then shut down.\n"
    "  restart -- Notify all servers of a restart, then restart the process."
)


async def run_console(bot: "TTRBot") -> None:  # noqa: F821  (forward ref, imported at runtime)
    """
    Background coroutine that listens to stdin for console commands.
    Runs until the bot closes or stdin is exhausted.
    Attach this in on_ready with:  asyncio.create_task(run_console(self))
    """
    loop = asyncio.get_running_loop()
    log.info("[console] Console command listener started. Type 'stop' or 'restart'.")

    while True:
        try:
            line: str = await loop.run_in_executor(None, _readline_safe)
        except Exception as exc:
            log.warning("[console] stdin read error: %s", exc)
            break

        if line is None:
            # EOF / stdin closed
            log.info("[console] stdin closed -- console listener exiting.")
            break

        cmd = line.strip().lower()

        if not cmd:
            continue

        if cmd == "stop":
            await _handle_stop(bot)
            break  # process is about to end

        elif cmd == "restart":
            await _handle_restart(bot)
            break  # process is about to be replaced

        elif cmd in ("help", "?"):
            print(HELP_TEXT, flush=True)

        else:
            print(
                f"[console] Unknown command: '{cmd}'. {HELP_TEXT}",
                flush=True,
            )


def _readline_safe() -> str | None:
    """Blocking stdin read; returns None on EOF."""
    try:
        line = sys.stdin.readline()
        return line if line else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Stop
# ---------------------------------------------------------------------------

async def _handle_stop(bot: "TTRBot") -> None:  # noqa: F821
    """
    1. Broadcast a maintenance-down embed to every tracked server.
    2. Set the skip flag so bot.close() doesn't send a second notice.
    3. Call bot.close().
    """
    print("[console] STOP command received -- notifying servers and shutting down...", flush=True)
    log.info("[console] STOP command received.")

    now_unix = int(time.time())

    embed = discord.Embed(
        title="🔧 LanceAQuack — Going Down for Maintenance",
        description=(
            "LanceAQuack is going down for maintenance.\n"
            f"**Went offline:** <t:{now_unix}:R>\n\n"
            "Check [toonhq.org](https://toonhq.org) in the meantime "
            "for your toony needs! We'll be back soon. 🐾"
        ),
        color=0xE67E22,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="LanceAQuack TTR • Maintenance Notice")

    await _broadcast_to_all_info_channels(bot, embed)

    # Tell close() not to fire its own maintenance broadcast (avoid duplicate).
    bot._console_stop_sent = True

    await bot.close()


# ---------------------------------------------------------------------------
# Restart
# ---------------------------------------------------------------------------

async def _handle_restart(bot: "TTRBot") -> None:  # noqa: F821
    """
    1. Broadcast a "restarting" embed to every tracked server.
    2. Hot-restart the process with os.execv (same pattern as the auto-updater).
    """
    print("[console] RESTART command received -- notifying servers and restarting...", flush=True)
    log.info("[console] RESTART command received.")

    now_unix = int(time.time())

    embed = discord.Embed(
        title="🔄 LanceAQuack — Restarting",
        description=(
            "LanceAQuack is restarting and will be back shortly!\n"
            f"**Went down:** <t:{now_unix}:R>\n\n"
            "Hang tight — the bot will reconnect in just a moment. 🐾"
        ),
        color=0x3498DB,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="LanceAQuack TTR • Restart Notice")

    await _broadcast_to_all_info_channels(bot, embed)

    # Give Discord a moment to deliver all the messages before the process dies.
    await asyncio.sleep(2)

    print("[console] Restarting process now...", flush=True)
    log.info("[console] Executing restart via os.execv.")

    # Replace this process with a fresh copy — same technique as the auto-updater.
    os.execv(sys.executable, [sys.executable] + sys.argv)


# ---------------------------------------------------------------------------
# Shared broadcast helper
# ---------------------------------------------------------------------------

async def _broadcast_to_all_info_channels(bot: "TTRBot", embed: discord.Embed) -> None:  # noqa: F821
    """
    Send *embed* to every tracked guild's #tt-information channel.
    Does NOT store the message ID for auto-deletion — these notices should persist
    until the bot clears maintenance messages on next startup (stop) or
    until the restart replaces them (restart).
    """
    guilds_block: dict = bot.state.get("guilds", {})
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
        f"[console] Broadcast complete — {sent} server(s) notified, {failed} failed.",
        flush=True,
    )
