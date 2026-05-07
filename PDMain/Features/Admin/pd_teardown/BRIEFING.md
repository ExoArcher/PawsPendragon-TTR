# Admin/pd-teardown Command Briefing

## Feature Purpose
Stop tracking a guild's live feeds. Remove guild from database (channels remain, no longer updated). Log teardown event to teardown_log.txt for auditing.

## Scope
- Slash command: `/pd-teardown`
- Remove guild from state["guilds"]
- Save state to database
- Log teardown event with guild info (ID, name, owner)
- Admin-only (requires Manage Channels + Manage Messages)

## Code to Extract
**From Main-1.5.0/bot.py**
- `@app_commands.command(name="pd-teardown")` handler
- Guild removal from state["guilds"]
- Teardown logging to teardown_log.txt

## Teardown Flow
```
1. User invokes /pd-teardown with Manage Channels + Manage Messages
2. Remove guild from state["guilds"][guild_id]
3. Save state to database
4. Append to teardown_log.txt: guild_id, guild_name, owner_name, owner_id, invoker_name, invoker_id, timestamp
5. Send ephemeral response: "Teardown complete"
```

## Teardown Log Format
Line format (tab-separated or structured):
```
[timestamp] guild_id=123456 guild_name="My Server" owner_name="John#1234" owner_id=987654 invoker_name="Admin#5678" invoker_id=555666
```

File: `teardown_log.txt` (append-only, at project root)

## State Cleanup
- state["guilds"][guild_id] completely removed
- state["allowlist"] unchanged (guild can still be added again later)
- No guild data remains in database after teardown

## Dependencies
- Core/db (remove guild from state, save state)
- Core/config (permission checks)
- discord.py library
- pathlib or os for log file handling

## Key Design Patterns
1. **Non-destructive channels** - Channels remain, just no longer updated
2. **Audit trail** - Log all teardown events for compliance
3. **Idempotent** - Safe to run even if guild not in state
4. **Atomic** - Save state only after all checks pass
5. **Permission check** - User must have Manage Channels + Manage Messages

## API Calls
- `ctx.guild.id`, `ctx.guild.name`, `ctx.author.name`
- `ctx.guild.owner` - Get guild owner info
- File append operation for teardown_log.txt

## Database Access
- Load state
- Remove state["guilds"][guild_id]
- Save state atomically

## Tests to Verify
- [ ] Guild removed from state["guilds"]
- [ ] State saved after removal
- [ ] Teardown event logged to teardown_log.txt
- [ ] Log includes: guild_id, guild_name, owner_name, owner_id
- [ ] Log includes: invoker_name, invoker_id, timestamp
- [ ] Teardown log is append-only (no truncation)
- [ ] Channels remain in Discord (not deleted)
- [ ] Ephemeral response sent
- [ ] Permission checks enforced

## Special Requirements
- Teardown log is append-only (never overwritten)
- Log format should be consistent and parseable
- Guild can be re-added to allowlist after teardown
- Channels are NOT deleted (manual cleanup only)

## Integration Notes
- Slash command handler in bot.py
- Called by guild admin to stop tracking
- Teardown log useful for audit and troubleshooting

## Error Handling
- Forbidden if user lacks required permissions
- Guild not in state - still log (idempotent)
- File write failures - log warning but don't crash

## File Paths
- Log file: `teardown_log.txt` at project root

## Reference Implementation
See Main-1.5.0/bot.py for complete pd-teardown command handler.
