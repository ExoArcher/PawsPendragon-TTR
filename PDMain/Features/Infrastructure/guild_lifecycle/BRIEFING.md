# Infrastructure/guild-lifecycle Feature Briefing

## Feature Purpose
Handle guild join/leave events, enforce allowlist, sync commands per-guild, and clean up stale guild state. Ensures only allowlisted guilds can use the bot.

## Scope
- **Guild join** - Bot joins guild; check allowlist; leave + notify owner if not allowed
- **Guild removal** - Clean up guild state from memory
- **on_ready** - Sync allowlist across live guilds, prune departed guilds from state, sync commands per-guild
- **Command syncing** - Register commands per-guild (prevents global + guild duplicates in Discord UI)
- **Allowlist enforcement** - Union of env var GUILD_ALLOWLIST + runtime allowlist from DB

## Code to Extract
**From Main-1.5.0/bot.py**
- Lines 201-206: is_guild_allowed(guild_id) - check effective allowlist
- Lines 255-300: on_ready() - full guild sync, allowlist check, state cleanup
- Lines 318-343: _sync_commands_to_guild(guild) - per-guild command sync
- Lines 344-405: _notify_and_leave(guild) - send closed-access message, leave guild
- on_guild_join(guild) - event handler for guild join
- on_guild_remove(guild) - event handler for guild leave

## Allowlist Logic
**Effective allowlist = GUILD_ALLOWLIST (env var) ∪ runtime allowlist (from DB)**
- Static allowlist comes from config.guild_allowlist
- Runtime allowlist comes from state["allowlist"] (persisted in DB)
- Union of both is the effective allowlist

## Guild Lifecycle

### 1. Guild Join
```
Bot invited to guild →
  Check is_guild_allowed(guild.id) →
    If not allowed:
      Send owner DM with closed-access message
      Leave guild
    If allowed:
      Continue to on_ready
```

### 2. on_ready (first run or bot restart)
```
on_ready triggered →
  Log bot login and stats
  For each live guild:
    If not allowlisted:
      Leave guild + notify owner
    Else:
      Sync commands to this guild
  Prune state for departed guilds
  Cleanup stale data
```

### 3. Guild Leave
```
Guild removed bot or bot left →
  Remove guild from state (pruned by on_ready)
```

## Closed Access Message
Sent to guild owner if bot is not allowlisted:
```
"Hello! Thank you for your enthusiasm to have me join your community! 
At this time I am only in closed access -- please DM **ExoArcher** on 
Discord (user ID `310233741354336257`) to request access."
```

## Command Syncing
Per-guild registration prevents Discord UI duplication:
```python
# Clear any stale commands in this guild
self.tree.clear_commands(guild=guild)
# Sync current command set to this guild
await self.tree.sync(guild=guild)
```

## Dependencies
- Core/config (for guild_allowlist and allowlist validation logic)
- Core/db (guild_feeds table for state cleanup)

## Key Design Patterns
1. **Allowlist union** - Effective allowlist is env + runtime combined
2. **Per-guild syncing** - Prevents global command duplication in Discord UI
3. **State cleanup** - Prune state for guilds that departed
4. **Graceful DM** - Notify owner of closed access before leaving
5. **on_ready idempotency** - Safe to run multiple times (e.g., reconnects)

## API Calls
- `guild.owner.send(content=...)` - Send DM to guild owner
- `guild.leave()` - Remove bot from guild
- `self.tree.clear_commands(guild=guild)` - Clear guild commands
- `self.tree.sync(guild=guild)` - Sync commands to guild
- `discord.Guild` event handlers (on_guild_join, on_guild_remove, on_ready)

## Database Access
- Read state["guilds"] to track which guilds are in state
- Prune state entries for guilds no longer in self.guilds
- Read allowlist table to check runtime allowlist

## Tests to Verify
- [ ] is_guild_allowed() returns True for env-allowlist guilds
- [ ] is_guild_allowed() returns True for runtime-allowlist guilds
- [ ] is_guild_allowed() returns False for non-allowlisted guilds
- [ ] on_guild_join() checks allowlist before continuing
- [ ] _notify_and_leave() sends owner DM then leaves
- [ ] on_ready() prunes state for departed guilds
- [ ] on_ready() leaves non-allowlisted guilds
- [ ] _sync_commands_to_guild() clears and syncs commands
- [ ] Effective allowlist is union of env + DB

## Special Requirements
- Closed-access message should mention ExoArcher (hardcoded user ID)
- Command syncing should prevent guild + global duplication
- State cleanup should be safe (idempotent)

## Integration Notes
- is_guild_allowed() is called frequently throughout the bot
- on_ready() runs on bot startup and on reconnect
- _sync_commands_to_guild() is called for each live guild
- Effective allowlist affects bot behavior in every event handler

## Event Flow
```
1. Bot boots → setup_hook() runs
2. Bot connects to Discord → on_ready() runs
   - Syncs commands per-guild
   - Prunes departed guilds
   - Enforces allowlist
3. Bot invited to new guild → on_guild_join() runs
   - Checks allowlist
   - Leaves + notifies if not allowed
4. Bot removed from guild → on_guild_remove() runs (handled by on_ready prune)
```

## Reference Implementation
See Main-1.5.0/bot.py lines 201-405 and on_ready/on_guild_join/on_guild_remove handlers.
