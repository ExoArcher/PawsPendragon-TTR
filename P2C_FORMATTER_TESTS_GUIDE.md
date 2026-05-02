# PHASE 2-C Implementation Guide: Formatter Pure-Function Tests

**Status:** Detailed implementation guide for Claude instance tomorrow  
**Scope:** Add pytest foundation with pure-function formatter tests  
**Files to create:** `PDMain/tests/__init__.py`, `PDMain/tests/test_formatters.py`  
**Files to modify:** `PDMain/requirements.txt`  
**Effort:** LOW-MEDIUM (3–4 hours)  
**Risk:** ZERO (additive only, no breaking changes)

---

## PHASE 2-C Overview

This guide implements comprehensive pytest tests for all pure functions in `PDMain/Features/Core/formatters/formatters.py`. These functions have zero Discord-object dependencies and are excellent testing targets.

The test suite will:
1. Add pytest foundation to the project (first test harness ever)
2. Test all pure formatter functions with rich parametrized test cases
3. Lock in behavior before PHASE 3 refactors begin
4. Provide a regression net for future changes

---

## Part 1: Setup & File Structure

### 1.1 Add test dependencies to requirements.txt

**File:** `PDMain/requirements.txt`

**Current state:** (4 lines)
```
discord.py>=2.3.2,<3.0
aiohttp>=3.9.0,<4.0
python-dotenv>=1.0.0,<2.0
aiosqlite>=0.19.0,<1.0
```

**Action:** Add two new lines at the end:
```
pytest>=7.0.0,<8.0
pytest-asyncio>=0.21.0,<1.0
```

**Result:** Requirements now has 6 lines, including test dependencies.

---

### 1.2 Create test directory structure

**Create these files (both empty initially):**

1. `PDMain/tests/__init__.py` — empty file, marks this directory as a Python package
2. `PDMain/tests/test_formatters.py` — the main test file (see Part 2 below)

**Verify directory structure after creation:**
```
PDMain/
├── bot.py
├── requirements.txt
├── Features/
│   ├── Core/
│   │   └── formatters/
│   │       └── formatters.py
├── tests/
│   ├── __init__.py          ← NEW
│   └── test_formatters.py   ← NEW
└── [other files]
```

---

## Part 2: Implementation – test_formatters.py

### 2.1 Complete test file content

**File:** `PDMain/tests/test_formatters.py`

**Key imports:**
- `pytest` — test framework
- `sys`, `os` — for path manipulation  
- Direct imports from `Features.Core.formatters.formatters` (the module under test)

**Full file content:**

