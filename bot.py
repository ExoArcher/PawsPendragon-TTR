# -*- coding: utf-8 -*-
"""TTR Discord bot -- multi-guild live feeds for the public TTR APIs.

How it works
------------
1. The bot is invited to one or more Discord servers. Only servers
   whose ID is in the *effective* allowlist (env ``GUILD_ALLOWLIST``
   u runtime allowlist persisted in ``state.json``) are accepted; the
   bot leaves any other guild that tries to add it, DMing the owner
   with instructions to request access from ExoArcher.
2. In each allowed guild, an admin runs **``/laq-setup``** once. That
   command finds-or-creates the ``Toontown Rewritten`` category plus a
   ``#tt-information`` and ``#tt-doodles`` channel, posts a placeholder
   message in each, and stores the message IDs in ``state.json``.
3. A background task runs every ``$REFRESH_INTERVAL`` seconds, fetches
   the TTR APIs ONCE, and edits each tracked guild's messages in place.
4. A separate sweep task runs every 15 minutes removing stale bot messages.

Slash commands (all users)
--------------------------
``/ttrinfo``      -- DM current district/invasion/sillymeter info. Works as a User App.
``/doodleinfo``   -- DM the full doodle list with ratings. Works as a User App.
``/laq-refresh``  -- force an immediate refresh and sweep old messages.

Slash commands (Manage Channels + Manage Messages)
---------------------------------------------------
``/laq-setup``    -- create channels and start tracking this guild.
``/laq-teardown`` -- stop tracking this guild (channels are NOT deleted).

Slash commands (bot owner only)
--------------------------------
``/laq-announce`` -- broadcast a message to every tracked guild.

Panel announcements
-------------------
Create ``panel_announce.txt`` in the File Manager. The bot picks it up
within 90 seconds, broadcasts it to every tracked guild, and deletes it.

Console commands (hosting panel stdin)
---------------------------------------
``stop``    -- Broadcast a maintenance-down embed to all servers, then shut down.
``restart`` -- Broadcast a restarting embed to all servers, then hot-restart the process.
``help``    -- List available console commands.
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
_GIT_REPO = "https://github.com/ExoArcher/LanceAQuack-TTR"

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
        # Compare local HEAD vs remote to avoid infinite restart loop
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
import os
import sys
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("ttr-bot")

STATE_FILE         = Path(__file__).with_name("state.json")
STATE_VERSION      = 2
ANNOUNCE_FILE      = Path(__file__).with_name("panel_announce.txt")
TEARDOWN_LOG       = Path(__file__).with_name("teardown_log.txt")
WELCOMED_FILE      = Path(__file__).with_name("welcomed_users.json")
BANNED_FILE        = Path(__file__).with_name("banned_users.json")
ANNOUNCEMENT_TITLE = "📢 LAQ Bot Announcement"
ANNOUNCEMENT_TTL_SECONDS = 30 * 60

# Shown to any guild owner whose server fails the allowlist check.
CLOSED_ACCESS_MSG = (
    "Hello! Thank you for your enthusiasm to have me join your community! "
    "At this time I am only in closed access -- please DM **ExoArcher** on "
    "Discord (user ID `310233741354336257`) to request access."
)


class TTRBot(discord.Client):
    def __init__(self, config: Config) -> None:
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(intents=intents)

        self.config = config
        self.tree = app_commands.CommandTree(self)
        self.state: dict[str, Any] = self._load_state()
        self._api: TTRApiClient | None = None
        self._refresh_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        # Set by the console 'stop' command so close() skips its own
        # duplicate maintenance broadcast.
        self._console_stop_sent: bool = False

    # ------------------------------------------------------------------ state

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
        return {"_version": STATE_VERSION, "guilds": {}, "allowlist": [], "announcements": []}

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

    # --------------------------------------------------------------- lifecycle

    async def setup_hook(self) -> None:
        self._api = TTRApiClient(self.config.user_agent)
        await self._api.__aenter__()

        # Push an empty global command list to Discord, wiping any old
        # stale global commands (ttr_refresh, laq_guild_add, etc.).
        self.tree.clear_commands(guild=None)
        await self.tree.sync()

        # Register the current commands in memory only.
        # They will be synced per-guild in on_ready / on_guild_join,
        # which prevents Discord from showing global + guild duplicates.
        self._register_commands()

    async def close(self) -> None:
        """Broadcast maintenance notices then shut down cleanly."""
        log.info("Shutdown signal received -- sending maintenance notices...")
        if not self._console_stop_sent:
            # Only fire the automatic notice when the console 'stop' command
            # hasn't already sent its own version, preventing a duplicate.
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
        # Guild syncs propagate instantly; this also removes leftover
        # ttr_refresh / laq_guild_add commands from previous versions.
        for guild in list(self.guilds):
            if not self.is_guild_allowed(guild.id):
                continue
            await self._sync_commands_to_guild(guild)

        await self._cleanup_maintenance_msgs()
        await self._cleanup_announcements_on_startup()
        await self._save_state()

        if not self._refresh_loop.is_running():
            self._refresh_loop.change_interval(seconds=self.config.refresh_interval)
            self._refresh_loop.start()
        if not self._sweep_loop.is_running():
            self._sweep_loop.start()

        # Start the hosting-panel console listener (stop / restart / help).
        asyncio.create_task(self._console_listener(), name="console-listener")

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

    async def _sync_commands_to_guild(self, guild: discord.Guild) -> None:
        """Aggressively wipe all old per-guild commands then push the new set.

        Two-phase sync:
          1. Push an empty tree -> Discord deletes every guild-specific command
             (removes ttr_setup, ttr_refresh, laq_guild_add, duplicates, etc.)
          2. Copy the in-memory global tree and push -> registers new /laq-* commands.
        """
        try:
            # Phase 1 -- nuke everything Discord knows about this guild.
            self.tree.clear_commands(guild=guild)
            await self.tree.sync(guild=guild)
            # Phase 2 -- register the current command set.
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

    # ------------------------------------------------- channel bootstrapping

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
        await self._save_state()

    async def _send_placeholder(self, key: str, channel: discord.TextChannel) -> discord.Message:
        msg = await channel.send(embed=discord.Embed(
            title=f"Loading {key}...", description="Fetching the latest data from TTR.", color=0x95A5A6,
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
        while len(verified) < at_least:
            msg = await self._send_placeholder(key, channel)
            verified.append(msg.id)
        self._set_state(guild_id, key, channel.id, verified)
        return verified

    # ------------------------------------------------------- announcement cleanup

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

        # Delete any tracked announcement messages from the previous session.
        stale_records = list(self._announcements())
        if stale_records:
            log.info("Startup cleanup: found %d tracked announcement(s) to clear.", len(stale_records))
        for record in stale_records:
            try:
                await self._delete_announcement_record(record)
                cleared += 1
            except Exception:
                failed += 1

        # Scan information channels for orphaned announcement embeds not in state.
        for guild_id_str, gs in list(self._guilds_block().items()):
            try:
                guild_id = int(guild_id_str)
           