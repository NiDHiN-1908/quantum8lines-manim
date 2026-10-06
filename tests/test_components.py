"""
Automated tests for Quantum8Lines visual components and reference-frame regression tests.
Follows SPEC.md Sections 4, 14, Milestone M2, and Milestone M3a Step 0.
"""

from pathlib import Path
import os
from typing import Tuple
import pytest
import numpy as np
from PIL import Image
from manim import Scene, tempconfig

from core.tokens import BACKGROUND, PRIMARY, SECONDARY, HIGHLIGHT, STATIC, TEXT
from core.layout import Layout, LAYOUT_169, LAYOUT_916, place, inside_safe
from core.components import (
    VectorArrow,
    MatrixView,
    GraphPlot,
    EquationLine,
    Callout,
    Mascot,
)
from core.mathengine import Facts, UnverifiedClaimError

REFERENCE_DIR = Path(__file__).resolve().parent / "reference_frames"

# Dual criteria calibration constants (Milestone M3a Step 0b)
MAD_THRESHOLD = 0.40            # Mean Absolute Difference threshold (calibrated for 480x270 / 270x480)
OUTLIER_INTENSITY_DIFF = 40.0   # Intensity level difference threshold
MAX_OUTLIER_PCT = 0.5           # Maximum allowable percentage of outlier pixels (0.5%)


def check_region_intersection(mob, region) -> bool:
    """Returns True if the mobject bounding box intersects the given region."""
    m_top = mob.get_top()[1]
    m_bottom = mob.get_bottom()[1]
    m_left = mob.get_left()[0]
    m_right = mob.get_right()[0]
    return not (
        m_right <= region.x_min
        or m_left >= region.x_max
        or m_top <= region.y_min
        or m_bottom >= region.y_max
    )


def compare_frames(
    current_frame: np.ndarray,
    golden_frame: np.ndarray,
    mad_threshold: float = MAD_THRESHOLD,
    outlier_intensity: float = OUTLIER_INTENSITY_DIFF,
    max_outlier_pct: float = MAX_OUTLIER_PCT,
) -> Tuple[bool, str]:
    """
    Compares two rendered RGB frames using dual criteria.
    Fails if EITHER:
      1. Mean Absolute Difference > mad_threshold
      2. Percentage of pixels differing by > outlier_intensity exceeds max_outlier_pct
    """
    assert current_frame.shape == golden_frame.shape, (
        f"Shape mismatch: {current_frame.shape} vs {golden_frame.shape}"
    )

    diff = np.abs(current_frame.astype(float) - golden_frame.astype(float))
    mad = float(np.mean(diff))

    pixel_max_diff = np.max(diff, axis=-1)
    outlier_count = int(np.sum(pixel_max_diff > outlier_intensity))
    total_pixels = current_frame.shape[0] * current_frame.shape[1]
    outlier_pct = (outlier_count / total_pixels) * 100.0

    mad_failed = mad > mad_threshold
    outlier_failed = outlier_pct > max_outlier_pct

    if mad_failed or outlier_failed:
        reasons = []
        if mad_failed:
            reasons.append(f"MAD {mad:.4f} > {mad_threshold:.4f}")
        if outlier_failed:
            reasons.append(
                f"{outlier_pct:.2f}% pixels differ by >{outlier_intensity} "
                f"(limit: {max_outlier_pct}%)"
            )
        return False, "Regression detected: " + "; ".join(reasons)

    return True, f"Passed: MAD {mad:.4f}, Outliers {outlier_pct:.2f}%"


# ---------------------------------------------------------------------------
# 1. Component Construction & Safe Zone Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("layout", [LAYOUT_169, LAYOUT_916])
def test_vector_arrow_inside_safe(layout: Layout):
    """VectorArrow constructs and lies inside safe zone when placed in stage."""
    v = VectorArrow(vector=[2.0, 1.2], label=r"\vec{v}")
    place(v, layout.regions["stage"])
    assert inside_safe(v, layout) is True


@pytest.mark.parametrize("layout", [LAYOUT_169, LAYOUT_916])
def test_matrix_view_inside_safe(layout: Layout):
    """MatrixView constructs and lies inside safe zone when placed in stage."""
    m = MatrixView([[2, 1], [0, 3]], label="A =", highlight_entries=[(0, 0)])
    place(m, layout.regions["stage"])
    assert inside_safe(m, layout) is True


