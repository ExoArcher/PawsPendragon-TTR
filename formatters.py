"""Turn raw TTR API JSON into Discord embeds.

Each formatter returns a ``discord.Embed`` (or a list of embeds when one
message would overflow). Discord caps embeds at 6000 chars total and each
field value at 1024, so the formatters keep things conservative.

Sections
--------
  Doodle trait system    -- tier constants, trait_tier(), priority/quality helpers
  Display constants      -- emoji IDs, district sets, star emoji mapping
  Shared helpers         -- _ts(), _footer(), _error(), district normalisation
  Zone / department data -- ZONE_NAMES, DEPARTMENTS, TTR_COLOR
  format_invasions       -- active cog invasion embed
  format_population      -- district population embed
  format_field_offices   -- active field office embed
  format_doodles         -- guide embed + 3 data embeds (sorted by tier)
  format_information     -- combined district + field office embed
  format_sillymeter      -- Silly Meter status embed
  FORMATTERS             -- public mapping used by the bot's refresh loop
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import discord

# ── DOODLE TRAIT SYSTEM ───────────────────────────────────────────────────────
#
# Each trait maps to one tier. The tier determines which star emoji appears
# in that trait's slot, and (alongside slot position for "Rarely Tired")
# which embed the doodle ends up in.
#
# Tiers, best → worst:
#   perfect : "Rarely Tired" in slot 0 (max trick-uses before tiring)
#   amazing : "Rarely Tired" in any other slot
#   great   : the 10 "Always Affectionate/Playful" + "Rarely X" traits
#   good    : Often Affectionate/Playful, Pretty Calm/Excitable
#   ok      : Rarely Affectionate/Playful, all Sometimes traits
#   bad     : Always/Often negative traits

GREAT_TRAITS: set[str] = {
    "Always Affectionate",
    "Always Playful",
    "Rarely Bored",
    "Rarely Confused",
    "Rarely Forgets",
    "Rarely Grumpy",
    "Rarely Hungry",
    "Rarely Lonely",
    "Rarely Restless",
    "Rarely Sad",
}

GOOD_TRAITS: set[str] = {
    "Often Affectionate",
    "Often Playful",
    "Pretty Calm",
    "Pretty Excitable",
}

OK_TRAITS: set[str] = {
    "Rarely Affectionate",
    "Rarely Playful",
    "Sometimes Bored",
    "Sometimes Confused",
    "Sometimes Forgets",
    "Sometimes Grumpy",
    "Sometimes Hungry",
    "Sometimes Lonely",
    "Sometimes Restless",
    "Sometimes Sad",
    "Sometimes Tired",
    # Treated as OK (neutral) for now; move to GOOD_TRAITS to rate them higher.
    "Sometimes Affectionate",
    "Sometimes Playful",
}

BAD_TRAITS: set[str] = {
    "Always Bored",
    "Always Confused",
    "Always Forgets",
    "Always Grumpy",
    "Always Hungry",
    "Always Lonely",
    "Always Restless",
    "Always Sad",
    "Always Tired",
    "Often Bored",
    "Often Confused",
    "Often Forgets",
    "Often Grumpy",
    "Often Hungry",
    "Often Lonely",
    "Often Restless",
    "Often Sad",
    "Often Tired",
}


def trait_tier(trait: str, slot: int) -> str:
    """Tier for a trait at a given slot (0..3).

    Returns one of: 'perfect', 'amazing', 'great', 'good', 'ok', 'bad'.
    Unlisted traits fall back to 'ok' rather than 'bad' — safer if TTR
    ever adds a new trait we haven't mapped. Only 'Rarely Tired' cares
    about slot.
    """
    if trait == "Rarely Tired":
        return "perfect" if slot == 0 else "amazing"
    if trait in GREAT_TRAITS:
        return "great"
    if trait in GOOD_TRAITS:
        return "good"
    if trait in OK_TRAITS:
        return "ok"
    if trait in BAD_TRAITS:
        return "bad"
    return "ok"


# Priority class — lower is better. Determines the order doodles flow
# into the embeds below.
#
#   0 PERFECT       : Rainbow in slot 0 + exactly 3 Gold (Great) in slots 1-3.
#   1 AMAZING       : one Crystal (Rarely Tired NOT in slot 0) + 3 Gold.
#   2 GREAT         : 4 Gold (Great) traits, no Rarely Tired.
#   3 GREAT_GOOD    : every trait is Rarely Tired / Great / Good (mixed).
#   4 GREAT_GOOD_OK : every trait is Rarely Tired / Great / Good / OK (mixed).
#   5 REST          : at least one Bad trait, or fewer than 4 traits.

PRIORITY_PERFECT    = 0
PRIORITY_AMAZING    = 1
PRIORITY_GREAT      = 2
PRIORITY_GREAT_GOOD = 3
PRIORITY_GREAT_GOOD_OK = 4
PRIORITY_REST       = 5

# Back-compat alias so callers that imported the old name keep working.
PRIORITY_ALL_GOLD = PRIORITY_GREAT

# Per-tier weight used as a quality tiebreaker within a priority bucket
# (higher = better). Two doodles in the same bucket can still differ —
# e.g. 3 Great + 1 Good beats 2 Great + 2 Good inside GREAT_GOOD — and
# this weight restores that ordering so higher-scoring doodles always
# print above lower-scoring ones.
_TIER_WEIGHT = {
    "perfect": 5,
    "amazing": 4,
    "great":   3,
    "good":    2,
    "ok":      1,
    "bad":     0,
}


def doodle_priority(traits: list[str]) -> int:
    """Classify a doodle into the six priority buckets.

    Strict thresholds (anything outside these is REST and not shown):
      Perfect : Rarely Tired in slot 0  +  3 Great
      Amazing : 1 Rarely Tired (any slot) + 3 Great
      Great   : 4 Great  (no Rarely Tired)
      Good    : 3 Great  + 1 Good
      OK      : 2 Great  + 2 Good
      Rest    : everything else (any bad trait, any OK trait, etc.)
    """
    traits = traits or []
    if len(traits) != 4:
        return PRIORITY_REST

    tiers = tuple(trait_tier(t, i) for i, t in enumerate(traits))

    # Any bad trait → REST immediately.
    if "bad" in tiers:
        return PRIORITY_REST

    n_perfect = tiers.count("perfect")   # Rarely Tired in slot 0
    n_amazing  = tiers.count("amazing")  # Rarely Tired in slots 1-3
    n_great    = tiers.count("great")
    n_good     = tiers.count("good")
    n_ok       = tiers.count("ok")
    n_rt       = n_perfect + n_amazing   # total Rarely Tired count

    # Any OK trait → lowest displayed tier (embed 3).
    if n_ok:
        return PRIORITY_GREAT_GOOD_OK

    # Perfect: EXACTLY Rarely Tired in slot 0 + 3 Great.
    if tiers == ("perfect", "great", "great", "great"):
        return PRIORITY_PERFECT

    # Amazing: exactly 1 Rarely Tired (any slot) + exactly 3 Great.
    if n_rt == 1 and n_great == 3 and n_good == 0:
        return PRIORITY_AMAZING

    # Great: exactly 4 Great, no Rarely Tired.
    if n_great == 4 and n_rt == 0 and n_good == 0:
        return PRIORITY_GREAT

    # Good: exactly 3 Great + 1 Good, no Rarely Tired.
    if n_great == 3 and n_good == 1 and n_rt == 0:
        return PRIORITY_GREAT_GOOD

    # OK: exactly 2 Great + 2 Good, no Rarely Tired.
    if n_great == 2 and n_good == 2 and n_rt == 0:
        return PRIORITY_GREAT_GOOD_OK

    # Everything else: REST — not shown.
    return PRIORITY_REST


def doodle_quality(traits: list[str]) -> int:
    """Sum of per-slot tier weights — higher is better.

    Used as a tiebreaker inside a priority bucket so e.g. a
    3-Gold + 1-Half doodle prints above a 2-Gold + 2-Half one.
    """
    traits = traits or []
    return sum(
        _TIER_WEIGHT[trait_tier(t, i)] for i, t in enumerate(traits)
    )


# ── DISPLAY CONSTANTS ─────────────────────────────────────────────────────────

# Custom jellybean emoji shown next to doodle costs.
JELLYBEAN_EMOJI = os.getenv("JELLYBEAN_EMOJI", "<:Jellybeans:1496983830106603551>")

# Shown next to districts with an active cog invasion.
COG_EMOJI = os.getenv("COG_EMOJI", "<:Cog:1496996533432877078>")

# Shown next to districts immune to Mega Invasions.
SAFE_EMOJI = os.getenv("SAFE_EMOJI", "<:Safe:1497311481711165625>")

# Districts immune to Mega Invasions. Compared against a normalised
# (lowercased, space-stripped) district name so minor spelling / casing
# variations don't break matching.
SAFE_FROM_MEGA_INVASIONS: set[str] = {
    "blamcanyon",
    "gulpgulch",
    "whooshrapids",
    "wooshrapids",  # common misspelling
    "zapwood",
    "welcomevalley",
}

# Districts where only pre-set SpeedChat phrases are available — Toons
# cannot type custom messages (no SpeedChat+ either).
SPEEDCHAT_ONLY_DISTRICTS: set[str] = {
    "boingbury",
    "gulpgulch",
    "whooshrapids",
    "wooshrapids",
}

# Tier-named star emojis used in the doodle rating column, one per
# trait slot. Defaults assume the bot has the matching custom emojis
# in a server it's a member of.
STAR_PERFECT = os.getenv("STAR_PERFECT", "<:RBStar:1497375968619135076>")
STAR_AMAZING = os.getenv("STAR_AMAZING", "<:RBStar:1497375968619135076>")
STAR_GREAT   = os.getenv("STAR_GREAT",   "<:GoldenStar:1497383695781462016>")
STAR_GOOD    = os.getenv("STAR_GOOD",    "<:SilverStar:1497299363590967549>")
STAR_OK      = os.getenv("STAR_OK",      "<:BronzeStar:1497300707554889891>")
STAR_BAD     = os.getenv("STAR_BAD",     "<:Trash:1497379832865226844>")

# Used for Kaboomberg's "Annexes Remaining" placeholder and anywhere else
# we want to render an infinity glyph. Override in .env for a custom emoji.
INFINITE_EMOJI = os.getenv("INFINITE_EMOJI", "♾️")

_TIER_STARS = {
    "perfect": STAR_PERFECT,
    "amazing": STAR_AMAZING,
    "great":   STAR_GREAT,
    "good":    STAR_GOOD,
    "ok":      STAR_OK,
    "bad":     STAR_BAD,
}

# Friendly tier label printed as the leading bracket box on each doodle
# row and used in the guide.
PRIORITY_LABELS: dict[int, str] = {
    PRIORITY_PERFECT:       "Perfect",
    PRIORITY_AMAZING:       "Amazing",
    PRIORITY_GREAT:         "Great",
    PRIORITY_GREAT_GOOD:    "Good",
    PRIORITY_GREAT_GOOD_OK: "OK",
    PRIORITY_REST:          "Bad",
}


def star_for(trait: str, slot: int) -> str:
    return _TIER_STARS[trait_tier(trait, slot)]


# ── SHARED HELPERS ────────────────────────────────────────────────────────────

def _norm_district(name: str) -> str:
    """Normalize a district name for set-membership checks."""
    return (name or "").lower().replace(" ", "").replace("'", "")


def _is_safe_district(name: str) -> bool:
    return _norm_district(name) in SAFE_FROM_MEGA_INVASIONS


def _is_speedchat_only(name: str) -> bool:
    return _norm_district(name) in SPEEDCHAT_ONLY_DISTRICTS


def _ts(epoch: int | float | None) -> str:
    if not epoch:
        return "unknown"
    # Discord relative timestamp, e.g. "12 seconds ago"
    return f"<t:{int(epoch)}:R>"


def _footer(embed: discord.Embed, last_updated: int | float | None) -> None:
    ts    = datetime.now(timezone.utc)
    extra = f" • TTR last refreshed {_ts(last_updated)}" if last_updated else ""
    embed.set_footer(text=f"Updated {ts.strftime('%Y-%m-%d %H:%M UTC')}" + extra)


def _error(title: str, message: str) -> discord.Embed:
    e = discord.Embed(
        title=title,
        description=f":warning: {message}",
        color=0xE74C3C,
    )
    _footer(e, None)
    return e


# ── ZONE / DEPARTMENT DATA ────────────────────────────────────────────────────

# Zone ID → street name, from the Field Offices API docs.
ZONE_NAMES: dict[int, str] = {
    3100: "Walrus Way",
    3200: "Sleet Street",
    3300: "Polar Place",
    4100: "Alto Avenue",
    4200: "Baritone Boulevard",
    4300: "Tenor Terrace",
    5100: "Elm Street",
    5200: "Maple Street",
    5300: "Oak Street",
    9100: "Lullaby Lane",
    9200: "Pajama Place",
}

# Department letter → name.
DEPARTMENTS = {
    "s": "Sellbot",
    "c": "Cashbot",
    "l": "Lawbot",
    "b": "Bossbot",
    "m": "Cashbot",  # some docs use 'm' for Cashbot historically
}

TTR_COLOR = 0x26A2EC  # TTR-ish blue


# ── FORMAT_INVASIONS ──────────────────────────────────────────────────────────

def format_invasions(data: dict[str, Any] | None) -> discord.Embed:
    if not data:
        return _error("Invasions", "Could not reach the TTR Invasions API.")
    if data.get("error"):
        return _error("Invasions", str(data["error"]))

    invasions = data.get("invasions", {}) or {}
    embed = discord.Embed(
        title=":rotating_light: Current Cog Invasions",
        color=TTR_COLOR,
    )

    if not invasions:
        embed.description = "No active invasions right now. :tada:"
    else:
        # Sort by district name for stable ordering.
        lines = []
        for district, inv in sorted(invasions.items()):
            cog      = inv.get("type", "Unknown")
            progress = inv.get("progress", "?/?")
            as_of    = inv.get("asOf")
            lines.append(
                f"**{district}** — {cog}  `{progress}`  ({_ts(as_of)})"
            )
        # Discord description cap is 4096. Trim defensively.
        embed.description = "\n".join(lines)[:4000]

    _footer(embed, data.get("lastUpdated"))
    return embed


# ── FORMAT_POPULATION ─────────────────────────────────────────────────────────

def format_population(data: dict[str, Any] | None) -> discord.Embed:
    if not data:
        return _error("Population", "Could not reach the TTR Population API.")
    if data.get("error"):
        return _error("Population", str(data["error"]))

    total  = data.get("totalPopulation", 0)
    pop_by = data.get("populationByDistrict", {}) or {}
    status_by = data.get("statusByDistrict", {}) or {}

    embed = discord.Embed(
        title=":busts_in_silhouette: Toontown Population",
        description=f"**Total Toons online:** {total:,}",
        color=TTR_COLOR,
    )

    status_icon = {
        "online":   ":green_circle:",
        "offline":  ":black_circle:",
        "draining": ":yellow_circle:",
        "closed":   ":red_circle:",
    }

    # Sorted alphabetically by district name.
    rows  = sorted(pop_by.items(), key=lambda kv: kv[0].lower())
    lines = []
    for district, pop in rows:
        status = status_by.get(district, "unknown")
        icon   = status_icon.get(status, ":white_circle:")
        lines.append(f"{icon} **{district}** — {pop:,} toons ({status})")

    if lines:
        embed.add_field(
            name="Districts",
            value="\n".join(lines)[:1024],
            inline=False,
        )

    _footer(embed, data.get("lastUpdated"))
    return embed


# ── FORMAT_FIELD_OFFICES ──────────────────────────────────────────────────────

def format_field_offices(data: dict[str, Any] | None) -> discord.Embed:
    if not data:
        return _error("Field Offices", "Could not reach the TTR Field Offices API.")

    offices = data.get("fieldOffices", {}) or {}
    embed   = discord.Embed(
        title=":office: Active Field Offices",
        color=TTR_COLOR,
    )

    if not offices:
        embed.description = "No Field Offices are currently active."
    else:
        def _sort_key(item: tuple[str, dict]) -> tuple[int, int]:
            zone_str, fo = item
            try:
                zone_id = int(zone_str)
            except (TypeError, ValueError):
                zone_id = 0
            return (-int(fo.get("difficulty", 0)), zone_id)

        lines = []
        for zone_str, fo in sorted(offices.items(), key=_sort_key):
            try:
                zone_id = int(zone_str)
            except (TypeError, ValueError):
                zone_id = 0
            street     = ZONE_NAMES.get(zone_id, f"Zone {zone_str}")
            dept       = DEPARTMENTS.get((fo.get("department") or "").lower(), "?")
            difficulty = int(fo.get("difficulty", 0)) + 1  # zero-indexed
            stars      = ":star:" * difficulty
            annexes    = fo.get("annexes", "?")
            open_state = ":unlock:" if fo.get("open") else ":lock:"
            expiring   = fo.get("expiring")
            expiring_str = f" • closing {_ts(expiring)}" if expiring else ""
            lines.append(
                f"{open_state} **{street}** — {dept} {stars}  "
                f"(annexes left: {annexes}){expiring_str}"
            )
        embed.description = "\n".join(lines)[:4000]

    _footer(embed, data.get("lastUpdated"))
    return embed


# ── FORMAT_DOODLES ────────────────────────────────────────────────────────────

def _b(text: str) -> str:
    """Bold: wraps content in **…**."""
    return f"**{text}**"


def _bi(text: str) -> str:
    """Bold + italic, using the **_X_** form to dodge the ***…*** boundary-
    ambiguity that Discord sometimes mis-parses when two adjacent bracket
    groups butt up against each other."""
    return f"**_{text}_**"


def _doodle_line(
    district: str, playground: str, traits: list[str], cost: Any
) -> str:
    """Render one doodle row:

    **[Tier]** **[<stars>]** **_[trait, ...]_** **[District · Playground jb cost jb]**

    Each bracket group is individually bolded (so the brackets themselves
    render heavy); the trait list is bold + italic. A real space separator
    goes between bracket groups so Discord's markdown parser doesn't choke.
    """
    traits       = traits or []
    label        = PRIORITY_LABELS[doodle_priority(traits)]
    location_box = (
        f"[{district} · {playground} "
        f"{JELLYBEAN_EMOJI} {cost} {JELLYBEAN_EMOJI}]"
    )
    if traits:
        stars      = "".join(star_for(t, i) for i, t in enumerate(traits[:4]))
        trait_str  = ", ".join(traits)
        return (
            f"{_b(f'[{label}]')} "
            f"{_b(f'[{stars}]')} "
            f"{_bi(f'[{trait_str}]')} "
            f"{_b(location_box)}"
        )
    return (
        f"{_b(f'[{label}]')} "
        f"{_bi('[traits not listed]')} "
        f"{_b(location_box)}"
    )


def _doodle_guide_embed() -> discord.Embed:
    """Embed #1: explanation of the star-rating system."""
    embed = discord.Embed(title=":dog: Doodle Trait Guide", color=TTR_COLOR)

    legend = "\n\n".join([
        (
            f"{STAR_PERFECT} {_b('[Rarely Tired]')} -- "
            "***Rarely Tired in the first slot offers the strongest "
            "benefit and is noted on Perfect Doodles. When Rarely Tired "
            "is in any other slot it still offers amazing benefit, keeping "
            "your doodle from tiring in battle and giving more trick uses "
            "before it gets tired.***"
        ),
        (
            f"{STAR_GREAT} {_b('[Great]')} -- "
            "***Talents that offer strong positive benefits to your doodle, "
            "but not as strong as Rarely Tired.***\n​\n"
            "*Always Affectionate, Always Playful, Rarely Bored, "
            "Rarely Confused, Rarely Forgets, Rarely Grumpy, "
            "Rarely Hungry, Rarely Lonely, Rarely Restless, Rarely Sad*"
        ),
        (
            f"{STAR_GOOD} {_b('[Good]')} -- "
            "***Decent talents that just aren't as strong as Great.***\n​\n"
            "*Often Affectionate, Often Playful, Pretty Calm, Pretty Excitable*"
        ),
        (
            f"{STAR_OK} {_b('[OK]')} -- "
            "***Not good talents, but could be worse.***\n​\n"
            "*Rarely Affectionate, Rarely Playful, Sometimes Affectionate, "
            "Sometimes Bored, Sometimes Confused, Sometimes Forgets, "
            "Sometimes Grumpy, Sometimes Hungry, Sometimes Lonely, "
            "Sometimes Playful, Sometimes Restless, Sometimes Sad, "
            "Sometimes Tired*"
        ),
        (
            f"{STAR_BAD} {_b('[Bad]')} -- "
            "***These are just bad traits for a doodle to have.***\n​\n"
            "*Always Bored, Always Confused, Always Forgets, Always Grumpy, "
            "Always Hungry, Always Lonely, Always Restless, Always Sad, "
            "Always Tired, Often Bored, Often Confused, Often Forgets, "
            "Often Grumpy, Often Hungry, Often Lonely, Often Restless, "
            "Often Sad, Often Tired*"
        ),
    ])

    tiering = "\n\n".join([
        _b("Tiering List"),
        (
            f"{_b('[Perfect]')} "
            "*Rarely Tired (first slot), Great Talent, Great Talent, Great Talent*"
        ),
        (
            f"{_b('[Amazing]')} "
            "*Great Talent, Great Talent, Great Talent, Rarely Tired "
            "(any combination with 3 Great Talents + Rarely Tired)*"
        ),
        (
            f"{_b('[Great]')} "
            "*Great Talent, Great Talent, Great Talent, Great Talent "
            "(4 Great Talents — no Rarely Tired)*"
        ),
        (
            f"{_b('[Good]')} "
            "*Great Talent, Great Talent, Great Talent, Good Talent "
            "(3 Great + 1 Good)*"
        ),
        (
            f"{_b('[OK]')} "
            "*Great Talent, Great Talent, Good Talent, Good Talent "
            "(2 Great + 2 Good)*"
        ),
        (
            f"{_b('[Bad]')} "
            "*Any doodle with fewer than 2 Great Talents, any doodle "
            "containing Bad or OK Talents, or any doodle below the OK "
            "threshold — **Bad doodles are not listed.**"
            "*"
        ),
    ])

    embed.description = legend + "\n\n" + tiering
    return embed


