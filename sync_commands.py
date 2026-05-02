"""
sync_commands.py — One-time global command sync for Paws Pendragon TTR.

Logs in as the real bot, calls tree.sync() ONCE, then exits cleanly.
Run this after making command changes:
    cd PDMain && python sync_commands.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import discord
from discord import app_commands
from Features.Core.config.config import Config


async def sync():
    config = Config.load()

    # We need a real TTRBot with all commands registered.
    # Import here (after path setup) to avoid circular issues.
    from bot import TTRBot

    class SyncBot(TTRBot):
        async def setup_hook(self):
            # Load DB minimally (needed for Config usage inside commands)
            from Features.Core.db import db
            await db.init_db()
            self.state = self._empty_state()

            from Features.Core.ttr_api.ttr_api import TTRApiClient
            self._api = TTRApiClient(self.config.user_agent)

            self._register_commands()
            print("[sync] Commands registered in tree. Syncing to Discord...")
            synced = await self.tree.sync()
            print(f"[sync] Successfully synced {len(synced)} global command(s):")
            for cmd in synced:
                print(f"   /{cmd.name}")

        async def on_ready(self):
            print(f"[sync] Logged in as {self.user}. Sync complete — closing.")
            await self.close()

    bot = SyncBot(config)
    await bot.start(config.token)


if __name__ == "__main__":
    print("=" * 50)
    print("Paws Pendragon - Global Command Sync")
    print("=" * 50)
    asyncio.run(sync())
