# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env: fill in DISCORD_TOKEN, GUILD_ALLOWLIST, BOT_ADMIN_IDS
python bot.py
```

The bot auto-initializes the SQLite database (`bot.db`) on first run and migrates any legacy JSON files (`state.json`, `welcomed_users.json`, `banned_users.json`, `maintenance_mode.json`) to it. Safe to delete JSON files after startup completes.

## Development

**No tests or linting setup.** This project is a single-bot deployment without a test harness. For local development:

1. Run `python bot.py` to start the bot (requires `.env` with a test Discord server ID in `GUILD_ALLOWLIST`).
2. Verify changes by running `/pd-refresh` to trigger an immediate data fetch and UI update.
3. Check console output for errors; the bot logs to stdout with level INFO.

**Debugging patterns:**
- Use `python -u bot.py 2>&1 | grep ERROR` to catch exceptions quickly.
- The TTR API often returns 503 errors during maintenance; the bot retries automatically.
- If embeds aren't updating, check: (a) message IDs stored in `bot.db` are correct, (b) the bot still has Send/Edit perms in the channel, (c) the feed is tracked in `guild_feeds` table.
- Use `sqlite3 bot.db ".dump guild_feeds"` to inspect stored message IDs per guild.

## Architecture

Paws Pendragon is a multi-guild Discord bot that mirrors live Toontown Rewritten API data into pinned Discord embeds. One hosted instance can serve multiple Discord servers via an allowlist. Supports both server installs and personal User App installs.

### Module responsibilities

| File | Role |
|---|---|
| `bot.py` | `TTRBot` (subclass of `discord.AutoShardedClient`). Owns: refresh loop, guild allowlist enforcement, state management, all 11 slash commands (user + admin), sweep loop, announcement system, ban enforcement, maintenance mode, welcome DMs, and teardown logging. |
| `config.py` | Loads `.env` into a frozen `Config` dataclass. All env var access is centralized here. |
| `db.py` | Async SQLite persistence layer. Handles state, allowlist, announcements, maintenance mode, welcomed users, and bans. Provides one-time JSON → SQLite migration on first run. |
| `ttr_api.py` | Thin async `aiohttp` client for the 5 public TTR endpoints: invasions, population, fieldoffices, doodles, sillymeter. Used as an async context manager. |
| `formatters.py` | Pure functions converting TTR API JSON into `discord.Embed` objects. The `FORMATTERS` dict maps feed key → formatter; used by `_update_feed()` in `bot.py`. |
| `calculate.py` | `/calculate` command logic and `build_suit_calculator_embeds()`. Owns all V1 + V2 suit point quota tables, activity ranges, suit name resolution, and the activity planner. Registered via `register_calculate(bot)`. |
| `Console.py` | Reads stdin in a background task for hosting panel commands: `stop`, `restart`, `maintenance`, `announce`. Called at startup via `run_console(bot)`. |

### Data flow (refresh loop)

1. Every `REFRESH_INTERVAL` seconds (default 90s), `_refresh_loop()` fires.
2. `_fetch_all()` gathers all 5 TTR endpoints in parallel via `ttr_api.py`.
3. For each tracked guild + feed key combo, `_update_feed()` is called:
   - Looks up the formatter from `FORMATTERS`
   - Builds the embed(s)
   - Edits the pinned message in place using stored message IDs from the database
   - Waits 3 seconds between edits to respect Discord rate limits
4. Doodle embeds are throttled to once every 12 hours (`DOODLE_REFRESH_INTERVAL`), unless forced via `/pd-refresh`.
5. Every 15 minutes, `_sweep_loop()` runs to delete stale bot messages outside the known message ID set.

### State persistence (SQLite)

The bot uses `bot.db` (SQLite) with these tables:

- **guild_feeds** — per-guild channel + message ID tracking (`guild_id`, `feed_key` → `{channel_id, message_ids[]}`).
- **allowlist** — runtime guild allowlist (unioned with `GUILD_ALLOWLIST` from `.env`).
- **announcements** — temporary announcement messages with expiry timestamps.
- **maintenance_msgs** — one message ID per guild × feed key during maintenance mode.
- **welcomed_users** — user IDs who received the first-use welcome DM.
- **banned_users** — ban records: `user_id` → `{reason, banned_at, banned_by, banned_by_id}`.
- **maintenance_mode** — active maintenance mode state per guild × feed key.

On first run, the bot runs a one-time migration from legacy JSON files (`state.json` v1/v2, `welcomed_users.json`, `banned_users.json`, `maintenance_mode.json`). The migration is idempotent and safe to retry.

### Slash commands

**User commands** (work everywhere: servers, DMs, group chats, User App):
- `/ttrinfo` — DMs you current districts, invasions, field offices, and Silly Meter.
- `/doodleinfo` — DMs you all available doodles with trait ratings and a buying guide.
- `/calculate <suit> <level> <current_points>` — shows points to next level with activity recommendations. Suit names or abbreviations; add `2.0` for 2.0 suits (e.g. `RB2.0`).
- `/invite` — DMs you the links to add the bot to a server or personal account.
- `/helpme` — DMs you the full command list (or ephemeral if DMs blocked).

**Server admin commands** (require **Manage Channels** and **Manage Messages**):
- `/pd-setup` — creates category + 3 channels, posts placeholders, starts live tracking.
- `/pd-refresh` — force an immediate data refresh, update suit-calculator embeds, sweep stale messages.
- `/pd-teardown` — stops tracking this server (channels remain, no longer updated).

**Console commands** (typed into Cybrancee hosting panel stdin, restricted to `BOT_ADMIN_IDS`):
- `stop` — notify all servers, then shut down gracefully.
- `restart` — notify all servers, then hot-restart the process.
- `maintenance` — toggle a persistent orange banner across all tracked servers.
- `announce <text>` — broadcast a message to every server's `#tt-information`. Auto-deletes after 30 minutes.
- `help` — list available console commands.

