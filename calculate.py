# -*- coding: utf-8 -*-
"""
calculate.py — Cog suit disguise point calculator for LanceAQuack TTR.

Exports
-------
register_calculate(bot)          Register the /calculate slash command.
build_suit_calculator_embed()    Build the pinned info embed for #suit-calculator.

Supports all four factions (Sellbot · Cashbot · Lawbot · Bossbot)
for both standard and 2.0 suits.

Returns points remaining + THREE optimised activity plans that each
minimise total runs via a different strategy:
  Option 1 — 🏆 Speed Run    : includes the faction boss (fewest possible runs)
  Option 2 — ⚡ No Boss      : best non-boss activity only
  Option 3 — 🔄 Smart Mix    : 1 boss run + non-boss fill  ·OR·  top two non-boss tiers

Point values are approximate averages based on community data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import discord
from discord import app_commands


# ══════════════════════════════════════════════════════════════════════════════
# Activity tables
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Activity:
    name: str
    min_pts: int
    max_pts: int
    avg_pts: int
    is_boss: bool = False

    @property
    def range_str(self) -> str:
        return f"~{self.min_pts:,}–{self.max_pts:,}"


SELLBOT_ACTIVITIES: list[Activity] = [
    Activity("VP (Sellbot Boss)",         1_800, 2_500, 2_200, is_boss=True),
    Activity("Factory — Full Run",          300,   425,   375),
    Activity("Factory — Short",             150,   250,   200),
    Activity("Individual Sellbot Cogs",       2,    10,     5),
]

CASHBOT_ACTIVITIES: list[Activity] = [
    Activity("CFO (Cashbot Boss)",        2_000, 3_000, 2_500, is_boss=True),
    Activity("Bullion Mint",                500,   700,   600),
    Activity("Dollar Mint",                 200,   300,   250),
    Activity("Short-Change Mint",            50,   100,    75),
    Activity("Individual Cashbot Cogs",       2,    10,     5),
]

LAWBOT_ACTIVITIES: list[Activity] = [
    Activity("CJ (Lawbot Boss)",          2_500, 3_500, 3_000, is_boss=True),
    Activity("DA Office — D",               850,   950,   900),
    Activity("DA Office — C",               600,   700,   650),
    Activity("DA Office — B",               350,   450,   400),
    Activity("DA Office — A",               175,   225,   200),
    Activity("Individual Lawbot Cogs",         2,    10,     5),
]

BOSSBOT_ACTIVITIES: list[Activity] = [
    Activity("CEO (Bossbot Boss)",        3_000, 4_000, 3_500, is_boss=True),
    Activity("Back 9 — Golf Course",      1_400, 1_600, 1_500),
    Activity("Middle 6 — Golf",             700,   900,   800),
    Activity("Front 3 — Golf",              350,   450,   400),
    Activity("Individual Bossbot Cogs",        2,    10,     5),
]

FACTION_ACTIVITIES: dict[str, list[Activity]] = {
    "sellbot": SELLBOT_ACTIVITIES,
    "cashbot":  CASHBOT_ACTIVITIES,
    "lawbot":   LAWBOT_ACTIVITIES,
    "bossbot":  BOSSBOT_ACTIVITIES,
}


# ══════════════════════════════════════════════════════════════════════════════
# Suit registry
# ══════════════════════════════════════════════════════════════════════════════

_SELLBOT_SUITS: dict[str, tuple[str, str, str]] = {
    "coldcaller":      ("Cold Caller",      "CC",   "sellbot"),
    "telemarketer":    ("Telemarketer",     "TM",   "sellbot"),
    "namedropper":     ("Name Dropper",     "ND",   "sellbot"),
    "gladhander":      ("Glad Hander",      "GH",   "sellbot"),
    "movershaker":     ("Mover & Shaker",   "MS",   "sellbot"),
    "twoface":         ("Two-Face",         "TF",   "sellbot"),
    "themingler":      ("The Mingler",      "TNG",  "sellbot"),
    "mrhollywood":     ("Mr. Hollywood",    "MH",   "sellbot"),
}

_CASHBOT_SUITS: dict[str, tuple[str, str, str]] = {
    "shortchange":     ("Short Change",     "SC",   "cashbot"),
    "pennypincher":    ("Penny Pincher",    "PNP",  "cashbot"),
    "tightwad":        ("Tightwad",         "TW",   "cashbot"),
    "beancounter":     ("Bean Counter",     "BC",   "cashbot"),
    "numbercruncher":  ("Number Cruncher",  "NC",   "cashbot"),
    "moneybags":       ("Money Bags",       "MB",   "cashbot"),
    "loanshark":       ("Loan Shark",       "LS",   "cashbot"),
    "robberbaron":     ("Robber Baron",     "RB",   "cashbot"),
}

_LAWBOT_SUITS: dict[str, tuple[str, str, str]] = {
    "bottomfeeder":    ("Bottom Feeder",    "BF",   "lawbot"),
    "bloodsucker":     ("Bloodsucker",      "BS",   "lawbot"),
    "doubletalker":    ("Double Talker",    "DT",   "lawbot"),
    "ambulancechaser": ("Ambulance Chaser", "AC",   "lawbot"),
    "backstabber":     ("Back Stabber",     "BAC",  "lawbot"),
    "spindoctor":      ("Spin Doctor",      "SD",   "lawbot"),
    "legaleagle":      ("Legal Eagle",      "LE",   "lawbot"),
    "bigwig":          ("Big Wig",          "BW",   "lawbot"),
}

_BOSSBOT_SUITS: dict[str, tuple[str, str, str]] = {
    "flunky":          ("Flunky",           "FL",   "bossbot"),
    "pencilpusher":    ("Pencil Pusher",    "PP",   "bossbot"),
    "yesman":          ("Yesman",           "YM",   "bossbot"),
    "micromanager":    ("Micromanager",     "MM",   "bossbot"),
    "downsizer":       ("Downsizer",        "DS",   "bossbot"),
    "headhunter":      ("Head Hunter",      "HH",   "bossbot"),
    "corporateraider": ("Corporate Raider", "CR",   "bossbot"),
    "thebigcheese":    ("The Big Cheese",   "TBC",  "bossbot"),
}

ALL_SUITS: dict[str, tuple[str, str, str]] = {
    **_SELLBOT_SUITS,
    **_CASHBOT_SUITS,
    **_LAWBOT_SUITS,
    **_BOSSBOT_SUITS,
}

_ABBR_TO_KEY: dict[str, str] = {
    info[1].lower(): key for key, info in ALL_SUITS.items()
}

FACTION_META: dict[str, dict] = {
    "sellbot": {"label": "Sellbot",  "currency": "Merits",        "color": 0xE74C3C},
    "cashbot":  {"label": "Cashbot",  "currency": "Cogbucks",      "color": 0x2ECC71},
    "lawbot":   {"label": "Lawbot",   "currency": "Jury Notices",  "color": 0x3498DB},
    "bossbot":  {"label": "Bossbot",  "currency": "Stock Options", "color": 0xF39C12},
}

SUITS_BY_FACTION: dict[str, list[tuple[str, str]]] = {
    "Sellbot": [(v[0], v[1]) for v in _SELLBOT_SUITS.values()],
    "Cashbot":  [(v[0], v[1]) for v in _CASHBOT_SUITS.values()],
    "Lawbot":   [(v[0], v[1]) for v in _LAWBOT_SUITS.values()],
    "Bossbot":  [(v[0], v[1]) for v in _BOSSBOT_SUITS.values()],
}


# ══════════════════════════════════════════════════════════════════════════════
# Promotion point quotas
# ══════════════════════════════════════════════════════════════════════════════
# Points required at each level to earn the NEXT promotion.
# Approximate values based on community data; exact figures vary per suit tier.
# 2.0 suits require ~5x the standard quota at each level.

LEVEL_QUOTAS: dict[int, int] = {
    1:    50,
    2:   100,
    3:   200,
    4:   400,
    5:   800,
    6:  1_600,
    7:  3_000,
    8:  5_000,
    9:  8_000,
    10: 12_000,
    11: 18_000,
    12: 25_000,
}

LEVEL_QUOTAS_V2: dict[int, int] = {k: v * 5 for k, v in LEVEL_QUOTAS.items()}
MAX_LEVEL = 12


# ══════════════════════════════════════════════════════════════════════════════
# Input parsing
# ══════════════════════════════════════════════════════════════════════════════

def _normalise(raw: str) -> str:
    return "".join(c for c in raw.lower() if c.isalnum())


def resolve_suit(raw: str) -> tuple[str, str, str, bool] | None:
    """
    Parse a user-supplied suit string.

    Accepts full names, abbreviations, and optional 2.0 suffix.
    Returns (canonical_key, display_name, faction, is_v2) or None.
    """
    is_v2 = False
    cleaned = raw.strip()

    for suffix in ("2.0", "20", "v2"):
        if cleaned.lower().endswith(suffix):
            candidate = cleaned[: -len(suffix)].strip().rstrip(".")
            if candidate:
                cleaned = candidate
                is_v2 = True
                break

    norm = _normalise(cleaned)

    if norm in ALL_SUITS:
        name, _, faction = ALL_SUITS[norm]
        return norm, name, faction, is_v2

    if norm in _ABBR_TO_KEY:
        key = _ABBR_TO_KEY[norm]
        name, _, faction = ALL_SUITS[key]
        return key, name, faction, is_v2

    for key, (name, _, faction) in ALL_SUITS.items():
        if key.startswith(norm) or _normalise(name).startswith(norm):
            return key, name, faction, is_v2

    return None


# ══════════════════════════════════════════════════════════════════════════════
# Three-option activity planner
# ══════════════════════════════════════════════════════════════════════════════

def _runs(pts: int, act: Activity) -> int:
    return max(1, math.ceil(pts / act.avg_pts)) if pts > 0 else 0


def _plan_lines(plan: list[tuple[Activity, int]]) -> str:
    return "\n".join(
        f"• **{r}×** {a.name}  *({a.range_str} pts/run)*"
        for a, r in plan if r > 0
    )


def build_options(points_remaining: int, activities: list[Activity]) -> list[dict]:
    """
    Return up to three dicts, each describing a minimum-run activity plan.

    Keys: label, emoji, plan [(Activity, runs)], total_runs, note.
    """
    boss_acts     = [a for a in activities if a.is_boss]
    non_boss_sort = sorted(
        [a for a in activities if not a.is_boss],
        key=lambda a: a.avg_pts, reverse=True,
    )
    options: list[dict] = []

    # ── Option 1 : Speed Run (best boss) ──────────────────────────────────
    if boss_acts:
        best_boss = max(boss_acts, key=lambda a: a.avg_pts)
        n = _runs(points_remaining, best_boss)
        options.append({
            "label": "Speed Run",
            "emoji": "🏆",
            "plan":  [(best_boss, n)],
            "total_runs": n,
            "note":  "Fewest runs possible. Requires access to the faction boss.",
        })

    # ── Option 2 : No Boss (best single non-boss) ─────────────────────────
    if non_boss_sort:
        best_nb = non_boss_sort[0]
        n = _runs(points_remaining, best_nb)
        options.append({
            "label": "No Boss Required",
            "emoji": "⚡",
            "plan":  [(best_nb, n)],
            "total_runs": n,
            "note":  "Best option if you aren't running the boss right now.",
        })

    # ── Option 3 : Smart Mix ──────────────────────────────────────────────
    if boss_acts and non_boss_sort:
        best_boss = max(boss_acts, key=lambda a: a.avg_pts)
        best_nb   = non_boss_sort[0]
        rem       = points_remaining - best_boss.avg_pts

        if rem <= 0:
            plan = [(best_boss, 1)]
            note = "A single boss run covers everything. No secondary grind needed."
        else:
            fill = _runs(rem, best_nb)
            plan = [(best_boss, 1), (best_nb, fill)]
            note = (
                "One boss run cuts the grind significantly; "
                "a short secondary session finishes it off."
            )

        options.append({
            "label": "Smart Mix",
            "emoji": "🔄",
            "plan":  plan,
            "total_runs": sum(r for _, r in plan),
            "note":  note,
        })

    elif len(non_boss_sort) >= 2:
        primary   = non_boss_sort[0]
        secondary = non_boss_sort[1]
        bulk      = points_remaining // primary.avg_pts
        rem       = points_remaining - bulk * primary.avg_pts
        fill      = _runs(rem, secondary) if rem > 0 else 0
        plan      = ([(primary, bulk)] if bulk else []) + ([(secondary, fill)] if fill else [])
        if not plan:
            plan = [(primary, 1)]

        options.append({
            "label": "Smart Mix",
            "emoji": "🔄",
            "plan":  plan,
            "total_runs": sum(r for _, r in plan),
            "note":  "Combines two activity tiers to minimise wasted points from over-shooting.",
        })

    return options


# ══════════════════════════════════════════════════════════════════════════════
# Result embed builder
# ══════════════════════════════════════════════════════════════════════════════

def build_result_embed(
    suit_name: str,
    faction: str,
    level: int,
    current_pts: int,
    quota: int,
    is_v2: bool,
    options: list[dict],
) -> discord.Embed:
    pts_remaining = quota - current_pts
    meta          = FACTION_META[faction]
    v2_tag        = " (2.0)" if is_v2 else ""

    embed = discord.Embed(
        title=f"🧮  {suit_name}{v2_tag}  ·  Level {level}",
        color=meta["color"],
    )
    embed.add_field(
        name="📊  Progress",
        value=(
            f"{current_pts:,} / {quota:,} {meta['currency']}\n"
            f"**{pts_remaining:,} {meta['currency']} still needed**"
        ),
        inline=False,
    )

    for i, opt in enumerate(options, start=1):
        total = opt["total_runs"]
        embed.add_field(
            name=(
                f"{opt['emoji']}  Option {i} — {opt['label']}"
                f"  ({total} run{'s' if total != 1 else ''})"
            ),
            value=f"{_plan_lines(opt['plan'])}\n*{opt['note']}*",
            inline=False,
        )

    embed.set_footer(
        text="Point values are averages — actual yields vary per run.  "
             "LanceAQuack TTR • #suit-calculator"
    )
    return embed


# ══════════════════════════════════════════════════════════════════════════════
# #suit-calculator channel info embed
# ══════════════════════════════════════════════════════════════════════════════

def build_suit_calculator_embed() -> discord.Embed:
    """
    Pinned info embed for the #suit-calculator channel.
    Covers: channel purpose, command format, all suits + abbreviations,
    2.0 suit explanation, and approximate points per activity per faction.
    """
    embed = discord.Embed(
        title="🧮  Suit Disguise Calculator",
        description=(
            "This channel is your home base for tracking your **cog suit disguise progress**.\n\n"
            "Use `/calculate` to get your remaining points and **three tailored activity plans** — "
            "each showing the fewest total runs for a different play style:\n"
            "🏆 **Speed Run** — boss-first for maximum efficiency\n"
            "⚡ **No Boss Required** — best non-boss activity only\n"
            "🔄 **Smart Mix** — one boss run + secondary fill, or a two-tier grind\n\n"
            "Results are sent as a private reply, so feel free to use the command any time."
        ),
        color=0x9B59B6,
    )

    # ── How to use ──
    embed.add_field(
        name="📋  Command Format",
        value=(
            "```\n/calculate <suit> <level> <current_points>\n```\n"
            "**`suit`**  Name or abbreviation of your cog suit (see list below).\n"
            "**`level`**  Your current suit level — a number from 1 to 12.\n"
            "**`current_points`**  Points already earned toward your next promotion.\n\n"
            "**Quick examples:**\n"
            "> `/calculate TBC 10 4200`\n"
            "> `/calculate Robber Baron 7 0`\n"
            "> `/calculate LE 12 9000`"
        ),
        inline=False,
    )

    # ── Suit list (one field per faction) ──
    faction_emojis = {
        "Sellbot": "🔴",
        "Cashbot":  "🟢",
        "Lawbot":   "🔵",
        "Bossbot":  "🟠",
    }
    for faction_label, suits in SUITS_BY_FACTION.items():
        lines = "\n".join(
            f"**{abbr}** — {name}" for name, abbr in suits
        )
        embed.add_field(
            name=f"{faction_emojis[faction_label]}  {faction_label} Suits",
            value=lines,
            inline=True,
        )

    # ── 2.0 suits ──
    embed.add_field(
        name="⚙️  Version 2.0 Suits",
        value=(
            "A **2.0 suit** is the upgraded form of a fully maxed cog disguise. "
            "Once you complete every promotion on the top-tier suit of a faction "
            "(The Big Cheese, Robber Baron, Big Wig, or The Big Cheese respectively), "
            "your disguise can continue ranking up into its **Version 2.0** — requiring "
            "roughly **5× more points** per level than the standard suit.\n\n"
            "**To calculate a 2.0 suit**, add `2.0` after the abbreviation:\n"
            "> `/calculate TBC2.0 8 12000`\n"
            "> `/calculate RB2.0 5 1500`\n"
            "> `/calculate BW2.0 11 40000`"
        ),
        inline=False,
    )

    # ── Points per activity (two columns) ──
    embed.add_field(
        name="\u200b",
        value="**── Approximate Points per Activity ──**",
        inline=False,
    )

    faction_order = ["sellbot", "cashbot", "lawbot", "bossbot"]
    for faction in faction_order:
        acts = FACTION_ACTIVITIES[faction]
        meta = FACTION_META[faction]
        lines = "\n".join(
            f"{'👑 ' if a.is_boss else '▸ '}**{a.name}**  {a.range_str}"
            for a in acts
            if "Individual" not in a.name
        )
        embed.add_field(
            name=f"{faction_emojis[meta['label']]}  {meta['label']}  ({meta['currency']})",
            value=lines,
            inline=True,
        )

    embed.set_footer(
        text="Point values are community averages and may vary slightly per run.  "
             "LanceAQuack TTR"
    )
    return embed


# ══════════════════════════════════════════════════════════════════════════════
# Command registration
# ══════════════════════════════════════════════════════════════════════════════

def register_calculate(bot) -> None:
    """Register the /calculate slash command on bot.tree."""

    @bot.tree.command(
        name="calculate",
        description=(
            "[User Command] Calculate remaining suit points and get 3 optimised activity plans."
        ),
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        suit="Suit name or abbreviation, e.g. TBC, Robber Baron, RB2.0",
        level="Your current suit level (1–12)",
        current_points="Points already earned toward your next promotion",
    )
    async def calculate(
        interaction: discord.Interaction,
        suit: str,
        level: app_commands.Range[int, 1, 12],
        current_points: app_commands.Range[int, 0, 500_000],
    ) -> None:

        await interaction.response.defer(ephemeral=True, thinking=True)

        result = resolve_suit(suit)
        if result is None:
            await interaction.followup.send(
                f"❌  **Unknown suit:** `{suit}`\n"
                "Check `#suit-calculator` for the full list of suit names and abbreviations.",
                ephemeral=True,
            )
            return

        _, suit_name, faction, is_v2 = result
        quotas = LEVEL_QUOTAS_V2 if is_v2 else LEVEL_QUOTAS
        quota  = quotas.get(level, LEVEL_QUOTAS[MAX_LEVEL])

        if current_points >= quota:
            await interaction.followup.send(
                f"✅  You already have enough points to promote!\n"
                f"**{current_points:,}** / **{quota:,}** — ready to rank up.",
                ephemeral=True,
            )
            return

        pts_remaining = quota - current_points
        activities    = FACTION_ACTIVITIES[faction]
        options       = build_options(pts_remaining, activities)
        embed         = build_result_embed(
            suit_name, faction, level, current_points, quota, is_v2, options,
        )

        await interaction.followup.send(embed=embed, ephemeral=True)
