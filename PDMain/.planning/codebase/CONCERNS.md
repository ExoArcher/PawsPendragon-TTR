# Codebase Concerns

**Analysis Date:** 2026-05-07

## Tech Debt

**Refresh interval mismatch between documentation and code:**
- Issue: README/documentation mention 90-second refresh interval; actual code default is 45 seconds for information feed and daily UTC 00:00 for doodles
- Files: `Features/Core/config/constants.py` (INFORMATION_FEED_REFRESH_SECONDS=45), `Features/Infrastructure/live_feeds/live_feeds.py` (UTC midnight check), various BRIEFING.md files
- Impact: Operator confusion when setting `REFRESH_INTERVAL` env var; discrepancy between stated and actual behavior. Documentation is stale.
- Fix approach: Audit and reconcile all README references to match code constants. Update DEPLOY.md section 7 to clarify actual 45s interval. Add comments explaining UTC doodle boundary logic.

**Hardcoded repository URL in auto-update logic:**
- Issue: GitHub URL is hardcoded in `bot.py` as `https://github.com/ExoArcher/PawsPendragon-TTR`
- Files: `bot.py` line 60 (_GIT_REPO constant)
- Impact: Bot cannot be forked or re-hosted without code modification. Blocks community forks or internal mirrors.
- Fix approach: Move repo URL to `Config` dataclass and load from `.env`, with sensible default. Allow operators to point to their own forks.

**Hardcoded admin user ID in guild lifecycle:**
- Issue: ExoArcher's Discord user ID referenced in rejection DM
- Files: `Features/Infrastructure/guild_lifecycle/BRIEFING.md` line 112 (noted as constraint); probably `guild_lifecycle.py`
- Impact: All DMs sent to non-allowlisted guilds mention ExoArcher by hardcoded ID; blocks multi-tenant use cases without code changes.
- Fix approach: Extract admin contact info to Config as `ADMIN_CONTACT_USER_ID` or `SUPPORT_CONTACT` (name or URL), inject via .env.

**Formatter/Config feed key divergence check warning (not enforced):**
- Issue: In `pd_refresh.py` lines 107–117, a startup assertion compares FORMATTERS.keys() to config.feeds().keys() and logs a warning if they diverge, but does NOT fail startup
- Files: `Features/Admin/pd_refresh/pd_refresh.py` lines 107–117
- Impact: If a formatter is missing (e.g., new feed added to config but no formatter defined), the bot silently skips updating that feed with no alert to admins. Silent degradation.
- Fix approach: Raise exception at startup or on first /pd-refresh if divergence detected. Require explicit config/formatter alignment.

**Database connection pooling with manual cleanup:**
- Issue: Connection pool in `db.py` lines 22–24, 96–110 uses manual asyncio.Queue-based pool with no automatic timeout/reaping
- Files: `Features/Core/db/db.py` lines 93–120
- Impact: Long-lived connections may accumulate, stale connections not recycled. Potential connection leaks under rapid on/off cycles or after prolonged inactivity.
- Fix approach: Add idle connection timeout; reap connections after N seconds of inactivity. Consider migrating to aiosqlite.Pool (if available in future versions).

**Refresh lock not held during fetch; state coherence risk:**
- Issue: In `live_feeds.py` _refresh_once() lines 146–148, TTR API fetch happens OUTSIDE _refresh_lock. Lock is only held for final state save.
- Files: `Features/Infrastructure/live_feeds/live_feeds.py` lines 125–180
- Impact: A user command that modifies state (e.g., /pd-setup adds message ID) can race with the feed update. Two concurrent writes may cause lost updates or inconsistent embed state.
- Fix approach: Acquire lock BEFORE fetch, hold it through all writes. Or use optimistic locking (version numbers) to detect and recover from races.

