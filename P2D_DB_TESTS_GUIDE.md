# P2-D Database CRUD Tests — Implementation Guide

**Phase:** P2-D (Database layer testing)  
**Target:** `PDMain/Features/Core/db/db.py` (23 CRUD functions, ~540 lines)  
**Goal:** Parametrized async pytest tests using `:memory:` SQLite (no disk I/O)  
**Expected Test Count:** ~120 tests across 12 test classes  
**Complexity:** MEDIUM (async + transactions, but pure CRUD patterns)  

---

## Test Structure Overview

### Test Classes (12 total)

| Class | Functions | Test Count |
|-------|-----------|-----------|
| `TestInitDb` | `init_db()` | ~4 |
| `TestStateLoadSave` | `load_state()`, `save_state()` | ~15 |
| `TestWelcomedUsers` | `load_welcomed()`, `add_welcomed()` | ~6 |
| `TestBannedUsers` | `get_ban()`, `load_all_banned()`, `add_ban()`, `remove_ban()`, `save_banned()` | ~22 |
| `TestAllowlist` | `add_guild_to_allowlist()`, `remove_guild_from_allowlist()`, `load_allowlist()` | ~8 |
| `TestGuildFeeds` | `delete_guild_feeds()` | ~5 |
| `TestMaintenanceMode` | `load_maint_mode()`, `save_maint_mode()` | ~8 |
| `TestQuarantinedGuilds` | `load_quarantined_guilds()`, `add_quarantined_guild()`, `remove_quarantined_guild()` | ~10 |
| `TestBlacklist` | `add_to_blacklist()`, `remove_from_blacklist()`, `get_all_blacklisted()` | ~10 |
| `TestAuditLog` | `log_audit_event()` | ~8 |
| `TestQuarantineUtils` | `remove_quarantine()`, `get_all_quarantined()` | ~6 |
| `TestMiscUtils` | `_is_fresh()`, `count_banned_users_with_dangerous_perms()` | ~8 |

**Total: ~120 test methods**

---

## Key Testing Patterns

### 1. `:memory:` SQLite Database

All tests use an in-memory SQLite database (no disk I/O):

```python
import tempfile
from pathlib import Path
import aiosqlite

@pytest.fixture
async def db():
    """Provide a fresh :memory: database for each test."""
    path = Path(":memory:")
    # Note: aiosqlite treats ":memory:" as in-memory
    # However, for concurrent tests, use a temp file instead
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    
    # Initialize schema
    from Features.Core.db.db import init_db
    await init_db(db_path)
    
    yield db_path
    
    # Cleanup
    db_path.unlink(missing_ok=True)
```

### 2. Async Test Functions

All test methods must be `async def` and use `await` for database calls:

```python
@pytest.mark.asyncio
async def test_add_welcomed_user(db):
    from Features.Core.db.db import add_welcomed, load_welcomed
    await add_welcomed(12345, db)
    result = await load_welcomed(db)
    assert 12345 in result
```

### 3. Parametrized Tests

Use `@pytest.mark.parametrize` to test multiple input combinations:

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("user_id,expected", [(1, 1), (999, 999), (0, 0)])
async def test_welcomed_user_ids(db, user_id, expected):
    from Features.Core.db.db import add_welcomed, load_welcomed
    await add_welcomed(user_id, db)
    result = await load_welcomed(db)
    assert expected in result
