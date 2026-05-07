"""Centralised config loaded from environment (.env).

The bot is multi-guild: it can serve as many Discord servers as you list
in ``GUILD_ALLOWLIST``. Channel/category names and the refresh interval
are global — the same defaults apply to every guild.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import os as _os_for_dotenv
from dotenv import load_dotenv

# Try loading from multiple locations (Cybrancee root, then PDMain, then current dir)
_dotenv_paths = [
    "/home/container/.env",
    "/home/container/PDMain/.env",
    ".env"
]
for _path in _dotenv_paths:
    if _os_for_dotenv.path.exists(_path):
        load_dotenv(dotenv_path=_path)
        _LIVE_ENV_PATH: str = _path
        break
else:
    # No .env found, still call load_dotenv to check environment variables
    load_dotenv()
    _LIVE_ENV_PATH = ".env"


def find_env_path() -> str:
    """Return the path to the live .env file used at startup."""
    return _LIVE_ENV_PATH


def update_env_var(name: str, value: str) -> str:
    """Rewrite *name=value* in the live .env file in place.

    Preserves all other lines and comments. If the key doesn't exist,
    appends it. Returns the path of the file that was written.
    """
    path = find_env_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []

    key_prefix = f"{name}="
    replaced = False
    new_lines = []
    for line in lines:
        if line.lstrip().startswith(key_prefix) or line.lstrip().startswith(f"#{key_prefix}"):
            # Replace (also un-comments if was commented out)
            new_lines.append(f"{name}={value}\n")
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        new_lines.append(f"{name}={value}\n")

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

    return path


def read_env_var(name: str) -> str:
    """Read the current raw value of *name* from the live .env file.

    Returns empty string if the key is absent or the file doesn't exist.
    """
    path = find_env_path()
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith(f"{name}="):
                    return stripped[len(name) + 1:]
    except FileNotFoundError:
        pass
    return ""


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
    # ── Custom emojis ──────────────────────────────────────────────────────────
    jellybean_emoji: str
    cog_emoji: str
    safe_emoji: str
    infinite_emoji: str
    pendragon_emoji: str
    purple_blue_circle_emoji: str
    purple_gld_diamond_emoji: str
    purple_r_diamond_emoji: str
    lav_emoji: str
    tu_emoji: str
    trap_emoji: str
    lure_emoji: str
    sound_emoji: str
    throw_emoji: str
    # ── Doodle star emojis ─────────────────────────────────────────────────────
    star_perfect: str
    star_amazing: str
    star_great: str
    star_good: str
    star_ok: str
    star_bad: str

    @classmethod
    def load(cls) -> "Config":
        """Load and validate all environment variables, returning a Config instance.

        Called once at startup. Required env vars:
        - DISCORD_TOKEN: Bot token from https://discord.com/developers/applications
        - GUILD_ALLOWLIST: Comma/space-separated Discord server IDs the bot can join
        - BOT_ADMIN_IDS: Comma/space-separated user IDs for console commands (optional, defaults to ExoArcher)

        Optional env vars with sensible defaults:
        - REFRESH_INTERVAL (default: 120) - seconds between live feed refreshes
        - USER_AGENT (default: "Paws Pendragon-DiscBot") - descriptive string for TTR API
        - CHANNEL_CATEGORY (default: "PendragonTTR") - category name for channels
        - CHANNEL_INFORMATION (default: "tt-info") - channel for live feeds
        - CHANNEL_DOODLES (default: "tt-doodles") - channel for doodle info
        - CHANNEL_SUIT_CALCULATOR (default: "suit-calc") - channel for suit calculator
        - BANNED_USER_IDS (optional) - user IDs to ban from bot
        - JELLYBEAN_EMOJI, COG_EMOJI, SAFE_EMOJI, INFINITE_EMOJI - general emojis
        - PENDRAGON_EMOJI, PurpleBlueCircle_EMOJI, PurpleGldDiamond_EMOJI, PurpleRDiamond_EMOJI - decoration emojis
        - LAV_Emoji, TU_EMOJI, TRAP_EMOJI, LURE_EMOJI, SOUND_EMOJI, THROW_EMOJI - gag track emojis
        - STAR_PERFECT, STAR_AMAZING, STAR_GREAT, STAR_GOOD, STAR_OK, STAR_BAD - doodle tier stars
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
            refresh_interval=_int_env("REFRESH_INTERVAL", default=120),
            user_agent=os.getenv(
                "USER_AGENT", "Paws Pendragon-DiscBot"
            ),
            category_name=os.getenv("CHANNEL_CATEGORY", "PendragonTTR"),
            channel_information=os.getenv(
                "CHANNEL_INFORMATION", "tt-info"
            ),
            channel_doodles=os.getenv("CHANNEL_DOODLES", "tt-doodles"),
            channel_suit_calculator=os.getenv(
                "CHANNEL_SUIT_CALCULATOR", "suit-calc"
            ),
            banned_user_ids=_parse_id_list(
                os.getenv("BANNED_USER_IDS"), var_name="BANNED_USER_IDS"
            ),
            # ── General emojis ────────────────────────────────────────────────
            jellybean_emoji=os.getenv("JELLYBEAN_EMOJI", "<:Jellybeans:1496983830106603551>"),
            cog_emoji=os.getenv("COG_EMOJI", "<:Cog:1496996533432877078>"),
            safe_emoji=os.getenv("SAFE_EMOJI", "<:Safe:1497311481711165625>"),
            infinite_emoji=os.getenv("INFINITE_EMOJI", "<:Infinite:1497383349046607882>"),
            pendragon_emoji=os.getenv("PENDRAGON_EMOJI", "<:Pendragon:1499923320613896282>"),
            purple_blue_circle_emoji=os.getenv("PurpleBlueCircle_EMOJI", "<:PurpleBlueCircle:1499922543396519956>"),
            purple_gld_diamond_emoji=os.getenv("PurpleGldDiamond_EMOJI", "<:PurpleGldDiamond:1499922496231571657>"),
            purple_r_diamond_emoji=os.getenv("PurpleRDiamond_EMOJI", "<:PurpleRDiamond:1499921992906706988>"),
            lav_emoji=os.getenv("LAV_Emoji", "<:Lav:1499503216084390019>"),
            tu_emoji=os.getenv("TU_EMOJI", "<:ToonUp:1499440893479092284>"),
            trap_emoji=os.getenv("TRAP_EMOJI", "<:Trap:1499440908884643942>"),
            lure_emoji=os.getenv("LURE_EMOJI", "<:Lure:1499440906170925066>"),
            sound_emoji=os.getenv("SOUND_EMOJI", "<:Sound:1499440907903176724>"),
            throw_emoji=os.getenv("THROW_EMOJI", "<:Throw:1499440890945474744>"),
            # ── Doodle star emojis ────────────────────────────────────────────
            star_perfect=os.getenv("STAR_PERFECT", "<:RBStar:1497375968619135076>"),
            star_amazing=os.getenv("STAR_AMAZING", "<:RBStar:1497375968619135076>"),
            star_great=os.getenv("STAR_GREAT", "<:GoldenStar:1497383695781462016>"),
            star_good=os.getenv("STAR_GOOD", "<:SilverStar:1497299363590967549>"),
            star_ok=os.getenv("STAR_OK", "<:BronzeStar:1497300707554889891>"),
            star_bad=os.getenv("STAR_BAD", "<:Trash:1497379832865226844>"),
        )

    def feeds(self) -> dict[str, str]:
        """Mapping of feed key -> default channel name.

        Returns:
            Dict mapping feed type to channel name:
            - "information": channel for live information feeds
            - "doodles": channel for doodle info

        Note: #suit-calc is NOT included here — it is static and
        updated only on startup and /pdrefresh, not on the refresh loop.
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
