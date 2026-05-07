# Paws Pendragon TTR – Toontown Rewritten Discord Bot (Closed Alpha)

**Live TTR data in your Discord.** A multi-guild bot that mirrors public Toontown Rewritten APIs into pinned embeds, complete with a full Cog suit progression calculator, doodle marketplace, and hierarchical logging.

⚠️ **Closed Alpha:** This bot is in active development. Features and APIs may change. Stability feedback welcome.

Deploy once, serve unlimited Discord servers from a single allowlist. Runs on **Cybrancee hosting** or any Linux box with Python 3.9+.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue)](https://www.python.org/downloads/)
[![discord.py](https://img.shields.io/badge/discord.py-2.0+-blue)](https://github.com/Rapptz/discord.py)
[![SQLite](https://img.shields.io/badge/SQLite-3-green)](https://www.sqlite.org/)
[![Async](https://img.shields.io/badge/async-aiohttp%2C%20aiosqlite-orange)](https://docs.aiohttp.org/)

---

## What It Does

### Three Live Channels (Per Server)

After an admin runs `/pdsetup`, your server gets:

| Channel | Updates | Content |
|---------|---------|---------|
| **`#tt-information`** | Every 90s | District populations, active Field Offices (department/difficulty/annexes/status), global Silly Meter (team scores & progress). |
| **`#tt-doodles`** | Every 12h | Every doodle for sale, sorted by rarity tier. Trait ratings + buying guide. |
| **`#suit-calculator`** | On startup + `/pdrefresh` | Full progression tables for all 4 Cog factions + v1.0/v2.0 variants (4 static pinned embeds). |

Clean & efficient: One pinned message per section. In-place edits. Stale messages auto-swept every 15 min.

### Live Updating Embeds

Every 90 seconds, the bot fetches fresh data from the TTR API and **edits the pinned embeds in-place** with the latest information. No new messages posted — same embed, refreshed content. This keeps channels noise-free and Discord history clean.

Doodle embeds update once every 12 hours (unless forced via `/pdrefresh`). Suit calculator embeds don't follow the 90-second loop; they're static and only update on bot startup and `/pdrefresh`.

---

## Suit Calculator

Complete point progression tracking for all Cog suit disguises.

### Input
`/calculate <suit> <level> <current_points>`

**Accepts:**
- Full faction names: `Sellbot`, `Cashbot`, `Lawbot`, `Bossbot`
- Abbreviations: `SB`, `CB`, `LB`, `BB`
- 2.0 suits: `SB2.0`, `CB2.0`, `LB2.0`, `BB2.0`
- Level range: 1–20 (max disguise level)
- Current points: Your earned progress toward the next level

### Output
- **Points needed:** Exact count to reach next level
- **Effort estimate:** Which activity is most efficient (ranked by avg yield/hour)
- **Yield ranges:** Min–max points per activity run
- **Activity recommendations:** All 4+ activities per faction with tier ratings
- **Laff boosts:** Milestones (levels 50, 65, 80, 95, 100) flagged with rewards

### Suit Calculator Embeds

`#suit-calculator` displays 4 pinned embeds (one per faction), showing the complete level-1-to-20 point quota table for both v1.0 and v2.0 suits. Updated on bot startup and `/pdrefresh` only (not the 90-second refresh loop).

**Factions & Colors:**
- Sellbot (Red) — Cog golf club & trash panda activities
- Cashbot (Purple) — Bank robbery & teller activities
- Lawbot (Green) — Courtroom & jury summons activities
- Bossbot (Yellow) — Toontask & boss activities

**Point Quotas:**
- v1.0: Standard progression (Sellbot 10–10600, Cashbot 15–15900, Lawbot 20–21200, Bossbot 30–31800)
- v2.0: Accelerated progression (~15% increase per level)

---

## Slash Commands

### User Commands
Available in servers, DMs, and group chats. Work as both a server bot and a personal User App install.

| Command | Description |
|---|---|
| `/ttrinfo` | DMs you the current district populations, cog invasions, field offices, and Silly Meter status. |
| `/doodleinfo` | DMs you the full doodle availability list with trait ratings and a buying guide. |
| `/doodlesearch [traits] [playground] [district] [cost]` | Advanced doodle finder. Filter by up to 4 traits (fuzzy-matched, e.g. "Playful"), playground, district, or exact jellybean cost. Returns top 7 ranked results with images in a thread. |
| `/calculate <suit> <level> <current_points>` | Suit disguise point calculator. Accepts faction names or abbreviations; add `2.0` for 2.0 suits (e.g. `RB2.0`). Returns points needed, activity recommendations with yield ranges, and laff boost milestones. |
| `/invite` | DMs you the links to add Paws Pendragon TTR to a server or personal account. |
| `/helpme` | DMs you the full command list. Falls back to ephemeral if DMs are closed. |

### Server Admin Commands
Require **Manage Channels** and **Manage Messages**.

| Command | Description |
|---|---|
| `/pdsetup` | Create `#tt-information`, `#tt-doodles`, and `#suit-calculator` channels and start live tracking for this server. |
| `/pdrefresh` | Force an immediate data refresh, update all feed embeds, and sweep stale messages. |
| `/pdteardown` | Stop tracking this server. Channels are kept but no longer updated. Logged to `teardown_log.txt`. |

### Console Commands
Typed directly into the Cybrancee hosting panel console (stdin).

| Command | Description |
|---|---|
| `stop` | Notify all servers of maintenance, then shut down gracefully. |
| `restart` | Notify all servers of a restart, then hot-restart the process. |
| `maintenance` | Toggle maintenance mode banner on/off in all tracked server channels. State persists across restarts. |
| `announce <text>` | Broadcast a message to every tracked server's `#tt-information` channel. Auto-deletes after 30 minutes. |
| `help` | List available console commands. |

---

## User App Install

Paws Pendragon TTR supports Discord's **User App** feature. Users can add the bot directly to their Discord account and use `/ttrinfo`, `/doodleinfo`, `/calculate`, `/invite`, and `/helpme` anywhere — in any server, DM, or group chat — without the bot needing to be a member of that server.

Use `/invite` to get the install links for personal accounts and servers.

---

## Architecture Highlights

### Multi-Guild Sharding
Uses `discord.AutoShardedClient` to efficiently shard across Discord when serving many servers. One allowlist controls all server access.

### Async-First
All I/O is async: aiohttp for TTR API calls, aiosqlite for SQLite operations, asyncio for background tasks. Non-blocking throughout.

### Live Feed System
**90-second refresh loop** polls TTR API endpoints in parallel, then updates all tracked guild channels in place. Respects Discord rate limits with per-guild throttling.

### State Persistence
All server state (guild ID, channel IDs, message IDs, preferences) lives in SQLite (`bot.db`). Auto-initializes on first run. Legacy JSON files from v1.x are automatically migrated.

### Hierarchical Logging
Logs reflect Discord hierarchy: `[guild_name][channel_name][thread_name]` for thread-level operations (suit calculator embeds). Concise one-line summaries per operation (messages added/removed/updated).

### Modular Features
Transitioning from monolithic `bot.py` to cleanly separated `Features/` directory (Core utilities, User commands, Admin commands, Infrastructure services). Each feature documents scope, database tables, and dependencies in a `BRIEFING.md`.

---

## TTR API Endpoints Used

The bot consumes 5 public Toontown Rewritten endpoints:

| Endpoint | Data | Update Frequency |
|----------|------|------------------|
| `/api/population` | District populations per server | Every 90s |
| `/api/fieldoffices` | Active Field Office locations, difficulty, open/closed status | Every 90s |
| `/api/doodles` | Available doodles for purchase with trait ratings | Every 12 hours |
| `/api/sillymeter` | Silly Meter team scores and global progress | Every 90s |

**Note:** Invasions API exists but is intentionally excluded (building-level granularity is unavailable; TTR API returns only department-level data).

---

## Setup & Deployment

### Quick Local Start

1. **Create a test Discord server** and get your guild ID (Developer Mode → right-click server → Copy ID).
2. **Set up environment:**
   ```bash
   cd PDMain
   python3 -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   cp .env.example .env
   ```
3. **Configure `.env`:**
   ```
   DISCORD_TOKEN=your_bot_token_here
   GUILD_ALLOWLIST=your_guild_id_here
   BOT_ADMIN_IDS=your_user_id_here
   ```
4. **Run:**
   ```bash
   python -u bot.py
   ```

The bot auto-initializes the SQLite database on first startup. Watch the console for `on_ready()` and `_refresh_loop()` messages.

### Cybrancee Hosting

Designed for **Cybrancee Discord Bot Hosting** (<https://cybrancee.com/discord-bot-hosting>).

**Recommended plan:** Basic ($1.49/mo, 512 MB RAM). The bot uses ~50–100 MB across multiple servers.

**Setup:**
1. Upload `PDMain/` directory to Cybrancee file manager.
2. Create `.env` with your real Discord token, allowlist, and admin IDs.
3. Set the worker command to: `python3 PDMain/bot.py`
4. Start the bot.

For console commands, type directly into the Cybrancee panel stdin.

See **`DEPLOY.md`** for detailed step-by-step instructions, invite URLs, and troubleshooting.

---

## Other Built-In Features

**Auto-update from GitHub** — On every startup, the bot fetches the latest commit from the configured GitHub repo. If a new version is found, it resets to the latest code and restarts automatically (hash comparison prevents restart loops).

**First-use welcome DM** — The first time a user runs any command, the bot DMs them a brief introduction and early-access notice. Tracked in the database to avoid repeats.

**Maintenance notices** — When the bot shuts down, it posts an orange embed to every tracked server's `#tt-information` channel noting the outage time and linking to ToonHQ as an alternative. The notice is automatically deleted on next startup.

**Panel announcements** — Upload `panel_announce.txt` to the hosting file manager. The bot picks it up within 90 seconds, broadcasts it to every tracked server, and deletes the file.

**Ban system** — The ban list blocks abusive users from all commands by Discord ID. Banned users receive an ephemeral rejection message on every blocked attempt. Ban records (reason, timestamp, banning admin) are stored in the database.

**Teardown logging** — Every `/pdteardown` event is logged with the guild ID, server name, owner name, owner ID, and invoking user ID.

**Message sweep** — Every 15 minutes, stale bot messages are automatically deleted from tracked channels (keeps feeds clean).

---

## Version History

**V Alpha 0.5.0** — Current release (Closed Alpha).
- **`#suit-calculator` static channel** — 4 pinned embeds (one per faction) showing the full promotion point tables for every cog suit level (1–20), including 2.0 variants. Posted/edited on startup and `/pdrefresh`; not on the 90-second loop.
- `/pdsetup` now creates `#suit-calculator` alongside `#tt-information` and `#tt-doodles`.
- `/pdrefresh` now also refreshes the suit-calculator embeds.
- Hierarchical logging for thread operations (suit calculator messages added/removed/updated per faction).

**V Alpha 0.4.0**
- `/calculate <suit> <level> <current_points>` — suit disguise point calculator for all 4 factions. Accepts full names or abbreviations; handles 2.0 suits (SB2.0, CB2.0, LB2.0, BB2.0). Returns points still needed and ranked activity recommendations with per-run yield ranges.

**V Alpha 0.3.0**
- Console command: `announce <text>` — broadcasts to all servers from the hosting panel (replaces `/pd-announce`).
- Console command: `maintenance` — toggles a persistent orange banner in both `#tt-information` and `#tt-doodles` across all guilds. State survives restarts via database.
- Console commands: `stop` and `restart` — each notifies all servers before acting.
- Removed all bot-admin Discord slash commands (`/pd-ban`, `/pd-unban`, `/pd-banlist`, `/pd-announce`). Ban enforcement remains; manage bans via the database.
- Discord 503 transient error handling: API outages are caught and retried automatically.

**V Alpha 0.2.0**
- User App install support (`/ttrinfo`, `/doodleinfo`, `/helpme`, `/invite` work outside servers).
- Silly Meter embed in `#tt-information` with team descriptions, accumulated points, and percentage display.
- Ban system with persistent ban records (reason, timestamp, banning admin).
- Maintenance embed broadcast on shutdown; auto-deleted on next startup.
- First-use welcome DM for new User App installs.
- Auto-update from GitHub on every startup using hash comparison to prevent restart loops.
- Teardown logging to the database.
- Rate limit protection: 3-second sleep between consecutive embed edits per guild.

**V Alpha 0.1.0**
- Multi-guild rewrite with `/pdsetup`, allowlist enforcement, and per-guild message persistence.
- Doodle tier guide with trait ratings.
- District, invasion, and field office live embeds.
- Panel announcement support via `panel_announce.txt`.

---

## File Structure

| File | Purpose |
|---|---|
| `bot.py` | Multi-guild bot core. Commands, 90s refresh loop, allowlist enforcement, ban enforcement, maintenance notices, auto-updates. |
| `Features/` | Modular feature directory: `Core/` (config, db, ttr_api, formatters), `User/` (user commands), `Admin/` (admin commands), `Infrastructure/` (background services). |
| `requirements.txt` | Pinned dependencies. |
| `Procfile` | `worker: python3 PDMain/bot.py` for hosts that read it. |
| `runtime.txt` | Python 3.11 pin. |
| `bot.db` | SQLite database (auto-created on first run). **Do not delete while running.** |
| `.env.example` | Template config — safe to commit. Fill values into `.env`. |
| `.env` | Your real secrets — **never commit this file.** |
| `.gitignore` | Keeps `.env`, `bot.db`, and tooling dirs out of git. |
| `DEPLOY.md` | Cybrancee step-by-step setup and troubleshooting. |

---

## Contributing

Contributions welcome. Please:
1. Fork the repo and create a feature branch.
2. Test locally with `/pdsetup` and `/pdrefresh`.
3. Submit a pull request with a clear description of changes.

For major changes, consider opening an issue first.

---

## License

Licensed under the [MIT License](LICENSE).

---

## Support

- **Issues & bugs:** Open a GitHub issue.
- **Setup help:** See `DEPLOY.md` for detailed hosting instructions.
- **Toontown Rewritten:** <https://www.toontownrewritten.com/>
