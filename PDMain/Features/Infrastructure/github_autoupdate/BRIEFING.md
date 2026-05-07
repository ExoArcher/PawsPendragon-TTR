# Infrastructure/github-autoupdate Feature Briefing

## Feature Purpose
On startup, compare local bot code to GitHub main branch. If behind, pull latest code and restart process. Enables zero-downtime deployment: push to GitHub, new instance auto-updates.

## Scope
- Compare local HEAD vs origin/main via git
- Initialize .git repo if missing (clone from GitHub)
- Fetch latest code and reset to remote
- Detect restart loops via hash comparison
- os.execv restart with Python subprocess
- Print status messages to stdout (hosting panels)

## Code to Extract
**From Main-1.5.0/bot.py**
- Lines 58-86: Auto-update startup logic
- Git repo initialization if .git missing
- Hash comparison for restart loop prevention
- git reset --hard origin/main
- os.execv process restart

## Startup Flow
```
On bot startup (before Discord login):
  If no .git directory:
    Initialize repo from GitHub
    Fetch main branch
    Checkout and track origin/main
    Restart with os.execv
  Else:
    Fetch origin/main
    Compare local HEAD vs origin/main (git rev-parse)
    If different:
      git reset --hard origin/main
      Print update message
      os.execv restart
    Else:
      Print "already up to date"
      Continue to Discord login
```

## Git Configuration
- Repository: `https://github.com/exokarma/Paws-Pendragon.git` (configurable)
- Branch: `main` (hardcoded)
- Remote: `origin` (hardcoded)
- Working directory: bot directory (where bot.py lives)

## Dependencies
- subprocess (stdlib, run git commands)
- os (stdlib, os.execv for restart)
- sys (stdlib, sys.argv and sys.executable)

## Key Design Patterns
1. **Hash comparison** - Prevents infinite restart loops
2. **Idempotent init** - Safe to run on every startup
3. **Hard reset** - Discards local changes (assumes production)
4. **os.execv** - True process restart (replaces current process)
5. **Stdout logging** - Print to stdout for hosting panel visibility

## API Calls
- subprocess.run() - Execute git commands
- subprocess.run(..., capture_output=True, text=True) - Get git output
- os.execv(executable, args) - Restart process
- os.path.isdir(".git") - Check for repo

## Database Access
- None (pure file operations)

## Tests to Verify
- [ ] Auto-update initializes .git if missing
- [ ] git fetch origin main succeeds
- [ ] Local and remote HEAD hashes are compared correctly
- [ ] If behind, git reset --hard origin/main executes
- [ ] os.execv restarts process with same args
- [ ] Restart loop prevented (hash comparison works)
- [ ] Already-up-to-date case prints correct message
- [ ] Git errors are handled (check=True raises on failure)

## Special Requirements
- Repository URL is hardcoded: "https://github.com/exokarma/Paws-Pendragon.git"
- Branch is hardcoded: "main"
- Local changes are DISCARDED (git reset --hard) - assumes production deployment
- Requires working git credentials (SSH key or PAT in .git/config)
- Prints to stdout (hosting panels capture this)

## Integration Notes
- Runs BEFORE bot.setup_hook() (earliest startup code)
- Must complete successfully before Discord login happens
- Restart via os.execv means bot process is completely replaced
- Next startup after restart will run auto-update again

## Error Handling
- subprocess.run(..., check=True) raises CalledProcessError on git failure
- If git commands fail, bot startup is blocked (intentional)
- Should be wrapped in try/except to log failures

## Git Commands Used
```bash
git init                              # Initialize repo
git remote add origin <URL>           # Add GitHub remote
git fetch origin main                 # Fetch latest main
git checkout -b main --track origin/main  # Track remote
git rev-parse HEAD                    # Get local HEAD hash
git rev-parse origin/main             # Get remote HEAD hash
git reset --hard origin/main          # Pull latest
```

## Reference Implementation
See Main-1.5.0/bot.py lines 58-86 for complete startup auto-update logic.
