# Core/ttr-api Feature Briefing

## Feature Purpose
Thin async HTTP client for the 5 public Toontown Rewritten API endpoints. Wraps aiohttp in a context manager for safe resource management.

## Scope
- Provide TTRApiClient async context manager for aiohttp session management
- Fetch data from 5 TTR public endpoints:
  1. **population** - district info and population counts
  2. **fieldoffices** - Sellbot, Cashbot, Lawbot, Bossbot field office status
  3. **doodles** - all available doodles with stats
  4. **sillymeter** - silly meter progress and laff boost status
  5. ~~**invasions**~~ - **DO NOT USE** (no building data available - user constraint)
- Handle User-Agent header for TTR API politeness
- Graceful error handling for API failures (e.g., 503 during maintenance)

## Code to Extract
**From Main-1.5.0/ttr_api.py (entire file, ~2800 lines)**
- TTRApiClient class with __aenter__, __aexit__ (async context manager)
- fetch(endpoint) method for each of the 5 endpoints
- Error handling and retry logic for transient failures

## TTR API Endpoints
```
GET https://www.toontownrewritten.com/api/invasions
GET https://www.toontownrewritten.com/api/population
GET https://www.toontownrewritten.com/api/fieldoffices
GET https://www.toontownrewritten.com/api/doodles
GET https://www.toontownrewritten.com/api/sillymeter
```

## Expected Response Format
- **population**: list of districts with {name, population, invasions_active}
- **fieldoffices**: dict of field offices with {Sellbot, Cashbot, Lawbot, Bossbot}
- **doodles**: list of doodle data with {name, traits, rarity}
- **sillymeter**: {teams: [{name, progress, laff_boost_active}], ...}
- **invasions**: {cogs_by_district: {...}} - **NOT USED**

## Dependencies
- Core/config (for USER_AGENT from config)
- aiohttp library (already in requirements.txt)

## Key Design Patterns
1. **Async context manager** - Use `async with TTRApiClient(user_agent) as client:`
2. **Single aiohttp session** - Reused across multiple fetch calls, cleaned up on exit
3. **No blocking calls** - Entirely async/await based
4. **Graceful degradation** - TTR API returns 503 during maintenance; bot retries automatically

## API Calls
- aiohttp.ClientSession.get() for each endpoint
- Proper User-Agent header setting

## Database Access
- None

## Tests to Verify
- [ ] TTRApiClient can be used as async context manager
- [ ] fetch("population") returns district data
- [ ] fetch("fieldoffices") returns field office data
- [ ] fetch("doodles") returns doodle data
- [ ] fetch("sillymeter") returns silly meter data
- [ ] TTR API 503 responses are handled gracefully (no crash)
- [ ] Session is properly closed on context exit
- [ ] User-Agent header is correctly set

## Special Requirements
- **CRITICAL**: Do NOT implement invasions endpoint fetching (user constraint: no building data available)
- User-Agent should be loaded from config

## Integration Notes
- Used by live-feeds feature to fetch data every 90 seconds
- Called via `async with TTRApiClient(config.user_agent) as client: data = await client.fetch("population")`
- Never call outside of async context manager (will leak connections)

## Reference Implementation
See Main-1.5.0/ttr_api.py for the complete original implementation.
