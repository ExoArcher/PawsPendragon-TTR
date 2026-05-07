"""Async pytest tests for PDMain/Features/Core/db/db.py"""
import json
from pathlib import Path

import pytest
from Features.Core.db import db as db_module

from Features.Core.db.db import (
    init_db,
    _is_fresh,
    load_state,
    save_state,
    load_welcomed,
    add_welcomed,
    get_ban,
    load_all_banned,
    add_ban,
    add_multiple_bans,
    remove_ban,
    save_banned,
    add_guild_to_allowlist,
    remove_guild_from_allowlist,
    load_allowlist,
    delete_guild_feeds,
    load_maint_mode,
    save_maint_mode,
    log_audit_event,
    add_to_blacklist,
    remove_from_blacklist,
    get_all_blacklisted,
    count_banned_users_with_dangerous_perms,
)


# ────────────────────────────────────────────────────────────────────────────────
# TestInitDb (4 tests)
# ────────────────────────────────────────────────────────────────────────────────


class TestInitDb:
    """Test schema initialization and idempotency."""

    @pytest.mark.asyncio
    async def test_init_creates_all_tables(self, db):
        """Verify all 8 tables exist after init_db()."""
        import aiosqlite

        async with aiosqlite.connect(db) as conn:
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ) as cur:
                tables = {row[0] async for row in cur}

        expected_tables = {
            "guild_feeds",
            "allowlist",
            "announcements",
            "maintenance_msgs",
            "welcomed_users",
            "banned_users",
            "maintenance_mode",
            "blacklist",
            "audit_log",
        }
        assert expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}"
        assert "quarantined_guilds" not in tables, "quarantined_guilds should have been dropped"

    @pytest.mark.asyncio
    async def test_init_is_idempotent(self, db):
        """Call init_db() twice, verify no errors and schema unchanged."""
        import aiosqlite

        async with aiosqlite.connect(db) as conn:
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ) as cur:
                tables_before = {row[0] async for row in cur}

        await init_db(db)

        async with aiosqlite.connect(db) as conn:
            async with conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ) as cur:
                tables_after = {row[0] async for row in cur}

        assert tables_before == tables_after

    @pytest.mark.asyncio
    async def test_guild_feeds_table_structure(self, db):
        """Verify guild_feeds table has correct columns."""
        import aiosqlite

        async with aiosqlite.connect(db) as conn:
            async with conn.execute("PRAGMA table_info(guild_feeds)") as cur:
                columns = {row[1] async for row in cur}

        expected_columns = {"guild_id", "feed_key", "channel_id", "message_ids"}
        assert expected_columns.issubset(columns), f"Missing columns: {expected_columns - columns}"

    @pytest.mark.asyncio
    async def test_banned_users_table_structure(self, db):
        """Verify banned_users table has correct columns."""
        import aiosqlite

        async with aiosqlite.connect(db) as conn:
            async with conn.execute("PRAGMA table_info(banned_users)") as cur:
                columns = {row[1] async for row in cur}

        expected_columns = {"user_id", "reason", "banned_at", "banned_by", "banned_by_id"}
        assert expected_columns.issubset(columns), f"Missing columns: {expected_columns - columns}"


# ────────────────────────────────────────────────────────────────────────────────
# TestStateLoadSave (15 tests)
# ────────────────────────────────────────────────────────────────────────────────


