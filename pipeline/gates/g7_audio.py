"""
Quality Gate G7: Audio Verification (SPEC.md Section 9 & Milestone M4b).
Verifies:
- G7a_loudness: Integrated loudness is within 1 LU of -14 LUFS, and true peak <= -1.0 dBTP.
- G7b_no_clipping: Peak sample below 0.999 and no run of 3+ consecutive full-scale samples.
- G7c_caption_text: Caption text matches script text exactly (via check_caption_text).
- G7d_caption_timing: Caption timestamps are non-negative, in chronological order, and within audio duration.
"""

import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import soundfile as sf

from pipeline.audio_fx import measure_loudness
from pipeline.captions import check_caption_text
from pipeline.gates.models import Check, GateConfig, GateResult


def parse_ass_timestamp(ts: str) -> float:
    """Parse H:MM:SS.cc ASS timestamp into seconds."""
    parts = ts.strip().split(":")
    if len(parts) == 3:
        h = float(parts[0])
        m = float(parts[1])
        s = float(parts[2])
        return h * 3600.0 + m * 60.0 + s
    return 0.0


def parse_srt_timestamp(ts: str) -> float:
    """Parse HH:MM:SS,mmm SRT timestamp into seconds."""
    clean = ts.strip().replace(",", ".")
    parts = clean.split(":")
    if len(parts) == 3:
        h = float(parts[0])
        m = float(parts[1])
        s = float(parts[2])
        return h * 3600.0 + m * 60.0 + s
    return 0.0


def extract_caption_intervals(caption_file: Path) -> List[Tuple[float, float, str]]:
    """Extract (start_sec, end_sec, text) intervals from an ASS or SRT file."""
    if not caption_file.exists():
        return []

    intervals: List[Tuple[float, float, str]] = []
    content = caption_file.read_text(encoding="utf-8")

    if caption_file.suffix.lower() == ".ass" or "Dialogue:" in content:
        for line in content.splitlines():
            if line.startswith("Dialogue:"):
                parts = line.split(",", 9)
                if len(parts) >= 10:
                    start = parse_ass_timestamp(parts[1])
                    end = parse_ass_timestamp(parts[2])
                    text = re.sub(r"\{.*?\}", "", parts[9]).strip()
                    intervals.append((start, end, text))
    else:
        # SRT parsing
        srt_time_re = re.compile(
            r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})"
        )
        current_times = None
        current_text = []

        for line in content.splitlines():
            line_str = line.strip()
            m = srt_time_re.search(line_str)
            if m:
                if current_times is not None:
                    intervals.append((
                        current_times[0],
                        current_times[1],
                        " ".join(current_text),
                    ))
                    current_text = []
                current_times = (
                    parse_srt_timestamp(m.group(1)),
                    parse_srt_timestamp(m.group(2)),
                )
            elif current_times is not None:
                if line_str and not line_str.isdigit():
                    current_text.append(line_str)
                elif not line_str and current_times:
                    intervals.append((
                        current_times[0],
                        current_times[1],
                        " ".join(current_text),
                    ))
                    current_times = None
                    current_text = []

        if current_times is not None:
            intervals.append((
                current_times[0],
                current_times[1],
                " ".join(current_text),
            ))

    return intervals


