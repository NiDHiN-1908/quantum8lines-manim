"""
Procedural simulation sound engine.
Coordinates palettes, musical scales, rhythm grid quantization, polyphony management,
stereo spatialization, Schroeder reverb, and two-pass loudness normalization.
Follows SPEC.md Section 22.5 and Milestone P2a.
"""

import math
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import soundfile as sf

from pipeline.audio_fx import measure_loudness, normalize
from core.sims.sound.dynamics import PolyphonyManager, apply_soft_saturation
from core.sims.sound.models import PRESET_CONFIGS, SoundPaletteSpec
from core.sims.sound.palettes import (
    render_chime,
    render_count_increase_chime,
    render_note,
    render_pad,
    render_thump,
)
from core.sims.sound.rhythm import quantize_events
from core.sims.sound.scales import SCALES, event_to_pitch, get_note_frequency, parse_root_hz
from core.sims.sound.space import apply_high_shelf, apply_schroeder_reverb, compute_stereo_gains


def generate_simulation_audio_array(
    spec: Any,
    events: List[Any],
    total_duration: Optional[float] = None,
    palette_override: Optional[Union[SoundPaletteSpec, str]] = None,
) -> np.ndarray:
    """
    Synthesizes raw stereo procedural audio array from simulation events.
    Applies palette timbres, scales, optional rhythm quantization, polyphony limiting,
    musical arpeggiation, focal convergence chords with low thump, count-increase chimes,
    Schroeder algorithmic reverb, master high-shelf EQ, and soft saturation.
    """
    # Resolve sound palette config
    if isinstance(palette_override, str):
        if palette_override not in PRESET_CONFIGS:
            raise ValueError(f"Unknown preset '{palette_override}'. Supported: {list(PRESET_CONFIGS.keys())}")
        palette_spec = PRESET_CONFIGS[palette_override]
    elif isinstance(palette_override, SoundPaletteSpec):
        palette_spec = palette_override
    elif hasattr(spec, "sound_palette") and spec.sound_palette is not None:
        palette_spec = spec.sound_palette
    else:
        # Fallback to default pleasant marimba or legacy settings if present
        if hasattr(spec, "sound") and getattr(spec.sound, "scale_semitones", None) is not None:
            palette_spec = SoundPaletteSpec(
                palette="marimba",
                scale="pentatonic_major",
                root="C5",
                pad_enabled=getattr(spec.sound, "pad_enabled", True),
                pad_gain=getattr(spec.sound, "pad_gain", 0.05),
            )
        else:
            palette_spec = SoundPaletteSpec()

    sr = getattr(getattr(spec, "sound", None), "sample_rate", 48000)
    dur = float(total_duration if total_duration is not None else spec.total_duration)
    total_samples = int(math.ceil(dur * sr))

    # 1. Optional rhythm grid quantization
    active_events = events
    if palette_spec.grid:
        active_events = quantize_events(
            events,
            enabled=True,
            tempo=palette_spec.tempo,
            subdivision=palette_spec.grid_subdivision,
        )

    # 2. Parse root pitch
    root_hz = parse_root_hz(palette_spec.root)

    # 3. Pre-index stage timing
    stages_timing: List[Tuple[float, float, int]] = []
    if hasattr(spec, "schedule"):
        cum_t = 0.0
        for s in spec.schedule:
            stages_timing.append((cum_t, cum_t + s.duration_sec, s.count))
            cum_t += s.duration_sec

    def get_stage_info(t_event: float) -> Tuple[int, int]:
        """Returns (stage_index, stage_ball_count)."""
        for idx, (t0, t1, count) in enumerate(stages_timing):
            if t0 <= t_event < t1:
                return idx, count
        if stages_timing:
            return len(stages_timing) - 1, stages_timing[-1][2]
        return 0, 1

    # 4. Map first bounces of each stage to arpeggiate upward across ball indices
    ball_pitch_ranks: Dict[Tuple[int, int], int] = {}
    stage_ball_pitches: Dict[int, List[float]] = {}

    for s_idx, (t0, t1, count) in enumerate(stages_timing):
        stage_bounces = [
            e for e in active_events
            if t0 <= e.time < t1 and "bounce" in str(getattr(e, "kind", "")).lower()
        ]
        earliest_per_ball: Dict[int, float] = {}
        for b in stage_bounces:
            b_id = getattr(b, "ball_id", 0)
            if b_id not in earliest_per_ball or b.time < earliest_per_ball[b_id]:
                earliest_per_ball[b_id] = b.time

        sorted_balls = sorted(earliest_per_ball.keys(), key=lambda b_id: (earliest_per_ball[b_id], b_id))
        for rank, b_id in enumerate(sorted_balls):
            ball_pitch_ranks[(s_idx, b_id)] = rank

        # Precalculate stage ball pitches
        pitches = []
        for rank in range(count):
            f = get_note_frequency(rank, root_hz=root_hz, scale_name=palette_spec.scale, octaves=palette_spec.octaves)
            pitches.append(f)
        stage_ball_pitches[s_idx] = pitches

    # 5. Pre-collect bounce timestamps for 1/sqrt(simultaneous onsets) energy scaling
    bounce_times = np.array([
        e.time for e in active_events if "bounce" in str(getattr(e, "kind", "")).lower()
    ], dtype=np.float64)

    # 6. Prepare voice events for polyphony manager
    # List of (start_sample, end_sample, left_sig, right_sig, base_amp, decay_samples)
    voice_events: List[Tuple[int, int, np.ndarray, np.ndarray, float, int]] = []
    semi_a = getattr(getattr(spec, "ellipse", None), "a", 0.6)

    # Count increase chimes on stage transitions (stage_idx >= 1)
    for s_idx in range(1, len(stages_timing)):
        t_stage_start = stages_timing[s_idx][0]
        if t_stage_start < dur:
            start_s = int(round(t_stage_start * sr))
            chime_sig = render_count_increase_chime(
                base_freq=root_hz * 1.5,
                interval_semitones=5,
                note_dur=0.10,
                sample_rate=sr,
                amplitude=0.30,
            )
            left_ch = chime_sig * 0.90
            right_ch = chime_sig * 0.90
            voice_events.append((
                start_s,
                start_s + len(chime_sig),
                left_ch,
                right_ch,
                0.30,
                int(0.20 * sr),
            ))

    # Note cache to minimize re-synthesis overhead
    note_cache: Dict[Tuple[int, float], np.ndarray] = {}
    last_f2_time = -1.0

    for evt in active_events:
        if evt.time >= dur:
            continue

        start_idx = int(round(evt.time * sr))
        if start_idx >= total_samples:
            continue

        kind_str = str(getattr(evt, "kind", "")).lower()
        if "bounce" in kind_str:
            s_idx, count = get_stage_info(evt.time)

            # Energy conservation: gain per onset scales with 1 / sqrt(simultaneous onsets)
            if len(bounce_times) > 0:
                simul_onsets = int(np.sum(np.abs(bounce_times - evt.time) <= 0.035))
            else:
                simul_onsets = 1
            gain_scale = 1.0 / math.sqrt(max(1.0, float(simul_onsets)))

            # Event velocity
            v_mag = 1.0
            if getattr(evt, "velocity", None) is not None:
                vx, vy = evt.velocity
                v_mag = math.sqrt(vx * vx + vy * vy)
            amp = 0.40 * gain_scale * max(0.2, min(1.2, v_mag))

            # Arpeggiated pitch mapping
            b_id = getattr(evt, "ball_id", 0)
            pitch_rank = ball_pitch_ranks.get((s_idx, b_id), b_id)
            pitch_hz = get_note_frequency(
                pitch_rank,
                root_hz=root_hz,
                scale_name=palette_spec.scale,
                octaves=palette_spec.octaves,
            )

            cache_key = (getattr(evt, "ball_id", 0), round(pitch_hz, 1))
            if cache_key not in note_cache:
                note_dur = 0.15 if palette_spec.palette == "legacy_ping" else 0.40
                note_cache[cache_key] = render_note(
                    palette=palette_spec.palette,
                    pitch_hz=pitch_hz,
                    velocity=1.0,
                    duration_sec=note_dur,
                    sample_rate=sr,
                    seed=palette_spec.seed,
                )
            note_sig = note_cache[cache_key]

            # Stereo panning from x position
            x_pos = evt.point[0] if getattr(evt, "point", None) is not None else 0.0
            gl, gr = compute_stereo_gains(x_pos, semi_a)

            left_sig = note_sig * (amp * gl)
            right_sig = note_sig * (amp * gr)
            end_idx = start_idx + len(note_sig)
            decay_samples = int(0.12 * sr)

            voice_events.append((start_idx, end_idx, left_sig, right_sig, amp, decay_samples))

        elif "pass_focus" in kind_str:
            # Trigger chord and low thump at F2 convergence instant
            if abs(evt.time - last_f2_time) > 0.08:
                last_f2_time = evt.time
                s_idx, _ = get_stage_info(evt.time)
                stage_pitches = stage_ball_pitches.get(s_idx, [root_hz * 2.0])

                # Voice the chord: up to 6 distinct tones across the ball pitches
                if len(stage_pitches) <= 6:
                    chord_freqs = stage_pitches
                else:
                    chord_indices = [int(round(i * (len(stage_pitches) - 1) / 5.0)) for i in range(6)]
                    chord_freqs = list(dict.fromkeys(stage_pitches[i] for i in chord_indices))

                chord_amp = 0.32 / math.sqrt(max(1.0, float(len(chord_freqs))))
                for f_note in chord_freqs:
                    chime_note = render_chime(
                        base_freq=f_note,
                        duration_sec=0.55,
                        sample_rate=sr,
                        decay_sec=0.30,
                    )
                    end_chime = start_idx + len(chime_note)
                    voice_events.append((
                        start_idx,
                        end_chime,
                        chime_note * chord_amp,
                        chime_note * chord_amp,
                        chord_amp,
                        int(0.30 * sr),
                    ))

                # Visceral low thump (sine sweep 80 Hz -> 40 Hz)
                thump_sig = render_thump(
                    duration_sec=0.12,
                    f_start=80.0,
                    f_end=40.0,
                    sample_rate=sr,
                    amplitude=0.42,
                )
                end_thump = start_idx + len(thump_sig)
                voice_events.append((
                    start_idx,
                    end_thump,
                    thump_sig * 0.95,
                    thump_sig * 0.95,
                    0.42,
                    int(0.08 * sr),
                ))

    # 7. Polyphony management and buffer allocation
    poly_mgr = PolyphonyManager(polyphony_limit=palette_spec.polyphony_limit, sample_rate=sr)
    stereo_buffer = poly_mgr.allocate_voices(voice_events, total_samples)

    # 8. Ambient pad layer (with optional stage-rising pitch)
    if palette_spec.pad_enabled:
        scale_semitones = SCALES.get(palette_spec.scale, [0, 2, 4, 7, 9])
        pad = render_pad(
            dur,
            sample_rate=sr,
            gain=palette_spec.pad_gain,
            root_freq=root_hz / 2.0,
            stages=stages_timing if palette_spec.pad_riser else None,
            scale_semitones=scale_semitones,
        )
        pad_len = min(len(pad), total_samples)
        stereo_buffer[:pad_len] += pad[:pad_len]

    # 9. Schroeder algorithmic reverb
    if palette_spec.reverb_wet > 1e-4:
        stereo_buffer = apply_schroeder_reverb(
            stereo_buffer,
            sample_rate=sr,
            wet_level=palette_spec.reverb_wet,
            decay_sec=palette_spec.reverb_decay,
        )

    # 10. Master high-shelf EQ boost (+3 dB above 3 kHz) for bright presence
    if palette_spec.high_shelf_db > 0.05:
        stereo_buffer = apply_high_shelf(
            stereo_buffer,
            sample_rate=sr,
            f0=3000.0,
            gain_db=palette_spec.high_shelf_db,
        )

    # 11. Soft tape-style saturation to prevent clipping
    stereo_buffer = apply_soft_saturation(stereo_buffer)

    return stereo_buffer.astype(np.float32)


