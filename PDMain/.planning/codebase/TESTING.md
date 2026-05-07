# Testing Patterns

**Analysis Date:** 2026-05-07

## Test Framework

**Runner:**
- `pytest>=7.0.0` (from `requirements.txt`)
- Config: No `pytest.ini` or `pyproject.toml` detected; uses pytest defaults
- Async support via `pytest-asyncio>=0.21.0`

**Assertion Library:**
- Standard `assert` statements (built-in)
- No `unittest` — pure pytest

**Run Commands:**
```bash
pytest                    # Run all tests in tests/ directory
pytest tests/test_db.py   # Run specific test file
pytest -v                 # Verbose output
pytest -s                 # Show print statements (useful for debugging)
pytest --tb=short         # Shorter traceback format
pytest -k test_name       # Run tests matching pattern
```

**Coverage:**
- No coverage config detected (`coverage.py` not in requirements)
- No CI/CD pipeline configured (no GitHub Actions, Jenkins, or similar)
- Manual testing: Run pytest locally before committing

## Test File Organization

**Location:**
- All tests in `tests/` directory at project root: `C:\...\PDMain\tests\`
- Co-located by module being tested, not by feature directory

**Naming:**
- Test modules: `test_*.py` (pytest auto-discovery)
- Test classes: `Test*` (pytest convention)
- Test methods: `test_*` (pytest convention)

**Structure:**
```
tests/
├── __init__.py              (empty, marks directory as package)
├── conftest.py              (shared fixtures)
├── test_db.py               (database operations)
├── test_db_part_b.py        (more database tests)
├── test_formatters.py       (Discord embed formatters)
├── test_guild_lifecycle.py  (guild join/remove lifecycle)
└── test_integration.py      (integration tests)
```

## Test Structure

**Suite Organization:**
```python
class TestTraitTier:
    """Test trait_tier(trait: str, slot: int) -> str.
    
    Returns one of: 'perfect', 'amazing', 'great', 'good', 'ok', 'bad'.
    """

    def test_rarely_tired_slot_0_is_perfect(self):
        """Rarely Tired in slot 0 → perfect (max trick-uses)."""
        assert trait_tier("Rarely Tired", 0) == "perfect"

    def test_rarely_tired_slot_1_is_amazing(self):
        """Rarely Tired in slot 1 → amazing."""
        assert trait_tier("Rarely Tired", 1) == "amazing"
```

**Patterns:**
- Group tests by function/class being tested
- Class docstring explains what's being tested
- Method docstring is the specific assertion (one sentence)
- Arrange-Act-Assert (AAA) pattern within each test

**Example from `test_db.py`:**
```python
@pytest.mark.asyncio
async def test_init_creates_all_tables(self, db):
    """Verify all 8 tables exist after init_db()."""
    import aiosqlite
    
    # Arrange (fixture provides db path)
    # Act
    async with aiosqlite.connect(db) as conn:
        async with conn.execute(...) as cur:
            tables = {row[0] async for row in cur}
    
    # Assert
    expected_tables = {"guild_feeds", "allowlist", ...}
    assert expected_tables.issubset(tables)
```

## Async Testing

**Decorator:** `@pytest.mark.asyncio`
```python
@pytest.mark.asyncio
async def test_async_operation(self):
    """Test an async function."""
    result = await some_async_func()
    assert result == expected
```

**Async context managers:**
```python
@pytest.mark.asyncio
async def test_context_manager(self):
    """Test async with."""
    async with TTRApiClient(user_agent) as client:
        data = await client.population()
        assert data is not None
