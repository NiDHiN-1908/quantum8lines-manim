"""
Automated tests for Milestone M1 (Design System, Layout Engine, Intro Conform).
"""

from pathlib import Path
import subprocess
from manim import Dot, Square, UP, DOWN, ORIGIN
import pytest

from core.tokens import BACKGROUND, PRIMARY, SECONDARY, DYNAMIC, STATIC, HIGHLIGHT, TEXT
from core.layout import (
    LAYOUT_169,
    LAYOUT_916,
    Layout,
    Region,
    px_to_units,
    units_to_px,
    place,
    inside_safe,
    LayoutTestScene,
)


# ---------------------------------------------------------------------------
# 1. Tokens Tests
# ---------------------------------------------------------------------------

def test_tokens_defined():
    """All required semantic roles are defined."""
    assert BACKGROUND == "#0e0e11"
    assert PRIMARY is not None
    assert SECONDARY is not None
    assert DYNAMIC is not None
    assert STATIC is not None
    assert HIGHLIGHT is not None
    assert TEXT is not None


def test_tokens_no_duplicates():
    """No duplicate values for different semantic roles."""
    roles = [PRIMARY, SECONDARY, DYNAMIC, STATIC, HIGHLIGHT, TEXT, BACKGROUND]
    unique_roles = set(str(r) for r in roles)
    assert len(unique_roles) == 7, "Each semantic token must have a unique value."


# ---------------------------------------------------------------------------
# 2. Layout Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("layout", [LAYOUT_169, LAYOUT_916])
def test_layout_safe_zones_inside_frame(layout: Layout):
    """Safe-zone rectangles must lie strictly inside the canvas frame."""
    half_w = layout.frame_width / 2.0
    half_h = layout.frame_height / 2.0

    assert layout.safe_x_min >= -half_w
    assert layout.safe_x_max <= half_w
    assert layout.safe_y_min >= -half_h
    assert layout.safe_y_max <= half_h
    assert layout.safe_width > 0
    assert layout.safe_height > 0


@pytest.mark.parametrize("layout", [LAYOUT_169, LAYOUT_916])
def test_layout_has_all_four_regions(layout: Layout):
    """Both layouts must contain title, stage, caption, and footer regions."""
    required = {"title", "stage", "caption", "footer"}
    assert required.issubset(layout.regions.keys())
    for name in required:
        reg = layout.regions[name]
        assert isinstance(reg, Region)
        assert reg.width > 0
        assert reg.height > 0


@pytest.mark.parametrize("layout", [LAYOUT_169, LAYOUT_916])
def test_regions_inside_safe_zone(layout: Layout):
    """All defined regions must lie strictly within the layout safe zone."""
    for reg in layout.regions.values():
        assert reg.x_min >= layout.safe_x_min - 1e-3, f"Region {reg.name} breaches safe left"
        assert reg.x_max <= layout.safe_x_max + 1e-3, f"Region {reg.name} breaches safe right"
        assert reg.y_min >= layout.safe_y_min - 1e-3, f"Region {reg.name} breaches safe bottom"
        assert reg.y_max <= layout.safe_y_max + 1e-3, f"Region {reg.name} breaches safe top"


@pytest.mark.parametrize("layout", [LAYOUT_169, LAYOUT_916])
def test_px_units_round_trip(layout: Layout):
    """px_to_units and units_to_px must round-trip accurately."""
    test_px = 270.0
    units = px_to_units(test_px, layout)
    back_to_px = units_to_px(units, layout)
    assert abs(back_to_px - test_px) < 1e-5

    test_units = 3.5
    px = units_to_px(test_units, layout)
    back_to_units = px_to_units(px, layout)
    assert abs(back_to_units - test_units) < 1e-5


# ---------------------------------------------------------------------------
# 3. inside_safe() Bounding Box Tests
# ---------------------------------------------------------------------------

def test_inside_safe_positive_and_negative():
    """Verify inside_safe handles positive (stage) and negative (bottom unsafe zone) cases."""
    # Positive case: placed in stage region of 9:16
    dot_in_stage = Dot(radius=0.1)
    place(dot_in_stage, LAYOUT_916.regions["stage"])
    assert inside_safe(dot_in_stage, LAYOUT_916) is True

    # Positive case: placed in stage region of 16:9
    dot_in_stage_169 = Dot(radius=0.1)
    place(dot_in_stage_169, LAYOUT_169.regions["stage"])
    assert inside_safe(dot_in_stage_169, LAYOUT_169) is True

    # Negative case: placed in the 9:16 bottom unsafe zone (y = -6.0; safe bottom is ~ -3.55)
    dot_in_bottom_unsafe = Dot(point=[0.0, -6.0, 0.0], radius=0.2)
    assert inside_safe(dot_in_bottom_unsafe, LAYOUT_916) is False

    # Negative case: placed in 9:16 top unsafe zone (y = +6.5; safe top is ~ +5.26)
    dot_in_top_unsafe = Dot(point=[0.0, 6.5, 0.0], radius=0.2)
    assert inside_safe(dot_in_top_unsafe, LAYOUT_916) is False

    # Negative case: placed past right boundary (x = +3.8; safe right is +3.333)
    dot_in_right_unsafe = Dot(point=[3.8, 0.0, 0.0], radius=0.2)
    assert inside_safe(dot_in_right_unsafe, LAYOUT_916) is False