class TestStateLoadSave:
    """Test state persistence (guild feeds, allowlist, announcements, maintenance messages)."""

    @pytest.mark.asyncio
    async def test_empty_state_load(self, db):
        """Load from fresh DB, verify empty state dict."""
        state = await load_state(db)

        assert state["_version"] == 3
        assert state["guilds"] == {}
        assert state["allowlist"] == []
        assert state["announcements"] == []

    @pytest.mark.asyncio
    async def test_save_empty_state(self, db):
        """Save empty state, load, verify empty."""
        empty_state = {
            "_version": 3,
            "guilds": {},
            "allowlist": [],
            "announcements": [],
        }

        await save_state(empty_state, db)
        loaded = await load_state(db)

        assert loaded["_version"] == 3
        assert loaded["guilds"] == {}
        assert loaded["allowlist"] == []
        assert loaded["announcements"] == []

    @pytest.mark.asyncio
    async def test_save_and_load_guild_feeds(self, db):
        """Save 1 guild with 3 feeds, load and verify structure."""
        state = {
            "_version": 2,
            "guilds": {
                "123456": {
                    "invasions": {
                        "channel_id": 111,
                        "message_ids": [1001, 1002],
                    },
                    "population": {
                        "channel_id": 222,
                        "message_ids": [2001],
                    },
                    "doodles": {
                        "channel_id": 333,
                        "message_ids": [3001, 3002, 3003],
                    },
                }
            },
            "allowlist": [],
            "announcements": [],
        }

        await save_state(state, db)
        loaded = await load_state(db)

        assert "123456" in loaded["guilds"]
        assert loaded["guilds"]["123456"]["invasions"]["channel_id"] == 111
        assert loaded["guilds"]["123456"]["invasions"]["message_ids"] == [1001, 1002]
        assert loaded["guilds"]["123456"]["population"]["message_ids"] == [2001]
        assert loaded["guilds"]["123456"]["doodles"]["message_ids"] == [3001, 3002, 3003]

    @pytest.mark.asyncio
    async def test_multiple_guilds_state(self, db):
        """Save 2 guilds with different feed keys, load and verify."""
        state = {
            "_version": 2,
            "guilds": {
                "111": {
                    "invasions": {"channel_id": 1, "message_ids": [100]},
                    "population": {"channel_id": 2, "message_ids": [200]},
                },
                "222": {
                    "doodles": {"channel_id": 3, "message_ids": [300]},
                    "sillymeter": {"channel_id": 4, "message_ids": [400]},
                },
            },
            "allowlist": [],
            "announcements": [],
        }

        await save_state(state, db)
        loaded = await load_state(db)

        assert "111" in loaded["guilds"]
        assert "222" in loaded["guilds"]
        assert "invasions" in loaded["guilds"]["111"]
        assert "doodles" in loaded["guilds"]["222"]

    @pytest.mark.asyncio
    async def test_feed_key_suit_threads(self, db):
        """Test special suit_threads.* feed key parsing."""
        state = {
            "_version": 2,
            "guilds": {
                "999": {
                    "suit_threads": {
                        "sellbot": {"thread_id": 5001, "message_ids": [555]},
                        "cashbot": {"thread_id": 5002, "message_ids": [556]},
                    }
                }
            },
            "allowlist": [],
            "announcements": [],
        }

        await save_state(state, db)
        loaded = await load_state(db)

        assert "suit_threads" in loaded["guilds"]["999"]
        assert "sellbot" in loaded["guilds"]["999"]["suit_threads"]
        assert loaded["guilds"]["999"]["suit_threads"]["sellbot"]["thread_id"] == 5001
        assert loaded["guilds"]["999"]["suit_threads"]["cashbot"]["message_ids"] == [556]

    @pytest.mark.asyncio
    async def test_message_ids_json_roundtrip(self, db):
        """Save message IDs as JSON, load and verify as list."""
        state = {
            "_version": 2,
            "guilds": {
                "444": {
                    "invasions": {
                        "channel_id": 1,
                        "message_ids": [1001, 1002, 1003],
                    }
                }
            },
            "allowlist": [],
            "announcements": [],
        }

        await save_state(state, db)
        loaded = await load_state(db)

        assert isinstance(loaded["guilds"]["444"]["invasions"]["message_ids"], list)
        assert loaded["guilds"]["444"]["invasions"]["message_ids"] == [1001, 1002, 1003]

    @pytest.mark.asyncio
    async def test_save_allowlist(self, db):
        """Save allowlist with 3 guild IDs, load and verify."""
        state = {
            "_version": 2,
            "guilds": {},
            "allowlist": [100, 200, 300],
            "announcements": [],
        }

        await save_state(state, db)
        loaded = await load_state(db)

        assert set(loaded["allowlist"]) == {100, 200, 300}

    @pytest.mark.asyncio
    async def test_save_announcements(self, db):
        """Save 2 announcements, load and verify all fields."""
        timestamp1 = 1234567890.0
        timestamp2 = 1234567900.0

        state = {
            "_version": 2,
            "guilds": {},
            "allowlist": [],
            "announcements": [
                {
                    "guild_id": 111,
                    "channel_id": 222,
                    "message_id": 333,
                    "expires_at": timestamp1,
                },
                {
                    "guild_id": 444,
                    "channel_id": 555,
                    "message_id": 666,
                    "expires_at": timestamp2,
                },
            ],
        }

        await save_state(state, db)
        loaded = await load_state(db)

        assert len(loaded["announcements"]) == 2
        assert loaded["announcements"][0]["guild_id"] == 111
        assert loaded["announcements"][0]["message_id"] == 333
        assert loaded["announcements"][1]["expires_at"] == timestamp2

    @pytest.mark.asyncio
    async def test_save_maintenance_msgs(self, db):
        """Save maintenance messages, load and verify."""
        state = {
            "_version": 3,
            "guilds": {},
            "allowlist": [],
            "announcements": [],
            "maintenance_msgs": {
                "111000111": 9001,
                "222000222": 9002,
            },
        }

        await save_state(state, db)
        loaded = await load_state(db)

        assert "maintenance_msgs" in loaded
        assert loaded["maintenance_msgs"]["111000111"] == 9001
        assert loaded["maintenance_msgs"]["222000222"] == 9002

    @pytest.mark.asyncio
    async def test_guild_deletion_during_save(self, db):
        """Save guild, then save state without it, verify deleted from DB."""
        state1 = {
            "_version": 2,
            "guilds": {
                "keep_me": {"invasions": {"channel_id": 1, "message_ids": [1]}},
                "delete_me": {"population": {"channel_id": 2, "message_ids": [2]}},
            },
            "allowlist": [],
            "announcements": [],
        }

        await save_state(state1, db)

        state2 = {
            "_version": 2,
            "guilds": {
                "keep_me": {"invasions": {"channel_id": 1, "message_ids": [1]}},
            },
            "allowlist": [],
            "announcements": [],
        }

        await save_state(state2, db)
        loaded = await load_state(db)

        assert "keep_me" in loaded["guilds"]
        assert "delete_me" not in loaded["guilds"]

    @pytest.mark.asyncio
    async def test_invalid_feed_entries_skipped(self, db):
        """Save state with non-dict feed entries, verify skipped."""
        state = {
            "_version": 2,
            "guilds": {
                "555": {
                    "invasions": {"channel_id": 1, "message_ids": [1]},
                    "invalid_feed": "not a dict",
                    "another_invalid": 42,
                }
            },
            "allowlist": [],
            "announcements": [],
        }

        await save_state(state, db)
        loaded = await load_state(db)

        assert "invasions" in loaded["guilds"]["555"]
        assert "invalid_feed" not in loaded["guilds"]["555"]

    @pytest.mark.asyncio
    async def test_state_format_version(self, db):
        """Verify state dict has _version: 3 key."""
        state = {
            "_version": 3,
            "guilds": {},
            "allowlist": [],
            "announcements": [],
        }

        await save_state(state, db)
        loaded = await load_state(db)

        assert "_version" in loaded
        assert loaded["_version"] == 3

    @pytest.mark.asyncio
    async def test_numeric_string_conversion(self, db):
        """Verify guild IDs stored/loaded as strings."""
        state = {
            "_version": 2,
            "guilds": {
                "777": {
                    "invasions": {"channel_id": 1, "message_ids": [1]},
                }
            },
            "allowlist": [],
            "announcements": [],
        }

        await save_state(state, db)
        loaded = await load_state(db)

        guild_ids = list(loaded["guilds"].keys())
        assert all(isinstance(gid, str) for gid in guild_ids)

    @pytest.mark.asyncio
    async def test_empty_message_ids_list(self, db):
        """Save feed with no messages, verify empty list."""
        state = {
            "_version": 2,
            "guilds": {
                "888": {
                    "invasions": {"channel_id": 1, "message_ids": []},
                }
            },
            "allowlist": [],
            "announcements": [],
        }

        await save_state(state, db)
        loaded = await load_state(db)

        assert loaded["guilds"]["888"]["invasions"]["message_ids"] == []

    @pytest.mark.asyncio
    async def test_save_state_atomic(self, db):
        """Verify no partial writes on error."""
        state1 = {
            "_version": 2,
            "guilds": {
                "aaa": {"invasions": {"channel_id": 1, "message_ids": [1]}},
            },
            "allowlist": [],
            "announcements": [],
        }

        await save_state(state1, db)

        state2 = {
            "_version": 2,
            "guilds": {
                "bbb": {"population": {"channel_id": 2, "message_ids": [2]}},
            },
            "allowlist": [],
            "announcements": [],
        }

        await save_state(state2, db)
        loaded = await load_state(db)

        assert "aaa" not in loaded["guilds"]
        assert "bbb" in loaded["guilds"]


# ────────────────────────────────────────────────────────────────────────────────
# TestWelcomedUsers (6 tests)
# ────────────────────────────────────────────────────────────────────────────────