_DATA_EMBED_TITLES = (
    ":dog: Best Doodles",
    ":dog: Great Doodles",
    ":dog: Good Doodles",
)

_EMPTY_DATA_MSGS = (
    "*No qualifying doodles right now. Check the next embed!*",
    "*Everything fit above — nothing more to show here.*",
    "*All remaining doodles fit above.*",
)


def format_doodles(data: dict[str, Any] | None) -> list[discord.Embed]:
    """Return 1 guide embed + 3 data embeds for the #ttr-doodles channel.

    Doodles are sorted by strict priority:

        PERFECT        ({rainbow} + 3{gold})     →
        AMAZING        ({crystal} + 3{gold})     →
        GREAT          (4{gold})                 →
        GREAT_GOOD     ({gold}/{half} mix)       →
        GREAT_GOOD_OK  (+{silver} mix)           →
        REST           (any {bronze} / anything else)

    Within a priority bucket, higher total trait-quality prints first.
    District / playground name is the final alphabetical tiebreaker.

    Then **flow-fill** across three data embeds: each doodle goes in the
    highest-numbered embed that still has room in its description. We never
    start a lower-priority doodle until every higher-priority doodle has been
    placed. If the third embed fills and doodles remain, a ToonHQ link is
    appended.
    """
    guide = _doodle_guide_embed()

    if data is None:
        err = _error("Doodles", "Could not reach the TTR Doodles API.")
        return [guide, err]

    # Flatten the nested structure.
    rows: list[tuple[str, str, list[str], Any]] = []
    for district, playgrounds in (data or {}).items():
        if not isinstance(playgrounds, dict):
            continue
        for playground, doodles in playgrounds.items():
            if not isinstance(doodles, list):
                continue
            for d in doodles:
                traits = d.get("traits") or []
                rows.append((district, playground, traits, d.get("cost", "?")))

    # Drop REST-tier doodles — only show Perfect through OK.
    rows = [r for r in rows if doodle_priority(r[2]) != PRIORITY_REST]

    # Strict priority sort, then higher-quality first, then alphabetical.
    rows.sort(key=lambda r: (
        doodle_priority(r[2]),
        -doodle_quality(r[2]),
        r[0].lower(),
        r[1].lower(),
    ))

    # Flow-fill three embed descriptions. Discord description cap = 4096;
    # MAX_DESC leaves a small safety margin.
    MAX_DESC = 4050
    embed_lines: list[list[str]] = [[], [], []]
    embed_used  = [0, 0, 0]
    cur      = 0
    leftover = 0

    for idx, (district, playground, traits, cost) in enumerate(rows):
        line = _doodle_line(district, playground, traits, cost)
        # First line in an embed doesn't need the leading blank line;
        # subsequent ones in the same embed pay for one.
        line_len = len(line) + (2 if embed_lines[cur] else 0)
        # Walk forward until we find an embed with room for this line.
        while cur < 3 and embed_used[cur] + line_len > MAX_DESC:
            cur += 1
            line_len = len(line) + (2 if cur < 3 and embed_lines[cur] else 0)
        if cur >= 3:
            leftover = len(rows) - idx
            break
        embed_lines[cur].append(line)
        embed_used[cur] += line_len

    result = [guide]
    for i in range(3):
        e = discord.Embed(title=_DATA_EMBED_TITLES[i], color=TTR_COLOR)
        if embed_lines[i]:
            e.description = "\n\n".join(embed_lines[i])
        else:
            e.description = _EMPTY_DATA_MSGS[i]
        if i == 2 and leftover:
            e.add_field(
                name="Need more doodles?",
                value=(
                    f"*{leftover} more doodle"
                    f"{'s' if leftover != 1 else ''} couldn't fit. "
                    "For a complete, searchable list of every doodle "
                    "currently in every pet shop, visit "
                    "[ToonHQ's doodle tracker]"
                    "(https://toonhq.org/doodles/).*"
                ),
                inline=False,
            )
        result.append(e)
    return result


