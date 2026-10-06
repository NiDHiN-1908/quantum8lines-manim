"""
Layout engine for Quantum8Lines animations.
Defines frame configurations, safe zones, regions, and placement helpers
for 16:9 and 9:16 aspect ratios according to SPEC.md section 4.3.
Includes LayoutTestScene and still PNG rendering helpers.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Union
import numpy as np
from manim import (
    Rectangle,
    Mobject,
    VGroup,
    Text,
    Scene,
    DL,
    UR,
    UP,
    DOWN,
    config,
)

from core.tokens import BACKGROUND, PRIMARY, SECONDARY, STATIC, HIGHLIGHT, TEXT
from core.fonts import get_inter_font


@dataclass(frozen=True)
class Region:
    """A rectangular region in Manim coordinates for placing content."""
    name: str
    center_x: float
    center_y: float
    width: float
    height: float

    @property
    def center(self) -> np.ndarray:
        return np.array([self.center_x, self.center_y, 0.0])

    @property
    def x_min(self) -> float:
        return self.center_x - self.width / 2.0

    @property
    def x_max(self) -> float:
        return self.center_x + self.width / 2.0

    @property
    def y_min(self) -> float:
        return self.center_y - self.height / 2.0

    @property
    def y_max(self) -> float:
        return self.center_y + self.height / 2.0

    def as_rect(self, color=None, stroke_width: float = 1.5, stroke_opacity: float = 0.8) -> Rectangle:
        """Create a Manim Rectangle outlining this region."""
        rect = Rectangle(
            width=self.width,
            height=self.height,
            stroke_width=stroke_width,
            stroke_opacity=stroke_opacity,
        )
        if color:
            rect.set_stroke(color)
        rect.move_to(self.center)
        return rect


@dataclass(frozen=True)
class Layout:
    """Full canvas layout specification."""
    name: str
    pixel_width: int
    pixel_height: int
    frame_width: float
    frame_height: float
    fps: int
    safe_top_px: float
    safe_bottom_px: float
    safe_left_px: float
    safe_right_px: float
    regions: Dict[str, Region]

    @property
    def px_per_unit(self) -> float:
        return self.pixel_height / self.frame_height

    @property
    def safe_x_min(self) -> float:
        return -self.frame_width / 2.0 + self.safe_left_px / self.px_per_unit

    @property
    def safe_x_max(self) -> float:
        return self.frame_width / 2.0 - self.safe_right_px / self.px_per_unit

    @property
    def safe_y_min(self) -> float:
        return -self.frame_height / 2.0 + self.safe_bottom_px / self.px_per_unit

    @property
    def safe_y_max(self) -> float:
        return self.frame_height / 2.0 - self.safe_top_px / self.px_per_unit

    @property
    def safe_width(self) -> float:
        return self.safe_x_max - self.safe_x_min

    @property
    def safe_height(self) -> float:
        return self.safe_y_max - self.safe_y_min

    @property
    def safe_center(self) -> np.ndarray:
        return np.array([
            (self.safe_x_min + self.safe_x_max) / 2.0,
            (self.safe_y_min + self.safe_y_max) / 2.0,
            0.0
        ])

    def safe_rect(self, color=None, stroke_width: float = 2.0, stroke_opacity: float = 0.9) -> Rectangle:
        """Create a Manim Rectangle outlining the safe zone."""
        rect = Rectangle(
            width=self.safe_width,
            height=self.safe_height,
            stroke_width=stroke_width,
            stroke_opacity=stroke_opacity,
        )
        if color:
            rect.set_stroke(color)
        rect.move_to(self.safe_center)
        return rect


# ---------------------------------------------------------------------------
# Layout Definitions (SPEC.md Section 4.3)
# ---------------------------------------------------------------------------

# 16:9 Landscape: 1920x1080 px, frame 14.222 x 8.0 units (135 px/unit)
# Safe zone: 5% margin on all sides (96 px left/right, 54 px top/bottom)
LAYOUT_169 = Layout(
    name="16:9",
    pixel_width=1920,
    pixel_height=1080,
    frame_width=14.222,
    frame_height=8.0,
    fps=30,
    safe_top_px=54.0,     # 5% of 1080
    safe_bottom_px=54.0,  # 5% of 1080
    safe_left_px=96.0,    # 5% of 1920
    safe_right_px=96.0,   # 5% of 1920
    regions={
        "title": Region(name="title", center_x=0.0, center_y=3.0, width=12.0, height=1.0),
        "stage": Region(name="stage", center_x=0.0, center_y=0.4, width=12.0, height=4.0),
        "caption": Region(name="caption", center_x=0.0, center_y=-2.3, width=11.0, height=1.2),
        "footer": Region(name="footer", center_x=0.0, center_y=-3.25, width=11.0, height=0.6),
    }
)

# 9:16 Portrait: 1080x1920 px, frame 8.0 x 14.222 units (135 px/unit)
# Safe zone: top 250 px, bottom 480 px, left/right 90 px
LAYOUT_916 = Layout(
    name="9:16",
    pixel_width=1080,
    pixel_height=1920,
    frame_width=8.0,
    frame_height=14.222,
    fps=30,
    safe_top_px=250.0,
    safe_bottom_px=480.0,
    safe_left_px=90.0,
    safe_right_px=90.0,
    regions={
        "title": Region(name="title", center_x=0.0, center_y=4.4, width=6.4, height=1.4),
        "stage": Region(name="stage", center_x=0.0, center_y=1.2, width=6.4, height=4.8),
        "caption": Region(name="caption", center_x=0.0, center_y=-2.1, width=6.2, height=1.6),
        "footer": Region(name="footer", center_x=0.0, center_y=-3.2, width=6.2, height=0.6),
    }
)


# ---------------------------------------------------------------------------
# Conversion and Placement Helpers
# ---------------------------------------------------------------------------

def px_to_units(px: float, layout: Layout) -> float:
    """Convert screen pixels to Manim coordinate units."""
    return px / layout.px_per_unit


def units_to_px(units: float, layout: Layout) -> float:
    """Convert Manim coordinate units to screen pixels."""
    return units * layout.px_per_unit


def place(mobject: Mobject, region: Region) -> Mobject:
    """Move mobject to the center of a specified region."""
    mobject.move_to(region.center)
    return mobject


def inside_safe(mobject: Mobject, layout: Layout, tolerance: float = 1e-3) -> bool:
    """
    Check if a mobject's bounding box is entirely within the layout's safe zone.
    Returns True if inside, False if any part breaches the safe zone.
    """
    dl = mobject.get_corner(DL)
    ur = mobject.get_corner(UR)

    obj_x_min = dl[0]
    obj_x_max = ur[0]
    obj_y_min = dl[1]
    obj_y_max = ur[1]

    if obj_x_min < layout.safe_x_min - tolerance:
        return False
    if obj_x_max > layout.safe_x_max + tolerance:
        return False
    if obj_y_min < layout.safe_y_min - tolerance:
        return False
    if obj_y_max > layout.safe_y_max + tolerance:
        return False

    return True


def apply_layout(cfg, layout: Layout):
    """Apply layout dimensions and framerate to a Manim config object."""
    cfg.pixel_width = layout.pixel_width
    cfg.pixel_height = layout.pixel_height
    cfg.frame_width = layout.frame_width
    cfg.frame_height = layout.frame_height
    cfg.frame_rate = layout.fps


# ---------------------------------------------------------------------------
# Layout Test Scene (M1)
# ---------------------------------------------------------------------------

class LayoutTestScene(Scene):
    """
    Draws the canvas frame, safe-zone rectangle, region outlines with labels,
    and a sample caption verifying the minimum text sizes (SPEC.md 4.3).
    """

    layout: Layout = LAYOUT_169

    def __init__(self, layout: Layout | None = None, **kwargs):
        if layout is not None:
            self.layout = layout
        super().__init__(**kwargs)

    def setup(self):
        super().setup()
        self.camera.background_color = BACKGROUND
        self.camera.frame_width = self.layout.frame_width
        self.camera.frame_height = self.layout.frame_height

    def construct(self):
        inter_font = get_inter_font()
        elements = VGroup()

        # 1. Canvas frame boundary
        frame_rect = Rectangle(
            width=self.layout.frame_width - 0.05,
            height=self.layout.frame_height - 0.05,
            stroke_color=STATIC,
            stroke_width=2.0,
            stroke_opacity=0.6,
        )
        elements.add(frame_rect)

        # 2. Safe-zone rectangle
        safe_rect = self.layout.safe_rect(color=HIGHLIGHT, stroke_width=2.5, stroke_opacity=0.9)
        safe_text = Text(
            f"SAFE ZONE ({self.layout.name})",
            font=inter_font,
            font_size=18,
            color=HIGHLIGHT,
        ).next_to(safe_rect.get_top(), DOWN, buff=0.15)
        elements.add(safe_rect, safe_text)

        # 3. Regions with outlines and labels
        for region in self.layout.regions.values():
            reg_rect = region.as_rect(color=PRIMARY, stroke_width=1.5, stroke_opacity=0.75)
            reg_label = Text(
                f"[{region.name.upper()}] {region.width:.1f}x{region.height:.1f}",
                font=inter_font,
                font_size=16,
                color=PRIMARY,
            ).next_to(reg_rect.get_top(), DOWN, buff=0.12)
            elements.add(reg_rect, reg_label)

        # 4. Stage placeholder content
        stage_text = Text(
            "STAGE CONTENT AREA",
            font=inter_font,
            font_size=24,
            color=SECONDARY,
        )
        place(stage_text, self.layout.regions["stage"])
        elements.add(stage_text)

        # 5. Caption at minimum text sizes from SPEC 4.3 (48 px labels, 72 px key words)
        cap_h_48 = px_to_units(48, self.layout)
        cap_h_72 = px_to_units(72, self.layout)

        cap_label = Text("Caption label (48px min)", font=inter_font, color=TEXT)
        cap_label.height = cap_h_48

        cap_keyword = Text("KEYWORD (72px min)", font=inter_font, color=HIGHLIGHT)
        cap_keyword.height = cap_h_72

        caption_group = VGroup(cap_label, cap_keyword).arrange(
            DOWN, buff=px_to_units(12, self.layout)
        )
        place(caption_group, self.layout.regions["caption"])
        elements.add(caption_group)

        self.add(elements)


def render_layout_still(layout_input: Union[str, Layout], output_path: Path) -> Path:
    """
    Render one still PNG frame for the specified layout to output_path.
    """
    layout = LAYOUT_169 if layout_input in ("16:9", "169", LAYOUT_169) else LAYOUT_916
    output_path = Path(output_path).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    apply_layout(config, layout)
    config.format = "png"
    config.media_dir = str(output_path.parent / "_media")
    config.output_file = str(output_path)
    config.verbosity = "WARNING"

    scene = LayoutTestScene(layout=layout)
    scene.render()

    generated_path = Path(scene.renderer.file_writer.image_file_path)
    if generated_path.exists() and generated_path != output_path:
        import shutil
        shutil.copy2(generated_path, output_path)

    return output_path
