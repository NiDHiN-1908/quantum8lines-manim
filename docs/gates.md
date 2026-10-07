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

---

### Gate G5: Render Verification (`pipeline/gates/g5_render.py`)
Executed after test-quality rendering. Evaluates render success, frame emptiness, audio duration matching, and animation overruns.

| Check ID | Verification Rule | Failure Mode |
|---|---|---|
| `G5a_render_succeeds` | Verifies that Manim test render completed cleanly and output video file exists. | Unhandled render exception or missing output video. |
| `G5b_no_empty_frames` | Samples frames every 0.5s; a frame is "blank" if fewer than 0.2% of pixels differ from BACKGROUND (#0e0e11); fails if >15% of sampled frames are blank. | Too many empty or black frames. |
| `G5c_duration_matches_audio` | Verifies that video duration matches narration audio duration within ±0.3s tolerance. | Video length mismatch relative to audio window. |
| `G5d_beat_overrun` | Verifies no animation in any beat exceeds its allocated audio window. | Beat overrun detected (`BeatOverrunError`). |

---

### Gate G6: Visual QA Verification (`pipeline/gates/g6_visual.py`)
Deterministic visual inspection evaluated from recorded beat snapshots per layout (`16:9` and `9:16`).

| Check ID | Verification Rule | Failure Mode |
|---|---|---|
| `G6a_inside_safe` | Verifies every essential and text mobject is inside the layout's safe area. | Object breaches safe margin (e.g. 9:16 bottom unsafe zone). |
| `G6b_no_overlap` | Verifies no pair of essential or text objects overlap by more than tolerance (`0.02` units), except pairs sharing the same `group`. | Disallowed visual collision between essential elements. |
| `G6c_min_text_size` | Verifies text height meets SPEC 4.3 minimums: 48 px for labels, 72 px for key words. | Text rendered too small to read on mobile. |
| `G6d_contrast` | Verifies WCAG relative luminance contrast ratio between text color and BACKGROUND (#0e0e11) is >= 4.5. | Low-contrast or dark text on dark background. |
| `G6e_expect_visible` | Verifies every item in each storyboard beat's `expect.visible` exists in that beat's snapshots and lies inside the frame. | Expected storyboard object missing or out of view. |
| `G6f_characters` | Verifies character mobjects do not intersect essential objects, and at most 2 characters appear in any snapshot. | Character covers essential math, or >2 characters on screen. |

#### Text Height Pixel Conversion (G6c / SPEC 4.3)
1. Canvas scale: Coordinate units map to pixels via `px_per_unit = 1080 / 8.0 = 135.0 px/unit`, matching LayoutTestScene and captions.
2. Pixel height formula: Rendered height is measured as `height_px = mobject.height * 135.0` (recorded in snapshots).
3. Minimum thresholds: Standard labels require `height_px >= 48.0 px` (0.356 units); key words require `height_px >= 72.0 px` (0.533 units).

---

### Gate G7: Audio Verification (`pipeline/gates/g7_audio.py`)
Verifies loudness compliance, dynamic range, clipping, and caption synchronization.

| Check ID | Verification Rule | Failure Mode |
|---|---|---|
| `G7a_loudness` | Verifies final mix integrated loudness is within ±1 LU of -14 LUFS, and true peak is $\le -1.0\text{ dBTP}$. | Too loud, too quiet (e.g. -25 LUFS), or peak exceeds -1.0 dBTP. |
| `G7b_no_clipping` | Verifies peak sample < 0.999 and no run of 3+ consecutive full-scale samples. | Digital clipping or harsh square-wave distortion. |
| `G7c_caption_text` | Verifies subtitle dialogue words match `script.json` text exactly (via `check_caption_text`). | Caption transcription divergence or missing words. |
| `G7d_caption_timing` | Verifies caption timestamps are non-negative, chronological, and end within audio duration (+0.3s tolerance). | Subtitles running past audio end or non-monotonic times. |

---

### Human Review Gates (Non-Automated)
- **Gate G3 (Plan Review):** Human review of `script.json` and `storyboard.json`. Recorded as `"needs_human"` in `status.json`.
- **Gate G8 (Final Review):** Human final review of dual-layout renders before export/publishing. Recorded as `"needs_human"` in `status.json`.

---

## 4. Gate Runner CLI (`pipeline/run_gates.py`)

The pipeline gate runner provides an automated, fail-fast verification harness across the full chapter lifecycle:

```bash
uv run python -m pipeline.run_gates topics/<topic>/chapters/<ch> [--layout 169|916|both]
```

### Execution Flow
1. **G1 (Script):** Runs schema, word count, and beat ordering checks.
2. **G2 (Math):** Runs SymPy claim verification on `facts.json`.
3. **G4 (Code):** Runs AST linter on `scene.py` and dry-run construct.
4. **Test Render & G5 / G6:** Renders low-res video (`480x270` for 16:9, `270x480` for 9:16 at 15 fps) and evaluates render and visual snapshot gates per layout.
5. **G7 (Audio):** Measures loudness, clipping, and caption synchronization.
6. **Fail-Fast Behavior:** Halts immediately at the first failing gate without running subsequent stages.
7. **Reporting & State:** Emits structured JSON to `qa/report.json`, updates lifecycle stages and records `G3`/`G8` as `"needs_human"` in `status.json`.
8. **Exit Codes:** Returns code `0` on clean pass, `1` on failure.

### Reading a QA Report (`qa/report.json`)
```json
{
  "passed": true,
  "timestamp": "2026-10-07T07:50:17+00:00",
  "gates": {
    "G1": {"passed": true, "checks": [...]},
    "G2": {"passed": true, "checks": [...]},
    "G4": {"passed": true, "checks": [...]},
    "G5_169": {"passed": true, "checks": [...]},
    "G6_169": {"passed": true, "checks": [...]},
    "G5_916": {"passed": true, "checks": [...]},
    "G6_916": {"passed": true, "checks": [...]},
    "G7": {"passed": true, "checks": [...]}
  }
}
```
Each entry in `"checks"` reports its unique `id`, boolean `passed`, severity (`"error"` or `"warning"`), human-readable `message`, and contextual `details` dictionary naming the exact beats, line numbers, or mobjects involved.

---

## 5. Configuration Defaults (`GateConfig`)

| Parameter | Default | Description |
|---|---|---|
| `min_words` | `100` | Minimum narration word count for G1 |
| `max_words` | `180` | Maximum narration word count for G1 |
| `allowed_beats` | `["hook", "setup", "build", "aha", "close"]` | Canonical beat taxonomy |
| `empty_frame_sample_sec` | `0.5` | Sampling interval in seconds for G5b empty frame check |
| `blank_pixel_diff_threshold` | `0.002` | Minimum ratio of non-background pixels (0.2%) |
| `max_blank_frame_fraction` | `0.15` | Maximum allowed fraction of blank frames (15%) |
| `duration_match_tolerance_sec` | `0.3` | Allowed difference between audio and video duration in G5c |
| `visual_overlap_tolerance` | `0.02` | Manim unit tolerance for bounding box intersections in G6b |
| `min_label_text_height_px` | `48.0` | Minimum label text height in pixels (SPEC 4.3) |
| `min_keyword_text_height_px` | `72.0` | Minimum keyword text height in pixels (SPEC 4.3) |
| `min_contrast_ratio` | `4.5` | Minimum WCAG contrast ratio against BACKGROUND (#0e0e11) |
| `max_character_count` | `2` | Maximum concurrent characters on screen in G6f |
| `target_lufs` | `-14.0` | Target integrated loudness in LUFS for G7a |
| `lufs_tolerance` | `1.0` | Allowed LUFS variation ([-15.0, -13.0] LUFS) |
| `max_true_peak_dbtp` | `-1.0` | Maximum true peak in dBTP |
| `max_peak_sample` | `0.999` | Maximum absolute sample value for G7b clipping |
| `max_consecutive_full_scale` | `3` | Full-scale sample run threshold for clipping |
| `caption_timing_tolerance_sec` | `0.3` | Small end tolerance for caption intervals |

---

## 6. Seeded Error Test Suites

### M4a Suite (`tests/test_gates_m4a.py`)
Validates baseline G1, G2, G4 gates against 10 seeded failure modes:
1. `G2_all_verified` (unverified claim)
2. `G4a_numeric_literals` (literal 2.7 in code)
3. `G4b_no_raw_colors` (raw BLUE / hex colors)
4. `G4c_imports` (import os)
5. `G4d_forbidden_names` (eval call)
6. `G4e_basescene_subclass` (missing BaseScene subclass)
7. `G4f_dry_run_construct` (construct error)
8. `G1_word_count` (word count out of range)
9. `G1_claim_ids_exist` (missing claim ID)
10. `G1_beat_order` (out of order beats)

### M4b Suite (`tests/test_gates_m4b.py`)
Validates dual-layout clean chapter end-to-end and 14 seeded failure modes:
1. Empty scene -> `G5b_no_empty_frames`
2. Video much shorter than audio -> `G5c_duration_matches_audio`
3. Animation longer than audio window -> `G5d_beat_overrun`
4. Essential object in 9:16 bottom unsafe zone -> `G6a_inside_safe`
5. Overlapping essential texts -> `G6b_no_overlap`
6. Text smaller than minimum -> `G6c_min_text_size`
7. Dark text on dark background -> `G6d_contrast`
8. Missing expect.visible object -> `G6e_expect_visible`
9. Character covering essential object / 3 characters -> `G6f_characters`
10. Too-quiet audio mix (-25 LUFS) -> `G7a_loudness`
11. Clipped audio file -> `G7b_no_clipping`
12. Captions mismatch script -> `G7c_caption_text`
13. Captions running past audio end -> `G7d_caption_timing`
14. MathTex("x = 2.7") digit literal -> `G4g_digits_in_text` (error), and same line with `# q8l: allow-digits <reason>` passes with warning.
