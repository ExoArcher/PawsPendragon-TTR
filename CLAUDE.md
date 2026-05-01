# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Paws Pendragon is a multi-guild Discord bot that mirrors live Toontown Rewritten API data into pinned Discord embeds. One hosted instance serves multiple Discord servers via an allowlist. The bot supports both traditional server installs and Discord's User App feature.

The project is currently transitioning from a monolithic `bot.py` (71KB, 1454 lines) to a modular architecture with cleanly separated features (see `FEATURE_SPECIFICATIONS.md` for the full refactoring plan).

**Python requirement**: Requires Python 3.9+.

## Refactoring Status

The codebase is transitioning from a monolithic `PDMain/bot.py` to modular `Features/` structure. Both exist simultaneously:
- **Current working code**: Mostly in `PDMain/bot.py` + `Features/Core/` utilities
- **New modular code**: `Features/Infrastructure/`, `Features/User/`, `Features/Admin/`, `Features/ServerManagement/`

When adding features, prefer the modular structure and create/update `BRIEFING.md` documentation.

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

## First Steps: Understanding the Codebase

**To understand the overall architecture:**
1. Read: `CLAUDE.md` (you are here)
2. Read: `FEATURE_SPECIFICATIONS.md` (17+ modular features and their dependencies)
3. Read: `PDMain/bot.py` (first 50 lines for overview; search `_refresh_loop()` for the main 90-second loop)

**To work on a specific feature:**
1. Locate the feature in `FEATURE_SPECIFICATIONS.md` (features 1–18)
2. Read the corresponding `BRIEFING.md` in `PDMain/Features/<Category>/<feature_name>/BRIEFING.md`
3. Reference `PDMain/CLAUDE.md` for detailed module responsibilities

**Key modules to understand first** (before working on features):
- `PDMain/Features/Core/config/config.py` — loads `.env`, frozen at startup
- `PDMain/Features/Core/db/db.py` — async SQLite layer with migration logic
- `PDMain/Features/Core/ttr_api/ttr_api.py` — async HTTP client for TTR endpoints (use as context manager)
- `PDMain/Features/Core/formatters/formatters.py` — converts TTR JSON → Discord embeds

## Project Structure

### Current Active Code (PDMain/)

This is where the bot runs from. Contains:

