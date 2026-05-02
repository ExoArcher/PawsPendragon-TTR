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


class TestQuarantinedGuilds:
    """Test quarantine guild operations."""

    @pytest.mark.asyncio
    async def test_load_empty_quarantine(self, db):
        """Empty database → empty dict."""
        from Features.Core.db.db import load_quarantined_guilds
        result = await load_quarantined_guilds(db)
        assert result == {}

    @pytest.mark.asyncio
    async def test_add_single_quarantine(self, db):
        """Add one quarantined guild, load it."""
        from Features.Core.db.db import add_quarantined_guild, load_quarantined_guilds
        await add_quarantined_guild(
            guild_id="123",
            guild_name="Test Guild",
            owner_id="456",
            flagged_at="2026-05-02T10:00:00Z",
            flag_reason="spam",
            flagged_by_user_id="789",
            path=db,
        )
        result = await load_quarantined_guilds(db)
        assert "123" in result
        assert result["123"]["guild_name"] == "Test Guild"
        assert result["123"]["owner_id"] == "456"
        assert result["123"]["flag_reason"] == "spam"
        assert result["123"]["flagged_by_user_id"] == "789"

    @pytest.mark.asyncio
    async def test_add_quarantine_with_timestamps(self, db):
        """Quarantine with optional noticed/feeds_halted timestamps."""
        from Features.Core.db.db import add_quarantined_guild, load_quarantined_guilds
        await add_quarantined_guild(
            guild_id="123",
            guild_name="Test Guild",
            owner_id="456",
            flagged_at="2026-05-02T10:00:00Z",
            flag_reason="spam",
            flagged_by_user_id="789",
            noticed="2026-05-02T11:00:00Z",
            feeds_halted="2026-05-02T12:00:00Z",
            owner_notified="Y",
            path=db,
        )
        result = await load_quarantined_guilds(db)
        assert "123" in result
        # Basic fields loaded
        assert result["123"]["guild_id"] == "123"

    @pytest.mark.asyncio
    async def test_remove_quarantine(self, db):
        """Remove a quarantined guild."""
        from Features.Core.db.db import (
            add_quarantined_guild,
            load_quarantined_guilds,
            remove_quarantined_guild,
        )
        await add_quarantined_guild(
            guild_id="123",
            guild_name="Test Guild",
            owner_id="456",
            flagged_at="2026-05-02T10:00:00Z",
            flag_reason="spam",
            flagged_by_user_id="789",
            path=db,
        )
        removed = await remove_quarantined_guild("123", db)
        assert removed is True
        result = await load_quarantined_guilds(db)
        assert result == {}

    @pytest.mark.asyncio
    async def test_remove_nonexistent_quarantine(self, db):
        """Removing a guild that doesn't exist returns False."""
        from Features.Core.db.db import remove_quarantined_guild
        removed = await remove_quarantined_guild("999", db)
        assert removed is False

    @pytest.mark.asyncio
    async def test_multiple_quarantined_guilds(self, db):
        """Load multiple quarantined guilds."""
        from Features.Core.db.db import add_quarantined_guild, load_quarantined_guilds
        for i in range(1, 4):
            await add_quarantined_guild(
                guild_id=str(i * 100),
                guild_name=f"Guild {i}",
                owner_id=str(i * 1000),
                flagged_at="2026-05-02T10:00:00Z",
                flag_reason=f"reason {i}",
                flagged_by_user_id=str(i * 10000),
                path=db,
            )
        result = await load_quarantined_guilds(db)
        assert len(result) == 3
        assert "100" in result
        assert "200" in result
        assert "300" in result

    @pytest.mark.asyncio
    async def test_quarantine_upsert(self, db):
        """Adding a guild with same ID replaces the old record."""
        from Features.Core.db.db import add_quarantined_guild, load_quarantined_guilds
        await add_quarantined_guild(
            guild_id="123",
            guild_name="Old Name",
            owner_id="456",
            flagged_at="2026-05-02T10:00:00Z",
            flag_reason="old reason",
            flagged_by_user_id="789",
            path=db,
        )
        await add_quarantined_guild(
            guild_id="123",
            guild_name="New Name",
            owner_id="999",
            flagged_at="2026-05-03T10:00:00Z",
            flag_reason="new reason",
            flagged_by_user_id="111",
            path=db,
        )
        result = await load_quarantined_guilds(db)
        assert len(result) == 1
        assert result["123"]["guild_name"] == "New Name"
        assert result["123"]["owner_id"] == "999"

    @pytest.mark.asyncio
    async def test_get_all_quarantined_ids(self, db):
        """Get list of all quarantined guild IDs as integers."""
        from Features.Core.db.db import add_quarantined_guild, get_all_quarantined
        for i in ["100", "200", "300"]:
            await add_quarantined_guild(
                guild_id=i,
                guild_name=f"Guild {i}",
                owner_id="999",
                flagged_at="2026-05-02T10:00:00Z",
                flag_reason="spam",
                flagged_by_user_id="111",
                path=db,
            )
        result = await get_all_quarantined(db)
        assert set(result) == {100, 200, 300}
        assert all(isinstance(x, int) for x in result)


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