```

**Async fixtures:** Use `@pytest_asyncio.fixture` for setup:
```python
@pytest_asyncio.fixture
async def db():
    """Fixture providing a fresh SQLite database for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    
    await init_db(db_path)
    
    yield db_path  # Provide to test
    
    # Cleanup
    pool = db_module._pools.pop(db_path, None)
    if pool is not None:
        while not pool.empty():
            conn = pool.get_nowait()
            await conn.close()
    db_path.unlink(missing_ok=True)
```

## Mocking

**Framework:** `unittest.mock` (standard library)

**Patterns:**

```python
from unittest.mock import AsyncMock, MagicMock, patch

# Mock a simple object
mock_bot = MagicMock()
mock_bot.is_guild_allowed = MagicMock(return_value=True)

# Mock an async function
with patch('path.to.module.func') as mock_func:
    mock_func = AsyncMock(side_effect=Exception("DB failed"))
    result = await some_func_that_calls_it()

# Mock with return value
@patch('Features.Infrastructure.guild_lifecycle.guild_lifecycle.db')
async def test_with_mocked_db(mock_db):
    mock_db.add_guild_to_allowlist = AsyncMock()
    # ...
```

**Example from `test_guild_lifecycle.py`:**
```python
with patch('Features.Infrastructure.guild_lifecycle.guild_lifecycle.db') as mock_db:
    mock_db.add_guild_to_allowlist = AsyncMock(
        side_effect=Exception("DB connection failed")
    )
    
    result = await manager._add_guild_to_allowlist_atomic(guild_id, db)
    
    assert result is False
    assert guild_id not in cache_manager.GUILD_ALLOWLIST
```

**What to Mock:**
- External services: TTR API, Discord API
- Database layer when testing business logic
- Filesystem operations
- Time-dependent code (e.g., `time.time()` → use `patch('time.time')`)

**What NOT to Mock:**
- Core domain functions (test them with real data)
- Pure functions (trait_tier, doodle_priority, formatters)
- Database schema/migration code (test against real SQLite)

## Fixtures and Factories

**Test Data:**

For database tests, use `pytest_asyncio.fixture` to provide fresh databases:
```python
@pytest_asyncio.fixture
async def db():
    """Fixture providing a fresh SQLite database for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    await init_db(db_path)
    yield db_path
    db_path.unlink(missing_ok=True)
```

For mocks, use `MagicMock` fixtures:
```python
@pytest_asyncio.fixture
def mock_bot():
    """Fixture providing a mock Discord bot."""
    bot = MagicMock()
    bot.is_guild_allowed = MagicMock(return_value=True)
    bot.state = {}
    return bot
```

For formatters and pure functions, inline test data:
```python
def test_doodle_quality_perfect():
    """Doodles with all perfect traits score highest."""
    doodle = {
        "traits": [
            {"name": "Rarely Tired", "slot": 0},
            {"name": "Rarely Tired", "slot": 1},
            {"name": "Rarely Tired", "slot": 2},
            {"name": "Rarely Tired", "slot": 3},
        ]
    }
    assert doodle_quality(doodle) == 100
```

**Location:**
- `conftest.py` — shared fixtures used across test files
- Same test file — test-specific fixtures
- Inline — simple test data (no need for separate factories)

## Coverage

**Requirements:** None enforced (no coverage.py in dependencies)

**View Coverage:**
```bash
pip install coverage
coverage run -m pytest
coverage report
coverage html  # Generate HTML report in htmlcov/
```

**What's Tested:**
- `Features/Core/db/` — comprehensive (test_db.py, test_db_part_b.py)
- `Features/Core/formatters/` — comprehensive (test_formatters.py)
- `Features/Infrastructure/guild_lifecycle/` — selective (test_guild_lifecycle.py)
- `bot.py` — integration tests only (test_integration.py)
- Other features — minimal or none

**Gaps:**
- TTR API client (`Features/Core/ttr_api/`) — no tests (uses real API in production)
- Console commands — no tests (stdin interaction, complex to mock)
- Discord event handlers (`on_ready`, `on_guild_join`, etc.) — integration tests only
- User-facing commands — integration tests only (requires Discord.py client)

## Test Types

**Unit Tests:**
- Pure functions: `trait_tier()`, `doodle_priority()`, `doodle_quality()`, `_norm_district()`
- Single-responsibility functions with clear inputs/outputs
- No external dependencies (Discord API, TTR API, filesystem)
- Fast (< 100ms per test)
- Located in `test_formatters.py` (largest test file by count)

**Example:**
```python
def test_rarely_tired_slot_0_is_perfect(self):
    """Rarely Tired in slot 0 → perfect (max trick-uses)."""
    assert trait_tier("Rarely Tired", 0) == "perfect"
