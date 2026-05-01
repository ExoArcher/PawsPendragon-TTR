# db.py
"""Async SQLite persistence layer for Paws Pendragon TTR.

Replaces the five flat JSON files:
  state.json            -> guild_feeds, allowlist, announcements, maintenance_msgs tables
  welcomed_users.json   -> welcomed_users table
  banned_users.json     -> banned_users table
  maintenance_mode.json -> maintenance_mode table
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import aiosqlite

log = logging.getLogger("ttr-bot.db")
DB_PATH = Path(__file__).with_name("bot.db")

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS guild_feeds (
    guild_id    TEXT    NOT NULL,
    feed_key    TEXT    NOT NULL,
    channel_id  INTEGER NOT NULL DEFAULT 0,
    message_ids TEXT    NOT NULL DEFAULT '[]',
    PRIMARY KEY (guild_id, feed_key)
);
CREATE TABLE IF NOT EXISTS allowlist (
    guild_id    INTEGER PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS announcements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    message_id  INTEGER NOT NULL UNIQUE,
    expires_at  REAL    NOT NULL
);
CREATE TABLE IF NOT EXISTS maintenance_msgs (
    guild_id    TEXT    PRIMARY KEY,
    message_id  INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS welcomed_users (
    user_id     INTEGER PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS banned_users (
    user_id     TEXT    PRIMARY KEY,
    reason      TEXT,
    banned_at   TEXT,
    banned_by   TEXT,
    banned_by_id TEXT
);
CREATE TABLE IF NOT EXISTS maintenance_mode (
    guild_id    TEXT    NOT NULL,
    feed_key    TEXT    NOT NULL,
    message_id  INTEGER NOT NULL,
    PRIMARY KEY (guild_id, feed_key)
);
"""


async def init_db(path: Path = DB_PATH) -> None:
    """Create all tables if they don't exist. Safe to call on every startup."""
    async with aiosqlite.connect(path) as db:
        await db.executescript(_SCHEMA)
        await db.commit()
    log.info("[db] Schema ready at %s", path.name)


async def _is_fresh(path: Path = DB_PATH) -> bool:
    """True if the DB has no guild feed rows (i.e. first run after migration)."""
    async with aiosqlite.connect(path) as db:
        async with db.execute("SELECT COUNT(*) FROM guild_feeds") as cur:
            row = await cur.fetchone()
            return (row[0] if row else 0) == 0


# ── State (guilds, allowlist, announcements, maintenance_msgs) ─────────────────

async def load_state(path: Path = DB_PATH) -> dict[str, Any]:
    """Return the state dict in the same v2 format bot.py expects."""
    state: dict[str, Any] = {
        "_version": 2, "guilds": {}, "allowlist": [], "announcements": [],
    }
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT guild_id, feed_key, channel_id, message_ids FROM guild_feeds"
        ) as cur:
            async for gid, key, ch_id, raw_ids in cur:
                if key.startswith("suit_threads."):
                    faction = key[len("suit_threads."):]
                    state["guilds"].setdefault(gid, {}).setdefault("suit_threads", {})[faction] = {
                        "thread_id": ch_id,
                        "message_ids": json.loads(raw_ids),
                    }
                else:
                    state["guilds"].setdefault(gid, {})[key] = {
                        "channel_id": ch_id,
                        "message_ids": json.loads(raw_ids),
                    }
        async with db.execute("SELECT guild_id FROM allowlist") as cur:
            state["allowlist"] = [row[0] async for row in cur]
        async with db.execute(
            "SELECT guild_id, channel_id, message_id, expires_at FROM announcements"
        ) as cur:
            state["announcements"] = [
                {
                    "guild_id":   row[0], "channel_id": row[1],
                    "message_id": row[2], "expires_at": row[3],
                }
                async for row in cur
            ]
        async with db.execute("SELECT guild_id, message_id FROM maintenance_msgs") as cur:
            mm = {row[0]: row[1] async for row in cur}
        if mm:
            state["maintenance_msgs"] = mm
    return state