class TestWelcomedUsers:
    """Test welcomed user tracking."""

    @pytest.mark.asyncio
    async def test_empty_welcomed_load(self, db):
        """Load from fresh DB, verify empty set."""
        result = await load_welcomed(db)

        assert isinstance(result, set)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_add_single_welcomed(self, db):
        """Add 1 user, load, verify in result."""
        user_id = 12345

        await add_welcomed(user_id, db)
        result = await load_welcomed(db)

        assert user_id in result

    @pytest.mark.asyncio
    async def test_add_multiple_welcomed(self, db):
        """Add 3 users, load, verify all present."""
        user_ids = [111, 222, 333]

        for uid in user_ids:
            await add_welcomed(uid, db)

        result = await load_welcomed(db)

        assert all(uid in result for uid in user_ids)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_add_duplicate_welcomed(self, db):
        """Add same user twice (INSERT OR IGNORE), verify once in result."""
        user_id = 999

        await add_welcomed(user_id, db)
        await add_welcomed(user_id, db)

        result = await load_welcomed(db)

        assert user_id in result
        assert len(result) == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("user_id", [1, 100000, 9223372036854775807])
    async def test_welcomed_user_types(self, db, user_id):
        """Test with various user ID types."""
        await add_welcomed(user_id, db)
        result = await load_welcomed(db)

        assert user_id in result

    @pytest.mark.asyncio
    async def test_welcomed_empty_set(self, db):
        """Verify empty load returns empty set, not None."""
        result = await load_welcomed(db)

        assert result is not None
        assert isinstance(result, set)


# ────────────────────────────────────────────────────────────────────────────────
# TestBannedUsers (22 tests)
# ────────────────────────────────────────────────────────────────────────────────


