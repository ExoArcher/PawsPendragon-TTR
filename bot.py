"""TTR Discord bot — multi-guild live feeds for the public TTR APIs.

How it works
------------
1. The bot is invited to one or more Discord servers. Only servers
   whose ID is in the *effective* allowlist (env ``GUILD_ALLOWLIST``
   ∪ runtime allowlist persisted in ``state.json``) are accepted; the
   bot leaves any other guild that tries to add it.
2. In each allowed guild, an admin runs **``/ttr_setup``** once. That
   command finds-or-creates the ``Toontown Rewritten`` category plus a
   ``#tt-information`` and ``#tt-doodles`` channel, posts a placeholder
   message in each, and stores the message IDs in ``state.json``.
3. A single background task runs every ``$REFRESH_INTERVAL`` seconds,
   fetches the four TTR APIs ONCE, and edits each tracked guild's
   messages in place. The channels stay clean — no new message per tick.

Slash commands
--------------
Server admin (``Manage Server``):
``/ttr_setup``    — create channels and start tracking this guild.
``/ttr_refresh``  — force an immediate refresh of all tracked guilds.
``/ttr_status``   — print the bot's current state for this guild.
``/ttr_teardown`` — stop tracking this guild (channels are NOT deleted).

Bot owner only (``BOT_OWNER_IDS``):
``/laq_announce``     — broadcast a message to every tracked guild.
                        Auto-deletes after 30 minutes; orphans are
                        cleaned on the bot's next startup.
``/laq_guild_add``    — add a guild ID to the runtime allowlist.
``/laq_guild_remove`` — remove a guild ID from the allowlist (the bot
                        will leave the guild and drop its tracking state).
"""
from __future__ import annotations

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
from formatters import FORMATTERS
from ttr_api import TTRApiClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("ttr-bot")

# Persisted channel + message IDs and runtime admin state.
# Schema v2:
#   {
#     "_version": 2,
#     "guilds":   {str(guild_id): {feed_key: {channel_id: int, message_ids: [int]}}},
#     "allowlist":     [int, ...],   # runtime additions to GUILD_ALLOWLIST
#     "announcements": [{"guild_id": int, "channel_id": int,
#                        "message_id": int, "expires_at": float}, ...],
#   }
STATE_FILE = Path(__file__).with_name("state.json")
STATE_VERSION = 2

# Title used on broadcast announcement embeds. Also serves as the marker
# we look for at startup when scanning for orphaned announcements that
# survived a previous crash before their TTL expired.
ANNOUNCEMENT_TITLE = "📢 LAQ Bot Announcement"
# 30 minutes, in seconds.
ANNOUNCEMENT_TTL_SECONDS = 30 * 60


