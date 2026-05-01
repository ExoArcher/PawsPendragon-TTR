# User/helpme Command Briefing

## Feature Purpose
DM user the complete command list with descriptions. Works as a User App (no server membership required).

## Scope
- Slash command: `/helpme`
- Build command list embed with descriptions
- Send embed via DM to user
- Handle DM failures gracefully
- Provide both DM and channel fallback

## Code to Extract
**From Main-1.5.0/bot.py**
- `@app_commands.command(name="helpme")` handler
- Build command list embed (no API call needed)
- Send embed to user via DM
- Fallback to ephemeral channel message if DM blocked

## Command Flow
```
1. User invokes /helpme (anywhere: server, DM, group, User App)
2. Check ban status (_reject_if_banned)
3. Build command list embed from hardcoded list
4. Attempt to DM embed to user
5. If DM fails, send ephemeral message in channel instead
6. Send ephemeral response: "Check your DMs" or "See below"
```

## Embeds Sent
Command list embed includes:
- User commands: /ttrinfo, /doodleinfo, /calculate, /invite, /helpme
- Admin commands: /pd-setup, /pd-refresh, /pd-teardown (only shown if user is admin)
- Each command with description and usage example
- Brief note about console commands (not user-accessible)

## Dependencies
- Infrastructure/user-system (_reject_if_banned)
- discord.py library

## Key Design Patterns
1. **User App compatible** - No guild check, works anywhere
2. **DM-first** - Try to send to DM, fall back to ephemeral
3. **Graceful DM failure** - If user has DMs blocked, send ephemeral in channel
4. **Ban check** - Reject before doing work
5. **No API calls** - Pure local data, instant response
6. **Admin-aware** - Optionally show admin commands if user is admin

## API Calls
- user.send(embed=...)
- ctx.response.send_message(content=..., ephemeral=True)

## Database Access
- Check banned_users

## Tests to Verify
- [ ] /helpme builds command list instantly
- [ ] Command list includes all 6+ user commands
- [ ] Admin commands only shown to admins
- [ ] Embed sent to user DM successfully
- [ ] If DM blocked, ephemeral message sent in channel
- [ ] Ban check prevents banned users
- [ ] Works in User App (no guild context)
- [ ] Works in DMs, servers, group chats
- [ ] DM failure handled gracefully

## Special Requirements
- Works as User App (no server membership required)
- Works in DMs, servers, group chats
- No API calls (all static data)
- DM failure should not prevent command success
- Ban check before doing work

## Integration Notes
- Slash command handler in bot.py
- Called by users seeking help
- Response is instant (no network I/O)

## Error Handling
- DM blocked - Send ephemeral message in channel instead
- No timeout needed (no I/O)
- Banned user - Reject with ephemeral message

## Response Pattern
If DM sent:
```
"Sent command list to your DMs!"
```

If DM blocked, ephemeral embed in channel:
```
(Full command list embed displayed in channel)
```

## Reference Implementation
See Main-1.5.0/bot.py for complete helpme command handler.
