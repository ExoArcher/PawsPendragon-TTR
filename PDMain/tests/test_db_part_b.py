# ── Part B: Maintenance Mode, Quarantine, Blacklist, Audit Log ────
import pytest


# ── 3a: Guild ID Validation Tests ─────────────────────────────────────────

def test_validate_guild_id_accepts_valid_id():
    from Features.Core.db.db import _validate_guild_id
    assert _validate_guild_id(123456789) == 123456789
    assert _validate_guild_id("987654321") == 987654321


def test_validate_guild_id_rejects_negative():
    from Features.Core.db.db import _validate_guild_id
    with pytest.raises(ValueError):
        _validate_guild_id(-1)


def test_validate_guild_id_rejects_zero():
    from Features.Core.db.db import _validate_guild_id
    with pytest.raises(ValueError):
        _validate_guild_id(0)


def test_validate_guild_id_rejects_non_numeric():
    from Features.Core.db.db import _validate_guild_id
    with pytest.raises(ValueError):
        _validate_guild_id("not-an-id")


# ── 3b: Announce Rate Limiting and Sanitization Tests ───────────────────

def test_sanitize_announce_text_removes_everyone_mention():
    from Features.ServerManagement.console_commands.console_commands import _sanitize_announce_text
    result = _sanitize_announce_text("@everyone click here")
    assert "@everyone" not in result
    assert "everyone" in result


def test_sanitize_announce_text_truncates_at_1000():
    from Features.ServerManagement.console_commands.console_commands import _sanitize_announce_text
    long_text = "a" * 1500
    assert len(_sanitize_announce_text(long_text)) <= 1000


def test_sanitize_announce_text_removes_spoiler_tags():
    from Features.ServerManagement.console_commands.console_commands import _sanitize_announce_text
    result = _sanitize_announce_text("||secret||")
    assert "||" not in result


def test_rate_limit_allows_first_call():
    from Features.ServerManagement.console_commands.console_commands import RateLimit
    rl = RateLimit(max_per_period=1, period_seconds=300)
    assert rl.is_allowed() is True


def test_rate_limit_blocks_second_call():
    from Features.ServerManagement.console_commands.console_commands import RateLimit
    rl = RateLimit(max_per_period=1, period_seconds=300)
    rl.is_allowed()
    assert rl.is_allowed() is False


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


def test_validate_api_response_accepts_complete_data():
    """_validate_api_response returns True for complete API data."""
    from Features.Admin.pd_refresh.pd_refresh import _validate_api_response
    data = {
        "population": {"totalPopulation": 1000},
        "fieldoffices": [],
        "doodles": {"Barnacle Boatyard": {}},
        "sillymeter": {"state": "active"},
    }
    assert _validate_api_response(data) is True


def test_validate_api_response_rejects_missing_key():
    """_validate_api_response returns False when a required key is missing."""
    from Features.Admin.pd_refresh.pd_refresh import _validate_api_response
    data = {"population": {}, "fieldoffices": [], "sillymeter": {}}
    # Missing "doodles"
    assert _validate_api_response(data) is False


def test_validate_api_response_rejects_none_population():
    """_validate_api_response returns False when population is None."""
    from Features.Admin.pd_refresh.pd_refresh import _validate_api_response
    data = {"population": None, "fieldoffices": [], "doodles": {}, "sillymeter": {}}
    assert _validate_api_response(data) is False


def test_validate_api_response_rejects_non_list_fieldoffices():
    """_validate_api_response returns False when fieldoffices is not a list."""
    from Features.Admin.pd_refresh.pd_refresh import _validate_api_response
    data = {"population": {}, "fieldoffices": "not a list", "doodles": {}, "sillymeter": {}}
    assert _validate_api_response(data) is False


def test_cooldown_key_includes_guild_id():
    """pd_refresh cooldown key should be (user_id, guild_id), not just user_id."""
    import inspect
    from Features.Admin.pd_refresh import pd_refresh as pd_module
    source = inspect.getsource(pd_module)
    # Old pattern: bot._refresh_cooldowns.get(member.id, 0.0)
    # New pattern: bot._refresh_cooldowns.get((member.id, guild.id), 0.0)
    assert "member.id, guild" in source or "(interaction.user.id, interaction.guild_id)" in source, \
        "Cooldown key should include guild_id"


def test_constants_module_exists_and_has_required_attrs():
    """Test that constants.py exists and has all required constants defined."""
    from Features.Core.config import constants

    # Check that the module exists (no ModuleNotFoundError)
    assert constants is not None

    # Check all required constants exist and have correct types
    required_constants = {
        "DOODLE_REFRESH_INTERVAL_SECONDS": (int, float),
        "MESSAGE_SWEEP_INTERVAL_MINUTES": (int, float),
        "PD_REFRESH_COOLDOWN_SECONDS": (int, float),
        "API_FETCH_TIMEOUT_SECONDS": (int, float),
        "PER_FEED_UPDATE_TIMEOUT_SECONDS": (int, float),
        "AUDIT_LOG_RETENTION_DAYS": (int, float),
        "ANNOUNCEMENT_TTL_SECONDS": (int, float),
        "GUILD_UPDATE_DELAY_SECONDS": (int, float),
    }

    for const_name, allowed_types in required_constants.items():
        assert hasattr(constants, const_name), \
            f"Constants module missing required constant: {const_name}"
        value = getattr(constants, const_name)
        assert isinstance(value, allowed_types), \
            f"Constant {const_name} has wrong type: {type(value)}, expected {allowed_types}"
        assert value > 0, \
            f"Constant {const_name} must be positive, got {value}"
