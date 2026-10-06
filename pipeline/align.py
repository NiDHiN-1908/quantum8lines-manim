"""
Forced word-level audio alignment using faster-whisper.
Follows SPEC.md Section 8, 10, 11 and Milestone M3a Step 4.
Aligns each line wav with the 'small' model, tries CUDA first with CPU fallback,
writes word timestamps into timings.json, and computes Word Error Rate (WER).
"""

from pathlib import Path
import json
import re
import time
from typing import Dict, Any, List, Tuple, Optional
from faster_whisper import WhisperModel


def compute_wer(reference: str, hypothesis: str) -> float:
    """
    Computes standard Word Error Rate (WER) using Levenshtein distance on words.
    WER = (S + D + I) / N_ref.
    Both texts are normalized (lowercased, punctuation stripped).
    """
    ref_words = re.sub(r"[^\w\s]", "", reference).lower().split()
    hyp_words = re.sub(r"[^\w\s]", "", hypothesis).lower().split()

    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    n = len(ref_words)
    m = len(hyp_words)
    d = [[0] * (m + 1) for _ in range(n + 1)]

    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                substitution = d[i - 1][j - 1] + 1
                insertion = d[i][j - 1] + 1
                deletion = d[i - 1][j] + 1
                d[i][j] = min(substitution, insertion, deletion)

    return d[n][m] / float(n)


def get_whisper_model(
    model_size: str = "small",
    device: Optional[str] = None,
) -> Tuple[WhisperModel, str, Optional[str]]:
    """
    Loads faster-whisper model.
    If device is None, tries CUDA first, and on failure falls back to CPU (int8).
    Returns (model, active_device, failure_reason_if_fallback).
    """
    if device is not None:
        compute_type = "float16" if device == "cuda" else "int8"
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        return model, device, None

    # Try CUDA first with inference probe
    try:
        import numpy as np
        model = WhisperModel(model_size, device="cuda", compute_type="float16")
        # Probe encoder inference to verify cublas/cudnn DLLs are loaded
        dummy_audio = np.zeros(16000, dtype=np.float32)
        segments, _ = model.transcribe(dummy_audio)
        list(segments)
        return model, "cuda", None
    except Exception as cuda_err:
        cuda_reason = str(cuda_err)
        print(f"[!] CUDA verification failed: {cuda_reason}")
        print("[!] Falling back to CPU (int8)...")
        model = WhisperModel(model_size, device="cpu", compute_type="int8")
        return model, "cpu", cuda_reason


def align_line_audio(
    model: WhisperModel,
    wav_path: Path,
) -> List[Dict[str, Any]]:
    """
    Transcribes a line wav and extracts word-level timestamps.
    """
    if not wav_path.exists():
        raise FileNotFoundError(f"Audio line file not found: {wav_path}")

    segments, _ = model.transcribe(
        str(wav_path),
        word_timestamps=True,
        language="en",
        beam_size=5,
    )

    words = []
    for segment in segments:
        if segment.words:
            for w in segment.words:
                cleaned_word = w.word.strip()
                if cleaned_word:
                    words.append({
                        "word": cleaned_word,
                        "start": round(float(w.start), 3),
                        "end": round(float(w.end), 3),
                        "probability": round(float(w.probability), 3),
                    })
    return words


