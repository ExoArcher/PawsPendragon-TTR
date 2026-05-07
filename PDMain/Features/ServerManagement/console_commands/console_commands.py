# -*- coding: utf-8 -*-
"""Console command handler for Paws Pendragon TTR.

Console-only commands (no Discord slash commands):
  stop / s / restart / r / maintenance [msg] / m / maint / announce / a
  ban <id> <reason> / unban <id>
  guildadd <id> / guildremove <id> / forcerefresh
  help / h
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import select
import sys
import time
from datetime import datetime, timezone
from time import time as _time
from typing import TYPE_CHECKING

import discord

from Features.Core.db import db
from Features.Core.config.config import update_env_var, read_env_var
from Features.Core.config.constants import ANNOUNCE_MAX_PER_PERIOD, ANNOUNCE_PERIOD_SECONDS
from Features.Core.formatters.formatters import (
    build_maintenance_embed,
    build_stop_embed,
    build_restart_embed,
)

if TYPE_CHECKING:
    from bot import TTRBot

log = logging.getLogger("ttr-bot.console")


# ── Rate Limiting and Sanitization ────────────────────────────────────────────

class RateLimit:
    """Simple sliding-window rate limiter."""
    def __init__(self, max_per_period: int, period_seconds: int) -> None:
        self.max_per_period = max_per_period
        self.period_seconds = period_seconds
        self._calls: list[float] = []

    def is_allowed(self) -> bool:
        now = _time()
        self._calls = [t for t in self._calls if now - t < self.period_seconds]
        if len(self._calls) < self.max_per_period:
            self._calls.append(now)
            return True
        return False


def _sanitize_announce_text(text: str, max_length: int = 1000) -> str:
    """Sanitize announcement text before broadcasting to Discord."""
    text = text[:max_length]
    text = re.sub(r"@(everyone|here)", r"@​\1", text)
    text = re.sub(r"\|\|", "", text)
    text = re.sub(r"```", "", text)
    return text


_announce_rate_limiter = RateLimit(
    max_per_period=ANNOUNCE_MAX_PER_PERIOD,
    period_seconds=ANNOUNCE_PERIOD_SECONDS,
)


# ── ALIAS MAPPING ─────────────────────────────────────────────────────────────
# Maps short command names and aliases to canonical handler names (case-insensitive)

COMMAND_ALIASES = {
    "stop": "stop",
    "s": "stop",
    "restart": "restart",
    "r": "restart",
    "maintenance": "maintenance",
    "m": "maintenance",
    "maint": "maintenance",
    "announce": "announce",
    "a": "announce",
    "help": "help",
    "h": "help",
    "?": "help",
    "ban": "ban",
    "unban": "unban",
    "guildadd": "guildadd",
    "guildremove": "guildremove",
    "forcerefresh": "forcerefresh",
}

HELP_TEXT = (
    "[console] Available commands:\n"
    "  stop (s)               -- Notify all channels of shutdown, then exit.\n"
    "  restart (r)            -- Notify all channels of restart, then restart.\n"
    "  maintenance (m)        -- Toggle maintenance banner (optional message).\n"
    "  maint                  -- Alias for maintenance.\n"
    "  announce (a)           -- Broadcast to all tracked channels (30-min TTL).\n"
    "  ban <id> <reason>      -- Ban a user by ID.\n"
    "  unban <id>             -- Remove a ban by user ID.\n"
    "  guildadd <id>          -- Add a guild to the allowlist (hot-reload).\n"
    "  guildremove <id>       -- Teardown, remove from allowlist, and leave a guild.\n"
    "  forcerefresh           -- Wipe and re-post all tracked messages across all servers.\n"
    "  help (h, ?)            -- Show this list."
)

_POLL_TIMEOUT = 2.0


async def run_console(bot: TTRBot) -> None:
    loop = asyncio.get_running_loop()
    log.info("[console] Console command listener started.")
    while True:
        if bot.is_closed():
            break
        try:
            line = await loop.run_in_executor(None, _readline_poll)
        except Exception as exc:
            log.warning("[console] stdin read error: %s", exc)
            break
        if line is None:
            break
        if line == "":
            continue

        raw = line.strip()
        if not raw:
            continue

        # Parse command and args
        cmd_lower = raw.split(None, 1)[0].lower()
        args = raw[len(raw.split(None, 1)[0]):].strip() if " " in raw else ""

        # Resolve alias to canonical command
        canonical_cmd = COMMAND_ALIASES.get(cmd_lower)
        if not canonical_cmd:
            print(f"[console] Unknown command: '{cmd_lower}'.\n{HELP_TEXT}", flush=True)
            continue

        # Log command execution
        log.info("[console] Command: %s (alias: %s) | args: %s", canonical_cmd, cmd_lower, args or "(none)")
        print(f"[console] > {cmd_lower} {args}".strip(), flush=True)

        # Dispatch to handler
        if canonical_cmd == "stop":
            await _handle_stop(bot)
            break
        elif canonical_cmd == "restart":
            await _handle_restart(bot)
            break
        elif canonical_cmd == "maintenance":
            await _handle_maintenance(bot, args or None)
        elif canonical_cmd == "help":
            print(HELP_TEXT, flush=True)
        elif canonical_cmd == "announce":
            if not args:
                print("[console] Usage: announce <message text>", flush=True)
            else:
                await _handle_announce(bot, args)
        elif canonical_cmd == "ban":
            await _handle_ban(bot, args)
        elif canonical_cmd == "unban":
            await _handle_unban(bot, args)
        elif canonical_cmd == "guildadd":
            await _handle_guildadd(bot, args)
        elif canonical_cmd == "guildremove":
            await _handle_guildremove(bot, args)
        elif canonical_cmd == "forcerefresh":
            await _handle_forcerefresh(bot)


def _readline_poll() -> str | None:
    try:
        ready, _, _ = select.select([sys.stdin], [], [], _POLL_TIMEOUT)
        if not ready:
            return ""
        line = sys.stdin.readline()
        return line if line else None
    except Exception:
        return None


# ── Stop ──────────────────────────────────────────────────────────────────────

async def _handle_stop(bot: TTRBot) -> None:
    print("[console] STOP -- notifying all tracked channels and shutting down...", flush=True)
    log.info("[console] STOP command executed. Broadcasting shutdown embed to all tracked channels.")

    embed = build_stop_embed()

    # Broadcast to all 3 tracked channels across all guilds
    sent, failed = await _broadcast_to_all_channels(bot, embed)
    print(f"[console] Shutdown notification sent to {sent} channel(s)" + (f", {failed} failed" if failed else "") + ".", flush=True)

    # Small delay to ensure messages are sent before shutdown
    await asyncio.sleep(1)
    await bot.close()


# ── Restart ───────────────────────────────────────────────────────────────────

async def _handle_restart(bot: TTRBot) -> None:
    print("[console] RESTART -- notifying all tracked channels and restarting...", flush=True)
    log.info("[console] RESTART command executed. Broadcasting restart embed to all tracked channels.")

    embed = build_restart_embed()

    # Broadcast to all 3 tracked channels across all guilds
    sent, failed = await _broadcast_to_all_channels(bot, embed)
    print(f"[console] Restart notification sent to {sent} channel(s)" + (f", {failed} failed" if failed else "") + ".", flush=True)

    # Wait for messages to send and settle before restarting
    await asyncio.sleep(2)
    os.execv(sys.executable, [sys.executable] + sys.argv)


# ── Maintenance ───────────────────────────────────────────────────────────────

async def _handle_maintenance(bot: TTRBot, msg: str | None) -> None:
    stored_mode = await db.load_maint_mode()
    if stored_mode:
        await _maintenance_turn_off(bot, stored_mode)
    else:
        await _maintenance_turn_on(bot, msg)


async def _maintenance_turn_off(bot: TTRBot, stored_mode: dict) -> None:
    print("[console] Maintenance OFF -- removing banners from all tracked channels...", flush=True)
    log.info("[console] Maintenance OFF. Removing maintenance embeds from all tracked channels.")
    removed = 0
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
                removed += 1
            except Exception as exc:
                log.warning("[console] Could not delete maintenance banner %s: %s", msg_id, exc)
    await db.save_maint_mode({})
    print(f"[console] Maintenance OFF -- {removed} banner(s) removed from all tracked channels.", flush=True)


async def _maintenance_turn_on(bot: TTRBot, custom_msg: str | None) -> None:
    print("[console] Maintenance ON -- posting embeds to all tracked channels...", flush=True)
    log.info("[console] Maintenance ON. Broadcasting maintenance embed to all tracked channels.")

    embed = build_maintenance_embed()

    # Broadcast to all 3 tracked channels across all guilds and store message IDs
    sent = 0
    failed = 0
    maint_mode: dict = {}

    guilds_block = bot.state.get("guilds", {})
    for guild_id_str, gs in list(guilds_block.items()):
        guild_maint: dict = {}
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
                guild_maint[feed_key] = msg.id
                sent += 1
            except Exception as exc:
                log.warning("[console] Maintenance broadcast failed for %s/%s: %s", guild_id_str, feed_key, exc)
                failed += 1
        if guild_maint:
            maint_mode[guild_id_str] = guild_maint

    await db.save_maint_mode(maint_mode)
    print(f"[console] Maintenance ON -- {sent} banner(s) posted to all tracked channels" + (f", {failed} failed" if failed else "") + ".", flush=True)
    log.info("[console] Maintenance embeds posted. Sent: %d, Failed: %d", sent, failed)


# ── Announce ──────────────────────────────────────────────────────────────────

async def _handle_announce(bot: TTRBot, text: str) -> None:
    if not text:
        print("[console] Usage: announce <message text>", flush=True)
        return

    if not _announce_rate_limiter.is_allowed():
        print(
            f"[console] Announce rate limited — max 1 per {ANNOUNCE_PERIOD_SECONDS}s",
            flush=True,
        )
        return

    sanitized = _sanitize_announce_text(text)
    print(f"[console] ANNOUNCE: {sanitized!r}", flush=True)
    try:
        sent, failed, guilds_touched = await bot._broadcast_announcement(sanitized)
        print(
            f"[console] Broadcast complete: {sent} message(s) across "
            f"{guilds_touched} server(s)"
            + (f", {failed} failed" if failed else "") + ".",
            flush=True,
        )
    except Exception as exc:
        print(f"[console] Announce failed: {exc}", flush=True)


# ── Ban ───────────────────────────────────────────────────────────────────────

async def _handle_ban(bot: TTRBot, args: str) -> None:
    parts = args.split(None, 1)
    if len(parts) < 2:
        print("[console] Usage: ban <UserID> <reason>", flush=True)
        return
    uid_str, reason = parts[0].strip(), parts[1].strip()
    try:
        uid = int(uid_str)
    except ValueError:
        print(f"[console] Invalid UserID: {uid_str!r}", flush=True)
        return

    banned_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    # Phase 3: Write to SQLite immediately
    try:
        await db.add_ban(uid, reason, banned_at)
    except Exception as exc:
        print(f"[console] Failed to write ban to database: {exc}", flush=True)
        log.exception("[console] Failed to ban user %s", uid)
        return

    # Update in-memory cache immediately
    if hasattr(bot, "_user_system"):
        bot._user_system.banned_users[uid_str] = {
            "reason": reason, "banned_at": banned_at,
            "banned_by": "console", "banned_by_id": None,
        }

    # Log to audit_log
    try:
        await db.log_audit_event(
            event_type="banned_user_added",
            details={"user_id": uid, "reason": reason},
        )
    except Exception as exc:
        log.warning("[console] Failed to log audit event: %s", exc)

    print(f"✓ User {uid} banned: {reason}", flush=True)
    print("⚠️ .env update deferred to next periodic check", flush=True)
    log.info("[console] Banned user %s: %s", uid, reason)


# ── Unban ─────────────────────────────────────────────────────────────────────

async def _handle_unban(bot: TTRBot, uid_str: str) -> None:
    uid_str = uid_str.strip()
    try:
        uid = int(uid_str)
    except ValueError:
        print(f"[console] Invalid UserID: {uid_str!r}", flush=True)
        return

    # Phase 3: Delete from SQLite immediately
    try:
        removed = await db.remove_ban(uid)
    except Exception as exc:
        print(f"[console] Failed to remove ban from database: {exc}", flush=True)
        log.exception("[console] Failed to unban user %s", uid)
        return

    # Update in-memory cache immediately
    if hasattr(bot, "_user_system"):
        bot._user_system.banned_users.pop(uid_str, None)

    # Log to audit_log
    try:
        await db.log_audit_event(
            event_type="banned_user_removed",
            details={"user_id": uid},
        )
    except Exception as exc:
        log.warning("[console] Failed to log audit event: %s", exc)

    if removed:
        print(f"✓ User {uid} unbanned", flush=True)
        print("⚠️ .env update deferred to next periodic check", flush=True)
    else:
        print(f"⚠️ User {uid} was not in the ban list.", flush=True)
    log.info("[console] Unbanned user %s", uid)


# ── GuildAdd ──────────────────────────────────────────────────────────────────

async def _handle_guildadd(bot: TTRBot, gid_str: str) -> None:
    gid_str = gid_str.strip()
    try:
        gid = int(gid_str)
    except ValueError:
        print(f"[console] Invalid GuildID: {gid_str!r}", flush=True)
        return

    # Phase 3: Write to SQLite immediately (allowlist table)
    try:
        await db.add_guild_to_allowlist(gid)
    except Exception as exc:
        print(f"[console] Failed to add guild to allowlist: {exc}", flush=True)
        log.exception("[console] Failed to add guild %s to allowlist", gid)
        return

    # Update GUILD_ALLOWLIST cache immediately (bot.state["allowlist"])
    runtime_allowlist = bot.state.setdefault("allowlist", [])
    if gid not in runtime_allowlist:
        runtime_allowlist.append(gid)

    # Log to audit_log
    try:
        await db.log_audit_event(
            event_type="allowed_guild_added",
            details={"guild_id": gid},
        )
    except Exception as exc:
        log.warning("[console] Failed to log audit event: %s", exc)

    print(f"✓ Guild {gid} added to allowlist", flush=True)
    print("⚠️ .env update deferred to next periodic check", flush=True)
    log.info("[console] Added guild %s to allowlist", gid)


# ── GuildRemove ───────────────────────────────────────────────────────────────

async def _handle_guildremove(bot: TTRBot, gid_str: str) -> None:
    gid_str = gid_str.strip()
    try:
        gid = int(gid_str)
    except ValueError:
        print(f"[console] Invalid GuildID: {gid_str!r}", flush=True)
        return

    guild = bot.get_guild(gid)
    if guild is None:
        print(f"[console] Bot is not in guild {gid} -- removing from allowlist only.", flush=True)
    else:
        print(f"[console] GuildRemove: tearing down {guild.name} ({gid})...", flush=True)
        await bot._run_teardown(guild, bot.user)

    # Phase 3: Delete from SQLite immediately (allowlist table)
    try:
        removed_from_allowlist = await db.remove_guild_from_allowlist(gid)
    except Exception as exc:
        print(f"[console] Failed to remove guild from allowlist: {exc}", flush=True)
        log.exception("[console] Failed to remove guild %s from allowlist", gid)
        removed_from_allowlist = False

    # Phase 3: Delete from SQLite guild_feeds and associated entries (same as /pdteardown protocol)
    try:
        deleted_feeds = await db.delete_guild_feeds(gid)
    except Exception as exc:
        print(f"[console] Failed to delete guild feeds: {exc}", flush=True)
        log.warning("[console] Failed to delete guild feeds for %s: %s", gid, exc)
        deleted_feeds = False

    # Update GUILD_ALLOWLIST cache immediately (bot.state["allowlist"])
    runtime = bot.state.setdefault("allowlist", [])
    if gid in runtime:
        runtime.remove(gid)

    # Log to audit_log
    try:
        await db.log_audit_event(
            event_type="allowed_guild_removed",
            details={"guild_id": gid},
        )
    except Exception as exc:
        log.warning("[console] Failed to log audit event: %s", exc)

    # Leave the guild if still in it
    if guild:
        try:
            await guild.leave()
        except Exception as exc:
            log.warning("[console] Failed to leave guild %s: %s", gid, exc)

    print(f"✓ Guild {gid} removed from allowlist and feeds", flush=True)
    print("⚠️ .env update deferred to next periodic check", flush=True)
    log.info("[console] Removed guild %s from allowlist and feeds", gid)


# ── ForceRefresh ──────────────────────────────────────────────────────────────

async def _handle_forcerefresh(bot: TTRBot) -> None:
    print("[console] ForceRefresh -- wiping and re-posting all tracked messages...", flush=True)
    guilds_block = bot._guilds_block()
    total = 0

    for guild_id_str in list(guilds_block.keys()):
        try:
            gid = int(guild_id_str)
        except ValueError:
            continue
        guild = bot.get_guild(gid)
        if guild is None:
            print(f"  [skip] Guild {guild_id_str} not in cache.", flush=True)
            continue

        gs = guilds_block.get(guild_id_str, {})

        # Delete suit threads
        suit_threads = gs.get("suit_threads", {})
        for _fk, entry in suit_threads.items():
            if not isinstance(entry, dict):
                continue
            tid = int(entry.get("thread_id", 0))
            if not tid:
                continue
            thread = guild.get_thread(tid)
            if thread:
                try:
                    await thread.delete()
                except Exception:
                    pass

        # Delete tracked messages in all feed channels + suit_calc
        for feed_key in ("information", "doodles", "suit_calculator"):
            entry = gs.get(feed_key)
            if not isinstance(entry, dict):
                continue
            ch_id = int(entry.get("channel_id", 0))
            if not ch_id:
                continue
            channel = bot.get_channel(ch_id)
            if not isinstance(channel, discord.TextChannel):
                continue
            for mid in entry.get("message_ids", []):
                try:
                    m = await channel.fetch_message(int(mid))
                    await m.delete()
                except Exception:
                    pass

        # Clear this guild's state so _ensure_channels_for_guild reposts fresh
        guilds_block[guild_id_str] = {}

        # Re-run full setup
        try:
            await bot._ensure_channels_for_guild(guild)
            api_data = await bot._fetch_all()
            for fk in bot.config.feeds():
                try:
                    await bot._update_feed(gid, fk, api_data)
                except Exception:
                    pass
            total += 1
            print(f"  [ok] {guild.name} ({gid}) refreshed.", flush=True)
        except Exception as exc:
            print(f"  [err] {guild.name} ({gid}): {exc}", flush=True)

    await bot._save_state()

    # Log to audit_log (Phase 3)
    try:
        await db.log_audit_event(
            event_type="force_refresh",
            details={"guilds_updated_count": total},
        )
    except Exception as exc:
        log.warning("[console] Failed to log audit event: %s", exc)

    print(f"✓ Refresh complete: {total} guild(s) updated", flush=True)
    log.info("[console] ForceRefresh complete: %d guild(s) refreshed", total)


# ── Broadcast helpers ─────────────────────────────────────────────────────────

async def _broadcast_to_all_channels(bot: TTRBot, embed: discord.Embed) -> tuple[int, int]:
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
            except Exception as exc:
                log.warning("[console] Broadcast failed for %s/%s: %s", guild_id_str, feed_key, exc)
                failed += 1
    return sent, failed


def _channel_id_for_feed(bot: TTRBot, guild_id_str: str, feed_key: str) -> int | None:
    gs = bot.state.get("guilds", {}).get(guild_id_str, {})
    entry = gs.get(feed_key)
    if not entry:
        return None
    try:
        ch = int(entry.get("channel_id", 0))
        return ch if ch else None
    except (TypeError, ValueError):
        return None


# ── Startup cleanup ───────────────────────────────────────────────────────────

async def clear_maintenance_on_startup(bot: TTRBot) -> None:
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
                m = await channel.fetch_message(msg_id)
                await m.delete()
                removed += 1
            except discord.NotFound:
                removed += 1
            except Exception as exc:
                log.warning("[console] Could not remove startup banner %s: %s", msg_id, exc)
    await db.save_maint_mode({})
    log.info("[console] Startup: cleared %d maintenance banner(s).", removed)
