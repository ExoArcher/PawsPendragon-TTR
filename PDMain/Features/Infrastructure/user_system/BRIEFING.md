# Infrastructure/user-system Feature Briefing

## Feature Purpose
Enforce bans and send welcome DMs. On first command use, DM user a welcome message. For banned users, reject them with ephemeral error messages.

## Scope
- First-use welcome DM (one per user, tracked in welcomed_users table)
- Ban enforcement on every command invocation
- Quarantine logic for banned users holding elevated permissions
- Load BANNED_USER_IDS from config and sync to database on startup

## Code to Extract
**From Main-1.5.0/bot.py**
- Lines 976-1000: _maybe_welcome(user, is_dismissed=False)
- Lines 1001-1015: _is_banned(user_id)
- Lines 1016-1027: _reject_if_banned(ctx)
- Ban sync logic from setup_hook (load BANNED_USER_IDS from config and insert into DB)
- Ban database initialization (load banned_users from db.py)
- Quarantine logic (check if banned user holds admin perms in any guild)

## Functionality Details

### _maybe_welcome(user)
- Check if user_id is in welcomed_users set (loaded at startup)
- If not welcomed, send DM with welcome message:
  ```
  "Hello! Welcome to Paws Pendragon. This is an early-access bot..."
  ```
- Add user_id to welcomed_users set and save to DB
- Does not error if user has DMs disabled (graceful failure)

### _is_banned(user_id)
- Check if user_id is in banned_users dict (loaded at startup)
- Return ban record if found, else None

### _reject_if_banned(ctx)
- Call _is_banned(ctx.user.id)
- If banned, send ephemeral message: "You are banned from using this bot. Reason: {reason}"
- Raise error/return early to prevent command execution

## Welcome Message Template
```
"Hello! Welcome to Paws Pendragon, the live Toontown Rewritten Discord bot. 

This is an early-access instance. Commands available: /ttrinfo, /doodleinfo, /calculate, etc.

Need help? Use /helpme."
```

## Dependencies
- Core/db (for load_welcomed, add_welcomed, get_ban, save_banned)
- Core/config (for BANNED_USER_IDS)

## Key Design Patterns
1. **In-memory caching** - welcomed_users and banned_users are loaded at startup and cached
2. **Graceful DM failure** - If user has DMs disabled, silently skip welcome (don't error)
3. **Ephemeral responses** - Ban rejections sent as ephemeral (only visible to user)
4. **One-time per user** - Welcome DM only sent once per user ID

## API Calls
- `user.send(embed=...)` (welcome DM, with try/except for DM failures)
- `ctx.response.send(content=..., ephemeral=True)` (ban rejection)

## Database Access
- load_welcomed() at startup
- add_welcomed(user_id) after sending welcome
- get_ban(user_id) for ban checks
- save_banned(dict) when bans change

## Tests to Verify
- [ ] _maybe_welcome() sends DM to first-time user
- [ ] _maybe_welcome() skips DM for already-welcomed user
- [ ] _maybe_welcome() gracefully handles DM send failure
- [ ] _is_banned() returns ban record for banned user
- [ ] _is_banned() returns None for non-banned user
- [ ] _reject_if_banned() sends ephemeral message for banned user
- [ ] _reject_if_banned() raises/returns early to skip command
- [ ] BANNED_USER_IDS from config are synced to DB at startup
- [ ] welcomed_users set is loaded from DB at startup
- [ ] banned_users dict is loaded from DB at startup

## Special Requirements
- Welcome DM should be guild-agnostic (works in servers, DMs, group chats, User App)
- Ban rejection should be ephemeral (not visible to other users)
- Graceful degradation if user has DMs blocked

## Integration Notes
- _maybe_welcome() is called in every user command handler
- _reject_if_banned() is called at the start of every command handler
- Ban syncing happens during bot.setup_hook() before commands are available
- Welcomed users and banned users are loaded once at startup for performance

## Call Pattern
```python
# In command handler:
await self._reject_if_banned(ctx)  # Reject if banned
await self._maybe_welcome(ctx.user)  # Send welcome if first-time
# ... rest of command logic
```

## Reference Implementation
See Main-1.5.0/bot.py lines 976-1027 for the complete original implementation.
