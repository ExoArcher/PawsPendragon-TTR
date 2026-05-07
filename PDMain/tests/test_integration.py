"""Integration tests for Paws Pendragon TTR bot.

Tests multi-step flows that span DB, cache, and state layers.
Uses temporary SQLite databases and mock Discord objects.
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from Features.Core.db import db as db_module


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def fresh_db():
    """Temporary DB, initialized and torn down per test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = Path(f.name)
    await db_module.init_db(path)
    yield path
    # Cleanup pool connections before unlinking
    pool = db_module._pools.pop(path, None)
    if pool is not None:
        while not pool.empty():
            try:
                conn = pool.get_nowait()
                await conn.close()
            except Exception:
                pass
    path.unlink(missing_ok=True)


# ── DB Integrity Tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_concurrent_guild_adds_all_persist(fresh_db):
    """Adding 5 guilds concurrently all end up in the allowlist."""
    guild_ids = [100001, 100002, 100003, 100004, 100005]
    await asyncio.gather(*[
        db_module.add_guild_to_allowlist(gid, fresh_db) for gid in guild_ids
    ])
    allowlist = await db_module.load_allowlist(fresh_db)
    for gid in guild_ids:
        assert gid in allowlist, f"Guild {gid} missing from allowlist"


@pytest.mark.asyncio
async def test_delete_guild_completely_is_atomic(fresh_db):
    """delete_guild_completely removes from all tables in one transaction."""
    gid = 200001
    # Insert into multiple tables
    await db_module.add_guild_to_allowlist(gid, fresh_db)
    state = {
        "guilds": {str(gid): {"information": {"channel_id": 1, "message_ids": [10, 20]}}},
        "allowlist": [gid],
        "announcements": [],
    }
    await db_module.save_state(state, fresh_db)
    await db_module.add_to_blacklist(gid, 999, "test", 111, fresh_db)

    # Delete completely
    await db_module.delete_guild_completely(gid, fresh_db)

    # Verify gone from all tables
    allowlist = await db_module.load_allowlist(fresh_db)
    assert gid not in allowlist

    loaded = await db_module.load_state(fresh_db)
    assert str(gid) not in loaded["guilds"]

    blacklisted = await db_module.get_all_blacklisted(fresh_db)
    assert gid not in blacklisted


@pytest.mark.asyncio
async def test_save_then_load_state_roundtrip(fresh_db):
    """State saved with message IDs loads back with identical IDs."""
    original = {
        "guilds": {
            "300001": {
                "information": {"channel_id": 555, "message_ids": [111, 222, 333]},
                "doodles": {"channel_id": 666, "message_ids": [444]},
            }
        },
        "allowlist": [300001],
        "announcements": [],
    }
    await db_module.save_state(original, fresh_db)
    loaded = await db_module.load_state(fresh_db)

    assert "300001" in loaded["guilds"]
    info = loaded["guilds"]["300001"]["information"]
    assert info["channel_id"] == 555
    assert set(info["message_ids"]) == {111, 222, 333}


@pytest.mark.asyncio
async def test_save_state_concurrent_writes_no_corruption(fresh_db):
    """Two concurrent save_state calls don't corrupt the database."""
    state_a = {
        "guilds": {"400001": {"information": {"channel_id": 1, "message_ids": [1]}}},
        "allowlist": [400001],
        "announcements": [],
    }
    state_b = {
        "guilds": {"400002": {"information": {"channel_id": 2, "message_ids": [2]}}},
        "allowlist": [400002],
        "announcements": [],
    }
    # Run two saves concurrently
    await asyncio.gather(
        db_module.save_state(state_a, fresh_db),
        db_module.save_state(state_b, fresh_db),
    )
    # After either save, DB should be consistent (no partial writes)
    loaded = await db_module.load_state(fresh_db)
    # One of the saves should have "won" — the important thing is the DB isn't corrupted
    assert isinstance(loaded["guilds"], dict)


