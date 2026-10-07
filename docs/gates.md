# Quality Gates Framework Documentation

This document describes the architecture, validation rules, AST linting specifications, and reporting formats for the Quantum8Lines Quality Gates implemented under **SPEC.md Section 8, Section 9, and Milestone M4a**.

---

## 1. Architectural Overview

Quality gates act as deterministic, blocking barriers between pipeline stages to guarantee mathematical accuracy, script formatting, design-token consistency, code security, and visual/audio fidelity before assets are rendered or published.

```
+------------+       +-------------+       +---------------+
|   script   | ----> |  G1 Script  | ----> |     verify    |
+------------+       +------+------+       +-------+-------+
                            |                      |
                            v                      v
                     [status.json]            +---------+
                     [qa/report]              | G2 Math |
                                              +----+----+
                                                   |
                                                   v
+------------+       +-------------+       +---------------+
|    code    | ----> |   G4 Code   | ----> |  test_render  |
+------------+       +------+------+       +---------------+
                            |
                            v
                     [status.json]
                     [qa/report]
```

### Core Design Principles
1. **Deterministic Blocking:** Gates pass or fail purely based on deterministic, reproducible checks.
2. **Actionable Feedback:** Every failure identifies the specific check ID, line number or entity ID, and reason for failure.
3. **Defense-in-Depth:** AST linting catches structural, security, and styling issues before any scene code is executed.
4. **Checkpointing & State Tracking:** Per-stage statuses (`pending`, `running`, `passed`, `failed`, `needs_human`) and gate reports are recorded in `status.json` and `qa/report.json`.

---

## 2. Gate Models (`pipeline/gates/models.py`)

### Check Model
Represents an atomic verification check:
- `id` (str): Unique identifier (e.g. `G4a_numeric_literals`, `G2_all_verified`).
- `passed` (bool): Whether the check passed.
- `severity` (str): `"error"` (blocking) or `"warning"` (advisory).
- `message` (str): Human-readable summary of the result.
- `details` (dict, optional): Contextual metadata (e.g., list of failed lines, duplicate IDs, missing claims).

### GateResult Model
Aggregates checks for a given gate:
- `gate_id` (str): Gate identifier (`"G1"`, `"G2"`, `"G4"`).
- `passed` (bool): `True` if and only if **all** checks with `severity == "error"` have `passed == True`.
- `checks` (list[Check]): List of executed checks.

### GateConfig Model
Configurable parameters with production defaults:
- `min_words` (int): Minimum total narration words (default: `100`).
- `max_words` (int): Maximum total narration words (default: `180`).
- `allowed_beats` (list[str]): Allowed beat tags (`["hook", "setup", "build", "aha", "close"]`).
- `canonical_beat_order` (list[str]): Required beat progression order (`["hook", "setup", "build", "aha", "close"]`).
- `allowed_cuts` (list[str]): Allowed cut tags (`["both", "short", "long"]`).

---

## 3. Implemented Gates (M4a)

### Gate G1: Script Verification (`pipeline/gates/g1_script.py`)
Executed immediately after the scriptwriter produces `script.json`.

| Check ID | Verification Rule | Failure Mode |
|---|---|---|
| `G1_schema` | Validates top-level `"chapter"` string and `"lines"` list of dicts with `"id"`, `"text"`, `"beat"`, `"cut"`. | Malformed JSON or missing required fields. |
| `G1_line_ids_unique` | Verifies that all line IDs (e.g. `l01`, `l02`) are unique within the chapter. | Duplicate line IDs detected. |
| `G1_beat_names` | Ensures every line's beat tag belongs to `config.allowed_beats`. | Unknown beat tag (e.g. `interlude`). |
| `G1_cut_tags` | Ensures every line's cut tag belongs to `config.allowed_cuts`. | Unknown cut tag (e.g. `full`). |
| `G1_word_count` | Sums word counts of `line["text"]` across all lines; must fall within `[min_words, max_words]`. | Script too brief (<100 words) or too long (>180 words). |
| `G1_beat_order` | Enforces that beats never regress backwards relative to `canonical_beat_order`. | Beat regression (e.g. `build` followed by `setup`). |
| `G1_claim_ids_exist` | Validates that every claim ID referenced in `line["claims"]` exists in `facts.json`. | Referenced claim ID missing from `facts.json`. |

---

### Gate G2: Math Verification (`pipeline/gates/g2_math.py`)
Executed after the math verifier evaluates claims in `facts.json`.

| Check ID | Verification Rule | Failure Mode |
|---|---|---|
| `G2_schema` | Validates that `facts.json` exists and contains a `"claims"` list. | Missing `facts.json` or missing `"claims"`. |
| `G2_all_verified` | Requires 100% of claims to have `status == "verified"`. | Any claim has status `failed`, `unverifiable`, or is unverified. |

---

### Gate G4: Code Quality & AST Linter (`pipeline/gates/g4_code.py`)
Executed after the scene coder produces `scene.py`. Parses Python Abstract Syntax Tree (AST) before executing any code.

