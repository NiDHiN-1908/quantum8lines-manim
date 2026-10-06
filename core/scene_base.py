"""
Base scene class and minimal HelloScene for Quantum8Lines.
Supports 16:9 and 9:16 aspect ratios based on SPEC.md section 4.3.
"""

from pathlib import Path
import time
from typing import Union
from manim import (
    Scene,
    Arrow,
    MathTex,
    ORIGIN,
    RIGHT,
    UP,
    FadeIn,
    GrowArrow,
    config,
)

from core.tokens import BACKGROUND, PRIMARY, TEXT
from core.layout import Layout, LAYOUT_169, LAYOUT_916, apply_layout


class BaseScene(Scene):
    """
    Base Scene class for Quantum8Lines animations.
    Takes layout from class attribute or constructor argument.
    Sets standard background color and default scene configuration.
    """

    layout: Layout = LAYOUT_169

    def __init__(self, layout: Layout | None = None, **kwargs):
        if layout is not None:
            self.layout = layout
        super().__init__(**kwargs)

    def setup(self):
        super().setup()
        self.camera.background_color = BACKGROUND
        # Ensure camera frame conforms to layout
        self.camera.frame_width = self.layout.frame_width
        self.camera.frame_height = self.layout.frame_height


class HelloScene(BaseScene):
    """
    Minimal test scene rendering one vector and one label.
    Used for verifying rendering in both 16:9 and 9:16 formats.
    """

    def construct(self):
        # One vector using PRIMARY token
        vector = Arrow(
            ORIGIN,
            2.0 * (RIGHT + 0.5 * UP),
            buff=0,
            stroke_width=6,
            color=PRIMARY,
        )
        # One label using TEXT token
        label = MathTex(r"\vec{v}", color=TEXT).next_to(
            vector.get_end(), UP + RIGHT * 0.2
        )

        self.play(GrowArrow(vector), run_time=1.0)
        self.play(FadeIn(label), run_time=0.6)
        self.wait(0.5)


def render_hello_scene(layout_input: Union[str, Layout], output_folder: Path) -> dict:
    """
    Render HelloScene in specified layout (16:9 or 9:16) at 30 fps.
    """
    output_folder.mkdir(parents=True, exist_ok=True)

    if isinstance(layout_input, Layout):
        layout = layout_input
    elif layout_input in ("16:9", "169"):
        layout = LAYOUT_169
    elif layout_input in ("9:16", "916"):
        layout = LAYOUT_916
    else:
        raise ValueError(f"Unsupported layout: {layout_input}")

    out_filename = "hello_16x9.mp4" if layout == LAYOUT_169 else "hello_9x16.mp4"
    target_video_file = output_folder / out_filename

    # Configure Manim settings from layout
    apply_layout(config, layout)
    config.media_dir = str(output_folder / "_media")
    config.output_file = str(target_video_file)
    config.verbosity = "WARNING"

    t0 = time.perf_counter()
    scene = HelloScene(layout=layout)
    scene.render()
    render_duration = time.perf_counter() - t0

    # Locate generated output file
    movie_path = Path(scene.renderer.file_writer.movie_file_path)

    return {
        "aspect_ratio": layout.name,
        "pixel_width": layout.pixel_width,
        "pixel_height": layout.pixel_height,
        "frame_width": layout.frame_width,
        "frame_height": layout.frame_height,
        "frame_rate": layout.fps,
        "output_path": str(movie_path.resolve()),
        "render_time_seconds": round(render_duration, 3),
        "file_size_bytes": movie_path.stat().st_size if movie_path.exists() else 0,
    }


def main():
    base_output = Path("temp_renders").resolve()
    print(f"Starting test renders in: {base_output}\n")

    t169 = render_hello_scene(LAYOUT_169, base_output / "16_9")
    print(f"16:9 Render Complete:")
    print(f"  Path: {t169['output_path']}")
    print(f"  Time: {t169['render_time_seconds']}s")
    print(f"  Size: {t169['file_size_bytes']} bytes\n")

    t916 = render_hello_scene(LAYOUT_916, base_output / "9_16")
    print(f"9:16 Render Complete:")
    print(f"  Path: {t916['output_path']}")
    print(f"  Time: {t916['render_time_seconds']}s")
    print(f"  Size: {t916['file_size_bytes']} bytes\n")


if __name__ == "__main__":
    main()
