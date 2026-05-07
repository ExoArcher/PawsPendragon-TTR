<!-- refreshed: 2026-05-07 -->
# Architecture

**Analysis Date:** 2026-05-07

## System Overview

```text
┌─────────────────────────────────────────────────────────────────────┐
│                      Discord.py AutoShardedClient                   │
│                    (TTRBot extends LiveFeedsFeature)                │
├──────────────────────────┬──────────────────────┬──────────────────┤
│    Slash Commands        │  Background Tasks    │  User System     │
│  (11 user + admin)       │  (refresh + sweep)   │  (bans + welcome)│
│                          │                      │                  │
│  - /ttrinfo              │  • _refresh_loop     │  • _maybe_welcome│
│  - /doodleinfo           │  • _sweep_loop       │  • _reject_if_   │
│  - /calculate            │  • periodic_checks   │    banned        │
│  - /doodlesearch         │  • audit cleanup     │                  │
│  - /helpme               │                      │                  │
│  - /invite               │                      │                  │
│  - /beanfest             │                      │                  │
│  - /pdsetup (admin)      │                      │                  │
│  - /pdrefresh (admin)    │                      │                  │
│  - /pdteardown (admin)   │                      │                  │
│  - /pdboot (admin)       │                      │                  │
└──────────────────────────┴──────────────────────┴──────────────────┘
         │                              │                    │
         ▼                              ▼                    ▼
┌────────────────────────────────────────────────────────────────────┐
│                       Core Services Layer                           │
├────────────────────────────────────────────────────────────────────┤
│  Configuration     Persistence   API Client      Formatters         │
│  `config/`         `db/`         `ttr_api/`      `formatters/`     │
│                                                                     │
│  • Config         • SQLite       • TTR API       • Embeds          │
│  • Constants        (10 tables)    (5 endpoints)  (info, doodles,  │
│                    • State         • Caching      silly, calc)      │
│                      JSON/SQL                                       │
└────────────────────────────────────────────────────────────────────┘
         │                    │                        │
         ▼                    ▼                        ▼
┌────────────────────────────────────────────────────────────────────┐
│                    Infrastructure Layer                             │
├─────────────┬──────────────┬─────────────┬────────────┬────────────┤
│  Guild      │  Live Feeds  │  Message    │ Cache      │ Periodic   │
│  Lifecycle  │  (mixin)     │  Sweep      │ Manager    │ Checks     │
│             │              │             │            │            │
│ `guild_     │ `live_feeds` │ `message_   │ `cache_    │ `periodic_ │
│  lifecycle` │              │  sweep`     │  manager`  │  checks`   │
│             │              │             │            │            │
│ • join/     │ • 120s       │ • 15min     │ • Guild    │ • Health   │
│   leave     │   refresh    │   sweep     │   allowed  │   checks   │
│ • allow/    │ • Feed       │ • Stale     │   list     │ • Status   │
│   deny      │   updates    │   deletion  │ • Banned   │   monitors │
│ • cleanup   │ • API        │             │   users    │            │
│             │   caching    │             │            │            │
└─────────────┴──────────────┴─────────────┴────────────┴────────────┘
         │                    │
         └────────────┬───────┘
                      ▼
┌────────────────────────────────────────────────────────────────────┐
│                      Discord API Layer                              │
│                      (discord.py 2.0+)                              │
│                                                                     │
│  • Guild join/remove events    • Message edit/delete               │
│  • Thread creation/deletion    • User DMs                          │
│  • Reaction handling           • Embed rendering                   │
└────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌────────────────────────────────────────────────────────────────────┐
│                   External Services                                 │
│                                                                     │
│  • TTR Public API (population, field offices, doodles, sillymeter) │
│  • GitHub (auto-update via git pull on startup)                   │
│  • SQLite (local persistence)                                      │
└────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| **TTRBot** | Main bot class, command registration, state management, lifecycle | `bot.py` |
| **LiveFeedsFeature** | Background refresh loop, feed dispatch, quarantine logic | `Features/Infrastructure/live_feeds/live_feeds.py` |
| **GuildLifecycleManager** | Guild join/leave, allowlist enforcement, state cleanup | `Features/Infrastructure/guild_lifecycle/guild_lifecycle.py` |
| **Config** | Frozen dataclass for all environment configuration | `Features/Core/config/config.py` |
| **Database** | SQLite persistence (10 tables), async pool, state migration | `Features/Core/db/db.py` |
| **TTRApiClient** | HTTP client for 5 TTR API endpoints, request caching | `Features/Core/ttr_api/ttr_api.py` |
| **Formatters** | Embed builders (information, doodles, sillymeter, suit calculator) | `Features/Core/formatters/formatters.py` |
| **Cache Manager** | In-memory caches for allowlists, banned users, quarantined guilds | `Features/Infrastructure/cache_manager.py` |
| **Periodic Checks** | Health checks and status monitors | `Features/Infrastructure/periodic_checks.py` |
| **User Commands** | `/ttrinfo`, `/doodleinfo`, `/doodlesearch`, `/calculate`, `/helpme`, `/invite`, `/beanfest` | `Features/User/` |
| **Admin Commands** | `/pdsetup`, `/pdrefresh`, `/pdteardown`, `/pdboot` | `Features/Admin/` |
| **Console Commands** | stdin dispatcher for admin operations (announce, ban, quarantine, etc.) | `Features/ServerManagement/console_commands/` |

## Pattern Overview

**Overall:** Mixin-based modular architecture with feature isolation and centralized state management.

**Key Characteristics:**
- **Mixin pattern** — `TTRBot` inherits from `LiveFeedsFeature` to add background feed logic without inflating bot.py
- **Single entry point** — `bot.py` ~1537 lines contains main bot class, slash command registration, lifecycle handlers
- **Feature modules** — Organized under `Features/<category>/<module>/` with clear ownership boundaries
- **Centralized persistence** — All state flows through `Features/Core/db/db.py` (SQLite async pool)
- **Async-first** — No blocking I/O; `aiosqlite` for DB, `aiohttp` for HTTP, `discord.py` event loop
- **Configuration as frozen dataclass** — `Config.load()` at startup; no runtime mutations after initialization

## Layers

**Bot & Command Layer:**
- Purpose: Discord command handling, user interaction dispatch, bot lifecycle
- Location: `bot.py`
- Contains: `TTRBot` class, slash command registration, event handlers (`on_ready`, `on_guild_join`, `on_guild_remove`)
- Depends on: `Config`, `TTRApiClient`, `LiveFeedsFeature` (mixin)
- Used by: Discord.py client event loop

**Feature Layer:**
- Purpose: Isolated feature modules (User commands, Admin commands, Infrastructure)
- Location: `Features/<category>/<module>/`
- Contains: Command handlers, background tasks, specialized logic
- Depends on: Core services (DB, API, formatters), each other rarely
- Used by: Bot command registration, lifecycle managers

**Infrastructure Layer:**
- Purpose: Cross-cutting concerns (lifecycle, feeds, sweeping, caching, monitoring)
- Location: `Features/Infrastructure/`
- Contains: Background tasks, state management, quota management, monitoring
- Depends on: Core services, DB
- Used by: Bot lifecycle, Feature modules

**Core Services Layer:**
- Purpose: Shared capabilities (config, persistence, API, formatting)
- Location: `Features/Core/`
- Contains: Configuration loader, SQLite pool, TTR HTTP client, embed builders
- Depends on: External libraries only (`aiosqlite`, `aiohttp`, `discord.py`)
- Used by: All layers above

## Data Flow

### Primary Request Path (Slash Command)

1. **User invokes `/ttrinfo`** — Discord delivers `Interaction` to bot
2. **Command handler** (`bot.py` ~line 1131) — Defers response, checks ban status
3. **API fetch** — Calls `TTRApiClient.fetch()` for `population`, `fieldoffices`, `sillymeter`
4. **Format embeds** — `format_information()` and `format_sillymeter()` build Discord embeds
5. **Send DM** — `interaction.user.send(embed=...)` delivers to user's DMs
6. **Ephemeral response** — `interaction.followup.send()` shows confirmation in channel (only invoker sees)

**File locations:**
- `bot.py:1131` — `/ttrinfo` command registration and handler
- `Features/Core/ttr_api/ttr_api.py:fetch()` — HTTP fetch + caching
- `Features/Core/formatters/formatters.py` — Embed builders

### Background Refresh Loop (LiveFeedsFeature)

1. **Every 120 seconds** — `_refresh_loop()` wakes up (`Features/Infrastructure/live_feeds/live_feeds.py:306`)
2. **Fetch all endpoints** — `_fetch_all()` fetches 4 TTR APIs in parallel (`asyncio.gather`)
3. **For each allowed guild** — Skip quarantined, iterate state guilds
4. **For each feed** — Load stored channel + message IDs from state
5. **Validate message** — `channel.fetch_message(msg_id)` or send fresh message
6. **Edit in place** — `message.edit(embed=new_embed)` with fresh TTR data
7. **Persist state** — `_save_state()` writes to SQLite via `db.save_state()`
8. **Rate limit** — 3-second sleep between consecutive guild edits

**File locations:**
- `Features/Infrastructure/live_feeds/live_feeds.py` — All feed logic
- `Features/Core/db/db.py` — State save/load
- `Features/Core/formatters/formatters.py` — Embed builders

### Guild Join Event

1. **Discord notifies bot** — `on_guild_join()` fires
2. **Guild lifecycle manager** — Calls `GuildLifecycleManager.on_guild_join()`
3. **Check allowlist** — Is guild ID in `effective_allowlist()` (env + DB)?
4. **If disallowed** — DM owner with closed-access message, leave guild
5. **If allowed** — Log join, continue

**File locations:**
- `bot.py:365` — `on_guild_join` handler
- `Features/Infrastructure/guild_lifecycle/guild_lifecycle.py` — Lifecycle logic

### Guild Leave Event

1. **Discord notifies bot** — `on_guild_remove()` fires
2. **Guild lifecycle manager** — Calls `GuildLifecycleManager.on_guild_remove()`
3. **Purge state** — Delete all guild-keyed rows from state dict
4. **Persist** — `_save_state()` writes to SQLite
5. **Log** — Record departure

**File locations:**
- `bot.py:368` — `on_guild_remove` handler
- `Features/Infrastructure/guild_lifecycle/guild_lifecycle.py` — Lifecycle logic

### Setup Path (`/pdsetup`)

1. **Admin invokes `/pdsetup`** — `pdsetup()` command handler in `bot.py`
2. **Create category** — Find or create "PendragonTTR" category via Discord API
3. **Create channels** — Ensure 3 text channels exist (`tt-info`, `tt-doodles`, `suit-calc`)
4. **Create faction threads** — 4 suit calculator threads under `suit-calc`
5. **Post placeholders** — Send initial embeds to each channel, pin them
6. **Store message IDs** — Save channel + message IDs to `state["guilds"][guild_id]`
7. **Persist** — `_save_state()` to SQLite

**File locations:**
- `bot.py:1214` — `/pdsetup` command registration
- `Features/Admin/pd_setup/pd_setup.py` — Setup logic

**State Management:**
- In-memory `self.state` (dict) — Mirrors SQLite `guild_feeds`, `allowlist`, `announcements` tables
- Loaded at startup — `on_ready()` calls `db.load_state()`
- Saved on mutation — Every state change calls `_save_state()` → `db.save_state()`
- Per-guild structure — `state["guilds"][guild_id] = {"feed_key": {"channel_id": X, "message_ids": [Y, Z]}}`

## Key Abstractions

**Feed Key:**
- Purpose: Uniquely identifies a live feed type within a guild
- Examples: `"information"`, `"doodles"`, `"suit_calculator"`, `"suit_threads.sellbot"`
- Pattern: Used as dict key in `state["guilds"][guild_id][feed_key]`

**Live Feed Message:**
- Purpose: A Discord message whose embed is edited in place every refresh
- Examples: The pinned message in `#tt-info` that shows population, the doodle listing in `#tt-doodles`
- Pattern: Stored as `(channel_id, [message_ids])` in state; refresh loop fetches and edits by ID