### Guild lifecycle

- **On join:** Bot immediately leaves if guild is not on the allowlist, DMs the owner with a closed-access message.
- **`/pd-setup`:** Creates the `Toontown Rewritten` category and three channels (`#tt-information`, `#tt-doodles`, `#suit-calculator`), posts placeholder embeds, stores message IDs in the database.
- **`/pd-teardown`:** Removes guild from the database; channels remain but are no longer updated.

### Ban management

Ban records are stored in the database (`banned_users` table). Direct edit of the table is the primary interface (no slash commands); bans are enforced server-wide by checking all command invocations.

The bot also reads `BANNED_USER_IDS` from `.env` on startup and syncs any entries into the database.

When a user is banned, the bot immediately checks all tracked guilds to see if the user holds elevated permissions anywhere and quarantines if needed (see below).

### Maintenance mode

When `maintenance` console command is run, an orange embed is posted to each tracked guild's three channels. The embeds persist until maintenance is toggled off. State is persisted in the database's `maintenance_mode` table.

### Announcements system

The `announce` console command broadcasts a temporary message to all servers' `#tt-information` channels. Announcements auto-delete after 30 minutes. Expiry is tracked in the database's `announcements` table and cleaned up by the sweep loop.

### First-use welcome DM

The first time any user runs a command, the bot DMs them a brief introduction and early-access notice. Tracked in the database's `welcomed_users` table. One DM per user; subsequent commands are not followed by another welcome.

### Teardown logging

Every `/pd-teardown` invocation is logged to `teardown_log.txt` (append-only) with guild ID, server name, owner name, owner ID, and the invoking user. Useful for auditing guild departures.

### Panel announcements

For hosting panels that support file uploads: create `panel_announce.txt` in the file manager. The bot checks for this file every 90 seconds, broadcasts its contents to all servers' `#tt-information` channels (if not in maintenance mode), and deletes the file. Useful for emergency announcements without restarting.

### Auto-update from GitHub

At startup, `bot.py` compares local `HEAD` to `origin/main`. If behind, it runs `git reset --hard origin/main` and `os.execv`-restarts the process. Hash comparison prevents restart loops. Requires a valid GitHub remote and working git credentials.