```

---

## Test Class Specifications

### TestInitDb (4 tests)

Test schema initialization and idempotency:

- `test_init_creates_all_tables()` — Verify all 8 tables exist after `init_db()`
- `test_init_is_idempotent()` — Call `init_db()` twice, verify no errors and schema unchanged
- `test_guild_feeds_table_structure()` — Verify `guild_feeds` table has correct columns
- `test_banned_users_table_structure()` — Verify `banned_users` table has correct columns

### TestStateLoadSave (15 tests)

Test state persistence (guild feeds, allowlist, announcements, maintenance messages):

- `test_empty_state_load()` — Load from fresh DB, verify empty state dict
- `test_save_empty_state()` — Save empty state, load, verify empty
- `test_save_and_load_guild_feeds()` — Save 1 guild with 3 feeds, load and verify structure
- `test_multiple_guilds_state()` — Save 2 guilds with different feed keys, load and verify
- `test_feed_key_suit_threads()` — Test special `suit_threads.*` feed key parsing
- `test_message_ids_json_roundtrip()` — Save message IDs as JSON, load and verify as list
- `test_save_allowlist()` — Save allowlist with 3 guild IDs, load and verify
- `test_save_announcements()` — Save 2 announcements, load and verify all fields
- `test_save_maintenance_msgs()` — Save maintenance messages, load and verify
- `test_guild_deletion_during_save()` — Save guild, then save state without it, verify deleted
- `test_invalid_feed_entries_skipped()` — Save state with non-dict feed entries, verify skipped
- `test_state_format_version()` — Verify state dict has `_version: 2` key
- `test_numeric_string_conversion()` — Verify guild IDs stored/loaded as strings
- `test_empty_message_ids_list()` — Save feed with no messages, verify empty list
- `test_save_state_atomic()` — Verify no partial writes on error

### TestWelcomedUsers (6 tests)

Test welcomed user tracking:

- `test_empty_welcomed_load()` — Load from fresh DB, verify empty set
- `test_add_single_welcomed()` — Add 1 user, load, verify in result
- `test_add_multiple_welcomed()` — Add 3 users, load, verify all present
- `test_add_duplicate_welcomed()` — Add same user twice (INSERT OR IGNORE), verify once in result
- `test_welcomed_user_types()` — Test with various user ID types (int, str)
- `test_welcomed_empty_set()` — Verify empty load returns empty set, not None

### TestBannedUsers (22 tests)

Test ban management (CRUD, bulk operations):

- `test_empty_banned_load()` — Load from fresh DB, verify empty dict
- `test_get_ban_not_found()` — Get ban for non-existent user, verify None
- `test_add_and_get_ban()` — Add ban, get it, verify all fields
- `test_get_ban_returns_dict()` — Verify get_ban() returns dict with correct keys
- `test_add_ban_idempotent()` — Add same ban twice, verify no duplicate
- `test_load_all_banned()` — Add 3 bans, load all, verify all present
- `test_ban_record_fields()` — Verify ban dict has: reason, banned_at, banned_by, banned_by_id
- `test_remove_ban_success()` — Remove existing ban, verify returns True
- `test_remove_ban_not_found()` — Remove non-existent ban, verify returns False
- `test_remove_ban_deletes_completely()` — Remove ban, verify load_all_banned() excludes it
- `test_add_ban_with_null_fields()` — Add ban with None values, load and verify
- `test_save_banned_replaces_all()` — Save dict of 2 bans, load, verify only those 2 exist
- `test_save_banned_empty()` — Save empty dict, verify all bans deleted
- `test_banned_user_id_string_conversion()` — Verify user IDs stored as strings
- `test_ban_timestamp_format()` — Verify timestamp strings persist unchanged
- `test_ban_admin_field()` — Verify "banned_by" and "banned_by_id" fields persist
- `test_multiple_bans_concurrent()` — Add 5 bans in sequence, verify all readable
- `test_ban_reason_with_special_chars()` — Store reason with quotes/newlines, verify persist
- `test_load_all_banned_returns_keyed_by_user_id()` — Verify result dict keys are user IDs
- `test_add_ban_overwrites_existing()` — Add ban, then add new record for same user, verify overwrite
- `test_remove_ban_after_save()` — Save ban dict, remove one, verify only removed one deleted
- `test_banned_users_isolation()` — Add bans, verify other tables not affected

### TestAllowlist (8 tests)

Test allowlist management:

- `test_empty_allowlist_load()` — Load from fresh DB, verify empty list
- `test_add_single_guild()` — Add 1 guild, load, verify present
- `test_add_multiple_guilds()` — Add 3 guilds, load, verify all present
- `test_add_duplicate_guild()` — Add same guild twice (INSERT OR IGNORE), verify once in result
- `test_remove_guild_success()` — Remove existing guild, verify returns True
- `test_remove_guild_not_found()` — Remove non-existent guild, verify returns False
- `test_remove_guild_actually_deletes()` — Remove guild, load, verify not in result
- `test_allowlist_guild_id_types()` — Test with int guild IDs

### TestGuildFeeds (5 tests)

Test guild feed deletion:

- `test_delete_feeds_success()` — Add feeds for guild, delete, verify returns True
- `test_delete_feeds_not_found()` — Delete feeds for non-existent guild, verify returns False
- `test_delete_feeds_only_target_guild()` — Add feeds for 2 guilds, delete for 1, verify only 1 deleted
- `test_delete_all_feeds_for_guild()` — Add multiple feed keys for 1 guild, delete, verify all gone
- `test_delete_feeds_returns_true_on_delete()` — Verify rowcount > 0 case returns True

### TestMaintenanceMode (8 tests)

Test maintenance mode tracking (guild × feed key → message ID):

- `test_empty_maint_mode_load()` — Load from fresh DB, verify empty dict
- `test_save_single_guild_feed_maint()` — Save 1 guild with 1 feed in maint, load, verify structure
- `test_maint_mode_nested_dict()` — Verify structure is {guild_id: {feed_key: message_id}}
- `test_save_multiple_guilds_feeds()` — Save 2 guilds each with 2 feeds, load, verify
- `test_save_maint_replaces_all()` — Save data, then save new data, verify only new present
- `test_maint_mode_message_id_int()` — Verify message IDs stored and returned as int
- `test_maint_mode_with_multiple_feeds_per_guild()` — 1 guild, 3 different feed keys
- `test_maint_mode_isolation()` — Save/load maint, verify other tables unaffected

### TestQuarantinedGuilds (10 tests)

Test quarantine tracking:

- `test_empty_quarantined_load()` — Load from fresh DB, verify empty dict
- `test_add_quarantined_guild()` — Add 1 quarantined guild, load, verify in result
- `test_quarantined_dict_structure()` — Verify returned dict has correct keys (guild_id, guild_name, owner_id, etc.)
- `test_load_quarantined_guilds_multiple()` — Add 2 quarantined guilds, load, verify both
- `test_remove_quarantined_success()` — Add guild, remove, verify returns True
- `test_remove_quarantined_not_found()` — Remove non-existent guild, verify returns False
- `test_quarantined_optional_fields()` — Add guild with noticed=None, feeds_halted=None, owner_notified=None
- `test_quarantined_all_fields_persist()` — Add guild with all fields, load, verify all present
- `test_add_quarantined_overwrites()` — Add guild, then add again with different reason, verify updated
- `test_quarantined_guild_id_type()` — Verify guild_id stored and returned as string

### TestBlacklist (10 tests)

Test blacklist management:

- `test_empty_blacklist_load()` — Load from fresh DB, verify empty list
- `test_add_to_blacklist()` — Add 1 guild to blacklist, get all, verify present
- `test_add_multiple_blacklist()` — Add 2 guilds, get all, verify both
- `test_blacklist_multiple_flaggers()` — Add same guild twice by different users, verify flagged_by_user_ids merged
- `test_blacklist_dedup_flaggers()` — Add same guild by same user twice, verify no duplicate user IDs
- `test_remove_from_blacklist_success()` — Add guild, remove, verify returns True
- `test_remove_from_blacklist_not_found()` — Remove non-existent, verify returns False
- `test_get_all_blacklisted_empty()` — Load from fresh DB, verify empty list
- `test_blacklist_reason_persist()` — Add with reason, get all, verify reason present
- `test_blacklist_flagged_by_parsing()` — Add guild by 3 different users, verify comma-separated parsing

### TestAuditLog (8 tests)

Test audit event logging:

- `test_log_simple_event()` — Log event with just type, verify stored
- `test_log_event_with_details()` — Log event with JSON details dict, verify stored as JSON
- `test_log_event_with_guild_id()` — Log event with guild_id, verify stored
- `test_log_event_with_user_id()` — Log event with triggered_by_user_id, verify stored
- `test_audit_log_json_serialization()` — Log event with nested dict details, verify JSON roundtrip
- `test_audit_log_details_none()` — Log event with details=None, verify stored as NULL
- `test_audit_log_multiple_events()` — Log 3 events, query, verify all present
- `test_audit_log_timestamps()` — Log event, verify timestamp is CURRENT_TIMESTAMP

### TestQuarantineUtils (6 tests)

Test quarantine utility functions:

- `test_remove_quarantine()` — Add quarantined guild, call remove_quarantine, verify deleted
- `test_remove_quarantine_not_found()` — Call on non-existent guild, verify returns False
- `test_get_all_quarantined_empty()` — Load from fresh DB, verify empty list
- `test_get_all_quarantined_multiple()` — Add 3 quarantined guilds, get all, verify all present
- `test_quarantine_utils_guild_id_int()` — Verify returned IDs are integers
- `test_quarantine_utils_isolation()` — Add quarantined + blacklisted guilds, verify get_all_quarantined() only returns quarantined

### TestMiscUtils (8 tests)

Test utility functions (_is_fresh, count_banned_users_with_dangerous_perms):

- `test_is_fresh_on_new_db()` — Fresh DB, verify _is_fresh() returns True
- `test_is_fresh_after_adding_feed()` — Add guild feed, verify _is_fresh() returns False
- `test_is_fresh_zero_guilds()` — Explicitly verify COUNT = 0 returns True
- `test_count_banned_users_empty()` — Fresh DB, verify count is 0
- `test_count_banned_users_multiple()` — Add 5 bans, verify count returns 5
- `test_count_banned_users_after_remove()` — Add 3 bans, remove 1, verify count is 2
- `test_count_includes_all_bans()` — Add bans via different functions, verify count reflects all
- `test_is_fresh_with_other_tables_populated()` — Add allowlist entries but no guild_feeds, verify _is_fresh() still True

---

## Integration Test (Bonus)

If time permits, add cross-function tests:

- `test_state_roundtrip()` — Save state, load, modify, save, load, verify consistency
- `test_ban_and_quarantine_isolation()` — Add bans and quarantined guilds, verify no cross-contamination
- `test_concurrent_table_updates()` — Update multiple tables in sequence, verify all consistent

---

## Implementation Notes

### Async Pytest Setup

Require `pytest-asyncio` in requirements.txt:

```ini
pytest>=7.0.0,<8.0
pytest-asyncio>=0.21.0,<1.0
```

Mark all test functions with `@pytest.mark.asyncio`:

```python
@pytest.mark.asyncio
async def test_example(db):
    ...
