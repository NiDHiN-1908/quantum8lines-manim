"""
Quality Gate G5: Render Test Verification (SPEC.md Section 9 & Milestone M4b).
Verifies:
- G5a_render_succeeds: Low-res render succeeds and video file is generated.
- G5b_no_empty_frames: No more than 15% of frames sampled every 0.5s are blank (< 0.2% diff from BACKGROUND).
- G5c_duration_matches_audio: Video duration is within 0.3s of narration audio duration.
- G5d_beat_overrun: Reports beat overruns if scene animation exceeded audio windows.
"""

import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
from PIL import Image

from pipeline.gates.models import Check, GateConfig, GateResult
from pipeline.render import RenderResult, render_chapter

# RGB value of BACKGROUND token #0e0e11
BACKGROUND_RGB = np.array([14, 14, 17], dtype=np.int16)


def sample_frames_and_check_blank(
    video_path: Union[str, Path],
    config: GateConfig,
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Sample video frames every config.empty_frame_sample_sec seconds using FFmpeg.
    A frame is 'blank' if fewer than config.blank_pixel_diff_threshold (0.2%) of pixels
    differ from BACKGROUND (#0e0e11).
    Fails if blank frame fraction exceeds config.max_blank_frame_fraction (15%).
    """
    video_p = Path(video_path)
    if not video_p.exists():
        return False, f"Video file {video_p} does not exist.", {}

    with tempfile.TemporaryDirectory(prefix="g5_frames_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        frame_pattern = tmp_path / "frame_%04d.png"
        sample_fps = 1.0 / max(0.1, config.empty_frame_sample_sec)

        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            str(video_p),
            "-vf",
            f"fps={sample_fps}",
            str(frame_pattern),
        ]
        try:
            subprocess.run(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=True,
                timeout=30,
            )
        except Exception as e:
            return (
                False,
                f"FFmpeg frame sampling failed: {type(e).__name__}: {str(e)}",
                {},
            )

        frame_files = sorted(tmp_path.glob("frame_*.png"))
        if not frame_files:
            return False, "No frames were extracted from video file.", {}

        blank_count = 0
        total_frames = len(frame_files)

        for fpath in frame_files:
            try:
                with Image.open(fpath) as img:
                    arr = np.array(img.convert("RGB"), dtype=np.int16)
                diff = np.abs(arr - BACKGROUND_RGB)
                is_differing = np.any(diff > 3, axis=-1)
                diff_ratio = float(np.mean(is_differing))
                if diff_ratio < config.blank_pixel_diff_threshold:
                    blank_count += 1
            except Exception:
                blank_count += 1

        blank_fraction = blank_count / float(total_frames)
        passed = blank_fraction <= config.max_blank_frame_fraction
        details = {
            "total_frames": total_frames,
            "blank_count": blank_count,
            "blank_fraction": round(blank_fraction, 4),
            "threshold_fraction": config.max_blank_frame_fraction,
            "pixel_diff_threshold": config.blank_pixel_diff_threshold,
        }

        if passed:
            msg = (
                f"Frame emptiness check passed: {blank_count}/{total_frames} "
                f"({blank_fraction * 100:.1f}%) blank frames (<= {config.max_blank_frame_fraction * 100:.0f}% allowed)."
            )
        else:
            msg = (
                f"Too many empty frames: {blank_count}/{total_frames} "
                f"({blank_fraction * 100:.1f}%) blank frames exceeds limit of {config.max_blank_frame_fraction * 100:.0f}%."
            )

        return passed, msg, details


def get_expected_audio_duration(chapter_dir: Path) -> Optional[float]:
    """Retrieve expected narration audio duration from timings.json or audio file."""
    timings_path = chapter_dir / "audio" / "timings.json"
    if not timings_path.exists():
        timings_path = chapter_dir / "timings.json"
    if timings_path.exists():
        try:
            with open(timings_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "total_duration" in data:
                return float(data["total_duration"])
            lines = data.get("lines", [])
            if lines:
                return float(max(l.get("end", 0.0) for l in lines))
        except Exception:
            pass

    audio_file = chapter_dir / "audio" / "narration.wav"
    if audio_file.exists():
        try:
            cmd = [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(audio_file),
            ]
            res = subprocess.run(
                cmd, capture_output=True, text=True, check=True, timeout=5
            )
            return float(res.stdout.strip())
        except Exception:
            pass

    return None


def run_g5_render(
    chapter_dir: Union[str, Path],
    render_result: Optional[RenderResult] = None,
    layout: str = "16:9",
    quality: str = "test",
    config: Optional[GateConfig] = None,
    gate_id: Optional[str] = None,
) -> GateResult:
    """
    Execute Quality Gate G5: Render Test on chapter.
    """
    cfg = config or GateConfig()
    ch_path = Path(chapter_dir).resolve()
    checks: List[Check] = []

    # 1. Render if result not provided
    if render_result is None:
        render_result = render_chapter(ch_path, layout=layout, quality=quality)

    # Check G5d_beat_overrun
    if render_result.overrun_error is not None:
        ov = render_result.overrun_error
        checks.append(
            Check(
                id="G5d_beat_overrun",
                passed=False,
                severity="error",
                message=f"Beat '{ov.get('beat_id')}' overran its allocated audio window by {ov.get('overrun_sec', 0.0):.4f}s.",
                details=ov,
            )
        )
    else:
        checks.append(
            Check(
                id="G5d_beat_overrun",
                passed=True,
                severity="error",
                message="No beat overruns detected during scene render.",
            )
        )

    # Check G5a_render_succeeds
    render_ok = render_result.success and render_result.video_path is not None
    checks.append(
        Check(
            id="G5a_render_succeeds",
            passed=render_ok,
            severity="error",
            message=f"Render succeeded: video output at {render_result.video_path}"
            if render_ok
            else f"Render failed: {render_result.error}",
            details={"video_path": render_result.video_path, "error": render_result.error},
        )
    )

    if not render_ok or render_result.video_path is None:
        # Cannot run visual and duration checks without video
        checks.append(
            Check(
                id="G5b_no_empty_frames",
                passed=False,
                severity="error",
                message="Skipped empty frame check because render failed.",
            )
        )
        checks.append(
            Check(
                id="G5c_duration_matches_audio",
                passed=False,
                severity="error",
                message="Skipped duration check because render failed.",
            )
        )
        return GateResult.create(gate_id or "G5", checks)

    # Check G5b_no_empty_frames
    no_empty_passed, empty_msg, empty_details = sample_frames_and_check_blank(
        render_result.video_path, cfg
    )
    checks.append(
        Check(
            id="G5b_no_empty_frames",
            passed=no_empty_passed,
            severity="error",
            message=empty_msg,
            details=empty_details,
        )
    )

    # Check G5c_duration_matches_audio
    expected_audio_dur = get_expected_audio_duration(ch_path)
    if expected_audio_dur is not None:
        diff_sec = abs(render_result.duration - expected_audio_dur)
        dur_passed = diff_sec <= cfg.duration_match_tolerance_sec
        checks.append(
            Check(
                id="G5c_duration_matches_audio",
                passed=dur_passed,
                severity="error",
                message=f"Video duration ({render_result.duration:.2f}s) matches audio duration ({expected_audio_dur:.2f}s) within {cfg.duration_match_tolerance_sec}s tolerance."
                if dur_passed
                else f"Video duration ({render_result.duration:.2f}s) differs from audio duration ({expected_audio_dur:.2f}s) by {diff_sec:.2f}s (> {cfg.duration_match_tolerance_sec}s tolerance).",
                details={
                    "video_duration": render_result.duration,
                    "audio_duration": expected_audio_dur,
                    "difference_sec": round(diff_sec, 3),
                    "tolerance_sec": cfg.duration_match_tolerance_sec,
                },
            )
        )
    else:
        checks.append(
            Check(
                id="G5c_duration_matches_audio",
                passed=True,
                severity="warning",
                message=f"No audio timings found in {ch_path}; video duration is {render_result.duration:.2f}s.",
            )
        )

    return GateResult.create(gate_id or "G5", checks)