@pytest.mark.parametrize("layout", [LAYOUT_169, LAYOUT_916])
def test_graph_plot_inside_safe(layout: Layout):
    """GraphPlot constructs and lies inside safe zone when placed in stage."""
    is_portrait = layout.frame_height > layout.frame_width
    w = 4.8 if is_portrait else 6.0
    h = 3.2 if is_portrait else 3.2
    g = GraphPlot("x**2 - 1", x_range=[-3, 3, 1], y_range=[-2, 5, 2], x_length=w, y_length=h)
    place(g, layout.regions["stage"])
    assert inside_safe(g, layout) is True


@pytest.mark.parametrize("layout", [LAYOUT_169, LAYOUT_916])
def test_equation_line_inside_safe(layout: Layout):
    """EquationLine constructs and lies inside safe zone when placed in stage."""
    eq = EquationLine(
        r"A \vec{v} = \lambda \vec{v}",
        color_map={"A": PRIMARY, r"\vec{v}": SECONDARY, r"\lambda": HIGHLIGHT},
        font_size=38 if layout.frame_height > layout.frame_width else 44,
    )
    place(eq, layout.regions["stage"])
    assert inside_safe(eq, layout) is True


@pytest.mark.parametrize("layout", [LAYOUT_169, LAYOUT_916])
def test_callout_inside_safe(layout: Layout):
    """Callout constructs and lies inside safe zone when placed in stage."""
    callout = Callout("Important Point", target_point=[0.0, 0.0, 0.0])
    place(callout, layout.regions["stage"])
    assert inside_safe(callout, layout) is True


@pytest.mark.parametrize("layout", [LAYOUT_169, LAYOUT_916])
@pytest.mark.parametrize("corner", ["bottom_right", "bottom_left", "top_right", "top_left"])
def test_mascot_all_corners_safe_and_non_intersecting(layout: Layout, corner: str):
    """
    Milestone M3a Step 0e:
    Mascot placed in ANY of the four corners must:
      1. Lie entirely within layout safe zone.
      2. NEVER intersect the stage region.
      3. NEVER intersect the caption region.
    """
    mascot = Mascot()
    mascot.place_corner(layout, corner)

    assert inside_safe(mascot, layout) is True, f"Mascot breaches safe zone at {corner} in {layout.name}"
    assert check_region_intersection(mascot, layout.regions["stage"]) is False, (
        f"Mascot intersects stage region at {corner} in {layout.name}"
    )
    assert check_region_intersection(mascot, layout.regions["caption"]) is False, (
        f"Mascot intersects caption region at {corner} in {layout.name}"
    )


# ---------------------------------------------------------------------------
# 2. Facts Enforcement Test
# ---------------------------------------------------------------------------

def test_component_fails_on_unverified_claim():
    """Attempting to construct a component from a FAILED claim raises UnverifiedClaimError."""
    facts = Facts()
    facts.add_claim({
        "id": "c_bad_eigen",
        "type": "eigenpair",
        "matrix": [[2, 1], [0, 3]],
        "vector": [1, 0],
        "eigenvalue": 3,
    })
    facts.verify_all()

    with pytest.raises(UnverifiedClaimError) as exc_info:
        verified_data = facts.require_verified("c_bad_eigen")
        VectorArrow(vector=verified_data["vector"])

    assert "Cannot use values from claim 'c_bad_eigen'" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 3. Reference-Frame Tests (SPEC.md Section 14, 16:9 and 9:16)
# ---------------------------------------------------------------------------

def _render_fixed_frame(mobject, layout: Layout, width: int, height: int) -> np.ndarray:
    """Helper to render a component frame to a NumPy RGB array."""
    class RefScene(Scene):
        def construct(self):
            self.add(mobject)

    with tempconfig({
        "pixel_width": width,
        "pixel_height": height,
        "frame_width": layout.frame_width,
        "frame_height": layout.frame_height,
        "background_color": BACKGROUND,
    }):
        scene = RefScene()
        scene.render()
        frame = scene.renderer.get_frame()
        return frame[:, :, :3]