**Unvalidated API response structure in doodle updates:**
- Issue: `_validate_api_response()` in `pd_refresh.py` checks only that dict has required keys and not all None. No schema validation of nested structures.
- Files: `Features/Admin/pd_refresh/pd_refresh.py` lines 72–87
- Impact: Malformed API response (e.g., doodle missing `traits` key) crashes formatter at embed-build time, not during validation. Formatter error surfaces after feed cycle completes but before state persists.
- Fix approach: Deep validate API schema (each district, each doodle, each field office). Build separate `validate_*_schema()` functions per endpoint.

**No circuit breaker on TTR API failures:**
- Issue: In `ttr_api.py` _get() lines 46–59, retries are hardcoded to 3 with exponential backoff, but no circuit breaker to stop hammering failed endpoint
- Files: `Features/Core/ttr_api/ttr_api.py` lines 46–59
- Impact: If TTR API is down for hours, bot continues attempting fetches every 45 seconds, wasting bandwidth. No adaptive backoff or fallback to cached data.
- Fix approach: Add circuit breaker (track failure count/rate, stop retrying after threshold, re-test periodically). Or add in-process cache of last successful fetch, reuse stale data if current fetch fails.

**Message ID list stored as JSON string in SQLite:**
- Issue: `guild_feeds.message_ids` stored as TEXT (JSON array), parsed/serialized on every state load/save
- Files: `Features/Core/db/db.py` schema (line 33), `db.py` load/save logic
- Impact: Performance overhead on each refresh cycle (parse/serialize JSON for every guild feed). Scales poorly as guild count or message count grows.
- Fix approach: Either normalize to separate `feed_messages` table with FK, or serialize to binary BLOB. Benchmark before migrating.

**Inline audit log but no retention enforcement:**
- Issue: `audit_log` table defined in schema (db.py lines 73–80) but never purged. `AUDIT_LOG_RETENTION_DAYS = 90` constant exists but not used.
- Files: `Features/Core/db/db.py` lines 73–80, `constants.py` line 36
- Impact: Audit log grows unbounded; over years, can bloat database. No cleanup task scheduled.
- Fix approach: Add periodic task (daily) to delete audit_log entries older than `AUDIT_LOG_RETENTION_DAYS`. Run at off-peak time.

**Console command rate limiting shared state:**
- Issue: `_announce_rate_limiter` in `console_commands.py` (lines 68–71) is a module-level RateLimit instance. No per-user or per-session isolation.
- Files: `Features/ServerManagement/console_commands/console_commands.py` lines 68–71, 43–56
- Impact: One operator can exhaust global announce quota, blocking other operators. No differentiation by role or privilege.
- Fix approach: Rate limit per operator (track by console session ID or operator user ID), or increase quota for trusted operators.

**No timeout on long-running refresh cycles:**
- Issue: _refresh_once() has no outer timeout. If a single guild's edit hangs (Discord rate limit, network issue), entire refresh cycle blocks
- Files: `Features/Infrastructure/live_feeds/live_feeds.py` lines 125–200 (estimated)
- Impact: One stuck guild blocks updates to all other guilds for 45 seconds. Cascades if multiple edits fail.
- Fix approach: Wrap entire _refresh_once in asyncio.wait_for(timeout=X). Per-guild edits already have PER_FEED_UPDATE_TIMEOUT_SECONDS; add outer constraint.

**Blacklist removal checks periodic but not on-demand:**
- Issue: Blacklist removal timers checked every 6 hours in `periodic_checks.py` (line 52)
- Files: `Features/Infrastructure/blacklist_removal.py`, `Features/Infrastructure/periodic_checks.py` lines 40–62
- Impact: Blacklisted guilds remain inactive for up to 6 hours after their 7-day timer expires. No immediate reinstatement option for manual override.
- Fix approach: Add on-demand console command `unquarantine <guild_id>` to immediately remove from blacklist and resume feeds.

