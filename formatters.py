"""Turn raw TTR API JSON into Discord embeds.

Each formatter returns a `discord.Embed` (or a list of embeds when one
message would overflow). Discord caps embeds at 6000 chars total and each
field value at 1024, so the formatters keep things conservative.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import discord

# --- Doodle trait tiers -----------------------------------------------
#
# Each trait maps to one tier. The tier determines which star emoji
# appears in that trait's slot, and (alongside slot position for the
# special "Rarely Tired" trait) which embed the doodle ends up in.
#
# Tiers, best -> worst:
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
    # These two real TTR traits weren't in the user's tier list. Treating
    # them as OK (neutral) for now; move to GOOD_TRAITS if you'd rather
    # rate them higher.
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
    Unlisted traits fall back to 'ok' (silver star, neutral) rather
    than 'bad' — safer if TTR ever adds a new trait we haven't mapped.
    Only 'Rarely Tired' cares about slot.
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
PRIORITY_PERFECT = 0
PRIORITY_AMAZING = 1
PRIORITY_GREAT = 2
PRIORITY_GREAT_GOOD = 3
PRIORITY_GREAT_GOOD_OK = 4
PRIORITY_REST = 5

# Back-compat alias so callers that imported the old name keep working.
PRIORITY_ALL_GOLD = PRIORITY_GREAT

# Per-tier weight used as a quality tiebreaker within a priority bucket
# (higher = better). Two doodles in the same bucket can still differ by
# a lot — e.g. 3 Great + 1 Good beats 2 Great + 2 Good inside
# GREAT_GOOD — and this weight restores that ordering so higher-scoring
# doodles always print above lower-scoring ones.
_TIER_WEIGHT = {
    "perfect": 5,
    "amazing": 4,
    "great": 3,
    "good": 2,
    "ok": 1,
    "bad": 0,
}


def doodle_priority(traits: list[str]) -> int:
    """Classify a doodle into the six priority buckets."""
    traits = traits or []
    if len(traits) != 4:
        return PRIORITY_REST
    tiers = tuple(trait_tier(t, i) for i, t in enumerate(traits))
    tier_set = set(tiers)

    # Perfect: Rainbow in slot 0 + three Gold.
    if tiers == ("perfect", "great", "great", "great"):
        return PRIORITY_PERFECT
    # Amazing: one Crystal (Rarely Tired in slots 1-3) + three Gold.
    if tiers.count("amazing") == 1 and tiers.count("great") == 3:
        return PRIORITY_AMAZING
    # Great: four Gold traits, no Rarely Tired at all.
    if tier_set == {"great"}:
        return PRIORITY_GREAT
    # Any Bad trait drops us straight to REST regardless of the rest.
    if "bad" in tier_set:
        return PRIORITY_REST
    # Great / Good mix (Rarely Tired is still welcome — it's strictly
    # better than Great).
    if tier_set <= {"perfect", "amazing", "great", "good"}:
        return PRIORITY_GREAT_GOOD
    # Great / Good / OK mix.
    if tier_set <= {"perfect", "amazing", "great", "good", "ok"}:
        return PRIORITY_GREAT_GOOD_OK
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


# Custom jellybean emoji. Must live in a server the bot is a member of.
JELLYBEAN_EMOJI = os.getenv(
    "JELLYBEAN_EMOJI", "<:Jellybeans:1496983830106603551>"
)

# Custom cog emoji — shown next to districts that are being invaded.
COG_EMOJI = os.getenv("COG_EMOJI", "<:Cog:1496996533432877078>")

# Custom "safe" shield emoji — shown next to districts that are immune
# to Mega Invasions (2.0s, Skelecog invasions, etc.).
SAFE_EMOJI = os.getenv("SAFE_EMOJI", "<:Safe:1497311481711165625>")

# Districts immune to Mega Invasions. Compared against a normalized
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


def _norm_district(name: str) -> str:
    """Normalize a district name for set-membership checks."""
    return (name or "").lower().replace(" ", "").replace("'", "")


def _is_safe_district(name: str) -> bool:
    return _norm_district(name) in SAFE_FROM_MEGA_INVASIONS


def _is_speedchat_only(name: str) -> bool:
    return _norm_district(name) in SPEEDCHAT_ONLY_DISTRICTS

# Tier-named star emojis used in the doodle rating column, one per
# trait slot. Defaults assume the bot has the matching custom emojis
# in a server it's a member of.
STAR_PERFECT = os.getenv(
    "STAR_PERFECT", "<:RBStar:1497375968619135076>"
)
STAR_AMAZING = os.getenv(
    "STAR_AMAZING", "<:RBStar:1497375968619135076>"
)
STAR_GREAT = os.getenv("STAR_GREAT", "<:GoldenStar:1497383695781462016>")
STAR_GOOD = os.getenv("STAR_GOOD", "<:SilverStar:1497299363590967549>")
STAR_OK = os.getenv("STAR_OK", "<:BronzeStar:1497300707554889891>")
STAR_BAD = os.getenv("STAR_BAD", "<:Trash:1497379832865226844>")

# Used for Kaboomberg's "Annexes Remaining" placeholder count and
# anywhere else we want to render an infinity glyph. Override in .env
# if you have a custom emoji you'd rather use.
INFINITE_EMOJI = os.getenv("INFINITE_EMOJI", "♾️")

_TIER_STARS = {
    "perfect": STAR_PERFECT,
    "amazing": STAR_AMAZING,
    "great": STAR_GREAT,
    "good": STAR_GOOD,
    "ok": STAR_OK,
    "bad": STAR_BAD,
}

# Friendly tier label printed as the leading bracket box on each
# doodle row and used in the guide.
PRIORITY_LABELS: dict[int, str] = {
    PRIORITY_PERFECT: "Perfect",
    PRIORITY_AMAZING: "Amazing",
    PRIORITY_GREAT: "Great",
    PRIORITY_GREAT_GOOD: "Good",
    PRIORITY_GREAT_GOOD_OK: "OK",
    PRIORITY_REST: "Bad",
}


def star_for(trait: str, slot: int) -> str:
    return _TIER_STARS[trait_tier(trait, slot)]

# Zone ID -> street name, from the Field Offices API docs.
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

# Department letter -> name.
DEPARTMENTS = {
    "s": "Sellbot",
    "c": "Cashbot",
    "l": "Lawbot",
    "b": "Bossbot",
    "m": "Cashbot",  # some docs use 'm' for Cashbot historically
}

TTR_COLOR = 0x26A2EC  # TTR-ish blue


def _ts(epoch: int | float | None) -> str:
    if not epoch:
        return "unknown"
    # Discord relative timestamp, e.g. "12 seconds ago"
    return f"<t:{int(epoch)}:R>"


def _footer(embed: discord.Embed, last_updated: int | float | None) -> None:
    ts = datetime.now(timezone.utc)
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


# --------------------------------------------------------------------- invasions


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
            cog = inv.get("type", "Unknown")
            progress = inv.get("progress", "?/?")
            as_of = inv.get("asOf")
            lines.append(
                f"**{district}** — {cog}  `{progress}`  ({_ts(as_of)})"
            )
        # Discord description cap is 4096. Trim defensively.
        embed.description = "\n".join(lines)[:4000]

    _footer(embed, data.get("lastUpdated"))
    return embed


# -------------------------------------------------------------------- population


def format_population(data: dict[str, Any] | None) -> discord.Embed:
    if not data:
        return _error("Population", "Could not reach the TTR Population API.")
    if data.get("error"):
        return _error("Population", str(data["error"]))

    total = data.get("totalPopulation", 0)
    pop_by = data.get("populationByDistrict", {}) or {}
    status_by = data.get("statusByDistrict", {}) or {}

    embed = discord.Embed(
        title=":busts_in_silhouette: Toontown Population",
        description=f"**Total Toons online:** {total:,}",
        color=TTR_COLOR,
    )

    status_icon = {
        "online": ":green_circle:",
        "offline": ":black_circle:",
        "draining": ":yellow_circle:",
        "closed": ":red_circle:",
    }

    # Sorted alphabetically by district name.
    rows = sorted(pop_by.items(), key=lambda kv: kv[0].lower())
    lines = []
    for district, pop in rows:
        status = status_by.get(district, "unknown")
        icon = status_icon.get(status, ":white_circle:")
        lines.append(f"{icon} **{district}** — {pop:,} toons ({status})")

    if lines:
        embed.add_field(
            name="Districts",
            value="\n".join(lines)[:1024],
            inline=False,
        )

    _footer(embed, data.get("lastUpdated"))
    return embed


# ----------------------------------------------------------------- field offices


def format_field_offices(data: dict[str, Any] | None) -> discord.Embed:
    if not data:
        return _error(
            "Field Offices", "Could not reach the TTR Field Offices API."
        )

    offices = data.get("fieldOffices", {}) or {}
    embed = discord.Embed(
        title=":office: Active Field Offices",
        color=TTR_COLOR,
    )

    if not offices:
        embed.description = "No Field Offices are currently active."
    else:
        # Sort by difficulty (stars) descending, then by zone id as a
        # stable tiebreaker so ordering is deterministic.
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
            street = ZONE_NAMES.get(zone_id, f"Zone {zone_str}")
            dept = DEPARTMENTS.get((fo.get("department") or "").lower(), "?")
            difficulty = int(fo.get("difficulty", 0)) + 1  # zero-indexed
            stars = ":star:" * difficulty
            annexes = fo.get("annexes", "?")
            open_state = ":unlock:" if fo.get("open") else ":lock:"
            expiring = fo.get("expiring")
            expiring_str = f" • closing {_ts(expiring)}" if expiring else ""
            lines.append(
                f"{open_state} **{street}** — {dept} {stars}  "
                f"(annexes left: {annexes}){expiring_str}"
            )
        embed.description = "\n".join(lines)[:4000]

    _footer(embed, data.get("lastUpdated"))
    return embed


# ---------------------------------------------------------------------- doodles


def _b(text: str) -> str:
    """Bold: wraps content in **…**."""
    return f"**{text}**"


def _bi(text: str) -> str:
    """Bold + italic, using the **_X_** form to dodge the ***…*** /
    **…** boundary-ambiguity that Discord sometimes mis-parses when
    two adjacent bracket groups butt up against each other."""
    return f"**_{text}_**"


def _doodle_line(
    district: str, playground: str, traits: list[str], cost: Any
) -> str:
    """Render one doodle row:

    **[Tier]** **[<stars>]** **_[trait, ...]_** **[District · Playground jb cost jb]**

    Each bracket group is individually bolded (so the brackets
    themselves render heavy); the trait list is bold + italic. A real
    space separator goes between bracket groups so the line has room
    to breathe and Discord's markdown parser doesn't choke on adjacent
    `**` runs.
    """
    traits = traits or []
    label = PRIORITY_LABELS[doodle_priority(traits)]
    location_box = (
        f"[{district} · {playground} "
        f"{JELLYBEAN_EMOJI} {cost} {JELLYBEAN_EMOJI}]"
    )
    if traits:
        stars = "".join(star_for(t, i) for i, t in enumerate(traits[:4]))
        trait_str = ", ".join(traits)
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
    """Embed #1: explanation of the star-rating system.

    Spells out the star → tier mapping at the top, then the tiering
    rubric (what trait combination makes a doodle Perfect / Amazing /
    Great / etc.). Each block is separated by a blank line so the
    embed has room to breathe and matches the spacing used in the
    data embeds below.
    """
    embed = discord.Embed(
        title=":dog: Doodle Trait Guide",
        color=TTR_COLOR,
    )

    # Star → trait-quality legend.
    legend = "\n\n".join(
        [
            f"{STAR_PERFECT} {_b('[Rarely Tired]')} — *Rarely Tired in "
            "the first slot offers the strongest benefit and is noted "
            "on Perfect Doodles. When Rarely Tired is in any other slot "
            "it still offers amazing benefit, keeping your doodle from "
            "tiring in battle and giving more trick uses before it "
            "gets tired.*",
            f"{STAR_GREAT} {_b('[Great]')} — *talents that offer strong "
            "positive benefits to your doodle, but not as strong as "
            "Rarely Tired.*",
            f"{STAR_GOOD} {_b('[Good]')} — *decent talents for your "
            "doodle that just aren't as strong as " + _b('[Great]')
            + " talents.*",
            f"{STAR_OK} {_b('[OK]')} — *these are not good talents, but "
            "they could be worse.*",
            f"{STAR_BAD} {_b('[Bad]')} — *these are just bad traits for "
            "a doodle to have.*",
        ]
    )

    # Tiering list rubric — what trait combination earns each label.
    tiering = "\n\n".join(
        [
            _b("Tiering List Descriptions"),
            f"{_b('[Perfect]')} *Rarely Tired, Great Talent, Great "
            "Talent, Great Talent*",
            f"{_b('[Amazing]')} *3 Great Talents + Rarely Tired*",
            f"{_b('[Great]')} *4 Great Talents (No Rarely Tired)*",
            f"{_b('[Good]')} *3 Great Talents + 1 Good Talent*",
            f"{_b('[OK]')} *2 Great Talents + 2 Good Talents*",
            f"{_b('[Bad]')} *Any Doodle with Negative Talents and any "
            "doodle below the OK threshold*",
        ]
    )

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

    Within a priority bucket, higher total trait-quality prints first
    (e.g. 3 Gold + 1 Half beats 2 Gold + 2 Half). District / playground
    name is the final alphabetical tiebreaker.

    Then **flow-fill** across three data embeds: each doodle goes in the
    highest-numbered embed that still has room in its description. We
    never start a lower-priority doodle until every higher-priority
    doodle has been placed, exactly as specified.

    If the third data embed fills up and doodles are still pending, we
    append a field pointing users to ToonHQ's tracker.
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
                rows.append(
                    (district, playground, traits, d.get("cost", "?"))
                )

    # Strict priority sort, then higher-quality first, then alphabetical.
    rows.sort(key=lambda r: (
        doodle_priority(r[2]),
        -doodle_quality(r[2]),
        r[0].lower(),
        r[1].lower(),
    ))

    # Flow-fill three embed descriptions. Discord's description cap is
    # 4096; we leave some headroom for safety.
    MAX_DESC = 3900
    embed_lines: list[list[str]] = [[], [], []]
    embed_used = [0, 0, 0]
    cur = 0
    leftover = 0
    # We separate doodles with a blank line (\n\n) for breathing room,
    # so each extra line costs len(line) + 2 characters.
    for idx, (district, playground, traits, cost) in enumerate(rows):
        line = _doodle_line(district, playground, traits, cost)
        # First line in an embed doesn't need the leading blank line;
        # subsequent ones in the same embed pay for one.
        line_len = len(line) + (2 if embed_lines[cur] else 0)
        # Walk forward until we find an embed with room for this line.
        while cur < 3 and embed_used[cur] + line_len > MAX_DESC:
            cur += 1
            # Recompute: if we jumped to an empty embed, no leading gap.
            line_len = len(line) + (
                2 if cur < 3 and embed_lines[cur] else 0
            )
        if cur >= 3:
            leftover = len(rows) - idx
            break
        embed_lines[cur].append(line)
        embed_used[cur] += line_len

    result = [guide]
    for i in range(3):
        e = discord.Embed(title=_DATA_EMBED_TITLES[i], color=TTR_COLOR)
        if embed_lines[i]:
            # Blank line between doodle rows for readability.
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


# ---------------------------------------------------- combined information


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
        # "closed" / "draining" are TTR statuses that effectively mean
        # the district is going down for re-tooning; show the wrench.
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
    """One combined embed for the #ttr-information channel.

    Districts come from the population API, with invasion info merged in.
    Field Offices come from the field-offices API (sorted ★★★ → ★).
    """
    pop_by = (population or {}).get("populationByDistrict", {}) or {}
    status_by = (population or {}).get("statusByDistrict", {}) or {}
    active_invasions = (invasions or {}).get("invasions", {}) or {}
    total_pop = (population or {}).get("totalPopulation")

    # Title carries the total toons online (e.g. "ToonTown Information
    # [ 1,234 Toons Online ]"). If the population API is down, we just
    # show the bare title.
    if isinstance(total_pop, int):
        title = f"ToonTown Information [ {total_pop:,} Toons Online ]"
    else:
        title = "ToonTown Information"
    embed = discord.Embed(title=title, color=TTR_COLOR)

    parts: list[str] = []

    # --- Districts (population + invasions combined) --------------

    if pop_by:
        # Each district now renders as a 2-line block with a blank line
        # between blocks, so build the body as a list of multi-line
        # strings and join them with "\n\n" at the end.
        district_blocks: list[str] = []
        for district in sorted(pop_by.keys(), key=str.lower):
            pop = pop_by[district]
            status = status_by.get(district, "unknown")
            inv = active_invasions.get(district)
            unavailable = _district_unavailable(status)

            # --- unavailable districts get a compact "down" layout ---
            if unavailable:
                icon = _district_status_icon(status)
                line1 = " ".join([
                    _b(f"[{icon}]"),
                    _b(f"[{district}]"),
                    _b("[Unavailable]"),
                ])
                line2 = _b("[This District is Down for Re-Tooning]")
                district_blocks.append(f"{line1}\n{line2}")
                continue

            # --- active districts: invasion > plain status ---
            # Line 1: [icon] [District] [N Online]
            icon = COG_EMOJI if inv else ":green_circle:"
            line1 = " ".join([
                _b(f"[{icon}]"),
                _b(f"[{district}]"),
                _b(f"[{pop} Online]"),
            ])

            # Line 2: [Invasion] [:Safe:] [SpeedChat Only]
            #         (only the boxes that apply; skip line 2 if all empty)
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

        # Legend — always show every icon so players have a reference
        # even when no district is currently in that state. Order
        # (top → bottom): Safe → SpeedChat Only → green → red → wrench,
        # with a blank line between each entry for breathing room.
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

    # --- Field Offices -------------------------------------------
    #
    # Each office renders as a 2-line block with a blank line between
    # blocks. Kaboomberg is a hidden 4-star field office only available
    # via a special quest; we always pin it to the top of the list.
    offices = (fieldoffices or {}).get("fieldOffices", {}) or {}

    fo_blocks: list[str] = []

    # Always-on Kaboomberg block (hidden quest field office). 4 RBStars
    # and an infinite-annex placeholder.
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
            street = ZONE_NAMES.get(zone_id, f"Zone {zone_str}")
            difficulty = int(fo.get("difficulty", 0)) + 1  # zero-indexed
            # GoldenStar emoji per spec — replaces the default :star:.
            stars = STAR_GREAT * difficulty
            annexes = fo.get("annexes", "?")
            is_full = not fo.get("open")
            open_state = ":lock:" if is_full else ":unlock:"

            # Line 1: [emoji] [stars] [street]
            line1 = " ".join([
                _b(f"[{open_state}]"),
                _b(f"[{stars}]"),
                _b(f"[{street}]"),
            ])
            # Line 2: [N Annexes Remaining] [FULL?]
            line2_parts = [_b(f"[{annexes} Annexes Remaining]")]
            if is_full:
                line2_parts.append(_b("[FULL]"))
            fo_blocks.append(f"{line1}\n{' '.join(line2_parts)}")

    parts.append("**Field Offices**\n\n" + "\n\n".join(fo_blocks))

    # --- Last updated (live relative timestamp) ------------------
    # Discord renders <t:EPOCH:R> as a live-updating "x seconds ago"
    # label that ticks forward without us having to edit the message.
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    parts.append(f"***Last updated: <t:{now_epoch}:R>***")

    description = "\n\n".join(parts)
    if len(description) > 4000:
        description = description[:3997] + "…"
    embed.description = description

    return embed




# ---------------------------------------------------------------------- sillymeter


def format_sillymeter(data: dict[str, Any] | None) -> discord.Embed:
    """Embed showing whether a Silly Team is active or the meter is charging.

    The TTR Silly Meter API returns a ``state`` field of either
    ``"Rewarding"`` (a winning team is currently active) or ``"Charging"``
    (the meter is filling up). The ``winner`` field holds the active team
    name when rewarding, and is null when charging.
    """
    embed = discord.Embed(title="\U0001f3aa Silly Meter", color=TTR_COLOR)

    if data is None:
        embed.description = ":warning: Could not reach the TTR Silly Meter API."
        _footer(embed, None)
        return embed

    state  = (data.get("state") or "").strip()
    winner = (data.get("winner") or "").strip()

    if state.lower() == "rewarding" and winner:
        embed.description = (
            f"\u2705 **There is an active Silly Team!**\n\n"
            f"**Current Team:** {winner}\n\n"
            f"*The Silly Meter is fully charged and rewarding Toons.*"
        )
    else:
        embed.description = (
            "\u26a1 **The Silly Meter is currently charging.**\n\n"
            "*There is no active Silly Team right now. "
            "Keep playing to help charge the meter!*"
        )

    teams = data.get("teams") or []
    if isinstance(teams, list) and teams:
        lines: list[str] = []
        for team in teams:
            if not isinstance(team, dict):
                continue
            name   = team.get("name") or "Unknown"
            points = team.get("points")
            if points is not None:
                try:
                    lines.append(f"\u2022 **{name}** \u2014 {int(points):,} points")
                except (TypeError, ValueError):
                    lines.append(f"\u2022 **{name}**")
            else:
                lines.append(f"\u2022 **{name}**")
        if lines:
            embed.add_field(name="Team Standings", value="\n".join(lines), inline=False)

    _footer(embed, data.get("lastUpdated"))
    return embed

# --------------------------------------------------------------- public mapping
#
# Each formatter takes the full api_data dict (keyed by API name) and
# returns a discord.Embed. This lets "information" combine three APIs
# while the others stay single-source.

# Each formatter returns list[discord.Embed] — the bot creates /
# maintains one Discord message per embed, in order.
FORMATTERS = {
    "information": lambda d: [format_information(
        invasions=d.get("invasions"),
        population=d.get("population"),
        fieldoffices=d.get("fieldoffices"),
    )],
    "doodles": lambda d: format_doodles(d.get("doodles")),
}