def build_and_normalize_audio(
    spec: Any,
    events: List[Any],
    output_path: Union[str, Path],
    total_duration: Optional[float] = None,
    target_i: float = -14.0,
    target_tp: float = -1.5,
    palette_override: Optional[Union[SoundPaletteSpec, str]] = None,
) -> Dict[str, Any]:
    """
    Synthesizes raw procedural audio array to temp WAV, normalizes with two-pass loudnorm,
    and returns normalization measurements.
    """
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    samples = generate_simulation_audio_array(
        spec,
        events,
        total_duration=total_duration,
        palette_override=palette_override,
    )
    sr = getattr(getattr(spec, "sound", None), "sample_rate", 48000)

    # Write raw unnormalized WAV into temporary file
    temp_dir = out_file.parent
    temp_raw = temp_dir / f"_temp_raw_{out_file.stem}.wav"

    try:
        sf.write(str(temp_raw), samples, sr, subtype="PCM_24")
        norm_result = normalize(
            path_in=temp_raw,
            path_out=out_file,
            target_i=target_i,
            target_tp=target_tp,
        )
        return norm_result
    finally:
        if temp_raw.exists():
            temp_raw.unlink(missing_ok=True)


def verify_audio_quality(audio_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Checks G7/S5 loudness and no-clipping constraints on audio_path:
    - Integrated loudness within 1 LU of -14 LUFS ([-15.0, -13.0])
    - True peak <= -1.0 dBTP
    - No clipping (peak sample < 0.999, 0 runs of 3+ consecutive full-scale samples)
    """
    p = Path(audio_path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"Audio file not found: {p}")

    if p.suffix.lower() != ".wav":
        # Decode container audio to temporary WAV for soundfile
        with tempfile.TemporaryDirectory() as td:
            temp_wav = Path(td) / "temp_extracted.wav"
            cmd = [
                "ffmpeg", "-y", "-nostdin",
                "-i", str(p),
                "-vn",
                "-c:a", "pcm_s16le",
                str(temp_wav),
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return verify_audio_quality(temp_wav)

    meas = measure_loudness(p)
    lufs = meas["integrated_lufs"]
    tp = meas["true_peak"]
    lra = meas.get("lra", 0.0)

    samples, sr = sf.read(str(p))
    if samples.ndim > 1:
        samples = np.mean(samples, axis=1)

    peak_sample = float(np.max(np.abs(samples)))
    is_fs = (np.abs(samples) >= 0.999).astype(np.int8)
    kernel = np.ones(3, dtype=np.int8)
    runs = np.convolve(is_fs, kernel, mode="valid")
    run_count = int(np.sum(runs >= 3))

    lufs_ok = -15.0 <= lufs <= -13.0
    tp_ok = tp <= -1.0 + 0.05
    peak_ok = peak_sample < 0.999
    runs_ok = run_count == 0

    return {
        "passed": bool(lufs_ok and tp_ok and peak_ok and runs_ok),
        "integrated_lufs": round(lufs, 2),
        "true_peak": round(tp, 2),
        "lra": round(lra, 2),
        "peak_sample": round(peak_sample, 4),
        "consecutive_full_scale_runs": run_count,
        "lufs_ok": lufs_ok,
        "tp_ok": tp_ok,
        "no_clipping": bool(peak_ok and runs_ok),
    }
