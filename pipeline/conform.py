"""
Intro and outro conforming pipeline for Quantum8Lines (Milestone M1).
Conforms brand/Quantum8Line_Intro.mp4 to:
  - 16:9 (1920x1080, 30 fps, H.264, AAC 48 kHz)
  - 9:16 (1080x1920, 30 fps, 3s sting with blurred background, candidates A & B)
Measures integrated loudness via FFmpeg loudnorm.
"""

from pathlib import Path
import subprocess
import json
from typing import Dict, Any

DEFAULT_INPUT = Path("brand/Quantum8Line_Intro.mp4")
DEFAULT_BUILD_DIR = Path("build")


def measure_loudness(media_path: Path) -> Dict[str, Any]:
    """
    Measure integrated loudness (LUFS) and true peak (dBTP) using ffmpeg loudnorm.
    Does not modify the media file.
    """
    cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-i", str(media_path),
        "-af", "loudnorm=print_format=json",
        "-f", "null", "-"
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stderr = proc.stderr

    # Locate JSON output block in stderr
    start_idx = stderr.find("{")
    end_idx = stderr.rfind("}") + 1
    if start_idx == -1 or end_idx == 0:
        raise RuntimeError(f"Could not parse loudnorm JSON output from ffmpeg:\n{stderr[-400:]}")

    data = json.loads(stderr[start_idx:end_idx])
    return {
        "integrated_lufs": float(data.get("input_i", 0.0)),
        "true_peak_dbtp": float(data.get("input_tp", 0.0)),
        "lra": float(data.get("input_lra", 0.0)),
        "threshold": float(data.get("input_thresh", 0.0)),
    }


def conform_intro(
    format_type: str,
    input_path: Path = DEFAULT_INPUT,
    output_dir: Path = DEFAULT_BUILD_DIR
) -> Dict[str, Any]:
    """
    Conform intro video for target aspect ratio.
    format_type: '169' (or '16:9') -> 1920x1080, 30 fps, H.264, AAC 48 kHz.
                 '916' (or '9:16') -> 1080x1920, 30 fps, 3s sting candidates A (0-3s) & B (7-10s).
    Outputs saved in output_dir (default: build/).
    """
    input_path = Path(input_path).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    if not input_path.exists():
        raise FileNotFoundError(f"Source intro file not found: {input_path}")

    fmt = format_type.replace(":", "")

    if fmt == "169":
        output_file = output_dir / "intro_169.mp4"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", "scale=1920:1080:flags=lanczos,fps=30",
            "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
            str(output_file)
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg failed conforming 16:9 intro:\n{proc.stderr[-400:]}")

        loudness = measure_loudness(output_file)
        return {
            "format": "16:9",
            "path": str(output_file),
            "file_size_bytes": output_file.stat().st_size,
            "loudness": loudness,
        }

    elif fmt == "916":
        # 9:16 filter: foreground centered over blurred, darkened, scaled-to-fill background
        filtergraph = (
            "[0:v]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=25:5,eq=brightness=-0.35[bg];"
            "[0:v]scale=1080:-2[fg];"
            "[bg][fg]overlay=(W-w)/2:(H-h)/2,fps=30[v]"
        )

        candidates = {
            "candidate_a": {"start": 0.0, "duration": 3.0, "filename": "intro_916_candidate_a.mp4"},
            "candidate_b": {"start": 7.0, "duration": 3.0, "filename": "intro_916_candidate_b.mp4"},
        }

        results = {}
        for key, spec in candidates.items():
            output_file = output_dir / spec["filename"]
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(spec["start"]),
                "-t", str(spec["duration"]),
                "-i", str(input_path),
                "-filter_complex", filtergraph,
                "-map", "[v]", "-map", "0:a",
                "-c:v", "libx264", "-preset", "fast", "-crf", "18", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-ar", "48000", "-b:a", "192k",
                str(output_file)
            ]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if proc.returncode != 0:
                raise RuntimeError(f"FFmpeg failed conforming 9:16 {key}:\n{proc.stderr[-400:]}")

            loudness = measure_loudness(output_file)
            results[key] = {
                "name": key,
                "time_range": f"{spec['start']}-{spec['start'] + spec['duration']}s",
                "path": str(output_file),
                "file_size_bytes": output_file.stat().st_size,
                "loudness": loudness,
            }

        return {
            "format": "9:16",
            "candidates": results,
        }

    else:
        raise ValueError(f"Unknown format_type '{format_type}'. Expected '169' or '916'.")


def main():
    print("=" * 60)
    print("CONFORMING INTROS (Milestone M1)")
    print("=" * 60)

    # 1. 16:9 Conform
    print("\n1. Conforming 16:9 Intro (1920x1080, 30fps)...")
    res_169 = conform_intro("169")
    print(f"  Output: {res_169['path']}")
    print(f"  Size: {res_169['file_size_bytes']} bytes")
    print(f"  Integrated Loudness: {res_169['loudness']['integrated_lufs']} LUFS")
    print(f"  True Peak: {res_169['loudness']['true_peak_dbtp']} dBTP")

    # 2. 9:16 Stings
    print("\n2. Conforming 9:16 Stings (1080x1920, 30fps, 3s)...")
    res_916 = conform_intro("916")
    cand_a = res_916["candidates"]["candidate_a"]
    print(f"  Candidate A (t={cand_a['time_range']}):")
    print(f"    Output: {cand_a['path']}")
    print(f"    Size: {cand_a['file_size_bytes']} bytes")
    print(f"    Integrated Loudness: {cand_a['loudness']['integrated_lufs']} LUFS")
    print(f"    True Peak: {cand_a['loudness']['true_peak_dbtp']} dBTP")

    cand_b = res_916["candidates"]["candidate_b"]
    print(f"  Candidate B (t={cand_b['time_range']}):")
    print(f"    Output: {cand_b['path']}")
    print(f"    Size: {cand_b['file_size_bytes']} bytes")
    print(f"    Integrated Loudness: {cand_b['loudness']['integrated_lufs']} LUFS")
    print(f"    True Peak: {cand_b['loudness']['true_peak_dbtp']} dBTP")

    print("\n" + "=" * 60)
    print("CONFORM COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
