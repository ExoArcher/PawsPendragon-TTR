# calculate.py
"""
Cog suit disguise point calculator for Paws Pendragon TTR.

Exports
-------
    register_calculate(bot)        Register the /calculate slash command.
    build_suit_calculator_embeds() Returns list of 4 static channel embeds.

Point quotas sourced from the official TTR suit wiki tables.
2.0 suits use separate higher quota tables.

Sections
--------
  Activities          -- Activity dataclass, per-faction activity lists, FACTION_ACTIVITIES
  Faction metadata    -- FACTION_META display info (label, currency, color, emoji)
  Suit registry       -- SUITS, _V2_SUITS, _NAME_TO_ABBR, SUITS_BY_FACTION
  Point quota tables  -- QUOTAS_V1 (normal), QUOTAS_V2 (2.0 suits)
  Input parsing       -- parse_level(), resolve_suit(), get_quota(), valid_level_range()
  Activity planner    -- build_options() and helpers
  Progress bar        -- _progress_bar()
  Result embed        -- build_result_embed()
  Static embeds       -- build_suit_calculator_embeds()
  Command registration-- register_calculate(bot)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import discord
from discord import app_commands


# ── ACTIVITIES ────────────────────────────────────────────────────────────────

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
    Activity("Steel Factory — Long",  1_525, 1_630),
    Activity("Steel Factory — Short",   867,   950),
    Activity("Scrap Factory — Long",    596,   638),
    Activity("Scrap Factory — Short",   350,   356),
]
CASHBOT_ACTIVITIES = [
    Activity("Bullion Mint", 1_626, 1_850),
    Activity("Coin Mint",      702,   807),
]
LAWBOT_ACTIVITIES = [
    Activity("DA Office — Senior Wing", 1_854, 2_082),
    Activity("DA Office — Junior Wing",   781,   889),
]
BOSSBOT_ACTIVITIES = [
    Activity("The Final Fringe",  2_097, 2_305),
    Activity("The First Fairway",   882,   975),
]

FACTION_ACTIVITIES: dict[str, list[Activity]] = {
    "sellbot": SELLBOT_ACTIVITIES,
    "cashbot": CASHBOT_ACTIVITIES,
    "lawbot":  LAWBOT_ACTIVITIES,
    "bossbot": BOSSBOT_ACTIVITIES,
}


# ── FACTION METADATA ──────────────────────────────────────────────────────────

FACTION_META: dict[str, dict] = {
    "sellbot": {
        "label":    "Sellbot",
        "currency": "Merits",
        "color":    0xE74C3C,
        "emoji":    "\U0001f4bc",
    },
    "cashbot": {
        "label":    "Cashbot",
        "currency": "Cogbucks",
        "color":    0xF1C40F,
        "emoji":    "\U0001f4b0",
    },
    "lawbot": {
        "label":    "Lawbot",
        "currency": "Jury Notices",
        "color":    0x3498DB,
        "emoji":    "⚖️",
    },
    "bossbot": {
        "label":    "Bossbot",
        "currency": "Stock Options",
        "color":    0x2ECC71,
        "emoji":    "\U0001f454",
    },
}


# ── SUIT REGISTRY ─────────────────────────────────────────────────────────────
# user_abbr -> (faction, chart_key, display_name)

SUITS: dict[str, tuple[str, str, str]] = {
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

# 2.0 versions exist only for the top-tier suit of each faction.
_V2_SUITS: frozenset[str] = frozenset({"MH", "RB", "BW", "TBC"})

_NAME_TO_ABBR: dict[str, str] = {
    "coldcaller":     "CC",  "telemarketer": "TM",  "namedropper":  "ND",
    "gladhander":     "GH",  "movershaker":  "MS",  "mover&shaker": "MS",
    "twoface":        "TF",  "two-face":     "TF",  "themingler":   "TNG",
    "mingler":        "TNG", "mrhollywood":  "MH",
    "shortchange":    "SC",  "pennypincher": "PNP", "tightwad":     "TW",
    "beancounter":    "BC",  "numbercruncher":"NC",  "moneybags":    "MB",
    "loanshark":      "LS",  "robberbaron":  "RB",
    "bottomfeeder":   "BF",  "bloodsucker":  "BLD", "doubletalker": "DT",
    "ambulancechaser":"AC",  "backstabber":  "BAC", "spindoctor":   "SD",
    "legaleagle":     "LE",  "bigwig":       "BW",
    "flunky":         "FL",  "pencilpusher": "PP",  "yesman":       "YM",
    "micromanager":   "MM",  "downsizer":    "DS",  "headhunter":   "HH",
    "corporateraider":"CR",  "thebigcheese": "TBC", "bigcheese":    "TBC",
}

SUITS_BY_FACTION: dict[str, list[tuple[str, str]]] = {
    "Sellbot": [
        ("CC","Cold Caller"),("TM","Telemarketer"),("ND","Name Dropper"),
        ("GH","Glad Hander"),("MS","Mover & Shaker"),("TF","Two-Face"),
        ("TNG","The Mingler"),("MH","Mr. Hollywood"),
    ],
    "Cashbot": [
        ("SC","Short Change"),("PNP","Penny Pincher"),("TW","Tightwad"),
        ("BC","Bean Counter"),("NC","Number Cruncher"),("MB","Money Bags"),
        ("LS","Loan Shark"),("RB","Robber Baron"),
    ],
    "Lawbot": [
        ("BF","Bottom Feeder"),("BLD","Bloodsucker"),("DT","Double Talker"),
        ("AC","Ambulance Chaser"),("BAC","Back Stabber"),("SD","Spin Doctor"),
        ("LE","Legal Eagle"),("BW","Big Wig"),
    ],
    "Bossbot": [
        ("FL","Flunky"),("PP","Pencil Pusher"),("YM","Yesman"),
        ("MM","Micromanager"),("DS","Downsizer"),("HH","Head Hunter"),
        ("CR","Corporate Raider"),("TBC","The Big Cheese"),
    ],
}


# ── POINT QUOTA TABLES ────────────────────────────────────────────────────────
# QUOTAS_V1[faction][chart_key][level]  = normal suit quota
# QUOTAS_V2[chart_key][level]           = 2.0 suit quota (MH/RB/BW/TBC only)
# level 50 = 0 = Maxed

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
            30:890,  31:1_100, 32:1_310, 33:1_520, 34:1_730,
            35:1_940, 36:2_150, 37:2_360, 38:2_570, 39:5_500,
            40:890,  41:1_100, 42:1_310, 43:1_520, 44:1_730,
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

# 2.0 quotas — top-tier suits only (MH / RB / BW / TBC), higher than V1.
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
        8:1_780,  9:2_200,  10:2_620, 11:3_040, 12:11_000,
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


# ── INPUT PARSING ─────────────────────────────────────────────────────────────

def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def parse_level(raw: str) -> tuple[int, bool]:
    """Parse level string -> (level_number, is_v2). Returns (-1, False) on failure."""
    s     = raw.strip()
    is_v2 = False
    for suffix in ("2.0", ".0", "v2"):
        if s.lower().endswith(suffix):
            s     = s[: -len(suffix)].strip()
            is_v2 = True
            break
    try:
        return int(s), is_v2
    except ValueError:
        return -1, is_v2


def resolve_suit(raw: str) -> tuple[str, str, str, str, bool] | None:
    """Returns (user_abbr, display_name, faction, chart_key, is_v2) or None."""
    is_v2 = False
    s     = raw.strip()
    for suffix in ("2.0", "20", "v2"):
        if s.lower().endswith(suffix):
            candidate = s[: -len(suffix)].strip().rstrip(".")
            if candidate:
                s     = candidate
                is_v2 = True
                break

    norm  = _norm(s)
    upper = s.upper()

    if upper in SUITS:
        faction, chart_key, name = SUITS[upper]
        if is_v2 and upper not in _V2_SUITS:
            is_v2 = False
        return upper, name, faction, chart_key, is_v2

    if norm in _NAME_TO_ABBR:
        abbr             = _NAME_TO_ABBR[norm]
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


# ── ACTIVITY PLANNER ──────────────────────────────────────────────────────────

def _ceil_runs(pts: int, act: Activity) -> int:
    return max(1, math.ceil(pts / act.avg_pts)) if pts > 0 else 0


def _plan_lines(plan: list[tuple[Activity, int]]) -> str:
    return "\n".join(
        f"• **{r}×** {a.name}  *({a.range_str} pts/run)*"
        for a, r in plan if r > 0
    )


def build_options(pts: int, activities: list[Activity]) -> list[dict]:
    """Return up to 3 named activity plans: Smart Mix, Fastest, Uber Friendly."""
    by_avg = sorted(activities, key=lambda a: a.avg_pts, reverse=True)
    best   = by_avg[0]
    second = by_avg[1] if len(by_avg) > 1 else best
    worst  = by_avg[-1]
    collected: list[dict] = []

    # Smart Mix: bulk runs of best, fill remainder with second-best.
    if second != best:
        bulk = pts // best.avg_pts
        rem  = pts - bulk * best.avg_pts
        fill = _ceil_runs(rem, second) if rem > 0 else 0
        if bulk > 0 and fill > 0:
            plan = [(best, bulk), (second, fill)]
            note = "Best facility for the bulk, second-best to finish the remainder."
        elif bulk > 0:
            plan = [(best, bulk)]
            note = "Best facility covers it exactly — no fill runs needed."
        else:
            plan = [(second, fill)]
            note = "Second-best facility handles the gap."
        collected.append({
            "label": "Smart Mix",
            "emoji": "\U0001f504",
            "plan":  plan,
            "total": sum(r for _, r in plan),
            "note":  note,
        })

    # Fastest: fewest runs using highest-yield facility.
    n = _ceil_runs(pts, best)
    collected.append({
        "label": "Fastest",
        "emoji": "\U0001f3c6",
        "plan":  [(best, n)],
        "total": n,
        "note":  "Most points per run — fewest total runs.",
    })

    # Uber Friendly: lowest-yield facility (easiest to access).
    if worst != best:
        n2 = _ceil_runs(pts, worst)
        collected.append({
            "label": "Uber Friendly",
            "emoji": "⚡",
            "plan":  [(worst, n2)],
            "total": n2,
            "note":  "Easiest facility to access — more runs required.",
        })

    return collected


# ── PROGRESS BAR ──────────────────────────────────────────────────────────────

def _progress_bar(pct: float, length: int = 12) -> str:
    filled = round(pct / 100 * length)
    return "█" * filled + "░" * (length - filled)


# ── RESULT EMBED ──────────────────────────────────────────────────────────────

def build_result_embed(
    suit_name: str, faction: str, level: int,
    current_pts: int, quota: int, is_v2: bool,
    options: list[dict],
) -> discord.Embed:
    meta          = FACTION_META[faction]
    pts_remaining = quota - current_pts
    pct           = min(100.0, current_pts / quota * 100) if quota > 0 else 100.0
    bar           = _progress_bar(pct)
    v2_tag        = " 2.0" if is_v2 else ""
    currency      = meta["currency"]

    embed = discord.Embed(
        title=f"{meta['emoji']} {suit_name}{v2_tag} — Level {level}",
        color=meta["color"],
    )
    embed.add_field(
        name=f"\U0001f4ca {currency} Progress",
        value=(
            f"{bar} **{pct:.1f}%**\n"
            f"Have: **{current_pts:,}** / Need: **{quota:,}**\n"
            f"Still needed: **{pts_remaining:,}** {currency}"
        ),
        inline=False,
    )
    for opt in options:
        runs = opt["total"]
        embed.add_field(
            name=(
                f"{opt['emoji']} {opt['label']}"
                f" — {runs} run{'s' if runs != 1 else ''}"
            ),
            value=f"{_plan_lines(opt['plan'])}\n*{opt['note']}*",
            inline=False,
        )
    embed.set_footer(text="Paws Pendragon TTR • Suit Calculator")
    return embed


# ── STATIC CHANNEL EMBEDS ─────────────────────────────────────────────────────

def build_suit_calculator_embeds() -> list[discord.Embed]:
    """Return the 4 static info embeds posted in #suit-calculator."""
    STATIC_COLOR = 0x9124F2
    faction_emojis = {
        "Sellbot": "\U0001f4bc",
        "Cashbot": "\U0001f4b0",
        "Lawbot":  "⚖️",
        "Bossbot": "\U0001f454",
    }

    # Embed 1: Introduction ───────────────────────────────────────────
    e1 = discord.Embed(
        title="\U0001f3b0 Suit-O-Nomics Calculator-inator",
        description=(
            "**Spending less time grinding, more time fighting bosses.**\n\n"
            "The Suit-O-Nomics Calculator-inator takes your current cog suit "
            "level and how many points you've already earned, then calculates "
            "exactly how many facility runs stand between you and your next boss "
            "fight.\n\n"
            "Three plans are returned — **Fastest**, **Uber Friendly**, and a "
            "**Smart Mix** — each showing the minimum number of runs for a "
            "different play style.\n\n"
            "Results are sent as a private reply so feel free to use it any time, "
            "right here."
        ),
        color=STATIC_COLOR,
    )

    # Embed 2: Suit list ──────────────────────────────────────────────
    suit_sections: list[str] = []
    for faction_label, suits in SUITS_BY_FACTION.items():
        emoji = faction_emojis[faction_label]
        lines = [f"{emoji} **{faction_label}**"]
        lines += [f"**{abbr}** — {name}" for abbr, name in suits]
        suit_sections.append("\n".join(lines))
    v2_section = (
        "⚙️ **Version 2.0 Suits**\n"
        "After fully maxing the top-tier suit of a faction at level 50, "
        "you unlock its 2.0 version — the same level range (8–50) "
        "starting fresh from level 8, with higher point quotas.\n"
        "Add `2.0` after the abbreviation: "
        "`MH2.0` · `RB2.0` · `BW2.0` · `TBC2.0`"
    )
    e2 = discord.Embed(
        title="\U0001f4cb Available Suits",
        description="\n\n".join(suit_sections) + "\n\n" + v2_section,
        color=STATIC_COLOR,
    )

    # Embed 3: How to use ─────────────────────────────────────────────
    e3 = discord.Embed(
        title="⌨️ How to Use",
        description=(
            "Use `/calculate` to find out exactly how many more points your cog "
            "suit needs and get three activity plans that minimise time between "
            "your runs!\n\n"
            "**Step-by-step dropdown flow**\n"
            "1. Type `/calculate` — a private menu appears.\n"
            "2. **Faction** — pick Sellbot, Cashbot, Lawbot, or Bossbot.\n"
            "3. **Suit** — pick from the 8 suits for that faction.\n"
            "4. **Version** *(top-tier suits only)* — choose 1.0 or 2.0.\n"
            "5. **Level** — pick the level shown next to your suit in-game.\n"
            "6. **Points** — enter how many points you've already earned "
            "toward this level's quota (enter `0` if you just ranked up).\n\n"
            "Results appear as a private reply — feel free to use it any time, "
            "right here."
        ),
        color=STATIC_COLOR,
    )

    # Embed 4: Activity points reference ─────────────────────────────
    activity_blocks: list[str] = []
    for faction_key, acts in FACTION_ACTIVITIES.items():
        meta  = FACTION_META[faction_key]
        emoji = faction_emojis[meta["label"]]
        lines = [f"{emoji} **{meta['label']} ({meta['currency']})**"]
        lines += [f"▸ {a.name} — {a.range_str} {meta['currency']}" for a in acts]
        activity_blocks.append("\n".join(lines))
    e4 = discord.Embed(
        title="—— Approximate Points Per Activity Run ——",
        description="\n\n".join(activity_blocks),
        color=STATIC_COLOR,
    )

    return [e1, e2, e3, e4]


