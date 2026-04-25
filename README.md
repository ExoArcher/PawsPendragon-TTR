# LanceAQuack – V1.1

Multi-guild Discord bot that mirrors the public Toontown Rewritten APIs
into live-updating channels. One hosted instance can serve up to 20+
Discord servers from a single allowlist.

## Channels each server gets

After an admin runs `/ttr_setup`:

- **`#tt-information`** — districts (population, invasions, Safe /
  SpeedChat-Only flags) plus Field Offices including the hidden
  Kaboomberg quest office.
- **`#tt-doodles`** — every doodle for sale, sorted into Best / Great /
  Good tiers with star ratings driven by trait quality.

Both channels are kept clean: one pinned message per embed, edited in
place on a timer.

## Slash commands

All four require **Manage Server**:

- `/ttr_setup` — create channels and start tracking this server.
- `/ttr_refresh` — force an immediate refresh.
- `/ttr_status` — show what the bot is currently editing.
- `/ttr_teardown` — stop tracking this server (channels are kept).

Bot-owner only:

- `/laq_announce` — broadcast a message to every tracked server (auto-deletes after 30 min).
- `/laq_guild_add` — add a server to the allowlist at runtime without restarting.
- `/laq_guild_remove` — remove a server from the allowlist; the bot will leave it.
- `/laq_clear` — delete all bot messages in a server and reset its tracking state.

## Hosting

Designed for **Cybrancee** Discord Bot Hosting (<https://cybrancee.com/discord-bot-hosting>).

**Recommended plan:** Basic ($1.49/mo — 512 MB RAM). The bot uses
~50–100 MB across up to 20 servers, so this plan has plenty of
headroom.

For full setup instructions see **`DEPLOY.md`**.

## Quick local start

1. Copy `.env.example` to `.env` and fill in `DISCORD_TOKEN` plus the
   server IDs you want to allow in `GUILD_ALLOWLIST`.
2. `pip install -r requirements.txt`
3. `python bot.py`

## What's in this folder

| File | Purpose |
|---|---|
| `bot.py` | Multi-guild bot core. Slash commands, refresh loop, allowlist enforcement. |
| `config.py` | Loads `.env` into a typed `Config`. Parses `GUILD_ALLOWLIST`. |
| `formatters.py` | Renders TTR API JSON into the two embed kinds. |
| `ttr_api.py` | Async aiohttp client for the public TTR endpoints. |
| `requirements.txt` | Pinned dependencies. |
| `Procfile` | `worker: python3 bot.py` for hosts that read it. |
| `runtime.txt` | Python 3.11 pin. |
| `.env.example` | Template config — safe to commit. Fill values into `.env`. |
| `.env` | Your real secrets — **never commit this file.** |
| `.gitignore` | Keeps `.env`, `state.json`, and pyc out of git. |
| `DEPLOY.md` | Cybrancee step-by-step + invite URL + troubleshooting. |

## Version history

**V1.1** — Cybrancee hosting edition.
- Rewrote `DEPLOY.md` for Cybrancee (Basic plan recommended).
- Secured `.env` — token placeholder only, never committed.
- No code changes required; bot is fully compatible as-is.

**0.1.0** — first packaged release.
- Multi-guild rewrite with `/ttr_setup`, allowlist, and per-guild
  message persistence.
- Doodle tier overhaul (Perfect / Amazing / Great / Good / OK / Bad).
- Two-line district format with reordered legend.
- Two-line field office format with Kaboomberg pinned to the top.
