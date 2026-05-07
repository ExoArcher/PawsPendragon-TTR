# ServerManagement/console-commands Feature Briefing

## Feature Purpose
Handle stdin console commands from hosting panel. Restricted to BOT_ADMIN_IDs. Supports: stop, restart, maintenance, announce, help.

## Scope
- Background stdin reader task
- Parse console commands: stop, restart, maintenance, announce
- Verify admin authorization (BOT_ADMIN_IDs)
- Execute actions: notify guilds, update maintenance state, broadcast announcements
- Graceful shutdown for stop/restart
- Log all console commands

## Code to Extract
**From Main-1.5.0/bot.py and Console.py**
- `@tasks.loop()` stdin reader task
- Command parsing and validation
- Admin authorization check
- `stop` command handler - notify guilds, shutdown gracefully
- `restart` command handler - notify guilds, hot-restart via os.execv
- `maintenance` command handler - toggle maintenance embed across all guilds
- `announce <text>` command handler - broadcast announcement to all guilds' #tt-info
- `help` command handler - list available commands
- Integration via `run_console(bot)` at startup

## Command Flow
```
On bot startup:
  1. Start background stdin reader task
  
When command received:
  1. Read line from stdin
  2. Parse command and arguments
  3. Check if invoker_id in BOT_ADMIN_IDS
  4. Route to handler:
     - stop: notify all tracked guilds → shutdown gracefully
     - restart: notify all tracked guilds → os.execv restart
     - maintenance: toggle maintenance embed in all guilds' channels
     - announce <text>: broadcast to all #tt-info channels (30-min TTL)
     - help: print command list
  5. Log action to stdout/file
```

## Command Specifications

### stop
```
stop
```
Notify all tracked guilds with goodbye message, then shut down gracefully.
Response: Print status to stdout, then exit process.

### restart
```
restart
```
Notify all tracked guilds, then hot-restart via `os.execv(sys.executable, [sys.executable, 'bot.py'] + sys.argv[1:])`.
Response: Print status to stdout, then replace process.

### maintenance
```
maintenance
```
Toggle maintenance mode. If OFF, post orange maintenance embed to all guilds' channels. If ON, remove embeds and turn off.
Response: Print "Maintenance mode enabled/disabled" to stdout.

### announce
```
announce This is an announcement text
```
Broadcast to all guilds' #tt-info channels. Message auto-deletes after 30 minutes.
Response: Print "Announcement broadcast to N guilds" to stdout.

### help
```
help
```
List all available console commands.
Response: Print command list to stdout.

## Dependencies
- Infrastructure/announcements-maintenance (for announce command)
- Infrastructure/live-feeds (for maintenance toggle)
- Core/db (for guild iteration and state)
- discord.py library
- os, sys (for process management)

## Key Design Patterns
1. **Background task** - Runs continuously, doesn't block bot
2. **Admin-only** - All commands require BOT_ADMIN_IDs authorization
3. **All-or-nothing broadcast** - Notify all tracked guilds, continue on individual failures
4. **Graceful shutdown** - Notify users before stop/restart
5. **Logging** - All commands logged with timestamp and invoker_id
6. **Non-blocking stdin** - Use async stdin reader, don't freeze event loop

## API Calls
- guild.text_channels[0].send(embed=...) for notifications
- db operations for guild iteration
- os.execv for restart
- sys.exit(0) for stop

## Database Access
- Iterate state["guilds"] for all tracked guilds
- Update maintenance_mode state via db
- Create/delete announcement records

## Tests to Verify
- [ ] stdin reader task starts on bot startup
- [ ] Admin check prevents non-admin usage
- [ ] stop command notifies guilds then exits
- [ ] restart command notifies guilds then restarts
- [ ] maintenance toggle creates/removes orange embeds
- [ ] announce broadcasts to all #tt-info channels
- [ ] announce creates 30-minute TTL record
- [ ] help lists all commands
- [ ] Commands logged with timestamp and invoker
- [ ] Invalid commands ignored gracefully

## Special Requirements
- Console commands restricted to BOT_ADMIN_IDs from config
- All commands must complete within reasonable time
- Notifications should be clear and visible to guild members
- maintenance toggle must be idempotent (safe to run twice)
- announce must respect 30-minute TTL via announcements system

## Integration Notes
- Registered via `run_console(bot)` at bot startup
- Runs in background (doesn't block Discord event loop)
- Called via hosting panel stdin (Cybrancee)
- All actions logged for audit trail

## Error Handling
- Invalid command - Log warning, ignore
- Missing guild/channel - Continue (log warning, skip)
- Admin check failure - Reject with permission error
- Broadcast partial failure - Log individual errors, notify of successful count
- stdin read error - Log warning, continue

## Response Messages
```
# stop
[timestamp] INFO: Notifying 3 guilds before shutdown
[timestamp] INFO: Shutdown complete

# restart
[timestamp] INFO: Notifying 3 guilds before restart
[timestamp] INFO: Restarting process...

# maintenance ON
[timestamp] INFO: Maintenance mode enabled in 3 guilds

# maintenance OFF
[timestamp] INFO: Maintenance mode disabled in 3 guilds

# announce
[timestamp] INFO: Broadcast announcement to 3 guilds (30-min TTL)

# help
Available console commands:
  stop - Shutdown gracefully after notifying guilds
  restart - Hot-restart the bot
  maintenance - Toggle maintenance mode
  announce <text> - Broadcast announcement (30-min TTL)
  help - Show this list
```

## Reference Implementation
See Main-1.5.0/bot.py and Main-1.5.0/Console.py for complete console command implementation.
