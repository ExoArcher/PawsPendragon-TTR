# Codebase Structure

**Analysis Date:** 2026-05-07

## Directory Layout

```
PDMain/
├── bot.py                              # Main bot class, entry point, slash commands (~1537 lines)
├── sync_commands.py                    # Utility to force Discord command tree sync
├── run.sh                              # Shell script wrapper for bot startup
├── Procfile                            # Heroku/Cybrancee process definition
├── runtime.txt                         # Python version specification
├── requirements.txt                    # pip dependencies
├── .env.example.template               # Template for environment configuration
├── .env.example                        # Previous env template (keep for reference)
├── state.json                          # Legacy JSON state file (migrated to SQLite on startup)
├── .gitignore                          # Git ignore rules
│
└── Features/                           # Main feature module tree
    ├── __init__.py                     # Makes Features a package
    │
    ├── Core/                           # Shared services (config, DB, API, formatters)
    │   ├── __init__.py
    │   ├── config/
    │   │   ├── __init__.py
    │   │   ├── config.py               # Config dataclass, .env loader (~200 lines)
    │   │   └── constants.py            # Constant definitions (refresh intervals, timeouts, etc.)
    │   ├── db/
    │   │   ├── __init__.py
    │   │   ├── db.py                   # SQLite schema, async pool, state migration (~500 lines)
    │   │   └── db_cache_coherence.py   # Cache invalidation helpers
    │   ├── formatters/
    │   │   ├── __init__.py
    │   │   └── formatters.py           # Embed builders (information, doodles, sillymeter, suit calc)
    │   └── ttr_api/
    │       ├── __init__.py
    │       └── ttr_api.py              # TTR HTTP client (5 endpoints + caching)
    │
    ├── Infrastructure/                 # Cross-cutting concerns (lifecycle, feeds, sweeping, monitoring)
    │   ├── __init__.py
    │   ├── live_feeds/
    │   │   ├── __init__.py
    │   │   └── live_feeds.py           # LiveFeedsFeature mixin (120s refresh loop)
    │   ├── guild_lifecycle/
    │   │   ├── __init__.py
    │   │   └── guild_lifecycle.py      # Guild join/leave + allowlist enforcement
    │   ├── message_sweep/
    │   │   ├── __init__.py
    │   │   └── message_sweep.py        # 15-min stale message cleanup
    │   ├── announcements_maintenance/
    │   │   ├── __init__.py
    │   │   └── announcements_maintenance.py  # Panel announcements and maintenance messages
    │   ├── user_system/
    │   │   ├── __init__.py
    │   │   └── user_system.py          # User ban/welcome system
    │   ├── github_autoupdate/
    │   │   ├── __init__.py
    │   │   └── github_autoupdate.py    # (Placeholder; git pull is in bot.py startup)
    │   ├── cache_manager.py            # In-memory caches (allowlists, bans, quarantine)
    │   ├── periodic_checks.py          # Health checks and status monitors
    │   ├── blacklist_removal.py        # Guild blacklist utility
    │   ├── quarantine_checks.py        # Quarantine enforcement
    │   └── unquarantine_checks.py      # Quarantine lifting
    │
    ├── User/                           # User-facing commands (11 commands total)
    │   ├── __init__.py
    │   ├── ttrinfo/
    │   │   ├── __init__.py
    │   │   └── ttrinfo.py              # /ttrinfo command (districts, invasions, field offices, sillymeter)
    │   ├── doodleinfo/
    │   │   ├── __init__.py
    │   │   └── doodleinfo.py           # /doodleinfo command (doodle trait guide)
    │   ├── doodlesearch/
    │   │   ├── __init__.py
    │   │   └── doodlesearch.py         # /doodlesearch command (search doodles by traits)
    │   ├── calculate/
    │   │   ├── __init__.py
    │   │   └── calculate.py            # /calculate command (suit promotion calculator + threads)
    │   ├── helpme/
    │   │   ├── __init__.py
    │   │   └── helpme.py               # /helpme command (available commands list)
    │   └── ttrinfo/
    │       ├── __init__.py
    │       └── ttrinfo.py              # /ttrinfo command (see ttrinfo above)
    │
    ├── Admin/                          # Admin-only commands
    │   ├── __init__.py
    │   ├── pd_setup/
    │   │   ├── __init__.py
    │   │   └── pd_setup.py             # /pdsetup command (initialize guild + channels)
    │   ├── pd_refresh/
    │   │   ├── __init__.py
    │   │   └── pd_refresh.py           # /pdrefresh command (force immediate refresh)
    │   └── pd_teardown/
    │       ├── __init__.py
    │       └── pd_teardown.py          # /pdteardown command (remove all channels + category)
    │
    └── ServerManagement/               # Console commands (stdin dispatcher)
        ├── __init__.py
        └── console_commands/
            ├── __init__.py
            └── console_commands.py     # stdin dispatcher (announce, ban, unban, quarantine, etc.)
```

