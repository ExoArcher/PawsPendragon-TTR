# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Paws Pendragon is a multi-guild Discord bot that mirrors live Toontown Rewritten API data into pinned Discord embeds. One hosted instance serves multiple Discord servers via an allowlist. The bot supports both traditional server installs and Discord's User App feature.

The project is currently transitioning from a monolithic `bot.py` (71KB, 1454 lines) to a modular architecture with cleanly separated features (see `FEATURE_SPECIFICATIONS.md` for the full refactoring plan).

**Python requirement**: Requires Python 3.9+.

## Quick Start

**Linux/macOS:**
```bash
cd PDMain
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: fill in DISCORD_TOKEN, GUILD_ALLOWLIST, BOT_ADMIN_IDS
python -u bot.py
```

**Windows (PowerShell):**
```powershell
cd PDMain
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env with your Discord credentials
python -u bot.py
```

The bot auto-initializes the SQLite database (`bot.db`) on first run. It also performs automatic git updates on startup (compares local HEAD to `origin/main` and restarts if behind).

## Common Development Commands

**Run the bot locally:**
```bash
cd PDMain && python -u bot.py
```

**Check Python syntax without running:**
```bash
python -m py_compile bot.py
python -m py_compile Features/**/*.py  # Check all features
```

**Inspect the SQLite database:**
```bash
sqlite3 bot.db ".schema"                                # Show all table schemas
sqlite3 bot.db ".dump guild_feeds"                      # Export guild_feeds table
sqlite3 bot.db "SELECT * FROM guild_feeds LIMIT 5;"     # Query a table
sqlite3 bot.db ".dump" > backup.sql                     # Backup entire database
```

**Reset database (deletes all state):**
```bash
rm PDMain/bot.db  # Auto-recreates on next run
```

**Verify imports in a feature module:**
```bash
python -c "from Features.Core.db import db; print('OK')"
```

## First Steps: Understanding the Codebase

**For a quick architecture overview (15 mins):**
1. Read: `CLAUDE.md` (you are here)
2. Skim: `FEATURE_SPECIFICATIONS.md` section "Integration Points & Data Flow"
3. Grep `_refresh_loop()` in `PDMain/bot.py` (the 90-second heartbeat)

**To work on a specific feature (30 mins):**
1. Locate the feature in `FEATURE_SPECIFICATIONS.md` (Features 1–18)
2. Read the corresponding `BRIEFING.md` in `PDMain/Features/<Category>/<feature_name>/BRIEFING.md`
3. If extracting from `bot.py`, search the line numbers listed in the spec
4. If modifying Core utilities, check `PDMain/Features/Core/*/BRIEFING.md`

**Key modules to understand first** (before working on features):
- `PDMain/Features/Core/config/config.py` — loads `.env`, frozen at startup
- `PDMain/Features/Core/db/db.py` — async SQLite layer with migration logic
- `PDMain/Features/Core/ttr_api/ttr_api.py` — async HTTP client for TTR endpoints (use as context manager)
- `PDMain/Features/Core/formatters/formatters.py` — converts TTR JSON → Discord embeds

## Refactoring Status

The codebase is transitioning from a monolithic `PDMain/bot.py` to modular `Features/` structure. Both exist simultaneously:
- **Current working code**: Mostly in `PDMain/bot.py` + `Features/Core/` utilities
- **New modular code**: `Features/Infrastructure/`, `Features/User/`, `Features/Admin/`, `Features/ServerManagement/`

When adding features, prefer the modular structure and create/update `BRIEFING.md` documentation.

## Project Structure

### Current Active Code (PDMain/)

This is where the bot runs from. Contains:

