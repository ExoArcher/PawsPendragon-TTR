# -*- coding: utf-8 -*-
"""
formatters.py — Discord embed builders for LanceAQuack TTR.

Produces three embeds for #tt-information (districts, field offices, silly meter)
and one multi-embed set for #tt-doodles, all with dynamic "Updated X ago" timestamps
using Discord's native <t:unix:R> format so they refresh in the client automatically.

FORMATTERS maps feed_key -> callable(api_data) -> list[discord.Embed].

API data keys fed in from bot.py:
    invasions    - {"invasions": {district: {type, progress, asOf, mega}}, "asOf": int}
    population   - {"populationByDistrict": {district: int}, "totalPopulation": int, "asOf": int}
    fieldoffices - {"fieldOffices": {zone_id: {department, difficulty, annexesRemaining, open, asOf}},
                    "asOf": int}
    sillymeter   - {"winner": {...}, "teams": [...], "nextTeams": [...], "phase": str,
                    "currentTeam": {...} | null, "sillymeterPoints": int,
                    "maxSillyMeterPoints": int, "asOf": int}
    doodles      - {"doodles": [...], "asOf": int}
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any

import discord
from dotenv import load_dotenv

load_dotenv()

# ── Custom emoji IDs from .env (fall back to plain text if not set) ───────────
JELLYBEANS  = os.getenv("JELLYBEANS_EMOJI",   "🫙")
COG_EMOJI   = os.getenv("COG_EMOJI",          "⚙️")
SAFE_EMOJI  = os.getenv("SAFE_EMOJI",         "🛡️")
INFINITE    = os.getenv("INFINITE_EMOJI",     "♾️")

STAR_PERFECT = os.getenv("STAR_PERFECT", "⭐")
STAR_AMAZING = os.getenv("STAR_AMAZING", "⭐")
STAR_GREAT   = os.getenv("STAR_GREAT",   "🌟")
STAR_GOOD    = os.getenv("STAR_GOOD",    "✨")
STAR_OK      = os.getenv("STAR_OK",      "💫")
STAR_BAD     = os.getenv("STAR_BAD",     "🗑️")

# Districts immune to Mega Invasions
MEGA_SAFE_DISTRICTS = frozenset({
    "Blam Canyon", "Gulp Gulch", "Whoosh Rapids", "Zapwood", "Welcome Valley",
})

# Zone ID → readable street name for field offices
ZONE_NAMES: dict[str, str] = {
    "2100": "Toontown Central",  "2200": "Donald's Dock",
    "2300": "Daisy Gardens",     "2400": "Minnie's Melodyland",
    "2500": "The Brrrgh",        "2600": "Donald's Dreamland",
    "3100": "Chip 'n Dale's Acorn Acres",
    "9100": "Sellbot HQ",        "9200": "Cashbot HQ",
    "9300": "Lawbot HQ",         "9400": "Bossbot HQ",
    "22000": "Toontown Central", "22100": "Loopy Lane",
    "22200": "Punchline Place",  "22300": "Silly Street",
    "23000": "Donald's Dock",
    "24000": "Daisy Gardens",
    "25000": "Minnie's Melodyland",
    "26000": "The Brrrgh",
    "27000": "Donald's Dreamland",
}

DEPT_NAMES: dict[str, str] = {
    "s": "Sellbot", "c": "Cashbot", "l": "Lawbot", "b": "Bossbot",
    "m": "Sellbot",  # fallback
}
DEPT_COLORS: dict[str, int] = {
    "s": 0xE74C3C, "c": 0x27AE60, "l": 0x3498DB, "b": 0xF39C12,
}

# ── Silly Meter team descriptions ─────────────────────────────────────────────
SILLY_TEAM_DESC: dict[str, str] = {
    "The Silliest": "Toons are at peak silliness — everything is funnier than usual!",
    "United Toon Front": "All Toons unite under one banner for maximum toony power.",
    "Resistance Rangers": "The Resistance strikes back! Defenders of Toontown stand ready.",
    "Toon Troopers": "Toon Troopers march forward, gags at the ready.",
    "Bean Counters": "The Cogbucks are flowing — Cashbots beware of extra-savvy Toons.",
    "Daffy Dandies": "Extra flair and extra laughs — style is the weapon of choice.",
    "Nature Lovers": "Toons in harmony with Toontown's greenery. Flower power!",
    "Schemers":  "Toons with a plan. Watch out, Cogs — these Toons mean business.",
    "Tech Savvy": "Gadgets, gizmos, and gags — these Toons have all the tools.",
    "Jokemasters": "Puns, pratfalls, and punchlines — the funniest Toons in town.",
}

def _team_desc(name: str | None) -> str:
    if not name:
        return ""
    for key, desc in SILLY_TEAM_DESC.items():
        if key.lower() in (name or "").lower():
            return desc
    return ""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ts(unix: int | float | None) -> str:
    """Return a Discord relative timestamp string, or empty string if missing."""
    if not unix:
        return ""
    return f"<t:{int(unix)}:R>"


def _now_ts() -> str:
    """Current time as a Discord relative timestamp (used when asOf is absent)."""
    return f"<t:{int(time.time())}:R>"


def _updated_line(as_of: int | float | None) -> str:
    if as_of:
        return f"-# Updated {_ts(as_of)}"
    return f"-# Updated {_now_ts()}"


def _safe_get(data: dict | None, *keys: str, default: Any = None) -> Any:
    cur = data
    for k in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(k, default)
    return cur


# ══════════════════════════════════════════════════════════════════════════════
# Embed 1 — Districts & Invasions
# ══════════════════════════════════════════════════════════════════════════════

def format_information(
    invasions: dict | None = None,
    population: dict | None = None,
    fieldoffices: dict | None = None,
) -> discord.Embed:
    """Build the Districts & Invasions embed."""
    as_of   = _safe_get(population, "asOf") or _safe_get(invasions, "asOf")
    inv_map = _safe_get(invasions, "invasions") or {}
    pop_map = _safe_get(population, "populationByDistrict") or {}
    total   = _safe_get(population, "totalPopulation") or sum(pop_map.values()) or 0

    embed = discord.Embed(
        title="🌎  Districts & Invasions",
        color=0x4FC3F7,
    )

    if not pop_map and not inv_map:
        embed.description = "*No district data available right now.*"
        embed.set_footer(text=_updated_line(as_of))
        return embed

    # Sort districts: invaded first (mega first within that), then by pop desc
    all_districts = sorted(
        set(pop_map) | set(inv_map),
        key=lambda d: (
            d not in inv_map,
            not inv_map.get(d, {}).get("mega", False),
            -pop_map.get(d, 0),
        ),
    )

    invasion_lines: list[str] = []
    district_lines: list[str] = []

    for district in all_districts:
        pop   = pop_map.get(district, 0)
        inv   = inv_map.get(district)
        safe  = f" {SAFE_EMOJI}" if district in MEGA_SAFE_DISTRICTS else ""

        if inv:
            cog_type = inv.get("type", "Unknown")
            progress = inv.get("progress", "?/?")
            mega_tag = " 🚨 **MEGA**" if inv.get("mega") else ""
            invasion_lines.append(
                f"{COG_EMOJI} **{district}**{mega_tag} — {cog_type} `{progress}`"
            )
        else:
            district_lines.append(f"**{district}**{safe} `{pop:,}`")

    sections: list[str] = []

    if invasion_lines:
        sections.append("**⚠️ Active Invasions**\n" + "\n".join(invasion_lines))

    if district_lines:
        # Group into rows of 2 for compact layout
        pairs = []
        for i in range(0, len(district_lines), 2):
            row = district_lines[i]
            if i + 1 < len(district_lines):
                row += "  •  " + district_lines[i + 1]
            pairs.append(row)
        sections.append(
            f"**🏙️ Districts — {total:,} Toons Online**\n" + "\n".join(pairs)
        )

    embed.description = "\n\n".join(sections) or "*No data available.*"
    embed.set_footer(text=_updated_line(as_of))
    return embed


# ══════════════════════════════════════════════════════════════════════════════
# Embed 2 — Field Offices
# ══════════════════════════════════════════════════════════════════════════════

def format_fieldoffices(fieldoffices: dict | None = None) -> discord.Embed:
    """Build the Field Offices embed."""
    as_of   = _safe_get(fieldoffices, "asOf")
    fo_map  = _safe_get(fieldoffices, "fieldOffices") or {}

    embed = discord.Embed(
        title="🏢  Sellbot Field Offices",
        color=0xE74C3C,
    )

    if not fo_map:
        embed.description = "*No Field Offices are currently active.*"
        embed.set_footer(text=_updated_line(as_of))
        return embed

    lines: list[str] = []
    for zone_id, fo in fo_map.items():
        if not isinstance(fo, dict):
            continue
        location   = ZONE_NAMES.get(str(zone_id), f"Zone {zone_id}")
        difficulty = int(fo.get("difficulty", 1))
        stars      = "⭐" * difficulty
        annexes    = fo.get("annexesRemaining", "?")
        is_open    = fo.get("open", True)
        status     = "🟢 Open" if is_open else "🔴 Closed"

        annex_str = (
            f"{INFINITE} Kaboomberg" if str(annexes) == "-1"
            else f"{annexes} annexe{'s' if annexes != 1 else ''} remaining"
        )

        lines.append(
            f"**{location}** {stars}\n"
            f"  {status}  •  {annex_str}"
        )

    embed.description = "\n\n".join(lines) if lines else "*No Field Offices active.*"
    embed.set_footer(text=_updated_line(as_of))
    return embed


# ══════════════════════════════════════════════════════════════════════════════
# Embed 3 — Silly Meter
# ══════════════════════════════════════════════════════════════════════════════

def format_sillymeter(sillymeter: dict | None = None) -> discord.Embed:
    """
    Build the Silly Meter embed.

    Handles three phases:
      active      — meter is filling; show current team, points, progress bar.
      cooldown    — meter maxed out and is cooling down; show winner + upcoming teams.
      sneak-peek  — showing upcoming team lineup before next cycle.
    """
    if not sillymeter:
        embed = discord.Embed(
            title="🎭  Silly Meter",
            description="*Silly Meter data unavailable right now.*",
            color=0x9B59B6,
        )
        return embed

    as_of  = sillymeter.get("asOf")
    phase  = (sillymeter.get("phase") or "active").lower().replace("-", "_")
    # Normalise phase name
    if "sneak" in phase:
        phase = "sneak_peek"
    elif "cool" in phase:
        phase = "cooldown"
    else:
        phase = "active"

    points     = int(sillymeter.get("sillymeterPoints") or 0)
    max_points = int(sillymeter.get("maxSillyMeterPoints") or 1)

    # Current winning / active team
    current_team = sillymeter.get("currentTeam") or sillymeter.get("winner") or {}
    current_name = current_team.get("name") or current_team.get("teamName") or "Unknown"

    # Upcoming teams (shown in cooldown / sneak-peek)
    next_teams: list[dict] = sillymeter.get("nextTeams") or []
    if not next_teams:
        # Fallback: look for teams list and skip the current one
        all_teams: list[dict] = sillymeter.get("teams") or []
        next_teams = [t for t in all_teams if
                      (t.get("name") or t.get("teamName")) != current_name]

    embed = discord.Embed(color=0x9B59B6)

    # ── ACTIVE ───────────────────────────────────────────────────────────────
    if phase == "active":
        pct        = max(0, min(100, round(points / max_points * 100)))
        filled     = round(pct / 5)
        bar        = "█" * filled + "░" * (20 - filled)
        pts_left   = max(0, max_points - points)

        embed.title = "🎭  Silly Meter — Filling Up!"
        embed.description = (
            f"**{current_name}** is leading the charge!\n"
            f"{_team_desc(current_name)}\n\n"
            f"`{bar}` **{pct}%**\n"
            f"**{points:,}** / **{max_points:,}** Silly Points\n"
            f"**{pts_left:,}** points to go!"
        )

        if next_teams:
            sneak: list[str] = []
            for t in next_teams[:3]:
                tname = t.get("name") or t.get("teamName") or "?"
                desc  = _team_desc(tname)
                sneak.append(f"**{tname}**" + (f"\n*{desc}*" if desc else ""))
            embed.add_field(
                name="👀  Coming Up Next",
                value="\n\n".join(sneak),
                inline=False,
            )

    # ── COOLDOWN ─────────────────────────────────────────────────────────────
    elif phase == "cooldown":
        embed.title = "❄️  Silly Meter — Cooling Down"
        embed.description = (
            f"The Silly Meter hit **{max_points:,}** points and the whole town went absolutely "
            f"*bananas!* 🎉\n\n"
            f"The meter needs a moment to cool off from all that toontastic activity. "
            f"Once it settles down, a brand new set of Silly Teams will step up to keep "
            f"the laughs going.\n\n"
            f"**Last winner: {current_name}**\n"
            f"{_team_desc(current_name)}"
        )

        if next_teams:
            sneak: list[str] = []
            for t in next_teams[:3]:
                tname = t.get("name") or t.get("teamName") or "?"
                desc  = _team_desc(tname)
                sneak.append(f"**{tname}**" + (f"\n*{desc}*" if desc else ""))
            embed.add_field(
                name="🔜  Next Up — Sneak Peek",
                value="\n\n".join(sneak),
                inline=False,
            )

    # ── SNEAK PEEK ────────────────────────────────────────────────────────────
    else:
        embed.title = "👀  Silly Meter — Sneak Peek!"
        embed.description = (
            "The meter is getting ready for its next cycle. "
            "Here's a sneak peek at the teams lined up for the next round of silliness!"
        )

        if next_teams:
            sneak: list[str] = []
            for t in next_teams[:3]:
                tname = t.get("name") or t.get("teamName") or "?"
                desc  = _team_desc(tname)
                sneak.append(f"**{tname}**" + (f"\n*{desc}*" if desc else ""))
            embed.add_field(
                name="🎭  Upcoming Teams",
                value="\n\n".join(sneak),
                inline=False,
            )
        else:
            embed.description += "\n\n*No lineup announced yet — check back soon!*"

    embed.set_footer(text=_updated_line(as_of))
    return embed


# ══════════════════════════════════════════════════════════════════════════════
# Doodles
# ══════════════════════════════════════════════════════════════════════════════

# Trait value ordering (best → worst)
_TRAIT_RANK: dict[str, int] = {
    "Rarely Tired": 0,
    "Always Affectionate": 1, "Always Playful": 1,
    "Often Affectionate": 2, "Often Playful": 2,
    "Rarely Affectionate": 3, "Rarely Playful": 3,
    "Sometimes Affectionate": 4, "Sometimes Playful": 4,
    "Pretty Calm": 5, "Pretty Excitable": 5,
    "Often Tired": 8, "Always Tired": 9,
    "Often Bored": 8, "Always Bored": 9,
    "Often Cranky": 8, "Always Cranky": 9,
    "Often Lonely": 8, "Always Lonely": 9,
}

_STAR_MAP: list[tuple[int, str, str]] = [
    (0,  STAR_PERFECT, "Perfect"),
    (1,  STAR_AMAZING, "Amazing"),
    (3,  STAR_GREAT,   "Great"),
    (5,  STAR_GOOD,    "Good"),
    (7,  STAR_OK,      "OK"),
    (99, STAR_BAD,     "Skip"),
]

_PLAYGROUND_EMOJI: dict[str, str] = {
    "Toontown Central": "🌐", "Donald's Dock": "⚓",
    "Daisy Gardens": "🌼",    "Minnie's Melodyland": "🎵",
    "The Brrrgh": "❄️",       "Donald's Dreamland": "🌙",
}


def _score_traits(traits: list[str]) -> tuple[int, str, str]:
    if not traits:
        return 99, STAR_BAD, "Skip"
    total = sum(_TRAIT_RANK.get(t, 6) for t in traits)
    avg   = total / len(traits)
    # Perfect: Rarely Tired in slot 0
    if traits and traits[0] == "Rarely Tired":
        return 0, STAR_PERFECT, "Perfect"
    for threshold, star, label in _STAR_MAP:
        if avg <= threshold:
            return round(avg), star, label
    return 99, STAR_BAD, "Skip"


def format_doodles(doodles: dict | None = None) -> list[discord.Embed]:
    """Build the doodle listing embeds, one per playground."""
    as_of      = _safe_get(doodles, "asOf")
    doodle_list = _safe_get(doodles, "doodles") or []
    updated    = _updated_line(as_of)

    if not doodle_list:
        embed = discord.Embed(
            title="🐾  Doodles",
            description="*No doodles are currently for sale.*",
            color=0xFF6B6B,
        )
        embed.set_footer(text=updated)
        return [embed]

    # Group by playground
    by_pg: dict[str, list[dict]] = {}
    for doodle in doodle_list:
        pg = doodle.get("playground", "Unknown")
        by_pg.setdefault(pg, []).append(doodle)

    embeds: list[discord.Embed] = []

    for pg_name, pg_doodles in by_pg.items():
        emoji = _PLAYGROUND_EMOJI.get(pg_name, "🐾")
        embed = discord.Embed(
            title=f"{emoji}  {pg_name} — Doodles for Sale",
            color=0xFF6B6B,
        )
        lines: list[str] = []

        for d in pg_doodles:
            name   = d.get("name", "Unknown Doodle")
            traits = d.get("traits") or []
            price  = d.get("price")
            color  = d.get("color", "")

            score, star, label = _score_traits(traits)
            trait_str = "  •  ".join(traits) if traits else "No traits listed"
            price_str = f"{JELLYBEANS} {price:,}" if isinstance(price, int) else ""
            color_str = f"*{color}*  " if color else ""

            lines.append(
                f"{star} **{name}** `[{label}]`\n"
                f"  {color_str}{trait_str}\n"
                f"  {price_str}"
            )

        embed.description = "\n\n".join(lines) if lines else "*None available.*"
        embed.set_footer(text=updated)
        embeds.append(embed)

    if not embeds:
        embed = discord.Embed(
            title="🐾  Doodles",
            description="*No doodles are currently for sale.*",
            color=0xFF6B6B,
        )
        embed.set_footer(text=updated)
        return [embed]

    return embeds


# ══════════════════════════════════════════════════════════════════════════════
# Top-level formatter callables
# Called by bot.py _update_feed(guild_id, feed_key, api_data)
# Each returns list[discord.Embed]
# ══════════════════════════════════════════════════════════════════════════════

def _format_information_feed(api_data: dict) -> list[discord.Embed]:
    """
    Returns 3 embeds for #tt-information:
      [0] Districts & Invasions
      [1] Field Offices
      [2] Silly Meter
    """
    invasions    = api_data.get("invasions")
    population   = api_data.get("population")
    fieldoffices = api_data.get("fieldoffices")
    sillymeter   = api_data.get("sillymeter")

    return [
        format_information(invasions=invasions, population=population,
                           fieldoffices=fieldoffices),
        format_fieldoffices(fieldoffices=fieldoffices),
        format_sillymeter(sillymeter=sillymeter),
    ]


def _format_doodles_feed(api_data: dict) -> list[discord.Embed]:
    return format_doodles(api_data.get("doodles"))


# Maps feed_key -> callable(api_data) -> list[discord.Embed]
FORMATTERS: dict[str, Any] = {
    "information": _format_information_feed,
    "doodles":     _format_doodles_feed,
}