# ── FACTION THREAD EMBEDS ─────────────────────────────────────────────────────

_ACT_SHORT: dict[str, str] = {
    "Steel Factory — Long":     "Steel-L",
    "Steel Factory — Short":    "Steel-S",
    "Scrap Factory — Long":     "Scrap-L",
    "Scrap Factory — Short":    "Scrap-S",
    "Bullion Mint":             "Bullion",
    "Coin Mint":                "Coin",
    "DA Office — Senior Wing":  "DA-Sr",
    "DA Office — Junior Wing":  "DA-Jr",
    "The Final Fringe":         "Fringe",
    "The First Fairway":        "Fairway",
}

# Per-faction activity text for each of the 3 thread embeds (normal / disguise / 2.0).
_THREAD_ACTIVITIES: dict[str, tuple[str, str, str]] = {
    "sellbot": (
        "• **Scrap Factory — Short** (350–356 pts) — quick; great for early suits\n"
        "• **Scrap Factory — Long** (596–638 pts) — solid mid-progression option\n"
        "• **Steel Factory — Long** (1,525–1,630 pts) — best merits per run\n"
        "• **VP (Vice President)** — large merit bonus on completion",

        "• **Steel Factory — Long** (1,525–1,630 pts) — best merits per run\n"
        "• **Scrap Factory — Long** (596–638 pts) — solid alternative\n"
        "• **VP (Vice President)** — large merit bonus; do it whenever available",

        "• **Steel Factory — Long** (1,525–1,630 pts) — best merit source for 2.0\n"
        "• **VP (Vice President)** — merit bonus; prioritise when available",
    ),
    "cashbot": (
        "• **Coin Mint** (702–807 pts) — efficient for early suits\n"
        "• **Bullion Mint** (1,626–1,850 pts) — best cogbucks per run\n"
        "• **CFO (Chief Financial Officer)** — large cogbuck bonus on completion",

        "• **Bullion Mint** (1,626–1,850 pts) — best cogbucks per run\n"
        "• **Coin Mint** (702–807 pts) — efficient alternative\n"
        "• **CFO (Chief Financial Officer)** — large bonus; do it whenever available",

        "• **Bullion Mint** (1,626–1,850 pts) — best cogbuck source for 2.0\n"
        "• **CFO (Chief Financial Officer)** — bonus; prioritise when available",
    ),
    "lawbot": (
        "• **DA Office — Junior Wing** (781–889 pts) — good for early suits\n"
        "• **DA Office — Senior Wing** (1,854–2,082 pts) — best jury notices per run\n"
        "• **CJ (Chief Justice)** — large jury notice bonus on completion",

        "• **DA Office — Senior Wing** (1,854–2,082 pts) — best jury notices per run\n"
        "• **DA Office — Junior Wing** (781–889 pts) — efficient alternative\n"
        "• **CJ (Chief Justice)** — large bonus; do it whenever available",

        "• **DA Office — Senior Wing** (1,854–2,082 pts) — best jury notice source for 2.0\n"
        "• **CJ (Chief Justice)** — bonus; prioritise when available",
    ),
    "bossbot": (
        "• **The First Fairway** (882–975 pts) — good for early suits\n"
        "• **The Final Fringe** (2,097–2,305 pts) — best stock options per run\n"
        "• **CEO (Chief Executive Officer)** — large stock option bonus on completion",

        "• **The Final Fringe** (2,097–2,305 pts) — best stock options per run\n"
        "• **The First Fairway** (882–975 pts) — efficient alternative\n"
        "• **CEO (Chief Executive Officer)** — large bonus; do it whenever available",

        "• **The Final Fringe** (2,097–2,305 pts) — best stock option source for 2.0\n"
        "• **CEO (Chief Executive Officer)** — bonus; prioritise when available",
    ),
}


