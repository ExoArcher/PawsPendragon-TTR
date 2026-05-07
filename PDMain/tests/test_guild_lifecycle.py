"""Async pytest tests for guild_lifecycle.py - cache/DB atomicity."""
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from Features.Core.db.db import init_db, add_guild_to_allowlist, load_allowlist
from Features.Infrastructure.guild_lifecycle.guild_lifecycle import (
    GuildLifecycleManager,
)
from Features.Infrastructure import cache_manager


@pytest_asyncio.fixture
async def db():
    """Fixture providing a fresh SQLite database for each test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = Path(tmp.name)

    await init_db(db_path)

    yield db_path

    db_path.unlink(missing_ok=True)


@pytest_asyncio.fixture
def mock_bot():
    """Fixture providing a mock Discord bot."""
    bot = MagicMock()
    bot.is_guild_allowed = MagicMock(return_value=True)
    bot.state = {}
    return bot


@pytest_asyncio.fixture
def mock_config():
    """Fixture providing a mock Config."""
    config = MagicMock()
    config.guild_allowlist = []
    return config


@pytest_asyncio.fixture
async def manager(mock_bot, mock_config):
    """Fixture providing a GuildLifecycleManager instance."""
    return GuildLifecycleManager(mock_bot, mock_config)


class TestAtomicGuildJoinAddition:
    """Test atomic guild addition to allowlist (cache + DB)."""

    @pytest.mark.asyncio
    async def test_db_write_failure_prevents_cache_update(self, manager, db):
        """Cache should NOT be updated if DB write fails."""
        guild_id = 123456789

        # Clear cache
        cache_manager.GUILD_ALLOWLIST.clear()
        assert guild_id not in cache_manager.GUILD_ALLOWLIST

        # Mock db.add_guild_to_allowlist to raise an exception
        with patch('Features.Infrastructure.guild_lifecycle.guild_lifecycle.db') as mock_db:
            mock_db.add_guild_to_allowlist = AsyncMock(
                side_effect=Exception("DB connection failed")
            )

            # Call the atomic function
            result = await manager._add_guild_to_allowlist_atomic(guild_id, db)

            # Should return False on failure
            assert result is False

            # Cache should still be empty (not updated on failure)
            assert guild_id not in cache_manager.GUILD_ALLOWLIST


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

        # Should return True on success
        assert result is True

        # Cache should be updated
        assert guild_id in cache_manager.GUILD_ALLOWLIST

        # DB should be updated
        after = await load_allowlist(db)
        assert guild_id in after


    @pytest.mark.asyncio
    async def test_on_guild_join_calls_atomic_helper_on_allowed_guild(self, manager, db):
        """on_guild_join should call _add_guild_to_allowlist_atomic for allowed guilds."""
        guild_id = 111111111

        # Create a mock guild
        mock_guild = MagicMock()
        mock_guild.id = guild_id
        mock_guild.name = "Test Guild"
        mock_guild.owner = MagicMock()

        # Mock the manager's allowlist check to return True
        manager.is_guild_allowed = MagicMock(return_value=True)

        # Patch the atomic helper and sync commands
        with patch.object(
            manager, '_add_guild_to_allowlist_atomic', new_callable=AsyncMock
        ) as mock_atomic:
            mock_atomic.return_value = True

            with patch.object(
                manager, '_sync_commands_to_guild', new_callable=AsyncMock
            ):
                await manager.on_guild_join(mock_guild)

                # Verify atomic helper was called
                mock_atomic.assert_called_once()


    @pytest.mark.asyncio
    async def test_on_guild_join_leaves_guild_if_not_allowed(self, manager):
        """on_guild_join should leave non-allowed guilds without updating allowlist."""
        guild_id = 222222222

        # Create a mock guild
        mock_guild = MagicMock()
        mock_guild.id = guild_id
        mock_guild.name = "Disallowed Guild"
        mock_guild.owner = MagicMock()

        # Mock the manager's allowlist check to return False
        manager.is_guild_allowed = MagicMock(return_value=False)

        # Patch the notify_and_leave method
        with patch.object(
            manager, '_notify_and_leave', new_callable=AsyncMock
        ) as mock_leave:
            with patch.object(
                manager, '_add_guild_to_allowlist_atomic', new_callable=AsyncMock
            ) as mock_atomic:
                await manager.on_guild_join(mock_guild)

                # Verify notify_and_leave was called
                mock_leave.assert_called_once_with(mock_guild)

                # Verify atomic helper was NOT called
                mock_atomic.assert_not_called()


@pytest.mark.asyncio
async def test_on_guild_remove_calls_delete_guild_completely(tmp_path):
    """on_guild_remove should call delete_guild_completely to clean DB."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch
    from Features.Infrastructure.guild_lifecycle.guild_lifecycle import GuildLifecycleManager
    from Features.Core.db import db as db_module

    db_path = tmp_path / "test.db"
    await db_module.init_db(db_path)

    bot = MagicMock()
    bot.state = {"guilds": {"99999": {"information": {"channel_id": 1, "message_ids": []}}}, "allowlist": [99999], "announcements": []}
    bot._save_state = AsyncMock()
    config = MagicMock()
    config.guild_allowlist = frozenset()

    manager = GuildLifecycleManager(bot, config)

    guild = MagicMock()
    guild.id = 99999
    guild.name = "TestGuild"

    with patch("Features.Infrastructure.guild_lifecycle.guild_lifecycle.db") as mock_db:
        mock_db.delete_guild_completely = AsyncMock()
        mock_db.DB_PATH = db_path
        await manager.on_guild_remove(guild)
        mock_db.delete_guild_completely.assert_called_once_with(99999)