async def save_state(state: dict[str, Any], path: Path = DB_PATH) -> None:
    """Persist the in-memory state dict to SQLite atomically."""
    async with aiosqlite.connect(path) as db:
        # guild_feeds: upsert present guilds, delete departed ones
        current_gids = set(state.get("guilds", {}).keys())
        async with db.execute("SELECT DISTINCT guild_id FROM guild_feeds") as cur:
            db_gids = {row[0] async for row in cur}
        for gid in db_gids - current_gids:
            await db.execute("DELETE FROM guild_feeds WHERE guild_id = ?", (gid,))
        for gid, feeds in state.get("guilds", {}).items():
            for key, entry in feeds.items():
                if not isinstance(entry, dict):
                    continue
                if key == "suit_threads":
                    for faction, fdata in entry.items():
                        if not isinstance(fdata, dict):
                            continue
                        await db.execute(
                            "INSERT INTO guild_feeds (guild_id, feed_key, channel_id, message_ids) "
                            "VALUES (?, ?, ?, ?) "
                            "ON CONFLICT(guild_id, feed_key) DO UPDATE SET "
                            "channel_id=excluded.channel_id, message_ids=excluded.message_ids",
                            (gid, f"suit_threads.{faction}",
                             int(fdata.get("thread_id", 0)),
                             json.dumps(fdata.get("message_ids") or [])),
                        )
                    continue
                await db.execute(
                    "INSERT INTO guild_feeds (guild_id, feed_key, channel_id, message_ids) "
                    "VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(guild_id, feed_key) DO UPDATE SET "
                    "channel_id=excluded.channel_id, message_ids=excluded.message_ids",
                    (
                        gid, key,
                        int(entry.get("channel_id", 0)),
                        json.dumps(entry.get("message_ids") or []),
                    ),
                )
        # allowlist: full replace
        await db.execute("DELETE FROM allowlist")
        for gid in state.get("allowlist", []):
            await db.execute(
                "INSERT OR IGNORE INTO allowlist (guild_id) VALUES (?)", (int(gid),)
            )
        # announcements: full replace
        await db.execute("DELETE FROM announcements")
        for rec in state.get("announcements", []):
            await db.execute(
                "INSERT OR IGNORE INTO announcements "
                "(guild_id, channel_id, message_id, expires_at) VALUES (?, ?, ?, ?)",
                (
                    int(rec["guild_id"]), int(rec["channel_id"]),
                    int(rec["message_id"]), float(rec["expires_at"]),
                ),
            )
        # maintenance_msgs: full replace
        await db.execute("DELETE FROM maintenance_msgs")
        for gid, mid in state.get("maintenance_msgs", {}).items():
            await db.execute(
                "INSERT INTO maintenance_msgs (guild_id, message_id) VALUES (?, ?)",
                (str(gid), int(mid)),
            )
        await db.commit()


# ── Welcomed users ─────────────────────────────────────────────────────────────

async def load_welcomed(path: Path = DB_PATH) -> set[int]:
    async with aiosqlite.connect(path) as db:
        async with db.execute("SELECT user_id FROM welcomed_users") as cur:
            return {row[0] async for row in cur}


async def add_welcomed(user_id: int, path: Path = DB_PATH) -> None:
    async with aiosqlite.connect(path) as db:
        await db.execute(
            "INSERT OR IGNORE INTO welcomed_users (user_id) VALUES (?)", (user_id,)
        )
        await db.commit()


# ── Banned users ───────────────────────────────────────────────────────────────

async def get_ban(user_id: int, path: Path = DB_PATH) -> dict | None:
    """Return the ban record for *user_id*, or None if not banned."""
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT reason, banned_at, banned_by, banned_by_id "
            "FROM banned_users WHERE user_id = ?",
            (str(user_id),),
        ) as cur:
            row = await cur.fetchone()
    if row is None:
        return None
    return {
        "reason": row[0], "banned_at": row[1],
        "banned_by": row[2], "banned_by_id": row[3],
    }


async def save_banned(banned: dict[str, dict], path: Path = DB_PATH) -> None:
    async with aiosqlite.connect(path) as db:
        await db.execute("DELETE FROM banned_users")
        for uid, rec in banned.items():
            await db.execute(
                "INSERT INTO banned_users "
                "(user_id, reason, banned_at, banned_by, banned_by_id) VALUES (?, ?, ?, ?, ?)",
                (
                    str(uid),
                    rec.get("reason"), rec.get("banned_at"),
                    rec.get("banned_by"), rec.get("banned_by_id"),
                ),
            )
        await db.commit()


# ── Maintenance mode ───────────────────────────────────────────────────────────