```

### Database Fixture

Use a fixture that initializes the schema:

```python
import pytest
from pathlib import Path
import tempfile

@pytest.fixture
async def db():
    """Fixture providing a fresh :memory: SQLite database."""
    from Features.Core.db.db import init_db
    
    # Create temp file for database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)
    
    # Initialize schema
    await init_db(db_path)
    
    yield db_path
    
    # Cleanup
    db_path.unlink(missing_ok=True)
```

### Key Imports

```python
import pytest
from pathlib import Path
import json
import tempfile
from datetime import datetime

# Import all db functions
from Features.Core.db.db import (
    init_db, _is_fresh,
    load_state, save_state,
    load_welcomed, add_welcomed,
    get_ban, load_all_banned, add_ban, remove_ban, save_banned,
    add_guild_to_allowlist, remove_guild_from_allowlist, load_allowlist,
    delete_guild_feeds,
    load_maint_mode, save_maint_mode,
    load_quarantined_guilds, add_quarantined_guild, remove_quarantined_guild,
    add_to_blacklist, remove_from_blacklist, get_all_blacklisted,
    log_audit_event,
    remove_quarantine, get_all_quarantined,
    count_banned_users_with_dangerous_perms,
    migrate_from_json,
)
```

---

## Success Criteria

- [ ] `PDMain/tests/test_db.py` created with 12 test classes
- [ ] ~120 parametrized async test methods
- [ ] All tests use `@pytest.mark.asyncio` decorator
- [ ] All tests use temp SQLite database (no disk state)
- [ ] Syntax valid: `python -m py_compile tests/test_db.py`
- [ ] Imports resolve: `python -c "from tests.test_db import *"`
- [ ] All ~120 tests pass: `python -m pytest tests/test_db.py -v`
- [ ] No changes to `Features/Core/db/db.py` (tests only)
- [ ] Requirements.txt already has pytest + pytest-asyncio from P2-C

---

## Verification Command

```powershell
cd PDMain
python -m pytest tests/test_db.py -v
# Expected: ~120 passed, 0 failed
```