**Guild State Entry:**
- Purpose: Tracks all feeds and threads for one guild
- Structure: `{"feed_key": {"channel_id": int, "message_ids": [int]}, ...}`
- Pattern: Loaded into memory, mutated in-place, persisted to SQLite

**Quarantine Set:**
- Purpose: In-memory cache of guilds whose feeds are paused (no feed updates)
- Location: `Features/Infrastructure/cache_manager.py` (loaded at startup from DB)
- Pattern: Checked in refresh loop; prevents feed updates without leaving guild

**Allowlist:**
- Purpose: Union of environment `GUILD_ALLOWLIST` and runtime allowlist from DB
- Pattern: Checked at guild join; non-allowlisted guilds auto-leave; commands refuse to work

## Entry Points

**Main Entry Point:**
- Location: `bot.py:1525-1532` (`main()` function)
- Triggers: `python bot.py` or `bot.py __main__`
- Responsibilities:
  1. Load config from `.env` (or hardcoded paths)
  2. Construct `TTRBot` instance with config
  3. Call `bot.run(token)` to connect to Discord

**on_ready Event:**
- Location: `bot.py:298`
- Triggers: After Discord connection is established (on startup or reconnect)
- Responsibilities:
  1. Initialize DB and load state from SQLite
  2. Create TTRApiClient and warm up HTTP session
  3. Register all slash commands to Discord
  4. Validate formatters config
  5. Start guild lifecycle manager
  6. Clean up stale maintenance messages and announcements
  7. Validate stored message IDs and clear stale ones
  8. Load caches from DB
  9. Start background tasks (refresh loop, sweep loop, periodic checks)