async def load_maint_mode(path: Path = DB_PATH) -> dict:
    """{str(guild_id): {feed_key: message_id}} or empty dict."""
    async with aiosqlite.connect(path) as db:
        async with db.execute(
            "SELECT guild_id, feed_key, message_id FROM maintenance_mode"
        ) as cur:
            result: dict[str, dict] = {}
            async for gid, fk, mid in cur:
                result.setdefault(gid, {})[fk] = mid
    return result


async def save_maint_mode(data: dict, path: Path = DB_PATH) -> None:
    async with aiosqlite.connect(path) as db:
        await db.execute("DELETE FROM maintenance_mode")
        for gid, channels in data.items():
            for fk, mid in channels.items():
                await db.execute(
                    "INSERT INTO maintenance_mode (guild_id, feed_key, message_id) VALUES (?, ?, ?)",
                    (str(gid), str(fk), int(mid)),
                )
        await db.commit()


# ── One-time JSON → SQLite migration ──────────────────────────────────────────

async def migrate_from_json(bot_dir: Path, path: Path = DB_PATH) -> None:
    """
    Import legacy JSON files into SQLite on first run.
    Does nothing if the DB already contains guild feed data.
    Handles state.json v1 and v2 formats.
    """
    if not await _is_fresh(path):
        return

    _STATE_VER = 2
    state: dict[str, Any] = {
        "_version": _STATE_VER, "guilds": {}, "allowlist": [], "announcements": [],
    }

    state_file = bot_dir / "state.json"
    if state_file.exists():
        try:
            raw = json.loads(state_file.read_text())
            if isinstance(raw, dict):
                ver = raw.get("_version")
                if ver == _STATE_VER:
                    state = raw
                    state.setdefault("guilds", {})
                    state.setdefault("allowlist", [])
                    state.setdefault("announcements", [])
                elif all(isinstance(v, dict) and not k.startswith("_") for k, v in raw.items()):
                    state["guilds"] = raw  # v1 migration
            log.info("[db] Migrating state.json (%d guild(s)) → SQLite", len(state.get("guilds", {})))
        except Exception as exc:
            log.warning("[db] Could not read state.json for migration: %s", exc)

    welcomed: list[int] = []
    welcomed_file = bot_dir / "welcomed_users.json"
    if welcomed_file.exists():
        try:
            welcomed = json.loads(welcomed_file.read_text())
            log.info("[db] Migrating welcomed_users.json (%d user(s)) → SQLite", len(welcomed))
        except Exception as exc:
            log.warning("[db] Could not read welcomed_users.json: %s", exc)

    banned: dict[str, dict] = {}
    banned_file = bot_dir / "banned_users.json"
    if banned_file.exists():
        try:
            banned = json.loads(banned_file.read_text())
            log.info("[db] Migrating banned_users.json (%d ban(s)) → SQLite", len(banned))
        except Exception as exc:
            log.warning("[db] Could not read banned_users.json: %s", exc)

    maint: dict[str, dict] = {}
    maint_file = bot_dir / "maintenance_mode.json"
    if maint_file.exists():
        try:
            data = json.loads(maint_file.read_text())
            if isinstance(data, dict) and data:
                maint = data
            log.info("[db] Migrating maintenance_mode.json → SQLite")
        except Exception as exc:
            log.warning("[db] Could not read maintenance_mode.json: %s", exc)

    await save_state(state, path)

    async with aiosqlite.connect(path) as db:
        for uid in welcomed:
            await db.execute(
                "INSERT OR IGNORE INTO welcomed_users (user_id) VALUES (?)", (int(uid),)
            )
        for uid, rec in banned.items():
            await db.execute(
                "INSERT OR IGNORE INTO banned_users "
                "(user_id, reason, banned_at, banned_by, banned_by_id) VALUES (?, ?, ?, ?, ?)",
                (
                    str(uid), rec.get("reason"), rec.get("banned_at"),
                    rec.get("banned_by"), rec.get("banned_by_id"),
                ),
            )
        for gid, channels in maint.items():
            for fk, mid in channels.items():
                await db.execute(
                    "INSERT OR IGNORE INTO maintenance_mode "
                    "(guild_id, feed_key, message_id) VALUES (?, ?, ?)",
                    (str(gid), str(fk), int(mid)),
                )
        await db.commit()

    log.info("[db] JSON → SQLite migration complete.")
