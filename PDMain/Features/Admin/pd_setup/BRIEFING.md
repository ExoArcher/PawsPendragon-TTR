# Admin/pd-setup Command Briefing

## Feature Purpose
Initialize guild for live feed tracking. Creates category + 3 channels, posts placeholder embeds, stores message IDs in database. Admin-only (requires Manage Channels + Manage Messages).

## Scope
- Slash command: `/pd-setup`
- Create "PendragonTTR" category (or use existing)
- Create/find 3 channels: #tt-info, #tt-doodles, #suit-calc
- Post placeholder embeds in each channel
- Store message IDs in state["guilds"][guild_id][feed_key]
- Save state to database

## Code to Extract
**From Main-1.5.0/bot.py**
- `@app_commands.command(name="pd-setup")` handler
- `_ensure_category()` - Create/find category
- `_ensure_channels()` - Create/find 3 channels
- `_ensure_placeholders()` - Post placeholder embeds
- `_ensure_suit_calculator_pin()` - Post suit calculator embeds
- `_ensure_suit_threads()` - Create suit calculator threads
- State management and save

## Channel Creation
```
Category: "PendragonTTR"
  #tt-info (for population, field offices, silly meter)
  #tt-doodles (for doodle listings)
  #suit-calc (for static suit point tables + faction threads)
```

## Placeholder Embeds
Each channel gets placeholder embeds with title "Loading {feed_key}..." and description "Fetching the latest data from TTR."

Suit calculator has 4 static embeds (not placeholders) showing point tables.

## Suit Calculator Threads
4 faction threads are created inside #suit-calc:
- "Sellbot" (red)
- "Cashbot" (teal)
- "Lawbot" (purple)
- "Bossbot" (green)

Each thread gets 3 static embeds.

## State Structure
After setup, state["guilds"][guild_id] contains:
```python
{
    "information": {
        "channel_id": 123456,
        "message_ids": [msg1, msg2, ...]
    },
    "doodles": {
        "channel_id": 234567,
        "message_ids": [msg3, msg4, ...]
    },
    "suit_calculator": {
        "channel_id": 345678,
        "message_ids": [msg5, msg6, msg7, msg8]
    },
    "suit_threads": {
        "sellbot": {
            "thread_id": 456789,
            "message_ids": [msg9, msg10, msg11]
        },
        # ... repeat for cashbot, lawbot, bossbot
    }
}
```

## Dependencies
- Core/config (feeds() dict for channel names, permissions checks)
- Core/db (save_state after setup)
- Core/formatters (FORMATTERS dict if using formatters for suit calculator)
- discord.py library

## Key Design Patterns
1. **Create or find** - Use existing channels if they exist
2. **Placeholder messages** - Temporary until first refresh updates them
3. **Message ID persistence** - Critical for in-place editing later
4. **Atomic save** - Save state only after all setup succeeds
5. **Permission checks** - Verify user has Manage Channels + Manage Messages

## API Calls
- `guild.create_category(name=...)` - Create category
- `guild.get_channel(channel_id)` - Find existing channel
- `guild.create_text_channel(name=..., category=...)` - Create channel
- `channel.send(embed=...)` - Post embed
- `message.pin(reason=...)` - Pin first message
- `channel.create_thread(name=..., type=...)` - Create thread
- `guild.get_thread(thread_id)` - Find existing thread
- Permission checks via ctx.author.guild_permissions

## Database Access
- Load state["guilds"][guild_id] if exists
- Create/update guild entry with new channel IDs and message IDs
- Save state atomically after completion

## Tests to Verify
- [ ] Category is created if missing
- [ ] 3 channels are created/found
- [ ] Placeholder embeds posted to each channel
- [ ] Suit calculator embeds posted (4 embeds)
- [ ] 4 faction threads created with 3 embeds each
- [ ] Message IDs stored in state["guilds"]
- [ ] State saved to database
- [ ] Existing channels are reused (idempotent)
- [ ] Permission checks pass for admin users
- [ ] Ephemeral response sent to user

## Special Requirements
- Category name: "PendragonTTR" (from config)
- Channel names from config.feeds() dict
- Suit calculator embeds are static (built by build_suit_calculator_embeds())
- Suit threads are named: "Sellbot", "Cashbot", "Lawbot", "Bossbot"
- First embed should be pinned (information, doodles, calculator)
- Permission check: User needs Manage Channels AND Manage Messages

## Integration Notes
- Slash command handler in bot.py
- Called once per guild by admin
- Can be re-run to refresh placeholders
- Idempotent (safe to run multiple times)

## Error Handling
- Forbidden error if bot lacks Create Channel permission
- HTTPException for channel creation failures
- Handle missing category gracefully (create it)

## Reference Implementation
See Main-1.5.0/bot.py for complete pd-setup command handler and helper methods.
