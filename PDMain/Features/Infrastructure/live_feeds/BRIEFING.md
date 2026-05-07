# Infrastructure/live-feeds Feature Briefing

## Feature Purpose
Background task that periodically fetches live TTR data and updates Discord embeds in tracked guilds. Runs every 90 seconds (configurable). Core of the "live" experience.

## Scope
- **Refresh loop** (90-second cycle)
  - Fetch all 4 enabled TTR endpoints in parallel
  - For each tracked guild, call _update_feed() to edit pinned messages
  - Respect 3-second delays between consecutive edits (rate limiting)
  - Throttle doodles to once every 12 hours unless forced via /pd-refresh
- **Feed updates**
  - Edit pinned messages in place with new embed data
  - Handle stale message IDs gracefully (skip if message not found)
  - Apply rate limiting (3 seconds between edits to same guild)
- **Panel announcements**
  - Check for panel_announce.txt every 90 seconds
  - Broadcast contents to all guilds' #tt-info channel
  - Delete the file after broadcasting

## Code to Extract
**From Main-1.5.0/bot.py**
- Lines 146-168: TTRBot class initialization (refresh loop task, timestamps)
- Lines 581-713: _refresh_loop() - background task decorator
- Lines 590-595: API_KEYS constant (feed_key → API endpoint mapping)
- Lines 598-610: _fetch_all() - fetch all 4 endpoints in parallel via ttr_api
- Lines 612-680: _refresh_once() - main refresh logic per guild
- Lines 681-713: _update_feed(guild_id, feed_key) - edit pinned messages
- Lines 721-740: _check_panel_announce() - read and broadcast panel_announce.txt

## TTR Endpoints Used
```python
API_KEYS = {
    "information": "population",  # Uses population + fieldoffices
    "doodles": "doodles",
    "sillymeter": "sillymeter",
    # "invasions": NEVER USED (no building data)
}
```

## Refresh Loop Timing
- **Interval**: Every 90 seconds (configurable via REFRESH_INTERVAL env var)
- **Doodle throttle**: Only update doodles every 12 hours (DOODLE_REFRESH_INTERVAL = 12 * 60 * 60)
- **Rate limiting**: 3-second delays between consecutive edits to same guild
- **Panel announcements**: Check every 90 seconds for panel_announce.txt

## Dependencies
- Core/ttr-api (TTRApiClient for fetching endpoints)
- Core/formatters (FORMATTERS dict for building embeds)
- Core/db (guild_feeds table for message IDs)
- Infrastructure/announcements-maintenance (for broadcast logic if reused)

## Key Design Patterns
1. **Background task** - @tasks.loop decorator, auto-starts in on_ready()
2. **Parallel fetch** - All 4 endpoints fetched in parallel via asyncio.gather()
3. **Rate limiting** - asyncio.sleep(3) between consecutive edits
4. **Doodle throttle** - Track _last_doodle_refresh timestamp, skip if recent
5. **Graceful failures** - Skip stale message IDs, continue with next guild

## API Calls
- TTRApiClient.fetch("population")
- TTRApiClient.fetch("fieldoffices")
- TTRApiClient.fetch("doodles")
- TTRApiClient.fetch("sillymeter")
- message.edit(embed=...) for Discord message editing
- Graceful error handling for 503 API errors

## Database Access
- Read guild_feeds table to get message IDs per guild/feed
- No writes (read-only)

## Tests to Verify
- [ ] _refresh_loop() runs every 90 seconds
- [ ] _fetch_all() fetches all 4 endpoints in parallel
- [ ] _refresh_once() iterates all tracked guilds
- [ ] _update_feed() edits message with correct embed
- [ ] 3-second delay between consecutive edits to same guild
- [ ] Doodles only refreshed every 12 hours
- [ ] Stale message IDs are skipped gracefully
- [ ] panel_announce.txt is checked every 90 seconds
- [ ] Panel announcements are broadcast correctly
- [ ] panel_announce.txt is deleted after broadcasting

## Special Requirements
- **CRITICAL**: Do NOT fetch or process invasions endpoint (user constraint: no building data)
- Doodle refresh should be throttled to 12 hours unless forced by /pd-refresh
- Message IDs may be stale; always handle edit failures gracefully
- Rate limiting (3 seconds) is mandatory to respect Discord API limits

## Integration Notes
- Started in on_ready() via self._refresh_loop.start()
- Uses @tasks.loop(seconds=...) decorator from discord.ext.tasks
- Loop interval changed to config.refresh_interval before starting
- Fetches happen in parallel but edits are sequential (due to rate limiting)
- Panel announcements are a convenience feature for hosting panels

## File Paths
- Panel announcement file: `panel_announce.txt` (at project root)
- Read but not deleted by this feature (separate cleanup)

## State Tracking
- `self._last_doodle_refresh: float` - timestamp of last doodle refresh
- Prevents unnecessarily re-fetching doodles within 12-hour window

## Error Handling
- TTR API 503 (maintenance) - gracefully skip that fetch, retry next cycle
- Stale message IDs (message not found) - log and continue
- Discord rate limits - respect 3-second delays

## Reference Implementation
See Main-1.5.0/bot.py lines 581-740 for the complete original implementation.
