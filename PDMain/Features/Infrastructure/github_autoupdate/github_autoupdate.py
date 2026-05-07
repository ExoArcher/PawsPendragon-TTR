# -*- coding: utf-8 -*-
"""GitHub auto-update module for Paws Pendragon Discord bot.

Ensures the bot runs the latest code from GitHub on every startup:
- Initializes .git repository if missing (clone from GitHub)
- Fetches latest main branch from GitHub
- Compares local HEAD vs origin/main via hash comparison
- Performs hard reset if behind (discards local changes)
- Restarts process via os.execv if update applied
- Prevents infinite restart loops via hash comparison
"""

import os
import subprocess
import sys


# Git configuration
REPO_URL: str = "https://github.com/exokarma/Paws-Pendragon.git"
BRANCH: str = "main"
REMOTE: str = "origin"


def auto_update_from_github() -> None:
    """Auto-update bot code from GitHub main branch on startup.

    Initializes .git repo if missing, fetches latest code, and restarts
    the process if an update is available. Hash comparison prevents infinite
    restart loops. Uses --ff-only to safely merge (does not hard reset).

    Respects AUTO_UPDATE env var (default "true"). If set to "false", skips
    all git operations.

    Startup flow:
    1. If no .git directory:
       - Initialize git repo
       - Add GitHub remote
       - Fetch main branch
       - Checkout and track main
       - Restart process via os.execv
    2. Else (repo already initialized):
       - Fetch latest main from origin
       - Get local HEAD hash
       - Get remote HEAD hash
       - If different: attempt --ff-only pull, print update, restart
       - If --ff-only fails (history diverged): warn and continue with existing code
       - Else: print up-to-date message, continue

    Raises:
        subprocess.CalledProcessError: If any git command fails (caught and handled)
        Exception: Any unhandled exception is caught and printed to stdout
    """
    # Check AUTO_UPDATE env var (default "true" for backwards compatibility)
    auto_update_enabled: bool = os.getenv("AUTO_UPDATE", "true").lower() in ("true", "1", "yes")

    if not auto_update_enabled:
        print("[auto-update] AUTO_UPDATE is disabled. Skipping git update.", flush=True)
        return

    try:
        bot_dir: str = os.path.dirname(os.path.abspath(__file__))
        git_dir: str = os.path.join(bot_dir, ".git")

        if not os.path.isdir(git_dir):
            # Initialize .git repo from GitHub
            print(
                "[auto-update] No .git found -- initialising repo from GitHub...",
                flush=True,
            )

            subprocess.run(
                ["git", "init"],
                cwd=bot_dir,
                check=True,
                capture_output=True,
            )

            subprocess.run(
                ["git", "remote", "add", "origin", REPO_URL],
                cwd=bot_dir,
                check=True,
                capture_output=True,
            )

            subprocess.run(
                ["git", "fetch", "origin", BRANCH],
                cwd=bot_dir,
                check=True,
                capture_output=True,
            )

            subprocess.run(
                ["git", "checkout", "-b", BRANCH, "--track", f"{REMOTE}/{BRANCH}"],
                cwd=bot_dir,
                check=True,
                capture_output=True,
            )

            print(
                "[auto-update] Repo initialised. Restarting with GitHub code...",
                flush=True,
            )
            os.execv(sys.executable, [sys.executable] + sys.argv)

        else:
            # Repo already initialized -- check for updates
            subprocess.run(
                ["git", "fetch", "origin", BRANCH],
                cwd=bot_dir,
                check=True,
                capture_output=True,
            )

            # Get local HEAD hash
            local_hash_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=bot_dir,
                capture_output=True,
                text=True,
            )
            local_hash: str = local_hash_result.stdout.strip()

            # Get remote HEAD hash
            remote_hash_result = subprocess.run(
                ["git", "rev-parse", f"{REMOTE}/{BRANCH}"],
                cwd=bot_dir,
                capture_output=True,
                text=True,
            )
            remote_hash: str = remote_hash_result.stdout.strip()

            # Compare hashes
            if local_hash != remote_hash:
                # Update available -- attempt fast-forward merge
                try:
                    subprocess.run(
                        ["git", "pull", "--ff-only", REMOTE, BRANCH],
                        cwd=bot_dir,
                        check=True,
                        capture_output=True,
                    )
                    print(
                        f"[auto-update] Updated {local_hash[:7]} -> {remote_hash[:7]}. Restarting...",
                        flush=True,
                    )
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                except subprocess.CalledProcessError:
                    # History diverged; cannot fast-forward
                    print(
                        f"[auto-update] WARNING: Cannot fast-forward ({local_hash[:7]} vs {remote_hash[:7]}). "
                        f"History may have diverged. Continuing with existing code.",
                        flush=True,
                    )

            else:
                # Already up to date
                print(
                    f"[auto-update] Already up to date ({local_hash[:7]}).",
                    flush=True,
                )

    except Exception as e:
        print(
            f"[auto-update] WARNING: git update failed ({e}). Running existing code.",
            flush=True,
        )


if __name__ == "__main__":
    # Allow direct invocation for testing
    auto_update_from_github()
