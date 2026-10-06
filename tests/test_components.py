"""
Automated tests for Quantum8Lines visual components and reference-frame regression tests.
Follows SPEC.md Sections 4, 14, and Milestone M2 Step 5.
"""

from pathlib import Path
import os
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
MAD_THRESHOLD = 5.0  # Documented Mean Absolute Difference threshold (0-255 scale)


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
def test_mascot_corner_placement(layout: Layout):
    """Mascot placed in safe corner lies strictly inside safe zone and does not overlap stage."""
    mascot = Mascot()
    mascot.place_corner(layout, "bottom_right")
    assert inside_safe(mascot, layout) is True

    # Ensure no overlap with stage region
    stage = layout.regions["stage"]
    mascot_top = mascot.get_top()[1]
    mascot_bottom = mascot.get_bottom()[1]
    mascot_left = mascot.get_left()[0]
    mascot_right = mascot.get_right()[0]

    overlaps_stage = not (
        mascot_right < stage.x_min
        or mascot_left > stage.x_max
        or mascot_top < stage.y_min
        or mascot_bottom > stage.y_max
    )
    assert overlaps_stage is False, "Mascot must never overlap the stage region"


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
        # Scene attempts to use verified data to construct VectorArrow:
        verified_data = facts.require_verified("c_bad_eigen")
        VectorArrow(vector=verified_data["vector"])

    assert "Cannot use values from claim 'c_bad_eigen'" in str(exc_info.value)


# ---------------------------------------------------------------------------
# 3. Reference-Frame Tests (SPEC.md Section 14)
# ---------------------------------------------------------------------------

def _render_fixed_frame(mobject, layout: Layout = LAYOUT_169, width: int = 480) -> np.ndarray:
    """Helper to render a component frame to a NumPy RGB array."""
    aspect = layout.pixel_height / layout.pixel_width
    height = int(width * aspect)

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
        # Convert RGBA to RGB
        return frame[:, :, :3]


@pytest.mark.parametrize("comp_name", [
    "vector_arrow",
    "matrix_view",
    "graph_plot",
    "equation_line",
    "callout",
    "mascot",
])
def test_component_reference_frame(comp_name: str):
    """
    Render fixed frame and compare against stored reference PNG.
    Supports update switch Q8L_UPDATE_REFS=1 to refresh golden reference frames.
    """
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    ref_file = REFERENCE_DIR / f"{comp_name}.png"

    # Construct standard fixed component
    if comp_name == "vector_arrow":
        mob = VectorArrow(vector=[2.5, 1.5], label=r"\vec{v}")
        place(mob, LAYOUT_169.regions["stage"])
    elif comp_name == "matrix_view":
        mob = MatrixView([[2, 1], [0, 3]], label="A =", highlight_entries=[(0, 0)])
        place(mob, LAYOUT_169.regions["stage"])
    elif comp_name == "graph_plot":
        mob = GraphPlot("x**2 - 2", x_range=[-3, 3, 1], y_range=[-3, 4, 1], x_length=5.5, y_length=3.0)
        place(mob, LAYOUT_169.regions["stage"])
    elif comp_name == "equation_line":
        mob = EquationLine(
            r"A \vec{v} = \lambda \vec{v}",
            color_map={"A": PRIMARY, r"\vec{v}": SECONDARY, r"\lambda": HIGHLIGHT},
            font_size=42,
        )
        place(mob, LAYOUT_169.regions["stage"])
    elif comp_name == "callout":
        mob = Callout("Critical Value", target_point=[0.0, 0.0, 0.0])
        place(mob, LAYOUT_169.regions["stage"])
    elif comp_name == "mascot":
        mob = Mascot()
        mob.place_corner(LAYOUT_169, "bottom_right")
    else:
        raise ValueError(f"Unknown component name: {comp_name}")

    current_frame = _render_fixed_frame(mob, LAYOUT_169, width=480)

    # Check update switch
    update_refs = os.environ.get("Q8L_UPDATE_REFS") == "1"

    if update_refs or not ref_file.exists():
        Image.fromarray(current_frame).save(ref_file)
        # If updating, assertion passes
        assert ref_file.exists()
        return

    # Compare with stored golden frame
    golden_img = np.array(Image.open(ref_file).convert("RGB"))
    assert current_frame.shape == golden_img.shape, (
        f"Shape mismatch: {current_frame.shape} vs reference {golden_img.shape}"
    )

    diff = np.abs(current_frame.astype(float) - golden_img.astype(float))
    mad = float(np.mean(diff))

    assert mad <= MAD_THRESHOLD, (
        f"Reference frame regression for {comp_name}: "
        f"Mean Absolute Difference {mad:.4f} exceeds threshold {MAD_THRESHOLD}. "
        f"Set Q8L_UPDATE_REFS=1 to intentionally update references."
    )
