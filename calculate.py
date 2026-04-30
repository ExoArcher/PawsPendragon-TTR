# -*- coding: utf-8 -*-
"""
calculate.py — Cog suit disguise point calculator for LanceAQuack TTR.

Exports
-------
register_calculate(bot)           Register the /calculate slash command.
build_suit_calculator_embeds()    Returns list of 4 static channel embeds.

All quotas sourced from the official TTR suit wiki tables.
The boss fight is the REWARD — activities earn the points TOWARD it.
2.0 suits use separate higher quota tables (also from official data).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import discord
from discord import app_commands


# ══════════════════════════════════════════════════════════════════════════════
# Activity tables  (points per run earned toward the boss fight)
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

SUITS: dict[str, tuple[str, str, str]] = {
    # user_abbr -> (faction, chart_key, display_name)
    "CC":  ("sellbot", "CC",  "Cold Caller"),
    "TM":  ("sellbot", "T",   "Telemarketer"),
    "ND":  ("sellbot", "ND",  "Name Dropper"),
    "GH":  ("sellbot", "GH",  "Glad Hander"),
    "MS":  ("sellbot", "MS",  "Mover & Shaker"),
    "TF":  ("sellbot", "TF",  "Two-Face"),
    "TNG": ("sellbot", "TM",  "The Mingler"),
    "MH":  ("sellbot", "MH",  "Mr. Hollywood"),
    "SC":  ("cashbot", "SC",  "Short Change"),
    "PNP": ("cashbot", "PP",  "Penny Pincher"),
    "TW":  ("cashbot", "T",   "Tightwad"),
    "BC":  ("cashbot", "BC",  "Bean Counter"),
    "NC":  ("cashbot", "NC",  "Number Cruncher"),
    "MB":  ("cashbot", "MB",  "Money Bags"),
    "LS":  ("cashbot", "LS",  "Loan Shark"),
    "RB":  ("cashbot", "RB",  "Robber Baron"),
    "BF":  ("lawbot",  "BF",  "Bottom Feeder"),
    "BLD": ("lawbot",  "B",   "Bloodsucker"),
    "DT":  ("lawbot",  "DT",  "Double Talker"),
    "AC":  ("lawbot",  "AC",  "Ambulance Chaser"),
    "BAC": ("lawbot",  "BS",  "Back Stabber"),
    "SD":  ("lawbot",  "SD",  "Spin Doctor"),
    "LE":  ("lawbot",  "LE",  "Legal Eagle"),
    "BW":  ("lawbot",  "BW",  "Big Wig"),
    "FL":  ("bossbot", "F",   "Flunky"),
    "PP":  ("bossbot", "PP",  "Pencil Pusher"),
    "YM":  ("bossbot", "Y",   "Yesman"),
    "MM":  ("bossbot", "M",   "Micromanager"),
    "DS":  ("bossbot", "D",   "Downsizer"),
    "HH":  ("bossbot", "HH",  "Head Hunter"),
    "CR":  ("bossbot", "CR",  "Corporate Raider"),
    "TBC": ("bossbot", "TBC", "The Big Cheese"),
}

# 2.0 versions exist only for the top-tier suit of each faction
_V2_SUITS: frozenset[str] = frozenset({"MH", "RB", "BW", "TBC"})

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
# Point quota tables  (official TTR wiki values)
# QUOTAS_V1[faction][chart_key][level]  = normal suit quota
# QUOTAS_V2[chart_key][level]           = 2.0 suit quota (MH/RB/BW/TBC only)
# level 50 = 0 = Maxed
# ══════════════════════════════════════════════════════════════════════════════

QUOTAS_V1: dict[str, dict[str, dict[int, int]]] = {

    "sellbot": {
        "CC": {1:20,  2:30,  3:40,  4:50,  5:150},
        "T":  {2:40,  3:50,  4:60,  5:70,  6:250},
        "ND": {3:60,  4:80,  5:100, 6:120, 7:400},
        "GH": {4:100, 5:130, 6:160, 7:190, 8:650},
        "MS": {5:160, 6:210, 7:260, 8:310, 9:1_050},
        "TF": {6:260, 7:340, 8:420, 9:500, 10:1_700},
        "TM": {7:420, 8:550, 9:680, 10:810, 11:2_750},
        "MH": {
            8:680,   9:890,   10:1_100, 11:1_310, 12:4_450,
            13:680,  14:4_450,
            15:680,  16:890,  17:1_100, 18:1_310, 19:4_450,
            20:680,  21:890,  22:1_100, 23:1_310, 24:1_520,
            25:1_730, 26:1_940, 27:2_150, 28:2_360, 29:4_450,
            30:680,  31:890,  32:1_100, 33:1_310, 34:1_520,
            35:1_730, 36:1_940, 37:2_150, 38:2_360, 39:4_450,
            40:680,  41:890,  42:1_100, 43:1_310, 44:1_520,
            45:1_730, 46:1_940, 47:2_150, 48:2_360, 49:4_450,
            50:0,
        },
    },

    "cashbot": {
        "SC": {1:30,  2:40,  3:50,  4:60,  5:200},
        "PP": {2:50,  3:60,  4:70,  5:80,  6:300},
        "T":  {3:80,  4:100, 5:120, 6:140, 7:500},
        "BC": {4:130, 5:160, 6:190, 7:210, 8:800},
        "NC": {5:210, 6:260, 7:310, 8:360, 9:1_300},
        "MB": {6:340, 7:420, 8:500, 9:580, 10:2_100},
        "LS": {7:550, 8:680, 9:810, 10:940, 11:3_400},
        "RB": {
            8:890,   9:1_100,  10:1_310, 11:1_520, 12:5_500,
            13:890,  14:5_500,
            15:890,  16:1_100, 17:1_310, 18:1_520, 19:5_500,
            20:890,  21:1_100, 22:1_310, 23:1_520, 24:1_730,
            25:1_940, 26:2_150, 27:2_360, 28:2_570, 29:5_500,
            30:890,  31:110,   32:1_310, 33:1_520, 34:1_730,
            35:1_940, 36:2_150, 37:2_360, 38:2_570, 39:5_500,
            40:890,  41:1_110, 42:1_310, 43:1_520, 44:1_730,
            45:1_940, 46:2_150, 47:2_360, 48:2_570, 49:5_500,
            50:0,
        },
    },

    "lawbot": {
        "BF": {1:40,  2:50,  3:60,  4:70,  5:250},
        "B":  {2:60,  3:70,  4:80,  5:90,  6:350},
        "DT": {3:100, 4:120, 5:140, 6:160, 7:600},
        "AC": {4:160, 5:190, 6:220, 7:250, 8:950},
        "BS": {5:260, 6:310, 7:360, 8:410, 9:1_550},
        "SD": {6:420, 7:500, 8:580, 9:660, 10:2_500},
        "LE": {7:680, 8:810, 9:940, 10:1_070, 11:4_050},
        "BW": {
            8:1_100,  9:1_310,  10:1_520, 11:1_730, 12:6_550,
            13:1_100, 14:6_550,
            15:1_100, 16:1_310, 17:1_520, 18:1_730, 19:6_550,
            20:1_100, 21:1_310, 22:1_520, 23:1_730, 24:1_940,
            25:2_150, 26:2_360, 27:2_570, 28:2_780, 29:6_550,
            30:1_100, 31:1_310, 32:1_520, 33:1_730, 34:1_940,
            35:2_150, 36:2_360, 37:2_570, 38:2_780, 39:6_550,
            40:1_100, 41:1_310, 42:1_520, 43:1_730, 44:1_940,
            45:2_150, 46:2_360, 47:2_570, 48:2_780, 49:6_550,
            50:0,
        },
    },

    "bossbot": {
        "F":   {1:50,  2:60,  3:70,  4:80,  5:300},
        "PP":  {2:70,  3:80,  4:90,  5:100, 6:400},
        "Y":   {3:120, 4:140, 5:160, 6:180, 7:700},
        "M":   {4:190, 5:220, 6:250, 7:280, 8:1_100},
        "D":   {5:310, 6:360, 7:410, 8:460, 9:1_800},
        "HH":  {6:500, 7:580, 8:660, 9:740, 10:2_900},
        "CR":  {7:810, 8:940, 9:1_070, 10:1_200, 11:4_700},
        "TBC": {
            8:1_310,  9:1_520,  10:1_730, 11:1_940, 12:7_600,
            13:1_310, 14:7_600,
            15:1_310, 16:1_520, 17:1_730, 18:1_940, 19:7_600,
            20:1_310, 21:1_520, 22:1_730, 23:1_940, 24:2_150,
            25:2_360, 26:2_570, 27:2_780, 28:2_990, 29:7_600,
            30:1_310, 31:1_520, 32:1_730, 33:1_940, 34:2_150,
            35:2_360, 36:2_570, 37:2_780, 38:2_990, 39:7_600,
            40:1_310, 41:1_520, 42:1_730, 43:1_940, 44:2_150,
            45:2_360, 46:2_570, 47:2_780, 48:2_990, 49:7_600,
            50:0,
        },
    },
}

# 2.0 quotas — top-tier suits only (MH/RB/BW/TBC), levels 8–50
QUOTAS_V2: dict[str, dict[int, int]] = {
    "MH": {
        8:1_360,  9:1_780,  10:2_200, 11:2_620, 12:8_900,
        13:1_360, 14:8_900,
        15:1_360, 16:1_780, 17:2_200, 18:2_620, 19:8_900,
        20:1_360, 21:1_780, 22:2_200, 23:2_620, 24:3_040,
        25:3_460, 26:3_880, 27:4_300, 28:4_720, 29:8_900,
        30:1_360, 31:1_780, 32:2_200, 33:2_620, 34:3_040,
        35:3_460, 36:3_880, 37:4_300, 38:4_720, 39:8_900,
        40:1_360, 41:1_780, 42:2_200, 43:2_620, 44:3_040,
        45:3_460, 46:3_880, 47:4_300, 48:4_720, 49:8_900,
        50:0,
    },
    "RB": {
        8:1_789,  9:2_200,  10:2_620, 11:3_040, 12:11_000,
        13:1_780, 14:11_000,
        15:1_780, 16:2_200, 17:2_620, 18:3_040, 19:11_000,
        20:1_780, 21:2_200, 22:2_620, 23:3_040, 24:3_460,
        25:3_880, 26:4_300, 27:4_720, 28:5_140, 29:11_000,
        30:1_780, 31:2_200, 32:2_620, 33:3_040, 34:3_460,
        35:3_880, 36:4_300, 37:4_720, 38:5_140, 39:11_000,
        40:1_780, 41:2_200, 42:2_620, 43:3_040, 44:3_460,
        45:3_880, 46:4_300, 47:4_720, 48:5_140, 49:11_000,
        50:0,
    },
    "BW": {
        8:2_200,  9:2_620,  10:3_040, 11:3_460, 12:13_100,
        13:2_200, 14:13_100,
        15:2_200, 16:2_620, 17:3_040, 18:3_460, 19:13_100,
        20:2_200, 21:2_620, 22:3_040, 23:3_460, 24:3_880,
        25:4_300, 26:4_720, 27:5_140, 28:5_560, 29:13_100,
        30:2_200, 31:2_620, 32:3_040, 33:3_460, 34:3_880,
        35:4_300, 36:4_720, 37:5_140, 38:5_560, 39:13_100,
        40:2_200, 41:2_620, 42:3_040, 43:3_460, 44:3_880,
        45:4_300, 46:4_720, 47:5_140, 48:5_560, 49:13_100,
        50:0,
    },
    "TBC": {
        8:2_620,  9:3_040,  10:3_460, 11:3_880, 12:15_200,
        13:2_620, 14:15_200,
        15:2_620, 16:3_040, 17:3_460, 18:3_880, 19:15_200,
        20:2_620, 21:3_040, 22:3_460, 23:3_880, 24:4_300,
        25:4_720, 26:5_140, 27:5_560, 28:5_980, 29:15_200,
        30:2_620, 31:3_040, 32:3_460, 33:3_880, 34:4_300,
        35:4_720, 36:5_140, 37:5_560, 38:5_980, 39:15_200,
        40:2_620, 41:3_040, 42:3_460, 43:3_880, 44:4_300,
        45:4_720, 46:5_140, 47:5_560, 48:5_980, 49:15_200,
        50:0,
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# Input parsing
# ══════════════════════════════════════════════════════════════════════════════

def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def resolve_suit(raw: str) -> tuple[str, str, str, str, bool] | None:
    """Returns (user_abbr, display_name, faction, chart_key, is_v2) or None."""
    is_v2 = False
    s = raw.strip()
    for suffix in ("2.0", "20", "v2"):
        if s.lower().endswith(suffix):
            candidate = s[: -len(suffix)].strip().rstrip(".")
            if candidate:
                s = candidate
                is_v2 = True
                break

    norm  = _norm(s)
    upper = s.upper()

    if upper in SUITS:
        faction, chart_key, name = SUITS[upper]
        # Only top-tier suits have 2.0 versions
        if is_v2 and upper not in _V2_SUITS:
            is_v2 = False
        return upper, name, faction, chart_key, is_v2

    if norm in _NAME_TO_ABBR:
        abbr = _NAME_TO_ABBR[norm]
        faction, chart_key, name = SUITS[abbr]
        if is_v2 and abbr not in _V2_SUITS:
            is_v2 = False
        return abbr, name, faction, chart_key, is_v2

    for abbr, (faction, chart_key, name) in SUITS.items():
        if abbr.lower().startswith(norm) or _norm(name).startswith(norm):
            if is_v2 and abbr not in _V2_SUITS:
                is_v2 = False
            return abbr, name, faction, chart_key, is_v2

    return None


def get_quota(user_abbr: str, faction: str, chart_key: str,
              level: int, is_v2: bool) -> int | None:
    if is_v2:
        return QUOTAS_V2.get(user_abbr, {}).get(level)
    return QUOTAS_V1[faction].get(chart_key, {}).get(level)


def valid_level_range(user_abbr: str, faction: str, chart_key: str,
                      is_v2: bool) -> tuple[int, int]:
    if is_v2:
        lvls = list(QUOTAS_V2.get(user_abbr, {}).keys())
    else:
        lvls = list(QUOTAS_V1[faction].get(chart_key, {}).keys())
    return (min(lvls), max(lvls)) if lvls else (1, 50)


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


def build_options(pts: int, activities: list[Activity],
                  currency: str) -> list[dict]:
    by_avg = sorted(activities, key=lambda a: a.avg_pts, reverse=True)
    best   = by_avg[0]
    second = by_avg[1] if len(by_avg) > 1 else best
    worst  = by_avg[-1]
    collected: list[dict] = []

    # Build Smart Mix
    if second != best:
        bulk = pts // best.avg_pts
        rem  = pts - bulk * best.avg_pts
        fill = _ceil_runs(rem, second) if rem > 0 else 0
        if bulk > 0 and fill > 0:
            mix_plan = [(best, bulk), (second, fill)]
            mix_note = "Best facility for the bulk, second-best to finish the remainder."
        elif bulk > 0:
            mix_plan = [(best, bulk)]
            mix_note = "Best facility covers it exactly — no fill runs needed."
        else:
            mix_plan = [(second, fill)]
            mix_note = "Second-best facility handles the gap."
        collected.append({
            "label": "Smart Mix",
            "emoji": "🔄",
            "plan":  mix_plan,
            "total": sum(r for _, r in mix_plan),
            "note":  mix_note,
        })

    # Build Fastest (best single activity)
    n = _ceil_runs(pts, best)
    collected.append({
        "label": "Fastest",
        "emoji": "🏆",
        "plan":  [(best, n)],
        "total": n,
        "note":  f"Most {currency} per run — fewest total runs.",
    })

    # Build Accessible (lowest yield, highest run count)
    if worst != best:
        n2 = _ceil_runs(pts, worst)
        collected.append({
            "label": "Accessible",
            "emoji": "⚡",
            "plan":  [(worst, n2)],
            "total": n2,
            "note":  "Easiest facility to access — more runs required.",
        })

    return collected


# ══════════════════════════════════════════════════════════════════════════════
# /calculate result embed
# ══════════════════════════════════════════════════════════════════════════════

def build_result_embed(
    suit_name: str, faction: str, level: int,
    current_pts: int, quota: int, is_v2: bool,
    options: list[dict],
) -> discord.Embed:
    meta = FACTION_META[faction]
    pts_remaining = quota - current_pts
    v2_tag = " (2.0)" if is_v2 else ""

    embed = discord.Embed(
        title=f"🧮  {suit_name}{v2_tag}  ·  Level {level}",
        color=meta["color"],
    )
    embed.add_field(
        name="📊  Progress",
        value=(
            f"{current_pts:,} / {quota:,} {meta['currency']}\n"
            f"**{pts_remaining:,} {meta['currency']} still needed**\n"
            f"*Run facilities to earn {meta['currency']}*"
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
        text="Point values are per-run averages.  LanceAQuack TTR • #suit-calculator"
    )
    return embed


# ══════════════════════════════════════════════════════════════════════════════
# Static channel embeds  (4 separate messages, updated on startup / /laq-refresh)
# ══════════════════════════════════════════════════════════════════════════════

def build_suit_calculator_embeds() -> list[discord.Embed]:
    """Return the list of 4 static embeds for the #suit-calculator channel."""
    embeds: list[discord.Embed] = []

    # ── Embed 1: Introduction ─────────────────────────────────────────────────
    e1 = discord.Embed(
        title="🎰  Suit-O-Nomics Calculator-inator",
        description=(
            "**Spending less time grinding, more time fighting bosses.**\n\n"
            "The Suit-O-Nomics Calculator-inator takes your current cog suit level "
            "and how many points you've already earned, then calculates exactly how "
            "many facility runs stand between you and your next boss fight.\n\n"
            "Three plans are returned — Fastest, Accessible, and a Smart Mix — "
            "each showing the minimum number of runs for a different play style.\n\n"
            "Results are sent as a private reply so feel free to use it any time, right here."
        ),
        color=0x9B59B6,
    )
    embeds.append(e1)

    # ── Embed 2: Suit list + 2.0 ─────────────────────────────────────────────
    faction_emojis = {"Sellbot": "🔴", "Cashbot": "🟢", "Lawbot": "🔵", "Bossbot": "🟠"}
    suit_sections: list[str] = []
    for faction_label, suits in SUITS_BY_FACTION.items():
        lines = [f"{faction_emojis[faction_label]} **{faction_label}**"]
        lines += [f"**{abbr}** — {name}" for abbr, name in suits]
        suit_sections.append("\n".join(lines))

    v2_section = (
        "⚙️ **Version 2.0 Suits**\n"
        "After fully maxing the top-tier suit of a faction at level 50, "
        "you unlock its 2.0 version — the same level range (8–50) starting "
        "fresh from level 8, with identical point quotas. "
        "Add `2.0` after the abbreviation to indicate a 2.0 suit:\n"
        "`MH2.0` · `RB2.0` · `BW2.0` · `TBC2.0`"
    )

    e2 = discord.Embed(
        title="📋  Available Suits",
        description="\n\n".join(suit_sections) + "\n\n" + v2_section,
        color=0x9B59B6,
    )
    embeds.append(e2)

    # ── Embed 3: Command format ───────────────────────────────────────────────
    e3 = discord.Embed(
        title="⌨️  How to Use",
        description=(
            "Use `/calculate` to find out exactly how many more points your cog suit "
            "needs and get three activity plans that minimise time between your runs!\n\n"
            "**Command Format**\n"
            "```\n/calculate <suit> <level> <current_points>\n```\n"
            "`suit` — Suit abbreviation or full name (see list above).\n"
            "`level` — The number shown next to your suit in-game "
            "(e.g. `12` for MH12, `1` for CC1).\n"
            "`current_points` — Points already earned toward this level's quota "
            "(enter `0` if you just ranked up).\n\n"
            "**Examples:**\n"
            "`/calculate MH 12 3000`\n"
            "`/calculate TBC 29 0`\n"
            "`/calculate RB2.0 19 7000` ← 2.0 suit"
        ),
        color=0x9B59B6,
    )
    embeds.append(e3)

    # ── Embed 4: Activity points ──────────────────────────────────────────────
    activity_blocks: list[str] = []
    for faction_key, acts in FACTION_ACTIVITIES.items():
        meta = FACTION_META[faction_key]
        emoji = faction_emojis[meta["label"]]
        lines = [f"{emoji} **{meta['label']} ({meta['currency']})**"]
        lines += [f"▸ {a.name} — {a.range_str} {meta['currency']}" for a in acts]
        activity_blocks.append("\n".join(lines))

    e4 = discord.Embed(
        title="── Approximate Points Earned Per Activity Run ──",
        description="\n\n".join(activity_blocks),
        color=0x9B59B6,
    )
    embeds.append(e4)

    return embeds


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
        lo, hi = valid_level_range(user_abbr, faction, chart_key, is_v2)

        if level < lo or level > hi:
            await interaction.followup.send(
                f"❌  **{suit_name}{'(2.0)' if is_v2 else ''}** uses levels "
                f"**{lo}–{hi}**. You entered `{level}`.",
                ephemeral=True,
            )
            return

        quota = get_quota(user_abbr, faction, chart_key, level, is_v2)
        if quota is None:
            await interaction.followup.send(
                f"❌  No data found for **{suit_name}** level `{level}`.",
                ephemeral=True,
            )
            return

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
        pts     = quota - current_points
        options = build_options(pts, FACTION_ACTIVITIES[faction], meta["currency"])
        embed   = build_result_embed(
            suit_name, faction, level, current_points, quota, is_v2, options,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)