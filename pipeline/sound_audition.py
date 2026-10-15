"""
Procedural sound audition runner for simulation shorts.
Renders the first 12 seconds of a simulation across sound palette presets,
measures objective audio metrics (loudness, true peak, LRA, brightness, onsets/sec, polyphony),
and outputs audio WAVs and a manifest.
Follows SPEC.md Section 22.5 and Milestone P2a Step 2.

Usage:
    python -m pipeline.sound_audition sims/ellipse_billiards
"""

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import scipy.signal
import soundfile as sf

from core.sims.ellipse_billiards import (
    EllipseBilliardsSim,
    EventKind,
    SimEvent,
    SimSpec,
)
from core.sims.sound import (
    PRESET_CONFIGS,
    SoundPaletteSpec,
    build_and_normalize_audio,
    quantize_events,
    verify_audio_quality,
)
from pipeline.audio_fx import measure_loudness


# 10 Standard and Bright Audition presets
AUDITION_PRESETS: List[Tuple[str, str, SoundPaletteSpec]] = [
    (
        "pluck+pentatonic",
        "pluck_pentatonic",
        PRESET_CONFIGS["pluck+pentatonic"],
    ),
    (
        "marimba+pentatonic",
        "marimba_pentatonic",
        PRESET_CONFIGS["marimba+pentatonic"],
    ),
    (
        "bell+lydian",
        "bell_lydian",
        PRESET_CONFIGS["bell+lydian"],
    ),
    (
        "glass+whole-tone",
        "glass_whole_tone",
        PRESET_CONFIGS["glass+whole-tone"],
    ),
    (
        "marimba+minor with reverb",
        "marimba_minor_reverb",
        PRESET_CONFIGS["marimba+minor with reverb"],
    ),
    (
        "pluck+major with grid quantization",
        "pluck_major_grid",
        PRESET_CONFIGS["pluck+major with grid quantization"],
    ),
    (
        "kalimba-like pluck with pentatonic",
        "kalimba_pluck_pentatonic",
        PRESET_CONFIGS["kalimba-like pluck with pentatonic"],
    ),
    (
        "glass+major with riser",
        "glass_major_riser",
        PRESET_CONFIGS["glass+major with riser"],
    ),
    (
        "pluck+lydian with chord payoff",
        "pluck_lydian_chord",
        PRESET_CONFIGS["pluck+lydian with chord payoff"],
    ),
    (
        "legacy_ping",
        "legacy_ping",
        PRESET_CONFIGS["legacy_ping"],
    ),
]