def build_faction_thread_embeds(faction_key: str) -> list[discord.Embed]:
    """Return [embed1, embed2, embed3] for one faction's suit-progression thread.

    embed1 — all 1.0 suits, levels 1–12 (inline fields per suit)
    embed2 — top-tier disguise, levels 13–50
    embed3 — 2.0 top-tier, levels 8–50
    """
    meta       = FACTION_META[faction_key]
    label      = meta["label"]
    currency   = meta["currency"]
    emoji      = meta["emoji"]
    color      = meta["color"]
    acts_texts = _THREAD_ACTIVITIES[faction_key]
    suits      = SUITS_BY_FACTION[label]
    activities = FACTION_ACTIVITIES[faction_key]
    best_act   = max(activities, key=lambda a: a.avg_pts)
    best_short = _ACT_SHORT.get(best_act.name, best_act.name.split()[0])

    top_abbr, top_name = suits[-1]
    _, top_chart, _    = SUITS[top_abbr]

    def _runs(quota: int) -> str:
        if quota == 0:
            return "Maxed"
        return str(max(1, math.ceil(quota / best_act.avg_pts)))

    # ── Embed 1: All 1.0 Suits (Lvl 1–12) ──────────────────────────────────
    e1 = discord.Embed(
        title=f"{emoji} {label} — 1.0 Suit Progression",
        description=(
            f"Points required to promote from each level. All suits earn **{currency}**.\n"
            f"Run counts assume starting from **0** using **{best_act.name}** "
            f"({best_act.range_str} pts/run)."
        ),
        color=color,
    )
    for abbr, name in suits:
        _, chart_key, _ = SUITS[abbr]
        level_data = QUOTAS_V1[faction_key].get(chart_key, {})
        normal_levels = {lv: pts for lv, pts in level_data.items() if lv <= 12}
        if not normal_levels:
            continue
        lines = []
        for lv in sorted(normal_levels):
            pts = normal_levels[lv]
            if pts == 0:
                lines.append(f"Lvl {lv} — Maxed")
            else:
                lines.append(
                    f"Lvl {lv} — {pts:,} {currency} — {_runs(pts)}× {best_short}"
                )
        e1.add_field(name=f"{abbr} — {name}", value="\n".join(lines), inline=True)

    e1.add_field(name="Recommended Activities", value=acts_texts[0], inline=False)
    e1.set_footer(text="Paws Pendragon TTR • Suit Progression Reference")

    # ── Embed 2: Top-Tier Disguise (Lvl 13–50) ──────────────────────────────
    top_data_v1    = QUOTAS_V1[faction_key].get(top_chart, {})
    disguise_lvls  = {lv: pts for lv, pts in top_data_v1.items() if lv >= 13}
    rows2: list[str] = []
    for lv in sorted(disguise_lvls):
        pts = disguise_lvls[lv]
        if pts == 0:
            rows2.append(f"Lvl {lv} — Maxed")
        else:
            rows2.append(
                f"Lvl {lv} — {pts:,} {currency} — {_runs(pts)}× {best_short}"
            )

    e2 = discord.Embed(
        title=f"{emoji} {label} — {top_name} Disguise (Lvl 13–50)",
        description="\n".join(rows2),
        color=color,
    )
    e2.add_field(name="Recommended Activities", value=acts_texts[1], inline=False)
    e2.set_footer(text="Paws Pendragon TTR • Suit Progression Reference")

    # ── Embed 3: 2.0 Top-Tier (Lvl 8–50) ───────────────────────────────────
    top_data_v2  = QUOTAS_V2.get(top_chart, {})
    rows3: list[str] = []
    for lv in sorted(top_data_v2):
        pts = top_data_v2[lv]
        if pts == 0:
            rows3.append(f"Lvl {lv} — Maxed")
        else:
            n = max(1, math.ceil(pts / best_act.avg_pts))
            rows3.append(
                f"Lvl {lv} — {pts:,} {currency} — {n}× {best_short}"
            )

    e3 = discord.Embed(
        title=f"{emoji} {label} — 2.0 {top_name} (Lvl 8–50)",
        description="\n".join(rows3),
        color=color,
    )
    e3.add_field(name="Recommended Activities", value=acts_texts[2], inline=False)
    e3.set_footer(text="Paws Pendragon TTR • Suit Progression Reference")

    return [e1, e2, e3]


