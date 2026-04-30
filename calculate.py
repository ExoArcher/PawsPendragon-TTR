# -*- coding: utf-8 -*-
"""
calculate.py — Cog suit disguise point calculator for LanceAQuack TTR.

Exports
-------
register_calculate(bot)          Register the /calculate slash command.
build_suit_calculator_embed()    Pinned info embed for #suit-calculator.

All point quotas are sourced directly from the official TTR suit charts.
The boss fight is the REWARD — activities earn points TOWARD it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import discord
from discord import app_commands


# ══════════════════════════════════════════════════════════════════════════════
# Activity tables  (points earned per run toward the boss fight)
# ══════════════════════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class Activity:
    name: str
    min_pts: int
    max_pts: int

    @property
    def avg_pts(self) -> int:
        return (self.min_pts + self.max_pts) // 2

    @property
    def range_str(self) -> str:
        return f"{self.min_pts:,}–{self.max_pts:,}"


SELLBOT_ACTIVITIES = [
    Activity("Steel Factory — Long",   1_525, 1_630),
    Activity("Steel Factory — Short",    867,   950),
    Activity("Scrap Factory — Long",     596,   638),
    Activity("Scrap Factory — Short",    350,   356),
]
CASHBOT_ACTIVITIES = [
    Activity("Bullion Mint",  1_626, 1_850),
    Activity("Coin Mint",       702,   807),
]
LAWBOT_ACTIVITIES = [
    Activity("Bullion Mint",  1_626, 1_850),
    Activity("Coin Mint",       702,   807),
]
BOSSBOT_ACTIVITIES = [
    Activity("The Final Fringe",  2_097, 2_305),
    Activity("The First Fairway",   882,   975),
]

FACTION_ACTIVITIES: dict[str, list[Activity]] = {
    "sellbot": SELLBOT_ACTIVITIES,
    "cashbot":  CASHBOT_ACTIVITIES,
    "lawbot":   LAWBOT_ACTIVITIES,
    "bossbot":  BOSSBOT_ACTIVITIES,
}

FACTION_META: dict[str, dict] = {
    "sellbot": {"label": "Sellbot",  "currency": "Merits",        "color": 0xA26DB3,
                "boss": "VP (Sellbot Playground)"},
    "cashbot":  {"label": "Cashbot",  "currency": "Cogbucks",      "color": 0x27AE60,
                 "boss": "CFO (Cashbot Playground)"},
    "lawbot":   {"label": "Lawbot",   "currency": "Jury Notices",  "color": 0x3498DB,
                 "boss": "CJ (Lawbot Playground)"},
    "bossbot":  {"label": "Bossbot",  "currency": "Stock Options", "color": 0xE67E22,
                 "boss": "CEO (Bossbot Playground)"},
}


# ══════════════════════════════════════════════════════════════════════════════
# Suit registry
# ══════════════════════════════════════════════════════════════════════════════
# user_abbr -> (faction, chart_key, display_name)
# chart_key matches the HTML source data prefix (some are single letters).

SUITS: dict[str, tuple[str, str, str]] = {
    # Sellbot
    "CC":  ("sellbot", "CC",  "Cold Caller"),
    "TM":  ("sellbot", "T",   "Telemarketer"),    # chart: "T"
    "ND":  ("sellbot", "ND",  "Name Dropper"),
    "GH":  ("sellbot", "GH",  "Glad Hander"),
    "MS":  ("sellbot", "MS",  "Mover & Shaker"),
    "TF":  ("sellbot", "TF",  "Two-Face"),
    "TNG": ("sellbot", "TM",  "The Mingler"),     # chart: "TM"
    "MH":  ("sellbot", "MH",  "Mr. Hollywood"),
    # Cashbot
    "SC":  ("cashbot", "SC",  "Short Change"),
    "PNP": ("cashbot", "PP",  "Penny Pincher"),   # chart: "PP"
    "TW":  ("cashbot", "T",   "Tightwad"),        # chart: "T"
    "BC":  ("cashbot", "BC",  "Bean Counter"),
    "NC":  ("cashbot", "NC",  "Number Cruncher"),
    "MB":  ("cashbot", "MB",  "Money Bags"),
    "LS":  ("cashbot", "LS",  "Loan Shark"),
    "RB":  ("cashbot", "RB",  "Robber Baron"),
    # Lawbot
    "BF":  ("lawbot",  "BF",  "Bottom Feeder"),
    "BLD": ("lawbot",  "B",   "Bloodsucker"),     # chart: "B"
    "DT":  ("lawbot",  "DT",  "Double Talker"),
    "AC":  ("lawbot",  "AC",  "Ambulance Chaser"),
    "BAC": ("lawbot",  "BS",  "Back Stabber"),    # chart: "BS"
    "SD":  ("lawbot",  "SD",  "Spin Doctor"),
    "LE":  ("lawbot",  "LE",  "Legal Eagle"),
    "BW":  ("lawbot",  "BW",  "Big Wig"),
    # Bossbot
    "FL":  ("bossbot", "F",   "Flunky"),          # chart: "F"
    "PP":  ("bossbot", "PP",  "Pencil Pusher"),
    "YM":  ("bossbot", "Y",   "Yesman"),          # chart: "Y"
    "MM":  ("bossbot", "M",   "Micromanager"),    # chart: "M"
    "DS":  ("bossbot", "D",   "Downsizer"),       # chart: "D"
    "HH":  ("bossbot", "HH",  "Head Hunter"),
    "CR":  ("bossbot", "CR",  "Corporate Raider"),
    "TBC": ("bossbot", "TBC", "The Big Cheese"),
}

_NAME_TO_ABBR: dict[str, str] = {
    "coldcaller":"CC",   "telemarketer":"TM", "namedropper":"ND",
    "gladhander":"GH",   "movershaker":"MS",  "mover&shaker":"MS",
    "twoface":"TF",      "two-face":"TF",     "themingler":"TNG",
    "mingler":"TNG",     "mrhollywood":"MH",
    "shortchange":"SC",  "pennypincher":"PNP","tightwad":"TW",
    "beancounter":"BC",  "numbercruncher":"NC","moneybags":"MB",
    "loanshark":"LS",    "robberbaron":"RB",
    "bottomfeeder":"BF", "bloodsucker":"BLD", "doubletalker":"DT",
    "ambulancechaser":"AC","backstabber":"BAC","spindoctor":"SD",
    "legaleagle":"LE",   "bigwig":"BW",
    "flunky":"FL",       "pencilpusher":"PP", "yesman":"YM",
    "micromanager":"MM", "downsizer":"DS",    "headhunter":"HH",
    "corporateraider":"CR","thebigcheese":"TBC","bigcheese":"TBC",
}

SUITS_BY_FACTION: dict[str, list[tuple[str, str]]] = {
    "Sellbot": [("CC","Cold Caller"),("TM","Telemarketer"),("ND","Name Dropper"),
                ("GH","Glad Hander"),("MS","Mover & Shaker"),("TF","Two-Face"),
                ("TNG","The Mingler"),("MH","Mr. Hollywood")],
    "Cashbot":  [("SC","Short Change"),("PNP","Penny Pincher"),("TW","Tightwad"),
                 ("BC","Bean Counter"),("NC","Number Cruncher"),("MB","Money Bags"),
                 ("LS","Loan Shark"),("RB","Robber Baron")],
    "Lawbot":   [("BF","Bottom Feeder"),("BLD","Bloodsucker"),("DT","Double Talker"),
                 ("AC","Ambulance Chaser"),("BAC","Back Stabber"),("SD","Spin Doctor"),
                 ("LE","Legal Eagle"),("BW","Big Wig")],
    "Bossbot":  [("FL","Flunky"),("PP","Pencil Pusher"),("YM","Yesman"),
                 ("MM","Micromanager"),("DS","Downsizer"),("HH","Head Hunter"),
                 ("CR","Corporate Raider"),("TBC","The Big Cheese")],
}


# ══════════════════════════════════════════════════════════════════════════════
# Point quota tables  (sourced from official TTR suit charts)
# quota[faction][chart_key][level] = points needed for promotion
# level 50 = 0 = Maxed
# ══════════════════════════════════════════════════════════════════════════════

QUOTAS: dict[str, dict[str, dict[int, int]]] = {

    "sellbot": {
        "CC": {1:20,  2:30,  3:40,  4:50,  5:200},
        "T":  {2:40,  3:50,  4:60,  5:70,  6:300},
        "ND": {3:60,  4:80,  5:100, 6:120, 7:500},
        "GH": {4:100, 5:130, 6:160, 7:190, 8:800},
        "MS": {5:160, 6:210, 7:260, 8:310, 9:1_300},
        "TF": {6:260, 7:340, 8:420, 9:500, 10:2_100},
        "TM": {7:420, 8:550, 9:680, 10:810, 11:3_400},
        "MH": {
            8:680,   9:890,   10:1_100, 11:1_310, 12:5_500,
            13:680, 14:5_500,
            15:680,  16:890,  17:1_100, 18:1_310, 19:5_500,
            20:680,  21:890,  22:1_100, 23:1_310, 24:1_520,
            25:1_730, 26:1_940, 27:2_150, 28:2_360, 29:5_500,
            30:680,  31:890,  32:1_100, 33:1_310, 34:1_520,
            35:1_730, 36:1_940, 37:2_150, 38:2_360, 39:5_500,
            40:680,  41:890,  42:1_100, 43:1_310, 44:1_520,
            45:1_730, 46:1_940, 47:2_150, 48:2_360, 49:5_500,
            50:0,
        },
    },

    "cashbot": {
        "SC": {1:40,  2:50,  3:60,  4:70,  5:300},
        "PP": {2:60,  3:80,  4:100, 5:120, 6:500},
        "T":  {3:100, 4:130, 5:160, 6:190, 7:800},
        "BC": {4:160, 5:210, 6:260, 7:310, 8:1_300},
        "NC": {5:260, 6:340, 7:420, 8:500, 9:2_100},
        "MB": {6:420, 7:550, 8:680, 9:810, 10:3_400},
        "LS": {7:680, 8:890, 9:1_100, 10:1_310, 11:5_500},
        "RB": {
            8:1_100,  9:1_440,  10:1_780, 11:2_120, 12:8_900,
            13:1_100, 14:8_900,
            15:1_100, 16:1_440, 17:1_780, 18:2_120, 19:8_900,
            20:1_100, 21:1_440, 22:1_780, 23:2_120, 24:2_460,
            25:2_800, 26:3_140, 27:3_480, 28:3_820, 29:8_900,
            30:1_100, 31:1_440, 32:1_780, 33:2_120, 34:2_460,
            35:2_800, 36:3_140, 37:3_480, 38:3_820, 39:8_900,
            40:1_100, 41:1_440, 42:1_780, 43:2_120, 44:2_460,
            45:2_800, 46:3_140, 47:3_480, 48:3_820, 49:8_900,
            50:0,
        },
    },

    "lawbot": {
        "BF": {1:60,  2:80,  3:100, 4:120, 5:500},
        "B":  {2:100, 3:130, 4:160, 5:190, 6:800},
        "DT": {3:160, 4:240, 5:260, 6:310, 7:1_300},
        "AC": {4:260, 5:340, 6:420, 7:500, 8:2_100},
        "BS": {5:420, 6:550, 7:680, 8:810, 9:3_400},
        "SD": {6:680, 7:890, 8:1_100, 9:1_310, 10:5_500},
        "LE": {7:1_110, 8:1_440, 9:1_780, 10:2_120, 11:8_900},
        "BW": {
            8:1_780,  9:2_330,  10:2_880, 11:3_430, 12:14_400,
            13:1_780, 14:14_400,
            15:1_780, 16:2_330, 17:2_880, 18:3_430, 19:14_400,
            20:1_780, 21:2_330, 22:2_880, 23:3_430, 24:3_980,
            25:4_530, 26:5_080, 27:5_630, 28:6_180, 29:14_400,
            30:1_780, 31:2_330, 32:2_880, 33:3_430, 34:3_980,
            35:4_530, 36:5_080, 37:5_630, 38:6_180, 39:14_400,
            40:1_780, 41:2_330, 42:2_880, 43:3_430, 44:3_980,
            45:4_530, 46:5_080, 47:5_630, 48:6_180, 49:14_400,
            50:0,
        },
    },

    "bossbot": {
        "F":   {1:100, 2:130, 3:160, 4:190, 5:800},
        "PP":  {2:160, 3:210, 4:260, 5:310, 6:1_300},
        "Y":   {3:260, 4:340, 5:420, 6:500, 7:2_100},
        "M":   {4:420, 5:550, 6:680, 7:810, 8:3_400},
        "D":   {5:680, 6:890, 7:1_100, 8:1_310, 9:5_500},
        "HH":  {6:1_100, 7:1_400, 8:1_780, 9:2_120, 10:8_900},
        "CR":  {7:1_780, 8:2_330, 9:2_880, 10:3_430, 11:14_400},
        "TBC": {
            8:2_880,   9:3_770,   10:4_660,  11:5_500,  12:23_330,
            13:2_880, 14:23_300,
            15:2_800,  16:3_770,  17:4_660,  18:5_500,  19:23_330,
            20:2_880,  21:3_770,  22:4_660,  23:5_500,  24:6_440,
            25:7_330,  26:8_220,  27:9_110,  28:10_000, 29:23_330,
            30:2_880,  31:3_770,  32:4_660,  33:5_500,  34:6_440,
            35:7_330,  36:8_220,  37:9_110,  38:10_000, 39:23_330,
            40:2_880,  41:3_770,  42:4_660,  43:5_500,  44:6_440,
            45:7_330,  46:8_220,  47:9_110,  48:10_000, 49:23_330,
            50:0,
        },
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# Input parsing
# ══════════════════════════════════════════════════════════════════════════════

def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def resolve_suit(raw: str) -> tuple[str, str, str, str, bool] | None:
    """
    Parse user suit input, stripping any 2.0 suffix.
    Returns (user_abbr, display_name, faction, chart_key, is_v2) or None.
    """
    is_v2 = False
    s = raw.strip()

    for suffix in ("2.0", "20", "v2"):
        if s.lower().endswith(suffix):
            candidate = s[: -len(suffix)].strip().rstrip(".")
            if candidate:
                s = candidate
                is_v2 = True
                break

    norm = _norm(s)
    upper = s.upper()

    if upper in SUITS:
        faction, chart_key, name = SUITS[upper]
        return upper, name, faction, chart_key, is_v2

    if norm in _NAME_TO_ABBR:
        abbr = _NAME_TO_ABBR[norm]
        faction, chart_key, name = SUITS[abbr]
        return abbr, name, faction, chart_key, is_v2

    for abbr, (faction, chart_key, name) in SUITS.items():
        if abbr.lower().startswith(norm) or _norm(name).startswith(norm):
            return abbr, name, faction, chart_key, is_v2

    return None


# ══════════════════════════════════════════════════════════════════════════════
# Activity planner — three options
# ══════════════════════════════════════════════════════════════════════════════

def _ceil_runs(pts: int, act: Activity) -> int:
    return max(1, math.ceil(pts / act.avg_pts)) if pts > 0 else 0


def _plan_lines(plan: list[tuple[Activity, int]]) -> str:
    return "\n".join(
        f"• **{r}×** {a.name}  *({a.range_str} pts/run)*"
        for a, r in plan if r > 0
    )


def build_options(points_remaining: int, activities: list[Activity],
                  currency: str) -> list[dict]:
    """
    Three plans for *points_remaining*:
      Option 1 — Best single activity (fastest)
      Option 2 — Lowest activity (most accessible)
      Option 3 — Smart mix: bulk on best, fill with second-best
    """
    by_avg = sorted(activities, key=lambda a: a.avg_pts, reverse=True)
    best   = by_avg[0]
    second = by_avg[1] if len(by_avg) > 1 else best
    worst  = by_avg[-1]

    options: list[dict] = []

    # Option 1: Best only
    n = _ceil_runs(points_remaining, best)
    options.append({
        "label": "Fastest",
        "emoji": "🏆",
        "plan":  [(best, n)],
        "total": n,
        "note":  f"Most {currency} per run — fewest total runs.",
    })

    # Option 2: Most accessible (lowest yield)
    if worst != best:
        n2 = _ceil_runs(points_remaining, worst)
        options.append({
            "label": "Accessible",
            "emoji": "⚡",
            "plan":  [(worst, n2)],
            "total": n2,
            "note":  "Easiest facility to access — more runs required.",
        })

    # Option 3: Smart mix (best for bulk, second for fill)
    if second != best:
        bulk = points_remaining // best.avg_pts
        rem  = points_remaining - bulk * best.avg_pts
        fill = _ceil_runs(rem, second) if rem > 0 else 0

        if bulk > 0 and fill > 0:
            mix_plan = [(best, bulk), (second, fill)]
            mix_note = "Best facility for the bulk, second-best to top off the remainder."
        elif bulk > 0:
            mix_plan = [(best, bulk)]
            mix_note = "Best facility covers it exactly with no fill needed."
        else:
            mix_plan = [(second, fill)]
            mix_note = "Second-best facility handles the small gap."

        options.append({
            "label": "Smart Mix",
            "emoji": "🔄",
            "plan":  mix_plan,
            "total": sum(r for _, r in mix_plan),
            "note":  mix_note,
        })

    return options


# ══════════════════════════════════════════════════════════════════════════════
# Result embed
# ══════════════════════════════════════════════════════════════════════════════

def build_result_embed(
    suit_name: str, faction: str, level: int,
    current_pts: int, quota: int, is_v2: bool,
    options: list[dict],
) -> discord.Embed:
    meta          = FACTION_META[faction]
    pts_remaining = quota - current_pts
    v2_tag        = " (2.0)" if is_v2 else ""

    embed = discord.Embed(
        title=f"🧮  {suit_name}{v2_tag}  ·  Level {level}",
        color=meta["color"],
    )
    embed.add_field(
        name="📊  Progress",
        value=(
            f"{current_pts:,} / {quota:,} {meta['currency']}\n"
            f"**{pts_remaining:,} {meta['currency']} still needed**\n"
            f"*Complete facilities to earn {meta['currency']} — "
            f"the {meta['boss']} is your reward.*"
        ),
        inline=False,
    )

    for i, opt in enumerate(options, start=1):
        embed.add_field(
            name=(
                f"{opt['emoji']}  Option {i} — {opt['label']}"
                f"  ({opt['total']} run{'s' if opt['total'] != 1 else ''})"
            ),
            value=f"{_plan_lines(opt['plan'])}\n*{opt['note']}*",
            inline=False,
        )

    embed.set_footer(
        text="Point values are per-run averages from in-game data.  "
             "LanceAQuack TTR • #suit-calculator"
    )
    return embed


# ══════════════════════════════════════════════════════════════════════════════
# #suit-calculator pinned channel embed
# ══════════════════════════════════════════════════════════════════════════════

def build_suit_calculator_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🧮  Suit Disguise Calculator",
        description=(
            "Use `/calculate` to find out exactly how many more points your cog suit "
            "needs and get **three activity plans** that minimise total runs.\n\n"
            "**The boss fight is your reward** — the activities listed below earn "
            "Merits / Cogbucks / Jury Notices / Stock Options that count toward your "
            "next promotion quota. Reach the quota, earn a boss fight.\n\n"
            "Results are sent as a private reply so feel free to use it any time."
        ),
        color=0x9B59B6,
    )

    # ── Command format ──
    embed.add_field(
        name="📋  Command Format",
        value=(
            "```\n/calculate <suit> <level> <current_points>\n```\n"
            "**`suit`** — Suit abbreviation or full name (see list below).\n"
            "**`level`** — The number shown next to your suit in-game "
            "(e.g. `12` for MH12, `1` for CC1).\n"
            "**`current_points`** — Points already earned toward this level's quota "
            "(enter `0` if you just ranked up).\n\n"
            "**Examples:**\n"
            "> `/calculate MH 12 3000`\n"
            "> `/calculate TBC 29 0`\n"
            "> `/calculate RB2.0 19 7000`  ← *2.0 suit (see below)*"
        ),
        inline=False,
    )

    # ── Suit lists ──
    faction_emojis = {"Sellbot": "🔴", "Cashbot": "🟢", "Lawbot": "🔵", "Bossbot": "🟠"}
    for faction_label, suits in SUITS_BY_FACTION.items():
        lines = "\n".join(f"**{abbr}** — {name}" for abbr, name in suits)
        embed.add_field(
            name=f"{faction_emojis[faction_label]}  {faction_label} Suits",
            value=lines,
            inline=True,
        )

    # ── 2.0 suits ──
    embed.add_field(
        name="⚙️  Version 2.0 Suits",
        value=(
            "After fully maxing the top-tier suit of a faction at level 50, you unlock "
            "its **2.0 version** — the same level range (8–50) starting fresh from level 8, "
            "with identical point quotas.\n\n"
            "Add `2.0` after the abbreviation to indicate a 2.0 suit:\n"
            "> `MH2.0` · `RB2.0` · `BW2.0` · `TBC2.0`\n\n"
            "*Example:* `/calculate TBC2.0 12 14000`"
        ),
        inline=False,
    )

    # ── Points per activity ──
    embed.add_field(
        name="\u200b",
        value="**── Approximate Points Earned Per Activity Run ──**",
        inline=False,
    )
    for faction_key, acts in FACTION_ACTIVITIES.items():
        meta = FACTION_META[faction_key]
        lines = "\n".join(
            f"▸ **{a.name}** — {a.range_str} {meta['currency']}"
            for a in acts
        )
        embed.add_field(
            name=f"{faction_emojis[meta['label']]}  {meta['label']}  ({meta['currency']})",
            value=lines,
            inline=True,
        )

    embed.set_footer(
        text="Point quotas sourced from official TTR suit charts.  LanceAQuack TTR"
    )
    return embed


# ══════════════════════════════════════════════════════════════════════════════
# Command registration
# ══════════════════════════════════════════════════════════════════════════════

def register_calculate(bot) -> None:

    @bot.tree.command(
        name="calculate",
        description="[User Command] Calculate remaining suit points and get 3 optimised activity plans.",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    @app_commands.describe(
        suit="Suit name or abbreviation, e.g. MH, TBC, Robber Baron, BW2.0",
        level="Level number shown next to your suit in-game (e.g. 12 for MH12)",
        current_points="Points already earned toward this level's quota (0 = just ranked up)",
    )
    async def calculate(
        interaction: discord.Interaction,
        suit: str,
        level: app_commands.Range[int, 1, 50],
        current_points: app_commands.Range[int, 0, 500_000],
    ) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)

        result = resolve_suit(suit)
        if result is None:
            await interaction.followup.send(
                f"❌  **Unknown suit:** `{suit}`\n"
                "Check `#suit-calculator` for the full abbreviation list.",
                ephemeral=True,
            )
            return

        user_abbr, suit_name, faction, chart_key, is_v2 = result

        level_map = QUOTAS[faction][chart_key]
        if level not in level_map:
            lo, hi = min(level_map), max(level_map)
            await interaction.followup.send(
                f"❌  **{suit_name}** uses levels **{lo}–{hi}**. "
                f"You entered `{level}`.",
                ephemeral=True,
            )
            return

        quota = level_map[level]

        if quota == 0:
            await interaction.followup.send(
                f"🎉  **{suit_name}** at level {level} is **Maxed** — "
                "nothing left to earn!",
                ephemeral=True,
            )
            return

        if current_points >= quota:
            await interaction.followup.send(
                f"✅  You already have enough points to promote!\n"
                f"**{current_points:,}** / **{quota:,}** — ready to rank up.",
                ephemeral=True,
            )
            return

        meta    = FACTION_META[faction]
        options = build_options(quota - current_points, FACTION_ACTIVITIES[faction],
                                meta["currency"])
        embed   = build_result_embed(
            suit_name, faction, level, current_points, quota, is_v2, options,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)