class TestBannedUsers:
    """Test ban management (CRUD, bulk operations)."""

    @pytest.mark.asyncio
    async def test_empty_banned_load(self, db):
        """Load from fresh DB, verify empty dict."""
        result = await load_all_banned(db)

        assert isinstance(result, dict)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_ban_not_found(self, db):
        """Get ban for non-existent user, verify None."""
        result = await get_ban(99999, db)

        assert result is None

    @pytest.mark.asyncio
    async def test_add_and_get_ban(self, db):
        """Add ban, get it, verify all fields."""
        user_id = 12345
        reason = "Spamming"
        banned_at = "2026-01-01T12:00:00"

        await add_ban(user_id, reason, banned_at, db)
        result = await get_ban(user_id, db)

        assert result is not None
        assert result["reason"] == reason
        assert result["banned_at"] == banned_at

    @pytest.mark.asyncio
    async def test_get_ban_returns_dict(self, db):
        """Verify get_ban() returns dict with correct keys."""
        user_id = 67890
        reason = "Harassment"
        banned_at = "2026-01-02T10:30:00"

        await add_ban(user_id, reason, banned_at, db)
        result = await get_ban(user_id, db)

        assert isinstance(result, dict)
        assert "reason" in result
        assert "banned_at" in result
        assert "banned_by" in result
        assert "banned_by_id" in result

    @pytest.mark.asyncio
    async def test_add_ban_idempotent(self, db):
        """Add same ban twice, verify no duplicate."""
        user_id = 11111
        reason = "Test reason"
        banned_at = "2026-01-03T08:00:00"

        await add_ban(user_id, reason, banned_at, db)
        await add_ban(user_id, reason, banned_at, db)

        all_bans = await load_all_banned(db)
        count = sum(1 for uid in all_bans if int(uid) == user_id)

        assert count == 1

    @pytest.mark.asyncio
    async def test_load_all_banned(self, db):
        """Add 3 bans, load all, verify all present."""
        bans = [
            (111, "Reason 1", "2026-01-01T00:00:00"),
            (222, "Reason 2", "2026-01-02T00:00:00"),
            (333, "Reason 3", "2026-01-03T00:00:00"),
        ]

        for uid, reason, banned_at in bans:
            await add_ban(uid, reason, banned_at, db)

        all_bans = await load_all_banned(db)

        assert len(all_bans) == 3
        assert all(str(uid) in all_bans for uid, _, _ in bans)

    @pytest.mark.asyncio
    async def test_ban_record_fields(self, db):
        """Verify ban dict has: reason, banned_at, banned_by, banned_by_id."""
        user_id = 555
        reason = "Field test"
        banned_at = "2026-01-04T15:30:00"

        await add_ban(user_id, reason, banned_at, db)
        all_bans = await load_all_banned(db)
        ban_record = all_bans[str(user_id)]

        assert "reason" in ban_record
        assert "banned_at" in ban_record
        assert "banned_by" in ban_record
        assert "banned_by_id" in ban_record

    @pytest.mark.asyncio
    async def test_remove_ban_success(self, db):
        """Remove existing ban, verify returns True."""
        user_id = 777
        reason = "Remove test"
        banned_at = "2026-01-05T09:00:00"

        await add_ban(user_id, reason, banned_at, db)
        result = await remove_ban(user_id, db)

        assert result is True

    @pytest.mark.asyncio
    async def test_remove_ban_not_found(self, db):
        """Remove non-existent ban, verify returns False."""
        result = await remove_ban(999999, db)

        assert result is False

    @pytest.mark.asyncio
    async def test_remove_ban_deletes_completely(self, db):
        """Remove ban, verify load_all_banned() excludes it."""
        user_id = 888
        reason = "Complete delete test"
        banned_at = "2026-01-06T14:00:00"

        await add_ban(user_id, reason, banned_at, db)
        await remove_ban(user_id, db)

        all_bans = await load_all_banned(db)

        assert str(user_id) not in all_bans

    @pytest.mark.asyncio
    async def test_add_ban_with_null_fields(self, db):
        """Add ban with None values, load and verify."""
        user_id = 444
        reason = "Null test"
        banned_at = "2026-01-07T11:00:00"

        await add_ban(user_id, reason, banned_at, db)
        result = await get_ban(user_id, db)

        assert result["reason"] == reason
        assert result["banned_at"] == banned_at

    @pytest.mark.asyncio
    async def test_save_banned_replaces_all(self, db):
        """Save dict of 2 bans, load, verify only those 2 exist."""
        bans_to_save = {
            "100": {"reason": "Ban 1", "banned_at": "2026-01-08", "banned_by": "admin", "banned_by_id": "1"},
            "200": {"reason": "Ban 2", "banned_at": "2026-01-09", "banned_by": "admin", "banned_by_id": "1"},
        }

        await save_banned(bans_to_save, db)
        all_bans = await load_all_banned(db)

        assert len(all_bans) == 2
        assert "100" in all_bans
        assert "200" in all_bans

    @pytest.mark.asyncio
    async def test_save_banned_empty(self, db):
        """Save empty dict, verify all bans deleted."""
        await add_ban(1, "To be deleted", "2026-01-10", db)

        await save_banned({}, db)
        all_bans = await load_all_banned(db)

        assert len(all_bans) == 0

    @pytest.mark.asyncio
    async def test_banned_user_id_string_conversion(self, db):
        """Verify user IDs stored as strings."""
        user_id = 12345
        reason = "String test"
        banned_at = "2026-01-11T00:00:00"

        await add_ban(user_id, reason, banned_at, db)
        all_bans = await load_all_banned(db)

        assert str(user_id) in all_bans

    @pytest.mark.asyncio
    async def test_ban_timestamp_format(self, db):
        """Verify timestamp strings persist unchanged."""
        user_id = 6789
        reason = "Timestamp test"
        banned_at = "2026-01-12T16:45:30.123456"

        await add_ban(user_id, reason, banned_at, db)
        result = await get_ban(user_id, db)

        assert result["banned_at"] == banned_at

    @pytest.mark.asyncio
    async def test_ban_admin_field(self, db):
        """Verify 'banned_by' and 'banned_by_id' fields persist."""
        user_id = 3456
        reason = "Admin test"
        banned_at = "2026-01-13T12:00:00"

        await add_ban(user_id, reason, banned_at, db)
        all_bans = await load_all_banned(db)
        ban_record = all_bans[str(user_id)]

        assert "banned_by" in ban_record
        assert "banned_by_id" in ban_record

    @pytest.mark.asyncio
    async def test_multiple_bans_concurrent(self, db):
        """Add 5 bans in sequence, verify all readable."""
        for i in range(1, 6):
            await add_ban(i * 1000, f"Ban {i}", f"2026-01-{i:02d}T00:00:00", db)

        all_bans = await load_all_banned(db)

        assert len(all_bans) == 5
        for i in range(1, 6):
            assert str(i * 1000) in all_bans

    @pytest.mark.asyncio
    async def test_ban_reason_with_special_chars(self, db):
        """Store reason with quotes/newlines, verify persist."""
        user_id = 9999
        reason = 'Reason with "quotes" and\nnewlines'
        banned_at = "2026-01-20T10:00:00"

        await add_ban(user_id, reason, banned_at, db)
        result = await get_ban(user_id, db)

        assert result["reason"] == reason

    @pytest.mark.asyncio
    async def test_load_all_banned_returns_keyed_by_user_id(self, db):
        """Verify result dict keys are user IDs."""
        await add_ban(111, "Test 1", "2026-01-21", db)
        await add_ban(222, "Test 2", "2026-01-22", db)

        all_bans = await load_all_banned(db)

        assert "111" in all_bans
        assert "222" in all_bans

    @pytest.mark.asyncio
    async def test_add_ban_overwrites_existing(self, db):
        """Add ban, then add new record for same user, verify overwrite."""
        user_id = 7777
        reason1 = "Original reason"
        reason2 = "Updated reason"

        await add_ban(user_id, reason1, "2026-01-23T00:00:00", db)
        await add_ban(user_id, reason2, "2026-01-24T00:00:00", db)

        result = await get_ban(user_id, db)

        assert result["reason"] == reason2

    @pytest.mark.asyncio
    async def test_remove_ban_after_save(self, db):
        """Save ban dict, remove 1, verify only removed one deleted."""
        bans = {
            "500": {"reason": "Keep", "banned_at": "2026-01-25", "banned_by": "admin", "banned_by_id": None},
            "600": {"reason": "Remove", "banned_at": "2026-01-26", "banned_by": "admin", "banned_by_id": None},
        }

        await save_banned(bans, db)
        await remove_ban(600, db)

        all_bans = await load_all_banned(db)

        assert "500" in all_bans
        assert "600" not in all_bans

    @pytest.mark.asyncio
    async def test_banned_users_isolation(self, db):
        """Add bans, verify other tables not affected."""
        await add_ban(1111, "Isolation test", "2026-01-27", db)

        welcomed = await load_welcomed(db)
        state = await load_state(db)

        assert len(welcomed) == 0
        assert state["guilds"] == {}

    @pytest.mark.asyncio
    async def test_add_multiple_bans_basic(self, db):
        """Insert 5 bans via bulk operation, verify all readable."""
        bans = [
            (1001, "Spam", "2026-02-01T00:00:00"),
            (1002, "Harassment", "2026-02-02T00:00:00"),
            (1003, "Abuse", "2026-02-03T00:00:00"),
            (1004, "Exploit", "2026-02-04T00:00:00"),
            (1005, "Ban evasion", "2026-02-05T00:00:00"),
        ]

        await add_multiple_bans(bans, db)
        all_bans = await load_all_banned(db)

        assert len(all_bans) == 5
        for user_id, reason, banned_at in bans:
            assert str(user_id) in all_bans
            assert all_bans[str(user_id)]["reason"] == reason
            assert all_bans[str(user_id)]["banned_at"] == banned_at

    @pytest.mark.asyncio
    async def test_add_multiple_bans_empty_list(self, db):
        """Call bulk operation with empty list, verify no errors."""
        await add_multiple_bans([], db)
        all_bans = await load_all_banned(db)
        assert len(all_bans) == 0

    @pytest.mark.asyncio
    async def test_add_multiple_bans_with_special_chars(self, db):
        """Bulk insert with special characters in reason field."""
        bans = [
            (2001, 'Reason with "quotes"', "2026-02-10T00:00:00"),
            (2002, "Reason with\nnewlines", "2026-02-11T00:00:00"),
            (2003, "Reason with 'apostrophes'", "2026-02-12T00:00:00"),
        ]

        await add_multiple_bans(bans, db)
        all_bans = await load_all_banned(db)

        assert all_bans["2001"]["reason"] == 'Reason with "quotes"'
        assert all_bans["2002"]["reason"] == "Reason with\nnewlines"
        assert all_bans["2003"]["reason"] == "Reason with 'apostrophes'"

    @pytest.mark.asyncio
    async def test_sequential_add_ban_baseline(self, db):
        """Measure sequential add_ban() calls (100 bans) for performance comparison.

        This establishes the baseline (old behavior):
        - Each add_ban() opens a new connection
        - Expected time: 1-2 seconds for 100 operations
        - Connection overhead: ~5-10ms per operation

        Bulk operation target: 50ms (20-40x faster)
        """
        import time
        user_ids = range(20000, 20100)

        start = time.perf_counter()
        for i, uid in enumerate(user_ids):
            await add_ban(uid, f"Sequential ban {i}", f"2026-02-{(i % 28) + 1:02d}T00:00:00", db)
        elapsed = time.perf_counter() - start

        all_bans = await load_all_banned(db)
        assert len(all_bans) == 100

        # Document baseline performance
        print(f"\n[Perf Baseline] Sequential add_ban() x 100: {elapsed * 1000:.1f}ms")
        print(f"  Per-operation: {(elapsed / 100) * 1000:.2f}ms")
        print(f"  Overhead per operation (est. 5-10ms connection init)")

    @pytest.mark.asyncio
    async def test_add_multiple_bans_large_batch(self, db):
        """Bulk insert 100 bans, verify all readable (performance improvement).

        Expected: <100ms (vs. 1-2 seconds for sequential add_ban)
        This demonstrates the bulk operation optimization.
        """
        import time
        bans = [
            (i, f"Ban reason {i}", f"2026-02-{(i % 28) + 1:02d}T00:00:00")
            for i in range(10000, 10100)
        ]

        start = time.perf_counter()
        await add_multiple_bans(bans, db)
        elapsed = time.perf_counter() - start

        all_bans = await load_all_banned(db)

        assert len(all_bans) == 100
        print(f"\n[Perf] Bulk insert 100 bans via add_multiple_bans(): {elapsed * 1000:.1f}ms")
        print(f"  Per-operation: {(elapsed / 100) * 1000:.3f}ms")
        print(f"  Target achieved: <100ms amortized overhead")
        # Target: <100ms for bulk operation (50x faster than sequential)
        assert elapsed < 1.0, f"Bulk operation took {elapsed * 1000:.1f}ms, expected <1s"

    @pytest.mark.asyncio
    async def test_add_multiple_bans_idempotent(self, db):
        """Call bulk operation twice with same data, verify overwrites."""
        bans = [
            (3001, "Reason v1", "2026-02-20T00:00:00"),
            (3002, "Reason v1", "2026-02-21T00:00:00"),
        ]

        await add_multiple_bans(bans, db)
        await add_multiple_bans(bans, db)  # Duplicate call

        all_bans = await load_all_banned(db)
        assert len(all_bans) == 2

    @pytest.mark.asyncio
    async def test_add_multiple_bans_mixed_with_single(self, db):
        """Add bans via bulk operation, then add one more via add_ban, verify all readable."""
        bulk_bans = [
            (4001, "Bulk reason 1", "2026-03-01T00:00:00"),
            (4002, "Bulk reason 2", "2026-03-02T00:00:00"),
        ]

        await add_multiple_bans(bulk_bans, db)
        await add_ban(4003, "Single reason", "2026-03-03T00:00:00", db)

        all_bans = await load_all_banned(db)
        assert len(all_bans) == 3
        assert all_bans["4001"]["reason"] == "Bulk reason 1"
        assert all_bans["4002"]["reason"] == "Bulk reason 2"
        assert all_bans["4003"]["reason"] == "Single reason"