def compute_spectral_centroid(wav_path: Union[str, Path]) -> float:
    """
    Computes average spectral centroid (timbre brightness) in Hz across active frames.
    Uses STFT spectrogram via scipy.signal.spectrogram.
    """
    samples, sr = sf.read(str(wav_path))
    if samples.ndim > 1:
        samples = np.mean(samples, axis=1)

    nperseg = min(2048, len(samples))
    if nperseg < 64:
        return 0.0

    f, t, sxx = scipy.signal.spectrogram(samples, fs=sr, nperseg=nperseg, noverlap=nperseg // 2)
    frame_energy = np.sum(sxx, axis=0)
    max_energy = float(np.max(frame_energy)) if len(frame_energy) > 0 else 0.0
    if max_energy <= 1e-9:
        return 0.0

    active_mask = frame_energy > 0.001 * max_energy
    if not np.any(active_mask):
        active_mask = np.ones(sxx.shape[1], dtype=bool)

    sxx_active = sxx[:, active_mask]
    denom = np.sum(sxx_active, axis=0) + 1e-12
    centroids = np.sum(f[:, None] * sxx_active, axis=0) / denom

    return float(np.mean(centroids))


def compute_peak_polyphony(
    events: List[SimEvent],
    t_start: float,
    t_end: float,
    sr: int = 48000,
    note_dur_sec: float = 0.40,
    polyphony_limit: int = 24,
) -> int:
    """
    Calculates the maximum concurrent voices sounding within [t_start, t_end],
    capped by the polyphony limit.
    """
    intervals: List[Tuple[float, float]] = []
    for evt in events:
        if evt.time < t_start or evt.time >= t_end:
            continue
        kind_str = str(evt.kind).lower()
        if "bounce" in kind_str or "pass_focus" in kind_str:
            d = 0.60 if "pass_focus" in kind_str else note_dur_sec
            intervals.append((evt.time, min(t_end, evt.time + d)))

    if not intervals:
        return 0

    point_events: List[Tuple[float, int]] = []
    for s, e in intervals:
        point_events.append((s, 1))
        point_events.append((e, -1))

    point_events.sort(key=lambda x: (x[0], -x[1]))

    current_voices = 0
    max_voices = 0
    for t, delta in point_events:
        current_voices += delta
        if current_voices > max_voices:
            max_voices = current_voices

    return min(max_voices, polyphony_limit)


def run_sound_audition(
    sim_dir: Union[str, Path] = "sims/ellipse_billiards",
    output_dir: Union[str, Path] = "build/sound_audition",
) -> Dict[str, Any]:
    """
    Renders audition audio clips for all candidate sound presets across two key segments:
    - seconds 0-8 (early / sparse arpeggiations)
    - seconds 20-32 (dense last 12 seconds with high collision rate)
    Computes objective metrics and outputs build/sound_audition/manifest.json.
    """
    s_dir = Path(sim_dir).resolve()
    spec_path = s_dir / "sim_spec.json"
    if not spec_path.is_file():
        raise FileNotFoundError(f"Simulation spec not found: {spec_path}")

    with open(spec_path, "r", encoding="utf-8") as f:
        spec_data = json.load(f)

    sim_spec = SimSpec.model_validate(spec_data)
    out_dir = Path(output_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    # Deterministic physics simulation
    sim = EllipseBilliardsSim(axes=sim_spec.ellipse, seed=sim_spec.seed)
    full_events = sim.simulate_spec(sim_spec)
    total_dur = sim_spec.total_duration

    segments = [
        ("0-8s (early)", 0.0, 8.0, "0_8s"),
        ("20-32s (dense)", max(0.0, total_dur - 12.0), total_dur, "20_32s"),
    ]

    sr = getattr(getattr(sim_spec, "sound", None), "sample_rate", 48000)
    results: List[Dict[str, Any]] = []

    print(f"\n=========================================================================")
    print(f" procedural sound audition: {s_dir.name} (10 presets x 2 segments)")
    print(f"=========================================================================\n")

    from core.sims.sound.engine import generate_simulation_audio_array
    from pipeline.audio_fx import normalize

    for preset_label, file_slug, palette_spec in AUDITION_PRESETS:
        print(f"\n--- Preset: {preset_label} ---")

        events_for_preset = full_events
        if palette_spec.grid:
            events_for_preset = quantize_events(
                full_events,
                enabled=True,
                tempo=palette_spec.tempo,
                subdivision=palette_spec.grid_subdivision,
            )

        # Synthesize full duration raw array once
        full_audio = generate_simulation_audio_array(
            spec=sim_spec,
            events=events_for_preset,
            total_duration=total_dur,
            palette_override=palette_spec,
        )

        for seg_name, t_start, t_end, seg_slug in segments:
            seg_dur = t_end - t_start
            s_start = int(round(t_start * sr))
            s_end = int(round(t_end * sr))
            seg_samples = full_audio[s_start:s_end]

            wav_filename = f"{file_slug}_{seg_slug}.wav"
            wav_path = out_dir / wav_filename
            temp_raw = out_dir / f"_temp_raw_{wav_filename}"

            # Write raw segment and normalize
            sf.write(str(temp_raw), seg_samples, sr, subtype="PCM_24")
            try:
                normalize(
                    path_in=temp_raw,
                    path_out=wav_path,
                    target_i=-14.0,
                    target_tp=-1.5,
                )
            finally:
                temp_raw.unlink(missing_ok=True)

            # Measure metrics
            loudness_meas = measure_loudness(wav_path)
            centroid = compute_spectral_centroid(wav_path)

            seg_bounces = [
                e for e in events_for_preset
                if t_start <= e.time < t_end and "bounce" in str(e.kind).lower()
            ]
            onsets_per_sec = round(len(seg_bounces) / float(seg_dur), 2)

            note_dur = 0.15 if palette_spec.palette == "legacy_ping" else 0.40
            peak_poly = compute_peak_polyphony(
                events_for_preset,
                t_start=t_start,
                t_end=t_end,
                sr=sr,
                note_dur_sec=note_dur,
                polyphony_limit=palette_spec.polyphony_limit,
            )

            entry = {
                "preset": preset_label,
                "segment": seg_name,
                "slug": f"{file_slug}_{seg_slug}",
                "palette": palette_spec.palette,
                "scale": palette_spec.scale,
                "root": str(palette_spec.root),
                "reverb_wet": palette_spec.reverb_wet,
                "reverb_decay": palette_spec.reverb_decay,
                "grid": palette_spec.grid,
                "pad_enabled": palette_spec.pad_enabled,
                "wav_path": str(wav_path.relative_to(Path.cwd()) if wav_path.is_relative_to(Path.cwd()) else wav_path),
                "integrated_lufs": round(loudness_meas["integrated_lufs"], 2),
                "true_peak": round(loudness_meas["true_peak"], 2),
                "lra": round(loudness_meas.get("lra", 0.0), 2),
                "spectral_centroid_hz": round(centroid, 1),
                "onsets_per_sec": onsets_per_sec,
                "peak_polyphony": peak_poly,
            }
            results.append(entry)
            print(f"  [{seg_name}] -> {wav_filename} (I: {entry['integrated_lufs']:.2f} LUFS, TP: {entry['true_peak']:.2f} dBTP, Centroid: {entry['spectral_centroid_hz']} Hz, Poly: {entry['peak_polyphony']})")

    # Write manifest
    manifest_path = out_dir / "manifest.json"
    manifest_data = {
        "simulation": s_dir.name,
        "total_duration_sec": total_dur,
        "segments": [s[0] for s in segments],
        "presets_count": len(AUDITION_PRESETS),
        "results_count": len(results),
        "results": results,
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)

    # Format Markdown Table
    print("\n" + "=" * 100)
    print("OBJECTIVE SOUND AUDITION REPORT (2 Segments per Preset: 0-8s and 20-32s)")
    print("=" * 100)
    print(format_markdown_table(results))
    print("=" * 100 + "\n")

    return manifest_data


def format_markdown_table(results: List[Dict[str, Any]]) -> str:
    """Formats audition results into GitHub markdown table for docs/sims.md."""
    headers = [
        "Preset",
        "Segment",
        "Palette",
        "Scale",
        "Integrated (LUFS)",
        "True Peak (dBTP)",
        "LRA (LU)",
        "Spectral Centroid (Hz)",
        "Onsets / sec",
        "Peak Polyphony",
    ]
    rows = []
    rows.append("| " + " | ".join(headers) + " |")
    rows.append("| " + " | ".join(["---"] * len(headers)) + " |")

    for r in results:
        row = [
            f"`{r['preset']}`",
            r["segment"],
            r["palette"],
            r["scale"],
            f"{r['integrated_lufs']:.2f}",
            f"{r['true_peak']:.2f}",
            f"{r['lra']:.2f}",
            f"{r['spectral_centroid_hz']:.1f}",
            f"{r['onsets_per_sec']:.2f}",
            str(r["peak_polyphony"]),
        ]
        rows.append("| " + " | ".join(row) + " |")

    return "\n".join(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Procedural Sound Audition Runner")
    parser.add_argument("sim_dir", nargs="?", default="sims/ellipse_billiards", help="Simulation folder path")
    parser.add_argument("--output-dir", default="build/sound_audition", help="Output directory")
    args = parser.parse_args()

    run_sound_audition(
        sim_dir=args.sim_dir,
        output_dir=args.output_dir,
    )
