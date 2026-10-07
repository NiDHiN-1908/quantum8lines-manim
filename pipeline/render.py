"""
Rendering helper for Quantum8Lines animations (SPEC.md Section 8, Section 9, & Milestone M4b).
Renders chapters in test (low-res/fps) or final quality, catches BeatOverrunError as data,
and produces standardized outputs under <chapter_dir>/renders/<layout>/.
"""

from pathlib import Path
import shutil
import subprocess
import time
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel
from manim import config as manim_config

from core.layout import Layout, LAYOUT_169, LAYOUT_916, apply_layout
from core.scene_base import BaseScene, BeatOverrunError


class RenderResult(BaseModel):
    """Result of rendering a chapter scene."""

    success: bool
    video_path: Optional[str] = None
    duration: float = 0.0
    overrun_error: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    chapter_dir: str
    layout: str
    quality: str


def get_video_duration(video_path: Union[str, Path]) -> float:
    """Extract exact video container duration in seconds using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        res = subprocess.run(
            cmd, capture_output=True, text=True, check=True, timeout=10
        )
        return float(res.stdout.strip())
    except Exception:
        return 0.0


def render_chapter(
    chapter_dir: Union[str, Path],
    layout: Union[str, Layout] = "16:9",
    quality: str = "test",
) -> RenderResult:
    """
    Render a chapter scene in specified layout and quality.
    - layout: '16:9' / '169' or '9:16' / '916' (or Layout object).
    - quality: 'test' (480x270 / 270x480 at 15 fps) or 'final' (1080p at 30 fps).
    - If scene raises BeatOverrunError, catches it and returns it as data.
    """
    ch_path = Path(chapter_dir).resolve()
    scene_file = ch_path / "scene.py"
    if not scene_file.exists():
        return RenderResult(
            success=False,
            error=f"scene.py not found in {ch_path}",
            chapter_dir=str(ch_path),
            layout="unknown",
            quality=quality,
        )

    # 1. Resolve layout
    if isinstance(layout, Layout):
        base_layout = layout
        slug = "169" if base_layout.name in ("16:9", "169") else "916"
    elif str(layout) in ("16:9", "169"):
        base_layout = LAYOUT_169
        slug = "169"
    elif str(layout) in ("9:16", "916"):
        base_layout = LAYOUT_916
        slug = "916"
    else:
        raise ValueError(f"Unsupported layout: {layout}. Allowed: 16:9, 9:16")

    # 2. Resolve quality parameters
    if quality == "test":
        if slug == "169":
            pixel_width, pixel_height = 480, 270
        else:
            pixel_width, pixel_height = 270, 480
        fps = 15
    elif quality == "final":
        if slug == "169":
            pixel_width, pixel_height = 1920, 1080
        else:
            pixel_width, pixel_height = 1080, 1920
        fps = 30
    else:
        raise ValueError(f"Unsupported quality: '{quality}'. Allowed: 'test', 'final'")

    render_layout = Layout(
        name=base_layout.name,
        pixel_width=pixel_width,
        pixel_height=pixel_height,
        frame_width=base_layout.frame_width,
        frame_height=base_layout.frame_height,
        fps=fps,
        safe_top_px=base_layout.safe_top_px * (pixel_height / base_layout.pixel_height),
        safe_bottom_px=base_layout.safe_bottom_px
        * (pixel_height / base_layout.pixel_height),
        safe_left_px=base_layout.safe_left_px * (pixel_width / base_layout.pixel_width),
        safe_right_px=base_layout.safe_right_px
        * (pixel_width / base_layout.pixel_width),
        regions=base_layout.regions,
    )

    # 3. Setup output folder
    output_dir = ch_path / "renders" / slug
    output_dir.mkdir(parents=True, exist_ok=True)
    target_video_file = output_dir / f"scene_{slug}.mp4"

    # 4. Load scene class from scene.py
    try:
        scene_code = scene_file.read_text(encoding="utf-8")
        compiled = compile(scene_code, str(scene_file), "exec")
        mod_ns: Dict[str, Any] = {
            "__file__": str(scene_file),
            "__name__": "__main__",
        }
        exec(compiled, mod_ns)

        scene_cls = None
        for obj in mod_ns.values():
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseScene)
                and obj is not BaseScene
            ):
                scene_cls = obj
                break

        if scene_cls is None:
            return RenderResult(
                success=False,
                error="No BaseScene subclass found in scene.py",
                chapter_dir=str(ch_path),
                layout=slug,
                quality=quality,
            )
    except Exception as e:
        return RenderResult(
            success=False,
            error=f"Error compiling/loading scene.py: {type(e).__name__}: {str(e)}",
            chapter_dir=str(ch_path),
            layout=slug,
            quality=quality,
        )

    # 5. Configure Manim config
    apply_layout(manim_config, render_layout)
    manim_config.media_dir = str(output_dir / "_media")
    manim_config.output_file = str(target_video_file)
    manim_config.dry_run = False
    manim_config.verbosity = "WARNING"

    # 6. Render scene instance
    try:
        scene_inst = scene_cls(
            layout=render_layout,
            chapter_dir=ch_path,
        )
        scene_inst.render()
    except BeatOverrunError as e:
        return RenderResult(
            success=False,
            overrun_error={"beat_id": e.beat_id, "overrun_sec": e.overrun_sec},
            error=str(e),
            chapter_dir=str(ch_path),
            layout=slug,
            quality=quality,
        )
    except Exception as e:
        return RenderResult(
            success=False,
            error=f"Scene render error: {type(e).__name__}: {str(e)}",
            chapter_dir=str(ch_path),
            layout=slug,
            quality=quality,
        )

    # 7. Locate output video file
    actual_file: Optional[Path] = None
    if target_video_file.exists():
        actual_file = target_video_file
    else:
        try:
            writer_path = Path(scene_inst.renderer.file_writer.movie_file_path)
            if writer_path.exists():
                shutil.copy(writer_path, target_video_file)
                actual_file = target_video_file
        except Exception:
            pass

    if actual_file is None or not actual_file.exists():
        return RenderResult(
            success=False,
            error="Video file was not generated by renderer.",
            chapter_dir=str(ch_path),
            layout=slug,
            quality=quality,
        )

    duration = get_video_duration(actual_file)
    if duration <= 0.0:
        duration = float(getattr(scene_inst, "time", 0.0))

    return RenderResult(
        success=True,
        video_path=str(actual_file.resolve()),
        duration=round(duration, 3),
        chapter_dir=str(ch_path),
        layout=slug,
        quality=quality,
    )
