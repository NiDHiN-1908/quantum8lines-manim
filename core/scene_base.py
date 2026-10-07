"""
Base scene class and minimal HelloScene for Quantum8Lines.
Supports 16:9 and 9:16 aspect ratios based on SPEC.md section 4.3.
"""

from contextlib import contextmanager
import json
from pathlib import Path
import time
from typing import Any, Dict, List, NamedTuple, Optional, Union
from manim import (
    Scene,
    Mobject,
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


class BeatOverrunError(Exception):
    """Raised when scene animations exceed the audio time window allocated for a beat."""

    def __init__(self, beat_id: str, overrun_sec: float):
        self.beat_id = beat_id
        self.overrun_sec = overrun_sec
        super().__init__(
            f"Beat '{beat_id}' overran its allocated audio window by {overrun_sec:.4f}s. "
            "Revise the storyboard/scene animation rather than stretching audio."
        )


class BeatSnapshot(NamedTuple):
    beat_id: str
    timestamp: float
    mobjects: Dict[str, Dict[str, Any]]


def get_mobject_bbox(mob: Mobject) -> List[float]:
    """Return bounding box in Manim coordinates [x_min, y_min, x_max, y_max]."""
    try:
        left = float(mob.get_left()[0])
        bottom = float(mob.get_bottom()[1])
        right = float(mob.get_right()[0])
        top = float(mob.get_top()[1])
        return [round(left, 4), round(bottom, 4), round(right, 4), round(top, 4)]
    except Exception:
        return [0.0, 0.0, 0.0, 0.0]


class BaseScene(Scene):
    """
    Base Scene class for Quantum8Lines animations.
    Supports audio-first timing via storyboard and timings data,
    registering scene mobjects per beat, and capturing visual snapshots.
    """

    layout: Layout = LAYOUT_169

    def __init__(
        self,
        layout: Optional[Layout] = None,
        chapter_dir: Optional[Union[str, Path]] = None,
        script_data: Optional[Dict[str, Any]] = None,
        storyboard_data: Optional[Dict[str, Any]] = None,
        timings_data: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        if layout is not None:
            self.layout = layout
        super().__init__(**kwargs)

        self.chapter_dir: Optional[Path] = (
            Path(chapter_dir) if chapter_dir is not None else None
        )
        self.script_data: Optional[Dict[str, Any]] = script_data
        self.storyboard_data: Optional[Dict[str, Any]] = storyboard_data
        self.timings_data: Optional[Dict[str, Any]] = timings_data
        self.snapshots: List[BeatSnapshot] = []
        self._registered_mobjects: Dict[str, Dict[str, Any]] = {}

        if self.chapter_dir is not None:
            self._load_chapter_data()

    def _load_chapter_data(self) -> None:
        """Load script.json, audio/timings.json, and storyboard.json from chapter_dir."""
        if self.chapter_dir is None or not self.chapter_dir.exists():
            return

        script_file = self.chapter_dir / "script.json"
        if self.script_data is None and script_file.exists():
            with open(script_file, "r", encoding="utf-8") as f:
                self.script_data = json.load(f)

        timings_file = self.chapter_dir / "audio" / "timings.json"
        if not timings_file.exists():
            timings_file = self.chapter_dir / "timings.json"
        if self.timings_data is None and timings_file.exists():
            with open(timings_file, "r", encoding="utf-8") as f:
                self.timings_data = json.load(f)

        storyboard_file = self.chapter_dir / "storyboard.json"
        if self.storyboard_data is None and storyboard_file.exists():
            with open(storyboard_file, "r", encoding="utf-8") as f:
                self.storyboard_data = json.load(f)

    def register(
        self,
        name: str,
        mob: Mobject,
        essential: bool = False,
        kind: str = "object",
    ) -> None:
        """
        Track a mobject for quality gate snapshot inspections.
        Allowed kinds: 'object', 'text', 'character'.
        """
        if kind not in ("object", "text", "character"):
            raise ValueError(
                f"Invalid kind '{kind}'. Allowed kinds: 'object', 'text', 'character'"
            )
        self._registered_mobjects[name] = {
            "mob": mob,
            "name": name,
            "essential": essential,
            "kind": kind,
        }

    def unregister(self, name: str) -> None:
        """Remove a mobject from registered snapshot tracking."""
        self._registered_mobjects.pop(name, None)

    def _capture_snapshot(self, beat_id: str) -> BeatSnapshot:
        mobjects_info: Dict[str, Dict[str, Any]] = {}
        for name, item in self._registered_mobjects.items():
            mob = item["mob"]
            bbox = get_mobject_bbox(mob)
            color_str = ""
            if hasattr(mob, "color") and mob.color is not None:
                color_str = getattr(mob.color, "hex", str(mob.color))
            mobjects_info[name] = {
                "name": name,
                "kind": item["kind"],
                "essential": item["essential"],
                "bbox": bbox,
                "color": color_str,
            }
        snap = BeatSnapshot(
            beat_id=beat_id,
            timestamp=float(round(self.time, 4)),
            mobjects=mobjects_info,
        )
        self.snapshots.append(snap)
        return snap

    @contextmanager
    def beat(self, beat_id: str):
        """
        Context manager for an animation beat.
        Resolves audio window for beat_id (from storyboard line_ids + timings timestamps).
        Measures elapsed animation time:
        - If elapsed < window duration: pads with self.wait(window_duration - elapsed).
        - If elapsed > window duration: raises BeatOverrunError(beat_id, overrun_sec).
        - At end of beat, records snapshot into self.snapshots.
        """
        window_duration: Optional[float] = None

        if self.storyboard_data is not None and self.timings_data is not None:
            beats = self.storyboard_data.get("beats", [])
            beat_info = next((b for b in beats if b.get("id") == beat_id), None)
            if beat_info is None:
                raise KeyError(f"Beat '{beat_id}' not found in storyboard.")

            line_ids = beat_info.get("line_ids", [])
            lines = self.timings_data.get("lines", [])
            matching_lines = [l for l in lines if l.get("id") in line_ids]

            if matching_lines:
                start_time = min(l["start"] for l in matching_lines)
                end_time = max(l["end"] + l.get("pause_after", 0.0) for l in matching_lines)
                window_duration = end_time - start_time
            elif "duration" in beat_info:
                window_duration = float(beat_info["duration"])

        t_start = self.time
        try:
            yield
        finally:
            t_elapsed = self.time - t_start

            if window_duration is not None:
                tol = 1e-3  # 1 ms numerical tolerance
                if t_elapsed > window_duration + tol:
                    overrun_sec = round(t_elapsed - window_duration, 4)
                    raise BeatOverrunError(beat_id, overrun_sec)
                elif t_elapsed < window_duration - tol:
                    pad_time = window_duration - t_elapsed
                    self.wait(pad_time)

            self._capture_snapshot(beat_id)

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