**on_guild_join Event:**
- Location: `bot.py:365`
- Triggers: Bot added to a new guild
- Responsibilities: Delegate to `GuildLifecycleManager.on_guild_join()`

**on_guild_remove Event:**
- Location: `bot.py:368`
- Triggers: Bot removed from a guild (or removed itself)
- Responsibilities: Delegate to `GuildLifecycleManager.on_guild_remove()` to purge state

## Architectural Constraints

- **Threading:** Single-threaded event loop (discord.py standard). Background tasks are scheduled on the same loop; no worker threads.
- **Global state:** `self.state` (in-memory dict) + SQLite DB (one async pool). Mutations must be atomic via `_state_lock` and `_refresh_lock`.
- **Circular imports:** Minimal risk; feature modules import from Core, Core has no cross-feature dependencies. Console commands import from features but are only loaded after all features.
- **Config immutability:** `Config` is frozen after `Config.load()`. Runtime mutations to env vars (e.g., ban/quarantine) are written to `.env` file, not to Config object.
- **API rate limiting:** TTR APIs have no documented rate limit, but refresh loop sleeps 3 seconds between guild edits and 120 seconds between full cycles. User commands cache the last API fetch snapshot to avoid redundant calls.
- **Message ID storage:** All feed message IDs stored in state and persisted to SQLite. On startup, stale IDs are cleared via `_validate_message_ids()`.

