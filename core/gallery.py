"""
Gallery renderer and contact sheet generator for Quantum8Lines components.
Follows SPEC.md Milestone M2 Step 4:
  - Renders one still per component and one per mascot state in both layouts.
  - Saves individual stills under temp_renders/gallery/.
  - Assembles labeled contact sheets:
      temp_renders/gallery_169.png
      temp_renders/gallery_916.png
      temp_renders/mascot_states.png
"""

from pathlib import Path
from typing import Dict, Any, Callable
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from manim import Scene, tempconfig, DEGREES, UP, RIGHT

from core.tokens import BACKGROUND, PRIMARY, SECONDARY, HIGHLIGHT, STATIC, TEXT
from core.layout import Layout, LAYOUT_169, LAYOUT_916, place
from core.components import (
    VectorArrow,
    MatrixView,
    GraphPlot,
    EquationLine,
    Callout,
    Mascot,
)

TEMP_RENDERS_DIR = Path("temp_renders")
GALLERY_DIR = TEMP_RENDERS_DIR / "gallery"


def create_component(name: str, layout: Layout):
    """Instantiate a component pre-configured and placed in layout's stage region."""
    stage = layout.regions["stage"]

    if name == "VectorArrow":
        mob = VectorArrow(vector=[2.8, 1.4], label=r"\vec{v}", color=PRIMARY)
    elif name == "MatrixView":
        mob = MatrixView(
            matrix=[[2, 1], [0, 3]],
            label="A =",
            highlight_entries=[(0, 0), (1, 1)],
            highlight_color=HIGHLIGHT,
        )
    elif name == "GraphPlot":
        # Adjust dimensions for 16:9 vs 9:16
        is_portrait = layout.frame_height > layout.frame_width
        w = 4.8 if is_portrait else 6.0
        h = 3.4 if is_portrait else 3.4
        mob = GraphPlot(
            expression="x**2 - 2",
            x_range=[-3.0, 3.0, 1.0],
            y_range=[-3.0, 5.0, 2.0],
            x_length=w,
            y_length=h,
            marked_points=[[-1.414, 0.0], [1.414, 0.0], [0.0, -2.0]],
        )
    elif name == "EquationLine":
        mob = EquationLine(
            r"A \vec{v} = \lambda \vec{v}",
            color_map={"A": PRIMARY, r"\vec{v}": SECONDARY, r"\lambda": HIGHLIGHT},
            font_size=40 if layout.frame_height > layout.frame_width else 46,
        )
    elif name == "Callout":
        mob = Callout(
            text="Eigenvector Point",
            target_point=[0.0, -0.6, 0.0],
            direction=UP,
        )
    else:
        raise ValueError(f"Unknown component: {name}")

    place(mob, stage)
    return mob


def create_mascot_state(state: str, layout: Layout = LAYOUT_169):
    """Instantiate mascot in a specific state."""
    mascot = Mascot(scale_val=0.7)
    mascot.move_to([0.0, 0.0, 0.0])

    if state == "idle":
        pass  # Standard resting state
    elif state == "blink":
        # Eyes scaled flat (closed)
        mascot.eyes.scale(np.array([1.0, 0.1, 1.0]))
    elif state == "think":
        # Quizzical tilt
        mascot.rotate(15.0 * DEGREES, about_point=mascot.get_bottom())
    elif state == "surprised":
        # Scaled up with widened eyes
        mascot.scale(1.12)
        mascot.eyes.scale(1.35)
    elif state == "point":
        # Oriented toward target at [3, 2, 0]
        mascot.rotate(-18.0 * DEGREES, about_point=mascot.get_center())
    else:
        raise ValueError(f"Unknown mascot state: {state}")

    return mascot


def render_scene_to_image(mobject, layout: Layout, width: int = 640) -> Image.Image:
    """Render a mobject on a layout frame to a PIL Image."""
    aspect = layout.pixel_height / layout.pixel_width
    height = int(width * aspect)

    class StillScene(Scene):
        def construct(self):
            self.add(mobject)

    with tempconfig({
        "pixel_width": width,
        "pixel_height": height,
        "frame_width": layout.frame_width,
        "frame_height": layout.frame_height,
        "background_color": BACKGROUND,
    }):
        scene = StillScene()
        scene.render()
        frame = scene.renderer.get_frame()
        return Image.fromarray(frame)