| Check ID | Rule Description | Enforcement Details |
|---|---|---|
| `G4a_numeric_literals` | **Numeric Literals Restriction** | Only `0`, `1`, `-1` (and `0.0`, `1.0`, `-1.0`) literals allowed directly in code. All other numbers must come from `facts.json` or `core.*` layout/token constants. |
| `G4b_no_raw_colors` | **Design Token Color Enforcement** | Forbids raw Manim color names (`BLUE`, `RED`, `GREEN`, etc.) in imports or expressions, and forbids raw hex color strings (`#...`). All colors must use tokens from `core.tokens` (`PRIMARY`, `SECONDARY`, `BACKGROUND`, etc.). |
| `G4c_imports` | **Strict Whitelist of Imports** | Only imports from `manim`, `math`, and `core.*` are permitted. Rejects `os`, `sys`, `subprocess`, `numpy`, etc. |
| `G4d_forbidden_names` | **Execution Security & Sandbox** | Rejects forbidden names: `eval`, `exec`, `open`, `__import__`, `compile`, `subprocess`, `os`, `sys`. Rejects attribute access starting with `__` (e.g. `__class__`, `__dict__`). |
| `G4e_basescene_subclass` | **BaseScene Architecture** | Requires defining at least one class that subclasses `BaseScene`. |
| `G4f_dry_run_construct` | **Dual-Layout Dry Run** | Compiles and executes `scene.construct()` in memory (`config.dry_run = True`) in both 16:9 (`LAYOUT_169`) and 9:16 (`LAYOUT_916`) aspect ratios without raising exceptions. |
| `G4g_digits_in_text` | **Digits in Text & Labels** | String literals containing digits passed directly to `Text`, `MathTex`, `Tex`, `EquationLine`, `Callout`, or a `label` argument are forbidden; numbers shown on screen must come from `Facts.latex(...)` or an f-string using verified facts. An explicit escape hatch `# q8l: allow-digits <reason>` on that line passes with severity `"warning"` and lists the reason for G3 human review. |

#### G4g Escape Hatch
When mathematical constants or labels legitimately require digit literals that are not tracked in `facts.json` (such as fixed axis labels or formatting), authors may append a trailing comment on the same line:
```python
label = Text("Step 1")  # q8l: allow-digits chapter progression marker
```
When this comment is detected, `G4g_digits_in_text` passes with severity `"warning"` rather than failing with `"error"`, recording the reason in `qa/report.json` so G3 human review can inspect and approve it.

#### Extension Point for M2.2
`g4_code.py` contains a documented extension point `check_character_roster_extension(tree, roster_path)` designed to validate character IDs, poses, and slot assignments against `characters/roster.json` once character rigs are introduced in M2.2.

---

## 4. Pipeline State Tracking (`pipeline/status.py`)

### `topics/<topic>/chapters/<ch>/status.json`
Maintains per-stage lifecycle state:
```json
{
  "stages": {
    "plan": {"status": "passed", "input_hash": "...", "started_at": "...", "completed_at": "...", "artifacts": ["plan.json"]},
    "script": {"status": "passed", "input_hash": "...", "started_at": "...", "completed_at": "...", "artifacts": ["script.json"]},
    "verify": {"status": "passed", "input_hash": "...", "started_at": "...", "completed_at": "...", "artifacts": ["facts.json"]},
    "code": {"status": "passed", "input_hash": "...", "started_at": "...", "completed_at": "...", "artifacts": ["scene.py"]}
  },
  "updated_at": "2026-10-07T07:15:00.000000+00:00"
}
```

### `topics/<topic>/chapters/<ch>/qa/report.json`
Emitted by gate runs:
```json
{
  "passed": true,
  "timestamp": "2026-10-07T07:15:00.000000+00:00",
  "gates": {
    "G1": {
      "passed": true,
      "checks": [
        {"id": "G1_schema", "passed": true, "severity": "error", "message": "Script schema is valid."}
      ]
    },
    "G4": {
      "passed": true,
      "checks": [
        {"id": "G4a_numeric_literals", "passed": true, "severity": "error", "message": "Numeric literals adhere to allowed set {0, 1, -1}."}
      ]
    }
  }
}
```

---

## 5. Seeded Error Test Suite (`tests/test_gates_m4a.py`)

The test suite validates both a 100% compliant baseline fixture (`tests/fixtures/seeded/clean_chapter/`) and exactly 10 seeded failure cases:

1. **`test_case_01_eigenpair_with_wrong_eigenvalue`**: Fails G2 check `G2_all_verified` when claim status is `failed`.
2. **`test_case_02_scene_with_hardcoded_number`**: Fails G4 check `G4a_numeric_literals` when literal `2.7` is present.
3. **`test_case_03_scene_using_blue_and_hex_color`**: Fails G4 check `G4b_no_raw_colors` when `BLUE` or `#58c4dd` is used.
4. **`test_case_04_scene_importing_os`**: Fails G4 check `G4c_imports` when `import os` is present.
5. **`test_case_05_scene_calling_eval`**: Fails G4 check `G4d_forbidden_names` when `eval()` is called.
6. **`test_case_06_scene_missing_basescene_subclass`**: Fails G4 check `G4e_basescene_subclass` when no `BaseScene` subclass is declared.
7. **`test_case_07_scene_raising_during_construct`**: Fails G4 check `G4f_dry_run_construct` when scene construction raises an unhandled error.
8. **`test_case_08_script_word_count_out_of_range`**: Fails G1 check `G1_word_count` when total words fall below `min_words`.
9. **`test_case_09_script_referencing_missing_claim_id`**: Fails G1 check `G1_claim_ids_exist` when claim `c999_nonexistent` is referenced.
10. **`test_case_10_script_with_out_of_order_beats`**: Fails G1 check `G1_beat_order` when `build` appears before `setup`.
