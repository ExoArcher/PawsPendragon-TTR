# LanceAQuack – Pebble Release 0.1.0

Multi-guild Discord bot that mirrors the public Toontown Rewritten APIs
into live-updating channels. One PebbleHost instance can serve any
number of Discord servers from a single allowlist.

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
- `/ttr_status` — show what the bot is editing here.
- `/ttr_teardown` — stop tracking this server (channels are kept).

## Quick start

1. Copy `.env.example` to `.env` and fill in `DISCORD_TOKEN` plus the
   server IDs you want to allow in `GUILD_ALLOWLIST`.
2. `pip install -r requirements.txt`
3. `python bot.py`

For PebbleHost deployment, OAuth invite URLs, and adding more friends
later, see **`DEPLOY.md`**.

## What's in this folder

| File | Purpose |
|---|---|
| `bot.py` | Multi-guild bot core. Slash commands, refresh loop, allowlist enforcement. |
| `config.py` | Loads `.env` into a typed `Config`. Parses `GUILD_ALLOWLIST`. |
| `formatters.py` | Renders TTR API JSON into the two embed kinds. |
| `ttr_api.py` | Async aiohttp client for the public TTR endpoints. |
| `requirements.txt` | Pinned dependencies. |
| `Procfile` | `worker: python3 bot.py` for hosts that read it. |
| `runtime.txt` | Python 3.11 pin (PebbleHost-friendly). |
| `.env.example` | Template config. Safe to commit. |
| `.gitignore` | Keeps `.env`, `state.json`, and pyc out of git. |
| `DEPLOY.md` | PebbleHost step-by-step + invite URL + troubleshooting. |

## Version

**0.1.0** — first packaged Pebble-ready release.
- Multi-guild rewrite with `/ttr_setup`, allowlist, and per-guild
  message persistence.
- Doodle tier overhaul (Perfect / Amazing / Great / Good / OK / Bad).
- Two-line district format with reordered legend.
- Two-line field office format with Kaboomberg pinned to the top.
