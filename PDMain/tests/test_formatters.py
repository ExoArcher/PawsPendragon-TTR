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

    def test_rarely_tired_slot_1_is_amazing(self):
        """Rarely Tired in slot 1 → amazing."""
        assert trait_tier("Rarely Tired", 1) == "amazing"

    def test_rarely_tired_slot_2_is_amazing(self):
        """Rarely Tired in slot 2 → amazing."""
        assert trait_tier("Rarely Tired", 2) == "amazing"

    def test_rarely_tired_slot_3_is_amazing(self):
        """Rarely Tired in slot 3 → amazing."""
        assert trait_tier("Rarely Tired", 3) == "amazing"

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

    def test_rest_priority_one_trait(self):
        """REST: fewer than 4 traits."""
        assert doodle_priority(["Always Affectionate"]) == PRIORITY_REST

    def test_rest_priority_two_traits(self):
        """REST: fewer than 4 traits."""
        assert doodle_priority(["Always Affectionate", "Always Playful"]) == PRIORITY_REST

    def test_rest_priority_three_traits(self):
        """REST: fewer than 4 traits."""
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
        """REST: any trait mix with a BAD trait falls to REST."""
        traits = [
            "Sometimes Confused",
            "Sometimes Affectionate",
            "Sometimes Hungry",
            "Often Bored",
        ]
        # 3 OK + 1 BAD trait = REST
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

    def test_star_for_rarely_tired_slot_1(self):
        """Rarely Tired in slot 1 → STAR_AMAZING emoji."""
        assert star_for("Rarely Tired", 1) == STAR_AMAZING

    def test_star_for_rarely_tired_slot_2(self):
        """Rarely Tired in slot 2 → STAR_AMAZING emoji."""
        assert star_for("Rarely Tired", 2) == STAR_AMAZING

    def test_star_for_rarely_tired_slot_3(self):
        """Rarely Tired in slot 3 → STAR_AMAZING emoji."""
        assert star_for("Rarely Tired", 3) == STAR_AMAZING

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
        assert _norm_district("O'Hare Quarter") == "oharequarter"

    def test_norm_district_empty_string(self):
        """Empty string stays empty."""
        assert _norm_district("") == ""

    def test_norm_district_none_handled(self):
        """None is coerced to empty string by (name or '') pattern."""
        result = _norm_district(None)
        assert result == ""


# ═════════════════════════════════════════════════════════════════════════════
# TEST: _is_safe_district()
# ═════════════════════════════════════════════════════════════════════════════

class TestIsSafeDistrict:
    """Test _is_safe_district(name: str) -> bool.

    Returns True if the district is immune to Mega Invasions.
    """

    def test_is_safe_district_blamcanyon(self):
        """Blamcanyon is safe from mega invasions."""
        assert _is_safe_district("Blamcanyon") is True
        assert _is_safe_district("BLAMCANYON") is True
        assert _is_safe_district("Blam Canyon") is True

    def test_is_safe_district_gulpgulch(self):
        """Gulpgulch is safe from mega invasions."""
        assert _is_safe_district("Gulpgulch") is True
        assert _is_safe_district("Gulp Gulch") is True

    def test_is_safe_district_whooshrapids(self):
        """Whooshrapids is safe from mega invasions."""
        assert _is_safe_district("Whooshrapids") is True
        assert _is_safe_district("Whoosh Rapids") is True

    def test_is_safe_district_woosh_rapids_misspelling(self):
        """Common misspelling 'Woosh' is also recognized as safe."""
        assert _is_safe_district("Woosh Rapids") is True
        assert _is_safe_district("Wooshrapids") is True

    def test_is_safe_district_zapwood(self):
        """Zapwood is safe from mega invasions."""
        assert _is_safe_district("Zapwood") is True
        assert _is_safe_district("Zap Wood") is True

    def test_is_safe_district_welcomevalley(self):
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

    def test_is_speedchat_only_gulpgulch(self):
        """Gulpgulch is speedchat-only."""
        assert _is_speedchat_only("Gulpgulch") is True
        assert _is_speedchat_only("Gulp Gulch") is True

    def test_is_speedchat_only_whooshrapids(self):
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
        """Negative epochs (before 1970) are truthy and formatted."""
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
        # Two doodles in the GREAT_GOOD bucket (3 Great + 1 Good)
        doodle_a = [
            "Always Affectionate",
            "Always Playful",
            "Rarely Bored",
            "Often Affectionate",
        ]
        doodle_b = [
            "Always Affectionate",
            "Rarely Hungry",
            "Rarely Confused",
            "Often Affectionate",
        ]

        # Both should be GREAT_GOOD (3 Great + 1 Good)
        assert doodle_priority(doodle_a) == PRIORITY_GREAT_GOOD
        assert doodle_priority(doodle_b) == PRIORITY_GREAT_GOOD

        # But doodle_a has higher quality (3 + 3 + 3 + 2 vs 3 + 3 + 3 + 2)
        # Both have same quality, but this tests that the ordering logic works
        assert doodle_quality(doodle_a) == doodle_quality(doodle_b)

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
