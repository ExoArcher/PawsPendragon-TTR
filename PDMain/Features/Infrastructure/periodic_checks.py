# periodic_checks.py
"""Periodic check scheduler for console update system Phase 1.

Manages two scheduled tasks:
1. Guild allowlist sync (12-hour interval)
2. Banned users and blacklist sync (6-hour interval)
   - Processes blacklist removal timers (7-day auto-removal)

Both tasks run once on bot startup, then repeat on their configured intervals.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from Features.Infrastructure import cache_manager
from Features.Infrastructure.blacklist_removal import check_blacklist_removal_timers

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
    """Run banned users and blacklist sync every 6 hours."""
    await bot.wait_until_ready()

    while True:
        try:
            await cache_manager.refresh_banned_and_quarantine()
            now = datetime.now(timezone.utc).isoformat()
            print(f"[Periodic Checks] Banned/blacklist sync completed at {now}", flush=True)

            # Check blacklist removal timers
            try:
                removed = await check_blacklist_removal_timers(bot)
                if removed:
                    log.info("[periodic-checks] Removed %d guild(s) from blacklist", removed)
            except Exception as exc:
                log.error("[periodic-checks] Failed during blacklist removal check: %s", exc)

        except Exception as e:
            log.exception("[periodic-checks] Banned check failed: %s", e)

        await asyncio.sleep(cache_manager.BANNED_QUARANTINE_REFRESH_INTERVAL)


async def start_periodic_checks(bot=None) -> None:
    """Start both periodic check tasks. Safe to call multiple times.

    Args:
        bot: TTRBot instance (required for blacklist removal checks).
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
        log.info("[periodic-checks] Starting banned/blacklist periodic check task...")
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
        log.info("[periodic-checks] Stopping banned/blacklist check task...")
        _banned_quarantine_check_task.cancel()
        try:
            await _banned_quarantine_check_task
        except asyncio.CancelledError:
            pass