**Guild lifecycle on_guild_join event may fail silently:**
- Issue: No error handling visible in BRIEFING; if DM send fails, no fallback. If allowlist check fails, guild still joins.
- Files: `Features/Infrastructure/guild_lifecycle/guild_lifecycle.py` (not read; inferred from BRIEFING)
- Impact: Non-allowlisted guild joins, bot fails to leave (e.g., due to missing permissions). Guild accumulates in cache but remains inactive.
- Fix approach: Wrap lifecycle in try/except; log failure reason. Force leave even if DM fails (separate the two operations).

**TTR API 503 errors not distinguished from other failures:**
- Issue: In `ttr_api.py` _get(), all aiohttp.ClientError exceptions are retried equally. No special handling for 503 (maintenance).
- Files: `Features/Core/ttr_api/ttr_api.py` lines 46–59
- Impact: During TTR API maintenance, bot wastes retries on guaranteed failures. Should back off more aggressively for 503.
- Fix approach: Check response.status before retrying. For 503, use longer delay (e.g., 30s) or circuit breaker. For 4xx (client error), don't retry.

## Known Bugs

**Cache coherence race in banned_users refresh:**
- Symptoms: After ban/unban command, cache may be stale for up to 6 hours until next periodic refresh
- Files: `Features/Infrastructure/cache_manager.py` lines 82–105 (allowlist refresh every 12h), lines 107–150 (banned/quarantine every 6h)
- Trigger: User runs console `ban <id>` command, then immediately invokes slash command. Cached Banned_user_ids not updated until next 6-hour window.
- Workaround: Manual `quarrefresh` console command triggers immediate cache reload. Or wait up to 6 hours.
- Fix: On ban/unban, immediately update both DB and in-memory cache set. Don't rely on periodic refresh for correctness.

**Doodle refresh at UTC midnight can skip if bot restarts at boundary:**
- Symptoms: Doodles not updated if bot restarts between 23:59:59 and 00:00:01 UTC
- Files: `Features/Infrastructure/live_feeds/live_feeds.py` lines 142–144 (today_utc check)
- Trigger: Bot restart or /pdrefresh exactly at UTC midnight when _last_doodle_refresh_date is cached in memory
- Workaround: Manually run /pd-refresh to force doodle update
- Fix: Persist _last_doodle_refresh_date to database (or .env) so it survives restarts. Currently in-memory only.

**Message sweep may delete pinned messages if state is out of sync:**
- Symptoms: Feed messages marked as stale and deleted even though bot still manages them
- Files: `Features/Infrastructure/message_sweep/message_sweep.py` (logic inferred; not fully read)
- Trigger: Database corruption or state.json not flushed before restart. Message IDs in DB don't match actual Discord channels.
- Workaround: Run `/pd-teardown` then `/pd-setup` to recreate channels and sync state
- Fix: Before deleting, verify message ID exists in current guild state AND in Discord channel. Add extra confirmation check.

## Security Considerations

**DISCORD_TOKEN not masked in logs:**
- Risk: If bot logs the raw token anywhere (e.g., in startup debug logs or exception tracebacks), token is exposed
- Files: Check `bot.py` startup, all logger.debug/info calls with config values
- Current mitigation: Likely none visible. Config.load() probably doesn't mask token in logs.
- Recommendations: Add `__repr__` override to Config to mask sensitive fields. Audit all log calls for token leakage. Use structured logging (json) to prevent accidental string interpolation.

**No rate-limit enforcement on slash commands:**
- Risk: User can spam `/ttrinfo`, `/doodleinfo` to DoS bot or Discord API
- Files: All slash command handlers in `bot.py`
- Current mitigation: Discord.py has built-in command cooldowns, but none are set in the code (checked pd_refresh.py; others not audited)
- Recommendations: Add @app_commands.cooldown(rate=1, per=5.0) (1 use per 5 seconds) to all public commands. Log repeated violators.

**Ban/unban console commands accept only user ID, no validation:**
- Risk: Operator can ban arbitrary IDs without verification. If typo, user cannot undo without console access.
- Files: `Features/ServerManagement/console_commands/console_commands.py` (ban/unban handler)
- Current mitigation: Requires console access (not Discord slash command). Mitigates some risk.
- Recommendations: Add confirmation prompt. Log ban/unban with operator ID and timestamp. Add audit review command.