def assemble_contact_sheet(
    images: Dict[str, Image.Image],
    output_path: Path,
    cols: int = 3,
    padding: int = 24,
    label_height: int = 36,
) -> Path:
    """
    Assemble multiple labeled images into a unified contact sheet grid.
    """
    names = list(images.keys())
    n = len(names)
    rows = (n + cols - 1) // cols

    first_img = next(iter(images.values()))
    img_w, img_h = first_img.size

    cell_w = img_w
    cell_h = img_h + label_height

    sheet_w = cols * cell_w + (cols + 1) * padding
    sheet_h = rows * cell_h + (rows + 1) * padding

    # Create dark slate background matching brand
    sheet = Image.new("RGB", (sheet_w, sheet_h), color=(20, 20, 26))
    draw = ImageDraw.Draw(sheet)

    # Use default bitmap font
    font = ImageFont.load_default()

    for idx, name in enumerate(names):
        r = idx // cols
        c = idx % cols

        x = padding + c * (cell_w + padding)
        y = padding + r * (cell_h + padding)

        # Label background bar
        label_rect = [x, y, x + cell_w, y + label_height]
        draw.rectangle(label_rect, fill=(30, 30, 38))

        # Label text
        draw.text((x + 10, y + 10), name, fill=(240, 240, 245), font=font)

        # Image placement
        img = images[name].convert("RGB")
        sheet.paste(img, (x, y + label_height))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output_path, "PNG")
    return output_path


def generate_all_galleries() -> Dict[str, Path]:
    """
    Renders all component stills and mascot states,
    saving stills and creating the 3 required contact sheets.
    """
    GALLERY_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_RENDERS_DIR.mkdir(parents=True, exist_ok=True)

    components = ["VectorArrow", "MatrixView", "GraphPlot", "EquationLine", "Callout"]
    mascot_states = ["idle", "blink", "think", "surprised", "point"]

    # 1. 16:9 Components
    images_169 = {}
    for comp in components:
        mob = create_component(comp, LAYOUT_169)
        img = render_scene_to_image(mob, LAYOUT_169, width=640)
        still_path = GALLERY_DIR / f"169_{comp}.png"
        img.save(still_path)
        images_169[f"{comp} (16:9)"] = img

    sheet_169_path = TEMP_RENDERS_DIR / "gallery_169.png"
    assemble_contact_sheet(images_169, sheet_169_path, cols=3)

    # 2. 9:16 Components
    images_916 = {}
    for comp in components:
        mob = create_component(comp, LAYOUT_916)
        img = render_scene_to_image(mob, LAYOUT_916, width=360)
        still_path = GALLERY_DIR / f"916_{comp}.png"
        img.save(still_path)
        images_916[f"{comp} (9:16)"] = img

    sheet_916_path = TEMP_RENDERS_DIR / "gallery_916.png"
    assemble_contact_sheet(images_916, sheet_916_path, cols=3)

    # 3. Mascot States
    images_mascot = {}
    for state in mascot_states:
        mob = create_mascot_state(state, LAYOUT_169)
        img = render_scene_to_image(mob, LAYOUT_169, width=480)
        still_path = GALLERY_DIR / f"mascot_{state}.png"
        img.save(still_path)
        images_mascot[f"Mascot: {state.capitalize()}"] = img

    sheet_mascot_path = TEMP_RENDERS_DIR / "mascot_states.png"
    assemble_contact_sheet(images_mascot, sheet_mascot_path, cols=3)

    return {
        "gallery_169": sheet_169_path,
        "gallery_916": sheet_916_path,
        "mascot_states": sheet_mascot_path,
    }


if __name__ == "__main__":
    outputs = generate_all_galleries()
    print("Gallery Generation Complete:")
    for k, p in outputs.items():
        print(f"  {k}: {p}")
