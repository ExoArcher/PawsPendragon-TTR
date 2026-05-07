# Admin/pd-refresh Command Briefing

## Feature Purpose
Force an immediate data refresh, update all embeds, refresh suit calculator, and sweep stale messages. Useful for testing or manual updates without waiting 90 seconds.

## Scope
- Slash command: `/pd-refresh`
- Call _refresh_once(force_doodles=True) immediately
- Call _sweep_loop once immediately
- Update suit calculator embeds for caller's guild
- Send ephemeral response to user
- Admin-only (requires Manage Channels + Manage Messages)

## Code to Extract
**From Main-1.5.0/bot.py**
- `@app_commands.command(name="pd-refresh")` handler
- Call to _refresh_once() with force_doodles=True
- Call to _sweep_loop() or _sweep_once() for this guild
- Suit calculator update logic
- Response messaging

## Refresh Flow
```
1. User invokes /pd-refresh
2. Force _refresh_once(force_doodles=True) immediately
   - Fetches all 4 TTR endpoints
   - Updates all feeds for all guilds
   - Includes doodles even if within 12-hour window
3. Force sweep for this guild
   - Delete stale messages
4. Update suit calculator embeds for this guild
5. Send ephemeral response: "Refreshed! All embeds updated."
```

## Force Doodles
When force_doodles=True:
- Reset _last_doodle_refresh to force doodle update
- Update doodle embeds even if within 12-hour throttle window

## Suit Calculator Update
- Call _ensure_suit_calculator_pin() for caller's guild
- This edits/reposts all 4 suit calculator embeds
- Updates suit threads with latest data

## Dependencies
- Infrastructure/live-feeds (_refresh_once, _sweep_once)
- Infrastructure/message-sweep (sweep logic)
- Admin/pd-setup (_ensure_suit_calculator_pin)
- discord.py library

## Key Design Patterns
1. **Force fetch** - Ignore doodle throttle, fetch all endpoints
2. **Immediate** - No waiting for next scheduled run
3. **Guild-scoped sweep** - Sweep only for caller's guild
4. **Suit calculator update** - Refresh static tables
5. **Ephemeral response** - Only visible to caller

## API Calls
- Call internal bot methods for refresh and sweep
- message.edit() for updating embeds

## Database Access
- Load state for caller's guild
- Update message IDs after editing
- Save state after changes

## Tests to Verify
- [ ] /pd-refresh triggers immediate _refresh_once()
- [ ] Force_doodles=True bypasses 12-hour throttle
- [ ] All 4 endpoints fetched even if recent
- [ ] Doodle embeds updated immediately
- [ ] Sweep runs for caller's guild
- [ ] Suit calculator embeds refreshed
- [ ] Suit threads updated
- [ ] Ephemeral response sent
- [ ] Permission checks enforced

## Special Requirements
- Force doodle refresh even if within 12-hour window
- Only refresh caller's guild (not all guilds)
- Response should be quick (async/await properly)
- Permission check: Manage Channels AND Manage Messages

## Integration Notes
- Slash command handler in bot.py
- Called by guild admin for manual refresh
- Useful for testing or urgent updates
- Safe to call multiple times

## Error Handling
- Missing guild in state - create it (optional enhancement)
- Forbidden if user lacks permissions
- Timeout if refresh takes too long - set reasonable timeout

## Reference Implementation
See Main-1.5.0/bot.py for complete pd-refresh command handler.