# ── FORMAT_INFORMATION ────────────────────────────────────────────────────────

# TTR's API returns some cog type names mashed into one word. Override
# those to the display spelling players actually use.
COG_NAME_OVERRIDES: dict[str, str] = {
    "Telemarketer": "Tele-Marketer",
}


def _fmt_cog_type(raw: str) -> str:
    """Pretty-print a TTR cog type name, patching known oddities."""
    if not raw:
        return "Unknown"
    return COG_NAME_OVERRIDES.get(raw, raw)


def _district_status_icon(status: str) -> str:
    """Icon for a district whose population line is otherwise unadorned."""
    s = (status or "").lower()
    if s in {"offline"}:
        return ":red_circle:"
    if s in {"maintenance", "closed", "draining"}:
        return ":wrench:"
    return ":green_circle:"


def _district_unavailable(status: str) -> bool:
    """True if the district should render as 'Down for Re-Tooning'."""
    return (status or "").lower() in {
        "offline", "maintenance", "closed", "draining",
    }


def format_information(
    *,
    invasions: dict[str, Any] | None,
    population: dict[str, Any] | None,
    fieldoffices: dict[str, Any] | None,
) -> discord.Embed:
    """One combined embed for the #tt-information channel.

    Districts come from the population API, with invasion info merged in.
    Field Offices come from the field-offices API (sorted ★★★ → ★).
    """
    pop_by         = (population or {}).get("populationByDistrict", {}) or {}
    status_by      = (population or {}).get("statusByDistrict", {}) or {}
    active_invasions = (invasions or {}).get("invasions", {}) or {}
    total_pop      = (population or {}).get("totalPopulation")

    if isinstance(total_pop, int):
        title = f"ToonTown Information [ {total_pop:,} Toons Online ]"
    else:
        title = "ToonTown Information"
    embed = discord.Embed(title=title, color=TTR_COLOR)

    parts: list[str] = []

    # Districts (population + invasions combined) ──────────────────────
    if pop_by:
        district_blocks: list[str] = []
        for district in sorted(pop_by.keys(), key=str.lower):
            pop         = pop_by[district]
            status      = status_by.get(district, "unknown")
            inv         = active_invasions.get(district)
            unavailable = _district_unavailable(status)

            if unavailable:
                icon  = _district_status_icon(status)
                line1 = " ".join([_b(f"[{icon}]"), _b(f"[{district}]"), _b("[Unavailable]")])
                line2 = _b("[This District is Down for Re-Tooning]")
                district_blocks.append(f"{line1}\n{line2}")
                continue

            icon  = COG_EMOJI if inv else ":green_circle:"
            line1 = " ".join([_b(f"[{icon}]"), _b(f"[{district}]"), _b(f"[{pop} Online]")])

            line2_parts: list[str] = []
            if inv:
                cog_type = _fmt_cog_type(inv.get("type") or "")
                progress = inv.get("progress", "?/?")
                line2_parts.append(_bi(f"[{cog_type} {progress}]"))
            if _is_safe_district(district):
                line2_parts.append(_b(f"[{SAFE_EMOJI}]"))
            if _is_speedchat_only(district):
                line2_parts.append(_b("[SpeedChat Only]"))

            if line2_parts:
                district_blocks.append(f"{line1}\n{' '.join(line2_parts)}")
            else:
                district_blocks.append(line1)

        body = "\n\n".join(district_blocks)

        legend_entries = [
            f"{SAFE_EMOJI} *Immune to Mega Invasions (event-wide "
            "invasions like 2.0s and Skelecogs that sweep across "
            "most districts at once).*",
            "**SpeedChat Only** *— you cannot use SpeedChat+ in these "
            "districts. Only the phrases from the SpeedChat menu are "
            "available.*",
            "[:green_circle:] *— District is active.*",
            "[:red_circle:] *— District is offline.*",
            "[:wrench:] *— This District is undergoing Re-Tooning by "
            "the Toon Council and will return soon.*",
        ]
        legend = "\n\n".join(legend_entries)
        parts.append("**Districts**\n\n" + body + "\n\n" + legend)
    else:
        parts.append("**Districts**\n*Population data unavailable.*")

    # Field Offices ────────────────────────────────────────────────────
    offices = (fieldoffices or {}).get("fieldOffices", {}) or {}

    fo_blocks: list[str] = []

    kaboomberg_line1 = " ".join([
        _b("[:unlock:]"),
        _b(f"[{STAR_PERFECT * 4}]"),
        _b("[Kaboomberg]"),
    ])
    kaboomberg_line2 = _b(f"[{INFINITE_EMOJI} Annexes Remaining]")
    fo_blocks.append(f"{kaboomberg_line1}\n{kaboomberg_line2}")

    if offices:
        def _sort_key(item: tuple[str, dict]) -> tuple[int, int]:
            zone_str, fo = item
            try:
                zone_id = int(zone_str)
            except (TypeError, ValueError):
                zone_id = 0
            return (-int(fo.get("difficulty", 0)), zone_id)

        for zone_str, fo in sorted(offices.items(), key=_sort_key):
            try:
                zone_id = int(zone_str)
            except (TypeError, ValueError):
                zone_id = 0
            street     = ZONE_NAMES.get(zone_id, f"Zone {zone_str}")
            difficulty = int(fo.get("difficulty", 0)) + 1  # zero-indexed
            stars      = STAR_GREAT * difficulty
            annexes    = fo.get("annexes", "?")
            is_full    = not fo.get("open")
            open_state = ":lock:" if is_full else ":unlock:"

            line1       = " ".join([_b(f"[{open_state}]"), _b(f"[{stars}]"), _b(f"[{street}]")])
            line2_parts = [_b(f"[{annexes} Annexes Remaining]")]
            if is_full:
                line2_parts.append(_b("[FULL]"))
            fo_blocks.append(f"{line1}\n{' '.join(line2_parts)}")

    parts.append("**Field Offices**\n\n" + "\n\n".join(fo_blocks))

    # Last updated timestamp ───────────────────────────────────────────
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    parts.append(f"***Last updated: <t:{now_epoch}:R>***")

    description = "\n\n".join(parts)
    if len(description) > 4000:
        description = description[:3997] + "…"
    embed.description = description

    return embed


