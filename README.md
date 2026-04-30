# LanceAQuack TTR – V1.2

Multi-guild Discord bot that mirrors the public Toontown Rewritten APIs into live-updating channels. One hosted instance can serve multiple Discord servers from a single allowlist. Also installable as a **User App** — no server required.

---

## Channels each server gets

After an admin runs `/laq-setup`:

- **`#tt-information`** — live district populations, cog invasions (type, progress, mega flag), active Field Offices (department, difficulty, annexes remaining, open/closed status), and the global Silly Meter (teams, accumulated points, percentage full).
- **`#tt-doodles`** — every doodle currently for sale across all playgrounds, with trait ratings and a tiered buying guide (Best / Great / Good / Skip).

Both channels are kept clean: one pinned embed per section, edited in place on a timer. Stale bot messages are swept automatically every 15 minutes.

---

## Slash commands

### User commands
Available in servers, DMs, and group chats. Work as both a server bot and a personal User App install.

| Command | Description |
|---|---|
| `/ttrinfo` | DMs you the current district populations, cog invasions, field offices, and Silly Meter status. |
| `/doodleinfo` | DMs you the full doodle availability list with trait ratings and a buying guide. |
| `/invite-app` | DMs you the link to add LanceAQuack TTR to your personal Discord account. |
| `/invite-server` | DMs you the link to add LanceAQuack TTR to a server. |
| `/helpme` | DMs you the full command list. Falls back to ephemeral if DMs are closed. |

### Server admin commands
Require **Manage Channels** and **Manage Messages**.

| Command | Description |
|---|---|
| `/laq-setup` | Create `#tt-information` and `#tt-doodles` channels and start live tracking for this server. |
| `/laq-refresh` | Force an immediate data refresh and sweep stale messages. |
| `/laq-teardown` | Stop tracking this server. Channels are kept but no longer updated. |

### Console commands
Typed directly into the Cybrancee hosting panel console (stdin).

| Command | Description |
|---|---|
| `stop` | Notify all servers of maintenance, then shut down. |
| `restart` | Notify all servers of a restart, then hot-restart the process. |
| `maintenance` | Toggle maintenance mode banner on/off in all tracked server channels. |
| `announce <text>` | Broadcast a message to every tracked server's `#tt-information` channel. Auto-deletes after 30 minutes. |
| `help` | List available console commands. |

---

## User App install

LanceAQuack TTR supports Discord's **User App** feature. Users can add the bot directly to their Discord account and use `/ttrinfo`, `/doodleinfo`, `/invite-app`, `/invite-server`, and `/helpme` anywhere — in any server, DM, or group chat — without the bot needing to be a member of that server.

Use `/invite-app` for the personal install link, or `/invite-server` to add it to a server.

---

## Other features

**Auto-update from GitHub** — on every startup the bot fetches the latest commit from the configured GitHub repo. If a new version is found it resets to the latest code and restarts automatically.

**First-use welcome DM** — the first time a user runs any command, the bot DMs them a brief introduction and early-access notice. Tracked in `welcomed_users.json`.

**Maintenance notices** — when the bot shuts down it sends an orange embed to every tracked server's `#tt-information` channel noting the outage time and linking to ToonHQ as an alternative. The notice is automatically deleted on next startup.

**Panel announcements** — create `panel_announce.txt` in the hosting file manager. The bot picks it up within 90 seconds, broadcasts it to every tracked server, and deletes the file.

**Ban system** — the ban list in `banned_users.json` blocks abusive users from all commands by Discord ID. Banned users receive an ephemeral rejection message on every blocked attempt. Records store the reason, timestamp, and banning admin. Edit `banned_users.json` directly to add or remove entries.

**Teardown logging** — every `/laq-teardown` is appended to `teardown_log.txt` with the guild ID, server name, owner name, owner ID, and the user who invoked it.

---

## Hosting

Designed for **Cybrancee** Discord Bot Hosting (<https://cybrancee.com/discord-bot-hosting>).

**Recommended plan:** Basic ($1.49/mo — 512 MB RAM). The bot uses ~50–100 MB RAM across multiple servers.

For full setup instructions see **`DEPLOY.md`**.

---

## Quick local start

1. Copy `.env.example` to `.env` and fill in `DISCORD_TOKEN`, `GUILD_ALLOWLIST`, and `BOT_ADMIN_IDS`.
2. `pip install -r requirements.txt`
3. `python bot.py`

---

## What's in this folder

| File | Purpose |
|---|---|
| `bot.py` | Multi-guild bot core. Commands, refresh loop, allowlist enforcement, ban enforcement, maintenance notices. |
| `Console.py` | Hosting panel stdin handler. Commands: `stop`, `restart`, `maintenance`, `announce`. |
| `config.py` | Loads `.env` into a typed `Config`. Parses `GUILD_ALLOWLIST`, `BOT_ADMIN_IDS`, etc. |
| `formatters.py` | Renders TTR API JSON into Discord embeds (information, doodles, Silly Meter). |
| `ttr_api.py` | Async aiohttp client for the public TTR endpoints. |
| `requirements.txt` | Pinned dependencies. |
| `Procfile` | `worker: python3 bot.py` for hosts that read it. |
| `runtime.txt` | Python 3.11 pin. |
| `state.json` | Per-guild channel and message ID tracking. Auto-created. **Do not delete while running.** |
| `welcomed_users.json` | Tracks which users have received the first-use welcome DM. Auto-created. |
| `banned_users.json` | Stores ban records (ID, reason, timestamp, banning admin). Auto-created. |
| `teardown_log.txt` | Append-only log of every `/laq-teardown` event. Auto-created. |
| `.env.example` | Template config — safe to commit. Fill values into `.env`. |
| `.env` | Your real secrets — **never commit this file.** |
| `.gitignore` | Keeps `.env`, `state.json`, and pyc out of git. |
| `DEPLOY.md` | Cybrancee step-by-step setup, invite URLs, and troubleshooting. |

---

## Version history

**V1.2** — Current release.
- Console command: `announce <text>` — broadcasts to all servers from the hosting panel (replaces `/laq-announce`).
- Console command: `maintenance` — toggles a persistent orange banner in both `#tt-information` and `#tt-doodles` across all guilds. State survives restarts via `maintenance_mode.json`.
- Console commands: `stop` and `restart` — each notifies all servers before acting.
- Removed all bot-admin Discord slash commands (`/laq-ban`, `/laq-unban`, `/laq-banlist`, `/laq-announce`). Ban enforcement remains; manage `banned_users.json` directly.
- Discord 503 transient error handling: `_ensure_messages` and `_update_feed` now catch `discord.HTTPException` to survive brief API outages.

**V1.1**
- User App install support (`/ttrinfo`, `/doodleinfo`, `/helpme`, `/invite-app`, `/invite-server` work outside servers).
- Silly Meter embed in `#tt-information` with team descriptions, accumulated points, and percentage display.
- Ban system with persistent `banned_users.json` records.
- Maintenance embed broadcast on shutdown; auto-deleted on next startup.
- First-use welcome DM for new User App installs.
- Auto-update from GitHub on every startup using hash comparison to prevent restart loops.
- Teardown logging to `teardown_log.txt`.
- Rate limit protection: 3-second sleep between embed edits.

**V1.0** — Cybrancee hosting edition.
- Multi-guild rewrite with `/laq-setup`, allowlist enforcement, and per-guild message persistence.
- Doodle tier guide with trait ratings.
- District, invasion, and field office live embeds.
- Panel announcement support via `panel_announce.txt`.
