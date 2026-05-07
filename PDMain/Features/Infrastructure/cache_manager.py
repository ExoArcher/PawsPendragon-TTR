# cache_manager.py
"""In-memory cache management for console update system Phase 1.

Maintains module-level sets for quick O(1) guild/user lookups:
- GUILD_ALLOWLIST: Set of allowed guild IDs
- Banned_user_ids: Set of banned user IDs
- BlacklistedServerid: Set of blacklisted server IDs

Caches are loaded from database on startup and periodically refreshed.
"""
from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path

from Features.Core.db import db
from Features.Core.db.db_cache_coherence import atomic_db_cache_update

log = logging.getLogger("ttr-bot.cache-manager")

# Module-level caches (populated by load_caches_from_db and refresh functions)
GUILD_ALLOWLIST: set[int] = set()
Banned_user_ids: set[int] = set()
BlacklistedServerid: set[int] = set()

# Track last refresh times to enforce intervals
_last_allowlist_refresh: float = 0.0
_last_banned_quarantine_refresh: float = 0.0

# Refresh intervals (in seconds)
ALLOWLIST_REFRESH_INTERVAL = 12 * 60 * 60  # 12 hours
BANNED_QUARANTINE_REFRESH_INTERVAL = 6 * 60 * 60  # 6 hours


async def load_caches_from_db(db_path: Path | None = None) -> None:
    """Load all caches from database on startup."""
    global _last_allowlist_refresh, _last_banned_quarantine_refresh

    log.info("[cache-manager] Loading caches from database...")

    try:
        # Load guild allowlist
        state = await db.load_state(db_path or db.DB_PATH)
        GUILD_ALLOWLIST.clear()
        for gid in state.get("allowlist", []):
            try:
                GUILD_ALLOWLIST.add(int(gid))
            except (ValueError, TypeError):
                pass

        # Load banned users
        banned_dict = await db.load_all_banned(db_path or db.DB_PATH)
        Banned_user_ids.clear()
        for uid_str in banned_dict.keys():
            try:
                Banned_user_ids.add(int(uid_str))
            except (ValueError, TypeError):
                pass

        # Load blacklisted servers
        blacklisted = await db.get_all_blacklisted(db_path or db.DB_PATH)
        BlacklistedServerid.clear()
        BlacklistedServerid.update(blacklisted)

        # Reset refresh timers
        now = time.time()
        _last_allowlist_refresh = now
        _last_banned_quarantine_refresh = now

        log.info(
            "[cache-manager] Caches loaded: "
            "allowlist=%d, banned=%d, blacklisted=%d",
            len(GUILD_ALLOWLIST), len(Banned_user_ids), len(BlacklistedServerid),
        )
    except Exception as e:
        log.exception("[cache-manager] Error loading caches from database: %s", e)
        raise


async def refresh_guild_allowlist(db_path: Path | None = None) -> None:
    """Refresh the guild allowlist cache (12-hour interval)."""
    global _last_allowlist_refresh

    now = time.time()
    if now - _last_allowlist_refresh < ALLOWLIST_REFRESH_INTERVAL:
        log.debug("[cache-manager] Skipping allowlist refresh (interval not met)")
        return

    try:
        log.info("[cache-manager] Refreshing guild allowlist cache...")
        state = await db.load_state(db_path or db.DB_PATH)
        GUILD_ALLOWLIST.clear()
        for gid in state.get("allowlist", []):
            try:
                GUILD_ALLOWLIST.add(int(gid))
            except (ValueError, TypeError):
                pass

        _last_allowlist_refresh = now
        log.info("[cache-manager] Guild allowlist refreshed: %d guilds", len(GUILD_ALLOWLIST))
    except Exception as e:
        log.exception("[cache-manager] Error refreshing allowlist: %s", e)


async def refresh_banned_and_quarantine(db_path: Path | None = None) -> None:
    """Refresh banned users and blacklist caches (6-hour interval)."""
    global _last_banned_quarantine_refresh

    now = time.time()
    if now - _last_banned_quarantine_refresh < BANNED_QUARANTINE_REFRESH_INTERVAL:
        log.debug("[cache-manager] Skipping banned/blacklist refresh (interval not met)")
        return

    try:
        log.info("[cache-manager] Refreshing banned users and blacklist caches...")

        # Refresh banned users
        banned_dict = await db.load_all_banned(db_path or db.DB_PATH)
        banned_ids = [int(uid_str) for uid_str in banned_dict.keys() if uid_str.isdigit()]
        success = await atomic_db_cache_update(
            db_path or db.DB_PATH,
            operation="delete",
            table="banned_users",
            where_clause={},
            cache_set=Banned_user_ids,
            cache_keys=banned_ids,
        )
        if not success:
            log.error("[cache] Failed to refresh banned_user_ids cache")
        else:
            log.info("[cache] Refreshed %d banned users", len(banned_ids))

        # Refresh blacklisted servers
        blacklisted = await db.get_all_blacklisted(db_path or db.DB_PATH)
        success = await atomic_db_cache_update(
            db_path or db.DB_PATH,
            operation="delete",
            table="blacklist",
            where_clause={},
            cache_set=BlacklistedServerid,
            cache_keys=list(blacklisted),
        )
        if not success:
            log.error("[cache] Failed to refresh blacklist cache")
        else:
            log.info("[cache] Refreshed %d blacklisted servers", len(blacklisted))

        _last_banned_quarantine_refresh = now
        log.info(
            "[cache-manager] Banned/blacklist caches refreshed: "
            "banned=%d, blacklisted=%d",
            len(Banned_user_ids), len(BlacklistedServerid),
        )
    except Exception as e:
        log.exception("[cache-manager] Error refreshing banned/blacklist caches: %s", e)
