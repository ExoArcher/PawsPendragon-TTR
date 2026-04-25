# Hosting on PebbleHost + multi-server invite guide

This bot is multi-guild. One PebbleHost instance can serve your Discord
server **and** your friend's Discord server (and any others you add to
the allowlist) at the same time. Each server runs `/ttr_setup` once
and gets its own `#tt-information` and `#tt-doodles` channels with the
same live embeds.

---

## 1. Get the bot's credentials

1. Go to <https://discord.com/developers/applications> and open your
   bot's application page (or create a new one).
2. **Bot tab** → reveal the token, copy it. This is your `DISCORD_TOKEN`.
3. **General Information tab** → copy the **Application ID**. You'll
   need it for the invite URL below.
4. **Bot tab → Privileged Gateway Intents** → leave them all *off*. The
   bot only uses default intents.
5. **Bot tab → Public Bot** → turn this **off** while it's a private
   bot. Combined with the allowlist, this means only you can install it.

## 2. Collect the guild IDs

For every server that should be allowed to use the bot:

1. In Discord, go to **User Settings → Advanced → Developer Mode** and
   turn it on.
2. Right-click the server icon → **Copy Server ID**.
3. Save the IDs. You'll list them as `GUILD_ALLOWLIST`.

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

Your friend opens this link, picks their server, clicks **Authorize**.
If their server ID isn't in `GUILD_ALLOWLIST`, the bot leaves
immediately and DMs them a note explaining how to ask you to add them.

## 4. Upload to PebbleHost

PebbleHost's *Bot Hosting* product runs a Pterodactyl panel. The flow:

1. Buy a Bot Hosting plan and pick **Python (Generic)** as the egg.
2. Open the server's panel and click the **File Manager** tab.
3. Drag-and-drop everything in this folder *except* `state.json`,
   `.env`, and `__pycache__/`. Specifically upload:
   - `bot.py`
   - `config.py`
   - `formatters.py`
   - `ttr_api.py`
   - `requirements.txt`
   - `Procfile`
   - `runtime.txt`
4. PebbleHost will install everything in `requirements.txt`
   automatically the next time the server starts.

> **Tip:** If PebbleHost's panel has a *Pull from Git* feature, push
> this folder to a private GitHub repo and pull it instead — that way
> updates are one click.

## 5. Set the startup command

In the panel, open the **Startup** tab. You should see a field labelled
something like *"Python File"* or *"Startup Command"*.

- **Python File:** `bot.py`
- **Startup Command** (if your egg uses one): `python3 bot.py`

The included `Procfile` (`worker: python3 bot.py`) is ignored by some
PebbleHost eggs but is there as a fallback. The `runtime.txt` pins
Python 3.11.

## 6. Set environment variables

Still on the **Startup** tab (or **Variables** tab on some eggs), add:

| Variable | Value | Notes |
|---|---|---|
| `DISCORD_TOKEN` | your bot token | Required. **Never** commit this. |
| `GUILD_ALLOWLIST` | `123,456` | Comma-separated server IDs. |
| `REFRESH_INTERVAL` | `60` | Optional. Seconds between refreshes. |
| `USER_AGENT` | `ttr-discord-bot (contact: you@example.com)` | The TTR API asks for a contact-y UA. |

You can set every star/jellybean/cog emoji variable here too if you
want to override the defaults. See `.env.example` for the full list.

> Setting them in the panel is preferred over uploading a `.env` file
> because the panel masks secrets and PebbleHost's backups don't
> capture them in plaintext.

## 7. Start the bot

Hit **Start** in the panel. Watch the console — you should see:

```
INFO ttr-bot: Logged in as your-bot#1234 (id=...)
INFO ttr-bot: In 1 guild(s); allowlist has 2 entries
```

If you see `Refusing to join non-allowlisted guild ...`, the bot was
invited to a server that isn't on `GUILD_ALLOWLIST`. Add the ID and
restart.

## 8. Run `/ttr_setup` in each server

In **your** server, type `/ttr_setup`. The bot will create
`#tt-information` and `#tt-doodles` under a `Toontown Rewritten`
category and start refreshing them.

Send your friend the invite link from step 3. After they invite the
bot to their server, **they** run `/ttr_setup` themselves — they don't
need any of your credentials, just the Manage Server permission in
their own server. Their channels will mirror yours independently.

## 9. Verify it's working

In any tracked server:

- `/ttr_status` — shows the channel/message IDs the bot is editing.
- `/ttr_refresh` — forces an immediate fetch (handy after editing
  formatters).
- `/ttr_teardown` — stops tracking that server (channels are NOT
  deleted; you can run `/ttr_setup` again later).

All four commands require **Manage Server** so random members can't
spam them.

---

## Adding more friends later

1. Get their server ID (step 2).
2. Edit `GUILD_ALLOWLIST` in PebbleHost's Startup/Variables tab —
   append the new ID, comma-separated.
3. Restart the bot from the panel.
4. Send them the invite link. They run `/ttr_setup`. Done.

## Troubleshooting

**Bot is in the server but `/ttr_setup` errors with "missing
permissions".**
The bot was invited with too few permissions. Re-invite using the
URL in step 3 (don't strip the `permissions=93200` query parameter).

**Slash commands don't appear after invite.**
Discord caches global slash commands for up to an hour the *first*
time they're synced. Wait a bit, or have the user kick + re-invite the
bot. Subsequent updates propagate within a minute.

**429 Too Many Requests in the logs.**
Increase `REFRESH_INTERVAL` to `90` or `120`. Discord throttles edits
per channel, and the TTR API server-side cache is ~10s anyway, so
faster than 60s gains you nothing.

**Channels were deleted accidentally.**
Run `/ttr_teardown` then `/ttr_setup` again. The bot will recreate
everything fresh and forget the dead message IDs.

**Bot leaves a server it should be in.**
Check that the server ID is in `GUILD_ALLOWLIST`. The check is exact
match against the integer ID — no whitespace, no quotes.
