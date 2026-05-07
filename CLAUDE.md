# CLAUDE.md — Paws Pendragon Project Guide

This document is the orientation guide for Claude Code when working in the Paws Pendragon repository. Read this first; it tells you what the project is, how it is organized, where to find things, and which constraints to honor when making changes.

---

## 1. Project Overview

**Paws Pendragon** is a multi-guild Discord bot (Discord.py 2.0+, AutoShardedClient) that posts live Toontown Rewritten (TTR) game data into pre-configured channels and exposes 11 slash commands for on-demand lookups (population, field offices, doodles, sillymeter, invasions, suit calculator, etc.). The bot polls the public TTR API and renders results as auto-refreshing embeds.

- **Language**: Python 3.9+ (async-first; aiohttp, aiosqlite, asyncio).
- **Runtime model**: Single process, AutoShardedClient. Refresh loop and sweep loop run as `bot.loop` background tasks.
- **Persistence**: SQLite via aiosqlite (10 tables; one-time JSON-to-SQLite migration on first boot).
- **Hosting**: Cybrancee panel (Linux container). Console commands are read from stdin.
- **License / repo**: GitHub-hosted; auto-update on startup uses `git pull --ff-only`.

The user-facing source of truth for *features* is the project [README.md](README.md). This file (`CLAUDE.md`) is the source of truth for *implementation*.

---

## 2. Repository Layout

```
Paws Pendragon/                                     ← repo root
├── CLAUDE.md                                        ← this file
├── FEATURE_SPECIFICATIONS.md                        ← module-by-module spec
├── README.md                                        ← user/operator docs
├── PDMain/                                          ← all bot source lives here
│   ├── bot.py                                       ← entry point, TTRBot class, slash commands, console loop (~1422 lines)
│   ├── .env.example.template                        ← env template (copy to .env)
│   ├── pyproject.toml / requirements.txt
│   └── Features/
│       ├── Admin/                                   ← admin slash commands (/pdsetup, /pdteardown, /pdrefresh, /pdboot)
│       ├── Core/
│       │   ├── config/                              ← Config dataclass, .env loader
│       │   ├── db/                                  ← SQLite schema, init_db, load_state, save_state
│       │   ├── formatters/                          ← embed builders (information, doodles, suit_calc, etc.)
│       │   └── ttr_api/                             ← TTR HTTP client (5 endpoints)
│       ├── Infrastructure/
│       │   ├── announcements_maintenance/
│       │   ├── github_autoupdate/
│       │   ├── guild_lifecycle/                     ← on_guild_join / on_guild_remove
│       │   ├── live_feeds/                          ← refresh loop (LiveFeedsFeature mixin)
│       │   ├── message_sweep/                       ← stale-message cleanup
│       │   ├── user_system/
│       │   ├── blacklist_removal.py
│       │   ├── cache_manager.py                     ← quarantined-guild set, in-memory caches
│       │   ├── periodic_checks.py
│       │   ├── quarantine_checks.py
│       │   └── unquarantine_checks.py
│       ├── ServerManagement/
│       │   └── console_commands/                    ← stdin command dispatcher
│       └── User/                                    ← user-facing slash commands (/ttrinfo, /doodleinfo, /doodlesearch, /helpme, /calculate, /invite, /beanfest)
└── (root-level: .gitignore, install scripts, etc.)
```

Each `Features/<area>/<module>/` directory contains a `BRIEFING.md` describing that module. When modifying a feature, read its BRIEFING.md first.

---

## 3. Architecture: TTRBot and the Mixin Pattern

The bot class is defined in [PDMain/bot.py](PDMain/bot.py) at roughly line 190:

```python
class TTRBot(LiveFeedsFeature, discord.AutoShardedClient):
    ...
```

`LiveFeedsFeature` (in `Features/Infrastructure/live_feeds/live_feeds.py`) is a **mixin** that adds the refresh loop, feed dispatch, and quarantine-skip logic onto the Discord client. This mixin pattern is the project's standard way to compose feature areas onto the bot without inflating `bot.py`. When adding a new feature area that needs lifecycle hooks or background work, prefer a mixin over piling more methods into `TTRBot` directly.

