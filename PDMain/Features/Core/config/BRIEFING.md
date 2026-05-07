# Core/config Feature Briefing

## Feature Purpose
Centralized configuration management that loads environment variables into a frozen `Config` dataclass at startup. All env var access is centralized here, preventing scattered config lookups across the codebase.

## Scope
- Load and validate required environment variables (DISCORD_TOKEN, GUILD_ALLOWLIST, BOT_ADMIN_IDS)
- Load optional environment variables with sensible defaults
- Provide helper functions for parsing ID lists and integers
- Export a frozen Config dataclass
- Define channel names and emoji IDs for customization

## Code to Extract
**From Main-1.5.0/config.py (entire file, 125 lines)**
- Lines 1-56: Helper functions (_required, _parse_id_list, _int_env)
- Lines 58-125: Config dataclass with load() classmethod, feeds() method, is_guild_allowed(), is_admin()

## Environment Variables (Required)
```
DISCORD_TOKEN          - Bot token from https://discord.com/developers/applications
GUILD_ALLOWLIST        - Comma/space-separated server IDs the bot can join
BOT_ADMIN_IDS          - Comma/space-separated user IDs for console commands
```

## Environment Variables (Optional with Defaults)
```
REFRESH_INTERVAL           (default: 90)              - seconds between live feed refreshes
USER_AGENT                 (default: "ttr-discord...")  - descriptive string for TTR API
CHANNEL_CATEGORY           (default: "Toontown...")    - category name for channels
CHANNEL_INFORMATION        (default: "tt-info") - channel for live feeds
CHANNEL_DOODLES            (default: "tt-doodles")     - channel for doodle info
CHANNEL_SUIT_CALCULATOR    (default: "suit-calc")- channel for suit calculator
BANNED_USER_IDS            (optional)                  - user IDs to ban from bot
QUARANTINED_GUILD_IDS      (optional)                  - guilds to quarantine
JELLYBEAN_EMOJI            (optional)                  - custom emoji ID for jellybeans
COG_EMOJI                  (optional)                  - custom emoji ID for cogs
STAR_*                     (optional)                  - custom emoji IDs for stars
```

## Dependencies
- None (foundational module, no dependencies)

## Key Design Patterns
1. **Frozen dataclass** - Config cannot be mutated after startup; env var changes require restart
2. **Centralized parsing** - _required(), _parse_id_list(), _int_env() helper functions
3. **Graceful defaults** - Optional env vars have sensible defaults, never crash on missing optional vars
4. **Type safety** - All values have explicit types (str, frozenset[int], int, etc.)

## API Calls
- None (pure configuration loading)

## Database Access
- None (configuration only)

## Tests to Verify
- [ ] DISCORD_TOKEN is required; missing raises RuntimeError
- [ ] GUILD_ALLOWLIST parses comma-separated and space-separated IDs correctly
- [ ] BOT_ADMIN_IDS defaults to ExoArcher's ID if not set
- [ ] REFRESH_INTERVAL defaults to 90 if missing/blank
- [ ] feeds() returns dict of {"information": channel_name, "doodles": channel_name}
- [ ] is_guild_allowed() returns True for allowlisted guilds
- [ ] is_admin() returns True for admin IDs
- [ ] Config is truly frozen (cannot set attributes after creation)

## Special Requirements
- None

## Integration Notes
- This module is imported and used by bot.py (main), db.py, and other features
- Config is loaded exactly once at startup: `config = Config.load()`
- All env var lookups should go through this module, never directly via os.getenv()

## Reference Implementation
See Main-1.5.0/config.py for the complete original implementation.