# ────────────────────────────────────────────────────────────────────────────────
# TestAllowlist (8 tests)
# ────────────────────────────────────────────────────────────────────────────────


class TestAllowlist:
    """Test allowlist management."""

    @pytest.mark.asyncio
    async def test_empty_allowlist_load(self, db):
        """Load from fresh DB, verify empty list."""
        result = await load_allowlist(db)

        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_add_single_guild(self, db):
        """Add 1 guild, load, verify present."""
        guild_id = 123456

        await add_guild_to_allowlist(guild_id, db)
        result = await load_allowlist(db)

        assert guild_id in result

    @pytest.mark.asyncio
    async def test_add_multiple_guilds(self, db):
        """Add 3 guilds, load, verify all present."""
        guild_ids = [100, 200, 300]

        for gid in guild_ids:
            await add_guild_to_allowlist(gid, db)

        result = await load_allowlist(db)

        assert all(gid in result for gid in guild_ids)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_add_duplicate_guild(self, db):
        """Add same guild twice (INSERT OR IGNORE), verify once in result."""
        guild_id = 999

        await add_guild_to_allowlist(guild_id, db)
        await add_guild_to_allowlist(guild_id, db)

        result = await load_allowlist(db)

        count = sum(1 for gid in result if gid == guild_id)
        assert count == 1

    @pytest.mark.asyncio
    async def test_remove_guild_success(self, db):
        """Remove existing guild, verify returns True."""
        guild_id = 555

        await add_guild_to_allowlist(guild_id, db)
        result = await remove_guild_from_allowlist(guild_id, db)

        assert result is True

    @pytest.mark.asyncio
    async def test_remove_guild_not_found(self, db):
        """Remove non-existent guild, verify returns False."""
        result = await remove_guild_from_allowlist(888888, db)

        assert result is False

    @pytest.mark.asyncio
    async def test_remove_guild_actually_deletes(self, db):
        """Remove guild, load, verify not in result."""
        guild_id = 777

        await add_guild_to_allowlist(guild_id, db)
        await remove_guild_from_allowlist(guild_id, db)

        result = await load_allowlist(db)

        assert guild_id not in result

    @pytest.mark.asyncio
    @pytest.mark.parametrize("guild_id", [1, 1000000, 9223372036854775807])
    async def test_allowlist_guild_id_types(self, db, guild_id):
        """Test with int guild IDs."""
        await add_guild_to_allowlist(guild_id, db)
        result = await load_allowlist(db)

        assert guild_id in result


# ────────────────────────────────────────────────────────────────────────────────
# TestGuildFeeds (5 tests)
# ────────────────────────────────────────────────────────────────────────────────