## Anti-Patterns

### Reaching Across Module Boundaries for State

**What happens:** A feature module directly accesses another feature's state dict (e.g., `bot.state["guilds"][guild_id]["some_internal_key"]` from User module).

**Why it's wrong:** Creates hidden dependencies, breaks encapsulation. If the state structure changes, multiple modules break.

**Do this instead:** Define a public API method on `TTRBot` (e.g., `bot._state_message_ids(guild_id, key)` at `bot.py:226`) and call it. State mutations go through `_set_state()` or module-specific methods.

**Example (correct):**
```python
# bot.py (TTRBot class)
def _state_message_ids(self, guild_id: int, key: str) -> list[int]:
    entry = self._guild_state(guild_id).get(key, {}) or {}
    ids = entry.get("message_ids")
    if isinstance(ids, list) and ids:
        return [int(i) for i in ids if isinstance(i, (int, str))]
    return []

# In a feature module:
msg_ids = bot._state_message_ids(guild_id, "information")  # ✓ Correct
```

### Blocking I/O on Event Loop

**What happens:** Code uses `time.sleep()`, synchronous file I/O, or `requests.get()` inside an async handler.

**Why it's wrong:** Freezes the entire event loop; all commands/tasks stall until the sleep completes.

**Do this instead:** Use `await asyncio.sleep()`, `aiosqlite` for DB, `aiohttp` for HTTP.

**File locations to watch:** `Features/Core/db/db.py` (uses `aiosqlite`), `Features/Core/ttr_api/ttr_api.py` (uses `aiohttp`).

### Mutating Config After Load

**What happens:** Code tries to change `bot.config.token = "new_token"` at runtime.

**Why it's wrong:** Config is frozen (`@dataclass(frozen=True)`), so this raises `FrozenInstanceError`. Also, settings should not change mid-flight.

**Do this instead:** If a setting needs to change at runtime, store it in a DB table (e.g., `maintenance_mode` table) and check it at decision points. Or restart the bot.

**Example:** `maintenance_mode` toggling is handled via `db.toggle_maintenance_mode()` in the console commands, not by mutating Config.

### Unprotected Concurrent State Mutations

**What happens:** Two async tasks mutate `self.state` simultaneously without locking, causing race conditions or corrupted state.

**Why it's wrong:** `dict` is not thread-safe in Python. Concurrent writes to nested dicts can lose data.

**Do this instead:** Always acquire `self._state_lock` before mutating and calling `_save_state()`.

**Example (correct):**
```python
async def _save_state(self) -> None:
    async with self._state_lock:
        await db.save_state(self.state)
```

---

*Architecture analysis: 2026-05-07*