## Directory Purposes

**PDMain Root:**
- Purpose: Bot source code and configuration entry point
- Contains: Main bot class, entry point script, environment templates, state file
- Key files: `bot.py` (1537 lines), `.env.example.template`, `requirements.txt`

**Features/Core/:**
- Purpose: Shared services and infrastructure components
- Contains: Configuration loader, SQLite persistence, TTR API client, embed formatters
- Key files: `config/config.py`, `db/db.py`, `ttr_api/ttr_api.py`, `formatters/formatters.py`

**Features/Infrastructure/:**
- Purpose: Cross-cutting background tasks and state management
- Contains: Live feed refresh loop (mixin), guild lifecycle management, message sweeping, caching
- Key files: `live_feeds/live_feeds.py` (mixin), `guild_lifecycle/guild_lifecycle.py`, `cache_manager.py`

**Features/User/:**
- Purpose: User-facing slash commands (non-admin)
- Contains: 7 command handlers (`ttrinfo`, `doodleinfo`, `doodlesearch`, `calculate`, `helpme`, plus 2 more in main bot)
- Key files: Individual command files under respective subdirectories
- Note: Some commands are registered directly in `bot.py` rather than imported

**Features/Admin/:**
- Purpose: Admin/server-manager slash commands
- Contains: Setup, refresh, teardown commands for guild initialization and removal
- Key files: `pd_setup/pd_setup.py`, `pd_refresh/pd_refresh.py`, `pd_teardown/pd_teardown.py`

**Features/ServerManagement/:**
- Purpose: Console command dispatcher for server operators
- Contains: stdin listener, command routing, help text
- Key files: `console_commands/console_commands.py`

## Key File Locations

**Entry Points:**
- `bot.py:1525-1532` — `main()` function, bot initialization, Discord login
- `bot.py:298-364` — `on_ready()` event handler (startup initialization, task startup)
- `bot.py:365-369` — `on_guild_join()` and `on_guild_remove()` event handlers

**Configuration:**
- `Features/Core/config/config.py` — Config dataclass, `.env` loader, env var utilities
- `Features/Core/config/constants.py` — Constant definitions (timeouts, refresh intervals, etc.)
- `.env.example.template` — Template showing all available env vars

**Core Logic:**
- `Features/Core/db/db.py` — SQLite schema (10 tables), async pool, state load/save
- `Features/Core/ttr_api/ttr_api.py` — TTR API client (5 endpoints), request caching
- `Features/Core/formatters/formatters.py` — Embed builders (called by all feed displays)

**Background Tasks:**
- `Features/Infrastructure/live_feeds/live_feeds.py:306` — `_refresh_loop()` (120s interval)
- `bot.py:939-958` — `_sweep_loop()` (15-minute interval, stale message cleanup)
- `bot.py:359-360` — `_audit_log_cleanup_loop()` (daily, audit log retention)
- `Features/Infrastructure/periodic_checks.py` — Health checks and status monitors

**Testing:**
- `tests/` — Test directory (structure TBD, see TESTING.md)

## Naming Conventions

**Files:**
- Python module files: `snake_case.py` (e.g., `pd_setup.py`, `formatters.py`)
- Feature directories: `snake_case/` (e.g., `live_feeds/`, `guild_lifecycle/`)
- Command modules named by command (e.g., `ttrinfo.py` for `/ttrinfo`)

**Directories:**
- Category folders: `PascalCase` (e.g., `Features/Admin/`, `Features/User/`, `Features/Core/`)
- Feature modules: `snake_case` (e.g., `pd_setup/`, `live_feeds/`, `guild_lifecycle/`)
- Core service types: `snake_case` (e.g., `config/`, `db/`, `formatters/`, `ttr_api/`)

**Python Identifiers:**
- Classes: `PascalCase` (e.g., `TTRBot`, `Config`, `LiveFeedsFeature`, `GuildLifecycleManager`)
- Functions/methods: `snake_case` (e.g., `_fetch_all()`, `_refresh_once()`, `_state_message_ids()`)
- Private methods: leading underscore (e.g., `_save_state()`, `_validate_api_response()`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `STATE_VERSION`, `REFRESH_INTERVAL`)

**Discord Integration:**
- Slash commands: lowercase with underscores in code, hyphens in Discord UI (e.g., `/pd-setup` shown as `/pdsetup` in command handler)
- Feed keys: lowercase (e.g., `"information"`, `"doodles"`, `"suit_calculator"`, `"suit_threads.sellbot"`)