```

**Integration Tests:**
- Database operations: init, load, save, queries
- Cache + DB atomicity (guild lifecycle manager)
- Full state flow: fixture → operation → assertion
- Require real SQLite (temporary in-memory or file)
- Slower (10-1000ms per test, setup overhead)
- Located in `test_db.py`, `test_guild_lifecycle.py`

**Example:**
```python
@pytest.mark.asyncio
async def test_successful_atomic_update_caches_and_writes_db(self, manager, db):
    """On success, both cache and DB should be updated."""
    guild_id = 987654321
    
    # Clear cache
    cache_manager.GUILD_ALLOWLIST.clear()
    assert guild_id not in cache_manager.GUILD_ALLOWLIST
    
    # Verify guild is not in DB yet
    before = await load_allowlist(db)
    assert guild_id not in before
    
    # Call the atomic function
    result = await manager._add_guild_to_allowlist_atomic(guild_id, db)
    
    # Assertions
    assert result is True
    assert guild_id in cache_manager.GUILD_ALLOWLIST
```

**E2E Tests:**
- Not automated (manual testing on Cybrancee panel or local Discord)
- Run via `/pdsetup`, `/pdrefresh`, `/ttrinfo` commands in live guild
- Verify message posting, editing, cleanup across Discord servers
- No test files for E2E (would require Discord bot account + test guild)

## Error Testing

**Pattern for testing exceptions:**
```python
import pytest

def test_trait_tier_unknown_trait_defaults_to_ok():
    """Unknown traits fall back to 'ok' tier."""
    result = trait_tier("NewUnknownTrait", 0)
    assert result == "ok"

@pytest.mark.asyncio
async def test_db_write_failure_prevents_cache_update(self, manager, db):
    """Cache should NOT be updated if DB write fails."""
    guild_id = 123456789
    
    cache_manager.GUILD_ALLOWLIST.clear()
    assert guild_id not in cache_manager.GUILD_ALLOWLIST
    
    # Mock db failure
    with patch('Features.Infrastructure.guild_lifecycle.guild_lifecycle.db') as mock_db:
        mock_db.add_guild_to_allowlist = AsyncMock(
            side_effect=Exception("DB connection failed")
        )
        
        # Should handle gracefully
        result = await manager._add_guild_to_allowlist_atomic(guild_id, db)
        
        # Verify atomicity
        assert result is False
        assert guild_id not in cache_manager.GUILD_ALLOWLIST
```

## Common Test Patterns

**Setup and Teardown:**
- Use fixtures (`@pytest_asyncio.fixture` or `@pytest.fixture`)
- `yield` for cleanup (no separate `setup_method` / `teardown_method`)

**Database cleanup:**
```python
@pytest_asyncio.fixture
async def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    
    await init_db(db_path)
    
    yield db_path
    
    # Cleanup: close pooled connections (important on Windows)
    pool = db_module._pools.pop(db_path, None)
    if pool is not None:
        while not pool.empty():
            conn = pool.get_nowait()
            await conn.close()
    
    db_path.unlink(missing_ok=True)
```

**Mocking time:**
```python
@patch('time.time')
def test_announcement_expiration(mock_time):
    """Announcements expire after TTL."""
    mock_time.return_value = 1000.0
    
    # ... create announcement with expiry = 1000 + TTL
    
    mock_time.return_value = 1000 + ANNOUNCEMENT_TTL + 1
    # ... verify announcement is marked expired
```

## Test Organization by Module

**`test_formatters.py` (250+ tests):**
- `TestTraitTier` — 6 basic + 4 per trait set (50+ tests)
- `TestDoodlePriority` — classify doodles by quality
- `TestDoodleQuality` — compute quality score
- `TestStarFor` — emoji mapping
- `TestDistrictHelpers` — normalization, safe/speedchat sets
- `TestTimestamp` — timestamp formatting

**`test_db.py` (20+ tests):**
- `TestInitDb` — schema creation, idempotency, column verification
- `TestStateLoadSave` — guild feeds, allowlist, announcements, maintenance
- `TestWelcomedUsers` — user tracking
- `TestBannedUsers` — ban/unban operations
- `TestAuditLog` — audit event logging

**`test_db_part_b.py` (10+ tests):**
- `TestBlacklistOperations` — guild blacklist add/remove/list
- `TestMaintenanceModeOperations` — maintenance mode persistence
- `TestAuditLogQueries` — audit log filtering by type/guild/timestamp

**`test_guild_lifecycle.py` (5+ tests):**
- `TestAtomicGuildJoinAddition` — cache + DB atomicity
- Mocks TTRBot, Config, discord.Guild
- Verifies cache stays consistent with DB writes

**`test_integration.py`:**
- Full workflow tests (if any; not extensively detailed)
- May test command execution flow

---

*Testing analysis: 2026-05-07*
