"""
Audio loudness normalization, post-processing FX, and ducked mixing.
Follows SPEC.md Section 10 and Milestone M3b Step 1.
Targets -14 LUFS integrated, true peak <= -1 dBTP via two-pass FFmpeg loudnorm.
"""

from pathlib import Path
import json
import subprocess
from typing import Dict, Any, Union, Optional


# Subtle postfx filter chains documented in docs/audio.md
POSTFX_PRESETS: Dict[str, Optional[str]] = {
    "clean": "highpass=f=70",
    "warm_narration": (
        "highpass=f=70,"
        "equalizer=f=200:t=q:w=1.0:g=1.5,"
        "acompressor=threshold=-18dB:ratio=2.5:attack=20:release=150"
    ),
    "none": None,
}


def measure_loudness(path: Union[str, Path]) -> Dict[str, float]:
    """
    Measures audio loudness using FFmpeg's loudnorm filter in measurement mode.
    Returns:
        integrated_lufs: Integrated loudness in LUFS (input_i)
        true_peak: True peak in dBTP (input_tp)
        lra: Loudness range in LU (input_lra)
        threshold: Measured threshold (input_thresh)
        target_offset: Target offset (target_offset)
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Audio file not found: {p}")

    cmd = [
        "ffmpeg", "-nostdin",
        "-i", str(p),
        "-af", "loudnorm=I=-14:TP=-1.0:LRA=11:print_format=json",
        "-f", "null", "-"
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    err = proc.stderr
    start_idx = err.rfind("{")
    end_idx = err.rfind("}") + 1
    if start_idx == -1 or end_idx == 0:
        raise RuntimeError(f"Failed to parse loudnorm JSON from FFmpeg output:\n{err}")

    raw_json = err[start_idx:end_idx]
    data = json.loads(raw_json)

    return {
        "integrated_lufs": float(data.get("input_i", -99.0)),
        "true_peak": float(data.get("input_tp", -99.0)),
        "lra": float(data.get("input_lra", 0.0)),
        "threshold": float(data.get("input_thresh", -99.0)),
        "target_offset": float(data.get("target_offset", 0.0)),
    }


def apply_postfx(
    path_in: Union[str, Path],
    path_out: Union[str, Path],
    preset: str = "warm_narration",
) -> Path:
    """
    Applies an FFmpeg audio post-processing preset filter chain.
    """
    p_in = Path(path_in)
    p_out = Path(path_out)
    p_out.parent.mkdir(parents=True, exist_ok=True)

    filter_chain = POSTFX_PRESETS.get(preset)
    if not filter_chain:
        # No filter; direct copy/transcode
        cmd = ["ffmpeg", "-y", "-nostdin", "-i", str(p_in), str(p_out)]
    else:
        cmd = [
            "ffmpeg", "-y", "-nostdin",
            "-i", str(p_in),
            "-af", filter_chain,
            str(p_out),
        ]

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg apply_postfx failed:\n{proc.stderr}")

    return p_out


def normalize(
    path_in: Union[str, Path],
    path_out: Union[str, Path],
    target_i: float = -14.0,
    target_tp: float = -1.0,
    postfx: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Performs two-pass loudnorm normalization to target_i LUFS and target_tp dBTP.
    Optionally prepends a postfx filter chain in the second pass.
    Preserves video streams if input is a video file.
    Returns:
        {"before": dict, "after": dict}
    """
    p_in = Path(path_in)
    p_out = Path(path_out)
    p_out.parent.mkdir(parents=True, exist_ok=True)

    # Pass 1: Measure
    before_stats = measure_loudness(p_in)

    # Build second pass filter string
    meas_i = before_stats["integrated_lufs"]
    meas_tp = before_stats["true_peak"]
    meas_lra = before_stats["lra"]
    meas_thresh = before_stats["threshold"]
    offset = before_stats["target_offset"]

    loudnorm_filter = (
        f"loudnorm=I={target_i:.1f}:TP={target_tp:.1f}:LRA=11:"
        f"measured_I={meas_i:.2f}:measured_TP={meas_tp:.2f}:"
        f"measured_LRA={meas_lra:.2f}:measured_thresh={meas_thresh:.2f}:"
        f"offset={offset:.2f}:linear=true"
    )

    if postfx and postfx in POSTFX_PRESETS and POSTFX_PRESETS[postfx]:
        af_chain = f"{POSTFX_PRESETS[postfx]},{loudnorm_filter}"
    else:
        af_chain = loudnorm_filter

    # Check if input is video (.mp4, .mov, .mkv)
    is_video = p_in.suffix.lower() in [".mp4", ".mov", ".mkv", ".webm"]
    is_video_out = p_out.suffix.lower() in [".mp4", ".mov", ".mkv", ".webm"]

    cmd = ["ffmpeg", "-y", "-nostdin", "-i", str(p_in)]
    if is_video and is_video_out:
        cmd.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"])
    elif p_out.suffix.lower() == ".wav":
        cmd.extend(["-c:a", "pcm_s16le"])

    cmd.extend(["-af", af_chain, str(p_out)])

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"FFmpeg loudnorm pass 2 failed:\n{proc.stderr}")

    # Pass 3: Measure result to verify
    after_stats = measure_loudness(p_out)

    return {
        "before": before_stats,
        "after": after_stats,
    }