# ── DROPDOWN CALCULATE FLOW ───────────────────────────────────────────────────

class _CalcView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=120)


class _FactionSelect(discord.ui.Select):
    def __init__(self) -> None:
        options = [
            discord.SelectOption(label="Sellbot", value="sellbot", emoji="\U0001f4bc"),
            discord.SelectOption(label="Cashbot", value="cashbot", emoji="\U0001f4b0"),
            discord.SelectOption(label="Lawbot",  value="lawbot",  emoji="⚖️"),
            discord.SelectOption(label="Bossbot", value="bossbot", emoji="\U0001f454"),
        ]
        super().__init__(placeholder="① Faction…", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        faction = self.values[0]
        view = _CalcView()
        view.add_item(_SuitSelect(faction))
        await interaction.response.edit_message(
            content=f"**{faction.capitalize()}** › Choose a suit:", view=view
        )


class _SuitSelect(discord.ui.Select):
    def __init__(self, faction: str) -> None:
        self.faction = faction
        suits = SUITS_BY_FACTION[faction.capitalize()]
        options = [discord.SelectOption(label=name, value=abbr) for abbr, name in suits]
        super().__init__(placeholder="② Suit…", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        abbr = self.values[0]
        _, _, suit_name = SUITS[abbr]
        if abbr in _V2_SUITS:
            view = _CalcView()
            view.add_item(_VersionSelect(abbr, suit_name, self.faction))
            await interaction.response.edit_message(
                content=f"**{suit_name}** › Normal or 2.0?", view=view
            )
        else:
            await interaction.response.show_modal(
                _LevelModal(abbr, suit_name, self.faction, False)
            )


class _VersionSelect(discord.ui.Select):
    def __init__(self, abbr: str, suit_name: str, faction: str) -> None:
        self.abbr      = abbr
        self.suit_name = suit_name
        self.faction   = faction
        options = [
            discord.SelectOption(label="1.0  —  Normal",   value="1"),
            discord.SelectOption(label="2.0  —  Upgraded", value="2"),
        ]
        super().__init__(placeholder="③ Version…", options=options)

    async def callback(self, interaction: discord.Interaction) -> None:
        is_v2 = self.values[0] == "2"
        await interaction.response.show_modal(
            _LevelModal(self.abbr, self.suit_name, self.faction, is_v2)
        )


class _LevelModal(discord.ui.Modal, title="Choose Level"):
    level_input = discord.ui.TextInput(
        label="Level number",
        placeholder="e.g. 5",
        min_length=1,
        max_length=2,
    )

    def __init__(self, abbr: str, suit_name: str, faction: str, is_v2: bool) -> None:
        super().__init__()
        self.abbr      = abbr
        self.suit_name = suit_name
        self.faction   = faction
        self.is_v2     = is_v2
        _, self.chart_key, _ = SUITS[abbr]

    async def on_submit(self, interaction: discord.Interaction) -> None:
        try:
            level_num = int(self.level_input.value.strip())
        except ValueError:
            await interaction.response.send_message(
                "❌ Please enter a valid level number (e.g. 5).",
                ephemeral=True,
            )
            return

        lo, hi = valid_level_range(self.abbr, self.faction, self.chart_key, self.is_v2)
        if not (lo <= level_num <= hi):
            await interaction.response.send_message(
                f"❌ Invalid level. **{self.suit_name}** levels range from {lo} to {hi}.",
                ephemeral=True,
            )
            return

        quota = get_quota(self.abbr, self.faction, self.chart_key, level_num, self.is_v2)
        if quota is None:
            await interaction.response.send_message(
                f"❌ Level {level_num} is not available.",
                ephemeral=True,
            )
            return

        if quota == 0:
            v2_tag = " 2.0" if self.is_v2 else ""
            await interaction.response.send_message(
                content=(
                    f"\U0001f43e **{self.suit_name}{v2_tag}** at level {level_num} "
                    "is **Maxed** — nothing left to earn! Use **/calculate** to try another suit."
                ),
                view=_RestartView(),
            )
            return

        await interaction.response.send_modal(
            _PointsModal(self.abbr, self.suit_name, self.faction, level_num, self.is_v2, quota)
        )


class _RestartView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=120)

    @discord.ui.button(label="Calculate Again", style=discord.ButtonStyle.primary, emoji="🔄")
    async def restart(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        view = _CalcView()
        view.add_item(_FactionSelect())
        await interaction.response.edit_message(
            content="Choose your cog suit faction:",
            embed=None,
            view=view,
        )


class _PointsModal(discord.ui.Modal):
    points_input = discord.ui.TextInput(
        label="Points already earned toward this level",
        placeholder="e.g. 3000   (enter 0 if you just ranked up)",
        min_length=1,
        max_length=7,
    )

    def __init__(
        self, abbr: str, suit_name: str, faction: str,
        level_num: int, is_v2: bool, quota: int,
    ) -> None:
        v2_tag = " 2.0" if is_v2 else ""
        super().__init__(title=f"{suit_name}{v2_tag} — Level {level_num}")
        self.abbr      = abbr
        self.suit_name = suit_name
        self.faction   = faction
        self.level_num = level_num
        self.is_v2     = is_v2
        self.quota     = quota

    async def on_submit(self, interaction: discord.Interaction) -> None:
        raw = self.points_input.value.replace(",", "").strip()
        try:
            current_pts = int(raw)
        except ValueError:
            await interaction.response.edit_message(
                content="❌ Enter a whole number for current points.", view=None
            )
            return
        if current_pts < 0:
            await interaction.response.edit_message(
                content="❌ Current points can't be negative.", view=None
            )
            return

        meta = FACTION_META[self.faction]
        if current_pts >= self.quota:
            await interaction.response.edit_message(
                content=(
                    f"✅ You already have enough to promote!\n"
                    f"**{current_pts:,}** / **{self.quota:,}** {meta['currency']} — "
                    "ready to rank up. \U0001f43e"
                ),
                embed=None,
                view=_RestartView(),
            )
            return

        pts_remaining = self.quota - current_pts
        options = build_options(pts_remaining, FACTION_ACTIVITIES[self.faction])
        embed   = build_result_embed(
            self.suit_name, self.faction, self.level_num,
            current_pts, self.quota, self.is_v2, options,
        )
        await interaction.response.edit_message(content=None, embed=embed, view=_RestartView())


# ── COMMAND REGISTRATION ──────────────────────────────────────────────────────

def register_calculate(bot) -> None:

    @bot.tree.command(
        name="calculate",
        description="[User Command] Calculate remaining suit points and get 3 optimised activity plans.",
    )
    @app_commands.allowed_installs(guilds=True, users=True)
    @app_commands.allowed_contexts(guilds=True, dms=True, private_channels=True)
    async def calculate(interaction: discord.Interaction) -> None:
        view = _CalcView()
        view.add_item(_FactionSelect())
        await interaction.response.send_message(
            "Choose your cog suit faction:", view=view, ephemeral=True
        )
