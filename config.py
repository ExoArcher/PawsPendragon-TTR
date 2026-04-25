"""Centralised config loaded from environment (.env).

The bot is multi-guild: it can serve as many Discord servers as you list
in ``GUILD_ALLOWLIST``. Channel/category names and the refresh interval
are global — the same defaults apply to every guild.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
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


@dataclass(frozen=True)
class Config:
    token: str
    # Guilds seeded into the runtime allowlist from .env. The bot also
    # tracks a *runtime* allowlist persisted in state.json that admins
    # mutate via /laq_guild_add and /laq_guild_remove. The effective
    # allowlist is the union of both.
    guild_allowlist: frozenset[int]
    # Discord user IDs that may invoke owner-only admin commands
    # (/laq_announce, /laq_guild_add, /laq_guild_remove). Empty == nobody.
    owner_ids: frozenset[int]
    refresh_interval: int
    user_agent: str
    category_name: str
    channel_information: str
    channel_doodles: str

    @classmethod
    def load(cls) -> "Config":
        return cls(
            token=_required("DISCORD_TOKEN"),
            guild_allowlist=_parse_id_list(
                os.getenv("GUILD_ALLOWLIST"), var_name="GUILD_ALLOWLIST"
            ),
            owner_ids=_parse_id_list(
                os.getenv("BOT_OWNER_IDS"), var_name="BOT_OWNER_IDS"
            ),
            refresh_interval=int(os.getenv("REFRESH_INTERVAL", "60")),
            user_agent=os.getenv(
                "USER_AGENT", "ttr-discord-bot (https://github.com/)"
            ),
            category_name=os.getenv("CHANNEL_CATEGORY", "Toontown Rewritten"),
            channel_information=os.getenv(
                "CHANNEL_INFORMATION", "tt-information"
            ),
            channel_doodles=os.getenv("CHANNEL_DOODLES", "tt-doodles"),
        )

    def feeds(self) -> dict[str, str]:
        """Mapping of feed key -> default channel name."""
        return {
            "information": self.channel_information,
            "doodles": self.channel_doodles,
        }

    def is_guild_allowed(self, guild_id: int) -> bool:
        """Static .env allowlist check. The bot combines this with the
        runtime allowlist in state.json before deciding to leave a guild."""
        return guild_id in self.guild_allowlist

    def is_owner(self, user_id: int) -> bool:
        return user_id in self.owner_ids
