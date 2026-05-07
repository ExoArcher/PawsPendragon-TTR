# Technology Stack

**Analysis Date:** 2026-05-07

## Languages

**Primary:**
- Python 3.9+ - Entire Discord bot application (`bot.py`, `Features/`)
- SQL - SQLite schema for persistence (`Features/Core/db/db.py`)

**Secondary:**
- Markdown - Documentation (README.md, CLAUDE.md, FEATURE_SPECIFICATIONS.md)

## Runtime

**Environment:**
- Python 3.9+ (tested on 3.9+; see README.md line 7)
- Single-process, async event loop

**Package Manager:**
- pip (standard Python package manager)
- Lockfile: No lockfile present; requirements.txt pins versions

## Frameworks

**Core:**
- discord.py 2.3.2+ - Discord bot client and slash commands API
- asyncio - Python async/await standard library (built-in, implicit in all I/O)

**HTTP Client:**
- aiohttp 3.9.0+ - Async HTTP requests to TTR API (TTRApiClient in `Features/Core/ttr_api/ttr_api.py`)

**Database:**
- aiosqlite 0.19.0+ - Async SQLite wrapper (`Features/Core/db/db.py`)
  - SQLite 3 backend (no server, file-based at `Features/Core/db/bot.db`)
  - WAL mode enabled for concurrency (`PRAGMA journal_mode=WAL`)

**Configuration:**
- python-dotenv 1.0.0+ - Load `.env` file into environment variables (`Features/Core/config/config.py`)

**Testing:**
- pytest 7.0.0+ - Test framework (in requirements.txt, not yet applied to test suite)
- pytest-asyncio 0.21.0+ - Async test support (paired with pytest)

## Key Dependencies

**Critical (for runtime):**
- discord.py 2.3.2 - Without this, bot cannot connect to Discord or handle slash commands
- aiohttp 3.9.0 - Without this, TTR API endpoints cannot be reached
- aiosqlite 0.19.0 - Without this, state persistence fails; bot has no memory across restarts
- python-dotenv 1.0.0 - Without this, environment variables (bot token, guild allowlist, admin IDs) cannot be loaded

**Infrastructure:**
- discord.py's built-in tasks module - Provides `@tasks.loop` decorator for background refresh loop (`Features/Infrastructure/live_feeds/live_feeds.py` line ~306)

## Configuration

**Environment:**
- Configured via `.env` file (example template at `.env.example.template`)
- Loader probes three paths in order (per `Features/Core/config/config.py` lines 16-29):
  1. `/home/container/.env` (Cybrancee panel root)
  2. `/home/container/PDMain/.env` (Cybrancee app root)
  3. `./.env` (current working directory)

**Key configs required:**
- `DISCORD_TOKEN` - Bot token from Discord Developer Portal (required)
- `GUILD_ALLOWLIST` - Comma/space-separated guild IDs allowed to use bot (required)
- `BOT_ADMIN_IDS` - User IDs for console admin commands (optional, defaults to `310233741354336257` / ExoArcher)
- `REFRESH_INTERVAL` - Seconds between live feed refreshes (optional, default 120)
- `USER_AGENT` - String sent to TTR API (optional, default "Paws Pendragon-DiscBot")
- `CHANNEL_CATEGORY` - Discord category name (optional, default "PendragonTTR")
- `CHANNEL_INFORMATION` - Live info channel name (optional, default "tt-info")
- `CHANNEL_DOODLES` - Doodle feed channel (optional, default "tt-doodles")
- `CHANNEL_SUIT_CALCULATOR` - Calculator channel (optional, default "suit-calc")
- `AUTO_UPDATE` - Auto-update from GitHub (optional, default "true")
- `BANNED_USER_IDS` - Banned user list (optional, seeded at startup)
- `QUARANTINED_GUILD_IDS` - Quarantined guild list (optional, seeded at startup)

**Build:**
- No build step; runs Python directly
- Auto-update logic: `bot.py` lines 47-127 handle `git pull --ff-only` if `AUTO_UPDATE=true`

## Platform Requirements

**Development:**
- Python 3.9+ interpreter
- pip or venv for dependency management
- Git (for repository cloning and auto-update)
- SQLite 3 (ships with Python; no separate install needed)

**Production:**
- **Hosting:** Cybrancee Discord Bot Hosting (Linux container, 512 MB RAM recommended) or any Linux box with Python 3.9+
- **Entrypoint:** `python3 PDMain/bot.py` (per README.md line 192)
- Requires network access to:
  - Discord API (`gateway.discord.gg`, `discordapp.com`)
  - Toontown Rewritten API (`https://www.toontownrewritten.com/api`)
  - GitHub (for auto-update; uses HTTPS clone/pull)
- Persistent storage: `Features/Core/db/bot.db` (SQLite file, must be writable)

---

*Stack analysis: 2026-05-07*