**Background tasks** (started in `setup_hook` / `on_ready`):
- **Refresh loop** — `Features/Infrastructure/live_feeds/live_feeds.py` ~line 306. Iterates allowed guilds, fetches TTR data, edits feed messages. Sleep interval = `config.refresh_interval` (default **120 s**).
- **Sweep loop** — `bot.py` ~line 826. Every 15 minutes, sweeps stale messages and tidies the bot's category.
- **Periodic checks** — `Features/Infrastructure/periodic_checks.py`. Cross-cutting health checks.

**Lifecycle handlers**:
- `on_ready` — init DB, load state, hydrate caches, start loops.
- `on_guild_join` — verify allowlist; auto-leave if not allowed.
- `on_guild_remove` — purge guild rows from DB.

---

## 4. Configuration (`.env`)

All configuration is loaded once at startup into a frozen dataclass: `Config` in [PDMain/Features/Core/config/config.py](PDMain/Features/Core/config/config.py). The dataclass is `@dataclass(frozen=True)` — env changes require a restart. Do not mutate `Config` at runtime.

The loader probes three paths in order:
1. `/home/container/.env` (Cybrancee root)
2. `/home/container/PDMain/.env`
3. `./.env`

Keys (see [PDMain/.env.example.template](PDMain/.env.example.template) for the canonical list):

| Key | Required | Default | Purpose |
|---|---|---|---|
| `DISCORD_TOKEN` | yes | — | Bot token. |
| `GUILD_ALLOWLIST` | yes | — | Comma/space-separated guild IDs. Bot auto-leaves any other guild. |
| `BOT_ADMIN_IDS` | no | `310233741354336257` (ExoArcher) | Users allowed to run console commands. |
| `BANNED_USER_IDS` | no | empty | Seeded into `banned_users` table at startup. |
| `QUARANTINED_GUILD_IDS` | no | empty | Seeded into `quarantined_guilds` table at startup. |
| `REFRESH_INTERVAL` | no | `120` | Seconds between feed refreshes. |
| `USER_AGENT` | no | `Paws Pendragon-DiscBot` | Sent to TTR API. |
| `AUTO_UPDATE` | no | `true` | If true, `git pull --ff-only` on startup. |
| `CHANNEL_CATEGORY` | no | `PendragonTTR` | Discord category name. |
| `CHANNEL_INFORMATION` | no | `tt-info` | Live info channel. |
| `CHANNEL_DOODLES` | no | `tt-doodles` | Doodle feed channel. |
| `CHANNEL_SUIT_CALCULATOR` | no | `suit-calc` | Static calculator channel. |
| Emoji vars | no | hard-coded fallbacks | See `Config.load()`. |

> **Note on README drift**: The README sometimes references `#tt-information` / `#tt-doodles` / `#suit-calculator` and a 90 s refresh. The *code* uses `tt-info` / `tt-doodles` / `suit-calc` and a 120 s default. Treat the code as authoritative; if you fix the drift, update README, not code defaults.

`update_env_var(name, value)` and `read_env_var(name)` exist in `config.py` for mutating the `.env` file in place (preserving comments). Used by ban/unban and quarantine commands so admin actions persist across restarts.

---

## 5. Persistence: SQLite Schema

Schema lives in [PDMain/Features/Core/db/db.py](PDMain/Features/Core/db/db.py). Tables:

1. **`guild_feeds`** — `(guild_id, feed_key) → channel_id, message_ids JSON`. Stores the message IDs the bot edits each refresh. `feed_key` is `"information"`, `"doodles"`, `"suit_calculator"`, or namespaced `"suit_threads.{faction}"`.
2. **`allowlist`** — runtime allowlist (in addition to env `GUILD_ALLOWLIST`).
3. **`announcements`** — pending announcement payloads, with TTL.
4. **`maintenance_msgs`** — sticky maintenance banners.
5. **`welcomed_users`** — users who have been DM'd the welcome message.
6. **`banned_users`** — bot-level user bans.
7. **`maintenance_mode`** — single-row table; global maintenance toggle.
8. **`quarantined_guilds`** — guilds whose feeds are paused without leaving.
9. **`blacklist`** — guild-level blacklist.
10. **`audit_log`** — append-only log of admin actions.