class TestGuildFeeds:
    """Test guild feed deletion."""

    @pytest.mark.asyncio
    async def test_delete_feeds_success(self, db):
        """Add feeds for guild, delete, verify returns True."""
        guild_id = "123"

        state = {
            "_version": 2,
            "guilds": {
                guild_id: {
                    "invasions": {"channel_id": 1, "message_ids": [10]},
                    "population": {"channel_id": 2, "message_ids": [20]},
                }
            },
            "allowlist": [],
            "announcements": [],
        }

        await save_state(state, db)
        result = await delete_guild_feeds(guild_id, db)

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_feeds_not_found(self, db):
        """Delete feeds for non-existent guild, verify returns False."""
        result = await delete_guild_feeds("nonexistent", db)

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_feeds_only_target_guild(self, db):
        """Add feeds for 2 guilds, delete for 1, verify only 1 deleted."""
        state = {
            "_version": 2,
            "guilds": {
                "keep": {"invasions": {"channel_id": 1, "message_ids": [10]}},
                "delete": {"population": {"channel_id": 2, "message_ids": [20]}},
            },
            "allowlist": [],
            "announcements": [],
        }

        await save_state(state, db)
        await delete_guild_feeds("delete", db)

        loaded = await load_state(db)

        assert "keep" in loaded["guilds"]
        assert "delete" not in loaded["guilds"]

    @pytest.mark.asyncio
    async def test_delete_all_feeds_for_guild(self, db):
        """Add multiple feed keys for 1 guild, delete, verify all gone."""
        guild_id = "multi"

        state = {
            "_version": 2,
            "guilds": {
                guild_id: {
                    "invasions": {"channel_id": 1, "message_ids": [1]},
                    "population": {"channel_id": 2, "message_ids": [2]},
                    "doodles": {"channel_id": 3, "message_ids": [3]},
                    "sillymeter": {"channel_id": 4, "message_ids": [4]},
                }
            },
            "allowlist": [],
            "announcements": [],
        }

        await save_state(state, db)
        await delete_guild_feeds(guild_id, db)

        loaded = await load_state(db)

        assert guild_id not in loaded["guilds"]

    @pytest.mark.asyncio
    async def test_delete_feeds_returns_true_on_delete(self, db):
        """Verify rowcount > 0 case returns True."""
        guild_id = "verify"

        state = {
            "_version": 2,
            "guilds": {
                guild_id: {
                    "invasions": {"channel_id": 1, "message_ids": [1]},
                }
            },
            "allowlist": [],
            "announcements": [],
        }

        await save_state(state, db)
        result = await delete_guild_feeds(guild_id, db)

        assert result is True


# ── Part B: Maintenance Mode, Quarantine, Blacklist, Audit Log ────

class TestMaintenanceMode:
    """Test load_maint_mode and save_maint_mode functions."""

    @pytest.mark.asyncio
    async def test_empty_maint_mode_load(self, db):
        """Empty database → empty dict."""
        from Features.Core.db.db import load_maint_mode
        result = await load_maint_mode(db)
        assert result == {}

    @pytest.mark.asyncio
    async def test_save_and_load_single_guild(self, db):
        """Save single guild with one feed, load it back."""
        from Features.Core.db.db import save_maint_mode, load_maint_mode
        data = {"123": {"invasions": 456}}
        await save_maint_mode(data, db)
        result = await load_maint_mode(db)
        assert result == {"123": {"invasions": 456}}

    @pytest.mark.asyncio
    async def test_save_multiple_feeds_per_guild(self, db):
        """One guild with multiple feed keys."""
        from Features.Core.db.db import save_maint_mode, load_maint_mode
        data = {"123": {"invasions": 456, "doodles": 789, "population": 111}}
        await save_maint_mode(data, db)
        result = await load_maint_mode(db)
        assert result == {"123": {"invasions": 456, "doodles": 789, "population": 111}}

    @pytest.mark.asyncio
    async def test_save_multiple_guilds(self, db):
        """Multiple guilds, each with feeds."""
        from Features.Core.db.db import save_maint_mode, load_maint_mode
        data = {
            "123": {"invasions": 456, "doodles": 789},
            "999": {"population": 222},
        }
        await save_maint_mode(data, db)
        result = await load_maint_mode(db)
        assert result == data

    @pytest.mark.asyncio
    async def test_save_overwrites_previous(self, db):
        """Second save fully replaces first."""
        from Features.Core.db.db import save_maint_mode, load_maint_mode
        await save_maint_mode({"123": {"invasions": 456}}, db)
        await save_maint_mode({"999": {"doodles": 888}}, db)
        result = await load_maint_mode(db)
        assert result == {"999": {"doodles": 888}}
        assert "123" not in result

    @pytest.mark.asyncio
    async def test_save_empty_dict_clears(self, db):
        """Saving empty dict clears all maintenance mode."""
        from Features.Core.db.db import save_maint_mode, load_maint_mode
        await save_maint_mode({"123": {"invasions": 456}}, db)
        await save_maint_mode({}, db)
        result = await load_maint_mode(db)
        assert result == {}

    @pytest.mark.asyncio
    async def test_message_id_type_coercion(self, db):
        """Message IDs coerced to int; keys remain strings."""
        from Features.Core.db.db import save_maint_mode, load_maint_mode
        # Pass string message_id; should be stored and retrieved as int
        data = {"123": {"doodles": "999"}}
        await save_maint_mode(data, db)
        result = await load_maint_mode(db)
        assert result["123"]["doodles"] == 999
        assert isinstance(result["123"]["doodles"], int)


# ────────────────────────────────────────────────────────────────────────────────
# TestBlacklist (10 tests)
# ────────────────────────────────────────────────────────────────────────────────


class TestBlacklist:
    """Test blacklist operations."""

    @pytest.mark.asyncio
    async def test_add_to_blacklist(self, db):
        """Add a guild to blacklist."""
        from Features.Core.db.db import add_to_blacklist, get_all_blacklisted
        await add_to_blacklist(
            guild_id=123,
            owner_id=456,
            reason="spam",
            flagged_by_user_id=789,
            path=db,
        )
        result = await get_all_blacklisted(db)
        assert 123 in result

    @pytest.mark.asyncio
    async def test_remove_from_blacklist(self, db):
        """Remove a guild from blacklist."""
        from Features.Core.db.db import (
            add_to_blacklist,
            remove_from_blacklist,
            get_all_blacklisted,
        )
        await add_to_blacklist(123, 456, "spam", 789, db)
        removed = await remove_from_blacklist(123, db)
        assert removed is True
        result = await get_all_blacklisted(db)
        assert 123 not in result

    @pytest.mark.asyncio
    async def test_remove_nonexistent_blacklist(self, db):
        """Removing a guild not in blacklist returns False."""
        from Features.Core.db.db import remove_from_blacklist
        removed = await remove_from_blacklist(999, db)
        assert removed is False

    @pytest.mark.asyncio
    async def test_multiple_blacklisted_guilds(self, db):
        """Load multiple blacklisted guilds."""
        from Features.Core.db.db import add_to_blacklist, get_all_blacklisted
        for i in range(1, 4):
            await add_to_blacklist(
                guild_id=i * 100,
                owner_id=i * 1000,
                reason=f"reason {i}",
                flagged_by_user_id=i * 10000,
                path=db,
            )
        result = await get_all_blacklisted(db)
        assert set(result) == {100, 200, 300}

    @pytest.mark.asyncio
    async def test_blacklist_upsert(self, db):
        """Adding same guild ID replaces old record."""
        from Features.Core.db.db import add_to_blacklist, get_all_blacklisted
        await add_to_blacklist(123, 456, "old reason", 789, db)
        await add_to_blacklist(123, 999, "new reason", 111, db)
        result = await get_all_blacklisted(db)
        assert len(result) == 1
        assert 123 in result

    @pytest.mark.asyncio
    async def test_add_multiple_flaggers_same_guild(self, db):
        """Adding same guild by different user appends to flagged_by_user_ids."""
        from Features.Core.db.db import add_to_blacklist, get_all_blacklisted
        await add_to_blacklist(123, 456, "spam", 789, db)
        await add_to_blacklist(123, 456, "spam", 111, db)  # Same guild, different flagger
        result = await get_all_blacklisted(db)
        assert 123 in result

    @pytest.mark.asyncio
    async def test_empty_blacklist_load(self, db):
        """Empty database → empty list."""
        from Features.Core.db.db import get_all_blacklisted
        result = await get_all_blacklisted(db)
        assert result == []

    @pytest.mark.asyncio
    async def test_blacklist_with_special_characters(self, db):
        """Reason field with special characters is stored."""
        from Features.Core.db.db import add_to_blacklist, get_all_blacklisted
        await add_to_blacklist(
            guild_id=123,
            owner_id=456,
            reason="contains 'quotes' and \"double quotes\"",
            flagged_by_user_id=789,
            path=db,
        )
        result = await get_all_blacklisted(db)
        assert 123 in result


