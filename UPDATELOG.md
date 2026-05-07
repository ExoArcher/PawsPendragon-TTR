# Update Log — Paws Pendragon TTR Bot

## Session: 2026-05-07

### Codebase Documentation
**Commit: b63cf45**

Generated comprehensive codebase map via parallel analysis agents:
- `STACK.md` (102 lines) — Languages, frameworks, dependencies, configuration
- `INTEGRATIONS.md` (180 lines) — External APIs, databases, TTR integration points
- `ARCHITECTURE.md` (346 lines) — System design, patterns, data flow, feature organization
- `STRUCTURE.md` (313 lines) — Directory layout, module organization, entry points
- `CONVENTIONS.md` (243 lines) — Code style, naming patterns, error handling
- `TESTING.md` (419 lines) — Test framework, mocking patterns, coverage gaps
- `CONCERNS.md` (315 lines) — Technical debt, security considerations, scaling limits

**Total: 1918 lines of structured documentation**

Location: `.planning/codebase/`

### Bug Fixes

#### Fix: Invasion Display in /ttrinfo
**Commit: a067ea4**

**Problem:** `/ttrinfo` command wasn't fetching invasions endpoint. Hardcoded `invasions=None` prevented showing invasion status.

**Fix:**
- Added `bot._api.fetch("invasions")` to parallel fetch (line 72)
- Unpacked invasions result from asyncio.gather (line 79)
- Included invasions in API failure check (line 83)
- Passed actual invasions data to formatter instead of None (line 93)

**Impact:** `/ttrinfo` DM now displays `[Cog Name][xxx/xxx Cogs Defeated]` in districts list when invasion present.

#### Fix: Invasion Display in #tt-info Live Feed
**Commit: ad88481**

**Problem:** Live feed was intentionally skipping invasions (per line 83 comment). #tt-info embed never showed invasion status despite formatter supporting it.

**Fix:**
- Added `bot._api.fetch("invasions")` to parallel fetch in `_fetch_all()` (line 94)
- Updated return dict to include invasions key (line 103)
- Updated docstring to reflect 5 endpoints instead of 4

**Impact:** #tt-info channel now displays invasion status matching /ttrinfo format.

### Deployment Infrastructure

#### SFTP Deployment Scripts
**Commits: c648679, f89a6a8**

Created two deployment scripts for syncing bot code to Cybrancee server:

**Bash Script: `deploy.sh`**
- Uses `lftp` for SFTP
- Target: `/home/container/PDMain/`
- Auto-confirms prompts, mirrors with delete
- Best for: Linux/Mac systems

**Python Script: `deploy.py`**
- Uses `paramiko` library (installed)
- Target: `/home/container/PDMain/`
- Shows upload progress per file
- Best for: Windows systems

**Usage:**
```bash
# Windows
python deploy.py

# Linux/Mac
bash deploy.sh
```

**Credentials:**
- Host: `cybrancee-bot-na-west-23.cybrancee.com:2022`
- User: `ilkmjqd5.6265dfe8`
- Password: embedded in scripts (manual deploy only, not in CI/CD)

### Summary

| Category | Count | Details |
|----------|-------|---------|
| Codebase docs | 7 | 1918 lines total |
| Bug fixes | 2 | invasion display (/ttrinfo + live feed) |
| Deployment scripts | 2 | bash + python |
| Commits | 5 | b63cf45, a067ea4, ad88481, c648679, f89a6a8 |

**Branch:** mainbranch  
**Remote:** https://github.com/ExoArcher/PawsPendragon-TTR
