# Core/db Feature Briefing

## Feature Purpose
Async SQLite persistence layer replacing 5 legacy JSON files. Provides read/write functions for all bot state: guild feeds, allowlist, announcements, maintenance mode, welcomed users, and ban records. Handles one-time migration from JSON on first run.

## Scope
- Initialize SQLite database with immutable schema (7 tables)
- Load/save guild feed state (channels and message IDs per guild/feed)
- Load/save runtime allowlist (guilds added after startup)
- Load/save announcements (temporary messages with expiry)
- Load/save maintenance mode state (per guild × feed key)
- Load/save welcomed users (first-time DM recipients)
- Load/save ban records (ban info per user)
- One-time JSON → SQLite migration on first run (idempotent)

## Database Schema

```sql
CREATE TABLE IF NOT EXISTS guild_feeds (
    guild_id    TEXT    NOT NULL,
    feed_key    TEXT    NOT NULL,
    channel_id  INTEGER NOT NULL DEFAULT 0,
    message_ids TEXT    NOT NULL DEFAULT '[]',  -- JSON array
    PRIMARY KEY (guild_id, feed_key)
);

CREATE TABLE IF NOT EXISTS allowlist (
    guild_id    INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS announcements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    message_id  INTEGER NOT NULL UNIQUE,
    expires_at  REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS maintenance_msgs (
    guild_id    TEXT    PRIMARY KEY,
    message_id  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS welcomed_users (
    user_id     INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS banned_users (
    user_id     TEXT    PRIMARY KEY,
    reason      TEXT,
    banned_at   TEXT,
    banned_by   TEXT,
    banned_by_id TEXT
);

CREATE TABLE IF NOT EXISTS maintenance_mode (
    guild_id    TEXT    NOT NULL,
    feed_key    TEXT    NOT NULL,
    message_id  INTEGER NOT NULL,
    PRIMARY KEY (guild_id, feed_key)
);
```

## Code to Extract
**From Main-1.5.0/db.py (entire file, 330 lines)**
- _SCHEMA constant (SQL schema definition)
- init_db() - Create tables if missing
- load_state() - Read guild_feeds, allowlist, announcements from DB → v2 state dict
- save_state() - Write state dict atomically to DB (upsert guild_feeds, replace allowlist, etc.)
- load_welcomed() - Read welcomed_users set
- add_welcomed(user_id) - Insert user into welcomed_users
- get_ban(user_id) - Read ban record
- save_banned(banned_dict) - Replace all ban records
- load_maint_mode() - Read maintenance_mode table
- save_maint_mode(data) - Write maintenance_mode state
- migrate_from_json(bot_dir) - One-time migration from legacy JSON files

## Legacy JSON Migration
Handles migration from:
- state.json (v1 and v2 formats) → guild_feeds, allowlist, announcements
- welcomed_users.json → welcomed_users table
- banned_users.json → banned_users table
- maintenance_mode.json → maintenance_mode table

Migration is idempotent and runs only once (checks if guild_feeds is empty).

## Key Design Patterns
1. **Async everywhere** - All operations are async (aiosqlite)
2. **State dict format** - Maintains v2 state format for compatibility:
   ```python
   {
       "_version": 2,
       "guilds": {
           "guild_id_str": {
               "feed_key": {
                   "channel_id": 123456,
                   "message_ids": [msg1, msg2, ...]
               }
           }
       },
       "allowlist": [guild_id1, guild_id2, ...],
       "announcements": [
           {"guild_id": ..., "channel_id": ..., "message_id": ..., "expires_at": ...}
       ]
   }
   ```
3. **Atomic writes** - save_state() writes all state atomically in one transaction
4. **Context manager pattern** - `async with aiosqlite.connect(path) as db:`

## Dependencies
- aiosqlite library (already in requirements.txt)
- pathlib (Python stdlib)
- json (Python stdlib)

## API Calls
- aiosqlite for all database access (async)

## Database Access
- All database operations go through this module
- Direct database access from other features should go through these exported functions

## Tests to Verify
- [ ] init_db() creates all 7 tables
- [ ] load_state() returns proper v2 state dict format
- [ ] save_state() writes guild_feeds atomically
- [ ] load_welcomed() returns set of user IDs
- [ ] add_welcomed() inserts user
- [ ] get_ban(user_id) returns ban record or None
- [ ] save_banned() replaces all bans
- [ ] load_maint_mode() returns {guild_id: {feed_key: message_id}}
- [ ] save_maint_mode() persists maintenance state
- [ ] migrate_from_json() handles v1 and v2 state.json formats
- [ ] Migration is idempotent (running twice doesn't duplicate data)

## Special Requirements
- **Message ID persistence is critical** - These are used for in-place embed editing in Discord
- **Atomic transactions** - State changes must be atomic (all-or-nothing)
- **Null safety** - Handle missing or malformed JSON gracefully during migration

## Integration Notes
- Called during bot.setup_hook() to load persistent state
- load_state() is called once at startup, result stored in bot.state
- save_state() is called whenever guild state changes (e.g., after /pd-setup)
- Other modules call load_welcomed(), add_welcomed(), get_ban(), save_banned(), etc.

## File Paths
- Database: `bot.db` (at project root)
- Legacy JSON files (if they exist): state.json, welcomed_users.json, banned_users.json, maintenance_mode.json

## Reference Implementation
See Main-1.5.0/db.py for the complete original implementation.
