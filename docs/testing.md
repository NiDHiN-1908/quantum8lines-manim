# Testing Strategy & Reference Frames

Follows **SPEC.md Section 14** and **Milestone M2**.

---

## 1. Overview of Test Suites

The test suite runs through `uv run pytest -v` without external service dependencies:

1. **Design System & Layout Tests (`tests/test_m1_design_system.py`)**:
   - Token uniqueness and semantic role existence.
   - Layout safe zone math for 16:9 and 9:16 aspect ratios.
   - Region bounding box containment.
   - Safe zone bounding box containment (`inside_safe()` positive and negative tests).
   - Video conform tests using pytest `tmp_path` fixture.

2. **Math Engine Tests (`tests/test_mathengine.py`)**:
   - Positive and negative cases for all 8 checkers (`equation_true`, `solution_set`, `eigenpair`, `intersection`, `derivative`, `integral`, `value_at`, `plot_matches`).
   - Seeded error tests verifying detection of:
     - Invalid eigenpair ($A=[[2,1],[0,3]], v=[1,0], \lambda=3$).
     - Incomplete intersection ($y=x^2$ and $y=4$ claiming only $x=2$).
     - Incorrect derivative ($\frac{d}{dx}(x^3)$ claiming $2x^2$).
   - `Facts` loading, saving, and `require_verified()` enforcement raising `UnverifiedClaimError`.

3. **Component & Reference-Frame Tests (`tests/test_components.py`)**:
   - Verification that every component constructs without exceptions in both 16:9 and 9:16.
   - Safe zone compliance: components placed in `stage` pass `inside_safe()`.
   - Mascot corner placement: sits inside safe area and never overlaps the stage region.
   - Golden reference-frame image regression comparisons.

---

## 2. Reference-Frame Regression Testing (SPEC Section 14)

### Purpose
Reference-frame tests render fixed visual frames of each component (`VectorArrow`, `MatrixView`, `GraphPlot`, `EquationLine`, `Callout`, `Mascot`) and compare the rendered pixels against golden reference PNGs stored in `tests/reference_frames/`.

### Cross-Machine Font & LaTeX Antialiasing
### Dual Comparison Criteria (Milestone M3a Step 0b)
To accommodate benign antialiasing variations without compromising visual regression detection, comparisons use **two criteria**, and a frame fails if **EITHER** criterion is violated:

1. **Mean Absolute Difference (MAD)** across all RGB channels:
   $$\text{MAD} = \frac{1}{3 \cdot W \cdot H} \sum_{x, y, c} |I_{\text{current}}(x, y, c) - I_{\text{golden}}(x, y, c)|$$
   - **Calibrated Threshold**: `MAD <= 0.40` (on a 0–255 scale).
   - Identical re-renders yield `MAD = 0.0`. Benign font smoothing variations typically yield `MAD < 0.15`.
   - Structural shifts or missing curves immediately cause `MAD > 0.50`, triggering a failure.

2. **Outlier Pixel Percentage**:
   - Computes the percentage of pixels whose color intensity in any RGB channel differs from the golden frame by more than **40 intensity levels**:
     $$\text{Outlier Pixels} = \{ (x, y) \mid \max_c |I_{\text{current}}(x, y, c) - I_{\text{golden}}(x, y, c)| > 40 \}$$
   - **Calibrated Threshold**: $\le 0.50\%$ of total pixels.
   - If more than 0.5% of pixels diverge by $> 40$ intensity levels, the test reports a regression failure.

### Aspect Ratios & Resolutions
Reference frames are generated and verified for all 6 components across **both layouts**:
- **16:9 Landscape**: `480x270` pixels (`tests/reference_frames/<comp>_169.png`).
- **9:16 Portrait**: `270x480` pixels (`tests/reference_frames/<comp>_916.png`).

### Negative Reference Tests
Negative test cases in `tests/test_components.py` deliberately alter component parameters (e.g. inverted vector in `VectorArrow`, substituted curve in `GraphPlot`) and assert that the regression detector flags failures, proving that the verification criteria are actively catching visual anomalies.

### Updating Golden Reference Frames
When intentional design changes or new component features are introduced, golden reference frames can be refreshed using the update switch:

```bash
# Windows PowerShell
$env:Q8L_UPDATE_REFS="1"
uv run pytest tests/test_components.py -v
$env:Q8L_UPDATE_REFS="0"

# Linux / Bash
Q8L_UPDATE_REFS=1 uv run pytest tests/test_components.py -v
```

Reference frames must only be updated in dedicated, reviewable commits per SPEC 14.
