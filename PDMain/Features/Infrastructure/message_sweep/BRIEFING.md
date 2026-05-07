# Infrastructure/message-sweep Feature Briefing

## Feature Purpose
Periodically clean up stale bot messages (embeds) that are no longer being tracked. Runs every 15 minutes to delete orphaned messages and keep channels tidy.

## Scope
- Background task running every 15 minutes
- Scan each tracked guild's channels for bot messages
- Delete messages NOT in the known message ID set from state
- Handle missing channels and permission errors gracefully
- Clean up expired announcements (if integrated)

## Code to Extract
**From Main-1.5.0/bot.py**
- Lines with `_sweep_loop` background task
- Sweep logic for iterating guild channels
- Message deletion with permission/not-found handling
- Stale message ID detection (messages not in known set)

## Sweep Flow
```
Every 15 minutes:
  For each tracked guild:
    For each tracked channel (information, doodles, calculator):
      Get all messages from bot
      Delete if message ID not in state["guilds"][guild_id][feed_key]["message_ids"]
      Skip if channel missing or no Send/Delete perms
```

## Message ID Tracking
- Known message IDs come from: `state["guilds"][guild_id][feed_key]["message_ids"]`
- Suit calculator uses: `state["guilds"][guild_id]["suit_calculator"]["message_ids"]`
- Any message posted by bot but not in this set is considered stale

## Dependencies
- Core/config (guild state access, feed channel names)
- Core/db (load state with known message IDs)
- discord.py library

## Key Design Patterns
1. **@tasks.loop decorator** - Background task running periodically
2. **Negative logic** - Delete if NOT in known set (safe from accidents)
3. **Graceful failures** - Skip missing channels, handle permission errors
4. **Idempotent** - Safe to run multiple times
5. **State-based cleanup** - Use known message IDs as source of truth

## API Calls
- `guild.get_channel(channel_id)` - Get tracked channel
- `channel.history(limit=100)` - Fetch recent bot messages
- `message.delete()` - Delete stale message
- Discord history API for message iteration

## Database Access
- Read state["guilds"] to get known message IDs per guild/feed
- Update state["guilds"] to remove deleted message IDs
- Save state after cleanup

## Tests to Verify
- [ ] _sweep_loop runs every 15 minutes
- [ ] Stale messages are deleted from tracked channels
- [ ] Messages in known set are NOT deleted
- [ ] Missing channels are skipped gracefully
- [ ] Permission errors (no Delete perm) are logged and skipped
- [ ] NotFound errors (already deleted) are handled
- [ ] State is updated after deletion
- [ ] Multiple guilds are swept without cross-contamination

## Special Requirements
- 15-minute interval is configurable (SWEEP_INTERVAL env var, default 15*60 seconds)
- Only delete bot's own messages (check message author)
- Must handle rate limiting (may need delays between deletes)
- Safe to run even if guild is no longer in allowlist

## Integration Notes
- Started in on_ready() via self._sweep_loop.start()
- Uses @tasks.loop(seconds=...) decorator from discord.ext.tasks
- Runs independently of refresh loop
- Should run last (after other tasks complete) to avoid conflicts

## File Paths
- Stale messages may exist in any channel the bot has posted to
- Focus on: #tt-info, #tt-doodles, #suit-calc (main tracked channels)

## Error Handling
- discord.NotFound - Message already deleted, skip
- discord.Forbidden - No Delete permission, log warning and skip
- discord.HTTPException - Rate limit or other error, continue to next message
- Missing channel - Log and skip guild

## Reference Implementation
See Main-1.5.0/bot.py for _sweep_loop() implementation (~100+ lines).