def run_g7_audio(
    chapter_dir: Union[str, Path],
    audio_path: Optional[Union[str, Path]] = None,
    captions_path: Optional[Union[str, Path]] = None,
    script_data: Optional[Dict[str, Any]] = None,
    config: Optional[GateConfig] = None,
) -> GateResult:
    """
    Execute Quality Gate G7: Audio Verification.
    """
    cfg = config or GateConfig()
    ch_path = Path(chapter_dir).resolve()
    checks: List[Check] = []

    # 1. Resolve audio file
    if audio_path is None:
        for candidate in (
            ch_path / "audio" / "narration_mix.wav",
            ch_path / "audio" / "narration_postfx.wav",
            ch_path / "audio" / "narration.wav",
        ):
            if candidate.exists():
                audio_path = candidate
                break

    if audio_path is None or not Path(audio_path).exists():
        checks.append(
            Check(
                id="G7a_loudness",
                passed=False,
                severity="error",
                message=f"No audio file found in {ch_path / 'audio'}.",
            )
        )
        checks.append(
            Check(
                id="G7b_no_clipping",
                passed=False,
                severity="error",
                message="No audio file available for clipping check.",
            )
        )
        return GateResult.create("G7", checks)

    audio_file = Path(audio_path)

    # -----------------------------------------------------------------------
    # G7a_loudness
    # -----------------------------------------------------------------------
    try:
        meas = measure_loudness(audio_file)
        lufs = meas.get("input_i", -99.0)
        tp = meas.get("input_tp", 0.0)

        min_lufs = cfg.target_lufs - cfg.lufs_tolerance
        max_lufs = cfg.target_lufs + cfg.lufs_tolerance
        lufs_ok = min_lufs <= lufs <= max_lufs
        tp_ok = tp <= cfg.max_true_peak_dbtp + 0.05  # 0.05 dB numerical tolerance

        loudness_passed = lufs_ok and tp_ok
        details = {
            "measured_lufs": lufs,
            "target_lufs": cfg.target_lufs,
            "measured_tp": tp,
            "max_tp": cfg.max_true_peak_dbtp,
        }

        if loudness_passed:
            msg = f"Audio loudness compliant: {lufs:.2f} LUFS (target -14 +/- 1 LU), true peak {tp:.2f} dBTP (<= -1.0 dBTP)."
        else:
            reasons = []
            if not lufs_ok:
                reasons.append(
                    f"integrated loudness {lufs:.2f} LUFS outside target [{min_lufs:.1f}, {max_lufs:.1f}] LUFS"
                )
            if not tp_ok:
                reasons.append(
                    f"true peak {tp:.2f} dBTP exceeds limit {cfg.max_true_peak_dbtp:.1f} dBTP"
                )
            msg = f"Loudness non-compliant: {'; '.join(reasons)}."

        checks.append(
            Check(
                id="G7a_loudness",
                passed=loudness_passed,
                severity="error",
                message=msg,
                details=details,
            )
        )
    except Exception as e:
        checks.append(
            Check(
                id="G7a_loudness",
                passed=False,
                severity="error",
                message=f"Failed to measure loudness: {type(e).__name__}: {str(e)}",
            )
        )

    # -----------------------------------------------------------------------
    # G7b_no_clipping
    # -----------------------------------------------------------------------
    try:
        samples, sr = sf.read(str(audio_file))
        if samples.ndim > 1:
            samples = np.mean(samples, axis=1)

        peak = float(np.max(np.abs(samples)))
        audio_dur_sec = len(samples) / float(sr)

        # Check peak sample < 0.999
        peak_ok = peak < cfg.max_peak_sample

        # Check consecutive full-scale runs
        is_fs = (np.abs(samples) >= 0.999).astype(np.int8)
        kernel = np.ones(cfg.max_consecutive_full_scale, dtype=np.int8)
        runs = np.convolve(is_fs, kernel, mode="valid")
        run_count = int(np.sum(runs >= cfg.max_consecutive_full_scale))
        runs_ok = run_count == 0

        clipping_passed = peak_ok and runs_ok
        details_clip = {
            "peak_sample": round(peak, 4),
            "max_peak_allowed": cfg.max_peak_sample,
            "consecutive_runs": run_count,
        }

        if clipping_passed:
            msg_clip = f"No clipping detected (peak sample: {peak:.4f} < {cfg.max_peak_sample})."
        else:
            clip_errs = []
            if not peak_ok:
                clip_errs.append(
                    f"peak sample {peak:.4f} >= {cfg.max_peak_sample}"
                )
            if not runs_ok:
                clip_errs.append(
                    f"{run_count} runs of {cfg.max_consecutive_full_scale}+ consecutive full-scale samples"
                )
            msg_clip = f"Clipping detected: {'; '.join(clip_errs)}."

        checks.append(
            Check(
                id="G7b_no_clipping",
                passed=clipping_passed,
                severity="error",
                message=msg_clip,
                details=details_clip,
            )
        )
    except Exception as e:
        audio_dur_sec = 0.0
        checks.append(
            Check(
                id="G7b_no_clipping",
                passed=False,
                severity="error",
                message=f"Failed to check audio clipping: {type(e).__name__}: {str(e)}",
            )
        )

    # -----------------------------------------------------------------------
    # G7c_caption_text
    # -----------------------------------------------------------------------
    # Resolve script data
    if script_data is None:
        script_file = ch_path / "script.json"
        if script_file.exists():
            with open(script_file, "r", encoding="utf-8") as f:
                script_data = json.load(f)

    # Resolve captions file
    if captions_path is None:
        for cand in (
            ch_path / "captions" / "captions_169.ass",
            ch_path / "captions" / "captions_916.ass",
            ch_path / "captions" / "captions.ass",
            ch_path / "captions" / "captions.srt",
        ):
            if cand.exists():
                captions_path = cand
                break

    if script_data is not None and captions_path is not None and Path(captions_path).exists():
        cap_ok, cap_msg = check_caption_text(script_data, Path(captions_path))
        checks.append(
            Check(
                id="G7c_caption_text",
                passed=cap_ok,
                severity="error",
                message=cap_msg,
                details={"captions_path": str(captions_path)},
            )
        )
    else:
        checks.append(
            Check(
                id="G7c_caption_text",
                passed=True,
                severity="warning",
                message="Skipped caption text comparison: script or captions file not found.",
            )
        )

    # -----------------------------------------------------------------------
    # G7d_caption_timing
    # -----------------------------------------------------------------------
    if captions_path is not None and Path(captions_path).exists():
        intervals = extract_caption_intervals(Path(captions_path))
        timing_errors = []
        last_start = -1.0

        for idx, (c_start, c_end, c_text) in enumerate(intervals):
            if c_start < 0.0:
                timing_errors.append(f"Caption {idx} has negative start time ({c_start:.2f}s)")
            if c_end < c_start:
                timing_errors.append(
                    f"Caption {idx} end time ({c_end:.2f}s) is earlier than start ({c_start:.2f}s)"
                )
            if c_start < last_start - 0.05:
                timing_errors.append(
                    f"Caption {idx} start time ({c_start:.2f}s) is out of chronological order after ({last_start:.2f}s)"
                )
            if audio_dur_sec > 0.0 and c_end > audio_dur_sec + cfg.caption_timing_tolerance_sec:
                timing_errors.append(
                    f"Caption {idx} end time ({c_end:.2f}s) exceeds audio duration ({audio_dur_sec:.2f}s) by > {cfg.caption_timing_tolerance_sec}s"
                )
            last_start = max(last_start, c_start)

        timing_passed = len(timing_errors) == 0
        checks.append(
            Check(
                id="G7d_caption_timing",
                passed=timing_passed,
                severity="error",
                message=f"All {len(intervals)} caption timestamps are valid, chronological, and within audio bounds."
                if timing_passed
                else f"Caption timing error: {'; '.join(timing_errors[:3])}",
                details={"errors": timing_errors, "interval_count": len(intervals)}
                if not timing_passed
                else {"interval_count": len(intervals)},
            )
        )
    else:
        checks.append(
            Check(
                id="G7d_caption_timing",
                passed=True,
                severity="warning",
                message="Skipped caption timing check: captions file not found.",
            )
        )

    return GateResult.create("G7", checks)