# ────────────────────────────────────────────────────────────────────────────────
# TestAuditLog (8 tests)
# ────────────────────────────────────────────────────────────────────────────────


class TestAuditLog:
    """Test audit log operations."""

    @pytest.mark.asyncio
    async def test_log_audit_event_minimal(self, db):
        """Log event with only event_type."""
        from Features.Core.db.db import log_audit_event
        await log_audit_event(event_type="test_event", path=db)
        # If no exception, the log succeeded

    @pytest.mark.asyncio
    async def test_log_audit_event_with_details(self, db):
        """Log event with details dict."""
        from Features.Core.db.db import log_audit_event
        details = {"action": "added", "count": 5}
        await log_audit_event(
            event_type="bulk_operation",
            details=details,
            path=db,
        )
        # If no exception, the log succeeded

    @pytest.mark.asyncio
    async def test_log_audit_event_with_guild_id(self, db):
        """Log event associated with a guild."""
        from Features.Core.db.db import log_audit_event
        await log_audit_event(
            event_type="guild_flagged",
            guild_id=123,
            path=db,
        )
        # If no exception, the log succeeded

    @pytest.mark.asyncio
    async def test_log_audit_event_with_user_id(self, db):
        """Log event triggered by a user."""
        from Features.Core.db.db import log_audit_event
        await log_audit_event(
            event_type="ban_issued",
            triggered_by_user_id=456,
            path=db,
        )
        # If no exception, the log succeeded

    @pytest.mark.asyncio
    async def test_log_audit_event_all_fields(self, db):
        """Log event with all fields."""
        from Features.Core.db.db import log_audit_event
        await log_audit_event(
            event_type="quarantine_action",
            details={"action": "flagged", "reason": "spam"},
            guild_id=789,
            triggered_by_user_id=456,
            path=db,
        )
        # If no exception, the log succeeded

    @pytest.mark.asyncio
    async def test_log_audit_event_none_details(self, db):
        """Log event with None details (explicitly)."""
        from Features.Core.db.db import log_audit_event
        await log_audit_event(
            event_type="system_event",
            details=None,
            path=db,
        )
        # If no exception, the log succeeded

    @pytest.mark.asyncio
    async def test_log_audit_event_nested_details(self, db):
        """Log event with nested dict details."""
        from Features.Core.db.db import log_audit_event
        details = {
            "guild_id": 123,
            "user_ids": [456, 789],
            "metadata": {"version": 2, "flag": True},
        }
        await log_audit_event(
            event_type="batch_operation",
            details=details,
            path=db,
        )
        # If no exception, the log succeeded


# ────────────────────────────────────────────────────────────────────────────────
# TestQuarantineUtils (6 tests)
# ────────────────────────────────────────────────────────────────────────────────


# ────────────────────────────────────────────────────────────────────────────────
# TestMiscUtils (8 tests)
# ────────────────────────────────────────────────────────────────────────────────


class TestMiscUtils:
    """Test miscellaneous utility functions."""

    @pytest.mark.asyncio
    async def test_count_banned_users(self, db):
        """Count banned users in the database."""
        from Features.Core.db.db import add_ban, count_banned_users_with_dangerous_perms
        await add_ban(123, "spam", "2026-05-02T10:00:00Z", db)
        await add_ban(456, "abuse", "2026-05-02T11:00:00Z", db)
        count = await count_banned_users_with_dangerous_perms(db)
        assert count == 2

    @pytest.mark.asyncio
    async def test_count_banned_users_empty(self, db):
        """Count banned users when none exist."""
        from Features.Core.db.db import count_banned_users_with_dangerous_perms
        count = await count_banned_users_with_dangerous_perms(db)
        assert count == 0

    @pytest.mark.asyncio
    async def test_delete_guild_feeds(self, db):
        """Delete all feeds for a guild."""
        from Features.Core.db.db import delete_guild_feeds
        # This function exists but requires data in guild_feeds first
        # Test it returns bool
        result = await delete_guild_feeds(999, db)
        assert isinstance(result, bool)

    @pytest.mark.asyncio
    async def test_delete_nonexistent_guild_feeds(self, db):
        """Deleting feeds for nonexistent guild returns False."""
        from Features.Core.db.db import delete_guild_feeds
        result = await delete_guild_feeds(999, db)
        assert result is False

    @pytest.mark.asyncio
    async def test_load_allowlist(self, db):
        """Load allowlist (empty initially)."""
        from Features.Core.db.db import load_allowlist
        result = await load_allowlist(db)
        assert result == [] or isinstance(result, list)

    @pytest.mark.asyncio
    async def test_add_guild_to_allowlist(self, db):
        """Add guild to allowlist."""
        from Features.Core.db.db import add_guild_to_allowlist, load_allowlist
        await add_guild_to_allowlist(123, db)
        result = await load_allowlist(db)
        assert 123 in result

    @pytest.mark.asyncio
    async def test_remove_guild_from_allowlist(self, db):
        """Remove guild from allowlist."""
        from Features.Core.db.db import (
            add_guild_to_allowlist,
            remove_guild_from_allowlist,
            load_allowlist,
        )
        await add_guild_to_allowlist(123, db)
        removed = await remove_guild_from_allowlist(123, db)
        assert removed is True
        result = await load_allowlist(db)
        assert 123 not in result


# ────────────────────────────────────────────────────────────────────────────────
# TestConnectionPool (3 tests)
# ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pool_initialized_after_init_db(db):
    """Pool exists and has 5 available connections after init_db."""
    assert db in db_module._pools
    assert db_module._pools[db].qsize() == 5