`init_db()` creates tables idempotently. `load_state()` and `save_state()` are the only paths the rest of the code uses to read/write persistent state — do not open ad-hoc connections in feature modules. There is a one-time JSON migration shim on first boot for legacy installations.

Constants in `bot.py`:
- `STATE_VERSION = 2`
- `ANNOUNCEMENT_TTL = 30 * 60` (30 min)
- `DOODLE_REFRESH = 12 * 60 * 60` (12 hr throttle on doodle reposts)
- `_REFRESH_COOLDOWN = 600` (10-min cooldown on `/pdrefresh`)

---

## 6. Slash Commands (11 total)

All defined in `bot.py`. Cross-installable as user apps (guild + user-install integration types).

| Command | bot.py line (approx.) | Visibility | Notes |
|---|---|---|---|
| `/ttrinfo` | 1012 | public | Population + field offices + invasions snapshot. |
| `/doodleinfo` | 1052 | public | Doodle trait guide. |
| `/helpme` | 1078 | public | Help embed. |
| `/invite` | 1132 | public | Invite link. |
| `/beanfest` | 1169 | public | Sillymeter / beanfest readout. |
| `/pdsetup` | 1214 | admin | Creates category + channels. |
| `/pdrefresh` | 1263 | admin | Force refresh; 10-min cooldown via `_REFRESH_COOLDOWN`. |
| `/pdteardown` | 1317 | admin | Removes category + channels. |
| `/pdboot` | 1333 | admin | Boot a guild from the runtime allowlist. |
| `/calculate` | 1403 | public | Suit-promotion calculator entry. |
| `/doodlesearch` | 1406 | public | Search doodle traits by name/criteria. |

Admin commands check `config.is_admin(user_id)` against `BOT_ADMIN_IDS`.

---

## 7. Console Commands (stdin)

Read from stdin in `Features/ServerManagement/console_commands/`. Used on the Cybrancee panel where there is no Discord-side admin UI for some operations.

`stop` / `s`, `restart` / `r`, `maintenance` / `m` / `maint`, `announce` / `a`, `ban`, `unban`, `quarlist`, `quarrefresh`, `quarmsg`, `guildadd`, `guildremove`, `forcerefresh`, `help` / `h` / `?`.

When adding a console command: register in the dispatcher, document in the `help` output, and update README's console section.

---

## 8. TTR API Client

Located in `Features/Core/ttr_api/`. Five endpoints:
- `population` — total + per-district counts.
- `fieldoffices` — active field offices and their remaining annexes.
- `doodles` — doodle market listings (per-district).
- `sillymeter` — beanfest meter state.
- `invasions` — current cog invasions.

The client sends the `USER_AGENT` string TTR requests. **Do not** loop tighter than `REFRESH_INTERVAL` against the TTR API; the loop already paces itself, and additional calls (e.g. inside slash commands) reuse the cached snapshot when possible (`cache_manager`).

---

## 9. Quarantine System

Quarantined guilds remain in the bot but receive **no feed updates**. Implementation:

- Set lives in `cache_manager.QuarantinedServerid` (in-memory, hydrated from `quarantined_guilds` table at startup).
- The refresh loop checks membership and skips quarantined guilds at `live_feeds.py` ~line 129.
- `quarantine_checks.py` and `unquarantine_checks.py` apply / lift quarantine and write through to both DB and `.env` (`QUARANTINED_GUILD_IDS`).

When debugging "why is feed X not updating in guild Y?", check the quarantine set first.

---

## 10. Auto-Update on Startup

Top of [PDMain/bot.py](PDMain/bot.py) (lines ~47–127): `_BOT_DIR`, `_GIT_REPO`, `_find_repo_dir()`, `_clear_bytecode_cache()`, the `AUTO_UPDATE` gate.