**Quarantine state stored in memory AND database; no sync on code changes:**
- Risk: Quarantine set in memory can diverge from database if operator edits DB directly or if periodic refresh fails
- Files: `Features/Infrastructure/cache_manager.py` (in-memory QuarantinedServerid set), database blacklist table
- Current mitigation: Periodic refresh every 6 hours. But still a 6-hour window for divergence.
- Recommendations: Add watch on blacklist table (if supported by sqlite WAL). Or sync before every guild operation, not just periodically.

**User DMs sent without rate limiting:**
- Risk: Bot can be forced to spam DMs to a user by invoking a command repeatedly
- Files: `Features/Infrastructure/user_system/user_system.py` (send_welcome_dm, check_ban)
- Current mitigation: DM failures caught and logged; no DM rate limit. Discord may soft-fail after threshold.
- Recommendations: Add per-user DM cooldown (track last DM time, skip if within N seconds). Or batch welcome DMs and send once per session.

## Performance Bottlenecks

**SQLite connection pool with fixed size may exhausted under high concurrency:**
- Problem: Pool size hardcoded to 5 connections. If 6+ DB operations queue, waits for connection release.
- Files: `Features/Core/db/db.py` lines 23, 104–110
- Cause: Default pool size too small for bots with 20+ guilds. Multiple refresh operations + console commands can contend.
- Improvement path: Make pool size configurable (env var). Measure actual peak concurrency. Consider async-context-manager queue draining to detect stalls.

**Message ID JSON parsing on every state load:**
- Problem: Every call to load_state() deserializes message_ids from JSON. Every save() re-serializes.
- Files: `Features/Core/db/db.py` (state dict building)
- Cause: No caching between load and save. High-frequency operations (refresh loop every 45s) pay parsing cost repeatedly.
- Improvement path: Cache parsed state in memory (e.g., `_cached_state` dict), invalidate on save. Or normalize to separate table (see Tech Debt above).

**Doodle embedding computation not cached:**
- Problem: Doodle formatter re-computes embed for every guild refresh (even if data unchanged)
- Files: `Features/Core/formatters/formatters.py` (not read; inferred from behavior)
- Cause: Embeds regenerated each cycle; no content-addressable cache (e.g., hash of doodle JSON → rendered embed)
- Improvement path: Add embed cache with TTL. On refresh, hash incoming doodle JSON; reuse cached embed if hash matches.

**No pagination for doodle list (all doodles in single embed):**
- Problem: If TTR adds more doodles, single embed may exceed Discord's 6000-character limit
- Files: `Features/Core/formatters/formatters.py` (doodle formatter)
- Cause: Assume doodle count < 50. No splitting logic.
- Improvement path: Add pagination (split into multiple embeds). Or switch to file upload (CSV/JSON) for doodle list.

**Per-guild edit operations sequential despite parallel fetch:**
- Problem: Fetch all 4 endpoints in parallel (good), then edit guilds sequentially with 3-second delays
- Files: `Features/Infrastructure/live_feeds/live_feeds.py` lines 190–210 (estimated; not fully read)
- Cause: Rate limiting to 1 edit per 3 seconds per guild. With 20 guilds, ~60 seconds to edit all.
- Improvement path: Batch edits by channel (if multiple feeds in same channel). Use asyncio semaphore to allow 2–3 concurrent edits. Still respect Discord limits.

## Fragile Areas

**Database schema migration logic (guild_id TEXT → INTEGER):**
- Files: `Features/Core/db/db.py` (referenced at line 118, not read)
- Why fragile: Type migration complex. If migration code fails mid-run, state may have mixed types. No rollback.
- Safe modification: Add migration tests covering partial runs. Log pre/post schema state. Add --revert-migration flag for debugging.
- Test coverage: Likely zero; migration is a one-shot operation. Hard to test without duplicating actual DB.

