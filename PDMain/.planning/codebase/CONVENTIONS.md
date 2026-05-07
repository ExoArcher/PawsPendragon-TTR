# Coding Conventions

**Analysis Date:** 2026-05-07

## Naming Patterns

**Files:**
- Lowercase with underscores: `ttr_api.py`, `guild_lifecycle.py`, `cache_manager.py`
- Feature directories use underscores: `pd_setup/`, `user_system/`, `live_feeds/`
- Entry point: `bot.py` (main TTRBot class)
- Test files: `test_*.py` (pytest convention)

**Functions:**
- Snake case: `init_db()`, `load_state()`, `format_doodles()`, `trait_tier()`
- Private/internal functions prefixed with underscore: `_empty_state()`, `_guild_state()`, `_norm_district()`
- Async functions use async/await: `async def setup_hook()`, `async def on_ready()`
- Getter/setter convention: `load_*()`, `save_*()`, `add_*()`, `remove_*()`

**Variables:**
- Snake case: `guild_id`, `channel_id`, `message_ids`, `refresh_interval`
- Constants in UPPER_SNAKE_CASE: `GUILD_ALLOWLIST`, `STATE_VERSION`, `ANNOUNCEMENT_TTL_SECONDS`, `DOODLE_REFRESH_INTERVAL`
- Private module-level variables prefixed with underscore: `_pools`, `_POOL_SIZE`, `_SCHEMA`, `_AUTO_UPDATE`
- Dictionary keys as lowercase strings: `"guild_id"`, `"feed_key"`, `"channel_id"`

**Types:**
- Type hints on function signatures: `async def init_db(path: Path = DB_PATH) -> None:`
- Union types: `dict[str, Any] | None`, `asyncio.Queue[str] | None`
- Generic types: `list[int]`, `set[str]`, `dict[str, Any]`
- Frozen dataclass for Config: `@dataclass(frozen=True)`

**Classes:**
- PascalCase: `TTRBot`, `TTRApiClient`, `LiveFeedsFeature`, `GuildLifecycleManager`
- Mixins suffix with `Feature`: `LiveFeedsFeature`
- Exception classes: Inherit from base exceptions (standard Python)

## Code Style

**Formatting:**
- Line length: No strict enforcement visible; code ranges from 80-120 characters
- Indentation: 4 spaces (Python standard)
- Imports: `from __future__ import annotations` at top of files (3.9+ compatibility)
- Module docstrings: Triple-quoted, describe purpose and sections/features

**Linting:**
- No `.eslintrc` or `.pylintrc` detected — no enforced linter
- Code uses type hints throughout (enables mypy-style checking without running it)
- No Black, Prettier, or isort config files — manual style adherence

**String formatting:**
- F-strings preferred: `f"[auto-update] Updated {_local[:7]} -> {_remote[:7]}."`
- Positional arguments to logging: `log.info("[db] Schema ready at %s (pool=%d)", path.name, _POOL_SIZE)`
- Log message prefixes in brackets: `"[auto-update]"`, `"[db]"`, `"[Commands]"`

## Import Organization

**Order:**
1. `from __future__ import annotations` (module compatibility)
2. Standard library: `asyncio`, `logging`, `json`, `os`, `sys`, `time`, `pathlib.Path`
3. Third-party: `discord`, `discord.ext.tasks`, `aiohttp`, `aiosqlite`, `python-dotenv`
4. Local Features: `from Features.Core.db import db`, `from Features.Infrastructure import cache_manager`
5. Relative imports: Within feature modules, use absolute paths from project root

**Path Aliases:**
- Always absolute from project root: `from Features.Core.config.config import Config`
- No relative imports like `from . import ...` (unless within the same feature)
- Project root is added to sys.path in `bot.py` line 59: `sys.path.insert(0, _BOT_DIR)`

**Examples:**
```python
# Good
from Features.Core.db import db
from Features.Core.db.db import init_db, load_state, save_state
from Features.Core.config.config import Config
from Features.Infrastructure import cache_manager
from Features.User.calculate.calculate import register_calculate

# Avoid
from . import db  # Only if in same package
import bot  # Use absolute paths
```

## Error Handling

**Patterns:**
- Broad exception catching with logging for external I/O:
  ```python
  except (aiohttp.ClientError, asyncio.TimeoutError) as e:
      log.warning("TTR API failed after %d attempts for %s: %s", retries, url, e)
  ```
- Retry logic with exponential backoff (TTR API):
  ```python
  for attempt in range(retries):
      try:
          return await resp.json(content_type=None)
      except (...) as e:
          if attempt < retries - 1:
              delay = base_delay * (2 ** attempt)  # 1s, 2s, 4s
              await asyncio.sleep(delay)
  ```
- Graceful degradation: Return `None` on API failure, not raising
- Database operations wrapped in `async with _db_conn()` context manager for rollback
- Config validation on startup: `RuntimeError` for missing required env vars