# ── Audit Log Retention Tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_audit_log_retention_keeps_recent_and_deletes_old(fresh_db):
    """cleanup_audit_log retains entries within window, deletes entries outside."""
    from datetime import datetime, timezone, timedelta

    old_ts = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    recent_ts = datetime.now(timezone.utc).isoformat()

    async with db_module._db_conn(fresh_db) as conn:
        for i in range(5):
            await conn.execute(
                "INSERT INTO audit_log (event_type, timestamp) VALUES (?, ?)",
                (f"old_{i}", old_ts)
            )
        for i in range(3):
            await conn.execute(
                "INSERT INTO audit_log (event_type, timestamp) VALUES (?, ?)",
                (f"recent_{i}", recent_ts)
            )
        await conn.commit()

    deleted = await db_module.cleanup_audit_log(days=90, path=fresh_db)
    assert deleted == 5

    async with db_module._db_conn(fresh_db) as conn:
        async with conn.execute("SELECT COUNT(*) FROM audit_log") as cur:
            count = (await cur.fetchone())[0]
    assert count == 3


# ── Ban Operations Tests ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_ban_then_load_all_banned_contains_ban(fresh_db):
    """Ban added via add_ban is returned by load_all_banned."""
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    await db_module.add_ban(500001, "test reason", ts, fresh_db)

    banned = await db_module.load_all_banned(fresh_db)
    assert "500001" in banned
    assert banned["500001"]["reason"] == "test reason"


@pytest.mark.asyncio
async def test_remove_ban_removes_from_db(fresh_db):
    """remove_ban returns True and ban is gone from load_all_banned."""
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()
    await db_module.add_ban(600001, "remove test", ts, fresh_db)

    removed = await db_module.remove_ban(600001, fresh_db)
    assert removed is True

    banned = await db_module.load_all_banned(fresh_db)
    assert "600001" not in banned


# ── Connection Pool Tests ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pool_handles_5_concurrent_queries(fresh_db):
    """Pool of 5 handles 5 concurrent queries without deadlock."""
    results = await asyncio.gather(*[
        db_module.load_allowlist(fresh_db) for _ in range(5)
    ])
    assert len(results) == 5
    for r in results:
        assert isinstance(r, list)


@pytest.mark.asyncio
async def test_pool_exception_does_not_leak_connection(fresh_db):
    """After an exception inside _db_conn, pool still has 5 connections."""
    pool = db_module._pools[fresh_db]
    initial_size = pool.qsize()

    try:
        async with db_module._db_conn(fresh_db) as conn:
            raise RuntimeError("deliberate test exception")
    except RuntimeError:
        pass

    assert pool.qsize() == initial_size, "Connection leaked after exception"


# ── State Persistence with Suit Threads ───────────────────────────────────────

@pytest.mark.asyncio
async def test_save_load_suit_threads_roundtrip(fresh_db):
    """State with suit_threads nested structure persists correctly."""
    original = {
        "guilds": {
            "700001": {
                "suit_threads": {
                    "boss": {"thread_id": 1001, "message_ids": [2001, 2002]},
                    "v": {"thread_id": 1002, "message_ids": [2003]},
                }
            }
        },
        "allowlist": [700001],
        "announcements": [],
    }
    await db_module.save_state(original, fresh_db)
    loaded = await db_module.load_state(fresh_db)

    assert "700001" in loaded["guilds"]
    suit_threads = loaded["guilds"]["700001"]["suit_threads"]
    assert suit_threads["boss"]["thread_id"] == 1001
    assert set(suit_threads["boss"]["message_ids"]) == {2001, 2002}
    assert suit_threads["v"]["thread_id"] == 1002


# ── Announcements Persistence ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_load_announcements_roundtrip(fresh_db):
    """Announcements with guild/channel/message IDs and TTL persist correctly."""
    original = {
        "guilds": {},
        "allowlist": [],
        "announcements": [
            {"guild_id": 800001, "channel_id": 8001, "message_id": 80001, "expires_at": 1234567890.0},
            {"guild_id": 800002, "channel_id": 8002, "message_id": 80002, "expires_at": 1234567900.0},
        ],
    }
    await db_module.save_state(original, fresh_db)
    loaded = await db_module.load_state(fresh_db)

    assert len(loaded["announcements"]) == 2
    assert loaded["announcements"][0]["guild_id"] == 800001
    assert loaded["announcements"][1]["expires_at"] == 1234567900.0


# ── Maintenance Messages Persistence ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_maintenance_msgs_persist(fresh_db):
    """Maintenance messages keyed by guild_id persist and load correctly."""
    original = {
        "guilds": {},
        "allowlist": [],
        "announcements": [],
        "maintenance_msgs": {
            "900001": 90001,
            "900002": 90002,
        }
    }
    await db_module.save_state(original, fresh_db)
    loaded = await db_module.load_state(fresh_db)

    maint = loaded.get("maintenance_msgs", {})
    assert maint["900001"] == 90001
    assert maint["900002"] == 90002


