# periodic_checks.py
"""Periodic check scheduler for console update system Phase 1-4.

Manages two scheduled tasks:
1. Guild allowlist sync (12-hour interval)
2. Banned users, quarantine, and blacklist sync (6-hour interval)
   - Phase 4: Detects quarantine candidates, checks unquarantine candidates,
     and processes blacklist removal timers (7-day auto-removal)

Both tasks run once on bot startup, then repeat on their configured intervals.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from Features.Infrastructure import cache_manager
from Features.Infrastructure.quarantine_checks import detect_quarantine_candidates, trigger_quarantine
from Features.Infrastructure.unquarantine_checks import check_unquarantine_candidates, trigger_unquarantine
from Features.Infrastructure.blacklist_removal import check_blacklist_removal_timers
from Features.Core.db import db

log = logging.getLogger("ttr-bot.periodic-checks")

_allowlist_check_task: asyncio.Task | None = None
_banned_quarantine_check_task: asyncio.Task | None = None


async def _periodic_allowlist_check() -> None:
    """Run guild allowlist sync every 12 hours."""
    while True:
        try:
            await cache_manager.refresh_guild_allowlist()
            now = datetime.now(timezone.utc).isoformat()
            print(f"[Periodic Checks] Guild allowlist sync completed at {now}", flush=True)
        except Exception as e:
            log.exception("[periodic-checks] Allowlist check failed: %s", e)

        # Sleep for 12 hours before next check
        await asyncio.sleep(cache_manager.ALLOWLIST_REFRESH_INTERVAL)


async def _periodic_banned_quarantine_check(bot) -> None:
    """Run banned users/quarantine/blacklist sync every 6 hours (Phase 4 support)."""
    while True:
        try:
            await cache_manager.refresh_banned_and_quarantine()
            now = datetime.now(timezone.utc).isoformat()
            print(f"[Periodic Checks] Banned/quarantine/blacklist sync completed at {now}", flush=True)

            # Phase 4: Run quarantine checks
            log.info("[periodic-checks] Running Phase 4 quarantine checks...")
            quarantined = 0
            unquarantined = 0
            removed = 0

            try:
                # 1. Detect and trigger new quarantines
                candidates = await detect_quarantine_candidates(bot)
                for guild_id, owner_id, banned_user_ids in candidates:
                    try:
                        await trigger_quarantine(bot, guild_id, owner_id, banned_user_ids)
                        quarantined += 1
                    except Exception as exc:
                        log.error(
                            "[periodic-checks] Failed to quarantine guild %s: %s",
                            guild_id, exc
                        )

                # 2. Check for unquarantine candidates
                unquarantine_candidates = await check_unquarantine_candidates(bot)
                for guild_id in unquarantine_candidates:
                    try:
                        # Get owner_id from database
                        quarantined_guilds = await db.load_quarantined_guilds()
                        qg = quarantined_guilds.get(str(guild_id))
                        if qg:
                            owner_id = int(qg.get("owner_id", 0)) if qg.get("owner_id") else 0
                            await trigger_unquarantine(bot, guild_id, owner_id)
                            unquarantined += 1
                    except Exception as exc:
                        log.error(
                            "[periodic-checks] Failed to unquarantine guild %s: %s",
                            guild_id, exc
                        )

                # 3. Check for blacklist removal timers
                try:
                    removed = await check_blacklist_removal_timers(bot)
                except Exception as exc:
                    log.error("[periodic-checks] Failed during blacklist removal check: %s", exc)

                log.info(
                    "[periodic-checks] Phase 4 checks complete: "
                    "%d quarantined, %d unquarantined, %d removed",
                    quarantined, unquarantined, removed
                )

            except Exception as exc:
                log.error("[periodic-checks] Error during Phase 4 checks: %s", exc)

        except Exception as e:
            log.exception("[periodic-checks] Banned/quarantine check failed: %s", e)

        # Sleep for 6 hours before next check
        await asyncio.sleep(cache_manager.BANNED_QUARANTINE_REFRESH_INTERVAL)


async def start_periodic_checks(bot=None) -> None:
    """Start both periodic check tasks. Safe to call multiple times.

    Args:
        bot: TTRBot instance (required for Phase 4 quarantine checks).
    """
    global _allowlist_check_task, _banned_quarantine_check_task

    if _allowlist_check_task is None or _allowlist_check_task.done():
        log.info("[periodic-checks] Starting guild allowlist periodic check task...")
        # Run once immediately on startup
        await cache_manager.refresh_guild_allowlist()
        _allowlist_check_task = asyncio.create_task(
            _periodic_allowlist_check(),
            name="periodic-allowlist-check",
        )

    if _banned_quarantine_check_task is None or _banned_quarantine_check_task.done():
        log.info("[periodic-checks] Starting banned/quarantine periodic check task...")
        # Run once immediately on startup
        await cache_manager.refresh_banned_and_quarantine()
        _banned_quarantine_check_task = asyncio.create_task(
            _periodic_banned_quarantine_check(bot),
            name="periodic-banned-quarantine-check",
        )


async def stop_periodic_checks() -> None:
    """Stop both periodic check tasks gracefully."""
    global _allowlist_check_task, _banned_quarantine_check_task

    if _allowlist_check_task and not _allowlist_check_task.done():
        log.info("[periodic-checks] Stopping guild allowlist check task...")
        _allowlist_check_task.cancel()
        try:
            await _allowlist_check_task
        except asyncio.CancelledError:
            pass

    if _banned_quarantine_check_task and not _banned_quarantine_check_task.done():
        log.info("[periodic-checks] Stopping banned/quarantine check task...")
        _banned_quarantine_check_task.cancel()
        try:
            await _banned_quarantine_check_task
        except asyncio.CancelledError:
            pass