- **`bot.py`** — The main `TTRBot` class (subclass of `discord.AutoShardedClient`). Owns: refresh loop, all slash commands (11 total), state management, ban/maintenance/welcome systems.
- **`Features/`** — Modular feature directory (refactoring in progress):
  - **Core/** — Core utilities: `config.py`, `db.py` (SQLite async layer), `formatters.py` (TTR JSON → Discord embeds), `ttr_api.py` (aiohttp client for TTR public endpoints).
  - **Infrastructure/** — Background systems: `live_feeds.py` (refresh loop), `user_system.py` (welcome DMs, ban enforcement), `guild_lifecycle.py` (join/leave), `announcements_maintenance.py` (maintenance mode, panel announcements), `message_sweep.py` (stale message cleanup), `github_autoupdate.py`, `state_persistence.py`.
  - **User/** — User-facing commands: `ttrinfo.py`, `doodleinfo.py`, `calculate.py`, `helpme.py`, `invite_app.py`, `invite_server.py`, `beanfest.py`.
  - **Admin/** — Admin commands: `pd_setup.py`, `pd_refresh.py`, `pd_teardown.py`.
  - **ServerManagement/** — `console_commands.py` (stdin handler for hosting panel: `stop`, `restart`, `maintenance`, `announce`).
- **`requirements.txt`** — Python dependencies (discord.py, aiohttp, python-dotenv, aiosqlite).
- **`.env.example`** — Template for environment variables.
- **`DEPLOY.md`** — Cybrancee hosting setup guide.
- **`CLAUDE.md`** — Detailed bot documentation (comprehensive reference; see PDMain/CLAUDE.md).

### Root-Level Files

- **`FEATURE_SPECIFICATIONS.md`** — The master refactoring spec: breaks down 17+ modular features with scope, dependencies, TTR domain knowledge, and database table requirements.
- **`bot.db`** — SQLite database (auto-created on first run). Schema: `guild_feeds`, `allowlist`, `announcements`, `maintenance_msgs`, `welcomed_users`, `banned_users`, `maintenance_mode`.
- **`.env`** — Your local test secrets (never commit).

### Root-Level Modules (Future/Reference)

- **`Core/`**, **`Infrastructure/`**, **`User/`** — Future modular structure templates (not yet active).

## Architecture

### Data Flow (90-second refresh loop)

1. Every `REFRESH_INTERVAL` seconds (default 90s), `_refresh_loop()` fires in `bot.py`.
2. `_fetch_all()` gathers all 5 TTR API endpoints in parallel (invasions, population, fieldoffices, doodles, sillymeter).
3. For each tracked guild + feed key, `_update_feed()` is called:
   - Looks up the formatter from `formatters.FORMATTERS` dict.
   - Builds the embed(s).
   - Edits the pinned message in place using stored message IDs from `bot.db`.
   - Waits 3 seconds between guild edits to respect Discord rate limits.
4. Doodle embeds are throttled to once every 12 hours (unless forced via `/pd-refresh`).
5. Every 15 minutes, `_sweep_loop()` runs to delete stale bot messages.

### State Persistence

All state lives in SQLite (`bot.db`):

- **`guild_feeds`** — Per-guild channel + message ID tracking.
- **`allowlist`** — Runtime guild allowlist (unioned with `GUILD_ALLOWLIST` from `.env`).
- **`announcements`** — Temporary announcement messages with expiry timestamps.
- **`maintenance_mode`** — Active maintenance mode state per guild × feed key.
- **`welcomed_users`** — User IDs who received the first-use welcome DM.
- **`banned_users`** — Ban records (user_id → {reason, banned_at, banned_by, banned_by_id}).
- **`maintenance_msgs`** — One message ID per guild × feed during maintenance.

On first run, a one-time idempotent migration from legacy JSON files (`state.json` v1/v2, `welcomed_users.json`, `banned_users.json`, `maintenance_mode.json`) to SQLite is performed.

### Slash Commands

**User commands** (work in servers, DMs, group chats, and User App):
- `/ttrinfo` — DMs you current districts, invasions, field offices, Silly Meter.
- `/doodleinfo` — DMs you all available doodles with trait ratings and buying guide.
- `/calculate <suit> <level> <current_points>` — Shows points to next level with activity recommendations.
- `/invite-app` — DMs you the link to add the bot to your personal Discord account.
- `/invite-server` — DMs you the link to add the bot to a server.
- `/helpme` — DMs you the full command list (ephemeral if DMs blocked).

**Server admin commands** (require Manage Channels + Manage Messages):
- `/pd-setup` — Creates category + 3 channels, posts placeholders, starts live tracking.
- `/pd-refresh` — Force immediate data refresh, sweep stale messages.
- `/pd-teardown` — Stop tracking this server (channels remain, no longer updated).

**Console commands** (stdin on Cybrancee hosting panel, restricted to `BOT_ADMIN_IDS`):
- `stop` — Notify all servers, then shut down gracefully.
- `restart` — Notify all servers, then hot-restart the process.
- `maintenance` — Toggle a persistent orange banner across all tracked servers.
- `announce <text>` — Broadcast a message to every server's `#tt-information`. Auto-deletes after 30 minutes.
- `help` — List available console commands.

## Development

**No tests or linting setup.** This project is a single-bot deployment without a test harness. For local development:

### Running the Bot Locally

1. Start the bot: `python -u PDMain/bot.py` (requires `.env` with a test Discord server ID in `GUILD_ALLOWLIST`).
2. Watch the console for startup messages and errors.
3. Verify changes work:
   - Run `/pd-refresh` in your test guild to force an immediate data fetch and UI update.
   - Check console output for errors (bot logs to stdout with level INFO).
   - For detailed error tracking: `python -u PDMain/bot.py 2>&1 | grep -i error`

### Verify State

After running `/pd-refresh` or making changes, inspect the database:
```bash
sqlite3 PDMain/bot.db ".dump guild_feeds"   # See stored message IDs
sqlite3 PDMain/bot.db ".dump announcements" # Check announcements
```

### Debugging Patterns

**Embeds not updating?**
- Check (a) bot has Send/Edit perms in the channel, (b) message IDs in `guild_feeds` table are correct, (c) feed is tracked for the guild.
- Verify formatter returns valid embeds: check `PDMain/Features/Core/formatters/formatters.py` for the feed key.

**TTR API errors?**
- 503 errors during TTR maintenance are normal; bot retries automatically.
- Check `ttr_api.py` context manager usage — leaving sessions open causes memory leaks.

**Env vars not taking effect?**
- `Config` is frozen at startup. Restart the bot after changing `.env`.

**Commands not responding?**
- Check bot has proper intents and permissions in Discord server.
- Verify the command is registered: search `@app_commands.command()` in the relevant feature module.
- For 3-second rate limit delays between guild edits, see `_update_feed()` in `bot.py`.

## Code Patterns & Important Invariants

**Async everywhere.** All I/O (discord.py API, aiosqlite, aiohttp) is async. Never use `requests` or sync SQLite.

**Formatter registration via dict.** `formatters.py` exports a `FORMATTERS` dict mapping feed keys (`"invasions"`, `"doodles"`, etc.) to builder functions. New feeds must be added to this dict and used in `_update_feed()`.

**Message ID persistence is critical.** Feeds work by editing pinned messages in place. The bot stores message IDs in the `guild_feeds` table. If a channel is deleted or the bot loses perms, message IDs become stale — the next edit fails silently. Always verify perms before troubleshooting missing embeds.

**Rate limiting.** The bot sleeps 3 seconds between consecutive embed edits in the same guild. This respects Discord's rate limit.

**Guild allowlist is unioned.** The effective allowlist is `GUILD_ALLOWLIST` (from `.env`) UNION with the runtime allowlist (from `bot.db`). The `allow` command (or direct DB edit) adds to the runtime allowlist.

**TTR API async context manager.** Use `ttr_api.TTRClient()` as a context manager; it auto-closes the aiohttp session. Calling it outside a context manager will leak connections.

**Config is frozen.** `config.py` exports a frozen `Config` dataclass loaded once at startup. Mutation requires a restart. Environment variable changes do not take effect until a restart.

## Common Pitfalls

- **Message IDs not updating?** Verify: (1) bot has Send/Edit perms, (2) message IDs are stored in `guild_feeds`, (3) formatter returns valid embeds, (4) the guild is in the effective allowlist (GUILD_ALLOWLIST ∪ runtime allowlist).

- **Env vars not taking effect?** `Config` is frozen at startup; restart the bot after changing `.env`.

- **TTR API returning 503?** Normal during TTR maintenance; bot retries automatically with exponential backoff.

- **Embed edit rate-limited?** Intentional: bot waits 3 seconds between consecutive edits per guild to respect Discord rate limits (see `_update_feed()`).

- **"Invasions" showing as empty?** This is intentional; building data is unavailable per user constraint. See FEATURE_SPECIFICATIONS.md Feature 11.

- **Lost aiohttp connections?** Always use `ttr_api.TTRClient()` as a context manager. Leaving sessions open causes gradual memory leak.

- **Stale message IDs in database?** If a channel is deleted or the bot loses perms, message IDs become stale. The next edit fails silently. Always verify perms before troubleshooting missing embeds.

- **Guild not accepting commands?** Check: (1) guild is in GUILD_ALLOWLIST or runtime allowlist, (2) bot has proper Discord intents (MESSAGE_CONTENT, etc.), (3) commands are synced to guild (happens on startup).

## Environment Variables

See `PDMain/.env.example` for the full list. **Required:**
- `DISCORD_TOKEN` — bot token from https://discord.com/developers/applications.
- `GUILD_ALLOWLIST` — comma-separated Discord server IDs the bot is allowed to join.
- `BOT_ADMIN_IDS` — comma-separated Discord user IDs that can run console commands.

**Important optional:**
- `REFRESH_INTERVAL` (default 90) — seconds between live feed refreshes. 60–90s recommended.
- `USER_AGENT` — descriptive string sent to the TTR API (they request one).
- Custom emoji IDs (`JELLYBEAN_EMOJI`, `COG_EMOJI`, `STAR_*`) — used by `formatters.py`. Omit to fall back to plaintext.

## Feature Refactoring

The `FEATURE_SPECIFICATIONS.md` document outlines a plan to break the monolithic `bot.py` into 17+ modular features. Each feature has:

- A dedicated module in `PDMain/Features/`.
- A `BRIEFING.md` documenting scope, database tables, Discord API calls, and dependencies.
- Clear separation of concerns (e.g., `live_feeds.py` owns the refresh loop; `formatters.py` owns embed building).

When working on a specific feature, check the corresponding `BRIEFING.md` to understand:
- What this feature is responsible for.
- Which database tables it uses.
- Which TTR API endpoints it calls.
- Dependencies on other features.

Example: `PDMain/Features/Core/db/BRIEFING.md` explains the async SQLite layer, schema, and migration logic.

## File Categories

**Source code (always commit):**
- `PDMain/bot.py`, `PDMain/Features/**/*.py`
- `PDMain/requirements.txt`, `PDMain/.env.example`, `PDMain/.gitignore`
- `PDMain/CLAUDE.md`, `PDMain/DEPLOY.md`, `PDMain/README.md`, `PDMain/Procfile`, `PDMain/runtime.txt`
- `FEATURE_SPECIFICATIONS.md`, `CLAUDE.md` (this file)

**Auto-generated (safe to delete, auto-recreated on startup):**
- `PDMain/bot.db` — SQLite database. First-run auto-initializes; schema is immutable.
- `PDMain/__pycache__/` — Python bytecode cache.
- Legacy JSON files (if present): `state.json`, `welcomed_users.json`, `banned_users.json`, `maintenance_mode.json`. Migrated to `bot.db` on first run; safe to delete after migration.
- `PDMain/teardown_log.txt` — Append-only audit log of `/pd-teardown` invocations.
- `PDMain/panel_announce.txt` — Read and deleted by the bot every 90 seconds (hosting panel feature).

**Never commit:**
- `.env` (or `PDMain/.env`) — Your real Discord token and secret IDs.

## Hosting

Designed for Cybrancee Discord Bot Hosting. Recommended plan: Basic ($1.49/mo, 512 MB RAM). The bot uses ~50–100 MB across multiple servers.

**Setup:**
- Set `worker:` to `python3 PDMain/bot.py` in the hosting panel.
- Upload `.env` (with real secrets) and `requirements.txt`.
- The bot auto-initializes the database on first startup.
- For emergency announcements, upload `panel_announce.txt` to the file manager.

See `PDMain/DEPLOY.md` for full setup, invite URLs, and troubleshooting.

## See Also

- **`PDMain/CLAUDE.md`** — Comprehensive technical reference for the current bot implementation. Read this for deep dives into specific modules.
- **`FEATURE_SPECIFICATIONS.md`** — Master refactoring plan with 17+ feature specs, each listing scope, dependencies, database tables, and TTR domain knowledge.
- **`PDMain/README.md`** — User-facing documentation and version history.
- **`PDMain/DEPLOY.md`** — Hosting setup guide.
- **Feature BRIEFINGs** — Each feature in `PDMain/Features/` has a `BRIEFING.md` explaining its scope and responsibilities.