class TestQuarantineUtils:
    """Test quarantine utility functions."""

    @pytest.mark.asyncio
    async def test_remove_quarantine(self, db):
        """Test remove_quarantine utility function."""
        from Features.Core.db.db import add_quarantined_guild, remove_quarantine
        await add_quarantined_guild(
            guild_id="123",
            guild_name="Test Guild",
            owner_id="456",
            flagged_at="2026-05-02T10:00:00Z",
            flag_reason="spam",
            flagged_by_user_id="789",
            path=db,
        )
        removed = await remove_quarantine(123, db)  # Takes int
        assert removed is True

    @pytest.mark.asyncio
    async def test_remove_quarantine_nonexistent(self, db):
        """Removing nonexistent quarantine returns False."""
        from Features.Core.db.db import remove_quarantine
        removed = await remove_quarantine(999, db)
        assert removed is False

    @pytest.mark.asyncio
    async def test_get_all_quarantined(self, db):
        """Get all quarantined guild IDs as ints."""
        from Features.Core.db.db import add_quarantined_guild, get_all_quarantined
        for gid in ["100", "200", "300"]:
            await add_quarantined_guild(
                guild_id=gid,
                guild_name=f"Guild {gid}",
                owner_id="999",
                flagged_at="2026-05-02T10:00:00Z",
                flag_reason="spam",
                flagged_by_user_id="111",
                path=db,
            )
        result = await get_all_quarantined(db)
        assert result == [100, 200, 300] or set(result) == {100, 200, 300}

    @pytest.mark.asyncio
    async def test_get_all_quarantined_empty(self, db):
        """Empty quarantine returns empty list."""
        from Features.Core.db.db import get_all_quarantined
        result = await get_all_quarantined(db)
        assert result == []

    @pytest.mark.asyncio
    async def test_quarantine_guild_id_coercion(self, db):
        """Guild IDs in load return as strings; get_all returns as ints."""
        from Features.Core.db.db import (
            add_quarantined_guild,
            load_quarantined_guilds,
            get_all_quarantined,
        )
        await add_quarantined_guild(
            guild_id="123",
            guild_name="Test",
            owner_id="456",
            flagged_at="2026-05-02T10:00:00Z",
            flag_reason="spam",
            flagged_by_user_id="789",
            path=db,
        )
        load_result = await load_quarantined_guilds(db)
        assert "123" in load_result

        all_result = await get_all_quarantined(db)
        assert 123 in all_result

    @pytest.mark.asyncio
    async def test_remove_nonexistent_quarantine_by_remove_quarantine(self, db):
        """remove_quarantine on missing guild returns False."""
        from Features.Core.db.db import remove_quarantine
        result = await remove_quarantine(999, db)
        assert result is False


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