- **`bot.py`** — The main `TTRBot` class (subclass of `discord.AutoShardedClient`). Owns: refresh loop, all slash commands (11 total), state management, ban/maintenance/welcome systems.
  - Lines 1-50: Auto-update from GitHub (pre-startup)
  - Lines 51-200: Imports, Config loading, TTRBot class init
  - Lines 201-400: Helper methods (guild allowlist, command sync, message management)
  - Lines 401-700: Core loops (_refresh_loop, _fetch_all, _update_feed)
  - Lines 701-800: Sweep loop (_sweep_loop, message cleanup)
  - Lines 801-900: Announcements & maintenance handling
  - Lines 901-1000: User system (welcome DMs, ban enforcement)
  - Lines 1001-1454: Slash commands (11 total)

- **`Features/`** — Modular feature directory (refactoring in progress):
  - **Core/** — Core utilities: `config.py`, `db.py` (SQLite async layer), `formatters.py` (TTR JSON → Discord embeds), `ttr_api.py` (aiohttp client for TTR public endpoints).
  - **Infrastructure/** — Background systems: `live_feeds.py`, `user_system.py`, `guild_lifecycle.py`, `announcements_maintenance.py`, `message_sweep.py`, `github_autoupdate.py`.
  - **User/** — User-facing commands: `ttrinfo.py`, `doodleinfo.py`, `calculate.py`, `helpme.py`, `invite.py`, `beanfest.py`.
  - **Admin/** — Admin commands: `pd_setup.py`, `pd_refresh.py`, `pd_teardown.py`.
  - **ServerManagement/** — `console_commands.py` (stdin handler for hosting panel).

- **`requirements.txt`** — Python dependencies (discord.py, aiohttp, python-dotenv, aiosqlite).
- **`.env.example`** — Template for environment variables.
- **`DEPLOY.md`** — Cybrancee hosting setup guide.

### Root-Level Files

- **`FEATURE_SPECIFICATIONS.md`** — The master refactoring spec: breaks down 17+ modular features with scope, dependencies, TTR domain knowledge, and database table requirements.
- **`bot.db`** — SQLite database (auto-created on first run).
- **`.env`** — Your local test secrets (never commit).

## Architecture

### Data Flow (90-second refresh loop)

1. Every `REFRESH_INTERVAL` seconds (default 90s), `_refresh_loop()` fires in `bot.py`.
2. `_fetch_all()` gathers all 5 TTR API endpoints in parallel (population, fieldoffices, doodles, sillymeter, no invasions).
3. For each tracked guild + feed key, `_update_feed()` is called:
   - Looks up the formatter from `formatters.FORMATTERS` dict.
   - Builds the embed(s).
   - Edits the pinned message in place using stored message IDs from `bot.db`.
   - Waits 3 seconds between guild edits to respect Discord rate limits.
4. Doodle embeds are throttled to once every 12 hours (unless forced via `/pdrefresh`).
5. Every 15 minutes, `_sweep_loop()` runs to delete stale bot messages.

### State Persistence

All state lives in SQLite (`bot.db`):

- **`guild_feeds`** — Per-guild channel + message ID tracking (critical for in-place editing).
- **`allowlist`** — Runtime guild allowlist (unioned with `GUILD_ALLOWLIST` from `.env`).
- **`announcements`** — Temporary announcement messages with expiry timestamps.
- **`maintenance_mode`** — Active maintenance mode state per guild × feed key.
- **`welcomed_users`** — User IDs who received the first-use welcome DM.
- **`banned_users`** — Ban records (user_id → {reason, banned_at, banned_by, banned_by_id}).
- **`maintenance_msgs`** — One message ID per guild × feed during maintenance.

On first run, a one-time idempotent migration from legacy JSON files (`state.json` v1/v2, `welcomed_users.json`, `banned_users.json`, `maintenance_mode.json`) to SQLite is performed.

## Development Workflows

### Running the Bot Locally

1. Set up `.env` with a test Discord server (see `DEPLOY.md` for how to get credentials).
2. Run: `python -u PDMain/bot.py`
3. The bot logs to stdout with level INFO. Watch for:
   - `[auto-update]` messages (GitHub sync)
   - `on_ready()` logs (guild sync, command registration)
   - `_refresh_loop()` messages (90-second ticks)
4. Verify changes work:
   - Run `/pdrefresh` in your test guild to force an immediate data fetch and UI update.
   - Check console output for errors.

### Debugging a Feature

**Embeds not updating?**
1. Check bot has Send/Edit perms in the channel: `discord.py` would log permission errors.
2. Inspect `guild_feeds` table: `sqlite3 PDMain/bot.db "SELECT * FROM guild_feeds WHERE guild_id = <your_guild_id>;"`
3. Verify formatter exists: check `PDMain/Features/Core/formatters/formatters.py` for the feed key.
4. Check feed is tracked: query `guild_feeds` for your guild + feed key combo.

**TTR API errors?**
- 503 errors during TTR maintenance are normal; bot retries automatically.
- Check `ttr_api.py` context manager usage — leaving sessions open causes memory leaks.
- Inspect the raw response: add print statements before `formatters.build_*()` calls.

**Env vars not taking effect?**
- `Config` is frozen at startup. Restart the bot after changing `.env`.

**Commands not responding?**
- Check bot has proper intents and permissions in Discord server.
- Verify the command is registered: search `@app_commands.command()` in the relevant feature module.
- Use Discord Developer Mode (right-click to copy IDs) to verify you're in an allowlisted guild.

### Extracting a Feature from bot.py

When extracting code from the monolithic `bot.py`:

1. Find the feature's line ranges in `FEATURE_SPECIFICATIONS.md` (e.g., Feature 1: lines 1100-1160).
2. Read those sections in `PDMain/bot.py` to understand current behavior.
3. Check the feature's `BRIEFING.md` to understand scope and dependencies.
4. Create the new module in `PDMain/Features/<Category>/<FeatureName>/`, with:
   - `__init__.py` (exports the public API)
   - `<feature>.py` (implementation)
   - `BRIEFING.md` (scope, database tables, dependencies)
5. Wire it into `bot.py`: remove old code, import and call the new module.
6. Test: run `/pdrefresh` to ensure the feature still works.

### Adding a New Feed

To add a new live feed (e.g., a new TTR API endpoint):

1. Add the TTR API call to `ttr_api.py` (async context manager pattern).
2. Add a formatter in `formatters.py` (maps TTR JSON → Discord embed).
3. Register the formatter in `formatters.FORMATTERS` dict (maps feed key to builder function).
4. Add the feed key to `_update_feed()` in `bot.py` or the new `live_feeds.py` module.
5. Create the channel + message via `/pdsetup` or manually via `guild_feeds` table.
6. Test: run `/pdrefresh` to verify the embed updates.

## Code Patterns & Important Invariants

**Async everywhere.** All I/O (discord.py API, aiosqlite, aiohttp) is async. Never use `requests` or sync SQLite.

**Formatter registration via dict.** `formatters.py` exports a `FORMATTERS` dict mapping feed keys to builder functions. New feeds must be added to this dict.

**Message ID persistence is critical.** Feeds work by editing pinned messages in place. The bot stores message IDs in the `guild_feeds` table. If a channel is deleted or the bot loses perms, message IDs become stale — the next edit fails silently.

**Rate limiting.** The bot sleeps 3 seconds between consecutive embed edits in the same guild.

**Guild allowlist is unioned.** The effective allowlist is `GUILD_ALLOWLIST` (from `.env`) UNION with the runtime allowlist (from `bot.db`).

**TTR API async context manager.** Use `ttr_api.TTRClient()` as a context manager; it auto-closes the aiohttp session. Calling it outside a context manager will leak connections.

**Config is frozen.** `config.py` exports a frozen `Config` dataclass loaded once at startup. Mutation requires a restart.

## Common Pitfalls

- **Message IDs not updating?** Verify: (1) bot has Send/Edit perms, (2) message IDs are stored in `guild_feeds`, (3) formatter returns valid embeds, (4) the guild is in the effective allowlist.

- **Env vars not taking effect?** `Config` is frozen at startup; restart the bot after changing `.env`.

- **TTR API returning 503?** Normal during TTR maintenance; bot retries automatically.

- **Embed edit rate-limited?** Intentional: bot waits 3 seconds between consecutive edits per guild.

- **"Invasions" showing as empty?** Intentional; building data is unavailable per user constraint.

- **Lost aiohttp connections?** Always use `ttr_api.TTRClient()` as a context manager.

- **Stale message IDs in database?** If a channel is deleted or the bot loses perms, message IDs become stale. The next edit fails silently.

- **Guild not accepting commands?** Check: (1) guild is in allowlist, (2) bot has proper intents (MESSAGE_CONTENT, etc.), (3) commands are synced.

## Environment Variables

See `PDMain/.env.example` for the full list. **Required:**
- `DISCORD_TOKEN` — bot token from https://discord.com/developers/applications.
- `GUILD_ALLOWLIST` — comma-separated Discord server IDs the bot is allowed to join.
- `BOT_ADMIN_IDS` — comma-separated Discord user IDs that can run console commands.

**Important optional:**
- `REFRESH_INTERVAL` (default 90) — seconds between live feed refreshes. 60–90s recommended.
- `USER_AGENT` — descriptive string sent to the TTR API (they request one).
- Custom emoji IDs (`JELLYBEAN_EMOJI`, `COG_EMOJI`, `STAR_*`) — used by formatters. Omit to fall back to plaintext.

## Feature Refactoring

The `FEATURE_SPECIFICATIONS.md` document outlines a plan to break the monolithic `bot.py` into 17+ modular features. Each feature has:

- A dedicated module in `PDMain/Features/`.
- A `BRIEFING.md` documenting scope, database tables, Discord API calls, and dependencies.
- Clear separation of concerns.

When working on a specific feature, check the corresponding `BRIEFING.md` to understand:
- What this feature is responsible for.
- Which database tables it uses.
- Which TTR API endpoints it calls.
- Dependencies on other features.

## File Categories

**Source code (always commit):**
- `PDMain/bot.py`, `PDMain/Features/**/*.py`
- `PDMain/requirements.txt`, `PDMain/.env.example`, `PDMain/.gitignore`
- `PDMain/CLAUDE.md`, `PDMain/DEPLOY.md`, `PDMain/README.md`, `PDMain/Procfile`, `PDMain/runtime.txt`
- `FEATURE_SPECIFICATIONS.md`, `CLAUDE.md` (this file)

**Auto-generated (safe to delete, auto-recreated on startup):**
- `PDMain/bot.db` — SQLite database. Auto-initializes; schema is immutable.
- `PDMain/__pycache__/` — Python bytecode cache.
- Legacy JSON files: `state.json`, `welcomed_users.json`, `banned_users.json`, `maintenance_mode.json`. Migrated to `bot.db` on first run; safe to delete after migration.
- `PDMain/teardown_log.txt` — Append-only audit log of `/pdteardown` invocations.
- `PDMain/panel_announce.txt` — Read and deleted by the bot every 90 seconds.

**Never commit:**
- `.env` — Your real Discord token and secret IDs.

## Hosting

Designed for Cybrancee Discord Bot Hosting. Recommended plan: Basic ($1.49/mo, 512 MB RAM).

**Setup:**
- Set `worker:` to `python3 PDMain/bot.py` in the hosting panel.
- Upload `.env` (with real secrets) and `requirements.txt`.
- The bot auto-initializes the database on first startup.
- For emergency announcements, upload `panel_announce.txt` to the file manager.

See `PDMain/DEPLOY.md` for full setup, invite URLs, and troubleshooting.

## See Also

- **`PDMain/CLAUDE.md`** — Detailed bot module documentation (deep reference for each component).
- **`FEATURE_SPECIFICATIONS.md`** — Master refactoring plan with 17+ feature specs.
- **`PDMain/README.md`** — User-facing documentation and version history.
- **`PDMain/DEPLOY.md`** — Hosting setup guide.
- **Feature BRIEFINGs** — Each feature in `PDMain/Features/` has a `BRIEFING.md` explaining scope.
