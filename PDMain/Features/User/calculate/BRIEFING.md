# User/calculate Command Briefing

## Feature Purpose
Show suit point progression tables and activity recommendations for a given suit/level/current_points. Works as a User App (no server membership required). Includes interactive suit calculator embeds in Discord with faction threads.

## Scope
- Slash command: `/calculate <suit> <level> <current_points>`
- Build suit calculator embeds showing V1 and V2 point quotas
- Show activity recommendations based on level
- Display faction-specific point tables
- Support both abbrevation and full suit names
- Support 2.0 suit notation (e.g. "RB2.0")
- Handle DM and channel responses
- Calculate laff boost milestone congratulations

## Code to Extract
**From Main-1.5.0/bot.py and calculate.py**
- `@app_commands.command(name="calculate")` handler
- Suit name resolution (abbrev → full name, handle "2.0" suffix)
- `build_suit_calculator_embeds()` - Generate static V1/V2 point tables
- `build_faction_thread_embeds()` - Generate faction-specific embeds for suit threads
- Activity recommendations logic based on level
- Laff boost milestone detection and congratulations

## Command Flow
```
1. User invokes /calculate <suit> <level> <current_points>
2. Check ban status (_reject_if_banned)
3. Parse suit name (accept abbrevs: RB, CB, LB, BB, and 2.0 suffixes)
4. Validate level (1-50)
5. Resolve to full suit name
6. Build calculator embeds with:
   - V1 point quota table
   - V2 point quota table
   - Activity recommendations for next 5 levels
7. Check if current_points hits a laff boost milestone (50-70-80-etc)
8. If milestone hit, add congratulations message
9. Send embed to channel
10. Send ephemeral response
```

## Embeds Sent
Calculator response includes:
- **Suit Type** (IMPORTANT: label as "Suit Type" not "faction")
- Current level and points
- Points to next level (V1 and V2)
- Activity recommendations (combat, toontasks, field office, etc.)
- Full V1 and V2 point quota tables for reference

### Laff Boost Congratulations
When a user reaches a laff boost milestone:
```
🎉 Congratulations! You've reached a laff boost milestone (XX laff)!
```

Milestones: 50, 70, 80, 100+ laff

## Dependencies
- Infrastructure/user-system (_reject_if_banned)
- discord.py library
- Internal suit data structures (point quotas, activity ranges)

## Key Design Patterns
1. **User App compatible** - No guild check, works anywhere
2. **Flexible input** - Accept suit name, abbreviation, or abbreviation + "2.0"
3. **Rich embeds** - Show point tables and recommendations
4. **Milestone detection** - Recognize and celebrate laff boost achievements
5. **Case-insensitive** - Accept uppercase and lowercase suit names
6. **Ban check** - Reject before doing work

## API Calls
- user.send(embed=...) or ctx.response.send_message(embed=...)
- ctx.response.send_message(content=..., ephemeral=True)

## Database Access
- Check banned_users

## Tests to Verify
- [ ] /calculate accepts suit name (full name)
- [ ] /calculate accepts suit abbreviation (RB, CB, LB, BB)
- [ ] /calculate accepts 2.0 suffix (RB2.0, etc)
- [ ] /calculate validates level (1-50)
- [ ] /calculate calculates points to next level correctly (V1 and V2)
- [ ] Activity recommendations shown for next 5 levels
- [ ] Laff boost milestones detected (50, 70, 80, 100+)
- [ ] Congratulations message shown for milestone
- [ ] "Suit Type" label used (not "faction")
- [ ] Ban check prevents banned users
- [ ] Works in User App (no guild context)
- [ ] Works in DMs, servers, group chats
- [ ] Full point quota tables displayed

## Special Requirements
- **CRITICAL:** Label as "Suit Type" NOT "faction" in embeds
- **CRITICAL:** Show congratulations message for laff boost milestones (50, 70, 80, etc)
- Accept suit names: Sellbot (RB), Cashbot (CB), Lawbot (LB), Bossbot (BB)
- Accept abbreviations: RB, CB, LB, BB (case-insensitive)
- Accept 2.0 suffix: RB2.0, CB2.0, LB2.0, BB2.0 (suit point tables differ for 2.0)
- Level range: 1-50
- Points range: 0-9999
- V1 and V2 point quotas must be accurate per suit and level
- Activity recommendations vary by level band

## Integration Notes
- Slash command handler in bot.py
- Called frequently by users planning gear progression
- Pure computation (no API calls)
- Response is instant

## Error Handling
- Invalid suit name - Ephemeral error message with suggestion
- Invalid level - Ephemeral error message with valid range
- Invalid points - Ephemeral error message with valid range
- Banned user - Reject with ephemeral message

## Response Pattern
Success:
```
"Here's your suit progression for [Suit Type] level [X]:"
[Calculator embed with tables and recommendations]
```

If milestone hit:
```
🎉 Congratulations! You've reached a [XX] laff boost!
```

Error:
```
"I don't recognize suit '[input]'. Try: RB, CB, LB, BB (or full names like 'Sellbot')."
```

## Reference Implementation
See Main-1.5.0/bot.py and Main-1.5.0/calculate.py for complete calculate command handler and suit data.