**Message sweep relies on guild cache accuracy:**
- Files: `Features/Infrastructure/message_sweep/message_sweep.py` lines 62–98 (not fully read)
- Why fragile: If state.json is stale or corrupt, sweep may delete wrong messages or miss stale ones.
- Safe modification: Always verify channel exists before deleting. Check message age (if available) before purging.
- Test coverage: Likely zero; requires Discord guild/channel fixtures.

**Console input polling with select() (Windows incompatible):**
- Files: `Features/ServerManagement/console_commands/console_commands.py` (uses select module, line 17)
- Why fragile: select() is Unix-only. On Windows, blocks console. Cybrancee runs Linux, so not an issue in production, but breaks local dev on Windows.
- Safe modification: Use aioconsole or asyncio.StreamReader for cross-platform stdin.
- Test coverage: None; console commands are manual/interactive.

**Live feeds mixin expects bot to provide specific attributes:**
- Files: `Features/Infrastructure/live_feeds/live_feeds.py` lines 50–68 (method contracts)
- Why fragile: Large implicit interface. If bot class refactored and a method removed, mixin breaks at runtime (not caught at import).
- Safe modification: Add runtime assertions in mixin __init__. Or use Protocol/ABC to enforce interface at type-check time.
- Test coverage: Low; integration tests only.

## Scaling Limits

**SQLite not optimized for concurrent writes from multiple processes:**
- Current capacity: Single bot process, no multi-process concurrency. Works fine for 1 instance.
- Limit: If deploying multiple bot instances (e.g., for redundancy or load balancing), all must serialize writes to single `bot.db` file. This causes lock contention.
- Scaling path: Migrate to PostgreSQL or MySQL (or cloud SQLite like Turso) for true concurrent writes. Or shard by guild (each bot instance manages a subset).

