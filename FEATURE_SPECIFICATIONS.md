# FEATURE_SPECIFICATIONS.md — Paws Pendragon

Module-by-module specification of the Paws Pendragon Discord bot. This document describes **what each module does, what state it owns, what it exposes, and what depends on it**. It is the implementation companion to [README.md](README.md) (user-facing) and [CLAUDE.md](CLAUDE.md) (orientation).

Each module under `PDMain/Features/<area>/<module>/` also has a `BRIEFING.md` with deeper context. This document is the index and contract layer above those briefings.

---

## Conventions used in this document

- **Owns**: persistent or in-memory state this module is the sole writer of.
- **Reads**: state this module consumes from elsewhere.
- **Exposes**: public functions / classes / mixins / commands other modules import.
- **Depends on**: upstream modules required at import time or call time.
- **Triggered by**: how the module gets invoked (slash command, lifecycle hook, loop tick, console command).

---

## Table of contents

1. [Core / Config](#1-core--config)
2. [Core / DB](#2-core--db)
3. [Core / Formatters](#3-core--formatters)
4. [Core / TTR API](#4-core--ttr-api)
5. [Infrastructure / Live Feeds](#5-infrastructure--live-feeds)
6. [Infrastructure / Message Sweep](#6-infrastructure--message-sweep)
7. [Infrastructure / Announcements & Maintenance](#7-infrastructure--announcements--maintenance)
8. [Infrastructure / Guild Lifecycle](#8-infrastructure--guild-lifecycle)
9. [Infrastructure / GitHub Auto-Update](#9-infrastructure--github-auto-update)
10. [Infrastructure / User System](#10-infrastructure--user-system)
11. [Infrastructure / Cache Manager](#11-infrastructure--cache-manager)
12. [Infrastructure / Periodic Checks](#12-infrastructure--periodic-checks)
13. [Infrastructure / Quarantine & Unquarantine Checks](#13-infrastructure--quarantine--unquarantine-checks)
14. [Infrastructure / Blacklist Removal](#14-infrastructure--blacklist-removal)
15. [Server Management / Console Commands](#15-server-management--console-commands)
16. [Admin / pdsetup](#16-admin--pdsetup)
17. [Admin / pdrefresh](#17-admin--pdrefresh)
18. [Admin / pdteardown](#18-admin--pdteardown)
19. [User / ttrinfo](#19-user--ttrinfo)
20. [User / doodleinfo](#20-user--doodleinfo)
21. [User / doodlesearch](#21-user--doodlesearch)
22. [User / helpme](#22-user--helpme)
23. [User / calculate](#23-user--calculate)
24. [Bot Entry & Slash Commands (`bot.py`)](#24-bot-entry--slash-commands-botpy)

---

## 1. Core / Config

**Path**: `PDMain/Features/Core/config/config.py`
**BRIEFING**: `PDMain/Features/Core/config/BRIEFING.md`

**Purpose**: Centralized, immutable runtime configuration. Loads `.env` once at startup; exposes a frozen dataclass. Provides helpers to read and rewrite individual `.env` keys for admin actions that must persist across restarts (bans, quarantines).

**Owns**:
- The `_LIVE_ENV_PATH` chosen at startup (probed in this order: `/home/container/.env`, `/home/container/PDMain/.env`, `./.env`).
- The frozen `Config` instance returned by `Config.load()`.

**Reads**: environment variables only.

**Exposes**:
- `Config` — frozen `@dataclass`. Fields include `token`, `guild_allowlist`, `admin_ids`, `refresh_interval`, `user_agent`, channel-name fields, banned/quarantined ID sets, and ~20 emoji fields.
- `Config.load() -> Config` — classmethod, called once at boot.
- `Config.feeds() -> dict[str, str]` — `{"information": <chan>, "doodles": <chan>}`. Suit-calculator is *not* listed because it is static.
- `Config.is_guild_allowed(guild_id) -> bool`
- `Config.is_admin(user_id) -> bool`
- `find_env_path() -> str`
- `read_env_var(name) -> str`
- `update_env_var(name, value) -> str` — preserves comments, un-comments commented keys, appends if absent.
- `_parse_id_list(raw, var_name)` — comma/space-separated ID parser; raises on non-numeric.
- `_int_env(name, default)`

**Depends on**: `python-dotenv`.

**Triggered by**: imported once at startup (`bot.py`).

**Required env**: `DISCORD_TOKEN`, `GUILD_ALLOWLIST`.
**Optional env with defaults**: `BOT_ADMIN_IDS`, `REFRESH_INTERVAL=120`, `USER_AGENT`, `AUTO_UPDATE=true`, `CHANNEL_CATEGORY=PendragonTTR`, `CHANNEL_INFORMATION=tt-info`, `CHANNEL_DOODLES=tt-doodles`, `CHANNEL_SUIT_CALCULATOR=suit-calc`, `BANNED_USER_IDS`, `QUARANTINED_GUILD_IDS`, all emoji `*_EMOJI` keys.

**Invariants**:
- `Config` is never mutated after `load()`. To change a value, write it with `update_env_var` *and* either restart the bot or update the relevant DB-backed cache.

---

## 2. Core / DB

**Path**: `PDMain/Features/Core/db/db.py`
**BRIEFING**: `PDMain/Features/Core/db/BRIEFING.md`

**Purpose**: SQLite schema definition, init, and the `load_state` / `save_state` API used by the rest of the bot. All persistence flows through this module — feature modules do not open their own connections.

**Owns**: the SQLite database file.

**Tables**:
1. `guild_feeds` — `(guild_id TEXT, feed_key TEXT, channel_id INTEGER, message_ids TEXT JSON)`, PK `(guild_id, feed_key)`. `feed_key` includes `"information"`, `"doodles"`, `"suit_calculator"`, and prefixed `"suit_threads.{faction}"`.
2. `allowlist` — runtime allowlist (effective allowlist = env ∪ this).
3. `announcements` — pending announcements with TTL.
4. `maintenance_msgs` — sticky maintenance banners.
5. `welcomed_users` — users already DM'd the welcome.
6. `banned_users` — user-level bans.
7. `maintenance_mode` — single-row global flag.
8. `quarantined_guilds` — guilds receiving no feed updates.
9. `blacklist` — guild-level blacklist.
10. `audit_log` — append-only admin-action log.

**Exposes**:
- `init_db()` — idempotent table creation; runs once at startup.
- `load_state()` — returns the in-memory state mapping consumed by feature modules.
- `save_state(state)` — atomic write-through.
- One-time migration shim: detects legacy `state.json` / `banned_users.json` and folds them into SQLite on first boot.

**Depends on**: `aiosqlite`.

**Triggered by**: `bot.on_ready` (init); various feature modules (load/save).

**Invariants**:
- Schema changes ship with `CREATE TABLE IF NOT EXISTS` and an in-place migration if column shapes change.
- `STATE_VERSION` (in `bot.py`) bumps when `load_state` semantics change.

---

## 3. Core / Formatters

**Path**: `PDMain/Features/Core/formatters/`
**BRIEFING**: `PDMain/Features/Core/formatters/BRIEFING.md`

**Purpose**: Build `discord.Embed` objects from cached TTR data. Formatters are pure — they take data in, return embeds out, never call Discord or the TTR API directly.

**Exposes**: one builder per embed type. Builders are registered in a dict so the live-feeds dispatcher can call them by `feed_key`. Categories of formatter:
- Information embed (population + invasions + field offices header).
- Field office detail (per-office embed).
- Doodle market embed (per-district).
- Suit calculator (static reference embed).
- Sillymeter / beanfest embed.

**Depends on**: emoji constants from `Config`, star tier emojis (`STAR_PERFECT`…`STAR_BAD`).

**Triggered by**: `live_feeds` refresh loop; slash commands that build one-shot embeds.

---

## 4. Core / TTR API

**Path**: `PDMain/Features/Core/ttr_api/`
**BRIEFING**: `PDMain/Features/Core/ttr_api/BRIEFING.md`

**Purpose**: Async HTTP client for the public Toontown Rewritten API. Sends the configured `USER_AGENT`. Wraps five endpoints:

1. `population` — districts + total players.
2. `fieldoffices` — active field offices, annexes remaining.
3. `doodles` — doodle market listings.
4. `sillymeter` — beanfest meter readout.
5. `invasions` — active cog invasions.

**Exposes**: one async function per endpoint, each returning a parsed dict/dataclass.

**Depends on**: `aiohttp`, `Config.user_agent`.

**Triggered by**: `live_feeds` (per refresh tick), some slash commands (cache-fallback).

**Invariants**:
- TTR API is rate-sensitive. Refresh loop is the only periodic caller; slash commands prefer `cache_manager` snapshots over fresh hits.
- 4xx/5xx errors degrade gracefully — return last-known data and log; never crash the loop.

---

## 5. Infrastructure / Live Feeds

**Path**: `PDMain/Features/Infrastructure/live_feeds/live_feeds.py`
**BRIEFING**: `PDMain/Features/Infrastructure/live_feeds/BRIEFING.md`

**Purpose**: The refresh loop, supplied to the bot as the `LiveFeedsFeature` mixin. Drives all auto-updating embeds.

**Owns**: the refresh task handle; the per-tick scratch state.

**Reads**: `guild_feeds` rows; `cache_manager.QuarantinedServerid`; TTR API client; formatters.

**Exposes**:
- `LiveFeedsFeature` — mixin class. `class TTRBot(LiveFeedsFeature, discord.AutoShardedClient)` in `bot.py:190`.
- Refresh loop entry point at ~line 306–325 of `live_feeds.py`.

**Depends on**: `Core/db`, `Core/ttr_api`, `Core/formatters`, `cache_manager`, `Config.refresh_interval`.

**Triggered by**: started in `setup_hook` / `on_ready`.

**Loop semantics**:
1. Iterate effective-allowlist guilds.
2. For each guild: skip if in `QuarantinedServerid`.
3. For each `feed_key` in `Config.feeds()`: edit the persisted message in-place; if the message ID is invalid (deleted, permission lost), send a new one and update `guild_feeds.message_ids`.
4. Sleep 3 s between guilds (rate-limit hygiene).
5. Sleep `config.refresh_interval` between full passes.

**Invariants**:
- The loop never raises out; per-guild errors are caught, logged, and the loop moves on.
- Suit calculator and per-thread suit feeds are *not* refreshed by this loop — they are written by `/pdsetup` and `/pdrefresh` only.
- Doodle reposts are throttled by `DOODLE_REFRESH = 12 * 60 * 60` to avoid channel noise.

---

## 6. Infrastructure / Message Sweep

**Path**: `PDMain/Features/Infrastructure/message_sweep/`
**BRIEFING**: `PDMain/Features/Infrastructure/message_sweep/BRIEFING.md`

**Purpose**: Periodic janitor. Removes stale or orphaned messages the bot owns inside its category. Runs every ~15 minutes from `bot.py:826`.

**Owns**: the sweep task handle.

**Reads**: `guild_feeds`; channel histories.

**Triggered by**: `bot.on_ready`.

**Invariants**: sweep is idempotent and read-mostly; only deletes messages clearly authored by this bot in this bot's category.

---

## 7. Infrastructure / Announcements & Maintenance

**Path**: `PDMain/Features/Infrastructure/announcements_maintenance/`
**BRIEFING**: `PDMain/Features/Infrastructure/announcements_maintenance/BRIEFING.md`

**Purpose**: Push admin-authored announcement banners and maintenance notices to all allowed guilds. Backed by the `announcements` and `maintenance_msgs` tables.

**Owns**: TTL on announcements (`ANNOUNCEMENT_TTL = 30 * 60`).

**Triggered by**: console commands `announce` / `a` and `maintenance` / `m` / `maint`.

**Invariants**: announcements expire automatically; maintenance banners are sticky until cleared.

---

## 8. Infrastructure / Guild Lifecycle

**Path**: `PDMain/Features/Infrastructure/guild_lifecycle/`
**BRIEFING**: `PDMain/Features/Infrastructure/guild_lifecycle/BRIEFING.md`

**Purpose**: `on_guild_join` and `on_guild_remove` handlers.

- **Join**: check the *effective* allowlist (env ∪ DB `allowlist` table). If not allowed, leave the guild after a courtesy DM. If allowed, no-op (admin must run `/pdsetup`).
- **Remove**: purge guild rows from `guild_feeds`, `allowlist`, `quarantined_guilds`.

**Triggered by**: Discord gateway events.

---

## 9. Infrastructure / GitHub Auto-Update

**Path**: `PDMain/Features/Infrastructure/github_autoupdate/` (also implemented inline at top of `bot.py`).
**BRIEFING**: `PDMain/Features/Infrastructure/github_autoupdate/BRIEFING.md`

**Purpose**: Pull latest code from origin on startup, then re-exec if HEAD moved.

**Algorithm** (`bot.py` ~lines 47–127):
1. If `AUTO_UPDATE != "true"`, skip.
2. Locate repo dir (`_find_repo_dir()`).
3. Capture pre-pull HEAD.
4. Run `git pull --ff-only`.
5. If HEAD changed → clear `__pycache__` (`_clear_bytecode_cache()`) and `os.execv` the interpreter to reload.
6. If history diverged (non-FF) → log a warning and continue with current code. **Do not** hard-reset.

**Invariants**:
- Hash comparison prevents restart loops on no-op pulls.
- Soft-fail on divergence is intentional: the host may have local hotfixes that should not be silently overwritten.

---

## 10. Infrastructure / User System

**Path**: `PDMain/Features/Infrastructure/user_system/`
**BRIEFING**: `PDMain/Features/Infrastructure/user_system/BRIEFING.md`

**Purpose**: User-level concerns — welcome DMs (tracked in `welcomed_users`), bot-level user bans (`banned_users`), and audit logging.

**Exposes**: ban / unban primitives used by both slash commands and console commands. Writes through to `.env` (`BANNED_USER_IDS`) so bans persist across restarts even if the DB is wiped.

---

## 11. Infrastructure / Cache Manager

**Path**: `PDMain/Features/Infrastructure/cache_manager.py`

**Purpose**: In-memory caches hydrated at startup and updated as state changes. Avoids hitting SQLite on every event.

**Owns**:
- `QuarantinedServerid: set[int]` — checked by the refresh loop.
- TTR snapshot cache (last successful API result per endpoint).
- Per-guild allowlist mirror.

**Triggered by**: `bot.on_ready` (hydrate); `quarantine_checks` / `unquarantine_checks` / ban handlers (mutate).

---

## 12. Infrastructure / Periodic Checks

**Path**: `PDMain/Features/Infrastructure/periodic_checks.py`

**Purpose**: Cross-cutting health checks running on a slow timer. Verifies that expected channels still exist, that DB snapshots match Discord state, and surfaces drift.

**Triggered by**: started in `bot.on_ready`.

---

## 13. Infrastructure / Quarantine & Unquarantine Checks

**Paths**:
- `PDMain/Features/Infrastructure/quarantine_checks.py`
- `PDMain/Features/Infrastructure/unquarantine_checks.py`

**Purpose**: Apply / lift quarantine on a guild.

**Behavior**:
- Quarantine: add to `quarantined_guilds`, add to `cache_manager.QuarantinedServerid`, write `QUARANTINED_GUILD_IDS` in `.env`.
- Unquarantine: reverse all three.

**Triggered by**: console commands `quarrefresh`, `quarmsg`; admin paths.

**Why both DB and `.env`**: defense in depth. If the SQLite file is lost, env still seeds the set on next boot.

---

## 14. Infrastructure / Blacklist Removal

**Path**: `PDMain/Features/Infrastructure/blacklist_removal.py`

**Purpose**: Remove a guild from the `blacklist` table and rebuild any cached blacklist set.

**Triggered by**: admin actions.

---

## 15. Server Management / Console Commands

**Path**: `PDMain/Features/ServerManagement/console_commands/`
**BRIEFING**: `PDMain/Features/ServerManagement/console_commands/BRIEFING.md`

**Purpose**: Read commands from stdin (the Cybrancee panel exposes a console). Dispatch to handlers.

**Commands**: `stop` / `s`, `restart` / `r`, `maintenance` / `m` / `maint`, `announce` / `a`, `ban`, `unban`, `quarlist`, `quarrefresh`, `quarmsg`, `guildadd`, `guildremove`, `forcerefresh`, `help` / `h` / `?`.

**Reads**: stdin.
**Calls**: announcement system, maintenance system, ban system, quarantine system, allowlist system, refresh-loop trigger.

**Invariants**:
- All admin actions write through to both DB and `.env` where applicable so they survive restarts and DB resets.
- `help` output is the canonical list — keep it in sync when adding commands.

---

## 16. Admin / pdsetup

**Path**: `PDMain/Features/Admin/pd_setup/`
**Slash command**: `/pdsetup` (`bot.py:1214`).

**Purpose**: Create the `PendragonTTR` category and the three channels (`tt-info`, `tt-doodles`, `suit-calc`) in the invoking guild. Idempotent — re-running is safe.

**Writes**: `guild_feeds` rows for each feed; persists initial message IDs.

**Permission**: admin-gated.

---

## 17. Admin / pdrefresh

**Path**: `PDMain/Features/Admin/pd_refresh/`
**Slash command**: `/pdrefresh` (`bot.py:1263`).

**Purpose**: Force an out-of-band refresh for the invoking guild — re-renders all feeds *and* the static suit-calculator embed.

**Cooldown**: `_REFRESH_COOLDOWN = 600` seconds (10 min) per invoker.

**Permission**: admin-gated.

---

## 18. Admin / pdteardown

**Path**: `PDMain/Features/Admin/pd_teardown/`
**Slash command**: `/pdteardown` (`bot.py:1317`).

**Purpose**: Inverse of `/pdsetup`. Deletes the category and channels; clears `guild_feeds` rows for the guild.

**Permission**: admin-gated.

---

## 19. User / ttrinfo

**Path**: `PDMain/Features/User/ttrinfo/`
**Slash command**: `/ttrinfo` (`bot.py:1012`).

**Purpose**: One-shot snapshot of population + field offices + invasions. Reads from `cache_manager` snapshot — does not call TTR API directly.

---

## 20. User / doodleinfo

**Path**: `PDMain/Features/User/doodleinfo/`
**Slash command**: `/doodleinfo` (`bot.py:1052`).

**Purpose**: Doodle trait reference (what each trait does, how to read tier stars).

---

## 21. User / doodlesearch

**Path**: `PDMain/Features/User/doodlesearch/`
**Slash command**: `/doodlesearch` (`bot.py:1406`).

**Purpose**: Search the live doodle market for doodles matching a trait or rating threshold.

**Reads**: cached doodles snapshot.

---

## 22. User / helpme

**Path**: `PDMain/Features/User/helpme/`
**Slash command**: `/helpme` (`bot.py:1078`).

**Purpose**: Render the help embed listing all user-facing commands. Sister command: `/invite` at `bot.py:1132`. Sister command `/beanfest` at `bot.py:1169` shows the sillymeter readout.

---

## 23. User / calculate

**Path**: `PDMain/Features/User/calculate/`
**Slash command**: `/calculate` (`bot.py:1403`).

**Purpose**: Suit-promotion calculator. Computes cogs-needed-to-promote.

---

## 24. Bot Entry & Slash Commands (`bot.py`)

**Path**: `PDMain/bot.py` (~1422 lines).

**Purpose**: Entry point. Builds the `TTRBot` class, registers all 11 slash commands, starts background tasks, runs the auto-update preamble, and runs the stdin console loop.

**Top-level constants**:
- `STATE_VERSION = 2`
- `ANNOUNCEMENT_TTL = 30 * 60`
- `DOODLE_REFRESH = 12 * 60 * 60`
- `_REFRESH_COOLDOWN = 600`

**Class**: `class TTRBot(LiveFeedsFeature, discord.AutoShardedClient)` at ~line 190.

**Lifecycle**:
- `setup_hook` — register slash commands, start background tasks.
- `on_ready` — `init_db`, `load_state`, hydrate caches, start refresh + sweep loops.
- `on_guild_join` / `on_guild_remove` — delegate to `guild_lifecycle`.

**Slash command registration**: each command is a thin wrapper that delegates to its feature module. Locations were tabulated in [CLAUDE.md §6](CLAUDE.md).

**When to extend `bot.py`**: only for new top-level lifecycle wiring. New commands should add a feature module under `Features/User/` or `Features/Admin/` and register a thin wrapper here.

---

## Cross-cutting invariants

- **Effective allowlist** = env `GUILD_ALLOWLIST` ∪ DB `allowlist`. Both `guild_lifecycle` and `live_feeds` honor the union.
- **Quarantine bypasses leaves**: a quarantined guild stays joined but receives no feed updates. Compare with the blacklist, which excludes a guild from the allowlist.
- **All admin mutations write through to `.env`** when the env has a corresponding key. This makes the bot self-healing if the DB is wiped.
- **One refresh loop, many feeds**: do not start additional loops for new feed types. Add a `feed_key` and a formatter; the existing loop will pick it up.
- **No blocking I/O on the event loop**: aiosqlite for DB, aiohttp for HTTP, `asyncio.sleep` for waits.

---

## Adding a new feature: checklist

1. Create `PDMain/Features/<Area>/<feature_name>/` and a `BRIEFING.md` describing intent, owned state, public surface.
2. If the feature has runtime config: add fields to `Config` and to `.env.example.template`.
3. If the feature persists state: add a table in `db.py` (with `CREATE TABLE IF NOT EXISTS`) and extend `load_state` / `save_state`.
4. If the feature is a slash command: add a thin wrapper in `bot.py` that delegates into the module.
5. If the feature is an auto-updating embed: add a `feed_key`, a formatter in `Core/formatters/`, and a dispatch entry in `live_feeds.py`. Do **not** start a new loop.
6. If the feature has admin operations: add a console command and update its `help` text.
7. Update [CLAUDE.md](CLAUDE.md) §6 (commands) or §14 (common-tasks map) and add a section to this document.