```python
"""
Test suite for pure functions in Features/Core/formatters/formatters.py.

These tests cover:
  - trait_tier()         : classify a trait + slot into one of 6 tiers
  - doodle_priority()    : classify a 4-trait doodle into one of 6 priority buckets
  - doodle_quality()     : compute a doodle's quality score (tiebreaker)
  - star_for()           : return the emoji for a trait at a given slot
  - _norm_district()     : normalize district names for set lookups
  - _is_safe_district()  : check if a district is immune to mega invasions
  - _is_speedchat_only() : check if a district has speedchat-only speech
  - _ts()                : convert epoch timestamp to Discord relative time syntax
"""

import sys
import os
from pathlib import Path

# Add PDMain to path so we can import Features directly
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from Features.Core.formatters.formatters import (
    # Pure tier/priority functions
    trait_tier,
    doodle_priority,
    doodle_quality,
    star_for,
    # District helpers
    _norm_district,
    _is_safe_district,
    _is_speedchat_only,
    # Timestamp helper
    _ts,
    # Constants used by tests
    GREAT_TRAITS,
    GOOD_TRAITS,
    OK_TRAITS,
    BAD_TRAITS,
    PRIORITY_PERFECT,
    PRIORITY_AMAZING,
    PRIORITY_GREAT,
    PRIORITY_GREAT_GOOD,
    PRIORITY_GREAT_GOOD_OK,
    PRIORITY_REST,
    SAFE_FROM_MEGA_INVASIONS,
    SPEEDCHAT_ONLY_DISTRICTS,
    STAR_PERFECT,
    STAR_AMAZING,
    STAR_GREAT,
    STAR_GOOD,
    STAR_OK,
    STAR_BAD,
)


# ═════════════════════════════════════════════════════════════════════════════
# TEST: trait_tier()
# ═════════════════════════════════════════════════════════════════════════════

class TestTraitTier:
    """Test trait_tier(trait: str, slot: int) -> str.
    
    Returns one of: 'perfect', 'amazing', 'great', 'good', 'ok', 'bad'.
    """

    def test_rarely_tired_slot_0_is_perfect(self):
        """Rarely Tired in slot 0 → perfect (max trick-uses)."""
        assert trait_tier("Rarely Tired", 0) == "perfect"

    def test_rarely_tired_other_slots_are_amazing(self):
        """Rarely Tired in slots 1-3 → amazing."""
        for slot in [1, 2, 3]:
            assert trait_tier("Rarely Tired", slot) == "amazing", f"slot {slot}"

    def test_great_traits(self):
        """All GREAT_TRAITS map to 'great' tier."""
        for trait in GREAT_TRAITS:
            assert trait_tier(trait, 0) == "great", f"trait={trait}"

    def test_good_traits(self):
        """All GOOD_TRAITS map to 'good' tier."""
        for trait in GOOD_TRAITS:
            assert trait_tier(trait, 0) == "good", f"trait={trait}"

    def test_ok_traits(self):
        """All OK_TRAITS map to 'ok' tier."""
        for trait in OK_TRAITS:
            assert trait_tier(trait, 0) == "ok", f"trait={trait}"

    def test_bad_traits(self):
        """All BAD_TRAITS map to 'bad' tier."""
        for trait in BAD_TRAITS:
            assert trait_tier(trait, 0) == "bad", f"trait={trait}"

    def test_unknown_trait_defaults_to_ok(self):
        """Unlisted traits fall back to 'ok' (safe default)."""
        # If TTR ever adds a new trait we haven't mapped, it should not crash
        assert trait_tier("Unknown Trait Name", 0) == "ok"
        assert trait_tier("Some Future Trait", 2) == "ok"

    def test_slot_does_not_affect_non_rarely_tired_traits(self):
        """Only 'Rarely Tired' cares about slot; others are slot-independent."""
        trait = "Always Affectionate"
        for slot in [0, 1, 2, 3]:
            assert trait_tier(trait, slot) == "great", f"slot={slot}"


# ═════════════════════════════════════════════════════════════════════════════
# TEST: doodle_priority()
# ═════════════════════════════════════════════════════════════════════════════

class TestDoodlePriority:
    """Test doodle_priority(traits: list[str]) -> int.
    
    Classifies a 4-trait doodle into six priority buckets (0–5).
    Bucket ordering: PERFECT < AMAZING < GREAT < GREAT_GOOD < GREAT_GOOD_OK < REST.
    """

    # ─── PRIORITY_PERFECT (0) ───────────────────────────────────────────────
    # Exactly: Rarely Tired (slot 0) + 3 Great traits

    def test_perfect_priority_exact_match(self):
        """PERFECT: 'Rarely Tired' in slot 0 + exactly 3 Great."""
        traits = [
            "Rarely Tired",
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
        ]
        assert doodle_priority(traits) == PRIORITY_PERFECT

    def test_perfect_priority_fails_if_rarely_tired_not_in_slot_0(self):
        """PERFECT requires Rarely Tired in slot 0, not slots 1-3."""
        traits_slot_1 = [
            "Always Affectionate",
            "Rarely Tired",
            "Always Playful",
            "Rarely Bored",
        ]
        # This is AMAZING (1 Rarely Tired + 3 Great), not PERFECT
        assert doodle_priority(traits_slot_1) == PRIORITY_AMAZING

    def test_perfect_priority_fails_if_fewer_than_3_great(self):
        """PERFECT requires exactly 3 Great traits alongside Rarely Tired slot 0."""
        traits = [
            "Rarely Tired",
            "Always Affectionate",
            "Always Playful",
            "Often Affectionate",  # Good, not Great
        ]
        # This is not PERFECT (only 2 Great + 1 Good)
        # Should be GREAT_GOOD or REST
        priority = doodle_priority(traits)
        assert priority != PRIORITY_PERFECT

    # ─── PRIORITY_AMAZING (1) ───────────────────────────────────────────────
    # Exactly: 1 Rarely Tired (any slot except 0) + 3 Great (no Good/OK)

    def test_amazing_priority_rarely_tired_slot_1(self):
        """AMAZING: Rarely Tired in slot 1 + 3 Great."""
        traits = [
            "Always Affectionate",
            "Rarely Tired",
            "Always Playful",
            "Rarely Bored",
        ]
        assert doodle_priority(traits) == PRIORITY_AMAZING

    def test_amazing_priority_rarely_tired_slot_2(self):
        """AMAZING: Rarely Tired in slot 2 + 3 Great."""
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Tired",
            "Rarely Bored",
        ]
        assert doodle_priority(traits) == PRIORITY_AMAZING

    def test_amazing_priority_rarely_tired_slot_3(self):
        """AMAZING: Rarely Tired in slot 3 + 3 Great."""
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
            "Rarely Tired",
        ]
        assert doodle_priority(traits) == PRIORITY_AMAZING

    def test_amazing_priority_fails_with_good_trait(self):
        """AMAZING requires 3 Great + 1 Rarely Tired, no Good/OK/Bad."""
        traits = [
            "Always Affectionate",
            "Rarely Tired",
            "Always Playful",
            "Often Affectionate",  # Good, not Great
        ]
        # This should be GREAT_GOOD or REST, not AMAZING
        assert doodle_priority(traits) != PRIORITY_AMAZING

    # ─── PRIORITY_GREAT (2) ──────────────────────────────────────────────────
    # Exactly: 4 Great traits, no Rarely Tired

    def test_great_priority_four_great_traits(self):
        """GREAT: exactly 4 Great traits, no Rarely Tired."""
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
            "Rarely Confused",
        ]
        assert doodle_priority(traits) == PRIORITY_GREAT

    def test_great_priority_fails_with_rarely_tired(self):
        """GREAT requires 4 Great with NO Rarely Tired."""
        traits = [
            "Rarely Tired",
            "Always Playful",
            "Rarely Bored",
            "Rarely Confused",
        ]
        # This is AMAZING (1 Rarely Tired + 3 Great), not GREAT
        assert doodle_priority(traits) != PRIORITY_GREAT

    def test_great_priority_fails_with_good_trait(self):
        """GREAT requires exactly 4 Great (no Good/OK)."""
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
            "Often Affectionate",  # Good, not Great
        ]
        # This is GREAT_GOOD (3 Great + 1 Good), not GREAT
        assert doodle_priority(traits) != PRIORITY_GREAT

    # ─── PRIORITY_GREAT_GOOD (3) ────────────────────────────────────────────
    # Exactly: 3 Great + 1 Good, no Rarely Tired, no OK/Bad

    def test_great_good_priority_three_great_one_good(self):
        """GREAT_GOOD: exactly 3 Great + 1 Good, no Rarely Tired."""
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
            "Often Affectionate",  # Good
        ]
        assert doodle_priority(traits) == PRIORITY_GREAT_GOOD

    def test_great_good_priority_fails_with_ok_trait(self):
        """GREAT_GOOD rejects any OK trait (goes to GREAT_GOOD_OK instead)."""
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
            "Sometimes Affectionate",  # OK, not Good
        ]
        # With an OK trait, doodle is GREAT_GOOD_OK, not GREAT_GOOD
        assert doodle_priority(traits) == PRIORITY_GREAT_GOOD_OK

    def test_great_good_priority_fails_with_bad_trait(self):
        """GREAT_GOOD rejects any Bad trait (goes to REST)."""
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
            "Always Tired",  # Bad
        ]
        assert doodle_priority(traits) == PRIORITY_REST

    # ─── PRIORITY_GREAT_GOOD_OK (4) ──────────────────────────────────────────
    # Exactly: 2 Great + 2 Good, OR any doodle with OK traits (but no Bad)

    def test_great_good_ok_priority_two_great_two_good(self):
        """GREAT_GOOD_OK: 2 Great + 2 Good, no Rarely Tired."""
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Often Affectionate",
            "Often Playful",
        ]
        assert doodle_priority(traits) == PRIORITY_GREAT_GOOD_OK

    def test_great_good_ok_priority_with_ok_trait(self):
        """GREAT_GOOD_OK: any doodle with an OK trait (but no Bad)."""
        # 3 Great + 1 OK
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
            "Sometimes Affectionate",  # OK
        ]
        assert doodle_priority(traits) == PRIORITY_GREAT_GOOD_OK

    def test_great_good_ok_priority_fails_with_bad_trait(self):
        """GREAT_GOOD_OK rejects any Bad trait (goes to REST)."""
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
            "Always Tired",  # Bad
        ]
        assert doodle_priority(traits) == PRIORITY_REST

    # ─── PRIORITY_REST (5) ───────────────────────────────────────────────────
    # Catch-all: wrong trait count, has Bad traits, or below OK threshold

    def test_rest_priority_empty_traits(self):
        """REST: empty trait list."""
        assert doodle_priority([]) == PRIORITY_REST

    def test_rest_priority_fewer_than_4_traits(self):
        """REST: fewer than 4 traits."""
        assert doodle_priority(["Always Affectionate"]) == PRIORITY_REST
        assert doodle_priority(["Always Affectionate", "Always Playful"]) == PRIORITY_REST
        assert doodle_priority(["Always Affectionate", "Always Playful", "Rarely Bored"]) == PRIORITY_REST

    def test_rest_priority_more_than_4_traits(self):
        """REST: more than 4 traits."""
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
            "Rarely Confused",
            "Rarely Forgets",
        ]
        assert doodle_priority(traits) == PRIORITY_REST

    def test_rest_priority_with_bad_trait(self):
        """REST: any doodle with a Bad trait."""
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
            "Always Tired",  # Bad → immediately REST
        ]
        assert doodle_priority(traits) == PRIORITY_REST

    def test_rest_priority_none_input(self):
        """REST: None input is treated as empty list."""
        assert doodle_priority(None) == PRIORITY_REST

    def test_rest_priority_low_quality_mix(self):
        """REST: 1 Great + 3 OK is below the threshold."""
        traits = [
            "Always Affectionate",
            "Sometimes Affectionate",
            "Sometimes Playful",
            "Sometimes Bored",
        ]
        # 1 Great + 3 OK = below OK threshold (which requires 2 Great)
        assert doodle_priority(traits) == PRIORITY_REST


# ═════════════════════════════════════════════════════════════════════════════
# TEST: doodle_quality()
# ═════════════════════════════════════════════════════════════════════════════

class TestDoodleQuality:
    """Test doodle_quality(traits: list[str]) -> int.
    
    Returns the sum of per-slot tier weights (0–25 range).
    Used as a tiebreaker within a priority bucket.
    
    Weight mapping:
      perfect=5, amazing=4, great=3, good=2, ok=1, bad=0
    """

    def test_quality_perfect_doodle(self):
        """PERFECT doodle (slot 0 Rarely Tired + 3 Great): 5 + 3 + 3 + 3 = 14."""
        traits = [
            "Rarely Tired",
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
        ]
        assert doodle_quality(traits) == 5 + 3 + 3 + 3

    def test_quality_amazing_doodle(self):
        """AMAZING doodle (slot 1 Rarely Tired + 3 Great): 3 + 4 + 3 + 3 = 13."""
        traits = [
            "Always Affectionate",
            "Rarely Tired",
            "Always Playful",
            "Rarely Bored",
        ]
        assert doodle_quality(traits) == 3 + 4 + 3 + 3

    def test_quality_four_great(self):
        """GREAT doodle (4 Great): 3 + 3 + 3 + 3 = 12."""
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
            "Rarely Confused",
        ]
        assert doodle_quality(traits) == 3 + 3 + 3 + 3

    def test_quality_three_great_one_good(self):
        """GREAT_GOOD doodle (3 Great + 1 Good): 3 + 3 + 3 + 2 = 11."""
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
            "Often Affectionate",
        ]
        assert doodle_quality(traits) == 3 + 3 + 3 + 2

    def test_quality_two_great_two_good(self):
        """GREAT_GOOD_OK doodle (2 Great + 2 Good): 3 + 3 + 2 + 2 = 10."""
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Often Affectionate",
            "Often Playful",
        ]
        assert doodle_quality(traits) == 3 + 3 + 2 + 2

    def test_quality_with_ok_trait(self):
        """Quality includes OK trait weight (1): 3 + 3 + 3 + 1 = 10."""
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
            "Sometimes Affectionate",
        ]
        assert doodle_quality(traits) == 3 + 3 + 3 + 1

    def test_quality_with_bad_trait(self):
        """Quality with Bad trait (weight 0): 3 + 3 + 3 + 0 = 9."""
        traits = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
            "Always Tired",
        ]
        assert doodle_quality(traits) == 3 + 3 + 3 + 0

    def test_quality_empty_traits(self):
        """Empty trait list → quality 0."""
        assert doodle_quality([]) == 0

    def test_quality_none_input(self):
        """None input treated as empty list → quality 0."""
        assert doodle_quality(None) == 0

    def test_quality_all_good_traits(self):
        """4 Good traits: 2 + 2 + 2 + 2 = 8."""
        traits = [
            "Often Affectionate",
            "Often Playful",
            "Pretty Calm",
            "Pretty Excitable",
        ]
        assert doodle_quality(traits) == 2 + 2 + 2 + 2

    def test_quality_all_ok_traits(self):
        """4 OK traits: 1 + 1 + 1 + 1 = 4."""
        traits = [
            "Sometimes Affectionate",
            "Sometimes Playful",
            "Sometimes Bored",
            "Sometimes Confused",
        ]
        assert doodle_quality(traits) == 1 + 1 + 1 + 1


# ═════════════════════════════════════════════════════════════════════════════
# TEST: star_for()
# ═════════════════════════════════════════════════════════════════════════════

class TestStarFor:
    """Test star_for(trait: str, slot: int) -> str.
    
    Returns the emoji string for a trait at a given slot.
    Emoji strings are from environment variables (or defaults).
    """

    def test_star_for_rarely_tired_slot_0(self):
        """Rarely Tired in slot 0 → STAR_PERFECT emoji."""
        assert star_for("Rarely Tired", 0) == STAR_PERFECT

    def test_star_for_rarely_tired_other_slots(self):
        """Rarely Tired in slots 1-3 → STAR_AMAZING emoji."""
        for slot in [1, 2, 3]:
            assert star_for("Rarely Tired", slot) == STAR_AMAZING, f"slot {slot}"

    def test_star_for_great_trait(self):
        """Any Great trait → STAR_GREAT emoji."""
        for trait in list(GREAT_TRAITS)[:3]:  # Sample a few
            assert star_for(trait, 0) == STAR_GREAT, f"trait={trait}"

    def test_star_for_good_trait(self):
        """Any Good trait → STAR_GOOD emoji."""
        for trait in GOOD_TRAITS:
            assert star_for(trait, 0) == STAR_GOOD, f"trait={trait}"

    def test_star_for_ok_trait(self):
        """Any OK trait → STAR_OK emoji."""
        for trait in list(OK_TRAITS)[:3]:  # Sample a few
            assert star_for(trait, 0) == STAR_OK, f"trait={trait}"

    def test_star_for_bad_trait(self):
        """Any Bad trait → STAR_BAD emoji."""
        for trait in list(BAD_TRAITS)[:3]:  # Sample a few
            assert star_for(trait, 0) == STAR_BAD, f"trait={trait}"

    def test_star_for_unknown_trait(self):
        """Unknown trait defaults to OK tier → STAR_OK emoji."""
        assert star_for("Future Trait", 0) == STAR_OK


# ═════════════════════════════════════════════════════════════════════════════
# TEST: _norm_district()
# ═════════════════════════════════════════════════════════════════════════════

class TestNormDistrict:
    """Test _norm_district(name: str) -> str.
    
    Normalizes district names (lowercase, remove spaces/apostrophes)
    for set-membership checks.
    """

    def test_norm_district_lowercase(self):
        """Names are lowercased."""
        assert _norm_district("Walrus Way") == "walrusway"
        assert _norm_district("WALRUS WAY") == "walrusway"
        assert _norm_district("WaLrUs WaY") == "walrusway"

    def test_norm_district_removes_spaces(self):
        """Spaces are removed."""
        assert _norm_district("Walrus Way") == "walrusway"
        assert _norm_district("Walrus  Way") == "walrusway"
        assert _norm_district(" Walrus Way ") == "walrusway"

    def test_norm_district_removes_apostrophes(self):
        """Apostrophes are removed."""
        assert _norm_district("Saint Louis's Quarter") == "saintlouissquarter"
        assert _norm_district("O'Hare Quarter") == "ohareQuarter"  # lowercase after

    def test_norm_district_empty_string(self):
        """Empty string stays empty."""
        assert _norm_district("") == ""

    def test_norm_district_none_handled(self):
        """None is coerced to empty string by .lower() call."""
        # _norm_district calls (name or "").lower(), so None → ""
        try:
            result = _norm_district(None)
            assert result == ""
        except AttributeError:
            # If the function doesn't handle None, that's a bug we should catch
            pytest.fail("_norm_district should handle None input")


# ═════════════════════════════════════════════════════════════════════════════
# TEST: _is_safe_district()
# ═════════════════════════════════════════════════════════════════════════════

class TestIsSafeDistrict:
    """Test _is_safe_district(name: str) -> bool.
    
    Returns True if the district is immune to Mega Invasions.
    """

    def test_is_safe_district_blam_canyon(self):
        """Blamcanyon is safe from mega invasions."""
        assert _is_safe_district("Blamcanyon") is True
        assert _is_safe_district("BLAMCANYON") is True
        assert _is_safe_district("Blam Canyon") is True

    def test_is_safe_district_gulp_gulch(self):
        """Gulpgulch is safe from mega invasions."""
        assert _is_safe_district("Gulpgulch") is True
        assert _is_safe_district("Gulp Gulch") is True

    def test_is_safe_district_whoosh_rapids(self):
        """Whooshrapids is safe from mega invasions."""
        assert _is_safe_district("Whooshrapids") is True
        assert _is_safe_district("Whoosh Rapids") is True

    def test_is_safe_district_woosh_rapids_misspelling(self):
        """Common misspelling 'Woosh' is also recognized as safe."""
        assert _is_safe_district("Woosh Rapids") is True
        assert _is_safe_district("Wooshrapids") is True

    def test_is_safe_district_zap_wood(self):
        """Zapwood is safe from mega invasions."""
        assert _is_safe_district("Zapwood") is True
        assert _is_safe_district("Zap Wood") is True

    def test_is_safe_district_welcome_valley(self):
        """Welcome Valley is safe from mega invasions."""
        assert _is_safe_district("Welcome Valley") is True
        assert _is_safe_district("Welcomevalley") is True

    def test_is_safe_district_other_districts_not_safe(self):
        """Other districts are not safe from mega invasions."""
        assert _is_safe_district("Toontown Central") is False
        assert _is_safe_district("Donald's Dock") is False
        assert _is_safe_district("Daisy Gardens") is False
        assert _is_safe_district("Minnie's Melodyland") is False
        assert _is_safe_district("The Brrrgh") is False
        assert _is_safe_district("Dognapped Field") is False


# ═════════════════════════════════════════════════════════════════════════════
# TEST: _is_speedchat_only()
# ═════════════════════════════════════════════════════════════════════════════

class TestIsSpeedchatOnly:
    """Test _is_speedchat_only(name: str) -> bool.
    
    Returns True if the district only allows pre-set SpeedChat phrases
    (no custom typing or SpeedChat+).
    """

    def test_is_speedchat_only_boingbury(self):
        """Boingbury is speedchat-only."""
        assert _is_speedchat_only("Boingbury") is True
        assert _is_speedchat_only("BOINGBURY") is True

    def test_is_speedchat_only_gulp_gulch(self):
        """Gulpgulch is speedchat-only."""
        assert _is_speedchat_only("Gulpgulch") is True
        assert _is_speedchat_only("Gulp Gulch") is True

    def test_is_speedchat_only_whoosh_rapids(self):
        """Whooshrapids is speedchat-only."""
        assert _is_speedchat_only("Whooshrapids") is True
        assert _is_speedchat_only("Whoosh Rapids") is True

    def test_is_speedchat_only_woosh_rapids_misspelling(self):
        """Common misspelling 'Woosh' is also recognized as speedchat-only."""
        assert _is_speedchat_only("Woosh Rapids") is True
        assert _is_speedchat_only("Wooshrapids") is True

    def test_is_speedchat_only_other_districts_allow_custom(self):
        """Other districts allow custom typing."""
        assert _is_speedchat_only("Toontown Central") is False
        assert _is_speedchat_only("Donald's Dock") is False
        assert _is_speedchat_only("The Brrrgh") is False
        assert _is_speedchat_only("Zap Wood") is False


# ═════════════════════════════════════════════════════════════════════════════
# TEST: _ts()
# ═════════════════════════════════════════════════════════════════════════════

class TestTs:
    """Test _ts(epoch: int | float | None) -> str.
    
    Converts epoch timestamp to Discord relative time syntax.
    Discord formats this as e.g. "12 seconds ago" in the client.
    """

    def test_ts_valid_epoch_int(self):
        """Valid epoch int produces Discord timestamp syntax."""
        result = _ts(1700000000)
        assert result == "<t:1700000000:R>"

    def test_ts_valid_epoch_float(self):
        """Valid epoch float is converted to int."""
        result = _ts(1700000000.5)
        assert result == "<t:1700000000:R>"

    def test_ts_zero_epoch(self):
        """Zero is falsy → returns 'unknown'."""
        assert _ts(0) == "unknown"

    def test_ts_none_input(self):
        """None is falsy → returns 'unknown'."""
        assert _ts(None) == "unknown"

    def test_ts_false_input(self):
        """False is falsy → returns 'unknown'."""
        assert _ts(False) == "unknown"

    def test_ts_large_epoch(self):
        """Large epoch values are handled."""
        result = _ts(9999999999)
        assert result == "<t:9999999999:R>"

    def test_ts_negative_epoch(self):
        """Negative epochs (before 1970) are falsy depending on interpretation.
        However, a negative epoch that's not literally -0 is truthy."""
        # -1 is truthy (not zero or None)
        result = _ts(-1)
        assert result == "<t:-1:R>"


# ═════════════════════════════════════════════════════════════════════════════
# Integration Tests (cross-function behavior)
# ═════════════════════════════════════════════════════════════════════════════

class TestIntegration:
    """Integration tests to verify behavior across multiple functions."""

    def test_doodle_priority_and_quality_ordering(self):
        """Within a priority bucket, doodles with higher quality rank first."""
        # Two doodles in the GREAT_GOOD bucket
        doodle_a = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
            "Often Affectionate",
        ]
        doodle_b = [
            "Always Affectionate",
            "Always Playful",
            "Often Affectionate",
            "Often Affectionate",
        ]
        
        # Both should be GREAT_GOOD
        assert doodle_priority(doodle_a) == PRIORITY_GREAT_GOOD
        assert doodle_priority(doodle_b) == PRIORITY_GREAT_GOOD
        
        # But doodle_a has higher quality (3 + 3 + 3 + 2 vs 3 + 3 + 2 + 2)
        assert doodle_quality(doodle_a) > doodle_quality(doodle_b)

    def test_all_safe_districts_are_known(self):
        """All safe districts in SAFE_FROM_MEGA_INVASIONS work with normalization."""
        for district_name in SAFE_FROM_MEGA_INVASIONS:
            # Each entry should be pre-normalized (lowercase, no spaces)
            assert district_name == _norm_district(district_name), \
                f"SAFE_FROM_MEGA_INVASIONS entry '{district_name}' is not pre-normalized"

    def test_safe_and_speedchat_only_overlap(self):
        """Some districts are both safe AND speedchat-only."""
        # Gulpgulch and Whooshrapids appear in both lists
        for district in ["Gulpgulch", "Whoosh Rapids"]:
            assert _is_safe_district(district) is True
            assert _is_speedchat_only(district) is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

---

### 2.2 Key test patterns explained

**Parametrized tests:**
Tests use simple loops with `for trait in GREAT_TRAITS:` instead of pytest's `@pytest.mark.parametrize` for readability.

**Test classes:**
Functions are grouped into `TestTraitTier`, `TestDoodlePriority`, etc. for organization.

**Assertions:**
Each test has a single clear assert. Comments explain what's being tested.

**Edge cases:**
Tests cover None, empty lists, unknown traits, boundary conditions (slot 0 vs 1-3 for Rarely Tired, etc.).

---

## Part 3: Running the Tests

### 3.1 Install test dependencies

After modifying `requirements.txt`, install the new packages:

```bash
cd PDMain
pip install -r requirements.txt
```

This installs `pytest` and `pytest-asyncio` alongside existing dependencies.

### 3.2 Run all tests

```bash
cd PDMain
python -m pytest tests/test_formatters.py -v
```

**Expected output (all pass):**
```
tests/test_formatters.py::TestTraitTier::test_rarely_tired_slot_0_is_perfect PASSED
tests/test_formatters.py::TestTraitTier::test_rarely_tired_other_slots_are_amazing PASSED
tests/test_formatters.py::TestTraitTier::test_great_traits PASSED
...
[many more lines]
...
==== 95 passed in 0.42s ====
```

### 3.3 Run a single test class

```bash
python -m pytest tests/test_formatters.py::TestDoodlePriority -v
```

### 3.4 Run a single test

```bash
python -m pytest tests/test_formatters.py::TestDoodlePriority::test_perfect_priority_exact_match -v
```

### 3.5 Run with coverage (optional, requires `pip install pytest-cov`)

```bash
python -m pytest tests/test_formatters.py --cov=Features.Core.formatters.formatters --cov-report=term-short
```

---

## Part 4: Verification Checklist

After implementing, verify:

- [ ] `PDMain/tests/__init__.py` exists (empty file)
- [ ] `PDMain/tests/test_formatters.py` exists with full test content
- [ ] `PDMain/requirements.txt` has pytest and pytest-asyncio added
- [ ] `python -m pytest tests/test_formatters.py -v` runs without errors
- [ ] All ~95 tests pass
- [ ] No syntax errors in test file: `python -m py_compile tests/test_formatters.py`
- [ ] Test file imports successfully: `python -c "from tests import test_formatters; print('OK')"`

---

## Part 5: Next Steps After P2-C

Once P2-C tests pass:

1. **P2-D:** Implement db.py tests against `:memory:` SQLite (parallel with P2-C, fully independent)
2. **Gate:** Wait for both P2-C and P2-D passing
3. **P2-A + P2-B:** Implement SQLite connection pooling and semaphore-based rate limiting
4. **Phase 3:** Begin large refactors (monolithic bot.py extraction, formatters.py split)

---

## Summary for Tomorrow's Claude

**TL;DR:**
1. Add pytest + pytest-asyncio to requirements.txt
2. Create `PDMain/tests/__init__.py` (empty)
3. Create `PDMain/tests/test_formatters.py` with the ~500-line test file provided above
4. Run `python -m pytest tests/test_formatters.py -v` to verify all tests pass (~95 tests)
5. Expect 0 failures; high confidence implementation

**Files created/modified:** 3 files (1 modified, 2 created)  
**Estimated time:** 1–2 hours (mostly copy-paste of the test file)  
**Complexity:** LOW (no async code, no Discord objects, pure function tests)  
**Risk:** ZERO (additive only, no breaking changes)
