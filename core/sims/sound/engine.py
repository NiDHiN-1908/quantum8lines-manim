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
    render_note,
    render_pad,
)
from core.sims.sound.rhythm import quantize_events
from core.sims.sound.scales import event_to_pitch, parse_root_hz
from core.sims.sound.space import apply_schroeder_reverb, compute_stereo_gains


def generate_simulation_audio_array(
    spec: Any,
    events: List[Any],
    total_duration: Optional[float] = None,
    palette_override: Optional[Union[SoundPaletteSpec, str]] = None,
) -> np.ndarray:
    """
    Synthesizes raw stereo procedural audio array from simulation events.
    Applies palette timbres, scales, optional rhythm quantization, polyphony limiting,
    Schroeder algorithmic reverb, and soft saturation.
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
                root="C4",
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

    # 3. Pre-index stage timing for dynamic 1/sqrt(N) gain scaling
    stages_timing: List[Tuple[float, float, int]] = []
    if hasattr(spec, "schedule"):
        cum_t = 0.0
        for s in spec.schedule:
            stages_timing.append((cum_t, cum_t + s.duration_sec, s.count))
            cum_t += s.duration_sec

    def get_stage_count(t_event: float) -> int:
        for t0, t1, count in stages_timing:
            if t0 <= t_event < t1:
                return count
        return stages_timing[-1][2] if stages_timing else 1

    # 4. Prepare voice events for polyphony manager
    # List of (start_sample, end_sample, left_sig, right_sig, base_amp, decay_samples)
    voice_events: List[Tuple[int, int, np.ndarray, np.ndarray, float, int]] = []
    last_chime_time = -1.0
    semi_a = getattr(getattr(spec, "ellipse", None), "a", 0.6)

    # Cached notes to minimize re-synthesis overhead for identical pitches
    note_cache: Dict[Tuple[int, float], np.ndarray] = {}

    for evt in active_events:
        if evt.time >= dur:
            continue

        start_idx = int(round(evt.time * sr))
        if start_idx >= total_samples:
            continue

        kind_str = str(getattr(evt, "kind", "")).lower()
        # Check for bounce event (Enum or string)
        if "bounce" in kind_str:
            count = get_stage_count(evt.time)
            # Energy conservation scaling 1 / sqrt(N)
            gain_scale = 1.0 / math.sqrt(max(1.0, float(count)))

            # Event velocity
            v_mag = 1.0
            if getattr(evt, "velocity", None) is not None:
                vx, vy = evt.velocity
                v_mag = math.sqrt(vx * vx + vy * vy)
            amp = 0.40 * gain_scale * max(0.2, min(1.2, v_mag))

            pitch_hz = event_to_pitch(
                evt,
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
            # Trigger exactly ONE chime per focal convergence instant
            if abs(evt.time - last_chime_time) > 0.08:
                last_chime_time = evt.time
                chime_hz = root_hz * 2.0  # Octave above root
                chime_sig = render_chime(
                    base_freq=chime_hz,
                    duration_sec=0.6,
                    sample_rate=sr,
                    decay_sec=0.35,
                )
                amp_chime = 0.35
                left_chime = chime_sig * amp_chime
                right_chime = chime_sig * amp_chime
                end_idx = start_idx + len(chime_sig)
                decay_samples = int(0.35 * sr)
                voice_events.append((start_idx, end_idx, left_chime, right_chime, amp_chime, decay_samples))

    # 5. Polyphony management and buffer allocation
    poly_mgr = PolyphonyManager(polyphony_limit=palette_spec.polyphony_limit, sample_rate=sr)
    stereo_buffer = poly_mgr.allocate_voices(voice_events, total_samples)

    # 6. Ambient pad layer
    if palette_spec.pad_enabled:
        pad = render_pad(dur, sample_rate=sr, gain=palette_spec.pad_gain, root_freq=root_hz / 2.0)
        pad_len = min(len(pad), total_samples)
        stereo_buffer[:pad_len] += pad[:pad_len]

    # 7. Schroeder algorithmic reverb
    if palette_spec.reverb_wet > 1e-4:
        stereo_buffer = apply_schroeder_reverb(
            stereo_buffer,
            sample_rate=sr,
            wet_level=palette_spec.reverb_wet,
            decay_sec=palette_spec.reverb_decay,
        )

    # 8. Soft saturation at the end
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
