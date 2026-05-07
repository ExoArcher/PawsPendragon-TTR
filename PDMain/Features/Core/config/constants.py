"""Constants: centralized timing and threshold magic numbers.

This module consolidates all hard-coded constants used across feature modules
to enable single-point-of-change updates and improve testability.
"""

# ── REFRESH INTERVALS ────────────────────────────────────────────────────────

# Doodle embeds are throttled to once per 12 hours to prevent spam
DOODLE_REFRESH_INTERVAL_SECONDS = 12 * 60 * 60  # 43,200 seconds

# Message sweep loop interval (cleanup stale bot messages)
MESSAGE_SWEEP_INTERVAL_MINUTES = 15

# Cooldown for /pd-refresh command (regular users; admins bypass)
PD_REFRESH_COOLDOWN_SECONDS = 600  # 10 minutes

# ── TIMEOUT CONSTANTS ────────────────────────────────────────────────────────

# Timeout for fetching data from the TTR API
API_FETCH_TIMEOUT_SECONDS = 10.0

# Timeout for updating a single feed (per-guild operation)
PER_FEED_UPDATE_TIMEOUT_SECONDS = 30.0

# Delay between guild state updates to respect rate limits
GUILD_UPDATE_DELAY_SECONDS = 3.0

# ── RETENTION AND TTL CONSTANTS ──────────────────────────────────────────────

# Audit log entries are purged after this many days
AUDIT_LOG_RETENTION_DAYS = 90

# Announcement messages auto-delete after this duration
ANNOUNCEMENT_TTL_SECONDS = 30 * 60  # 30 minutes

# Rate limiting for announcements (optional, reserved for future use)
ANNOUNCE_MAX_PER_PERIOD = 1
ANNOUNCE_PERIOD_SECONDS = 300