## Where to Add New Code

**New User Command:**
1. Create `Features/User/<command_name>/` directory
2. Add `__init__.py` (empty or with exports)
3. Implement `<command_name>.py` with:
   - `<command_name>_command(bot, interaction)` — async handler function
   - `register_<command_name>(bot)` — registration function with `@bot.tree.command` decorator
4. Import and call `register_<command_name>(bot)` in `bot.py:_register_commands()`
5. Check ban status with `await bot._reject_if_banned(interaction)` if public

**Example (from `Features/User/ttrinfo/ttrinfo.py`):**
```python
async def ttrinfo_command(bot: Any, interaction: discord.Interaction) -> None:
    # Command logic here
    pass

def register_ttrinfo(bot: Any) -> None:
    @bot.tree.command(name="ttrinfo", description="...")
    @app_commands.allowed_installs(guilds=True, users=True)
    async def ttrinfo(interaction: discord.Interaction) -> None:
        await ttrinfo_command(bot, interaction)
```

**New Admin Command:**
1. Follow same pattern as User commands, place in `Features/Admin/<command_name>/`
2. Add permission checks: `@app_commands.default_permissions(manage_channels=True, manage_messages=True)` or call `bot.config.is_admin(user_id)`
3. Ensure idempotency (safe to re-run)

**New Background Task:**
1. Implement as method on `TTRBot` class (in `bot.py` or as a mixin)
2. Decorate with `@tasks.loop(seconds=interval)` from `discord.ext.tasks`
3. Add `@<method>.before_loop` to wait for bot ready
4. Call `<method>.start()` in `on_ready()` after `self.wait_until_ready()`

**Example (from `bot.py:939-958`):**
```python
@tasks.loop(minutes=15)
async def _sweep_loop(self) -> None:
    # Task logic here
    pass

@_sweep_loop.before_loop
async def _before_sweep_loop(self) -> None:
    await self.wait_until_ready()

# In on_ready():
if not self._sweep_loop.is_running():
    self._sweep_loop.start()
```

**New Formatter/Embed Type:**
1. Add function to `Features/Core/formatters/formatters.py`
2. Function signature: `def format_<type>(data: dict | None) -> discord.Embed | list[discord.Embed]`
3. Call from command handlers or refresh loop
4. Register with `@validate_config()` if it uses emoji config vars

**New Database Table:**
1. Add `CREATE TABLE IF NOT EXISTS ...` to `_SCHEMA` in `Features/Core/db/db.py`
2. Add index entries to `_CREATE_INDEXES` if querying by non-primary columns
3. Add `async def load_<table>()` and `async def save_<table>()` functions to `db.py`
4. Call from appropriate places (e.g., `on_ready()` for load, mutation handlers for save)
5. Bump `STATE_VERSION` in `bot.py` if load/save semantics change and migration is needed

**New Console Command:**
1. Implement handler in `Features/ServerManagement/console_commands/console_commands.py`
2. Add to command dispatcher routing dictionary
3. Add help text to `help_text()` function
4. Ensure async-safe (use `await` for DB/network calls)

## Special Directories

**`.planning/`:**
- Purpose: Generated by GSD codebase mapper; contains architecture/structure documentation
- Generated: Yes (by `/gsd:map-codebase`)
- Committed: No (ignored in `.gitignore`)
- Contents: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, CONCERNS.md (as generated)

**`tests/`:**
- Purpose: Test suite (unit, integration, e2e)
- Generated: No (manually created)
- Committed: Yes
- Contents: Test files following naming pattern `test_*.py` or `*_test.py`

## Module Import Patterns

**From bot.py to Features:**
```python
# Single import (preferred for large modules)
from Features.Core.db import db

# Function import
from Features.Core.formatters.formatters import format_doodles, format_information

# Class import
from Features.Infrastructure.guild_lifecycle.guild_lifecycle import GuildLifecycleManager
```

**From Features modules to Core:**
```python
# Config
from ...Core.config.config import Config
from ...Core.config.constants import REFRESH_INTERVAL

# Database
from ...Core.db import db
from ...Core.db.db import save_state, load_state

# API
from ...Core.ttr_api.ttr_api import TTRApiClient

# Formatters
from ...Core.formatters.formatters import format_doodles
```

**Between Feature modules:**
- Avoid circular imports by importing only what's needed
- If module A needs B's state/logic, go through `bot` instance (e.g., `bot._state_message_ids()`) or the DB layer
- Console commands can import from all features; they load last

**Relative imports:**
- Use `from ...Core.X` style (relative paths) within Features/ subdirectories
- Use absolute imports (`from Features.X`) in `bot.py`

---

*Structure analysis: 2026-05-07*