Behavior:
1. If `AUTO_UPDATE=true`, the bot resolves its repo dir.
2. Runs `git pull --ff-only`.
3. If the post-pull HEAD differs from the pre-pull HEAD, clears `__pycache__` and `os.execv`s itself to reload code.
4. If history has diverged (non-FF), logs a warning and continues with the existing checkout — **does not** hard-reset.

Hash comparison prevents restart loops when nothing changed. **Do not** revert this to `git reset --hard`; the soft path was a deliberate change to prevent silent loss of local hotfixes on the host.

---

## 11. Logging Conventions

Hierarchical `[guild][channel][thread]` prefix on log lines. When adding logs, follow the existing pattern so grep-by-guild keeps working. The bot uses Python's stdlib `logging`; output goes to stdout (Cybrancee captures it).

---

## 12. Rate-Limit Hygiene

- **Inter-guild edits**: 3-second sleep between guilds in the refresh loop.
- **Doodle reposts**: throttled to once per 12 hours per guild (`DOODLE_REFRESH`).
- **`/pdrefresh`**: 10-minute cooldown per invoker.
- **Discord edits**: never bulk-edit; always edit-in-place a known message ID. New messages are sent only when the persisted ID is missing or invalid.

If you find yourself adding a new periodic operation, ask whether it can ride the existing 120 s loop instead of spawning another task.

---

## 13. Working in This Codebase: Conventions

- **Feature modules own their state**. Do not reach across modules to mutate state directly; go through `db.load_state` / `db.save_state` or the module's public API.
- **`Config` is read-only**. To change configured values at runtime, mutate `.env` via `update_env_var()` and require a restart, or use a DB-backed table for things that should persist hot.
- **Slash command bodies stay thin**. Heavy work delegates into a feature module.
- **Embeds are built by formatters**, not inline in command handlers. New embed types go in `Features/Core/formatters/`.
- **Async everywhere**. No `time.sleep`; use `asyncio.sleep`. No blocking I/O on the event loop; aiosqlite for DB, aiohttp for HTTP.
- **Idempotency**. Setup/teardown commands must tolerate partial prior runs.
- **Read the BRIEFING.md** of any feature you touch.

---

## 14. Common Tasks: Quick Map

| Task | Touch |
|---|---|
| Add a new slash command | `bot.py` (registration) + new module under `Features/User/` or `Features/Admin/` |
| Add a new feed | New `feed_key`, formatter in `Features/Core/formatters/`, dispatch entry in `live_feeds.py`, default channel in `Config` + `.env.example.template` |
| Add a new TTR endpoint | New method in `Features/Core/ttr_api/` + cache entry in `cache_manager.py` |
| Add a console command | `Features/ServerManagement/console_commands/` + help text |
| Change DB schema | Add `CREATE TABLE IF NOT EXISTS` in `db.py`, add migration shim, bump `STATE_VERSION` if load semantics change |
| Add an env var | `Config` dataclass + `Config.load()` + `.env.example.template` + this file's table |

---

## 15. Known Drift / Watch-Outs

- README mentions `#tt-information` and `#tt-doodles`; code defaults to `tt-info` / `tt-doodles`. README is stale. (Recent commits renamed channel defaults.)
- README mentions a 90 s refresh; `Config.refresh_interval` defaults to **120** s.
- The deleted `PDMain/CLAUDE.md` and `PDMain/FEATURE_SPECIFICATIONS.md` are older versions kept for history. Do not consult them; this file and the new `FEATURE_SPECIFICATIONS.md` at the repo root supersede them.
- `bot.py` is around 1422 lines. If a planned change would push it past ~1600, extract a mixin or feature module instead.

---

## 16. When in Doubt

1. Read the relevant `BRIEFING.md`.
2. Read [README.md](README.md) for user-facing intent.
3. Read [FEATURE_SPECIFICATIONS.md](FEATURE_SPECIFICATIONS.md) for module-by-module spec.
4. `git log -- <file>` for the change history of a specific module.

The bot is multi-guild and runs in production. Prefer reversible changes; verify with `/pdrefresh` in a test guild before relying on the refresh loop to surface a bug.