# ---------------------------------------------------------------------------
# 4. LayoutTestScene Construction Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("layout", [LAYOUT_169, LAYOUT_916])
def test_layout_test_scene_construct(layout: Layout):
    """LayoutTestScene must construct under both layouts without error."""
    scene = LayoutTestScene(layout=layout)
    scene.setup()
    scene.construct()
    assert len(scene.mobjects) > 0


# ---------------------------------------------------------------------------
# 5. Conformed Video Output Tests
# ---------------------------------------------------------------------------

def _probe_stream(video_path: Path) -> dict:
    """Helper using ffprobe to query video dimensions and frame rate."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-of", "json",
        str(video_path)
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.returncode == 0, f"ffprobe failed on {video_path}: {proc.stderr}"
    data = json.loads(proc.stdout)
    return data["streams"][0]


import json


def test_conformed_outputs_exist_and_conform(tmp_path):
    """Output files generated into tmp_path must exist with exact resolution and 30 fps."""
    intro_source = Path("brand/Quantum8Line_Intro.mp4")
    if not intro_source.exists():
        pytest.skip(f"Intro video not found at {intro_source}")

    from pipeline.conform import conform_intro
    conform_intro("169", input_path=intro_source, output_dir=tmp_path)
    conform_intro("916", input_path=intro_source, output_dir=tmp_path)

    files_to_check = {
        tmp_path / "intro_169.mp4": {"width": 1920, "height": 1080, "fps": "30/1"},
        tmp_path / "intro_916_candidate_a.mp4": {"width": 1080, "height": 1920, "fps": "30/1"},
        tmp_path / "intro_916_candidate_b.mp4": {"width": 1080, "height": 1920, "fps": "30/1"},
    }

    for path, expected in files_to_check.items():
        assert path.exists(), f"Expected conformed file {path} does not exist"
        stream_info = _probe_stream(path)
        assert stream_info["width"] == expected["width"]
        assert stream_info["height"] == expected["height"]
        assert stream_info["r_frame_rate"] == expected["fps"]


# ---------------------------------------------------------------------------
# 6. Font Weight Ink Coverage Test
# ---------------------------------------------------------------------------

def test_inter_bold_ink_coverage():
    """
    Verify static Inter bold font has at least 20% more ink coverage than regular at 48 px.
    Saves labeled side-by-side proof to temp_renders/font_weight_check.png.
    """
    import numpy as np
    from manim import Scene, Text, VGroup, DOWN, tempconfig
    from core.fonts import register_project_fonts, get_inter_font

    register_project_fonts()
    font_name = get_inter_font()

    class FontCheckScene(Scene):
        def construct(self):
            t_reg = Text("Quantum8Lines Math 2026", font=font_name, weight="NORMAL", font_size=48)
            lbl_reg = Text("Regular (NORMAL)", font=font_name, font_size=24, color="#71717a").next_to(t_reg, DOWN, buff=0.2)
            group_reg = VGroup(t_reg, lbl_reg).shift([-4.5, 0, 0])

            t_bold = Text("Quantum8Lines Math 2026", font=font_name, weight="BOLD", font_size=48)
            lbl_bold = Text("Bold (BOLD)", font=font_name, font_size=24, color="#71717a").next_to(t_bold, DOWN, buff=0.2)
            group_bold = VGroup(t_bold, lbl_bold).shift([4.5, 0, 0])

            self.add(group_reg, group_bold)

    Path("temp_renders").mkdir(exist_ok=True)
    with tempconfig({"pixel_width": 1920, "pixel_height": 600, "frame_width": 20, "frame_height": 5, "verbosity": "ERROR"}):
        scene = FontCheckScene()
        scene.render()
        img = scene.camera.get_image()
        output_path = Path("temp_renders/font_weight_check.png")
        img.save(str(output_path))
        assert output_path.exists()

    arr = np.array(img)
    gray = np.mean(arr[:, :, :3], axis=2)
    threshold = 30
    reg_half = gray[:, :960]
    bold_half = gray[:, 960:]

    ink_reg = np.sum(reg_half > threshold)
    ink_bold = np.sum(bold_half > threshold)
    ink_ratio = (ink_bold - ink_reg) / ink_reg

    # Bold must have at least 20% more ink than regular
    assert ink_ratio >= 0.20, f"Bold ink increase ({ink_ratio*100:.1f}%) is below required 20%"
