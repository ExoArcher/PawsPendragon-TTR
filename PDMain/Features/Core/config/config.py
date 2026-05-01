"""Centralised config loaded from environment (.env).

The bot is multi-guild: it can serve as many Discord servers as you list
in ``GUILD_ALLOWLIST``. Channel/category names and the refresh interval
are global — the same defaults apply to every guild.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv(dotenv_path="/home/container/.env")


def _required(name: str) -> str:
    """Load a required environment variable, raising RuntimeError if missing."""
    val = os.getenv(name)
    if not val:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in."
        )
    return val


def _parse_id_list(raw: str | None, *, var_name: str = "GUILD_ALLOWLIST") -> frozenset[int]:
    """Parse a comma- or whitespace-separated list of Discord IDs."""
    if not raw:
        return frozenset()
    out: set[int] = set()
    for chunk in raw.replace(",", " ").split():
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            out.add(int(chunk))
        except ValueError:
            raise RuntimeError(
                f"{var_name} contains a non-numeric entry: {chunk!r}"
            )
    return frozenset(out)


def _int_env(name: str, default: int) -> int:
    """Read an int env var, falling back to *default* if missing or blank."""
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(
            f"Environment variable {name} must be an integer, got {raw!r}"
        )


@dataclass(frozen=True)
class Config:
    """Frozen configuration dataclass loaded once at startup.

    All environment variable access is centralized here. The config is
    immutable after creation; env var changes require a restart.
    """
    token: str
    # Guilds seeded into the runtime allowlist from .env. The effective
    # allowlist is the union of env + state.json.
    guild_allowlist: frozenset[int]
    # Discord user IDs that may use bot-admin commands.
    # Defaults to ExoArcher's ID if BOT_ADMIN_IDS is not set.
    admin_ids: frozenset[int]
    refresh_interval: int
    user_agent: str
    category_name: str
    channel_information: str
    channel_doodles: str
    channel_suit_calculator: str
    banned_user_ids: frozenset[int]
    quarantined_guild_ids: frozenset[int]

    @classmethod
    def load(cls) -> "Config":
        """Load and validate all environment variables, returning a Config instance.

        Called once at startup. Required env vars:
        - DISCORD_TOKEN: Bot token from https://discord.com/developers/applications
        - GUILD_ALLOWLIST: Comma/space-separated Discord server IDs the bot can join
        - BOT_ADMIN_IDS: Comma/space-separated user IDs for console commands (optional, defaults to ExoArcher)

        Optional env vars with sensible defaults:
        - REFRESH_INTERVAL (default: 90) - seconds between live feed refreshes
        - USER_AGENT (default: "ttr-discord-bot (https://github.com/)") - descriptive string for TTR API
        - CHANNEL_CATEGORY (default: "Toontown Rewritten") - category name for channels
        - CHANNEL_INFORMATION (default: "tt-information") - channel for live feeds
        - CHANNEL_DOODLES (default: "tt-doodles") - channel for doodle info
        - CHANNEL_SUIT_CALCULATOR (default: "suit-calculator") - channel for suit calculator
        - BANNED_USER_IDS (optional) - user IDs to ban from bot
        - QUARANTINED_GUILD_IDS (optional) - guilds to quarantine
        - JELLYBEAN_EMOJI (optional) - custom emoji ID for jellybeans
        - COG_EMOJI (optional) - custom emoji ID for cogs
        - STAR_* (optional) - custom emoji IDs for stars
        """
        return cls(
            token=_required("DISCORD_TOKEN"),
            guild_allowlist=_parse_id_list(
                os.getenv("GUILD_ALLOWLIST"), var_name="GUILD_ALLOWLIST"
            ),
            admin_ids=_parse_id_list(
                os.getenv("BOT_ADMIN_IDS") or "310233741354336257",
                var_name="BOT_ADMIN_IDS",
            ),
            refresh_interval=_int_env("REFRESH_INTERVAL", default=90),
            user_agent=os.getenv(
                "USER_AGENT", "ttr-discord-bot (https://github.com/)"
            ),
            category_name=os.getenv("CHANNEL_CATEGORY", "Toontown Rewritten"),
            channel_information=os.getenv(
                "CHANNEL_INFORMATION", "tt-information"
            ),
            channel_doodles=os.getenv("CHANNEL_DOODLES", "tt-doodles"),
            channel_suit_calculator=os.getenv(
                "CHANNEL_SUIT_CALCULATOR", "suit-calculator"
            ),
            banned_user_ids=_parse_id_list(
                os.getenv("BANNED_USER_IDS"), var_name="BANNED_USER_IDS"
            ),
            quarantined_guild_ids=_parse_id_list(
                os.getenv("QUARANTINED_GUILD_IDS"), var_name="QUARANTINED_GUILD_IDS"
            ),
        )

    def feeds(self) -> dict[str, str]:
        """Mapping of feed key -> default channel name.

        Returns:
            Dict mapping feed type to channel name:
            - "information": channel for live information feeds
            - "doodles": channel for doodle info

        Note: #suit-calculator is NOT included here — it is static and
        updated only on startup and /pd-refresh, not on the 90-second loop.
        """
        return {
            "information": self.channel_information,
            "doodles": self.channel_doodles,
        }

    def is_guild_allowed(self, guild_id: int) -> bool:
        """Check if a guild is in the static .env allowlist.

        Args:
            guild_id: Discord guild ID to check

        Returns:
            True if the guild is in GUILD_ALLOWLIST, False otherwise

        Note: The bot combines this with the runtime allowlist (from the database)
        before deciding whether to leave a guild.
        """
        return guild_id in self.guild_allowlist

    def is_admin(self, user_id: int) -> bool:
        """Check if a user is a bot admin (can run console commands).

        Args:
            user_id: Discord user ID to check

        Returns:
            True if the user is in BOT_ADMIN_IDS, False otherwise
        """
        return user_id in self.admin_ids
