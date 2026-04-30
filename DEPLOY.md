# Hosting on Cybrancee + multi-server invite guide

This bot is multi-guild. One Cybrancee instance can serve your Discord
server **and** your friends' Discord servers (up to however many you add
to the allowlist) at the same time. Each server runs `/ttr_setup` once
and gets its own `#tt-information` and `#tt-doodles` channels with the
same live embeds.

**Recommended plan:** Basic ($1.49/mo — 512 MB RAM, 15 GB Storage).
The bot uses ~50–100 MB at runtime even across 20 servers, so the Basic
plan gives you plenty of headroom. All Cybrancee plans include Unlimited
CPU Time, meaning your bot never idles or sleeps.

---

## 1. Get the bot's credentials

1. Go to <https://discord.com/developers/applications> and open your
   bot's application page (or create a new one).
2. **Bot tab** → reveal the token, copy it. This is your `DISCORD_TOKEN`.
3. **General Information tab** → copy the **Application ID**. You'll
   need it for the invite URL in step 3.
4. **Bot tab → Privileged Gateway Intents** → leave them all *off*. The
   bot only needs default intents.
5. **Bot tab → Public Bot** → turn this **off** while it's a private
   bot. Combined with the allowlist, this prevents anyone from inviting
   it to random servers.

## 2. Collect the guild IDs

For every server that should be allowed to use the bot:

1. In Discord, go to **User Settings → Advanced → Developer Mode** and
   turn it on.
2. Right-click the server icon → **Copy Server ID**.
3. Save the IDs — you'll need them for `GUILD_ALLOWLIST` in step 5.

## 3. Build the OAuth invite link

Replace `<APP_ID>` with the Application ID from step 1.3:

```
https://discord.com/api/oauth2/authorize?client_id=<APP_ID>&permissions=93200&scope=bot+applications.commands
```

The permission integer `93200` grants exactly:

- **Manage Channels** — to create the `Toontown Rewritten` category and
  feed channels.
- **View Channels**, **Send Messages**, **Embed Links**,
  **Read Message History**, **Manage Messages** — to post, edit, and
  pin the live feed embeds.

## 4. Purchase and set up your Cybrancee plan

1. Go to <https://cybrancee.com/discord-bot-hosting> and order the
   **Basic** plan.
2. During checkout, select **Python** as the language/egg.
3. Choose a server location closest to you or your players (any region
   works — the TTR API is globally accessible).
4. Complete checkout and wait for your welcome email with panel login
   details.

## 5. Upload your files via the panel

1. Log into your Cybrancee panel (the link is in your welcome email).
2. Select your bot server and click the **File Manager** tab.
3. Upload everything **except** `.env` and `state.json`. Specifically:
   - `bot.py`
   - `config.py`
   - `formatters.py`
   - `ttr_api.py`
   - `requirements.txt`
   - `Procfile`
   - `runtime.txt`
4. Cybrancee will automatically install the packages in `requirements.txt`
   the next time the server starts.

> **Tip — use Git instead of dragging files:**
> If your panel has a *Git* or *Pull from GitHub* feature, point it at
> your private GitHub repo and pull. Future updates become a one-click
> pull + restart rather than re-uploading files.

## 6. Set the startup command

In the panel, open the **Startup** tab and find the startup command or
Python file field:

- **Python File:** `bot.py`
- **Startup Command** (if shown): `python3 bot.py`

The included `Procfile` (`worker: python3 bot.py`) acts as a fallback
for panels that read it automatically.

## 7. Set environment variables

In the **Startup** or **Variables** tab, add the following. Do **not**
upload your `.env` file — setting them here is safer because the panel
masks secrets and Cybrancee backups don't capture them in plaintext.

| Variable | Value | Notes |
|---|---|---|
| `DISCORD_TOKEN` | your bot token | **Required.** Never put this in a file you commit. |
| `GUILD_ALLOWLIST` | `123456789,987654321` | Comma-separated server IDs from step 2. |
| `BOT_OWNER_IDS` | your Discord user ID | Comma-separated. Controls who can run `/pd_*` commands. |
| `REFRESH_INTERVAL` | `90` | Optional. Seconds between refreshes (60–90 is ideal). |
| `USER_AGENT` | `PawsPendragon-DiscBot (contact: you@example.com)` | The TTR API asks for a contact-y UA. |

You can optionally set all the star/emoji variables here too — see
`.env.example` for the full list with descriptions.

## 8. Start the bot

Click **Start** in the panel. Watch the console — within a few seconds
you should see:

```
INFO ttr-bot: Logged in as YourBot#1234 (id=...)
INFO ttr-bot: In 1 guild(s); env-allowlist=2 entries; runtime-allowlist=0 entries
```

If you see `Refusing to join non-allowlisted guild ...`, the bot was
invited to a server whose ID isn't in `GUILD_ALLOWLIST`. Add the ID in
the Variables tab and restart.

## 9. Run `/ttr_setup` in each server

In your Discord server, type `/ttr_setup`. The bot will create
`#tt-information` and `#tt-doodles` under a `Toontown Rewritten`
category and start refreshing them every `REFRESH_INTERVAL` seconds.

Share the invite link from step 3 with any friends you want to add.
After they invite the bot to their server, **they** run `/ttr_setup`
themselves — they don't need any of your credentials, just Manage Server
permission in their own server.

## 10. Verify it's working

In any tracked server:

- `/ttr_status` — shows the channel/message IDs the bot is editing.
- `/ttr_refresh` — forces an immediate data fetch.
- `/ttr_teardown` — stops tracking that server (channels are kept;
  run `/ttr_setup` again to restart tracking).

All four commands require **Manage Server** so regular members can't
spam them.

---

## Adding more servers later

1. Get their server ID (step 2).
2. In the Cybrancee panel → **Variables** tab, append the new ID to
   `GUILD_ALLOWLIST` (comma-separated).
3. Restart the bot from the panel.
4. Send them the invite link from step 3. They run `/ttr_setup`. Done.

Alternatively, use the `/pd_guild_add <server_id>` slash command to
add a server to the *runtime* allowlist without restarting — handy for
adding servers on the fly.

---

## Troubleshooting

**`/ttr_setup` errors with "missing permissions."**
The bot was invited with too few permissions. Re-invite using the URL
from step 3 — make sure `permissions=93200` is in the link.

**Slash commands don't appear after invite.**
Discord caches global slash commands for up to an hour the first time.
Wait, or kick + re-invite the bot. Per-guild syncs (which `on_ready`
triggers automatically) propagate within seconds.

**`429 Too Many Requests` in the logs.**
Increase `REFRESH_INTERVAL` to `90` or `120` in the Variables tab and
restart. Discord throttles edits per channel; the TTR API server-side
cache is ~10s anyway, so faster than 60s gains nothing.

**Channels were deleted accidentally.**
Run `/ttr_teardown` then `/ttr_setup` again. The bot recreates
everything fresh and forgets the dead message IDs.

**Bot leaves a server it should be in.**
The server ID is not in `GUILD_ALLOWLIST`. Add it in the Variables tab
and restart, or use `/pd_guild_add` from a server the bot is already in.

**`state.json` — do I need to upload it?**
No. The bot creates `state.json` automatically on first run. Uploading
your local copy would just pre-seed it with your channel/message IDs,
which is only useful if you're migrating an existing install.