def _build_test_component(comp_name: str, layout: Layout):
    """Constructs standard component instance positioned for reference tests."""
    is_portrait = layout.frame_height > layout.frame_width

    if comp_name == "vector_arrow":
        mob = VectorArrow(vector=[2.5, 1.5], label=r"\vec{v}")
        place(mob, layout.regions["stage"])
    elif comp_name == "matrix_view":
        mob = MatrixView([[2, 1], [0, 3]], label="A =", highlight_entries=[(0, 0)])
        place(mob, layout.regions["stage"])
    elif comp_name == "graph_plot":
        w = 4.8 if is_portrait else 5.5
        h = 3.0 if is_portrait else 3.0
        mob = GraphPlot("x**2 - 2", x_range=[-3, 3, 1], y_range=[-3, 4, 1], x_length=w, y_length=h)
        place(mob, layout.regions["stage"])
    elif comp_name == "equation_line":
        mob = EquationLine(
            r"A \vec{v} = \lambda \vec{v}",
            color_map={"A": PRIMARY, r"\vec{v}": SECONDARY, r"\lambda": HIGHLIGHT},
            font_size=38 if is_portrait else 42,
        )
        place(mob, layout.regions["stage"])
    elif comp_name == "callout":
        mob = Callout("Critical Value", target_point=[0.0, 0.0, 0.0])
        place(mob, layout.regions["stage"])
    elif comp_name == "mascot":
        mob = Mascot()
        mob.place_corner(layout, "bottom_right")
    else:
        raise ValueError(f"Unknown component name: {comp_name}")

    return mob


@pytest.mark.parametrize("layout_key,layout,width,height", [
    ("169", LAYOUT_169, 480, 270),
    ("916", LAYOUT_916, 270, 480),
])
@pytest.mark.parametrize("comp_name", [
    "vector_arrow",
    "matrix_view",
    "graph_plot",
    "equation_line",
    "callout",
    "mascot",
])
def test_component_reference_frame(layout_key: str, layout: Layout, width: int, height: int, comp_name: str):
    """
    Render fixed frame and compare against stored reference PNG in both layouts.
    Uses dual criteria: MAD <= 5.0 and outliers <= 0.5%.
    """
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    ref_file = REFERENCE_DIR / f"{comp_name}_{layout_key}.png"

    mob = _build_test_component(comp_name, layout)
    current_frame = _render_fixed_frame(mob, layout, width, height)

    update_refs = os.environ.get("Q8L_UPDATE_REFS") == "1"

    if update_refs or not ref_file.exists():
        Image.fromarray(current_frame).save(ref_file)
        assert ref_file.exists()
        return

    golden_img = np.array(Image.open(ref_file).convert("RGB"))
    passed, msg = compare_frames(current_frame, golden_img)
    assert passed is True, f"Reference test failed for {comp_name}_{layout_key}: {msg}"


# ---------------------------------------------------------------------------
# 4. Negative Reference Tests (Milestone M3a Step 0c)
# ---------------------------------------------------------------------------

def test_negative_reference_test_vector_arrow():
    """Altered vector arrow must fail the dual criteria comparison."""
    ref_file = REFERENCE_DIR / "vector_arrow_169.png"
    if not ref_file.exists():
        pytest.skip("Golden reference file not yet generated.")

    # Deliberately altered vector coordinates
    altered_mob = VectorArrow(vector=[-2.0, 3.0], label=r"\vec{w}")
    place(altered_mob, LAYOUT_169.regions["stage"])

    altered_frame = _render_fixed_frame(altered_mob, LAYOUT_169, 480, 270)
    golden_img = np.array(Image.open(ref_file).convert("RGB"))

    passed, msg = compare_frames(altered_frame, golden_img)
    assert passed is False, "Deliberately altered VectorArrow should have failed reference test!"
    assert "Regression detected" in msg


def test_negative_reference_test_graph_plot():
    """Altered graph plot curve must fail the dual criteria comparison."""
    ref_file = REFERENCE_DIR / "graph_plot_169.png"
    if not ref_file.exists():
        pytest.skip("Golden reference file not yet generated.")

    # Deliberately altered function
    altered_mob = GraphPlot("sin(x)", x_range=[-3, 3, 1], y_range=[-2, 2, 1], x_length=5.5, y_length=3.0)
    place(altered_mob, LAYOUT_169.regions["stage"])

    altered_frame = _render_fixed_frame(altered_mob, LAYOUT_169, 480, 270)
    golden_img = np.array(Image.open(ref_file).convert("RGB"))

    passed, msg = compare_frames(altered_frame, golden_img)
    assert passed is False, "Deliberately altered GraphPlot should have failed reference test!"
    assert "Regression detected" in msg
