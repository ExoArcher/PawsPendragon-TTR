# -*- coding: utf-8 -*-
"""TTR Discord bot -- multi-guild live feeds for the public TTR APIs.

How it works
------------
1. The bot is invited to one or more Discord servers. Only servers
   whose ID is in the *effective* allowlist (env ``GUILD_ALLOWLIST``
   + runtime allowlist persisted in ``state.json``) are accepted; the
   bot leaves any other guild that tries to add it, DMing the owner
   with instructions to request access from ExoArcher.
2. In each allowed guild, an admin runs **``/pd-setup``** once. That
   command finds-or-creates the ``Toontown Rewritten`` category plus a
   ``#tt-information``, ``#tt-doodles``, and ``#suit-calculator`` channel,
   posts placeholder messages in each, and stores the message IDs in
   ``state.json``.
3. A background task runs every ``$REFRESH_INTERVAL`` seconds, fetches
   the TTR APIs ONCE, and edits each tracked guild's messages in place.
   Doodle embeds are only updated every 12 hours (or on /pd-refresh).
4. A separate sweep task runs every 15 minutes removing stale bot messages.

Slash commands (all users)
--------------------------
``/ttrinfo``      -- DM current district/invasion/sillymeter info. Works as a User App.
``/doodleinfo``   -- DM the full doodle list with ratings. Works as a User App.
``/helpme``       -- DM the list of available bot commands.
``/invite-app``   -- DM the link to add the bot to a personal Discord account.
``/invite-server``-- DM the link to add the bot to a Discord server.
``/pd-refresh``  -- Force an immediate refresh and sweep old messages.
``/calculate``    -- Calculate remaining suit points and get optimised activity plans.

Slash commands (Manage Channels + Manage Messages)
---------------------------------------------------
``/pd-setup``    -- Create channels and start tracking this guild.
``/pd-teardown`` -- Stop tracking this guild (channels are NOT deleted).

Console commands
----------------
``announce <text>`` -- Broadcast a message to every tracked guild (auto-deletes in 30 min).
``maintenance``     -- Toggle maintenance mode banner in all tracked guild channels.
``stop``            -- Notify all servers of shutdown, then exit.
``restart``         -- Notify all servers, then hot-restart the process.

Panel announcements
-------------------
Create ``panel_announce.txt`` in the File Manager. The bot picks it up
within 90 seconds, broadcasts it to every tracked guild, and deletes it.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Self-update from GitHub -- runs before anything else.
# Initialises the repo on first boot (works even with files already present);
# pulls on every subsequent boot and restarts if new code was downloaded.
# ---------------------------------------------------------------------------
import os as _os
import subprocess as _subprocess
import sys as _sys

_BOT_DIR = _os.path.dirname(_os.path.abspath(__file__))
_GIT_REPO = "https://github.com/ExoArcher/PawsPendragon-TTR"

try:
    if not _os.path.isdir(_os.path.join(_BOT_DIR, ".git")):
        print("[auto-update] No .git found -- initialising repo from GitHub...", flush=True)
        _subprocess.run(["git", "init"],                                cwd=_BOT_DIR, check=True, capture_output=True)
        _subprocess.run(["git", "remote", "add", "origin", _GIT_REPO],  cwd=_BOT_DIR, check=True, capture_output=True)
        _subprocess.run(["git", "fetch", "origin", "main"],              cwd=_BOT_DIR, check=True, capture_output=True)
        _subprocess.run(["git", "checkout", "-b", "main", "--track", "origin/main"],
                        cwd=_BOT_DIR, check=True, capture_output=True)
        print("[auto-update] Repo initialised. Restarting with GitHub code...", flush=True)
        _os.execv(_sys.executable, [_sys.executable] + _sys.argv)
    else:
        # Compare local HEAD vs remote to avoid infinite restart loop.
        _subprocess.run(["git", "fetch", "origin", "main"],
                        cwd=_BOT_DIR, check=True, capture_output=True)
        _local  = _subprocess.run(["git", "rev-parse", "HEAD"],
                                  cwd=_BOT_DIR, capture_output=True, text=True).stdout.strip()
        _remote = _subprocess.run(["git", "rev-parse", "origin/main"],
                                  cwd=_BOT_DIR, capture_output=True, text=True).stdout.strip()
        if _local != _remote:
            _subprocess.run(["git", "reset", "--hard", "origin/main"],
                            cwd=_BOT_DIR, check=True, capture_output=True)
            print(f"[auto-update] Updated {_local[:7]} -> {_remote[:7]}. Restarting...", flush=True)
            _os.execv(_sys.executable, [_sys.executable] + _sys.argv)
        else:
            print(f"[auto-update] Already up to date ({_local[:7]}).", flush=True)
except Exception as _e:
    print(f"[auto-update] WARNING: git update failed ({_e}). Running existing code.", flush=True)
# ---------------------------------------------------------------------------

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import discord
from discord import app_commands
from discord.ext import tasks

from config import Config
from formatters import FORMATTERS, format_doodles, format_information, format_sillymeter
from ttr_api import TTRApiClient
from Console import run_console, clear_maintenance_on_startup
from calculate import register_calculate, build_suit_calculator_embeds, build_faction_thread_embeds
from dotenv import set_key, find_dotenv as _find_dotenv

_ENV_PATH = _find_dotenv()

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("ttr-bot")

# ── Constants & paths ─────────────────────────────────────────────────────────

STATE_FILE     = Path(__file__).with_name("state.json")
STATE_VERSION  = 2
ANNOUNCE_FILE  = Path(__file__).with_name("panel_announce.txt")
TEARDOWN_LOG   = Path(__file__).with_name("teardown_log.txt")
WELCOMED_FILE  = Path(__file__).with_name("welcomed_users.json")
BANNED_FILE    = Path(__file__).with_name("banned_users.json")

ANNOUNCEMENT_TITLE       = "<:Lav:1499503216084390019> Paws Pendragon Dev Notice <:Lav:1499503216084390019>"
ANNOUNCEMENT_TTL_SECONDS = 30 * 60
DOODLE_REFRESH_INTERVAL  = 12 * 60 * 60  # 12 hours in seconds

_FACTION_ORDER        = ("sellbot", "cashbot", "lawbot", "bossbot")
_FACTION_THREAD_NAMES = {
    "sellbot": "Sellbot Suits",
    "cashbot": "Cashbot Suits",
    "lawbot":  "Lawbot Suits",
    "bossbot": "Bossbot Suits",
}

# Shown to any guild owner whose server fails the allowlist check.
CLOSED_ACCESS_MSG = (
    "Hello! Thank you for your enthusiasm to have me join your community! "
    "At this time I am only in closed access -- please DM **ExoArcher** on "
    "Discord (user ID `310233741354336257`) to request access."
)


# ─────────────────────────────────────────────────────────────────────────────
# TTRBot
# ─────────────────────────────────────────────────────────────────────────────

class TTRBot(discord.AutoShardedClient):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(intents=intents)

        self.config = config
        self.tree   = app_commands.CommandTree(self)
        self.state: dict[str, Any] = self._load_state()
        self._api: TTRApiClient | None = None
        self._refresh_lock  = asyncio.Lock()
        self._state_lock    = asyncio.Lock()
        # Set by Console 'stop' so close() skips its own duplicate broadcast.
        self._console_stop_sent: bool = False
        # Timestamp of the last time doodle embeds were pushed to Discord.
        # 0.0 = never, which triggers an immediate doodle refresh on first run.
        self._last_doodle_refresh: float = 0.0
        # Per-user cooldown for /pd-refresh: user_id → last-use timestamp.
        self._refresh_cooldowns: dict[int, float] = {}
        self._last_quarantine_scan: dict[str, float] = {}

    # ── STATE MANAGEMENT ──────────────────────────────────────────────────────

    def _load_state(self) -> dict[str, Any]:
        if not STATE_FILE.exists():
            return self._empty_state()
        try:
            raw = json.loads(STATE_FILE.read_text())
        except Exception as e:
            log.warning("Could not load state file: %s", e)
            return self._empty_state()
        if not isinstance(raw, dict) or not raw:
            return self._empty_state()
        version = raw.get("_version")
        if version == STATE_VERSION:
            raw.setdefault("guilds", {})
            raw.setdefault("allowlist", [])
            raw.setdefault("announcements", [])
            raw.setdefault("quarantined", {})
            return raw
        # v0 migration
        if all(isinstance(v, dict) and "channel_id" in v for v in raw.values()):
            if len(self.config.guild_allowlist) == 1:
                only = next(iter(self.config.guild_allowlist))
                log.info("Migrating v0 state to v%d under guild %s", STATE_VERSION, only)
                return {"_version": STATE_VERSION, "guilds": {str(only): raw}, "allowlist": [], "announcements": []}
            log.warning("v0 state found but cannot migrate (need exactly one guild). Starting fresh.")
            return self._empty_state()
        # v1 migration
        if all(isinstance(v, dict) and not k.startswith("_") for k, v in raw.items()):
            log.info("Migrating v1 state to v%d", STATE_VERSION)
            return {"_version": STATE_VERSION, "guilds": dict(raw), "allowlist": [], "announcements": []}
        log.warning("Unrecognised state.json shape; starting fresh.")
        return self._empty_state()

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {"_version": STATE_VERSION, "guilds": {}, "allowlist": [], "announcements": [], "quarantined": {}}

    async def _save_state(self) -> None:
        async with self._state_lock:
            try:
                STATE_FILE.write_text(json.dumps(self.state, indent=2))
            except Exception as e:
                log.warning("Could not save state file: %s", e)

    def _guilds_block(self) -> dict[str, dict[str, dict[str, Any]]]:
        return self.state.setdefault("guilds", {})

    def _guild_state(self, guild_id: int) -> dict[str, dict[str, Any]]:
        return self._guilds_block().setdefault(str(guild_id), {})

    def _state_message_ids(self, guild_id: int, key: str) -> list[int]:
        entry = self._guild_state(guild_id).get(key, {}) or {}
        ids = entry.get("message_ids")
        if isinstance(ids, list) and ids:
            return [int(i) for i in ids if isinstance(i, (int, str))]
        legacy = entry.get("message_id")
        if legacy:
            return [int(legacy)]
        return []

    def _set_state(self, guild_id: int, key: str, channel_id: int, message_ids: list[int]) -> None:
        self._guild_state(guild_id)[key] = {"channel_id": channel_id, "message_ids": message_ids}

    def _runtime_allowlist(self) -> set[int]:
        return {int(x) for x in self.state.get("allowlist", [])}

    def effective_allowlist(self) -> set[int]:
        return set(self.config.guild_allowlist) | self._runtime_allowlist()

    def is_guild_allowed(self, guild_id: int) -> bool:
        return guild_id in self.effective_allowlist()

    def _announcements(self) -> list[dict[str, Any]]:
        return self.state.setdefault("announcements", [])

    async def _record_announcement(self, guild_id: int, channel_id: int, message_id: int, expires_at: float) -> None:
        self._announcements().append({
            "guild_id": int(guild_id), "channel_id": int(channel_id),
            "message_id": int(message_id), "expires_at": float(expires_at),
        })
        await self._save_state()

    # ── LIFECYCLE ─────────────────────────────────────────────────────────────

    async def setup_hook(self) -> None:
        self._api = TTRApiClient(self.config.user_agent)
        await self._api.__aenter__()
        print("[API Client] Loaded successfully", flush=True)

        # Push an empty global command list to Discord, wiping any stale
        # global commands (ttr_refresh, pd_guild_add, etc.).
        self.tree.clear_commands(guild=None)
        await self.tree.sync()

        # Register the current commands in memory only.
        # They will be synced per-guild in on_ready / on_guild_join,
        # which prevents Discord from showing global + guild duplicates.
        self._register_commands()
        print("[Commands] Registered successfully", flush=True)

    async def close(self) -> None:
        """Broadcast maintenance notices then shut down cleanly."""
        log.info("Shutdown signal received -- sending maintenance notices...")
        if not self._console_stop_sent:
            try:
                await asyncio.wait_for(self._broadcast_maintenance(), timeout=15.0)
            except Exception as exc:
                log.warning("Maintenance broadcast failed: %s", exc)
        else:
            log.info("Console stop already sent maintenance notice -- skipping auto-broadcast.")
        if self._api is not None:
            await self._api.__aexit__(None, None, None)
        await super().close()

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info("Logged in as %s (id=%s)", self.user, self.user.id)
        log.info(
            "In %d guild(s); env-allowlist=%d; runtime-allowlist=%d; admins=%d",
            len(self.guilds), len(self.config.guild_allowlist),
            len(self._runtime_allowlist()), len(self.config.admin_ids),
        )
        log.info("Bot-admin IDs: %s", ", ".join(str(i) for i in sorted(self.config.admin_ids)))

        for guild in list(self.guilds):
            if not self.is_guild_allowed(guild.id):
                log.warning("Leaving non-allowlisted guild %s (id=%s)", guild.name, guild.id)
                await self._notify_and_leave(guild)

        live_ids = {str(g.id) for g in self.guilds}
        for gid in list(self._guilds_block().keys()):
            if gid not in live_ids:
                log.info("Pruning state for departed guild %s", gid)
                self._guilds_block().pop(gid, None)

        # Per-guild command sync: clears old names and registers new ones.
        for guild in list(self.guilds):
            if not self.is_guild_allowed(guild.id):
                continue
            await self._sync_commands_to_guild(guild)
            print(f"[{guild.name}] [{guild.id}] Joined Successfully", flush=True)

        await self._cleanup_maintenance_msgs()
        print("[Maintenance Cleanup] Loaded successfully", flush=True)
        await clear_maintenance_on_startup(self)
        asyncio.create_task(run_console(self), name="console-listener")
        print("[Console Listener] Loaded successfully", flush=True)
        await self._cleanup_announcements_on_startup()
        print("[Announcement Cleanup] Loaded successfully", flush=True)
        await self._refresh_suit_calculator_all_guilds()
        print("[Suit Calculator] Loaded successfully", flush=True)
        await self._save_state()

        _seeded_bans = 0
        if self.config.banned_user_ids:
            _existing_banned = self._load_banned()
            for _uid in self.config.banned_user_ids:
                if str(_uid) not in _existing_banned:
                    _existing_banned[str(_uid)] = {
                        "reason": "seeded from .env",
                        "banned_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                        "banned_by": "system",
                        "banned_by_id": 0,
                    }
                    _seeded_bans += 1
            if _seeded_bans:
                self._save_banned(_existing_banned)
        _seeded_quarantines = 0
        if self.config.quarantined_guild_ids:
            _q = self._quarantined_guilds()
            for _gid in self.config.quarantined_guild_ids:
                if str(_gid) not in _q:
                    _q[str(_gid)] = {
                        "triggered_by_user_id": 0,
                        "triggered_at": time.time(),
                        "manual": True,
                        "quarantine_msg_ids": {},
                    }
                    _seeded_quarantines += 1
        if _seeded_bans or _seeded_quarantines:
            log.info("Startup seed: %d ban(s), %d quarantine(s) from .env",
                     _seeded_bans, _seeded_quarantines)
            await self._save_state()

        if not self._refresh_loop.is_running():
            self._refresh_loop.change_interval(seconds=self.config.refresh_interval)
            self._refresh_loop.start()
        print("[Live Feed Loop] Loaded successfully", flush=True)
        if not self._sweep_loop.is_running():
            self._sweep_loop.start()
        print("[Sweep Loop] Loaded successfully", flush=True)

        if not self._quarantine_scan_loop.is_running():
            self._quarantine_scan_loop.start()
        print("[Quarantine Scan Loop] Loaded successfully", flush=True)
        asyncio.create_task(self._run_quarantine_scan(), name="startup-quarantine-scan")

        guild_count = len([g for g in self.guilds if self.is_guild_allowed(g.id)])
        print(f"Paws Pendragon TTR is online in {guild_count} server(s).", flush=True)

    async def on_guild_join(self, guild: discord.Guild) -> None:
        if not self.is_guild_allowed(guild.id):
            log.warning("Refusing to join non-allowlisted guild %s (id=%s)", guild.name, guild.id)
            await self._notify_and_leave(guild)
            return
        log.info("Joined allowlisted guild %s (id=%s)", guild.name, guild.id)
        await self._sync_commands_to_guild(guild)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        log.info("Removed from guild %s (id=%s)", guild.name, guild.id)
        self._guilds_block().pop(str(guild.id), None)
        await self._save_state()

    # ── GUILD ACCESS ──────────────────────────────────────────────────────────

    async def _sync_commands_to_guild(self, guild: discord.Guild) -> None:
        """Aggressively wipe all old per-guild commands then push the new set."""
        try:
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            log.info("Command sync OK for %s (id=%s)", guild.name, guild.id)
        except Exception:
            log.exception("Command sync failed for %s (id=%s)", guild.name, guild.id)

    async def _notify_and_leave(self, guild: discord.Guild) -> None:
        """DM the guild owner the closed-access message, then leave."""
        try:
            owner = guild.owner or await guild.fetch_member(guild.owner_id)
            if owner is not None:
                await owner.send(CLOSED_ACCESS_MSG)
        except Exception as e:
            log.debug("Could not DM owner of %s: %s", guild.name, e)
        try:
            await guild.leave()
        except Exception as e:
            log.warning("Failed to leave guild %s: %s", guild.id, e)

    # ── CHANNEL BOOTSTRAPPING ─────────────────────────────────────────────────

    async def _ensure_channels_for_guild(self, guild: discord.Guild) -> None:
        category = discord.utils.get(guild.categories, name=self.config.category_name)
        if category is None:
            log.info("Creating category %r in %s", self.config.category_name, guild.name)
            category = await guild.create_category(self.config.category_name)
        for key, channel_name in self.config.feeds().items():
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            if channel is None:
                log.info("Creating channel #%s in %s", channel_name, guild.name)
                channel = await guild.create_text_channel(
                    channel_name, category=category,
                    topic=f"Live TTR {key} feed -- auto-updated by bot.",
                )
            await self._ensure_messages(guild.id, key, channel, at_least=1)

        calc_name = self.config.channel_suit_calculator
        calc_ch   = discord.utils.get(guild.text_channels, name=calc_name)
        if calc_ch is None:
            log.info("Creating channel #%s in %s", calc_name, guild.name)
            calc_ch = await guild.create_text_channel(
                calc_name, category=category,
                topic="Cog suit disguise calculator — use /calculate here.",
            )
        await self._ensure_suit_calculator_pin(guild.id, calc_ch)
        await self._ensure_suit_threads(guild.id, calc_ch)
        await self._save_state()

    async def _send_placeholder(self, key: str, channel: discord.TextChannel) -> discord.Message:
        msg = await channel.send(embed=discord.Embed(
            title=f"Loading {key}...", description="Fetching the latest data from TTR.", color=0x9124F2,
        ))
        try:
            await msg.pin(reason="Live TTR feed pin")
        except (discord.Forbidden, discord.HTTPException) as e:
            log.debug("Could not pin in #%s: %s", channel.name, e)
        return msg

    async def _ensure_messages(
        self, guild_id: int, key: str, channel: discord.TextChannel, at_least: int,
    ) -> list[int]:
        ids = self._state_message_ids(guild_id, key)
        verified: list[int] = []
        for mid in ids:
            try:
                await channel.fetch_message(mid)
                verified.append(mid)
            except discord.NotFound:
                log.info("Stored message %s for %s/%s is gone.", mid, guild_id, key)
            except discord.Forbidden:
                log.warning("No permission to fetch message in #%s", channel.name)
                verified.append(mid)
            except discord.HTTPException as e:
                log.warning("Transient HTTP %s verifying message %s in #%s -- keeping ID.", e.status, mid, channel.name)
                verified.append(mid)
        while len(verified) < at_least:
            msg = await self._send_placeholder(key, channel)
            verified.append(msg.id)
        self._set_state(guild_id, key, channel.id, verified)
        return verified

    # ── SUIT CALCULATOR ───────────────────────────────────────────────────────

    async def _ensure_suit_calculator_pin(
        self, guild_id: int, channel: discord.TextChannel,
    ) -> None:
        """Post (or edit in place) the 4 static info embeds in #suit-calculator."""
        embeds     = build_suit_calculator_embeds()
        gs         = self._guild_state(guild_id)
        entry      = gs.get("suit_calculator", {})
        stored_ids: list[int] = []

        if isinstance(entry, dict):
            raw_ids = entry.get("message_ids", [])
            if isinstance(raw_ids, list):
                stored_ids = [int(i) for i in raw_ids if i]

        verified_ids: list[int] = []
        for i, embed in enumerate(embeds):
            mid = stored_ids[i] if i < len(stored_ids) else None
            if mid:
                try:
                    msg = await channel.fetch_message(mid)
                    await msg.edit(embed=embed)
                    verified_ids.append(msg.id)
                    log.info("[suit-calc] Edited embed %d/%d msg=%s guild=%s",
                             i+1, len(embeds), msg.id, guild_id)
                    continue
                except discord.NotFound:
                    log.info("[suit-calc] Embed %d gone for guild %s -- reposting.", i+1, guild_id)
                except discord.HTTPException as exc:
                    log.warning("[suit-calc] Could not edit embed %d: %s", i+1, exc)
            try:
                new_msg = await channel.send(embed=embed)
                if i == 0:
                    try:
                        await new_msg.pin(reason="Suit Calculator -- Paws Pendragon TTR")
                    except (discord.Forbidden, discord.HTTPException) as exc:
                        log.debug("[suit-calc] Could not pin: %s", exc)
                verified_ids.append(new_msg.id)
                log.info("[suit-calc] Posted embed %d/%d msg=%s guild=%s (#%s)",
                         i+1, len(embeds), new_msg.id, guild_id, channel.name)
            except Exception as exc:
                log.warning("[suit-calc] Failed to post embed %d in guild %s: %s",
                            i+1, guild_id, exc)

        if verified_ids:
            gs["suit_calculator"] = {"channel_id": channel.id, "message_ids": verified_ids}

    async def _ensure_suit_threads(
        self, guild_id: int, channel: discord.TextChannel,
    ) -> None:
        """Post or edit the 3 static embeds inside each of the 4 faction threads."""
        gs          = self._guild_state(guild_id)
        suit_threads: dict = gs.setdefault("suit_threads", {})

        for faction_key in _FACTION_ORDER:
            thread_name = _FACTION_THREAD_NAMES[faction_key]
            embeds      = build_faction_thread_embeds(faction_key)
            entry       = suit_threads.get(faction_key, {})
            thread_id   = int(entry.get("thread_id", 0)) if isinstance(entry, dict) else 0
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

            # Create thread if still missing
            if thread is None:
                try:
                    thread = await channel.create_thread(
                        name=thread_name,
                        auto_archive_duration=10080,
                        type=discord.ChannelType.public_thread,
                    )
                    log.info("[suit-threads] Created thread '%s' guild=%s", thread_name, guild_id)
                except discord.Forbidden:
                    log.warning("[suit-threads] No permission to create thread '%s' guild=%s",
                                thread_name, guild_id)
                    continue
                except discord.HTTPException as exc:
                    log.warning("[suit-threads] Failed to create thread '%s': %s", thread_name, exc)
                    continue

            # Unarchive if needed so we can post/edit
            if getattr(thread, "archived", False):
                try:
                    await thread.edit(archived=False)
                except (discord.Forbidden, discord.HTTPException):
                    pass

            # Post or edit the 3 embeds
            verified_ids: list[int] = []
            for i, embed in enumerate(embeds):
                mid = msg_ids[i] if i < len(msg_ids) else None
                if mid:
                    try:
                        msg = await thread.fetch_message(mid)
                        await msg.edit(embed=embed)
                        verified_ids.append(msg.id)
                        log.info("[suit-threads] Edited embed %d/3 in '%s' guild=%s",
                                 i + 1, thread_name, guild_id)
                        continue
                    except discord.NotFound:
                        pass
                    except discord.HTTPException as exc:
                        log.warning("[suit-threads] Could not edit embed %d in '%s': %s",
                                    i + 1, thread_name, exc)
                try:
                    new_msg = await thread.send(embed=embed)
                    verified_ids.append(new_msg.id)
                    log.info("[suit-threads] Posted embed %d/3 in '%s' guild=%s",
                             i + 1, thread_name, guild_id)
                except discord.Forbidden:
                    log.warning("[suit-threads] No send permission in thread '%s' guild=%s",
                                thread_name, guild_id)
                    break
                except discord.HTTPException as exc:
                    log.warning("[suit-threads] Failed to post embed %d in '%s': %s",
                                i + 1, thread_name, exc)

            # Lock thread so only the bot can post
            try:
                await thread.edit(locked=True, archived=False)
            except (discord.Forbidden, discord.HTTPException) as exc:
                log.debug("[suit-threads] Could not lock '%s': %s", thread_name, exc)

            suit_threads[faction_key] = {"thread_id": thread.id, "message_ids": verified_ids}

        gs["suit_threads"] = suit_threads

    async def _refresh_suit_calculator_all_guilds(self) -> None:
        """Refresh the suit-calculator embeds for every tracked guild."""
        calc_name = self.config.channel_suit_calculator
        updated   = 0
        for guild_id_str in list(self._guilds_block().keys()):
            try:
                guild_id = int(guild_id_str)
            except ValueError:
                continue
            if self.get_guild(guild_id) is None:
                continue
            gs         = self._guild_state(guild_id)
            entry      = gs.get("suit_calculator", {})
            channel_id = int(entry.get("channel_id", 0)) if isinstance(entry, dict) else 0
            channel    = self.get_channel(channel_id) if channel_id else None
            if not isinstance(channel, discord.TextChannel):
                guild   = self.get_guild(guild_id)
                channel = (
                    discord.utils.get(guild.text_channels, name=calc_name)
                    if guild else None
                )
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                await self._ensure_suit_calculator_pin(guild_id, channel)
                await self._ensure_suit_threads(guild_id, channel)
                updated += 1
            except Exception:
                log.exception("[suit-calc] Refresh failed for guild %s", guild_id)
        if updated:
            log.info("[suit-calc] Refreshed embeds for %d guild(s).", updated)
            await self._save_state()

    # ── FEED REFRESH ──────────────────────────────────────────────────────────

    _API_KEYS = ("invasions", "population", "fieldoffices", "doodles", "sillymeter")

    async def _fetch_all(self) -> dict[str, dict | None]:
        if self._api is None:
            return {k: None for k in self._API_KEYS}
        results = await asyncio.gather(
            *(self._api.fetch(k) for k in self._API_KEYS), return_exceptions=True,
        )
        return {
            k: (None if isinstance(r, BaseException) else r)
            for k, r in zip(self._API_KEYS, results)
        }

    async def _refresh_once(self, *, force_doodles: bool = False) -> None:
        """Refresh all live feed embeds across tracked guilds.

        Doodle embeds are throttled to once every 12 hours unless
        *force_doodles* is True (set by /pd-refresh).
        """
        if self._api is None:
            return
        async with self._refresh_lock:
            now             = time.time()
            refresh_doodles = force_doodles or (
                (now - self._last_doodle_refresh) >= DOODLE_REFRESH_INTERVAL
            )
            api_data         = await self._fetch_all()
            total_messages   = 0
            guilds_updated: set[int] = set()

            for guild_id_str in list(self._guilds_block().keys()):
                try:
                    guild_id = int(guild_id_str)
                except ValueError:
                    continue
                if not self.is_guild_allowed(guild_id) or self.get_guild(guild_id) is None:
                    continue
                if self._is_quarantined(guild_id):
                    continue
                for feed_key in self.config.feeds():
                    # Skip doodle embeds unless the 12-hour interval has elapsed
                    # (or this is a forced refresh from /pd-refresh).
                    if feed_key == "doodles" and not refresh_doodles:
                        continue
                    try:
                        updated = await self._update_feed(guild_id, feed_key, api_data)
                        if updated:
                            total_messages += updated
                            guilds_updated.add(guild_id)
                    except Exception:
                        log.exception("Failed updating %s/%s", guild_id, feed_key)

            if refresh_doodles:
                self._last_doodle_refresh = now
                log.info("Doodle embeds refreshed (next automatic refresh in 12 hours).")

            if total_messages:
                log.info(
                    "Embed refresh: %d message(s) updated across %d server(s)",
                    total_messages, len(guilds_updated),
                )
            else:
                log.info("Embed refresh: no tracked servers to update.")
            await self._save_state()

    async def _update_feed(self, guild_id: int, feed_key: str, api_data: dict[str, dict | None]) -> int:
        """Update a single feed for a guild. Returns the number of messages edited/sent."""
        entry = self._guild_state(guild_id).get(feed_key)
        if not entry:
            return 0
        channel = self.get_channel(int(entry["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return 0
        formatter = FORMATTERS.get(feed_key)
        if formatter is None:
            return 0
        embeds = formatter(api_data)
        if not isinstance(embeds, list):
            embeds = [embeds]
        if not embeds:
            return 0

        ids      = await self._ensure_messages(guild_id, feed_key, channel, at_least=len(embeds))
        kept_ids: list[int] = []
        edited   = 0

        for mid, embed in zip(ids, embeds):
            try:
                await (await channel.fetch_message(mid)).edit(embed=embed)
                kept_ids.append(mid)
                edited += 1
            except discord.NotFound:
                new_msg = await channel.send(embed=embed)
                try:
                    await new_msg.pin(reason="Live TTR feed pin")
                except (discord.Forbidden, discord.HTTPException):
                    pass
                kept_ids.append(new_msg.id)
                edited += 1
            except discord.HTTPException as e:
                log.warning("Transient HTTP %s editing message %s (%s/%s) -- will retry.", e.status, mid, guild_id, feed_key)
                kept_ids.append(mid)
            await asyncio.sleep(3.0)

        for mid in ids[len(embeds):]:
            try:
                await (await channel.fetch_message(mid)).edit(
                    embed=discord.Embed(description="*(no data for this tier right now)*", color=0x9124F2)
                )
                kept_ids.append(mid)
                edited += 1
            except discord.NotFound:
                pass
            except discord.HTTPException as e:
                log.warning("Transient HTTP %s on stale-slot message %s -- keeping ID.", e.status, mid)
                kept_ids.append(mid)
            await asyncio.sleep(3.0)

        self._set_state(guild_id, feed_key, channel.id, kept_ids)
        return edited

    @tasks.loop(seconds=60)
    async def _refresh_loop(self) -> None:
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
    async def _before_loop(self) -> None:
        await self.wait_until_ready()

    # ── STALE MESSAGE SWEEP ───────────────────────────────────────────────────

    def _channel_keep_ids(self, guild_id: int, channel_id: int) -> set[int]:
        """Return the set of message IDs the bot should NOT delete in *channel_id*."""
        keep: set[int] = set()
        for entry in self._guild_state(guild_id).values():
            if not isinstance(entry, dict):
                continue
            if int(entry.get("channel_id", 0)) != channel_id:
                continue
            for mid in entry.get("message_ids", []) or []:
                try:
                    keep.add(int(mid))
                except (TypeError, ValueError):
                    pass
        for record in self._announcements():
            if int(record.get("channel_id", 0)) == channel_id:
                try:
                    keep.add(int(record.get("message_id", 0)))
                except (TypeError, ValueError):
                    pass
        q_record = self._get_quarantine(guild_id)
        if q_record:
            for mid in q_record.get("quarantine_msg_ids", {}).values():
                try:
                    keep.add(int(mid))
                except (TypeError, ValueError):
                    pass
        return keep

    async def _sweep_channel_stale(
        self, channel: discord.TextChannel, *, keep_ids: set[int], history_limit: int = 200,
    ) -> int:
        if self.user is None:
            return 0
        bot_id  = self.user.id
        deleted = 0
        try:
            async for msg in channel.history(limit=history_limit):
                if msg.author.id != bot_id or msg.id in keep_ids:
                    continue
                try:
                    await msg.delete()
                    deleted += 1
                except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                    pass
        except discord.Forbidden:
            log.debug("No Read Message History in #%s; skipping sweep", channel.name)
        return deleted

    async def _sweep_guild_stale(self, guild_id: int) -> int:
        total = 0
        seen: set[int] = set()
        for entry in self._guild_state(guild_id).values():
            channel_id = int(entry.get("channel_id", 0))
            if channel_id in seen or channel_id == 0:
                continue
            seen.add(channel_id)
            channel = self.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue
            total += await self._sweep_channel_stale(channel, keep_ids=self._channel_keep_ids(guild_id, channel_id))
        return total

    async def _sweep_expired_announcements(self) -> None:
        now     = time.time()
        expired = [r for r in list(self._announcements()) if float(r.get("expires_at", 0)) <= now]
        for record in expired:
            await self._delete_announcement_record(record)
        if expired:
            await self._save_state()

    @tasks.loop(minutes=15)
    async def _sweep_loop(self) -> None:
        """Sweep stale bot messages from all tracked channels every 15 minutes."""
        for guild_id_str in list(self._guilds_block().keys()):
            try:
                guild_id = int(guild_id_str)
            except ValueError:
                continue
            if not self.is_guild_allowed(guild_id) or self.get_guild(guild_id) is None:
                continue
            try:
                swept = await self._sweep_guild_stale(guild_id)
                if swept:
                    log.info("Periodic sweep: removed %d stale message(s) in guild %s", swept, guild_id)
            except Exception:
                log.exception("Periodic sweep failed for guild %s", guild_id)

    @_sweep_loop.before_loop
    async def _before_sweep_loop(self) -> None:
        await self.wait_until_ready()

    # ── ANNOUNCEMENTS ─────────────────────────────────────────────────────────

    async def _broadcast_announcement(self, text: str) -> tuple[int, int, int]:
        embed = discord.Embed(title=ANNOUNCEMENT_TITLE, description=text, color=0x9124F2)
        embed.set_footer(text=f"This message will auto-delete in {ANNOUNCEMENT_TTL_SECONDS // 60} minutes.")
        expires_at     = time.time() + ANNOUNCEMENT_TTL_SECONDS
        sent = failed  = 0
        guilds_touched: set[int] = set()

        for guild_id_str, gs in list(self._guilds_block().items()):
            try:
                guild_id = int(guild_id_str)
            except ValueError:
                continue
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
                    log.warning("Broadcast failed for %s/#%s: %s", guild_id, channel.name, e)
                    failed += 1

        return sent, failed, len(guilds_touched)

    async def _delete_announcement_record(self, record: dict[str, Any]) -> None:
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
            r for r in self._announcements() if int(r.get("message_id", -1)) != message_id
        ]

    async def _cleanup_announcements_on_startup(self) -> None:
        cleared = 0
        failed  = 0

        stale_records = list(self._announcements())
        if stale_records:
            log.info("Startup cleanup: found %d tracked announcement(s) to clear.", len(stale_records))
        for record in stale_records:
            try:
                await self._delete_announcement_record(record)
                cleared += 1
            except Exception:
                failed += 1

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
                    if msg.author.id != (self.user.id if self.user else 0):
                        continue
                    if msg.embeds and ANNOUNCEMENT_TITLE in (msg.embeds[0].title or ""):
                        try:
                            await msg.delete()
                            log.info("Startup cleanup: deleted orphan announcement %s in guild %s", msg.id, guild_id)
                            cleared += 1
                        except (discord.Forbidden, discord.NotFound) as e:
                            log.warning("Startup cleanup: could not delete orphan %s: %s", msg.id, e)
                            failed += 1
            except Exception:
                log.exception("Startup cleanup: orphan scan failed in %s/#%s", guild_id, getattr(channel, "name", "?"))

        if cleared == 0 and failed == 0:
            log.info("Startup cleanup: no stale messages found -- channels are clean.")
        elif failed == 0:
            log.info("Startup cleanup: cleared %d stale message(s) successfully.", cleared)
        else:
            log.warning(
                "Startup cleanup: cleared %d message(s), but %d could not be deleted (check permissions).",
                cleared, failed,
            )

    # ── MAINTENANCE ───────────────────────────────────────────────────────────

    async def _broadcast_maintenance(self) -> None:
        """Send a maintenance embed to every tracked guild info channel."""
        embed = discord.Embed(
            title=":wrench: Temporary Maintenance",
            description=(
                "The bot is going down for temporary maintenance. "
                "Please check [toonhq.org](https://toonhq.org) in the "
                "meantime for your toony needs!"
            ),
            color=0x9124F2,
            timestamp=datetime.now(timezone.utc),
        )
        maintenance_ids: dict[str, int] = {}
        for guild_id_str, gs in list(self._guilds_block().items()):
            info_entry = gs.get("information")
            if not info_entry:
                continue
            channel = self.get_channel(int(info_entry["channel_id"]))
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                msg = await channel.send(embed=embed)
                maintenance_ids[guild_id_str] = msg.id
                log.info("Sent maintenance notice to guild %s", guild_id_str)
            except Exception as exc:
                log.warning("Could not send maintenance notice to %s: %s", guild_id_str, exc)
        if maintenance_ids:
            self.state["maintenance_msgs"] = maintenance_ids
            await self._save_state()

    async def _cleanup_maintenance_msgs(self) -> None:
        """Delete maintenance messages left from the previous shutdown."""
        maintenance_ids: dict[str, int] = self.state.pop("maintenance_msgs", {})
        if not maintenance_ids:
            return
        cleaned = 0
        for guild_id_str, msg_id in maintenance_ids.items():
            gs         = self._guilds_block().get(guild_id_str, {})
            info_entry = gs.get("information")
            if not info_entry:
                continue
            channel = self.get_channel(int(info_entry["channel_id"]))
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.delete()
                cleaned += 1
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                pass
        await self._save_state()
        if cleaned:
            log.info("Startup cleanup: removed %d maintenance notice(s).", cleaned)

    async def _check_panel_announce(self) -> None:
        """Broadcast panel_announce.txt contents if the file exists, then delete it."""
        if not ANNOUNCE_FILE.exists():
            return
        try:
            text = ANNOUNCE_FILE.read_text(encoding="utf-8").strip()
            ANNOUNCE_FILE.unlink()
        except Exception as e:
            log.warning("Could not read/delete panel_announce.txt: %s", e)
            return
        if not text:
            return
        log.info("Panel announcement detected -- broadcasting: %s", text[:80])
        sent, failed, guilds = await self._broadcast_announcement(text)
        log.info("Panel announcement: %d msg(s) across %d guild(s), %d failed.", sent, guilds, failed)

    # ── USER SYSTEM ───────────────────────────────────────────────────────────

    def _load_welcomed(self) -> set[int]:
        """Return set of user IDs that have already received the welcome DM."""
        try:
            if WELCOMED_FILE.exists():
                return set(json.loads(WELCOMED_FILE.read_text()))
        except Exception:
            pass
        return set()

    def _save_welcomed(self, welcomed: set[int]) -> None:
        try:
            WELCOMED_FILE.write_text(json.dumps(sorted(welcomed)))
        except Exception as exc:
            log.warning("Could not save welcomed_users.json: %s", exc)

    async def _maybe_welcome(self, user: discord.abc.User) -> None:
        """Send a one-time welcome DM the first time a user uses the bot."""
        welcomed = self._load_welcomed()
        if user.id in welcomed:
            return
        msg = (
            "**Thanks for installing Paws Pendragon TTR!** :duck:\n\n"
            ":warning: *This bot is currently in Early Access -- features are still "
            "being added and things may change.*\n\n"
            "**Available Commands:**\n"
            "`/ttrinfo` -- Get the current Toontown district populations, cog invasions, "
            "field offices, and Silly Meter status sent directly to your DMs.\n\n"
            "`/doodleinfo` -- Get the full Toontown doodle list with trait ratings and a "
            "buying guide sent directly to your DMs."
        )
        try:
            await user.send(msg)
            welcomed.add(user.id)
            self._save_welcomed(welcomed)
            log.info("Sent welcome DM to user %s (id=%s)", user, user.id)
        except discord.Forbidden:
            pass  # DMs closed, skip silently

    def _load_banned(self) -> dict[str, dict]:
        """Return banlist as {str(user_id): {reason, banned_at, banned_by, banned_by_id}}."""
        try:
            if BANNED_FILE.exists():
                return json.loads(BANNED_FILE.read_text())
        except Exception:
            pass
        return {}

    def _save_banned(self, banned: dict[str, dict]) -> None:
        try:
            BANNED_FILE.write_text(json.dumps(banned, indent=2))
        except Exception as exc:
            log.warning("Could not save banned_users.json: %s", exc)

    def _is_banned(self, user_id: int) -> dict | None:
        """Return the ban record if the user is banned, else None."""
        return self._load_banned().get(str(user_id))

    async def _reject_if_blocked(self, interaction: discord.Interaction) -> bool:
        """Return True and send an ephemeral reply if the user is banned. Also handles dm_count throttling."""
        record = self._is_banned(interaction.user.id)
        if record is None:
            return False

        dm_count = record.get("dm_count", 0)
        user_id = interaction.user.id

        if dm_count >= 25:
            msg = "You have been banned from using Paws Pendragon."
            try:
                await interaction.response.send_message(msg, ephemeral=True)
            except discord.InteractionResponded:
                await interaction.followup.send(msg, ephemeral=True)
            log.info("Blocked banned user %s (id=%s) [dm_count=%d cap]", interaction.user, user_id, dm_count)
            return True

        ephemeral_msg = "Pendragon is unavailable, please check your DMs for more info."
        try:
            await interaction.response.send_message(ephemeral_msg, ephemeral=True)
        except discord.InteractionResponded:
            await interaction.followup.send(ephemeral_msg, ephemeral=True)

        dm_embeds = [
            discord.Embed(description=(
                "Unfortunately you have been recognized for your abuse of Pendragon's "
                "commands in a nature that makes the usage for others less reliable."
            ), color=0xFF4444),
            discord.Embed(description=(
                "In the event that you try to use the Discord-App version, or any "
                "server's Guild version your inputs will be rejected."
            ), color=0xFF4444),
            discord.Embed(description=(
                "Servers that you have management access to will also lose the ability "
                "to use Pendragon to safeguard other toons."
            ), color=0xFF4444),
            discord.Embed(description=(
                "Appeal services are unavailable at this time, if you were on this list "
                "you were added for a reason."
            ), color=0xFF4444),
        ]
        try:
            for embed in dm_embeds:
                await interaction.user.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

        banned = self._load_banned()
        if str(user_id) in banned:
            banned[str(user_id)]["dm_count"] = dm_count + 1
            self._save_banned(banned)

        log.info("Blocked banned user %s (id=%s) from %s [dm_count now %d]",
                 interaction.user, user_id,
                 interaction.command and interaction.command.name,
                 dm_count + 1)
        return True

    def _sync_env(self) -> None:
        if not _ENV_PATH:
            return
        banned = self._load_banned()
        quarantined = self._quarantined_guilds()
        set_key(_ENV_PATH, "BANNED_USER_IDS", ",".join(sorted(banned.keys())))
        set_key(_ENV_PATH, "QUARANTINED_GUILD_IDS", ",".join(sorted(quarantined.keys())))

    async def _ban_user(self, user_id: int, reason: str, banned_by: str, banned_by_id: int) -> None:
        banned = self._load_banned()
        banned[str(user_id)] = {
            "reason": reason,
            "banned_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "banned_by": banned_by,
            "banned_by_id": banned_by_id,
            "dm_count": 0,
        }
        self._save_banned(banned)
        self._sync_env()
        asyncio.create_task(self._scan_new_ban(user_id))

    def _unban_user(self, user_id: int) -> bool:
        banned = self._load_banned()
        if str(user_id) not in banned:
            return False
        del banned[str(user_id)]
        self._save_banned(banned)
        self._sync_env()
        return True

    def _quarantined_guilds(self) -> dict[str, dict]:
        return self.state.setdefault("quarantined", {})

    def _is_quarantined(self, guild_id: int) -> bool:
        return str(guild_id) in self._quarantined_guilds()

    def _get_quarantine(self, guild_id: int) -> dict | None:
        return self._quarantined_guilds().get(str(guild_id))

    async def _check_guild_for_banned_users(self, guild_id: int):
        guild = self.get_guild(guild_id)
        if guild is None:
            return None
        banned = self._load_banned()
        for uid_str in banned:
            try:
                uid = int(uid_str)
            except ValueError:
                continue
            if uid == guild.owner_id:
                return (uid, discord.Permissions.all())
            try:
                member = await guild.fetch_member(uid)
            except discord.NotFound:
                continue
            except discord.HTTPException:
                continue
            perms = member.guild_permissions
            if any([perms.administrator, perms.manage_channels,
                    perms.manage_messages, perms.manage_threads]):
                return (uid, perms)
        return None

    async def _quarantine_guild(self, guild_id: int, triggered_by_user_id: int, manual: bool = False) -> None:
        gs = self._guild_state(guild_id)
        quarantine_msg_ids: dict[str, int] = {}
        embed = discord.Embed(
            title="⚠️ Server Quarantine Active",
            description=(
                "This server is currently outside the realm of Pendragon's reach, "
                "your server administrator needs to fix something before I can "
                "continue guarding this server."
            ),
            color=0xFF4444,
        )
        for feed_key in ("information", "doodles", "suit_calculator"):
            entry = gs.get(feed_key)
            if not entry:
                continue
            channel = self.get_channel(int(entry.get("channel_id", 0)))
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                msg = await channel.send(embed=embed)
                quarantine_msg_ids[feed_key] = msg.id
            except Exception as exc:
                log.warning("[quarantine] Failed to post quarantine embed in guild %s %s: %s",
                            guild_id, feed_key, exc)
        guild_obj = self.get_guild(guild_id)
        guild_name = guild_obj.name if guild_obj else str(guild_id)
        now = time.time()
        self._quarantined_guilds()[str(guild_id)] = {
            "triggered_by_user_id": triggered_by_user_id,
            "triggered_at": now,
            "manual": manual,
            "quarantine_msg_ids": quarantine_msg_ids,
            "owner_last_dm_at": now,
            "owner_dm_count": 1,
        }
        await self._save_state()
        self._sync_env()
        if guild_obj and guild_obj.owner_id:
            try:
                owner = await self.fetch_user(guild_obj.owner_id)
                bot_id = self.user.id if self.user else ""
                owner_embed1 = discord.Embed(description=(
                    f"Hello, I'm **Paws Pendragon** (`{bot_id}`).\n\n"
                    f"Your server **{guild_name}** has been placed under quarantine. "
                    f"A banned user (Discord ID: `{triggered_by_user_id}`) was detected "
                    "holding elevated permissions in your server."
                ), color=0xFF4444)
                owner_embed2 = discord.Embed(description=(
                    "To restore bot services, please remove the following permissions from "
                    f"user `{triggered_by_user_id}` (or remove them from your server entirely):\n\n"
                    "> `Manage Messages`  `Manage Threads`  `Manage Channels`"
                ), color=0xFF4444)
                owner_embed3 = discord.Embed(description=(
                    "Paws Pendragon scans your server periodically for permission changes. "
                    "Once the issue is resolved, bot operations will resume automatically.\n\n"
                    "You will receive reminder messages if the issue persists. "
                    "If unresolved after 7 days, Pendragon will leave your server."
                ), color=0xFF4444)
                await owner.send(embed=owner_embed1)
                await owner.send(embed=owner_embed2)
                await owner.send(embed=owner_embed3)
            except Exception:
                pass
        admin_embed = discord.Embed(
            title="⚠️ Guild Quarantined",
            description=(
                f"**Server:** {guild_name} (`{guild_id}`)\n"
                f"**Triggered by user ID:** `{triggered_by_user_id}`\n"
                f"**Manual:** {manual}"
            ),
            color=0xFF4444,
        )
        for admin_id in self.config.admin_ids:
            try:
                user = await self.fetch_user(admin_id)
                await user.send(embed=admin_embed)
            except Exception:
                pass
        log.info("[quarantine] Guild %s (%s) quarantined (triggered_by=%s, manual=%s)",
                 guild_id, guild_name, triggered_by_user_id, manual)

    async def _lift_quarantine(self, guild_id: int) -> None:
        record = self._get_quarantine(guild_id)
        if record is None:
            return
        quarantine_msg_ids: dict[str, int] = record.get("quarantine_msg_ids", {})
        gs = self._guild_state(guild_id)
        for feed_key, msg_id in quarantine_msg_ids.items():
            entry = gs.get(feed_key)
            if not entry:
                continue
            channel = self.get_channel(int(entry.get("channel_id", 0)))
            if not isinstance(channel, discord.TextChannel):
                continue
            try:
                msg = await channel.fetch_message(msg_id)
                await msg.delete()
            except (discord.NotFound, discord.HTTPException):
                pass
        guild_obj = self.get_guild(guild_id)
        guild_name = guild_obj.name if guild_obj else str(guild_id)
        del self._quarantined_guilds()[str(guild_id)]
        await self._save_state()
        self._sync_env()
        admin_embed = discord.Embed(
            title="✅ Guild Quarantine Lifted",
            description=f"**Server:** {guild_name} (`{guild_id}`)",
            color=0x57F287,
        )
        for admin_id in self.config.admin_ids:
            try:
                user = await self.fetch_user(admin_id)
                await user.send(embed=admin_embed)
            except Exception:
                pass
        log.info("[quarantine] Quarantine lifted for guild %s (%s)", guild_id, guild_name)
        asyncio.create_task(self._refresh_once())

    async def _run_quarantine_scan(self, target_guild_id: int | None = None) -> dict:
        now = time.time()
        newly_quarantined = 0
        newly_lifted = 0
        scanned = 0
        guild_ids = (
            [target_guild_id] if target_guild_id is not None
            else [int(gid) for gid in self._guilds_block().keys() if gid.isdigit()]
        )
        for guild_id in guild_ids:
            is_q = self._is_quarantined(guild_id)
            last = self._last_quarantine_scan.get(str(guild_id), 0.0)
            if not is_q and (now - last) < 6 * 3600:
                continue
            scanned += 1
            result = await self._check_guild_for_banned_users(guild_id)
            if result is not None and not is_q:
                uid, _ = result
                await self._quarantine_guild(guild_id, uid)
                newly_quarantined += 1
            elif result is None and is_q:
                await self._lift_quarantine(guild_id)
                newly_lifted += 1
            if result is None:
                self._last_quarantine_scan[str(guild_id)] = now

            # Escalation checks for guilds that remain quarantined
            if self._is_quarantined(guild_id):
                q = self._get_quarantine(guild_id)
                triggered_at = q.get("triggered_at", now)
                owner_dm_count = q.get("owner_dm_count", 1)
                days_elapsed = (now - triggered_at) / 86400

                if days_elapsed >= 7:
                    guild_obj = self.get_guild(guild_id)
                    guild_name = guild_obj.name if guild_obj else str(guild_id)
                    log.warning("[quarantine] Day 7 limit reached for guild %s (%s) — leaving", guild_id, guild_name)
                    try:
                        if guild_obj:
                            await guild_obj.leave()
                    except Exception:
                        pass
                    del self._quarantined_guilds()[str(guild_id)]
                    await self._save_state()
                    self._sync_env()
                    continue

                needed_count = 1
                if days_elapsed >= 3:
                    needed_count = 2
                if days_elapsed >= 6:
                    needed_count = 3

                if owner_dm_count < needed_count:
                    guild_obj = self.get_guild(guild_id)
                    guild_name = guild_obj.name if guild_obj else str(guild_id)
                    triggered_by = q.get("triggered_by_user_id", "unknown")
                    day_label = 3 if needed_count == 2 else 6
                    try:
                        if guild_obj and guild_obj.owner_id:
                            owner = await self.fetch_user(guild_obj.owner_id)
                            reminder_embed = discord.Embed(
                                title="⚠️ Quarantine Reminder",
                                description=(
                                    f"**{guild_name}** has been quarantined for {day_label} day(s).\n\n"
                                    f"User `{triggered_by}` still holds elevated permissions. "
                                    f"Please remove `Manage Messages`, `Manage Threads`, or `Manage Channels` "
                                    f"from this user, or remove them from the server.\n\n"
                                    f"Pendragon will leave your server in {7 - day_label} day(s) if unresolved."
                                ),
                                color=0xFF8800,
                            )
                            await owner.send(embed=reminder_embed)
                    except Exception:
                        pass
                    q["owner_dm_count"] = needed_count
                    q["owner_last_dm_at"] = now
                    await self._save_state()

        return {"scanned": scanned, "quarantined": newly_quarantined, "lifted": newly_lifted}

    async def _scan_new_ban(self, user_id: int) -> None:
        guild_ids = [int(gid) for gid in self._guilds_block().keys() if gid.isdigit()]
        for guild_id in guild_ids:
            if self._is_quarantined(guild_id):
                continue
            guild = self.get_guild(guild_id)
            if guild is None:
                continue
            try:
                if user_id == guild.owner_id:
                    await self._quarantine_guild(guild_id, user_id)
                    continue
                member = await guild.fetch_member(user_id)
                perms = member.guild_permissions
                if any([perms.administrator, perms.manage_channels,
                        perms.manage_messages, perms.manage_threads]):
                    await self._quarantine_guild(guild_id, user_id)
            except (discord.NotFound, discord.HTTPException):
                pass

    @tasks.loop(minutes=30)
    async def _quarantine_scan_loop(self) -> None:
        try:
            await self._run_quarantine_scan()
        except Exception:
            log.exception("[quarantine] Scan loop error")

    @_quarantine_scan_loop.before_loop
    async def _before_quarantine_scan_loop(self) -> None:
        await self.wait_until_ready()

    # ── SLASH COMMANDS ────────────────────────────────────────────────────────

    def _register_commands(self) -> None:

        # ── /ttrinfo  (all users, guild + user install) ────────────────────
        @self.tree.command(
            name="ttrinfo",
            description="[User Command] See current Toontown district, invasion, field office, and Silly Meter info.",
        )
        @app_commands.allowed_installs(guilds=True, users=True)
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        async def ttrinfo(interaction: discord.Interaction) -> None:
            if await self._reject_if_blocked(interaction):
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self._maybe_welcome(interaction.user)
            if self._api is None:
                await interaction.followup.send("API client not ready yet -- try again in a moment.", ephemeral=True)
                return
            results = await asyncio.gather(
                self._api.fetch("invasions"),
                self._api.fetch("population"),
                self._api.fetch("fieldoffices"),
                self._api.fetch("sillymeter"),
                return_exceptions=True,
            )
            invasions    = None if isinstance(results[0], BaseException) else results[0]
            population   = None if isinstance(results[1], BaseException) else results[1]
            fieldoffices = None if isinstance(results[2], BaseException) else results[2]
            sillymeter   = None if isinstance(results[3], BaseException) else results[3]

            info_embeds = format_information(invasions=invasions, population=population, fieldoffices=fieldoffices)
            silly_embed = format_sillymeter(sillymeter)
            try:
                for embed in info_embeds:
                    await interaction.user.send(embed=embed)
                await interaction.user.send(embed=silly_embed)
                await interaction.followup.send("Check your DMs! 📬", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send(
                    "I couldn't DM you -- please enable DMs from server members and try again.",
                    ephemeral=True,
                )

        # ── /doodleinfo  (all users, guild + user install) ─────────────────
        @self.tree.command(
            name="doodleinfo",
            description="[User Command] See the current Toontown doodle list with trait ratings.",
        )
        @app_commands.allowed_installs(guilds=True, users=True)
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        async def doodleinfo(interaction: discord.Interaction) -> None:
            if await self._reject_if_blocked(interaction):
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self._maybe_welcome(interaction.user)
            if self._api is None:
                await interaction.followup.send("API client not ready yet -- try again in a moment.", ephemeral=True)
                return
            doodle_data = await self._api.fetch("doodles")
            embeds = format_doodles(doodle_data)
            try:
                await interaction.user.send(embeds=embeds)
                await interaction.followup.send("Check your DMs! 📬", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send(
                    "I couldn't DM you -- please enable DMs from server members and try again.",
                    ephemeral=True,
                )

        # ── /helpme  (all users, guild + user install) ────────────────────
        @self.tree.command(
            name="helpme",
            description="[User Command] Show available commands for the Paws Pendragon app.",
        )
        @app_commands.allowed_installs(guilds=True, users=True)
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        async def help_me(interaction: discord.Interaction) -> None:
            if await self._reject_if_blocked(interaction):
                return
            embed = discord.Embed(
                title="Paws Pendragon TTR — Commands",
                description=(
                    ":warning: *This bot is currently in Early Access — features are still "
                    "being added and things may change.*"
                ),
                color=0x9124F2,
            )
            embed.add_field(
                name="/ttrinfo",
                value="Current district populations, cog invasions, field offices, and Silly Meter status — sent to your DMs.",
                inline=False,
            )
            embed.add_field(
                name="/doodleinfo",
                value="Current doodle list with trait ratings and a buying guide — sent to your DMs.",
                inline=False,
            )
            embed.add_field(
                name="/calculate",
                value="Cog suit merit/stock options/jury notices calculator — interactive dropdown flow.",
                inline=False,
            )
            embed.add_field(
                name="/beanfest",
                value="Weekly Beanfest event schedule — sent to your DMs.",
                inline=False,
            )
            embed.add_field(
                name="/invite-app",
                value="Add Paws Pendragon TTR to your personal Discord account.",
                inline=False,
            )
            embed.add_field(
                name="/invite-server",
                value="Add Paws Pendragon TTR to a Discord server.",
                inline=False,
            )
            embed.add_field(
                name="/helpme",
                value="Show this message.",
                inline=False,
            )
            try:
                await interaction.user.send(embed=embed)
                await interaction.response.send_message("Check your DMs! 📬", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message(embed=embed, ephemeral=True)

        # ── /invite-app  (all users, guild + user install) ─────────────────
        @self.tree.command(
            name="invite-app",
            description="[User Command] Add Paws Pendragon TTR to your personal Discord account.",
        )
        @app_commands.allowed_installs(guilds=True, users=True)
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        async def invite_app(interaction: discord.Interaction) -> None:
            if await self._reject_if_blocked(interaction):
                return
            link = (
                "https://discord.com/oauth2/authorize"
                "?client_id=1496971496709689654"
                "&integration_type=1"
                "&scope=applications.commands"
            )
            msg = (
                f":link: **Add Paws Pendragon TTR to your Discord account**\n"
                f"{link}\n"
                f"​\n"
                f"**About the bot**\n"
                f"Paws Pendragon TTR is a Toontown Rewritten companion bot. "
                f"It delivers live game data -- district populations, cog invasions, "
                f"active field offices, Silly Meter status, and the full doodle guide -- "
                f"directly to your DMs from anywhere in Discord.\n"
                f"​\n"
                f"**Permissions requested**\n"
                f"This is a **User App install** -- it does **not** join your server and "
                f"requires **no server permissions**. "
                f"It adds the slash commands `/ttrinfo`, `/doodleinfo`, `/calculate`, "
                f"`/beanfest`, `/helpme`, `/invite-app`, and `/invite-server` to your "
                f"personal Discord account, usable in any server, DM, or group chat."
            )
            try:
                await interaction.user.send(msg)
                await interaction.response.send_message("Check your DMs! :mailbox_with_mail:", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message(msg, ephemeral=True)

        # ── /invite-server  (all users, guild + user install) ──────────────
        @self.tree.command(
            name="invite-server",
            description="[User Command] Add Paws Pendragon TTR to a Discord server.",
        )
        @app_commands.allowed_installs(guilds=True, users=True)
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        async def invite_server(interaction: discord.Interaction) -> None:
            if await self._reject_if_blocked(interaction):
                return
            link = (
                "https://discord.com/oauth2/authorize"
                "?client_id=1496971496709689654"
                "&permissions=7318489585232976"
                "&scope=bot+applications.commands"
            )
            msg = (
                f":link: **Add Paws Pendragon TTR to a server**\n"
                f"{link}\n"
                f"​\n"
                f"**About the bot**\n"
                f"Paws Pendragon TTR is a Toontown Rewritten companion bot. "
                f"When added to a server it automatically creates a **#tt-information** "
                f"channel and a **#tt-doodles** channel. These are kept up to date "
                f"with live TTR data: district populations, cog invasions, field offices, "
                f"the Silly Meter, and the full doodle buying guide.\n"
                f"​\n"
                f"**Permissions requested**\n"
                f"• **Manage Channels** -- create the `#tt-information` and `#tt-doodles` channels on setup.\n"
                f"• **Send Messages** -- post live game data into those channels.\n"
                f"• **Manage Messages** -- edit and clean up its own posts as data updates.\n"
                f"• **Embed Links** -- display rich embeds with formatted game information.\n"
                f"• **Read Message History** -- locate and update previously posted embeds.\n"
                f"• **View Channels** -- see the channels it manages.\n"
                f"\nThe bot does **not** read general chat messages and only operates in the channels it creates."
            )
            try:
                await interaction.user.send(msg)
                await interaction.response.send_message("Check your DMs! :mailbox_with_mail:", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message(msg, ephemeral=True)

        # ── /beanfest  (all users, guild + user install) ─────────────────
        @self.tree.command(
            name="beanfest",
            description="[User Command] View the weekly Beanfest schedule. Events are community-run and subject to change.",
        )
        @app_commands.allowed_installs(guilds=True, users=True)
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        async def beanfest(interaction: discord.Interaction) -> None:
            if await self._reject_if_blocked(interaction):
                return
            embed = discord.Embed(
                title="Beanfest Schedule",
                description=(
                    "These are **community-run** events and schedules are subject to change. "
                    "Always check with the hosting guild for the latest info."
                ),
                color=0x9124F2,
            )
            embed.add_field(
                name="Wednesday",
                value="Adult ToonTown Addicts\nKaboom Cliffs · 8pm TTT / 11pm ET",
                inline=False,
            )
            embed.add_field(
                name="Friday",
                value="Adult ToonTown Addicts\nKaboom Cliffs · 4pm TTT / 7pm ET",
                inline=False,
            )
            embed.add_field(
                name="Saturday",
                value="Cold Callers Guild\nHiccup Hills · 12pm TTT / 3pm ET",
                inline=False,
            )
            embed.add_field(
                name="Sunday",
                value="Adult ToonTown Addicts\nKaboom Cliffs · 10am TTT / 1pm ET",
                inline=False,
            )
            embed.set_footer(text="Location: Goofy's Speedway")
            try:
                await interaction.user.send(embed=embed)
                await interaction.response.send_message("Check your DMs! 📬", ephemeral=True)
            except discord.Forbidden:
                await interaction.response.send_message(embed=embed, ephemeral=True)

        # ── /pd-setup  (Manage Channels + Manage Messages) ────────────────
        @self.tree.command(
            name="pd-setup",
            description="[Server Admin Command] Create the TTR feed channels in this server and start tracking them.",
        )
        @app_commands.default_permissions(manage_channels=True, manage_messages=True)
        @app_commands.guild_only()
        async def pd_setup(interaction: discord.Interaction) -> None:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message("Must be used inside a server.", ephemeral=True)
                return
            if not self.is_guild_allowed(guild.id):
                await interaction.response.send_message(
                    f"This server isn't on the allowlist. Contact the bot owner to add `{guild.id}`.",
                    ephemeral=True,
                )
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            swept = 0
            try:
                await self._ensure_channels_for_guild(guild)
                api_data = await self._fetch_all()
                for feed_key in self.config.feeds():
                    try:
                        await self._update_feed(guild.id, feed_key, api_data)
                    except Exception:
                        log.exception("Initial refresh failed for %s/%s", guild.id, feed_key)
                swept = await self._sweep_guild_stale(guild.id)
                if swept:
                    log.info("pd-setup swept %d stale message(s) in %s", swept, guild.id)
                await self._save_state()
            except discord.Forbidden:
                await interaction.followup.send(
                    "I'm missing permissions. Make sure I have **Manage Channels**, "
                    "**Send Messages**, and **Embed Links**, then try again.",
                    ephemeral=True,
                )
                return
            channels_msg = ", ".join(f"#{n}" for n in self.config.feeds().values())
            tail = f" Cleaned up {swept} old message(s)." if swept else ""
            await interaction.followup.send(
                f"All set! Tracking **{channels_msg}** and `#{self.config.channel_suit_calculator}`. "
                f"Refreshes every {self.config.refresh_interval}s.{tail}",
                ephemeral=True,
            )

        # ── /pd-refresh  (all users, guild only) ──────────────────────────
        _REFRESH_COOLDOWN = 600  # 10 minutes in seconds

        @self.tree.command(
            name="pd-refresh",
            description="[User Command] Force an immediate refresh of TTR feeds in this server.",
        )
        @app_commands.guild_only()
        async def pd_refresh(interaction: discord.Interaction) -> None:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message("Must be used inside a server.", ephemeral=True)
                return

            # Check manage_messages permission to bypass cooldown.
            member = interaction.user
            can_bypass = (
                isinstance(member, discord.Member)
                and member.guild_permissions.manage_messages
            )

            if not can_bypass:
                last_used = self._refresh_cooldowns.get(member.id, 0.0)
                remaining = _REFRESH_COOLDOWN - (time.time() - last_used)
                if remaining > 0:
                    mins, secs = divmod(int(remaining), 60)
                    wait = f"{mins}m {secs}s" if mins else f"{secs}s"
                    await interaction.response.send_message(
                        f"You can use `/pd-refresh` again in **{wait}**.",
                        ephemeral=True,
                    )
                    return

            await interaction.response.defer(ephemeral=True, thinking=True)

            if not can_bypass:
                self._refresh_cooldowns[member.id] = time.time()

            async with self._refresh_lock:
                api_data = await self._fetch_all()
                try:
                    await self._update_feed(guild.id, "information", api_data)
                except Exception:
                    log.exception("Feed refresh failed for guild %s", guild.id)

            swept = 0
            try:
                swept = await self._sweep_guild_stale(guild.id)
            except Exception:
                log.exception("Sweep failed for %s", guild.id)
            if swept:
                await self._save_state()

            tail = f" Cleaned up {swept} old message(s)." if swept else ""
            await interaction.followup.send(f"Refreshed.{tail}", ephemeral=True)

        # ── /pd-teardown  (Manage Channels + Manage Messages) ─────────────
        @self.tree.command(
            name="pd-teardown",
            description="[Server Admin Command] Stop TTR feed tracking. Channels are kept; delete them manually if needed.",
        )
        @app_commands.default_permissions(manage_channels=True, manage_messages=True)
        @app_commands.guild_only()
        async def pd_teardown(interaction: discord.Interaction) -> None:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message("Must be used inside a server.", ephemeral=True)
                return
            existed = self._guilds_block().pop(str(guild.id), None) is not None
            await self._save_state()
            if existed:
                await self._log_teardown(guild, interaction.user)
            msg = (
                "Stopped tracking this server. Channels still exist; delete them manually if you'd like."
                if existed else "Nothing to tear down -- this server isn't being tracked."
            )
            await interaction.response.send_message(msg, ephemeral=True)

        async def self_log_teardown(guild: discord.Guild, invoker: discord.abc.User) -> None:
            """Append one line to teardown_log.txt for every /pd-teardown."""
            try:
                owner_id   = guild.owner_id
                owner_name = "unknown"
                try:
                    owner = guild.owner or await guild.fetch_member(owner_id)
                    owner_name = str(owner)
                except Exception:
                    pass
                ts    = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
                entry = (
                    f"[{ts}]\n"
                    f"  Guild ID    : {guild.id}\n"
                    f"  Server Name : {guild.name}\n"
                    f"  Owner Name  : {owner_name}\n"
                    f"  Owner ID    : {owner_id}\n"
                    f"  Invoked by  : {invoker} (id={invoker.id})\n"
                    f"{'=' * 48}\n"
                )
                with open(TEARDOWN_LOG, "a", encoding="utf-8") as fh:
                    fh.write(entry)
                log.info("Teardown logged for guild %s (%s)", guild.id, guild.name)
            except Exception as exc:
                log.warning("Could not write teardown log: %s", exc)

        self._log_teardown = self_log_teardown

        # ── /pd-ban  (BOT_ADMIN_IDS only) ────────────────────────────────────
        @self.tree.command(
            name="pd-ban",
            description="[Admin] Ban a user from using this bot.",
        )
        @app_commands.allowed_installs(guilds=True, users=True)
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        async def pd_ban(interaction: discord.Interaction, user_id: str, reason: str = "") -> None:
            if interaction.user.id not in self.config.admin_ids:
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
                return
            try:
                uid = int(user_id)
            except ValueError:
                await interaction.response.send_message("Invalid user ID.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self._ban_user(uid, reason or "No reason given.", str(interaction.user), interaction.user.id)
            await interaction.followup.send(f"Banned `{uid}`.", ephemeral=True)

        # ── /pd-unban  (BOT_ADMIN_IDS only) ──────────────────────────────────
        @self.tree.command(
            name="pd-unban",
            description="[Admin] Remove a user's ban.",
        )
        @app_commands.allowed_installs(guilds=True, users=True)
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        async def pd_unban(interaction: discord.Interaction, user_id: str) -> None:
            if interaction.user.id not in self.config.admin_ids:
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
                return
            try:
                uid = int(user_id)
            except ValueError:
                await interaction.response.send_message("Invalid user ID.", ephemeral=True)
                return
            removed = self._unban_user(uid)
            msg = f"Unbanned `{uid}`." if removed else f"User `{uid}` was not banned."
            await interaction.response.send_message(msg, ephemeral=True)

        # ── /pd-banlist  (BOT_ADMIN_IDS only) ────────────────────────────
        @self.tree.command(
            name="pd-banlist",
            description="[Admin] List all banned users.",
        )
        @app_commands.allowed_installs(guilds=True, users=True)
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        async def pd_banlist(interaction: discord.Interaction) -> None:
            if interaction.user.id not in self.config.admin_ids:
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
                return
            banned = self._load_banned()
            if not banned:
                await interaction.response.send_message("No users are currently banned.", ephemeral=True)
                return
            embed = discord.Embed(title="Banned Users", color=0xFF4444)
            for uid_str, record in list(banned.items())[:25]:
                embed.add_field(
                    name=f"ID: {uid_str}",
                    value=(
                        f"Reason: {record.get('reason', 'N/A')}\n"
                        f"Banned: {record.get('banned_at', 'N/A')}\n"
                        f"By: {record.get('banned_by', 'N/A')}"
                    ),
                    inline=False,
                )
            if len(banned) > 25:
                embed.set_footer(text=f"Showing 25 of {len(banned)} entries.")
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ── /pd-quarantine  (BOT_ADMIN_IDS only) ─────────────────────────────
        @self.tree.command(
            name="pd-quarantine",
            description="[Admin] Manually quarantine a guild.",
        )
        @app_commands.allowed_installs(guilds=True, users=True)
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        async def pd_quarantine(interaction: discord.Interaction, guild_id: str, reason: str = "") -> None:
            if interaction.user.id not in self.config.admin_ids:
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
                return
            try:
                gid = int(guild_id)
            except ValueError:
                await interaction.response.send_message("Invalid guild ID.", ephemeral=True)
                return
            if self._is_quarantined(gid):
                await interaction.response.send_message(f"Guild `{gid}` is already quarantined.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self._quarantine_guild(gid, interaction.user.id, manual=True)
            await interaction.followup.send(f"Guild `{gid}` quarantined.", ephemeral=True)

        # ── /pd-unquarantine  (BOT_ADMIN_IDS only) ───────────────────────────
        @self.tree.command(
            name="pd-unquarantine",
            description="[Admin] Lift quarantine from a guild.",
        )
        @app_commands.allowed_installs(guilds=True, users=True)
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        async def pd_unquarantine(interaction: discord.Interaction, guild_id: str) -> None:
            if interaction.user.id not in self.config.admin_ids:
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
                return
            try:
                gid = int(guild_id)
            except ValueError:
                await interaction.response.send_message("Invalid guild ID.", ephemeral=True)
                return
            if not self._is_quarantined(gid):
                await interaction.response.send_message(f"Guild `{gid}` is not quarantined.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self._lift_quarantine(gid)
            await interaction.followup.send(f"Quarantine lifted for guild `{gid}`.", ephemeral=True)

        # ── /pd-quarantine-list  (BOT_ADMIN_IDS only) ────────────────────────
        @self.tree.command(
            name="pd-quarantine-list",
            description="[Admin] List all quarantined guilds.",
        )
        @app_commands.allowed_installs(guilds=True, users=True)
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        async def pd_quarantine_list(interaction: discord.Interaction) -> None:
            if interaction.user.id not in self.config.admin_ids:
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
                return
            q = self._quarantined_guilds()
            if not q:
                await interaction.response.send_message("No guilds are currently quarantined.", ephemeral=True)
                return
            embed = discord.Embed(title="Quarantined Guilds", color=0xFF4444)
            for gid_str, record in list(q.items())[:25]:
                guild_obj = self.get_guild(int(gid_str))
                name = guild_obj.name if guild_obj else gid_str
                triggered_at = record.get("triggered_at", 0)
                ts = f"<t:{int(triggered_at)}:R>" if triggered_at else "unknown"
                embed.add_field(
                    name=name,
                    value=(
                        f"ID: `{gid_str}`\n"
                        f"Triggered by: `{record.get('triggered_by_user_id', 'N/A')}`\n"
                        f"At: {ts}\n"
                        f"Manual: {record.get('manual', False)}"
                    ),
                    inline=False,
                )
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ── /pd-quarantine-refresh  (BOT_ADMIN_IDS only) ─────────────────────
        @self.tree.command(
            name="pd-quarantine-refresh",
            description="[Admin] Force an immediate quarantine scan for all or one guild.",
        )
        @app_commands.allowed_installs(guilds=True, users=True)
        @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
        async def pd_quarantine_refresh(interaction: discord.Interaction, guild_id: str = "") -> None:
            if interaction.user.id not in self.config.admin_ids:
                await interaction.response.send_message("Unauthorized.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            target: int | None = None
            if guild_id:
                try:
                    target = int(guild_id)
                except ValueError:
                    await interaction.followup.send("Invalid guild ID.", ephemeral=True)
                    return
            result = await self._run_quarantine_scan(target_guild_id=target)
            await interaction.followup.send(
                f"Scan complete — {result['scanned']} guild(s) scanned, "
                f"{result['quarantined']} newly quarantined, "
                f"{result['lifted']} lifted.",
                ephemeral=True,
            )

        # ── /calculate  (all users, guild + user install) ──────────────────
        register_calculate(self)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    config = Config.load()
    if not config.guild_allowlist:
        log.warning(
            "GUILD_ALLOWLIST is empty -- the bot cannot join any server. Edit your .env."
        )
    bot = TTRBot(config)
    bot.run(config.token, log_handler=None)


if __name__ == "__main__":
    main()