def align_chapter(
    chapter_dir: Path,
    model: WhisperModel,
    device_name: str,
) -> Dict[str, Any]:
    """
    Aligns all line audio files for a chapter, enriches audio/timings.json with word timings,
    and computes WER for each line and overall.
    """
    audio_dir = chapter_dir / "audio"
    timings_path = audio_dir / "timings.json"
    if not timings_path.exists():
        raise FileNotFoundError(f"timings.json not found in {audio_dir}")

    with open(timings_path, "r", encoding="utf-8") as f:
        timings = json.load(f)

    lines = timings.get("lines", [])
    all_ref_texts = []
    all_hyp_texts = []

    for line in lines:
        line_id = line["id"]
        wav_path = audio_dir / "lines" / f"{line_id}.wav"
        words = align_line_audio(model, wav_path)

        # Annotate line words with relative and absolute timestamps
        line_start = line.get("start", 0.0)
        for w in words:
            w["absolute_start"] = round(line_start + w["start"], 3)
            w["absolute_end"] = round(line_start + w["end"], 3)

        aligned_text = " ".join(w["word"] for w in words)
        ref_text = line.get("text", "")
        line_wer = compute_wer(ref_text, aligned_text)

        line["words"] = words
        line["aligned_text"] = aligned_text
        line["wer"] = round(line_wer, 4)

        all_ref_texts.append(ref_text)
        all_hyp_texts.append(aligned_text)

    full_ref = " ".join(all_ref_texts)
    full_hyp = " ".join(all_hyp_texts)
    profile_wer = compute_wer(full_ref, full_hyp)

    timings["alignment"] = {
        "engine": "faster-whisper-small",
        "device": device_name,
        "overall_wer": round(profile_wer, 4),
        "aligned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    with open(timings_path, "w", encoding="utf-8") as f:
        json.dump(timings, f, indent=2)

    return timings


def run_audition_alignment(
    build_dir: Path = Path("build/voice_audition"),
    compare_benchmark: bool = True,
) -> Dict[str, Any]:
    """
    Performs alignment for all audition profiles in build/voice_audition/.
    If compare_benchmark is True and CUDA is available, tests both CUDA and CPU
    to report speed comparison.
    """
    manifest_path = build_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"Audition manifest not found at {manifest_path}. Run audition.py first.")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    profiles = manifest.get("profiles", [])
    if not profiles:
        raise ValueError("No profiles found in audition manifest.")

    # 1. Primary Alignment with automatic device selection (CUDA first)
    model, primary_device, fallback_reason = get_whisper_model()
    print(f"\n=======================================================")
    print(f"Aligning Voice Audition Profiles (Device: {primary_device})")
    if fallback_reason:
        print(f"Fallback Reason: {fallback_reason}")
    print(f"=======================================================\n")

    results = []
    t_primary_start = time.perf_counter()

    for p_info in profiles:
        p_id = p_info["profile_id"]
        chapter_dir = build_dir / p_id
        t0 = time.perf_counter()
        timings = align_chapter(chapter_dir, model, primary_device)
        elapsed = time.perf_counter() - t0

        wer = timings["alignment"]["overall_wer"]
        results.append({
            "profile_id": p_id,
            "voice": p_info["voice"],
            "speed": p_info["speed"],
            "tone": p_info["tone"],
            "wer": wer,
            "align_time_sec": round(elapsed, 3),
        })

        print(
            f"  [+] {p_id:<28} | Voice: {p_info['voice']:<10} | "
            f"WER: {wer*100:<5.1f}% | Align Time: {elapsed:<5.2f}s"
        )

    t_primary_total = time.perf_counter() - t_primary_start

    # 2. Benchmark CPU vs CUDA if primary was CUDA and compare_benchmark is True
    benchmark_report = {
        "primary_device": primary_device,
        "primary_total_sec": round(t_primary_total, 3),
    }

    if compare_benchmark and primary_device == "cuda":
        print(f"\n=======================================================")
        print(f"Benchmarking CPU Alignment (int8) for Speed Comparison")
        print(f"=======================================================\n")
        cpu_model, _, _ = get_whisper_model(device="cpu")
        t_cpu_start = time.perf_counter()
        # Benchmark one sample profile or all profiles
        # To get an accurate comparison across all 6 profiles:
        for p_info in profiles:
            p_id = p_info["profile_id"]
            chapter_dir = build_dir / p_id
            align_chapter(chapter_dir, cpu_model, "cpu")
        t_cpu_total = time.perf_counter() - t_cpu_start

        speedup = t_cpu_total / t_primary_total if t_primary_total > 0 else 0.0
        benchmark_report["cpu_total_sec"] = round(t_cpu_total, 3)
        benchmark_report["cuda_total_sec"] = round(t_primary_total, 3)
        benchmark_report["cuda_speedup"] = round(speedup, 2)

        print(f"  CUDA Total Alignment Time: {t_primary_total:.2f}s")
        print(f"  CPU  Total Alignment Time: {t_cpu_total:.2f}s")
        print(f"  CUDA Speedup:              {speedup:.2f}x faster than CPU")

    report_path = build_dir / "alignment_report.json"
    full_report = {
        "benchmark": benchmark_report,
        "profiles": results,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(full_report, f, indent=2)

    return full_report


if __name__ == "__main__":
    run_audition_alignment()
