# External Integrations

**Analysis Date:** 2026-05-07

## APIs & External Services

**Toontown Rewritten (TTR) Public API:**
- Service: https://www.toontownrewritten.com/api
- What it's used for: Fetches live game data (population, field offices, doodles, sillymeter, invasions)
- SDK/Client: Custom TTRApiClient in `Features/Core/ttr_api/ttr_api.py` (async wrapper around aiohttp)
- Auth: None (public endpoints, no authentication required)
- Endpoints (per `Features/Core/ttr_api/ttr_api.py` lines 19-25):
  - `/api/invasions` - Active cog invasions by department
  - `/api/population` - District populations per server
  - `/api/fieldoffices` - Active Field Office locations, difficulty, status
  - `/api/doodles` - Available doodles for purchase with trait ratings
  - `/api/sillymeter` - Silly Meter team scores and progress
- Update frequency: Every 45 seconds for information feeds; daily at 00:00 UTC for doodles
- Retry policy: 3 attempts with exponential backoff (1s, 2s, 4s) per `Features/Core/ttr_api/ttr_api.py` line 48
- Timeout: 15 seconds per request (configured at line 31)
- User-Agent: Sent from `Config.user_agent` (default "Paws Pendragon-DiscBot"); TTR API requests this header

**Discord API:**
- Service: Discord.com (gateway.discord.gg, discordapp.com)
- What it's used for: Bot client connection, slash command handling, message creation/editing, embeds
- SDK/Client: discord.py 2.3.2+
- Auth: `DISCORD_TOKEN` environment variable (required, per `Features/Core/config/config.py` line 196)
- Bot capabilities:
  - 11 slash commands (user + admin, installed as User App + Server Bot)
  - Message pinning and in-place edits (core feed update mechanism)
  - Sharding via `discord.AutoShardedClient` (for multi-guild efficiency)
  - Intents: guilds only (minimal permissions, per `bot.py` line 193)

**GitHub:**
- Service: https://github.com/ExoArcher/PawsPendragon-TTR
- What it's used for: Source code repository; auto-update mechanism
- Protocol: HTTPS (git clone, fetch, pull --ff-only)
- Auth: None required (public repo)
- Trigger: On bot startup if `AUTO_UPDATE=true` (default)
- Behavior: Fetches `origin/main`, compares with local HEAD, pulls if behind (--ff-only only; does not hard-reset)
- Restart: Clears `__pycache__` and os.execv's self to reload code (per `bot.py` lines 119-121)

## Data Storage

**Databases:**
- SQLite 3 (file-based, no server)
  - File location: `Features/Core/db/bot.db`
  - Connection: Async via aiosqlite (pool of 5 connections, per `Features/Core/db/db.py` line 23)
  - Client: aiosqlite 0.19.0+
  - Mode: WAL (Write-Ahead Logging) enabled for concurrency (`PRAGMA journal_mode=WAL`, line 107)
  - Foreign keys: Enabled (`PRAGMA foreign_keys=ON`, line 108)

**SQLite Schema (10 tables per `Features/Core/db/db.py` lines 28-81):**
1. `guild_feeds` - Guild ID, feed key (information/doodles), channel ID, message IDs JSON
2. `allowlist` - Runtime allowlist (guild IDs allowed in addition to env `GUILD_ALLOWLIST`)
3. `announcements` - Pending announcements, channel/message IDs, TTL (expires_at)
4. `maintenance_msgs` - Sticky maintenance banners per guild
5. `welcomed_users` - User IDs who've received welcome DM
6. `banned_users` - Bot-level user bans (user_id, reason, banned_at, banned_by)
7. `maintenance_mode` - Single-row table; global maintenance toggle
8. `quarantined_guilds` - Guilds paused without leaving (guild_id, message_id)
9. `blacklist` - Guild blacklist (owner_id, reason, timestamp, flagged_by_user_ids)
10. `audit_log` - Append-only log of admin actions (event_type, details, triggered_by_user_id)

**File Storage:**
- Local filesystem only
- `.env` file for persistent configuration (mutable via `update_env_var()`, `read_env_var()` in `Features/Core/config/config.py`)
- `panel_announce.txt` - Panel announcements file (checked every ~90 seconds, per `Features/Infrastructure/live_feeds/live_feeds.py` line 46)
- `teardown_log.txt` - Log of guild teardowns
- `.git/` - Git repository for auto-update

**Caching:**
- In-memory caches via `Features/Infrastructure/cache_manager.py`:
  - `QuarantinedServerid` - Set of quarantined guild IDs (hydrated from DB at startup)
  - TTR API snapshot caches (refreshed every 45 seconds in the refresh loop)
- No external cache service (e.g., Redis); all caching is in-process

## Authentication & Identity

**Auth Provider:**
- None for end users (bot is public; commands available to all members in allowed servers)
- Discord OAuth2 implicit (bot token = single identity)

