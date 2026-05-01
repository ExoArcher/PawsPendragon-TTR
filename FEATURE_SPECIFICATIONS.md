# Paws Pendragon Feature Specifications v1.0

## Overview
This document breaks down the 1454-line monolithic `bot.py` into 17+ modular features for the refactored architecture. Each feature is independent and will be implemented as a separate module/extension.

---

## Feature 1: ttrinfo Command

**Purpose**: User slash command that DMs the user with current Toontown Rewritten live data: districts, field offices, and silly meter status.

**Code Sections to Extract**:
- Lines 1100-1160 (slash command registration and handler)
- Uses `format_information()` from formatters.py for embed creation
- Calls TTR API endpoints: population, fieldoffices, sillymeter

**TTR Domain Knowledge Required**:
- Districts (server instances in TTR)
- Population counts
- Field Offices (Sellbot, Cashbot, Lawbot, Bossbot locations)
- Silly Meter (team progress, laff boost thresholds)

**Discord API Calls**:
- `app_commands.command()`
- `await ctx.user.send(embed=...)`

**Database Tables Used**:
- `welcomed_users` (via _maybe_welcome)

**Performance Constraints**:
- None specific; one-shot command

**Dependencies**:
- live-feeds feature (for TTR API data)
- formatters module (format_information)
- User system feature (welcome DM)

---

## Feature 2: doodleinfo Command

**Purpose**: User slash command that DMs the user with a comprehensive list of all available Toontown Rewritten doodles, their traits, rarity ratings, and buying guide.

**Code Sections to Extract**:
- Lines 1161-1220 (slash command registration and handler)
- Uses `format_doodles()` from formatters.py
- Calls TTR API endpoint: doodles

**TTR Domain Knowledge Required**:
- Doodles (collectible creatures in TTR)
- Doodle traits (properties that affect gameplay)
- Trait ratings (rarity, power, effect)
- Buying guide (how to acquire doodles)

**Discord API Calls**:
- `app_commands.command()`
- `await ctx.user.send(embed=...)`

**Database Tables Used**:
- `welcomed_users` (via _maybe_welcome)

**Performance Constraints**:
- Typically creates multiple embeds; may paginate

**Dependencies**:
- live-feeds feature (for TTR API doodles endpoint)
- formatters module (format_doodles)
- User system feature (welcome DM)

---

## Feature 3: calculate Command

**Purpose**: User slash command that allows players to calculate remaining Cog suit points, recommend optimal activities, and show progress to next level. Includes suit-calculator embed updates.

**Code Sections to Extract**:
- Lines 1280-1330 (slash command registration)
- `register_calculate()` from calculate.py (entire module)
- Suit calculator embed pinning: lines 406-580 (\_ensure_suit_calculator_pin, \_ensure_suit_threads, \_refresh_suit_calculator_all_guilds)

**Special Requirements**:
- Change UI label from "faction" to "**Suit Type**" in all embeds
- Add congratulations message when user reaches laff boost milestone (health boost)
- Laff boost appears at specific levels per faction/version

**TTR Domain Knowledge Required**:
- Cog Disguise system (4 factions: Sellbot, Cashbot, Lawbot, Bossbot)
- Suit point quotas (v1.0 and v2.0)
- Activity ranges and recommendations
- Suit progression (which activities give which points)
- Laff boost thresholds (level 50, 65, 80, 95, 100 or varies by faction)
- Boss encounters (CEO, CFO, CJ, VP) and rewards

**Discord API Calls**:
- `app_commands.command()` with parameters (suit, level, current_points)
- `await ctx.response.defer()`
- Embed creation and editing in guild channels

**Database Tables Used**:
- `guild_feeds` (for message IDs of suit calculator embeds)
- `welcomed_users` (via _maybe_welcome)

**Performance Constraints**:
- Suit calculator embeds refreshed only on startup and `/pd-refresh` (not on 90-second loop)
- Creates 4 static embeds per guild + faction threads

**Dependencies**:
- State-persistence feature (guild_feeds table)
- User system feature (welcome DM)
- formatters module (embed creation)

---

## Feature 4: helpme Command

**Purpose**: User slash command that DMs the user a list of all available bot commands with brief descriptions. Sends ephemeral message if user has DMs blocked.