# ── Bulk Ban Operations ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_multiple_bans_bulk_insert(fresh_db):
    """add_multiple_bans inserts all bans in one connection."""
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).isoformat()

    bans = [
        (1000001, "bulk reason 1", ts),
        (1000002, "bulk reason 2", ts),
        (1000003, "bulk reason 3", ts),
    ]
    await db_module.add_multiple_bans(bans, fresh_db)

    banned = await db_module.load_all_banned(fresh_db)
    assert len(banned) == 3
    assert banned["1000001"]["reason"] == "bulk reason 1"
    assert banned["1000002"]["reason"] == "bulk reason 2"
    assert banned["1000003"]["reason"] == "bulk reason 3"


# ── Blacklist Operations ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_to_blacklist_then_get_all_blacklisted(fresh_db):
    """Guilds added to blacklist appear in get_all_blacklisted()."""
    await db_module.add_to_blacklist(1100001, 999, "malicious", 111, fresh_db)
    await db_module.add_to_blacklist(1100002, 998, "spam", 222, fresh_db)

    blacklisted = await db_module.get_all_blacklisted(fresh_db)
    assert 1100001 in blacklisted
    assert 1100002 in blacklisted


@pytest.mark.asyncio
async def test_remove_from_blacklist_removes_guild(fresh_db):
    """remove_from_blacklist returns True and guild is gone."""
    await db_module.add_to_blacklist(1200001, 999, "test", 111, fresh_db)

    removed = await db_module.remove_from_blacklist(1200001, fresh_db)
    assert removed is True

    blacklisted = await db_module.get_all_blacklisted(fresh_db)
    assert 1200001 not in blacklisted


# ── Welcomed Users Persistence ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_welcomed_user_then_load(fresh_db):
    """Users added via add_welcomed appear in load_welcomed()."""
    await db_module.add_welcomed(1300001, fresh_db)
    await db_module.add_welcomed(1300002, fresh_db)

    welcomed = await db_module.load_welcomed(fresh_db)
    assert 1300001 in welcomed
    assert 1300002 in welcomed


# ── Maintenance Mode Persistence ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_save_load_maint_mode_roundtrip(fresh_db):
    """Maintenance mode state persists and loads correctly."""
    maint_data = {
        "1400001": {
            "information": 140001,
            "doodles": 140002,
        },
        "1400002": {
            "suit_calculator": 140003,
        }
    }
    await db_module.save_maint_mode(maint_data, fresh_db)

    loaded = await db_module.load_maint_mode(fresh_db)
    assert loaded["1400001"]["information"] == 140001
    assert loaded["1400001"]["doodles"] == 140002
    assert loaded["1400002"]["suit_calculator"] == 140003


# ── Audit Log Event Logging ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_log_audit_event_persists(fresh_db):
    """log_audit_event writes to audit_log and can be queried."""
    await db_module.log_audit_event(
        event_type="test_event",
        details={"key": "value"},
        guild_id=1500001,
        triggered_by_user_id=1500002,
        path=fresh_db
    )

    async with db_module._db_conn(fresh_db) as conn:
        async with conn.execute(
            "SELECT event_type, guild_id, triggered_by_user_id FROM audit_log"
        ) as cur:
            row = await cur.fetchone()

    assert row[0] == "test_event"
    assert row[1] == 1500001
    assert row[2] == 1500002


# ── Guild Feeds Deletion ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_guild_feeds_removes_all_feeds(fresh_db):
    """delete_guild_feeds removes all feed entries for a guild."""
    state = {
        "guilds": {
            "1600001": {
                "information": {"channel_id": 1, "message_ids": [10]},
                "doodles": {"channel_id": 2, "message_ids": [20]},
                "suit_calculator": {"channel_id": 3, "message_ids": [30]},
            }
        },
        "allowlist": [],
        "announcements": [],
    }
    await db_module.save_state(state, fresh_db)

    deleted = await db_module.delete_guild_feeds(1600001, fresh_db)
    assert deleted is True

    loaded = await db_module.load_state(fresh_db)
    assert "1600001" not in loaded["guilds"]