def mix(
    narration: Union[str, Path],
    music: Optional[Union[str, Path]] = None,
    out: Union[str, Path] = "mixed.wav",
    duck_music_db: float = -18.0,
) -> Path:
    """
    Mixes narration with optional background music:
    - Normalizes narration to -14 LUFS / -1 dBTP.
    - If music is provided, scales music down and ducks under voice with sidechain compression.
    - Conjoins voice and ducked music using amix, normalized to -14 LUFS.
    """
    p_narr = Path(narration)
    p_out = Path(out)
    p_out.parent.mkdir(parents=True, exist_ok=True)

    if not p_narr.exists():
        raise FileNotFoundError(f"Narration file not found: {p_narr}")

    if music is None:
        normalize(p_narr, p_out)
        return p_out

    p_music = Path(music)
    if not p_music.exists():
        raise FileNotFoundError(f"Music file not found: {p_music}")

    # Temporary normalized narration
    temp_narr = p_out.parent / f"_temp_norm_narr_{p_out.stem}.wav"
    temp_mix = p_out.parent / f"_temp_mix_{p_out.stem}.wav"

    try:
        normalize(p_narr, temp_narr)

        # Complex filter graph:
        # 1. Volume reduction on music [0:a] -> [bg_music]
        # 2. Voice split into main audio and sidechain control [1:a] -> [voice_main][voice_sc]
        # 3. Sidechain compression: ducks bg_music when voice_sc is active
        # 4. amix joins voice_main and ducked music, ending when narration ends
        filter_complex = (
            f"[0:a]volume={duck_music_db}dB[bg_music];"
            f"[1:a]asplit=2[voice_main][voice_sc];"
            f"[bg_music][voice_sc]sidechaincompress=threshold=0.08:ratio=4:attack=50:release=300[ducked_music];"
            f"[voice_main][ducked_music]amix=inputs=2:duration=first:dropout_transition=2[mixed]"
        )

        cmd = [
            "ffmpeg", "-y", "-nostdin",
            "-i", str(p_music),
            "-i", str(temp_narr),
            "-filter_complex", filter_complex,
            "-map", "[mixed]",
            "-c:a", "pcm_s16le",
            str(temp_mix)
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg ducking mix failed:\n{proc.stderr}")

        # Final normalization of the mix to -14 LUFS
        normalize(temp_mix, p_out)
        return p_out

    finally:
        if temp_narr.exists():
            temp_narr.unlink(missing_ok=True)
        if temp_mix.exists():
            temp_mix.unlink(missing_ok=True)


def normalize_intro_files(build_dir: Path = Path("build")) -> Dict[str, Any]:
    """
    Normalizes intro video files in build/ to -14 LUFS / -1 dBTP in-place (via temp file).
    Reports LUFS and true peak before and after.
    """
    candidates = [
        build_dir / "intro_169.mp4",
        build_dir / "intro_916_candidate_a.mp4",
        build_dir / "intro_916_candidate_b.mp4",
    ]
    report = {}

    for path in candidates:
        if not path.exists():
            continue
        temp_out = path.parent / f"_norm_{path.name}"
        res = normalize(path, temp_out)
        # Replace original with normalized file
        temp_out.replace(path)
        report[path.name] = res

    return report