**Code Sections to Extract**:
- Lines 1390-1420 (slash command registration and handler)

**TTR Domain Knowledge Required**:
- None (purely informational)

**Discord API Calls**:
- `app_commands.command()`
- `await ctx.user.send()` (with fallback to ephemeral)

**Database Tables Used**:
- `welcomed_users` (via _maybe_welcome)

**Performance Constraints**:
- None

**Dependencies**:
- User system feature (welcome DM)

---

## Feature 5: invite Command

**Purpose**: User slash command that DMs the user a link to add the bot to their personal Discord account (User App feature) or to a Discord server.

**Code Sections to Extract**:
- Lines 1345-1370 (slash command registration and handler)

**TTR Domain Knowledge Required**:
- None

**Discord API Calls**:
- `app_commands.command()`
- `await ctx.user.send()`

**Database Tables Used**:
- `welcomed_users` (via _maybe_welcome)

**Performance Constraints**:
- None

**Dependencies**:
- User system feature (welcome DM)

---

- None

**Discord API Calls**:
- `app_commands.command()`
- `await ctx.user.send()`

**Database Tables Used**:
- `welcomed_users` (via _maybe_welcome)

**Performance Constraints**:
- None

**Dependencies**:
- User system feature (welcome DM)

---

## Feature 7: beanfest Command

**Purpose**: User slash command for Beanfest seasonal event information (if applicable to TTR).

**Code Sections to Extract**:
- Check bot.py for beanfest command registration (user mentioned it in command list)

**TTR Domain Knowledge Required**:
- Beanfest event mechanics (if seasonal in TTR)

**Discord API Calls**:
- `app_commands.command()`
- `await ctx.user.send()`

**Database Tables Used**:
- `welcomed_users` (via _maybe_welcome)

**Performance Constraints**:
- None

**Dependencies**:
- User system feature (welcome DM)
- live-feeds (if event data comes from TTR API)

---

## Feature 8: pd-setup Command