# ── FORMAT_SILLYMETER ─────────────────────────────────────────────────────────

# Keyword → (wiki display name, emoji, short description).
# Keys are lowercase substrings checked against the API team name.
_TEAM_INFO: dict[str, tuple[str, str, str]] = {
    "sound":     ("Double Sound Experience",    ":mega:",
                  "Toons earn twice the amount of skill points for Sound gags from defeating Cogs."),
    "squirt":    ("Double Squirt Experience",   ":droplet:",
                  "Toons earn twice the amount of skill points for Squirt gags from defeating Cogs."),
    "throw":     ("Double Throw Experience",    ":pie:",
                  "Toons earn twice the amount of skill points for Throw gags from defeating Cogs."),
    "drop":      ("Double Drop Experience",     ":rock:",
                  "Toons earn twice the amount of skill points for Drop gags from defeating Cogs."),
    "toon-up":   ("Double Toon-Up Experience",  ":sparkling_heart:",
                  "Toons earn twice the amount of skill points for Toon-Up gags from defeating Cogs."),
    "toonup":    ("Double Toon-Up Experience",  ":sparkling_heart:",
                  "Toons earn twice the amount of skill points for Toon-Up gags from defeating Cogs."),
    "trap":      ("Double Trap Experience",     ":mouse_trap:",
                  "Toons earn twice the amount of skill points for Trap gags from defeating Cogs."),
    "lure":      ("Double Lure Experience",     ":fishing_pole_and_fish:",
                  "Toons earn twice the amount of skill points for Lure gags from defeating Cogs."),
    "garden":    ("Speedy Garden Growth",       ":seedling:",
                  "Toons' gardens grow every six hours at 12:00 AM, 6:00 AM, 12:00 PM, and "
                  "6:00 PM Pacific Time. Gardens do not deplete water."),
    "laff":      ("Overjoyed Laff Meters",      ":heart:",
                  "Toons receive +8 laff points to their maximum laff. "
                  "The maximum laff of 140 is temporarily raised to 148."),
    "fish":      ("Teeming Fish Waters",        ":fish:",
                  "Extra fishing docks are available, fish have bigger shadows, "
                  "and an extra fish appears in all ponds."),
    "jellybean": ("Double Jellybeans",          ":jar:",
                  "Jellybeans awarded from activities, including unites, are doubled."),
    "jelly":     ("Double Jellybeans",          ":jar:",
                  "Jellybeans awarded from activities, including unites, are doubled."),
    "racing":    ("Double Racing Tickets",      ":racing_car:",
                  "Toons receive twice the amount of tickets from all race tracks "
                  "in Goofy Speedway, with the exception of Grand Prix."),
    "teleport":  ("Global Teleport Access",     ":globe_with_meridians:",
                  "Toons automatically gain temporary teleport access to any area "
                  "across Toontown that they have already visited."),
    "global":    ("Global Teleport Access",     ":globe_with_meridians:",
                  "Toons automatically gain temporary teleport access to any area "
                  "across Toontown that they have already visited."),
    "doodle":    ("Doodle Trick Boost",         ":dog:",
                  "Toons' doodles perform tricks more frequently and earn more "
                  "experience from each trick they perform."),
}


