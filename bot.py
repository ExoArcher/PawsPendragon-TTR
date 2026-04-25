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
``/ttrinfo``      -- DM current district/invasion/sillymeter info.
``/ttrdoodle``    -- DM the current doodle list.
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
import time
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

STATE_FILE = Path(__file__).with_name("state.json")
STATE_VERSION = 2
ANNOUNCE_FILE = Path(__file__).with_name("panel_announce.txt")
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

        await self._cleanup_announcements_on_startup()
        await self._save_state()

        if not self._refresh_loop.is_running():
            self._refresh_loop.change_interval(seconds=self.config.refresh_interval)
            self._refresh_loop.start()
        if not self._sweep_loop.is_running():
            self._sweep_loop.start()

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
        failed = 0

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

    # --------------------------------------------------------- stale-message sweep

    def _channel_keep_ids(self, guild_id: int, channel_id: int) -> set[int]:
        keep: set[int] = set()
        for entry in self._guild_state(guild_id).values():
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
        return keep

    async def _sweep_channel_stale(
        self, channel: discord.TextChannel, *, keep_ids: set[int], history_limit: int = 200,
    ) -> int:
        if self.user is None:
            return 0
        bot_id = self.user.id
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
        now = time.time()
        expired = [r for r in list(self._announcements()) if float(r.get("expires_at", 0)) <= now]
        for record in expired:
            await self._delete_announcement_record(record)
        if expired:
            await self._save_state()

    # --------------------------------------------------------- panel file announce

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

    # ----------------------------------------------------------------- poll loops

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

    _API_KEYS = ("invasions", "population", "fieldoffices", "doodles")

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

    async def _refresh_once(self) -> None:
        if self._api is None:
            return
        async with self._refresh_lock:
            api_data = await self._fetch_all()
            total_messages = 0
            guilds_updated: set[int] = set()
            for guild_id_str in list(self._guilds_block().keys()):
                try:
                    guild_id = int(guild_id_str)
                except ValueError:
                    continue
                if not self.is_guild_allowed(guild_id) or self.get_guild(guild_id) is None:
                    continue
                for feed_key in self.config.feeds():
                    try:
                        updated = await self._update_feed(guild_id, feed_key, api_data)
                        if updated:
                            total_messages += updated
                            guilds_updated.add(guild_id)
                    except Exception:
                        log.exception("Failed updating %s/%s", guild_id, feed_key)
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
        ids = await self._ensure_messages(guild_id, feed_key, channel, at_least=len(embeds))
        kept_ids: list[int] = []
        edited = 0
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
            await asyncio.sleep(1.5)
        for mid in ids[len(embeds):]:
            try:
                await (await channel.fetch_message(mid)).edit(
                    embed=discord.Embed(description="*(no data for this tier right now)*", color=0x95A5A6)
                )
                kept_ids.append(mid)
                edited += 1
            except discord.NotFound:
                pass
            await asyncio.sleep(1.5)
        self._set_state(guild_id, feed_key, channel.id, kept_ids)
        return edited

    # ------------------------------------------------------- announcement broadcast

    async def _broadcast_announcement(self, text: str) -> tuple[int, int, int]:
        embed = discord.Embed(title=ANNOUNCEMENT_TITLE, description=text, color=0xF1C40F)
        embed.set_footer(text=f"This message will auto-delete in {ANNOUNCEMENT_TTL_SECONDS // 60} minutes.")
        expires_at = time.time() + ANNOUNCEMENT_TTL_SECONDS
        sent = failed = 0
        guilds_touched: set[int] = set()
        for guild_id_str, gs in list(self._guilds_block().items()):
            try:
                guild_id = int(guild_id_str)
            except ValueError:
                continue
            for feed_key in self.config.feeds():
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

    # ----------------------------------------------------------------- commands

    def _register_commands(self) -> None:

        # -- /ttrinfo  (all users) ------------------------------------------
        @self.tree.command(
            name="ttrinfo",
            description="[User Command] See current Toontown district, invasion, field office, and Silly Meter info.",
        )
        @app_commands.guild_only()
        async def ttrinfo(interaction: discord.Interaction) -> None:
            await interaction.response.defer(ephemeral=True, thinking=True)
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

            info_embed  = format_information(invasions=invasions, population=population, fieldoffices=fieldoffices)
            silly_embed = format_sillymeter(sillymeter)
            try:
                await interaction.user.send(embed=info_embed)
                await interaction.user.send(embed=silly_embed)
                await interaction.followup.send("Check your DMs! 📬", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send(
                    "I couldn't DM you -- please enable DMs from server members and try again.",
                    ephemeral=True,
                )

        # -- /ttrdoodle  (all users) ----------------------------------------
        @self.tree.command(
            name="ttrdoodle",
            description="[User Command] See the current Toontown doodle list with trait ratings.",
        )
        @app_commands.guild_only()
        async def ttrdoodle(interaction: discord.Interaction) -> None:
            await interaction.response.defer(ephemeral=True, thinking=True)
            if self._api is None:
                await interaction.followup.send("API client not ready yet -- try again in a moment.", ephemeral=True)
                return
            doodle_data = await self._api.fetch("doodles")
            embeds = format_doodles(doodle_data)
            try:
                for embed in embeds:
                    await interaction.user.send(embed=embed)
                await interaction.followup.send("Check your DMs! 📬", ephemeral=True)
            except discord.Forbidden:
                await interaction.followup.send(
                    "I couldn't DM you -- please enable DMs from server members and try again.",
                    ephemeral=True,
                )

        # -- /laq-setup  (Manage Channels + Manage Messages) --------------
        @self.tree.command(
            name="laq-setup",
            description="[Server Admin Command] Create the TTR feed channels in this server and start tracking them.",
        )
        @app_commands.default_permissions(manage_channels=True, manage_messages=True)
        @app_commands.guild_only()
        async def laq_setup(interaction: discord.Interaction) -> None:
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
                    log.info("laq-setup swept %d stale message(s) in %s", swept, guild.id)
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
                f"All set! Tracking **{channels_msg}**. "
                f"Refreshes every {self.config.refresh_interval}s.{tail}",
                ephemeral=True,
            )

        # -- /laq-refresh  (all users) -------------------------------------
        @self.tree.command(
            name="laq-refresh",
            description="[User Command] Force an immediate refresh of all TTR feeds and remove old messages.",
        )
        @app_commands.guild_only()
        async def laq_refresh(interaction: discord.Interaction) -> None:
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self._refresh_once()
            swept = 0
            if interaction.guild is not None:
                try:
                    swept = await self._sweep_guild_stale(interaction.guild.id)
                except Exception:
                    log.exception("Sweep failed for %s", interaction.guild.id)
                if swept:
                    await self._save_state()
            tail = f" Cleaned up {swept} old message(s)." if swept else ""
            await interaction.followup.send(f"Refreshed.{tail}", ephemeral=True)

        # -- /laq-teardown  (Manage Channels + Manage Messages) -----------
        @self.tree.command(
            name="laq-teardown",
            description="[Server Admin Command] Stop TTR feed tracking. Channels are kept; delete them manually if needed.",
        )
        @app_commands.default_permissions(manage_channels=True, manage_messages=True)
        @app_commands.guild_only()
        async def laq_teardown(interaction: discord.Interaction) -> None:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message("Must be used inside a server.", ephemeral=True)
                return
            existed = self._guilds_block().pop(str(guild.id), None) is not None
            await self._save_state()
            msg = (
                "Stopped tracking this server. Channels still exist; delete them manually if you'd like."
                if existed else "Nothing to tear down -- this server isn't being tracked."
            )
            await interaction.response.send_message(msg, ephemeral=True)

        # -- admin-only guard ----------------------------------------------
        async def _reject_non_admin(interaction: discord.Interaction) -> bool:
            if not self.config.is_admin(interaction.user.id):
                log.info("Rejecting non-admin %s (id=%s)", interaction.user, interaction.user.id)
                await interaction.response.send_message(
                    f"This command is restricted to bot admins. "
                    f"Your user ID `{interaction.user.id}` is not in `BOT_ADMIN_IDS`.",
                    ephemeral=True,
                )
                return True
            return False

        # -- /laq-announce  (owner only) -----------------------------------
        @self.tree.command(
            name="laq-announce",
            description="[Bot Admin Command] Broadcast a message to every tracked server. Auto-deletes in 30 min.",
        )
        @app_commands.describe(text="The announcement text to send to every tracked server.")
        async def laq_announce(interaction: discord.Interaction, text: str) -> None:
            if await _reject_non_admin(interaction):
                return
            text = text.strip()
            if not text:
                await interaction.response.send_message("Announcement text cannot be empty.", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            sent, failed, guilds_touched = await self._broadcast_announcement(text)
            tracked = len(self._guilds_block())
            ttl_min = ANNOUNCEMENT_TTL_SECONDS // 60
            if sent == 0:
                msg = (
                    "Broadcast sent **0** messages -- no servers are tracked yet. "
                    "Run `/laq-setup` in each server first."
                    if tracked == 0 else
                    f"Broadcast sent **0** messages despite {tracked} tracked server(s). "
                    "Check the console log -- the bot may have lost channel permissions."
                )
            else:
                msg = (
                    f"Broadcast complete: **{sent}** message(s) across **{guilds_touched}** server(s)"
                    + (f", {failed} failed" if failed else "")
                    + f". Auto-deletes in {ttl_min} min."
                )
            await interaction.followup.send(msg, ephemeral=True)



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
