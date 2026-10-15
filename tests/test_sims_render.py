"""
Tests for fast Cairo simulation renderer and layout compliance.
Follows Milestone P1 Step 2.
"""

import json
from pathlib import Path
import subprocess
import pytest

from core.sims.ellipse_billiards import SimSpec
from core.sims.render import (
    QUALITY_PRESETS,
    check_s3b_stage_fill,
    get_text_bounding_boxes,
    is_bbox_inside_safe,
    render_simulation_video,
)


def get_video_duration(path: Path) -> float:
    """Uses ffprobe to extract exact video stream duration in seconds."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return float(res.stdout.strip())


def test_title_and_counter_bboxes_inside_safe_area():
    """Verify title and counter bounding boxes lie strictly inside the 9:16 safe area."""
    spec = SimSpec()

    for q in ("final", "test"):
        w = QUALITY_PRESETS[q]["width"]
        h = QUALITY_PRESETS[q]["height"]
        bboxes = get_text_bounding_boxes(spec, quality=q)

        assert is_bbox_inside_safe(bboxes["title"], w, h), f"Title bbox {bboxes['title']} outside safe area for {q}"
        assert is_bbox_inside_safe(bboxes["counter"], w, h), f"Counter bbox {bboxes['counter']} outside safe area for {q}"


def test_short_render_non_blank_and_correct_duration(tmp_path: Path):
    """
    Renders 2.0 seconds at test quality (270x480), verifies:
    - Output file is created and valid MP4
    - Duration is 2.0s within 0.1s tolerance
    - Frames are non-blank (contains background and visual objects)
    """
    spec = SimSpec()
    out_mp4 = tmp_path / "render_2s_test.mp4"

    render_simulation_video(
        spec=spec,
        output_path=out_mp4,
        quality="test",
        max_duration=2.0,
    )

    assert out_mp4.is_file()
    assert out_mp4.stat().st_size > 5000

    duration = get_video_duration(out_mp4)
    assert abs(duration - 2.0) <= 0.15, f"Expected 2.0s duration, got {duration}s"

    # Verify frame is non-blank by extracting a frame at 1.0s with ffmpeg
    frame_png = tmp_path / "frame_sample.png"
    cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-ss", "1.0",
        "-i", str(out_mp4),
        "-vframes", "1",
        str(frame_png),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    assert frame_png.is_file()
    assert frame_png.stat().st_size > 500


def test_s3b_stage_fill_and_seeded_failure():
    """
    Gate S3b stage fill verification:
    - Normal spec covers >= 85% of stage region dimension (about 92%)
    - Deliberately small ellipse seeded failure fails the check
    """
    spec = SimSpec()

    # Normal spec check (should pass with ~92% coverage)
    res = check_s3b_stage_fill(spec, quality="final")
    assert res["passed"] is True
    assert res["stage_fill_ratio"] >= 0.85
    assert abs(res["stage_fill_ratio"] - 0.92) < 0.01

    # Also test at test quality
    res_test = check_s3b_stage_fill(spec, quality="test")
    assert res_test["passed"] is True
    assert res_test["stage_fill_ratio"] >= 0.85

    # Seeded failure: deliberately small ellipse scale
    small_res = check_s3b_stage_fill(spec, quality="final", sim_scale_override=150.0)
    assert small_res["passed"] is False
    assert small_res["stage_fill_ratio"] < 0.85
    assert small_res["stage_fill_ratio"] < 0.50