def _team_info(api_name: str) -> tuple[str, str, str]:
    """Return (wiki name, emoji, description) for a team API name."""
    lower = api_name.lower()
    for keyword, info in _TEAM_INFO.items():
        if keyword in lower:
            return info
    return (api_name, ":star:", "")


# Total Global Silly Points required to fill the meter each cycle.
_SILLYMETER_TOTAL = 5_000_000


def format_sillymeter(data: dict[str, Any] | None) -> discord.Embed:
    """Embed for the #tt-information channel showing Silly Meter status."""
    embed = discord.Embed(title=":circus_tent: Silly Meter", color=TTR_COLOR)

    if data is None:
        embed.description = ":warning: Could not reach the TTR Silly Meter API."
        _footer(embed, None)
        return embed

    state   = (data.get("state") or "").strip()
    winner  = (data.get("winner") or "").strip()
    rewards = data.get("rewards") or []
    descs   = data.get("rewardDescriptions") or []
    hp      = data.get("hp")
    as_of   = data.get("asOf")
    next_ts = data.get("nextUpdateTimestamp")

    if not isinstance(rewards, list):
        rewards = []
    if not isinstance(descs, list):
        descs = []

    try:
        accumulated = int(hp) if hp is not None else 0
    except (TypeError, ValueError):
        accumulated = 0

    # REWARDING: a winning team is active ─────────────────────────────
    if winner:
        wiki_name, emoji, wiki_desc = _team_info(winner)
        body = f":white_check_mark: {emoji} **{wiki_name}** is active!"
        if wiki_desc:
            body += f"\n\n***{wiki_desc}***"
        body += "\n\n*The Silly Meter has been filled. Enjoy the rewards while they last!*"
        embed.description = body

    # COOLING DOWN: meter full, between cycles ────────────────────────
    elif accumulated >= _SILLYMETER_TOTAL or state.lower() not in ("", "active"):
        embed.description = (
            "**The Silly Meter is cooling down...**"
            "\n*Here\'s a sneak peek at the upcoming rewards!*"
        )
        if rewards:
            team_blocks: list[str] = []
            for i, api_name in enumerate(rewards):
                api_name  = api_name.strip()
                wiki_name, emoji, wiki_desc = _team_info(api_name)
                display_desc = wiki_desc or (descs[i] if i < len(descs) else "")
                block = f"{emoji} **{wiki_name}**"
                if display_desc:
                    block += f"\n***{display_desc}***"
                team_blocks.append(block)
            if team_blocks:
                embed.add_field(
                    name="Upcoming Rewards",
                    value="\n​\n".join(team_blocks),
                    inline=False,
                )
        if next_ts:
            try:
                embed.add_field(
                    name="​",
                    value=f":clock3: **Next Silly Cycle begins** <t:{int(next_ts)}:R> — <t:{int(next_ts)}:t>",
                    inline=False,
                )
            except (TypeError, ValueError):
                pass

    # ACTIVE: meter is filling up ─────────────────────────────────────
    else:
        remaining = max(0, _SILLYMETER_TOTAL - accumulated)
        pct       = min(100, accumulated / _SILLYMETER_TOTAL * 100)
        embed.description = (
            "**The Silly Meter is filling up...**"
            f"\n***{remaining:,} Global Silly Points to go!***"
            f"\n​\n{accumulated:,} / {_SILLYMETER_TOTAL:,} ({pct:.0f}%)"
        )
        if rewards:
            team_blocks_active: list[str] = []
            for i, api_name in enumerate(rewards):
                api_name  = api_name.strip()
                wiki_name, emoji, wiki_desc = _team_info(api_name)
                display_desc = wiki_desc or (descs[i] if i < len(descs) else "")
                block = f"{emoji} **{wiki_name}**"
                if display_desc:
                    block += f"\n***{display_desc}***"
                team_blocks_active.append(block)
            if team_blocks_active:
                embed.add_field(
                    name="Competing Teams",
                    value="\n​\n".join(team_blocks_active),
                    inline=False,
                )

    _footer(embed, as_of)
    return embed


# ── FORMATTERS mapping ────────────────────────────────────────────────────────
#
# Each value takes the full api_data dict (keyed by API name) and returns
# list[discord.Embed]. The bot creates / maintains one Discord message per
# embed, in order.
#
# "information" combines three APIs while the others remain single-source.

FORMATTERS = {
    "information": lambda d: [
        format_information(
            invasions=d.get("invasions"),
            population=d.get("population"),
            fieldoffices=d.get("fieldoffices"),
        ),
        format_sillymeter(d.get("sillymeter")),
    ],
    "doodles": lambda d: format_doodles(d.get("doodles")),
}