**In-memory caches not distributed across instances:**
- Current capacity: Caches (GUILD_ALLOWLIST, Banned_user_ids, QuarantinedServerid) are in-process only.
- Limit: Multi-instance setups have stale caches (instance A doesn't see ban added on instance B until refresh).
- Scaling path: Use Redis or similar for shared cache. Update on write, not just periodic refresh.

**Single refresh loop shared across all guilds:**
- Current capacity: 45-second cycle fetches all 4 endpoints once, then edits all guilds. With 20 guilds, ~60 seconds total (due to 3s delays). Fits in 45s window.
- Limit: At ~50+ guilds, editing overruns the 45-second refresh cycle. Queue depth and latency grow. Embeds become stale.
- Scaling path: Shard refresh by guild (e.g., guild hash % num_shards). Or run multiple refresh loops in parallel, each handling subset of guilds.

**TTR API rate limits not enforced client-side:**
- Current capacity: Assume TTR API allows ~1-2 req/s per endpoint, shared across all bots. Single bot makes ~8 requests per 45s (fetch × 4 endpoints × 2 manual calls). Likely no issue.
- Limit: At 100+ deployed bots, TTR API could rate-limit or block. No client-side queueing.
- Scaling path: Implement distributed rate limiter (e.g., Redis-backed token bucket). Coordinate across instances.

## Dependencies at Risk

**aiosqlite (v0.x):**
- Risk: aiosqlite is not 1.0 yet. API may change. Connection pooling is basic.
- Impact: Future version bumps may require code changes. Pool exhaustion under load has no built-in backpressure.
- Migration plan: Monitor aiosqlite roadmap. If stability concerns grow, consider async-sqlalchemy or asyncpg (PostgreSQL-only).

**discord.py (2.0+):**
- Risk: discord.py 2.0+ is stable, but 3.0 may have breaking changes (not yet released, but planned).
- Impact: Slash command API, intents, or event system could change.
- Migration plan: Pin to 2.0.x for now. Monitor discord.py releases. Plan 3.0 migration 6+ months in advance.

**Cybrancee (external hosting platform):**
- Risk: Cybrancee may discontinue service, change pricing, or have uptime issues. No backup hosting strategy.
- Impact: Bot goes offline if Cybrancee fails. No ability to quickly migrate to another host.
- Migration plan: Keep git repo and all code in GitHub. Containerize with Docker (Dockerfile + docker-compose). Enable rapid re-deploy to any Linux host.

## Missing Critical Features

**No persistent session/state for guild-level settings:**
- Problem: /pdsetup creates channels + stores message IDs, but no per-guild configuration table (e.g., "disable auto-doodle", "custom category name")
- Blocks: Users cannot customize bot behavior per guild. One-size-fits-all config.
- Workaround: Re-run /pdsetup with manual edits? (not really feasible)
- Priority: Medium. Nice-to-have for multi-guild deployments.

**No analytics or telemetry:**
- Problem: No metrics on command usage, feed update latency, TTR API availability.
- Blocks: Can't diagnose performance issues. Don't know which guilds are most active. Can't measure bot health.
- Workaround: Parse logs manually (tedious).
- Priority: Low for now. High value for operations/SRE.

**No health-check endpoint:**
- Problem: No way to monitor bot availability from external services (e.g., Uptime Robot, Datadog).
- Blocks: Can't set up automated alerts if bot goes down.
- Workaround: SSH into Cybrancee and check logs.
- Priority: Medium for production-grade setup.

## Test Coverage Gaps

**Live feeds refresh loop not tested end-to-end:**
- What's not tested: Full cycle of fetching TTR API, building embeds, editing Discord messages, persisting state
- Files: `Features/Infrastructure/live_feeds/live_feeds.py`
- Risk: Changes to refresh logic could break silently (e.g., race condition, missing state flush). Only caught in production.
- Priority: High. Add integration tests with mocked Discord guild/channel/message.

**Message sweep deletion logic not tested:**
- What's not tested: Identifying stale messages, deleting them, handling permission errors
- Files: `Features/Infrastructure/message_sweep/message_sweep.py`
- Risk: Stale message cleanup could delete active messages or miss orphaned ones. Data loss.
- Priority: High.

**Database schema migration (TEXT → INTEGER guild_id) not tested:**
- What's not tested: Type migration across all tables, rollback, partial runs
- Files: `Features/Core/db/db.py` (migration code at ~line 118)
- Risk: Migration could corrupt data if run on partially-synced DB. No recovery path.
- Priority: High. Add migration tests with fixtures.

**Console command input parsing not tested:**
- What's not tested: Alias resolution, rate limiting, command dispatch for ban/unban/guildadd/etc.
- Files: `Features/ServerManagement/console_commands/console_commands.py`
- Risk: Typos in command names not caught. Rate limiter logic untested.
- Priority: Medium. Add unit tests for COMMAND_ALIASES and RateLimit class.

**Guild lifecycle allowlist checks not tested:**
- What's not tested: on_guild_join with allowed/non-allowed IDs, DM sending, auto-leave behavior
- Files: `Features/Infrastructure/guild_lifecycle/guild_lifecycle.py`
- Risk: Non-allowlisted guild joins and stays (if on_guild_remove fails). Silent failure.
- Priority: High. Add integration tests with mocked bot client.

**User ban enforcement not tested:**
- What's not tested: Banned user attempts slash command, user_system.check_ban() filters them out
- Files: `Features/Infrastructure/user_system/user_system.py`
- Risk: Banned user can invoke commands if check_ban fails. Security bypass.
- Priority: High. Add unit tests for ban checking logic.

**Config loading from .env not tested:**
- What's not tested: Env var parsing, fallback defaults, type coercion (e.g., REFRESH_INTERVAL as int)
- Files: `Features/Core/config/config.py`
- Risk: Invalid config silently accepted or crashes at runtime. Operators don't see errors until bot starts.
- Priority: Medium. Add unit tests for Config.load() with various invalid inputs.

---

*Concerns audit: 2026-05-07*
