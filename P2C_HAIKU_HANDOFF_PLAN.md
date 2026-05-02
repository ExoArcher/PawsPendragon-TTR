# P2-C Implementation Handoff Plan for Haiku Tomorrow

**Date Created:** 2026-05-01  
**For:** Claude Haiku (tomorrow's session)  
**Task:** Deploy subagents to implement P2-C formatter tests  
**Expected Duration:** 3–4 hours  
**Complexity:** LOW  
**Risk:** ZERO (additive only)  

---

## Executive Summary

You are being handed off the **P2-C Implementation Phase** for Paws Pendragon. This is the third phase of a larger multi-phase improvement workflow:

- **Phase 1 (COMPLETE):** Quick-win fixes (git safety, retry logic, config validation, etc.) deployed via 3 Haiku subagents in parallel.
- **Phase 2-C (YOUR TASK):** Implement comprehensive pytest test suite for pure formatter functions.
- **Phase 2-A/B (GATED):** Performance improvements (connection pooling, per-guild rate limiting) — *only after P2-C/D tests pass*.
- **Phase 3 (FUTURE):** Modular refactoring (extract bot.py features, split formatters.py).

Your role tomorrow: **Read the detailed P2C_FORMATTER_TESTS_GUIDE.md, then spawn 3 parallel subagents to implement the changes.** This is an ideal delegation task because the work breaks cleanly into independent parts.

---

## What You Need to Know (Context)

### Project: Paws Pendragon Discord Bot

A multi-guild Discord bot that mirrors **Toontown Rewritten** API data into live-updating Discord embeds. The bot has:

- **71-line monolithic bot.py** being refactored into modular Features/
- **Pure formatter functions** in `PDMain/Features/Core/formatters/formatters.py` (no Discord object dependencies)
- **Zero test harness** (first tests ever being added)
- **5 pure functions to test:**
  - `trait_tier()` — classify a doodle trait+slot into 6 tiers (perfect, amazing, great, good, ok, bad)
  - `doodle_priority()` — classify a full 4-trait doodle into 6 priority buckets
  - `doodle_quality()` — compute quality score (tiebreaker within buckets)
  - `star_for()` — return emoji for a trait at a given tier
  - Plus 4 more: `_norm_district()`, `_is_safe_district()`, `_is_speedchat_only()`, `_ts()`

### Why Now?

Before the Phase 3 monolithic→modular refactor begins, we need **regression tests locked in** to ensure existing behavior is preserved. Pure functions are perfect testing targets because they have zero external dependencies (no Discord API calls, no database, no file I/O).

---

## Your Task (Step by Step)

### Step 1: Read the Implementation Guide

**File:** `C:\Users\exoki\OneDrive\Documents\Claude\Projects\Paws Pendragon\P2C_FORMATTER_TESTS_GUIDE.md`

**What to do:**
- Read the entire guide (it's ~1000 lines but well-structured)
- Understand the test file structure (imports, test classes, parametrized tests)
- Note the 3 independent implementation tasks (see Step 2 below)

**Key sections:**
- **Part 1:** Setup (add pytest dependencies, create test directory)
- **Part 2:** Implementation (full ~500-line test_formatters.py content)
- **Part 3:** Running tests (how to verify locally)
- **Part 4:** Verification checklist (8-item success criteria)

### Step 2: Identify Parallel Work Streams

The implementation work breaks into **3 independent subagent tasks** that can run in parallel. Each subagent owns one task completely:

#### **Subagent 1: Setup & Infrastructure**
**Responsibility:** Prepare the environment for testing
- Task 1A: Add `pytest>=7.0.0,<8.0` and `pytest-asyncio>=0.21.0,<1.0` to `PDMain/requirements.txt`
- Task 1B: Create `PDMain/tests/__init__.py` (empty file)
- Task 1C: Verify directory structure matches the guide's expected layout

**Input:** The P2C_FORMATTER_TESTS_GUIDE.md Part 1 section  
**Output:** Updated requirements.txt, new __init__.py file, confirmation message  
**Success Criteria:** requirements.txt has 6 lines (4 original + 2 new), __init__.py exists, directory structure is correct

#### **Subagent 2: Test File – Part A (Pure Function Tests)**
**Responsibility:** Implement the test file (lines 1–300 of test_formatters.py)
- Implement all imports and test setup
- Implement TestTraitTier class (7 test methods)
- Implement TestDoodlePriority class (25 test methods)
- Implement TestDoodleQuality class (10 test methods)

**Input:** The P2C_FORMATTER_TESTS_GUIDE.md Part 2.1 section, extract the test code from line 85 onwards  
**Output:** Partial test_formatters.py with the above 3 test classes  
**Success Criteria:** Code is syntactically valid Python, imports work, test methods follow parametrized test pattern (use @pytest.mark.parametrize)

#### **Subagent 3: Test File – Part B (Remaining Pure Function Tests)**
**Responsibility:** Implement the test file continuation (lines 301–500 of test_formatters.py)
- Implement TestStarFor class (6 test methods)
- Implement TestNormDistrict class (5 test methods)
- Implement TestIsSafeDistrict class (7 test methods)
- Implement TestIsSpeedchatOnly class (5 test methods)
- Implement TestTs class (7 test methods)
- Implement TestIntegration class (3 integration test methods)

**Input:** The P2C_FORMATTER_TESTS_GUIDE.md Part 2.1 section (same as Subagent 2, but different lines)  
**Output:** Partial test_formatters.py with the above 6 test classes  
**Success Criteria:** Code is syntactically valid Python, test methods follow parametrized pattern, all classes defined and ready to merge

---

## How to Deploy the Subagents

### Subagent 1: Setup

```
Agent(
  description: "P2-C Setup: Add pytest dependencies and create test directory",
  prompt: """You are implementing PHASE 2-C for Paws Pendragon: adding pytest test infrastructure.

YOUR TASK:
1. Read C:\Users\exoki\OneDrive\Documents\Claude\Projects\Paws Pendragon\P2C_FORMATTER_TESTS_GUIDE.md Part 1 (Setup & File Structure) sections 1.1 and 1.2
2. Modify C:\Users\exoki\OneDrive\Documents\Claude\Projects\Paws Pendragon\PDMain\requirements.txt:
   - Add these two lines at the end:
     pytest>=7.0.0,<8.0
     pytest-asyncio>=0.21.0,<1.0
3. Create C:\Users\exoki\OneDrive\Documents\Claude\Projects\Paws Pendragon\PDMain\tests\__init__.py (empty file)
4. Verify the directory structure matches the guide's expectation:
   PDMain/tests/__init__.py should exist (empty)
   PDMain/requirements.txt should have exactly 6 lines
5. Report: List the 6 lines of requirements.txt and confirm __init__.py exists

SUCCESS CRITERIA:
- requirements.txt has exactly 6 lines (4 original + pytest + pytest-asyncio)
- PDMain/tests/__init__.py exists and is empty
- No other changes made
- Clear status report

REPORT FORMAT:
- Line 1: "✓ SETUP COMPLETE"
- Line 2: "requirements.txt now has X lines:"
- Lines 3-8: Show all 6 lines of requirements.txt
- Line 9: "__init__.py created at: PDMain/tests/__init__.py"
- Line 10-12: Any notes or issues
"""
)
```

### Subagent 2: Test File Part A

```
Agent(
  description: "P2-C Test Implementation Part A: trait_tier, doodle_priority, doodle_quality",
  prompt: """You are implementing PHASE 2-C for Paws Pendragon: test suite for pure formatter functions.

YOUR TASK — PART A (Test Classes 1–3):
1. Read C:\Users\exoki\OneDrive\Documents\Claude\Projects\Paws Pendragon\P2C_FORMATTER_TESTS_GUIDE.md FULL FILE to understand context
2. Extract from the guide's Part 2.1 section (starting at "Full file content") the test code
3. Implement PDMain/tests/test_formatters.py with:
   - ALL imports (sys, os, pytest, pytest.mark.parametrize, and imports from Features.Core.formatters.formatters)
   - Module docstring (from the guide)
   - TestTraitTier class: 7 test methods covering:
     * Rarely Tired in slot 0 → perfect tier
     * Rarely Tired in slots 1-3 → amazing tier
     * All trait set classifications (GREAT_TRAITS, GOOD_TRAITS, OK_TRAITS, BAD_TRAITS)
     * Unknown traits → bad tier fallback
   - TestDoodlePriority class: 25+ test methods covering:
     * All 6 priority buckets (PERFECT, AMAZING, GREAT, GREAT_GOOD, GREAT_GOOD_OK, REST)
     * Exact thresholds from the doodle_priority() function
     * Edge cases and boundary conditions
   - TestDoodleQuality class: 10 test methods covering:
     * Quality scoring (weight sum: perfect=5, amazing=4, great=3, good=2, ok=1, bad=0)
     * Tiebreaking within priority buckets
     * Edge cases

4. Use @pytest.mark.parametrize for all test inputs (don't hardcode test cases in loop)
5. Each test method should be focused and test ONE condition
6. Code must be syntactically valid Python (py_compile check)
7. No need to implement TestStarFor or later classes — that's Subagent 3

CRITICAL REQUIREMENTS:
- The file MUST start with imports and module docstring
- Imports MUST include: sys, os, pytest, from Features.Core.formatters.formatters import trait_tier, doodle_priority, doodle_quality, GREAT_TRAITS, GOOD_TRAITS, OK_TRAITS, BAD_TRAITS
- TestTraitTier, TestDoodlePriority, TestDoodleQuality must be complete classes with all methods
- @pytest.mark.parametrize decorators MUST be used (no hardcoded test loops)
- Indentation and syntax must be perfect (test will be run with py_compile)

REPORT FORMAT:
- Line 1: "✓ PART A COMPLETE"
- Line 2-4: Summary of what was implemented (class count, method count)
- Line 5: "File location: PDMain/tests/test_formatters.py"
- Line 6: "Next: Subagent 3 will implement remaining test classes"
- Lines 7+: Any notes or implementation decisions
"""
)
```

### Subagent 3: Test File Part B

```
Agent(
  description: "P2-C Test Implementation Part B: star_for, districts, timestamps, integration",
  prompt: """You are implementing PHASE 2-C for Paws Pendragon: test suite for pure formatter functions.

YOUR TASK — PART B (Test Classes 4–9):
1. Read C:\Users\exoki\OneDrive\Documents\Claude\Projects\Paws Pendragon\P2C_FORMATTER_TESTS_GUIDE.md FULL FILE
2. Read C:\Users\exoki\OneDrive\Documents\Claude\Projects\Paws Pendragon\PDMain\tests\test_formatters.py (created by Subagent 2) to understand the structure
3. APPEND to the existing test_formatters.py file (do NOT overwrite) the following test classes:
   - TestStarFor: 6 test methods testing star_for() emoji mapping per tier (perfect, amazing, great, good, ok, bad)
   - TestNormDistrict: 5 test methods testing _norm_district() normalization (lowercase, spaces, apostrophes, case sensitivity)
   - TestIsSafeDistrict: 7 test methods testing _is_safe_district() for mega-invasion immunity
   - TestIsSpeedchatOnly: 5 test methods testing _is_speedchat_only() for speedchat-only districts
   - TestTs: 7 test methods testing _ts() Discord relative timestamp conversion from epoch
   - TestIntegration: 3 test methods for cross-function behavior tests

4. Use @pytest.mark.parametrize for all test inputs
5. Code must be syntactically valid Python
6. Proper indentation and class nesting

CRITICAL REQUIREMENTS:
- APPEND to existing test_formatters.py (don't recreate the whole file)
- Import the additional functions needed: from Features.Core.formatters.formatters import star_for, _norm_district, _is_safe_district, _is_speedchat_only, _ts
- All 6 test classes must be properly defined
- @pytest.mark.parametrize decorators MUST be used for test inputs
- Imports can be added at the top if needed
- Indentation must match the existing file

REPORT FORMAT:
- Line 1: "✓ PART B COMPLETE"
- Line 2-4: Summary of what was appended (class count, method count)
- Line 5: "File location: PDMain/tests/test_formatters.py"
- Line 6: "Total classes in file: 9 (all test_formatters.py classes complete)"
- Line 7: "Ready for Subagent 4 (verification)"
- Lines 8+: Any notes
"""
)
```

---

## Step 3: Merge & Verify (After Subagents Complete)

Once all 3 subagents report completion:

1. **Verify file structure:**
   ```
   PDMain/
   ├── requirements.txt (6 lines)
   ├── tests/
   │   ├── __init__.py (empty)
   │   └── test_formatters.py (~500 lines with 9 test classes)
   └── Features/Core/formatters/formatters.py (unchanged)
   ```

2. **Syntax check** (run before moving forward):
   ```powershell
   cd PDMain
   python -m py_compile tests/test_formatters.py
   ```
   Expected output: No errors, silent exit.

3. **Import check** (verify imports resolve):
   ```powershell
   cd PDMain
   python -c "from tests.test_formatters import *; print('OK')"
   ```
   Expected output: `OK`

4. **Install dependencies** (install pytest):
   ```powershell
   cd PDMain
   pip install -r requirements.txt
   ```

5. **Run the tests** (verify all tests pass):
   ```powershell
   cd PDMain
   python -m pytest tests/test_formatters.py -v
   ```
   Expected output: **~95 tests, all PASS**

---

## Step 4: Verification Checklist (From Guide Part 4)

After tests pass, confirm:

- [ ] `PDMain/requirements.txt` has `pytest>=7.0.0,<8.0` and `pytest-asyncio>=0.21.0,<1.0`
- [ ] `PDMain/tests/__init__.py` exists (empty)
- [ ] `PDMain/tests/test_formatters.py` exists with ~500 lines
- [ ] All 9 test classes defined: TestTraitTier, TestDoodlePriority, TestDoodleQuality, TestStarFor, TestNormDistrict, TestIsSafeDistrict, TestIsSpeedchatOnly, TestTs, TestIntegration
- [ ] Syntax valid: `py_compile` returns no errors
- [ ] Imports work: `python -c "from tests.test_formatters import *"` succeeds
- [ ] All dependencies installed: `pip install -r requirements.txt` succeeds
- [ ] All tests pass: `python -m pytest tests/test_formatters.py -v` shows ~95 passing tests with **0 failures**
- [ ] No changes to any source files in `Features/` or `bot.py`

---

## Success Criteria

**P2-C is COMPLETE when:**

1. ✓ Requirements.txt updated with pytest + pytest-asyncio
2. ✓ Test directory structure created (tests/__init__.py)
3. ✓ test_formatters.py implemented with 9 test classes and ~95 test methods
4. ✓ All syntax is valid (py_compile passes)
5. ✓ All imports resolve (no ImportError)
6. ✓ All ~95 tests pass (0 failures)
7. ✓ No source code changes (only additive: requirements.txt, tests/ dir)
8. ✓ Clear report documenting what was done

---

## What's Next (After P2-C)

Once P2-C tests pass, the next phases are:

- **P2-D (Future):** Add pytest tests for db.py (database CRUD functions against :memory: SQLite)
- **P2-C/D Gate:** Both test suites must pass before proceeding
- **P2-A (Performance):** SQLite connection pooling (single connection instead of one-per-call)
- **P2-B (Scale):** Per-guild asyncio.Semaphore for rate limiting (fixes 120-second refresh issue)
- **Phase 3:** Monolithic→modular refactor (extract bot.py features, split formatters.py)

---

## Important Notes

- **No deployment or running the bot required.** This is purely test infrastructure setup.
- **Zero breaking changes.** All work is additive; no existing code is modified.
- **Pure functions only.** The tests exercise pure functions with no Discord API or database dependencies.
- **Regression net.** Once in place, these tests lock in current behavior so refactoring in Phase 3 can be confident.
- **First test harness.** This project has never had automated tests before; this is the foundation.

---

## Troubleshooting

**If subagent reports import error:**
- Check that formatters.py exists at: `PDMain/Features/Core/formatters/formatters.py`
- Verify the functions exist in formatters.py: trait_tier, doodle_priority, doodle_quality, star_for, _norm_district, _is_safe_district, _is_speedchat_only, _ts
- Check sys.path includes the PDMain directory

**If pytest not found:**
- Ensure `pip install -r requirements.txt` was run
- Verify requirements.txt has the pytest lines

**If test methods fail syntactically:**
- Check @pytest.mark.parametrize syntax (decorator goes above method, has correct parameter names)
- Verify indentation is consistent (4 spaces per level)
- Ensure no hardcoded loops inside test methods

**If tests fail at runtime:**
- This shouldn't happen if the guide is followed exactly
- The functions being tested are stable, pure functions
- If a test fails, it indicates a mismatch between test expectations and actual function behavior (which would be a discovery — report it)

---

## Summary for You

**You are the coordinator.** Read the P2C_FORMATTER_TESTS_GUIDE.md, then deploy the 3 subagents in parallel using the prompts above. Each subagent owns one independent task. Once all 3 report completion, verify the file structure and run the tests. If all ~95 tests pass, P2-C is done.

**Expected timeline:** 3–4 hours total (subagents run in parallel, verification takes ~30 min).

**Risk level:** ZERO — this is purely additive infrastructure, no changes to existing code.

Good luck! 🚀
