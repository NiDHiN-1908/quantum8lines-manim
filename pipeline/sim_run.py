"""
CLI Runner for procedural simulation shorts.
Follows Milestone P1 Steps 4 and 5.
Usage:
    python -m pipeline.sim_run sims/ellipse_billiards --quality test|final
"""

import argparse
import json
import math
from pathlib import Path
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from core.sims.ellipse_billiards import (
    EllipseAxes,
    EllipseBilliardsSim,
    EventKind,
    SimEvent,
    SimSpec,
)
from core.sims.render import (
    QUALITY_PRESETS,
    SimulationRenderer,
    render_simulation_video,
)
from core.sims.sound import (
    build_and_normalize_audio,
    verify_audio_quality,
)


def get_media_duration(file_path: Path) -> float:
    """Uses ffprobe to extract duration in seconds."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(file_path),
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        return 0.0
    try:
        return float(res.stdout.strip())
    except ValueError:
        return 0.0


def extract_stage_frames(
    spec: SimSpec,
    video_path: Path,
    out_dir: Path,
) -> List[Path]:
    """
    Extracts one representative PNG frame at each count stage
    (at the focal convergence moment t = stage_t0 + 2*b) into out_dir.
    """
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted_frames: List[Path] = []

    cum_t = 0.0
    for idx, stage in enumerate(spec.schedule):
        # Convergence moment at F2: stage_t0 + 2*b
        conv_time = cum_t + 2.0 * spec.ellipse.b
        # Ensure timestamp does not exceed stage duration
        extract_time = min(cum_t + stage.duration_sec - 0.2, conv_time)

        frame_file = out_dir / f"frame_stage_{idx + 1:02d}_count_{stage.count:02d}.png"
        cmd = [
            "ffmpeg",
            "-y",
            "-nostdin",
            "-ss", f"{extract_time:.3f}",
            "-i", str(video_path),
            "-vframes", "1",
            str(frame_file),
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        if frame_file.is_file():
            extracted_frames.append(frame_file)

        cum_t += stage.duration_sec

    return extracted_frames


def run_sim_pipeline(
    sim_dir: Union[str, Path],
    quality: str = "test",
    outdir: Optional[Union[str, Path]] = None,
    extract_frames: bool = True,
) -> Dict[str, Any]:
    """
    Executes the full simulation short pipeline:
    1. Loads SimSpec
    2. Runs analytical simulation
    3. Renders video via Cairo + FFmpeg rawvideo pipe
    4. Synthesizes and normalizes procedural audio via loudnorm (-14 LUFS, <= -1.5 dBTP)
    5. Muxes video + audio into final MP4
    6. Runs verification checks
    7. Extracts stage frames if requested
    """
    sim_path = Path(sim_dir).resolve()
    spec_file = sim_path / "sim_spec.json"
    if not spec_file.is_file():
        raise FileNotFoundError(f"sim_spec.json not found in {sim_path}")

    with open(spec_file, "r", encoding="utf-8") as f:
        spec_data = json.load(f)
    spec = SimSpec.model_validate(spec_data)

    out_dir = Path(outdir) if outdir else Path("temp_renders/sim")
    out_dir.mkdir(parents=True, exist_ok=True)

    t_start_total = time.perf_counter()

    # 1. Simulation
    t0_sim = time.perf_counter()
    sim = EllipseBilliardsSim(axes=spec.ellipse, seed=spec.seed)
    events = sim.simulate_spec(spec)
    dur_sim = time.perf_counter() - t0_sim

    # 2. Video Rendering
    temp_video = out_dir / f"_temp_video_{sim_path.name}_{quality}.mp4"
    t0_render = time.perf_counter()
    render_simulation_video(
        spec=spec,
        output_path=temp_video,
        quality=quality,
        events=events,
    )
    dur_render = time.perf_counter() - t0_render

    # 3. Audio Synthesis & Normalization
    temp_audio = out_dir / f"_temp_audio_{sim_path.name}.wav"
    t0_audio = time.perf_counter()
    build_and_normalize_audio(
        spec=spec,
        events=events,
        output_path=temp_audio,
        total_duration=spec.total_duration,
        target_i=-14.0,
        target_tp=-1.5,
    )
    dur_audio = time.perf_counter() - t0_audio

    # 4. Muxing
    final_mp4 = out_dir / f"{sim_path.name}_916_{quality}.mp4"
    t0_mux = time.perf_counter()
    mux_cmd = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-i", str(temp_video),
        "-i", str(temp_audio),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        "-shortest",
        str(final_mp4),
    ]
    mux_proc = subprocess.run(mux_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    if mux_proc.returncode != 0:
        raise RuntimeError(f"FFmpeg muxing failed:\n{mux_proc.stderr}")
    dur_mux = time.perf_counter() - t0_mux

    # Cleanup temporary intermediate files
    temp_video.unlink(missing_ok=True)
    temp_audio.unlink(missing_ok=True)

    total_time = time.perf_counter() - t_start_total

    # 5. Verification Checks
    audio_qa = verify_audio_quality(final_mp4)
    file_size_bytes = final_mp4.stat().st_size
    file_size_mb = file_size_bytes / (1024.0 * 1024.0)
    actual_duration = get_media_duration(final_mp4)

    # 6. Extract stage frames if requested
    extracted_frames = []
    if extract_frames:
        frames_dir = out_dir / "frames"
        extracted_frames = extract_stage_frames(spec, final_mp4, frames_dir)

    report = {
        "simulation": sim_path.name,
        "quality": quality,
        "resolution": f"{QUALITY_PRESETS[quality]['width']}x{QUALITY_PRESETS[quality]['height']}",
        "output_file": str(final_mp4),
        "file_size_bytes": file_size_bytes,
        "file_size_mb": round(file_size_mb, 2),
        "expected_duration_sec": spec.total_duration,
        "actual_duration_sec": round(actual_duration, 2),
        "audio_qa": audio_qa,
        "timings_sec": {
            "simulation": round(dur_sim, 3),
            "video_render": round(dur_render, 2),
            "audio_build": round(dur_audio, 2),
            "muxing": round(dur_mux, 2),
            "total_pipeline": round(total_time, 2),
        },
        "event_counts": {
            "total_events": len(events),
            "bounces": sum(1 for e in events if e.kind == EventKind.BOUNCE),
            "focus_passes": sum(1 for e in events if e.kind == EventKind.PASS_FOCUS),
        },
        "extracted_frames": [str(f) for f in extracted_frames],
    }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Procedural Simulation Short Runner")
    parser.add_argument("sim_dir", type=str, help="Path to simulation directory (containing sim_spec.json)")
    parser.add_argument("--quality", choices=["test", "final"], default="test", help="Render quality (test or final)")
    parser.add_argument("--outdir", type=str, default="temp_renders/sim", help="Output directory")
    parser.add_argument("--extract-frames", action="store_true", default=True, help="Extract stage frames to outdir/frames")

    args = parser.parse_args()

    print("=" * 70)
    print("QUANTUM8LINES SIMULATION RUNNER")
    print(f"Simulation: {args.sim_dir}")
    print(f"Quality:    {args.quality}")
    print(f"Output dir: {args.outdir}")
    print("=" * 70)

    try:
        report = run_sim_pipeline(
            sim_dir=args.sim_dir,
            quality=args.quality,
            outdir=args.outdir,
            extract_frames=args.extract_frames,
        )

        print("\n[SUCCESS] Simulation run complete:")
        print(f" - Output File:     {report['output_file']}")
        print(f" - Resolution:      {report['resolution']}")
        print(f" - File Size:       {report['file_size_mb']} MB ({report['file_size_bytes']} bytes)")
        print(f" - Duration:        {report['actual_duration_sec']}s (Expected: {report['expected_duration_sec']}s)")
        print(f" - Integrated LUFS: {report['audio_qa']['integrated_lufs']} LUFS (Target: -14 +/- 1)")
        print(f" - True Peak:       {report['audio_qa']['true_peak']} dBTP (Target: <= -1.0)")
        print(f" - Peak Sample:     {report['audio_qa']['peak_sample']} (No clipping: {report['audio_qa']['no_clipping']})")
        print("\nPipeline Timing:")
        print(f" - Simulation:      {report['timings_sec']['simulation']}s")
        print(f" - Video Render:    {report['timings_sec']['video_render']}s")
        print(f" - Audio Build:     {report['timings_sec']['audio_build']}s")
        print(f" - Muxing:          {report['timings_sec']['muxing']}s")
        print(f" - Total Time:      {report['timings_sec']['total_pipeline']}s")

        if report.get("extracted_frames"):
            print(f"\nExtracted {len(report['extracted_frames'])} stage frames into:")
            print(f" - {Path(report['extracted_frames'][0]).parent}")

        print("=" * 70)

    except Exception as e:
        print(f"\n[ERROR] Simulation run failed: {e}")
        raise


if __name__ == "__main__":
    main()