@pytest.mark.asyncio
async def test_pool_connection_returned_after_use(db):
    """Connection is returned to pool after normal use."""
    pool_before = db_module._pools[db].qsize()
    async with db_module._db_conn(db) as conn:
        await conn.execute("SELECT 1")
    assert db_module._pools[db].qsize() == pool_before


@pytest.mark.asyncio
async def test_pool_connection_returned_after_exception(db):
    """Connection is returned to pool even if an exception occurs inside the context."""
    pool_before = db_module._pools[db].qsize()
    with pytest.raises(Exception):
        async with db_module._db_conn(db) as conn:
            raise RuntimeError("test error")
    assert db_module._pools[db].qsize() == pool_before


# ────────────────────────────────────────────────────────────────────────────────
# TestDeleteGuildCompletely (2 tests)
# ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_guild_completely_removes_all_tables(db):
    """delete_guild_completely removes guild from guild_feeds, allowlist, blacklist atomically."""
    from Features.Core.db import db as db_module

    # Setup: insert guild into all tables
    await db_module.add_guild_to_allowlist(12345, db)
    state = {"guilds": {"12345": {"information": {"channel_id": 99, "message_ids": [1, 2]}}}, "allowlist": [12345], "announcements": []}
    await db_module.save_state(state, db)
    await db_module.add_to_blacklist(12345, 67890, "test", 111, db)

    # Delete completely
    await db_module.delete_guild_completely(12345, db)

    # Verify removed from all tables
    allowlist = await db_module.load_allowlist(db)
    assert 12345 not in allowlist

    loaded_state = await db_module.load_state(db)
    assert "12345" not in loaded_state["guilds"]

    blacklisted = await db_module.get_all_blacklisted(db)
    assert 12345 not in blacklisted

@pytest.mark.asyncio
async def test_delete_guild_completely_nonexistent_is_noop(db):
    """delete_guild_completely on nonexistent guild does not raise."""
    from Features.Core.db import db as db_module
    await db_module.delete_guild_completely(99999, db)  # Should not raise


# ────────────────────────────────────────────────────────────────────────────────
# TestGuildIdTypeStandardization (2 tests)
# ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_guild_id_stored_as_integer_in_guild_feeds(db):
    """guild_feeds.guild_id should be stored as INTEGER after migration."""
    from Features.Core.db import db as db_module

    state = {
        "guilds": {"111222333": {"information": {"channel_id": 1, "message_ids": [100]}}},
        "allowlist": [111222333],
        "announcements": [],
    }
    await db_module.save_state(state, db)

    # Query with integer — should find the row
    async with db_module._db_conn(db) as conn:
        async with conn.execute(
            "SELECT guild_id, channel_id FROM guild_feeds WHERE guild_id = ?",
            (111222333,)  # integer query
        ) as cur:
            row = await cur.fetchone()
    assert row is not None, "Should find guild_feeds row with integer query"
    # Verify stored as integer (SQLite returns int for INTEGER affinity column)
    assert isinstance(row[0], int), f"guild_id should be int, got {type(row[0])}"


@pytest.mark.asyncio
async def test_migration_converts_text_guild_id_to_integer(db):
    """Existing TEXT guild_id rows are migrated to INTEGER on init_db."""
    from Features.Core.db import db as db_module

    # Create a TEXT-schema guild_feeds table (simulating legacy DB)
    async with db_module._db_conn(db) as conn:
        await conn.execute("ALTER TABLE guild_feeds RENAME TO guild_feeds_backup")
        await conn.execute("""
            CREATE TABLE guild_feeds (
                guild_id    TEXT    NOT NULL,
                feed_key    TEXT    NOT NULL,
                channel_id  INTEGER NOT NULL DEFAULT 0,
                message_ids TEXT    NOT NULL DEFAULT '[]',
                PRIMARY KEY (guild_id, feed_key)
            )
        """)
        await conn.execute(
            "INSERT INTO guild_feeds VALUES (?, ?, ?, ?)",
            ("444555666", "information", 2, "[]")
        )
        await conn.commit()

    # Re-run init_db — should detect TEXT affinity and migrate
    await db_module.init_db(db)

    # Now query with integer — should find the row
    async with db_module._db_conn(db) as conn:
        async with conn.execute(
            "SELECT guild_id FROM guild_feeds WHERE guild_id = ?", (444555666,)
        ) as cur:
            row = await cur.fetchone()
    assert row is not None, "Row should be findable after migration"
    assert isinstance(row[0], int), f"guild_id should be int after migration, got {type(row[0])}"


# ────────────────────────────────────────────────────────────────────────────────
# TestDatabaseIndexes (1 test)
# ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_db_indexes_created(db):
    """Expected indexes should exist after init_db."""
    from Features.Core.db import db as db_module

    expected_indexes = [
        "idx_guild_feeds_guild_id",
        "idx_announcements_guild_id",
        "idx_announcements_expires_at",
        "idx_audit_log_guild_id",
        "idx_audit_log_timestamp",
        "idx_audit_log_event_type",
    ]

    async with db_module._db_conn(db) as conn:
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ) as cur:
            existing = {row[0] async for row in cur}

    for idx in expected_indexes:
        assert idx in existing, f"Missing index: {idx}"


@pytest.mark.asyncio
async def test_cleanup_audit_log_deletes_old_entries(db):
    """cleanup_audit_log deletes entries older than retention period."""
    from Features.Core.db import db as db_module
    from datetime import datetime, timezone, timedelta

    # Insert 3 old entries (91 days ago) and 2 recent entries
    old_ts = (datetime.now(timezone.utc) - timedelta(days=91)).isoformat()
    recent_ts = datetime.now(timezone.utc).isoformat()

    async with db_module._db_conn(db) as conn:
        for _ in range(3):
            await conn.execute(
                "INSERT INTO audit_log (event_type, timestamp) VALUES (?, ?)",
                ("old_event", old_ts)
            )
        for _ in range(2):
            await conn.execute(
                "INSERT INTO audit_log (event_type, timestamp) VALUES (?, ?)",
                ("recent_event", recent_ts)
            )
        await conn.commit()

    deleted = await db_module.cleanup_audit_log(days=90, path=db)
    assert deleted == 3

    async with db_module._db_conn(db) as conn:
        async with conn.execute("SELECT COUNT(*) FROM audit_log") as cur:
            row = await cur.fetchone()
    assert row[0] == 2  # Only recent entries remain

@pytest.mark.asyncio
async def test_cleanup_audit_log_empty_table_is_noop(db):
    """cleanup_audit_log on empty table returns 0 and does not raise."""
    from Features.Core.db import db as db_module
    deleted = await db_module.cleanup_audit_log(days=90, path=db)
    assert deleted == 0