### User App support

Paws Pendragon supports Discord's User App feature. Users can add the bot to their personal account via `/invite` and use `/ttrinfo`, `/doodleinfo`, `/calculate`, `/helpme`, and `/invite` anywhere—any server, DM, or group chat—without the bot being a server member. All commands work seamlessly in both modes.

## Code patterns & important invariants

**Async everywhere.** All I/O (discord.py API, aiosqlite, aiohttp) is async. Never use `requests` or sync SQLite.

**Formatter registration via dict.** `formatters.py` exports a `FORMATTERS` dict that maps feed keys (`"invasions"`, `"doodles"`, etc.) to builder functions. New feeds must be added to this dict and registered in `_update_feed()` in `bot.py`.

**Message ID persistence is critical.** Feeds work by editing pinned messages in place. The bot stores the message IDs in the `guild_feeds` table. If a channel is deleted or the bot loses perms, message IDs become stale — the next edit fails silently. Always verify perms before troubleshooting missing embeds.

**Rate limiting.** The bot sleeps 3 seconds between consecutive embed edits in the same guild (see `_update_feed()`). This respects Discord's rate limit. When adding new feeds, respect this delay.

**Guild allowlist is unioned.** The effective allowlist is `GUILD_ALLOWLIST` (from `.env`) UNION with the runtime allowlist (from `db.db`). The `allow` command (or direct DB edit) adds to the runtime allowlist; `.env` is the seed list.

**TTR API async context manager.** Use `ttr_api.TTRClient()` as a context manager; it auto-closes the aiohttp session. Calling it outside a context manager will leak connections.

**Config is frozen.** `config.py` exports a frozen `Config` dataclass loaded once at startup. Mutation requires a restart. Environment variable changes do not take effect until a restart.

## Environment variables

See `.env.example` for the full list. **Required:**
- `DISCORD_TOKEN` — bot token from https://discord.com/developers/applications.
- `GUILD_ALLOWLIST` — comma-separated Discord server IDs the bot is allowed to join.
- `BOT_ADMIN_IDS` — comma-separated Discord user IDs that can run console commands.

**Important optional:**
- `REFRESH_INTERVAL` (default 90) — seconds between live feed refreshes. 60–90s recommended.
- `USER_AGENT` — descriptive string sent to the TTR API (they request one).
- Custom emoji IDs (`JELLYBEAN_EMOJI`, `COG_EMOJI`, `STAR_*`) — used by `formatters.py` for rich embed display. Omit these to fall back to plaintext.

## File categories

**Source code (always commit):**
- `bot.py`, `config.py`, `db.py`, `ttr_api.py`, `formatters.py`, `calculate.py`, `Console.py`
- `.env.example`, `.env.example.template`, `requirements.txt`, `.gitignore`
- `README.md`, `DEPLOY.md`, `CLAUDE.md`, `Procfile`, `runtime.txt`

**Auto-generated (safe to delete, auto-recreated on startup):**
- `bot.db` — SQLite database. First-run auto-initializes; schema is immutable.
- `__pycache__/` — Python bytecode cache.
- `state.json`, `welcomed_users.json`, `banned_users.json`, `maintenance_mode.json` — legacy JSON files. Migrated to `bot.db` on first run; safe to delete after migration completes.
- `teardown_log.txt` — append-only audit log of `/pd-teardown` invocations.
- `panel_announce.txt` — read and deleted by the bot every 90 seconds (hosting panel feature).

**Never commit:**
- `.env` — your real Discord token and secret IDs.

## Hosting

Designed for Cybrancee Discord Bot Hosting. Recommended plan: Basic ($1.49/mo, 512 MB RAM). The bot uses ~50–100 MB across multiple servers.

**Setup:**
- Set `worker:` to `python3 bot.py` in the hosting panel.
- Upload `.env` (with real secrets) and `requirements.txt`.
- The bot auto-initializes the database on first startup.
- For emergency announcements, upload `panel_announce.txt` to the file manager.

See `DEPLOY.md` for full setup, invite URLs, and troubleshooting.