**What NOT to do:**
- No bare `except:` clauses
- No silent failures — always log before returning None/empty
- No `time.sleep()` — use `asyncio.sleep()` in async context
- No blocking I/O on event loop

## Logging

**Framework:** Python's stdlib `logging` module

**Pattern:**
- Named loggers: `log = logging.getLogger(__name__)` or `log = logging.getLogger("ttr-bot.db")`
- Hierarchical: `"ttr-bot"` is root, `"ttr-bot.db"` is specific module
- Prefix with brackets for context: `log.info("[guild 123456] Feed updated")`
- Levels:
  - `log.info()` — normal operation milestones (`"[db] Schema ready"`)
  - `log.warning()` — degraded but recoverable (`"TTR API failed after retries"`)
  - `log.debug()` — not used in production (enable selectively)

**Standard prefixes:**
- `[auto-update]` — GitHub self-update bootstrap
- `[db]` — database operations
- `[Commands]` — slash command registration
- `[guild {id}]` — guild-specific operations
- `[{guild}][{channel}]` — channel-specific operations

**Setup:** `bot.py` line 154-158:
```python
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
```

## Comments

**When to Comment:**
- Explain WHY, not WHAT (code reads as WHAT)
- Algorithm choices and gotchas: `# Use --ff-only to safely merge only if fast-forward is possible`
- Non-obvious Discord.py patterns: `# Commands are global and only need to be synced once after changes`
- Warnings about state/side-effects: `# Set by Console 'stop' so close() skips its own duplicate broadcast.`

**JSDoc/TSDoc:**
- Module docstrings: Describe file purpose and section breakdown
  ```python
  """Async client for the Toontown Rewritten public APIs.
  
  Docs: https://github.com/toontown-rewritten/api-doc
  Only uses the *public* endpoints (no auth). The Local/Companion-app API
  and Login API are intentionally out of scope for a server-wide bot.
  """
  ```
- Function docstrings: One-liner for simple functions, detailed for complex logic
  ```python
  async def _get(self, url: str, *, retries: int = 3, base_delay: float = 1.0) -> dict[str, Any] | None:
      """Fetch URL with exponential backoff retry. Returns None on all failures."""
  ```

## Function Design

**Size:** Functions stay focused. Helper functions are small (5-30 lines); public functions may be 50-100 lines with clear sections.

**Parameters:**
- Positional for required args: `async def init_db(path: Path = DB_PATH)`
- Keyword-only for optional/configurable: `async def _get(url: str, *, retries: int = 3, base_delay: float = 1.0)`
- Type hints mandatory on all parameters: `guild_id: int`, `path: Path`, `retries: int = 3`

**Return Values:**
- Explicit `-> ReturnType` on all functions
- Use `None` for no return value: `async def setup_hook(self) -> None:`
- Optional returns named clearly: `dict[str, Any] | None` (not just `Optional`)
- Async context managers return `self`: `async def __aenter__(self) -> "TTRApiClient":`

**Examples from codebase:**
```python
def trait_tier(trait: str, slot: int) -> str:
    """Tier for a trait at a given slot (0..3)."""
    
def _norm_district(name: str) -> str:
    """Normalize district name for set lookups."""

async def load_state(path: Path = DB_PATH) -> dict[str, Any]:
    """Load bot state from database."""

async def _db_conn(path: Path = DB_PATH) -> AsyncGenerator[aiosqlite.Connection, None]:
    """Yield a pooled connection; roll back and re-raise on exception."""
```

## Module Design

**Exports:**
- Public API functions/classes at top level of module
- Internal helpers prefixed with underscore: `_empty_state()`, `_migrate_guild_id_types()`
- Modules own their state — no cross-module direct mutation

**Barrel Files (re-exports):**
- `Features/__init__.py` typically empty or minimal
- Import from specific submodules: `from Features.Core.db import db`, not `from Features import db`

**Module docstring format:**
```python
"""Brief description.

Longer description with sections:
  - Section 1: what it does
  - Section 2: how to use it
"""
```

## Discord.py Conventions

**Intents:**
- Minimal required: `intents.guilds = True` (bot.py line 192)
- `discord.AutoShardedClient` for multi-guild scaling

**Slash commands:**
- Registered via `app_commands.CommandTree`
- Handler methods in `TTRBot` class or delegated to feature modules
- Sync via `python sync_commands.py` (not on every restart)
- Error handling with `try/except` → user-visible error messages

**Embeds:**
- Built by formatter functions in `Features/Core/formatters/`
- Maximum 6000 chars per embed, 1024 per field
- Color: `0x4ca1ff` (TTR blue)
- Footers: Bot name + timestamp

**Message handling:**
- Always edit in-place (known message ID from DB)
- Never bulk-edit; single edit operations
- Track message IDs in `guild_feeds` table: `(guild_id, feed_key) → [message_id1, message_id2]`

**Rate limiting:**
- 3-second sleep between guild refreshes
- 10-minute cooldown per user on `/pdrefresh`
- 12-hour throttle on doodle reposts

---

*Convention analysis: 2026-05-07*