**Implementation:**
- Bot token stored in `DISCORD_TOKEN` env var, loaded by `Config.load()` in `Features/Core/config/config.py` line 196
- Admin checks via `Config.is_admin(user_id)` (line 273), which compares against `BOT_ADMIN_IDS` env var
- No user authentication; permissions delegated to Discord's "Manage Channels" / "Manage Messages" perms for admin commands

## Monitoring & Observability

**Error Tracking:**
- None (no external service)
- Errors logged to stdout via Python's stdlib `logging` module (configured in `bot.py` lines 154-158)

**Logs:**
- Output to stdout (captured by Cybrancee panel or container logs)
- Hierarchical format: `[guild][channel][thread]` prefix on log lines
- TTR API failures logged at WARNING level (line 58 in `Features/Core/ttr_api/ttr_api.py`)
- State changes logged at INFO level (e.g., guild join/leave, feed setup)

## CI/CD & Deployment

**Hosting:**
- Cybrancee Discord Bot Hosting (<https://cybrancee.com/discord-bot-hosting>) — recommended $1.49/mo plan
- Alternative: Any Linux box with Python 3.9+, persistent storage, and network access

**CI Pipeline:**
- None configured (no GitHub Actions, no automated tests triggered on push)
- Manual deployment via:
  - Upload PDMain/ to Cybrancee file manager
  - Create `.env` with real token/allowlist/admin IDs
  - Set worker command to `python3 PDMain/bot.py`
  - Click start
  - (Optional) Configure auto-update via `AUTO_UPDATE=true` in `.env`

**Auto-Update:**
- Mechanism: `git pull --ff-only` on startup (bot.py lines 47-127)
- Gate: `AUTO_UPDATE` env var (default "true")
- Behavior: Fetches origin/main, compares HEAD, pulls if behind
- Safety: Non-destructive; only fast-forwards (does not hard-reset if history diverges)
- Restart: Clears bytecode cache and os.execv's self if code changed
- Logs: Prints to stdout (captured by Cybrancee)

## Environment Configuration

**Required env vars:**
- `DISCORD_TOKEN` - Bot token (no fallback)
- `GUILD_ALLOWLIST` - Comma/space-separated guild IDs (no fallback; can be empty string)

**Secrets location:**
- `.env` file (plaintext, must not be committed to Git per .gitignore)
- Cybrancee panel file manager (UI-protected)
- Alternative: System environment variables (loaded by python-dotenv if `.env` absent)

**Env var mutation:**
- Persistent updates via `Config.update_env_var(name, value)` (used by ban/unban/quarantine commands)
- Changes written to live `.env` file in place, preserving comments
- Requires bot restart to take effect (Config is frozen at startup, per line 129 in `Features/Core/config/config.py`)

## Webhooks & Callbacks

**Incoming:**
- None (bot is listener-only; slash commands are triggered by Discord)

**Outgoing:**
- None (no custom webhooks; bot edits messages and posts embeds, no outbound HTTP calls except TTR API)

## Discord-Specific Integration Points

**Slash Commands (11 total, all in `bot.py`):**
- User commands: `/ttrinfo`, `/doodleinfo`, `/helpme`, `/invite`, `/beanfest`, `/calculate`, `/doodlesearch`
- Admin commands: `/pdsetup`, `/pdteardown`, `/pdrefresh`, `/pdboot`
- App context: User App install + Server Bot (hybrid integration types)
- Perms: Admin commands require "Manage Channels" + "Manage Messages" Discord permissions

**Background Tasks:**
- Refresh loop: `Features/Infrastructure/live_feeds/live_feeds.py` (~line 306, runs every 45 seconds via `@tasks.loop`)
  - Fetches TTR API in parallel
  - Edits pinned messages in tracked guilds
  - Rate-limits edits (3-second delays between guilds)
- Sweep loop: `bot.py` (~line 826, runs every 15 minutes)
  - Removes stale bot messages older than 24 hours
  - Tidies category structure
- Periodic checks: `Features/Infrastructure/periodic_checks.py`
  - Cross-cutting health checks

**Lifecycle Handlers:**
- `on_ready()` - Initializes DB, loads state, hydrates caches, starts background loops
- `on_guild_join()` - Validates allowlist; auto-leaves if not allowed (per `Features/Infrastructure/guild_lifecycle/guild_lifecycle.py`)
- `on_guild_remove()` - Purges guild rows from DB
- `setup_hook()` - Syncs command tree to Discord

**Embeds & Rich Content:**
- Formatters in `Features/Core/formatters/formatters.py` build Discord embeds (information, doodles, suit_calc, etc.)
- Embeds pinned and edited in-place (not posted as new messages)
- Emoji customization via env vars (jellybean, cog, safe, infinite, pendragon, gag tracks, doodle stars)

---

*Integration audit: 2026-05-07*