class TTRBot(discord.Client):
    def __init__(self, config: Config) -> None:
        # Default intents only — we never read message content.
        intents = discord.Intents.default()
        intents.guilds = True
        super().__init__(intents=intents)

        self.config = config
        self.tree = app_commands.CommandTree(self)
        self.state: dict[str, Any] = self._load_state()
        self._api: TTRApiClient | None = None
        self._refresh_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()

    # ---------- state persistence -----------------------------------

    def _load_state(self) -> dict[str, Any]:
        """Load state.json and migrate older schemas to v2."""
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
            # Make sure all v2 keys exist (defensive against partial files).
            raw.setdefault("guilds", {})
            raw.setdefault("allowlist", [])
            raw.setdefault("announcements", [])
            return raw

        # ---- migrate older schemas ----

        # v0 (legacy single-guild flat): {feed_key: {channel_id, message_ids}}
        if all(
            isinstance(v, dict) and "channel_id" in v
            for v in raw.values()
        ):
            if len(self.config.guild_allowlist) == 1:
                only = next(iter(self.config.guild_allowlist))
                log.info(
                    "Migrating legacy v0 state to v%d under guild %s",
                    STATE_VERSION, only,
                )
                return {
                    "_version": STATE_VERSION,
                    "guilds": {str(only): raw},
                    "allowlist": [],
                    "announcements": [],
                }
            log.warning(
                "Found legacy v0 state but cannot migrate (need exactly "
                "one guild in allowlist). Starting fresh."
            )
            return self._empty_state()

        # v1 (multi-guild flat): {str(guild_id): {feed_key: {...}}}
        if all(
            isinstance(v, dict) and not k.startswith("_")
            for k, v in raw.items()
        ):
            log.info("Migrating v1 state to v%d", STATE_VERSION)
            return {
                "_version": STATE_VERSION,
                "guilds": dict(raw),
                "allowlist": [],
                "announcements": [],
            }

        log.warning("Unrecognised state.json shape; starting fresh.")
        return self._empty_state()

    @staticmethod
    def _empty_state() -> dict[str, Any]:
        return {
            "_version": STATE_VERSION,
            "guilds": {},
            "allowlist": [],
            "announcements": [],
        }

    async def _save_state(self) -> None:
        async with self._state_lock:
            try:
                STATE_FILE.write_text(json.dumps(self.state, indent=2))
            except Exception as e:
                log.warning("Could not save state file: %s", e)

    # ---- state convenience ----

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

    def _set_state(
        self,
        guild_id: int,
        key: str,
        channel_id: int,
        message_ids: list[int],
    ) -> None:
        gs = self._guild_state(guild_id)
        gs[key] = {"channel_id": channel_id, "message_ids": message_ids}

    # ---- runtime allowlist ----

    def _runtime_allowlist(self) -> set[int]:
        return {int(x) for x in self.state.get("allowlist", [])}

    def effective_allowlist(self) -> set[int]:
        """Combined env + runtime allowlist."""
        return set(self.config.guild_allowlist) | self._runtime_allowlist()

    def is_guild_allowed(self, guild_id: int) -> bool:
        return guild_id in self.effective_allowlist()

    async def _add_runtime_allowlist(self, guild_id: int) -> bool:
        """Add a guild to the runtime allowlist. Returns True if newly added."""
        runtime = self._runtime_allowlist()
        if guild_id in runtime or guild_id in self.config.guild_allowlist:
            # Already allowed (whether via env or runtime).
            if guild_id not in runtime:
                # Persist it anyway so removal via slash command is possible.
                runtime.add(guild_id)
                self.state["allowlist"] = sorted(runtime)
                await self._save_state()
            return guild_id not in runtime  # always False here, but explicit
        runtime.add(guild_id)
        self.state["allowlist"] = sorted(runtime)
        await self._save_state()
        return True

    async def _remove_runtime_allowlist(self, guild_id: int) -> bool:
        """Remove a guild from the runtime allowlist. Returns True if it was present."""
        runtime = self._runtime_allowlist()
        env_only = guild_id in self.config.guild_allowlist and guild_id not in runtime
        if guild_id not in runtime and not env_only:
            return False
        runtime.discard(guild_id)
        self.state["allowlist"] = sorted(runtime)
        # Drop tracked state for that guild.
        self._guilds_block().pop(str(guild_id), None)
        await self._save_state()
        return True

    # ---- announcements ----

    def _announcements(self) -> list[dict[str, Any]]:
        return self.state.setdefault("announcements", [])

    async def _record_announcement(
        self, guild_id: int, channel_id: int, message_id: int, expires_at: float
    ) -> None:
        self._announcements().append({
            "guild_id": int(guild_id),
            "channel_id": int(channel_id),
            "message_id": int(message_id),
            "expires_at": float(expires_at),
        })
        await self._save_state()

    # ---------- Discord lifecycle -----------------------------------

    async def setup_hook(self) -> None:
        # Open a persistent aiohttp session for the TTR API.
        self._api = TTRApiClient(self.config.user_agent)
        await self._api.__aenter__()

        self._register_commands()
        # Global sync makes the commands available everywhere the bot
        # is invited, but Discord can take up to an hour to propagate
        # *new* commands the first time. We also sync per-guild in
        # on_ready below for instant propagation in tracked servers.
        await self.tree.sync()

    async def close(self) -> None:
        if self._api is not None:
            await self._api.__aexit__(None, None, None)
        await super().close()

    async def on_ready(self) -> None:
        assert self.user is not None
        log.info("Logged in as %s (id=%s)", self.user, self.user.id)
        log.info(
            "In %d guild(s); env-allowlist=%d entries; "
            "runtime-allowlist=%d entries; owners=%d",
            len(self.guilds),
            len(self.config.guild_allowlist),
            len(self._runtime_allowlist()),
            len(self.config.owner_ids),
        )
        # Print the actual owner IDs so the user can sanity-check that
        # their Discord user ID is in the list. (Owner user IDs are
        # not secrets — they're public on every Discord profile.)
        if self.config.owner_ids:
            log.info(
                "Bot-owner IDs loaded: %s",
                ", ".join(str(i) for i in sorted(self.config.owner_ids)),
            )
        else:
            log.warning(
                "BOT_OWNER_IDS is empty — /laq_* commands will reject "
                "every user. Add your Discord user ID to .env."
            )

        # Enforce allowlist on currently-joined guilds. Anything not on
        # the (env ∪ runtime) list gets a friendly DM (best effort) and
        # is left.
        for guild in list(self.guilds):
            if not self.is_guild_allowed(guild.id):
                log.warning(
                    "Leaving non-allowlisted guild %s (id=%s)",
                    guild.name, guild.id,
                )
                await self._notify_and_leave(guild)

        # Drop state for guilds we're no longer in (cleanup).
        live_ids = {str(g.id) for g in self.guilds}
        for gid in list(self._guilds_block().keys()):
            if gid not in live_ids:
                log.info("Pruning state for departed guild %s", gid)
                self._guilds_block().pop(gid, None)

        # Per-guild sync: copy global commands into each currently-joined
        # allowlisted guild and sync there. Discord propagates per-guild
        # syncs instantly, so newly-added commands like /laq_announce
        # appear in the slash picker right away rather than waiting up
        # to an hour for global propagation.
        for guild in list(self.guilds):
            if not self.is_guild_allowed(guild.id):
                continue
            try:
                self.tree.copy_global_to(guild=guild)
                await self.tree.sync(guild=guild)
                log.info("Per-guild command sync OK for %s (id=%s)",
                         guild.name, guild.id)
            except Exception:  # noqa: BLE001
                log.exception(
                    "Per-guild command sync failed for %s (id=%s)",
                    guild.name, guild.id,
                )

        # Sweep stale / orphaned announcements before the first refresh.
        await self._cleanup_announcements_on_startup()

        await self._save_state()

        if not self._refresh_loop.is_running():
            self._refresh_loop.change_interval(
                seconds=self.config.refresh_interval
            )
            self._refresh_loop.start()

    async def on_guild_join(self, guild: discord.Guild) -> None:
        if not self.is_guild_allowed(guild.id):
            log.warning(
                "Refusing to join non-allowlisted guild %s (id=%s)",
                guild.name, guild.id,
            )
            await self._notify_and_leave(guild)
            return
        log.info("Joined allowlisted guild %s (id=%s)", guild.name, guild.id)

    async def on_guild_remove(self, guild: discord.Guild) -> None:
        log.info("Removed from guild %s (id=%s)", guild.name, guild.id)
        self._guilds_block().pop(str(guild.id), None)
        await self._save_state()

    async def _notify_and_leave(self, guild: discord.Guild) -> None:
        """Try to DM the guild owner explaining why we're leaving, then leave."""
        msg = (
            "Hi! I'm a private TTR feeds bot and I'm not configured to "
            "operate in your server. The owner needs to add your "
            f"server ID (`{guild.id}`) to the bot's allowlist before "
            "re-inviting me."
        )
        try:
            owner = guild.owner or await guild.fetch_member(guild.owner_id)
            if owner is not None:
                await owner.send(msg)
        except Exception as e:  # noqa: BLE001
            log.debug("Could not DM owner of %s: %s", guild.name, e)
        try:
            await guild.leave()
        except Exception as e:  # noqa: BLE001
            log.warning("Failed to leave guild %s: %s", guild.id, e)

    # ---------- channel + message bootstrapping ---------------------

    async def _ensure_channels_for_guild(
        self, guild: discord.Guild
    ) -> None:
        """Find-or-create the category and feed channels for this guild,
        then make sure each feed has its tracking messages posted."""
        category = discord.utils.get(
            guild.categories, name=self.config.category_name
        )
        if category is None:
            log.info(
                "Creating category %r in %s",
                self.config.category_name, guild.name,
            )
            category = await guild.create_category(
                self.config.category_name
            )

        for key, channel_name in self.config.feeds().items():
            channel = discord.utils.get(
                guild.text_channels, name=channel_name
            )
            if channel is None:
                log.info(
                    "Creating channel #%s in %s",
                    channel_name, guild.name,
                )
                channel = await guild.create_text_channel(
                    channel_name,
                    category=category,
                    topic=f"Live TTR {key} feed — auto-updated by bot.",
                )
            await self._ensure_messages(guild.id, key, channel, at_least=1)

        await self._save_state()

    async def _send_placeholder(
        self, key: str, channel: discord.TextChannel
    ) -> discord.Message:
        placeholder = discord.Embed(
            title=f"Loading {key}…",
            description="Fetching the latest data from TTR.",
            color=0x95A5A6,
        )
        msg = await channel.send(embed=placeholder)
        try:
            await msg.pin(reason="Live TTR feed pin")
        except (discord.Forbidden, discord.HTTPException) as e:
            log.debug("Could not pin message in #%s: %s", channel.name, e)
        return msg

    async def _ensure_messages(
        self,
        guild_id: int,
        key: str,
        channel: discord.TextChannel,
        at_least: int,
    ) -> list[int]:
        """Make sure the feed has at least `at_least` live messages."""
        ids = self._state_message_ids(guild_id, key)
        verified: list[int] = []
        for mid in ids:
            try:
                await channel.fetch_message(mid)
                verified.append(mid)
            except discord.NotFound:
                log.info(
                    "Stored message %s for %s/%s is gone.",
                    mid, guild_id, key,
                )
            except discord.Forbidden:
                log.warning(
                    "No permission to fetch message in #%s", channel.name
                )
                verified.append(mid)

        while len(verified) < at_least:
            msg = await self._send_placeholder(key, channel)
            verified.append(msg.id)

        self._set_state(guild_id, key, channel.id, verified)
        return verified

    # ---------- announcement cleanup --------------------------------

    async def _delete_announcement_record(
        self, record: dict[str, Any]
    ) -> None:
        """Delete the Discord message referenced by `record` and drop it
        from state.announcements. Any errors are logged and swallowed."""
        guild_id = int(record.get("guild_id", 0))
        channel_id = int(record.get("channel_id", 0))
        message_id = int(record.get("message_id", 0))
        try:
            channel = self.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                try:
                    msg = await channel.fetch_message(message_id)
                    await msg.delete()
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    log.warning(
                        "No permission to delete announcement %s in #%s",
                        message_id, channel.name,
                    )
        except Exception:  # noqa: BLE001
            log.exception(
                "Failed deleting announcement record %s/%s/%s",
                guild_id, channel_id, message_id,
            )
        # Drop from list regardless — we don't want to retry forever.
        self._announcements()[:] = [
            r for r in self._announcements()
            if int(r.get("message_id", -1)) != message_id
        ]

    async def _cleanup_announcements_on_startup(self) -> None:
        """On startup we delete every announcement we previously
        broadcast — anything still up is from a session that crashed
        before its TTL fired. We also scan each tracked information
        channel for stray bot messages whose embed title matches the
        announcement marker (defensive: covers cases where state.json
        was lost or rolled back)."""
        # 1) Delete tracked announcements.
        for record in list(self._announcements()):
            await self._delete_announcement_record(record)

        # 2) Defensive scan: for each tracked guild's #tt-information
        #    channel, look at recent history for our own messages with
        #    the announcement title and delete them too.
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
                    if not msg.embeds:
                        continue
                    title = (msg.embeds[0].title or "")
                    if ANNOUNCEMENT_TITLE in title:
                        try:
                            await msg.delete()
                            log.info(
                                "Deleted orphan announcement %s in %s/#%s",
                                msg.id, guild_id, channel.name,
                            )
                        except (discord.Forbidden, discord.NotFound):
                            pass
            except discord.Forbidden:
                log.debug(
                    "No permission to read history in %s/#%s",
                    guild_id, channel.name,
                )
            except Exception:  # noqa: BLE001
                log.exception(
                    "Orphan-announcement scan failed in %s/#%s",
                    guild_id, getattr(channel, "name", "?"),
                )

    # ---------- stale-message sweep --------------------------------

    def _channel_keep_ids(
        self, guild_id: int, channel_id: int,
    ) -> set[int]:
        """Build the set of bot message IDs we want to KEEP in
        `channel_id` for this guild — currently-tracked feed messages
        plus any announcement records targeting that channel."""
        keep: set[int] = set()
        gs = self._guild_state(guild_id)
        for entry in gs.values():
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
        self,
        channel: discord.TextChannel,
        *,
        keep_ids: set[int],
        history_limit: int = 200,
    ) -> int:
        """Delete bot messages in `channel` whose IDs are not in
        `keep_ids`. Returns the number of messages deleted. Bots can
        delete their own messages without Manage Messages, so this
        only requires Read Message History on the channel."""
        if self.user is None:
            return 0
        bot_id = self.user.id
        deleted = 0
        try:
            async for msg in channel.history(limit=history_limit):
                if msg.author.id != bot_id:
                    continue
                if msg.id in keep_ids:
                    continue
                try:
                    await msg.delete()
                    deleted += 1
                except discord.NotFound:
                    pass
                except discord.Forbidden:
                    # Shouldn't happen for own messages, but log once.
                    log.debug(
                        "Forbidden deleting own msg %s in #%s",
                        msg.id, channel.name,
                    )
                except discord.HTTPException as e:
                    log.debug(
                        "HTTP error deleting %s in #%s: %s",
                        msg.id, channel.name, e,
                    )
        except discord.Forbidden:
            log.debug(
                "No Read Message History in #%s; skipping sweep",
                channel.name,
            )
        return deleted

    async def _sweep_guild_stale(self, guild_id: int) -> int:
        """Sweep every tracked feed channel for this guild; delete bot
        messages that aren't in the keep-set. Returns total deletions."""
        total = 0
        gs = self._guild_state(guild_id)
        seen_channels: set[int] = set()
        for entry in gs.values():
            channel_id = int(entry.get("channel_id", 0))
            if channel_id in seen_channels or channel_id == 0:
                continue
            seen_channels.add(channel_id)
            channel = self.get_channel(channel_id)
            if not isinstance(channel, discord.TextChannel):
                continue
            keep = self._channel_keep_ids(guild_id, channel_id)
            total += await self._sweep_channel_stale(channel, keep_ids=keep)
        return total

    async def _sweep_expired_announcements(self) -> None:
        """Delete any announcement whose TTL has elapsed. Called once
        per refresh tick."""
        now = time.time()
        expired = [
            r for r in list(self._announcements())
            if float(r.get("expires_at", 0)) <= now
        ]
        for record in expired:
            await self._delete_announcement_record(record)
        if expired:
            await self._save_state()

    # ---------- the poll loop --------------------------------------

    @tasks.loop(seconds=60)
    async def _refresh_loop(self) -> None:
        # Sweep first so expired announcements vanish promptly even on
        # ticks where the API fetches all fail.
        try:
            await self._sweep_expired_announcements()
        except Exception:  # noqa: BLE001
            log.exception("Announcement sweep failed")
        await self._refresh_once()

    @_refresh_loop.before_loop
    async def _before_loop(self) -> None:
        await self.wait_until_ready()

    # API endpoints fetched every tick. Shared across feeds and across
    # guilds so we only hit each TTR endpoint once per tick.
    _API_KEYS = (
        "invasions",
        "population",
        "fieldoffices",
        "doodles",
    )

    async def _fetch_all(self) -> dict[str, dict | None]:
        if self._api is None:
            return {k: None for k in self._API_KEYS}
        results = await asyncio.gather(
            *(self._api.fetch(k) for k in self._API_KEYS),
            return_exceptions=True,
        )
        api_data: dict[str, dict | None] = {}
        for k, r in zip(self._API_KEYS, results):
            if isinstance(r, BaseException):
                log.warning("Fetch %s raised: %s", k, r)
                api_data[k] = None
            else:
                api_data[k] = r
        return api_data

    async def _refresh_once(self) -> None:
        if self._api is None:
            return
        async with self._refresh_lock:
            api_data = await self._fetch_all()
            for guild_id_str in list(self._guilds_block().keys()):
                try:
                    guild_id = int(guild_id_str)
                except ValueError:
                    continue
                if not self.is_guild_allowed(guild_id):
                    continue
                guild = self.get_guild(guild_id)
                if guild is None:
                    continue
                for feed_key in self.config.feeds():
                    try:
                        await self._update_feed(
                            guild_id, feed_key, api_data,
                        )
                    except Exception:  # noqa: BLE001
                        log.exception(
                            "Failed updating %s/%s", guild_id, feed_key,
                        )
            await self._save_state()

    async def _update_feed(
        self,
        guild_id: int,
        feed_key: str,
        api_data: dict[str, dict | None],
    ) -> None:
        entry = self._guild_state(guild_id).get(feed_key)
        if not entry:
            return
        channel = self.get_channel(int(entry["channel_id"]))
        if not isinstance(channel, discord.TextChannel):
            return

        formatter = FORMATTERS.get(feed_key)
        if formatter is None:
            log.warning("No formatter registered for feed %r", feed_key)
            return
        embeds = formatter(api_data)
        if not isinstance(embeds, list):
            embeds = [embeds]
        if not embeds:
            return

        ids = await self._ensure_messages(
            guild_id, feed_key, channel, at_least=len(embeds),
        )

        kept_ids: list[int] = []
        for mid, embed in zip(ids, embeds):
            try:
                message = await channel.fetch_message(mid)
                await message.edit(embed=embed)
                kept_ids.append(mid)
            except discord.NotFound:
                log.info(
                    "Message %s for %s/%s vanished mid-edit; reposting.",
                    mid, guild_id, feed_key,
                )
                new_msg = await channel.send(embed=embed)
                try:
                    await new_msg.pin(reason="Live TTR feed pin")
                except (discord.Forbidden, discord.HTTPException):
                    pass
                kept_ids.append(new_msg.id)

        # Blank any leftover messages from a previous (longer) tick so
        # they don't lie about old data, but keep their IDs.
        for mid in ids[len(embeds):]:
            try:
                message = await channel.fetch_message(mid)
                blank = discord.Embed(
                    description="*(no data for this tier right now)*",
                    color=0x95A5A6,
                )
                await message.edit(embed=blank)
                kept_ids.append(mid)
            except discord.NotFound:
                pass

        self._set_state(guild_id, feed_key, channel.id, kept_ids)

    # ---------- announcement broadcast helper -----------------------

    async def _broadcast_announcement(
        self, text: str
    ) -> tuple[int, int, int]:
        """Post the announcement embed to *every* tracked feed channel
        in every tracked guild — both #tt-information and #tt-doodles —
        so the announcement shows up directly below each pinned embed.
        Returns (sent_count, failed_count, guilds_touched)."""
        embed = discord.Embed(
            title=ANNOUNCEMENT_TITLE,
            description=text,
            color=0xF1C40F,
        )
        embed.set_footer(
            text=(
                f"This message will auto-delete in "
                f"{ANNOUNCEMENT_TTL_SECONDS // 60} minutes."
            )
        )

        expires_at = time.time() + ANNOUNCEMENT_TTL_SECONDS
        sent = 0
        failed = 0
        guilds_touched: set[int] = set()
        for guild_id_str, gs in list(self._guilds_block().items()):
            try:
                guild_id = int(guild_id_str)
            except ValueError:
                continue
            # Post into every configured feed channel — currently
            # 'information' and 'doodles'. Iterating Config.feeds()
            # keeps this in sync if more feeds get added later.
            for feed_key in self.config.feeds():
                entry = gs.get(feed_key)
                if not entry:
                    log.debug(
                        "Guild %s has no tracked %s feed; skipping.",
                        guild_id, feed_key,
                    )
                    continue
                channel = self.get_channel(int(entry.get("channel_id", 0)))
                if not isinstance(channel, discord.TextChannel):
                    log.debug(
                        "Guild %s/%s channel_id %s missing; skipping.",
                        guild_id, feed_key, entry.get("channel_id"),
                    )
                    continue
                try:
                    msg = await channel.send(embed=embed)
                    await self._record_announcement(
                        guild_id, channel.id, msg.id, expires_at,
                    )
                    sent += 1
                    guilds_touched.add(guild_id)
                    log.info(
                        "Announcement posted to %s/#%s (msg=%s)",
                        guild_id, channel.name, msg.id,
                    )
                except (discord.Forbidden, discord.HTTPException) as e:
                    log.warning(
                        "Failed to broadcast to %s/#%s: %s",
                        guild_id, channel.name, e,
                    )
                    failed += 1
        return sent, failed, len(guilds_touched)

    # ---------- slash commands --------------------------------------

    def _register_commands(self) -> None:
        # ---- standard server-admin commands ----
        @self.tree.command(
            name="ttr_setup",
            description=(
                "Create the TTR feed channels in this server and start "
                "tracking them."
            ),
        )
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.guild_only()
        async def ttr_setup(interaction: discord.Interaction) -> None:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message(
                    "This command must be used inside a server.",
                    ephemeral=True,
                )
                return
            if not self.is_guild_allowed(guild.id):
                await interaction.response.send_message(
                    "This server isn't on the bot's allowlist. Ask the "
                    f"bot owner to add `{guild.id}` via "
                    "`/laq_guild_add`.",
                    ephemeral=True,
                )
                return

            await interaction.response.defer(ephemeral=True, thinking=True)
            swept = 0
            try:
                await self._ensure_channels_for_guild(guild)
                # Kick off an immediate refresh so the new channels
                # have real data instead of the loading placeholder.
                api_data = await self._fetch_all()
                for feed_key in self.config.feeds():
                    try:
                        await self._update_feed(guild.id, feed_key, api_data)
                    except Exception:  # noqa: BLE001
                        log.exception(
                            "Initial refresh failed for %s/%s",
                            guild.id, feed_key,
                        )
                # After (re)posting feed messages, delete any leftover
                # bot messages in those channels — covers stale loading
                # placeholders, expired announcements, and embeds from
                # crashed prior runs whose IDs are no longer tracked.
                swept = await self._sweep_guild_stale(guild.id)
                if swept:
                    log.info(
                        "ttr_setup swept %d stale bot message(s) in %s",
                        swept, guild.id,
                    )
                await self._save_state()
            except discord.Forbidden:
                await interaction.followup.send(
                    "I'm missing permissions. Make sure I have **Manage "
                    "Channels**, **Send Messages**, and **Embed Links** "
                    "in this server, then try again.",
                    ephemeral=True,
                )
                return

            channels_msg = ", ".join(
                f"#{name}" for name in self.config.feeds().values()
            )
            tail = f" Cleaned up {swept} old message(s)." if swept else ""
            await interaction.followup.send(
                f"All set! Tracking **{channels_msg}**. They'll refresh "
                f"every {self.config.refresh_interval} seconds.{tail}",
                ephemeral=True,
            )

        @self.tree.command(
            name="ttr_refresh",
            description="Force an immediate refresh of all TTR feeds.",
        )
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.guild_only()
        async def ttr_refresh(interaction: discord.Interaction) -> None:
            await interaction.response.defer(ephemeral=True, thinking=True)
            await self._refresh_once()
            # Sweep stale bot messages in this guild's tracked channels
            # so any orphans left over from previous runs disappear.
            swept = 0
            if interaction.guild is not None:
                try:
                    swept = await self._sweep_guild_stale(interaction.guild.id)
                except Exception:  # noqa: BLE001
                    log.exception(
                        "Stale-message sweep failed for %s",
                        interaction.guild.id,
                    )
                if swept:
                    await self._save_state()
            tail = f" Cleaned up {swept} old message(s)." if swept else ""
            await interaction.followup.send(
                f"Refreshed.{tail}", ephemeral=True,
            )

        @self.tree.command(
            name="ttr_status",
            description="Show the bot's current feed state for this server.",
        )
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.guild_only()
        async def ttr_status(interaction: discord.Interaction) -> None:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message(
                    "This command must be used inside a server.",
                    ephemeral=True,
                )
                return
            gs = self._guild_state(guild.id)
            lines = [
                f"Refresh interval: **{self.config.refresh_interval}s**",
                f"Tracked feeds in this server: **{len(gs)}**",
            ]
            if not gs:
                lines.append("\n*Run `/ttr_setup` to start tracking.*")
            for key, v in gs.items():
                mids = self._state_message_ids(guild.id, key)
                mids_str = ", ".join(str(m) for m in mids) or "none"
                lines.append(
                    f"• **{key}** — <#{v['channel_id']}> "
                    f"({len(mids)} msg: {mids_str})"
                )
            await interaction.response.send_message(
                "\n".join(lines), ephemeral=True
            )

        @self.tree.command(
            name="ttr_teardown",
            # Discord caps slash-command descriptions at 100 chars.
            description="Stop tracking TTR feeds here. Channels are kept; delete them manually if you want.",
        )
        @app_commands.default_permissions(manage_guild=True)
        @app_commands.guild_only()
        async def ttr_teardown(interaction: discord.Interaction) -> None:
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message(
                    "This command must be used inside a server.",
                    ephemeral=True,
                )
                return
            existed = self._guilds_block().pop(str(guild.id), None) is not None
            await self._save_state()
            if existed:
                await interaction.response.send_message(
                    "Stopped tracking this server. The channels still "
                    "exist; delete them manually if you'd like.",
                    ephemeral=True,
                )
            else:
                await interaction.response.send_message(
                    "Nothing to tear down — this server isn't being "
                    "tracked.",
                    ephemeral=True,
                )

        # ---- bot-owner-only admin commands ----
        # NOTE: we deliberately do NOT use @app_commands.default_permissions
        # here. That decorator is a Discord-side UI gate based on the
        # invoker's *server* permissions, not bot-owner status — so a
        # bot owner who isn't an admin in some random guild would see
        # the command vanish from the slash picker. Instead the runtime
        # owner-ID check below is the sole security boundary.

        async def _reject_non_owner(
            interaction: discord.Interaction,
        ) -> bool:
            if not self.config.is_owner(interaction.user.id):
                log.info(
                    "Rejecting non-owner %s (id=%s) on /%s",
                    interaction.user, interaction.user.id,
                    interaction.command.name if interaction.command else "?",
                )
                await interaction.response.send_message(
                    "This command is restricted to the bot owners. "
                    f"Your user ID `{interaction.user.id}` is not in "
                    "`BOT_OWNER_IDS`.",
                    ephemeral=True,
                )
                return True
            return False

        @self.tree.command(
            name="laq_announce",
            description=(
                "Broadcast a message to every tracked server. Auto-deletes "
                "after 30 minutes. Bot-owner only."
            ),
        )
        @app_commands.describe(
            text="The announcement text to send to every tracked server."
        )
        async def laq_announce(
            interaction: discord.Interaction, text: str,
        ) -> None:
            if await _reject_non_owner(interaction):
                return
            text = text.strip()
            if not text:
                await interaction.response.send_message(
                    "Announcement text cannot be empty.",
                    ephemeral=True,
                )
                return

            await interaction.response.defer(ephemeral=True, thinking=True)
            sent, failed, guilds_touched = await self._broadcast_announcement(
                text
            )
            tracked_guilds = len(self._guilds_block())
            ttl_min = ANNOUNCEMENT_TTL_SECONDS // 60

            if sent == 0:
                if tracked_guilds == 0:
                    msg = (
                        "Broadcast sent **0** messages — no servers are "
                        "currently tracked. An admin needs to run "
                        "`/ttr_setup` in each server first so the bot "
                        "knows which channels to post into."
                    )
                else:
                    msg = (
                        f"Broadcast sent **0** messages despite "
                        f"{tracked_guilds} tracked server(s). The bot "
                        "may have lost permission to post in the feed "
                        "channels, or the channels were deleted. Check "
                        "the bot console log for the exact reason."
                    )
            else:
                msg = (
                    f"Broadcast complete: **{sent}** message(s) posted "
                    f"across **{guilds_touched}** server(s) "
                    f"(both `#tt-information` and `#tt-doodles` per "
                    f"server)"
                    + (f", {failed} failed" if failed else "")
                    + f". Each post will auto-delete in {ttl_min} minutes."
                )
            await interaction.followup.send(msg, ephemeral=True)

        @self.tree.command(
            name="laq_guild_add",
            description=(
                "Add a Discord server ID to the bot's allowlist. "
                "Bot-owner only."
            ),
        )
        @app_commands.describe(
            guild_id="The numeric Discord server (guild) ID to allowlist.",
        )
        async def laq_guild_add(
            interaction: discord.Interaction, guild_id: str,
        ) -> None:
            if await _reject_non_owner(interaction):
                return
            try:
                gid = int(guild_id.strip())
            except (TypeError, ValueError):
                await interaction.response.send_message(
                    f"`{guild_id}` is not a valid numeric server ID.",
                    ephemeral=True,
                )
                return

            await interaction.response.defer(ephemeral=True, thinking=True)
            already = (
                gid in self.config.guild_allowlist
                or gid in self._runtime_allowlist()
            )
            await self._add_runtime_allowlist(gid)

            invite_url = (
                f"https://discord.com/api/oauth2/authorize"
                f"?client_id={self.user.id if self.user else 0}"
                f"&permissions=93200"
                f"&scope=bot+applications.commands"
            )
            if already:
                await interaction.followup.send(
                    f"Server `{gid}` was already on the allowlist. "
                    f"Invite link if your friend still needs it: <{invite_url}>",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    f"Added server `{gid}` to the runtime allowlist. "
                    f"Invite the bot with: <{invite_url}>",
                    ephemeral=True,
                )

        @self.tree.command(
            name="laq_clear",
            description=(
                "Delete every LanceAQuack message from this server and "
                "reset its tracking state. Bot-owner only."
            ),
        )
        @app_commands.guild_only()
        async def laq_clear(interaction: discord.Interaction) -> None:
            if await _reject_non_owner(interaction):
                return
            guild = interaction.guild
            if guild is None:
                await interaction.response.send_message(
                    "This command must be used inside a server.",
                    ephemeral=True,
                )
                return

            await interaction.response.defer(ephemeral=True, thinking=True)

            bot_id = self.user.id if self.user else 0
            deleted = 0
            no_history: list[str] = []

            # Walk every text channel in the server. Bots can delete
            # their own messages without Manage Messages, so the only
            # permission we strictly need is Read Message History.
            for channel in list(guild.text_channels):
                try:
                    async for msg in channel.history(limit=500):
                        if msg.author.id != bot_id:
                            continue
                        try:
                            await msg.delete()
                            deleted += 1
                        except discord.NotFound:
                            pass
                        except discord.Forbidden:
                            log.debug(
                                "Forbidden deleting own msg %s in #%s",
                                msg.id, channel.name,
                            )
                            break
                        except discord.HTTPException as e:
                            log.debug(
                                "HTTP error deleting %s in #%s: %s",
                                msg.id, channel.name, e,
                            )
                except discord.Forbidden:
                    no_history.append(f"#{channel.name}")
                except Exception:  # noqa: BLE001
                    log.exception(
                        "Sweep of #%s failed", channel.name,
                    )

            # Reset tracking state for this guild and drop any
            # announcement records pointing at it.
            self._guilds_block().pop(str(guild.id), None)
            self._announcements()[:] = [
                r for r in self._announcements()
                if int(r.get("guild_id", 0)) != guild.id
            ]
            await self._save_state()

            parts = [f"deleted **{deleted}** bot message(s)"]
            parts.append(
                "tracking state reset — run `/ttr_setup` to start again"
            )
            if no_history:
                preview = ", ".join(no_history[:5])
                more = (
                    f" (+{len(no_history) - 5} more)"
                    if len(no_history) > 5 else ""
                )
                parts.append(
                    f"couldn't read history in: {preview}{more}"
                )
            log.info(
                "laq_clear in %s (id=%s): deleted=%d, skipped_channels=%d",
                guild.name, guild.id, deleted, len(no_history),
            )
            await interaction.followup.send(
                "Done — " + "; ".join(parts) + ".",
                ephemeral=True,
            )

        @self.tree.command(
            name="laq_guild_remove",
            description=(
                "Remove a Discord server ID from the allowlist and leave it. "
                "Bot-owner only."
            ),
        )
        @app_commands.describe(
            guild_id="The numeric Discord server (guild) ID to remove.",
        )
        async def laq_guild_remove(
            interaction: discord.Interaction, guild_id: str,
        ) -> None:
            if await _reject_non_owner(interaction):
                return
            try:
                gid = int(guild_id.strip())
            except (TypeError, ValueError):
                await interaction.response.send_message(
                    f"`{guild_id}` is not a valid numeric server ID.",
                    ephemeral=True,
                )
                return

            await interaction.response.defer(ephemeral=True, thinking=True)

            in_env = gid in self.config.guild_allowlist
            in_runtime = gid in self._runtime_allowlist()
            removed = await self._remove_runtime_allowlist(gid)

            # Leave the guild if we're currently a member.
            left = False
            guild = self.get_guild(gid)
            if guild is not None:
                try:
                    await guild.leave()
                    left = True
                except Exception as e:  # noqa: BLE001
                    log.warning("Failed to leave %s: %s", gid, e)

            parts = []
            if removed and in_runtime:
                parts.append("removed from the runtime allowlist")
            if in_env:
                parts.append(
                    f"**still in `GUILD_ALLOWLIST` env**: edit `.env` and "
                    f"restart the bot to remove `{gid}` permanently"
                )
            if left:
                parts.append(f"left the server")
            if not parts:
                parts.append(
                    f"server `{gid}` wasn't on the allowlist; nothing to do"
                )
            await interaction.followup.send(
                "Done — " + "; ".join(parts) + ".",
                ephemeral=True,
            )


def main() -> None:
    config = Config.load()
    if not config.guild_allowlist and not config.owner_ids:
        log.warning(
            "Both GUILD_ALLOWLIST and BOT_OWNER_IDS are empty — the bot "
            "cannot be invited to any server and has no admins. Edit "
            "your .env."
        )
    bot = TTRBot(config)
    bot.run(config.token, log_handler=None)


if __name__ == "__main__":
    main()
