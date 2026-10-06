"""
Base scene class and minimal HelloScene for Quantum8Lines.
Supports 16:9 and 9:16 aspect ratios based on SPEC.md section 4.3.
"""

from pathlib import Path
import time
from manim import (
    Scene,
    Arrow,
    MathTex,
    ORIGIN,
    RIGHT,
    UP,
    BLUE,
    WHITE,
    FadeIn,
    GrowArrow,
    config,
)


class BaseScene(Scene):
    """
    Base Scene class for Quantum8Lines animations.
    Sets standard background color and default scene configuration.
    """

    def setup(self):
        super().setup()
        self.camera.background_color = "#0e0e11"


class HelloScene(BaseScene):
    """
    Minimal test scene rendering one vector and one label.
    Used for verifying rendering in both 16:9 and 9:16 formats.
    """

    def construct(self):
        # One vector
        vector = Arrow(
            ORIGIN,
            2.0 * (RIGHT + 0.5 * UP),
            buff=0,
            stroke_width=6,
            color=BLUE,
        )
        # One label
        label = MathTex(r"\vec{v}", color=WHITE).next_to(
            vector.get_end(), UP + RIGHT * 0.2
        )

        self.play(GrowArrow(vector), run_time=1.0)
        self.play(FadeIn(label), run_time=0.6)
        self.wait(0.5)


def render_hello_scene(aspect_ratio: str, output_folder: Path) -> dict:
    """
    Render HelloScene in specified aspect ratio (16:9 or 9:16) at 30 fps.
    Frame dimensions follow SPEC.md section 4.3:
      - 16:9 -> 1920x1080 (frame_width: 14.222, frame_height: 8.0)
      - 9:16 -> 1080x1920 (frame_width: 8.0, frame_height: 14.222)
    """
    output_folder.mkdir(parents=True, exist_ok=True)

    if aspect_ratio == "16:9":
        pixel_width = 1920
        pixel_height = 1080
        frame_width = 14.222
        frame_height = 8.0
        out_filename = "hello_16x9.mp4"
    elif aspect_ratio == "9:16":
        pixel_width = 1080
        pixel_height = 1920
        frame_width = 8.0
        frame_height = 14.222
        out_filename = "hello_9x16.mp4"
    else:
        raise ValueError(f"Unsupported aspect_ratio: {aspect_ratio}")

    target_video_file = output_folder / out_filename

    # Configure Manim settings
    config.pixel_width = pixel_width
    config.pixel_height = pixel_height
    config.frame_width = frame_width
    config.frame_height = frame_height
    config.frame_rate = 30
    config.media_dir = str(output_folder / "_media")
    config.output_file = str(target_video_file)
    config.verbosity = "WARNING"

    t0 = time.perf_counter()
    scene = HelloScene()
    scene.render()
    render_duration = time.perf_counter() - t0

    # Locate generated output file
    movie_path = Path(scene.renderer.file_writer.movie_file_path)

    return {
        "aspect_ratio": aspect_ratio,
        "pixel_width": pixel_width,
        "pixel_height": pixel_height,
        "frame_width": frame_width,
        "frame_height": frame_height,
        "frame_rate": 30,
        "output_path": str(movie_path.resolve()),
        "render_time_seconds": round(render_duration, 3),
        "file_size_bytes": movie_path.stat().st_size if movie_path.exists() else 0,
    }


def main():
    base_output = Path("temp_renders").resolve()
    print(f"Starting test renders in: {base_output}\n")

    t169 = render_hello_scene("16:9", base_output / "16_9")
    print(f"16:9 Render Complete:")
    print(f"  Path: {t169['output_path']}")
    print(f"  Time: {t169['render_time_seconds']}s")
    print(f"  Size: {t169['file_size_bytes']} bytes\n")

    t916 = render_hello_scene("9:16", base_output / "9_16")
    print(f"9:16 Render Complete:")
    print(f"  Path: {t916['output_path']}")
    print(f"  Time: {t916['render_time_seconds']}s")
    print(f"  Size: {t916['file_size_bytes']} bytes\n")


if __name__ == "__main__":
    main()