**Purpose**: Server admin command that initializes the bot in a Discord server. Creates a category ("Toontown Rewritten"), three channels (#tt-information, #tt-doodles, #suit-calculator), posts placeholder embeds, and begins live tracking.

**Code Sections to Extract**:
- Lines 344-405 (\_ensure_channels_for_guild, \_send_placeholder, \_ensure_messages)
- Slash command registration: lines 1221-1280

**Discord API Calls**:
- Requires Manage Channels and Manage Messages permissions
- `guild.create_category()`
- `category.create_text_channel()`
- `channel.send(embed=...)`
- Store message IDs for later editing

**Database Tables Used**:
- `guild_feeds` (store channel_id and message_ids)

**Performance Constraints**:
- One-time per guild
- Waits 3 seconds between channel creates to avoid rate limits

**Dependencies**:
- State-persistence feature (guild_feeds table)
- Guild-lifecycle feature (guild join/leave)

---

## Feature 9: pd-teardown Command

**Purpose**: Server admin command that stops tracking a Discord server. Removes guild from the database; channels remain but are no longer updated. Logs the event to teardown_log.txt.

**Code Sections to Extract**:
- Slash command registration: lines 1221-1280
- Teardown logic (lines 1420+ or search for teardown)
- Teardown logging: lines 904-975 (append to TEARDOWN_LOG)

**Discord API Calls**:
- Requires Manage Channels and Manage Messages permissions
- No Discord API calls needed; state-only

**Database Tables Used**:
- `guild_feeds` (remove guild entry)

**File I/O**:
- Append to `teardown_log.txt` (audit trail)

**Performance Constraints**:
- One-time per guild teardown

**Dependencies**:
- State-persistence feature (guild_feeds table)

---

## Feature 10: pd-refresh Command

**Purpose**: Server admin command that forces an immediate data refresh for the guild, updates suit calculator embeds, and sweeps stale bot messages.

**Code Sections to Extract**:
- Slash command registration: lines 1221-1280
- `_refresh_once()` and related refresh logic: lines 581-713
- `_sweep_guild_stale()`: lines 775-795
- Per-user cooldown enforcement

**Discord API Calls**:
- Requires Manage Channels and Manage Messages permissions
- Edits live feed messages via stored message IDs
- Deletes stale bot messages

**Database Tables Used**:
- `guild_feeds` (read message IDs)

**Performance Constraints**:
- 3-second delays between message edits (rate limiting)
- Per-user cooldown (configurable, default ~30 seconds)

**Dependencies**:
- live-feeds feature (fetches and updates TTR data)
- message-sweep feature (deletes stale messages)
- State-persistence feature (guild_feeds)

---

## Feature 11: live-feeds System

**Purpose**: Background system that periodically fetches live data from the 5 public TTR API endpoints and updates embedded messages in tracked guilds.

**Code Sections to Extract**:
- `_refresh_loop()`: lines 581-660
- `_fetch_all()`: calls ttr_api.py for all 5 endpoints
- `_update_feed()`: lines 681-713 (edits pinned messages in place)
- API_KEYS constant: lines 590-595
- FORMATTERS dict usage: maps feed_key to formatter function

**TTR API Endpoints Used** (via ttr_api.py):
- population
- fieldoffices
- doodles (with 12-hour refresh throttle)
- sillymeter
- **NOT** invasions (user constraint: building data unavailable)

**TTR Domain Knowledge Required**:
- What each endpoint returns and how to format it
- Refresh intervals (90 seconds default, 12 hours for doodles)
- Rate limiting (3 seconds between consecutive edits)

**Discord API Calls**:
- `message.edit(embed=...)` for each pinned message

**Database Tables Used**:
- `guild_feeds` (read message IDs and channel IDs)

**File I/O**:
- `panel_announce.txt` (read every 90 seconds for hosting panel announcements)

**Performance Constraints**:
- Runs every 90 seconds (configurable via REFRESH_INTERVAL)
- 3-second delays between consecutive edits to same guild
- Doodles only refreshed every 12 hours unless forced via `/pd-refresh`

**Dependencies**:
- State-persistence feature (guild_feeds)
- formatters module (FORMATTERS dict)
- ttr_api module (TTRApiClient)

---

## Feature 12: state-persistence System

**Purpose**: Database abstraction layer for persistent storage of guild feeds, allowlists, announcements, maintenance mode, welcomed users, and ban records. Handles SQLite access and one-time JSON-to-SQLite migration.

**Code Sections to Extract**:
- Entire `db.py` file

**Database Tables**:
- `guild_feeds` (guild_id, feed_key → channel_id, message_ids)
- `allowlist` (runtime guild allowlist)
- `announcements` (temporary messages with expiry)
- `maintenance_msgs` (message IDs during maintenance)
- `welcomed_users` (first-use DM recipients)
- `banned_users` (ban records)
- `maintenance_mode` (active maintenance state)

**Performance Constraints**:
- All operations async (aiosqlite)
- One-time migration on first run (handles legacy JSON files)
- Message ID persistence is critical for in-place editing

**Dependencies**:
- None (foundational)

---

## Feature 13: announcements-maintenance System

**Purpose**: Manages temporary announcement messages and maintenance mode banners. Announcements auto-expire after 30 minutes. Maintenance mode broadcasts orange banners across all tracked guilds.

**Code Sections to Extract**:
- `_broadcast_announcement()`: lines 804-820
- `_delete_announcement_record()`: lines 821-835
- `_cleanup_announcements_on_startup()`: lines 836-855
- `_sweep_expired_announcements()`: lines 856-875
- `_broadcast_maintenance()`: lines 906-945
- `_cleanup_maintenance_msgs()`: lines 946-975
- ANNOUNCEMENT_TTL_SECONDS constant: line 124
- Sweep loop integration: lines 800-915

**Discord API Calls**:
- `channel.send(embed=...)` for announcements/maintenance
- `message.delete()` for expired messages

**Database Tables Used**:
- `announcements` (track expiry timestamps)
- `maintenance_msgs` (message IDs for cleanup)
- `maintenance_mode` (state per guild × feed key)

**File I/O**:
- `panel_announce.txt` (auto-picked up by refresh loop every 90 seconds)

**Performance Constraints**:
- Announcements auto-delete after 30 minutes
- Sweep loop runs every 15 minutes
- Check panel_announce.txt every 90 seconds

**Dependencies**:
- State-persistence feature (database tables)
- live-feeds feature (refresh loop integration)

---

## Feature 14: github-autoupdate System

**Purpose**: On startup, automatically fetches the latest code from GitHub, compares local HEAD to origin/main, and restarts the bot if updates are available. Prevents infinite restart loops via hash comparison.

**Code Sections to Extract**:
- Lines 51-89 (entire self-update block at top of bot.py)
- Uses git commands: init, remote add, fetch, checkout, rev-parse, reset --hard

**Git Commands Used**:
- `git init` (if .git doesn't exist)
- `git remote add origin https://github.com/ExoArcher/PawsPendragon-TTR`
- `git fetch origin main`
- `git checkout -b main --track origin/main`
- `git rev-parse HEAD` (get local hash)
- `git rev-parse origin/main` (get remote hash)
- `git reset --hard origin/main` (if update needed)

**Constraints**:
- Requires valid GitHub remote and working git credentials
- Runs BEFORE any bot initialization
- Graceful fallback if git is unavailable

**Dependencies**:
- None (runs at module load time)

---

## Feature 15: guild-lifecycle System

**Purpose**: Handles guild join/leave events, allowlist enforcement, command syncing, and guild state cleanup.

**Code Sections to Extract**:
- `on_guild_join()`: handles guild join event
- `on_guild_remove()`: handles guild leave event
- `on_ready()`: lines 255-300 (guild sync, allowlist check, state cleanup)
- `_sync_commands_to_guild()`: lines 318-343 (per-guild command registration)
- `_notify_and_leave()`: lines 344-405 (send closed-access message, leave guild)
- Guild allowlist logic: lines 198-206

**Discord API Calls**:
- `guild.owner.send()` (notify of closed access)
- `guild.leave()` (remove self from guild)
- `self.tree.sync(guild=guild)` (sync commands per-guild)

**Database Tables Used**:
- Allowlist table (check effective allowlist)
- guild_feeds (prune departed guilds)

**Performance Constraints**:
- Runs once on_ready, then per guild_join/guild_remove event

**Dependencies**:
- State-persistence feature (allowlist, guild_feeds)
- Config module (guild_allowlist from env)

---

## Feature 16: message-sweep System

**Purpose**: Background task that runs every 15 minutes, deletes stale bot messages outside the known message ID set, and cleans up expired announcements.

**Code Sections to Extract**:
- `_sweep_loop()`: lines 798-915
- `_channel_keep_ids()`: lines 785-795 (collect message IDs to preserve)
- `_sweep_channel_stale()`: lines 796-810 (delete non-tracked bot messages)
- `_sweep_guild_stale()`: lines 811-825 (iterate channels)
- `_sweep_expired_announcements()`: lines 856-875 (delete auto-expire messages)

**Discord API Calls**:
- `channel.history()` (fetch recent messages)
- `message.delete()` (remove stale messages)

**Database Tables Used**:
- `guild_feeds` (read message IDs to preserve)
- `announcements` (read expiry timestamps)

**Performance Constraints**:
- Runs every 15 minutes (background task)
- Iterates all channels in all guilds

**Dependencies**:
- State-persistence feature (guild_feeds, announcements)

---

## Feature 17: serverside-management (Console Commands)

**Purpose**: Reads stdin for hosting panel commands (available only on Cybrancee hosting panel). Allows bot admins to control global state without restarting.

**Code Sections to Extract**:
- Entire `Console.py` file
- `run_console()`: background task reading stdin
- Commands:
  - `stop` — notify all servers, then shut down gracefully
  - `restart` — notify all servers, then hot-restart
  - `maintenance` — toggle maintenance mode banner
  - `announce <text>` — broadcast temporary message to all servers
  - `help` — list available commands
- `clear_maintenance_on_startup()`: cleanup stale maintenance state

**Console API Calls**:
- `sys.stdin` reading (blocking in executor)
- `os.execv()` for restart

**Discord API Calls**:
- Broadcast messages to all guilds

**Database Tables Used**:
- `maintenance_mode` (toggle state)

**Constraints**:
- Only `BOT_ADMIN_IDS` can run commands
- Runs as background task
- Uses executor for blocking stdin read

**Dependencies**:
- State-persistence feature (maintenance_mode table)
- Announcements-maintenance feature (broadcast logic)

---

## Feature 18: User System (Welcome DMs + Ban Enforcement)

**Purpose**: On first command use, sends a welcome DM to the user. Enforces bans by rejecting banned users with ephemeral error messages.

**Code Sections to Extract**:
- `_maybe_welcome()`: lines 976-1000
- `_is_banned()`: lines 1001-1015
- `_reject_if_banned()`: lines 1016-1027
- Ban initialization from config: load `BANNED_USER_IDS` from env and sync to DB
- `welcomed_users` set (in-memory cache)
- `banned_users` dict (in-memory cache)

**Discord API Calls**:
- `user.send()` (welcome DM)
- `await ctx.response.send(ephemeral=True)` (ban rejection)

**Database Tables Used**:
- `welcomed_users` (track first-use)
- `banned_users` (enforce bans)

**Performance Constraints**:
- One DM per user (cached in memory)
- Instant ban check on every command

**Dependencies**:
- State-persistence feature (welcomed_users, banned_users tables)
- Config module (BANNED_USER_IDS from env)

---

## Integration Points & Data Flow

### Startup Sequence
1. GitHub auto-update (feature 14) — check for new code
2. Config load (config.py)
3. Database init (feature 12)
4. TTR API client init (ttr_api.py)
5. Guild lifecycle sync (feature 15) — enforce allowlist
6. Announcements cleanup (feature 13)
7. Suit calculator refresh (feature 3)
8. Console listener start (feature 17)
9. Live feeds loop start (feature 11) — begins 90-second refresh
10. Message sweep loop start (feature 16) — begins 15-minute cleanup

### Refresh Loop (90 seconds)
1. Live-feeds (feature 11) fetches all 5 TTR endpoints in parallel
2. For each guild + feed, calls `_update_feed()` with 3-second delays
3. Checks for `panel_announce.txt` (feature 13)
4. Doodles refreshed every 12 hours (feature 11)

### Sweep Loop (15 minutes)
1. Message-sweep (feature 16) deletes stale bot messages
2. Announcements-maintenance (feature 13) cleans expired messages

### User Command Flow
1. User runs any command (ttrinfo, doodleinfo, calculate, etc.)
2. User system (feature 18) checks ban status
3. User system sends welcome DM if first-time
4. Command executes and responds

---

## Dependencies Matrix

| Feature | Depends On |
|---------|-----------|
| 1. ttrinfo | 11 (live-feeds), formatters, 18 (user system) |
| 2. doodleinfo | 11 (live-feeds), formatters, 18 (user system) |
| 3. calculate | 12 (state-persist), 18 (user system), formatters |
| 4. helpme | 18 (user system) |
| 5. invite | 18 (user system) |
| 6. (merged) | 18 (user system) |
| 7. beanfest | 18 (user system), possibly 11 (live-feeds) |
| 8. pd-setup | 15 (guild-lifecycle), 12 (state-persist) |
| 9. pd-teardown | 12 (state-persist) |
| 10. pd-refresh | 11 (live-feeds), 16 (message-sweep), 12 (state-persist) |
| 11. live-feeds | 12 (state-persist), formatters, ttr_api |
| 12. state-persist | None (foundational) |
| 13. announce-maint | 12 (state-persist), 11 (live-feeds) |
| 14. github-autoupdate | None (pre-startup) |
| 15. guild-lifecycle | 12 (state-persist), config |
| 16. message-sweep | 12 (state-persist) |
| 17. serverside-mgmt | 12 (state-persist), 13 (announce-maint) |
| 18. user-system | 12 (state-persist), config |

---

## Next Steps

1. **Create Git workflow branches** for each feature
2. **Create GitHub branches** matching workflow
3. **Create subfolders** in Main-1.5.0/ for each feature
4. **Create detailed briefings** for Haiku sub-agents
5. **Sub-agents rewrite** each feature independently
6. **Integration testing** to ensure clean interfaces
7. **Suit calculator enhancements**:
   - Change "faction" → "Suit Type"
   - Add laff boost congratulations
8. **Validate no invasions** are calculated/displayed
