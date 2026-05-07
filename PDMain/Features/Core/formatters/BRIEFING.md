# Core/formatters Feature Briefing

## Feature Purpose
Convert TTR API JSON responses into richly formatted Discord embeds. Pure functions with no side effects. Central registry of all feed formatters via the FORMATTERS dict.

## Scope
- Implement formatter functions that convert TTR API data to discord.Embed objects
- Export FORMATTERS dict mapping feed_key → formatter function
- Format data for:
  1. **information** feed (districts, field offices, silly meter)
  2. **doodles** feed (doodle listings with traits and ratings)
  3. **sillymeter** feed (silly meter progress and team status)
  4. Support custom emoji IDs from config (fallback to plaintext if not set)

## Code to Extract
**From Main-1.5.0/formatters.py (entire file, ~1800 lines)**
- format_information() - creates embed(s) for districts, field offices, sillymeter
- format_doodles() - creates embed(s) for doodle data
- format_sillymeter() - creates embed(s) for silly meter
- FORMATTERS dict registration: `FORMATTERS = {"information": format_information, "doodles": format_doodles, ...}`
- Helper functions for color coding, emoji usage, truncation

## TTR Data to Format
- **population** API → information embed (districts, populations)
- **fieldoffices** API → information embed (field office locations and progress)
- **doodles** API → doodles embed (name, traits, rarity)
- **sillymeter** API → sillymeter embed (team progress, laff boost status)

## TTR Domain Knowledge Required
- **Districts**: Server instances, shown with population counts
- **Field Offices**: 4 factions (Sellbot, Cashbot, Lawbot, Bossbot) with progress bars
- **Doodles**: Collectible creatures with traits (e.g., color, size, personality)
- **Silly Meter**: Teams competing, laff boost at milestones, color coding by faction
- **Laff Boost**: Shows in orange with white glow, +8 temporary laff when active

## Dependencies
- Core/config (for custom emoji IDs)
- discord.py (for discord.Embed)

## Key Design Patterns
1. **Pure functions** - No side effects, no state mutation
2. **FORMATTERS dict** - Maps feed_key to formatter; used by bot.py's _update_feed()
3. **Embed creation** - Return list[discord.Embed] to support multiple embeds per feed
4. **Emoji fallback** - Use custom emoji IDs if set in config, otherwise plaintext
5. **Color coding** - Different colors for different factions/teams

## API Calls
- discord.Embed creation (discord.py)
- Color setting (discord.Color)
- Emoji mentions (if custom emoji IDs are set)

## Database Access
- None (pure formatters)

## Tests to Verify
- [ ] FORMATTERS dict exists and contains all feed keys
- [ ] format_information() returns list[discord.Embed]
- [ ] format_doodles() returns list[discord.Embed]
- [ ] format_sillymeter() returns list[discord.Embed]
- [ ] Embeds are properly titled and colored
- [ ] Custom emoji IDs are used when set in config
- [ ] Plaintext fallback works when emoji IDs are missing
- [ ] Data truncation works for long content (Discord embed limits)

## Special Requirements
- Embeds should be Discord-friendly (under 6000 chars, proper formatting)
- Support multiple embeds per feed (e.g., doodles might span multiple pages)
- Color scheme should match faction themes (Sellbot red, Cashbot teal, Lawbot purple, Bossbot green)

## Integration Notes
- Called by _update_feed() in bot.py: `formatter = FORMATTERS.get(feed_key)`
- Never called directly by commands; always via the bot's refresh loop
- Embeds are edited in place in Discord channels (must fit embed size limits)

## Reference Implementation
See Main-1.5.0/formatters.py for the complete original implementation.
