# Infrastructure/announcements-maintenance Feature Briefing

## Feature Purpose
Manage temporary announcement messages broadcast to all tracked guilds with automatic expiry cleanup. Announcements auto-delete after 30 minutes or can be deleted manually via console commands.

## Scope
- Broadcast announcements to all guilds' #tt-info channels
- Track announcement message IDs with expiry timestamps in database
- Clean up expired announcements automatically (sweep loop)
- Support console command `announce <text>` for broadcasting
- Graceful handling of missing channels or perms

## Code to Extract
**From Main-1.5.0/bot.py**
- Announcement-related state management (announcements table structure)
- Console command `announce <text>` handler
- Sweep loop logic for expired announcements
- Broadcast logic to all tracked guild channels
- Announcement record creation and cleanup

## Announcement Flow
```
1. Console command: announce "Hello everyone"
2. Bot posts message to each tracked guild's #tt-info
3. Store message ID + expiry (now + 30 mins) in DB
4. Every 15 minutes, sweep loop deletes expired announcements
5. Auto-cleanup of DB records for deleted messages
```

## Database Schema
**announcements table:**
```sql
CREATE TABLE IF NOT EXISTS announcements (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL,
    message_id  INTEGER NOT NULL UNIQUE,
    expires_at  REAL    NOT NULL
);
```

## Dependencies
- Core/db (save announcements to database, load/cleanup on sweep)
- Core/config (guild channel names, feed_key mappings)
- discord.py library

## Key Design Patterns
1. **Expiry-based cleanup** - Track expires_at timestamp, delete when passed
2. **All-or-nothing** - Send to all guilds or abort gracefully
3. **Stale message handling** - Skip deleted messages in sweep
4. **Broadcast pattern** - Send to all guilds' #tt-info channels

## API Calls
- `guild.get_channel(channel_id).send(content=...)` - Send announcement
- `message.delete()` - Delete expired announcement
- Database reads/writes for announcement tracking

## Database Access
- Load announcements from DB at startup
- Create announcement record with expiry
- Delete expired announcements on schedule
- Read state["announcements"] for all tracked announcements

## Tests to Verify
- [ ] Announcement posted to all tracked guilds
- [ ] Message ID + expiry stored in database
- [ ] Expired announcements deleted after 30 minutes
- [ ] Stale message IDs handled gracefully
- [ ] console command `announce <text>` triggers broadcast
- [ ] Empty/invalid channels skipped without crashing
- [ ] Sweep loop finds and deletes only expired announcements

## Special Requirements
- 30-minute expiry time is hardcoded (1800 seconds)
- Broadcast should use channel name from config (e.g., "tt-info")
- Graceful failure if channel is missing or bot lacks Send perms

## Integration Notes
- Broadcast logic called from console command handler
- Sweep loop runs every 15 minutes (same as message sweep)
- Announcements are stored in database and loaded on startup

## Reference Implementation
See Main-1.5.0/bot.py for console command and sweep loop announcement cleanup logic.
