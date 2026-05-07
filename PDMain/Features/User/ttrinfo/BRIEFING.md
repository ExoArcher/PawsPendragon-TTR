# User/ttrinfo Command Briefing

## Feature Purpose
DM user current TTR game state: districts with populations, field office invasions, and silly meter status. Works as a User App (no server membership required).

## Scope
- Slash command: `/ttrinfo`
- Fetch TTR API endpoints: population, fieldoffices, sillymeter
- Format embeds using Core/formatters
- Send embeds via DM to user
- Handle DM failures gracefully

## Code to Extract
**From Main-1.5.0/bot.py**
- `@app_commands.command(name="ttrinfo")` handler
- Fetch population, fieldoffices, sillymeter endpoints
- Call formatter: format_information(data)
- Send embeds to user via DM

## Command Flow
```
1. User invokes /ttrinfo (anywhere: server, DM, group, User App)
2. Check ban status (_reject_if_banned)
3. Send welcome DM if first-time (_maybe_welcome)
4. Fetch population + fieldoffices + sillymeter from TTR API
5. Call format_information({data})
6. DM embeds to user
7. Send ephemeral response: "Sent to your DMs"
```

## Embeds Sent
Information embed includes:
- Districts with population counts
- Field office invasions (4 factions)
- Silly meter team status

## Dependencies
- Core/ttr-api (fetch population, fieldoffices, sillymeter)
- Core/formatters (format_information)
- Infrastructure/user-system (_reject_if_banned, _maybe_welcome)
- discord.py library

## Key Design Patterns
1. **User App compatible** - No guild check, works anywhere
2. **DM-first** - Send embeds to DM, not channel
3. **Ephemeral response** - Tell user "check your DMs"
4. **Graceful DM failure** - If user has DMs blocked, still respond
5. **Ban check** - Reject before doing work
6. **Welcome DM** - Send once per user

## API Calls
- TTRApiClient.fetch("population")
- TTRApiClient.fetch("fieldoffices")
- TTRApiClient.fetch("sillymeter")
- user.send(embeds=...)
- ctx.response.send_message(content=..., ephemeral=True)

## Database Access
- Check banned_users
- Check welcomed_users
- Add to welcomed_users if first-time

## Tests to Verify
- [ ] /ttrinfo fetches all 3 endpoints
- [ ] format_information called with correct data
- [ ] Embeds sent to user DM
- [ ] Ephemeral response sent in channel
- [ ] Ban check prevents banned users
- [ ] Welcome DM sent to first-time users
- [ ] Works in User App (no guild context)
- [ ] Works in DMs, servers, group chats
- [ ] DM failure handled gracefully

## Special Requirements
- Works as User App (no server membership required)
- Works in DMs, servers, group chats
- DM failure should not prevent command success
- Ban check before doing work

## Integration Notes
- Slash command handler in bot.py
- Called frequently by users
- TTR API may return 503 (maintenance) - handle gracefully

## Error Handling
- TTR API 503 - Skip fetch, inform user ("API under maintenance")
- DM blocked - Still send ephemeral response in channel
- Timeout - Set reasonable timeout for API fetches
- Banned user - Reject with ephemeral message

## Response Pattern
Ephemeral message:
```
"Sent info about districts, invasions, and silly meter status to your DMs!"
```

If DM failed:
```
"I tried to send the info to your DMs, but they appear to be closed. Try enabling DMs and use /helpme for command list."
```

## Reference Implementation
See Main-1.5.0/bot.py for complete ttrinfo command handler.
