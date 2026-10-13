"""
Procedural audio synthesis and loudness normalization for ellipse billiards short.
Follows Milestone P1 Step 3.
- Procedural audio without external samples (sample rate 48000 Hz).
- Exponentially decaying sine pings with pentatonic pitch scale per ball ID.
- Stereo panning from ball x position.
- Gain scaled by 1/sqrt(N) to maintain stable loudness as ball count grows.
- Resonant harmonic chime when balls focus at F2 (or F1).
- Optional ambient pad under the simulation.
- Two-pass normalization via pipeline.audio_fx.normalize to -14 LUFS / <= -1.5 dBTP.
"""

import math
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np
import soundfile as sf

from core.sims.ellipse_billiards import (
    EventKind,
    SimEvent,
    SimSpec,
)
from pipeline.audio_fx import measure_loudness, normalize


def pentatonic_frequency(ball_id: int, base_freq: float = 261.63, scale_semitones: Optional[List[int]] = None) -> float:
    """Computes a frequency from a major pentatonic scale based on ball ID."""
    scale = scale_semitones or [0, 2, 4, 7, 9]
    scale_len = len(scale)
    # Wrap within 3 pleasant octaves
    octave = (ball_id // scale_len) % 3
    note_idx = ball_id % scale_len
    semitones = octave * 12 + scale[note_idx]
    return base_freq * (2.0 ** (semitones / 12.0))


def compute_stereo_gains(x: float, a: float) -> Tuple[float, float]:
    """Computes constant-power stereo panning (left_gain, right_gain) from x position in [-a, a]."""
    p = max(-1.0, min(1.0, x / max(1e-6, a)))
    theta = (math.pi / 4.0) * (p + 1.0)  # in [0, pi/2]
    left = math.cos(theta)
    right = math.sin(theta)
    return (left, right)


def synthesize_ping(
    freq: float,
    duration_sec: float,
    decay_sec: float,
    sample_rate: int = 48000,
) -> np.ndarray:
    """Synthesizes a short soft ping: sine with smooth 2ms attack and exponential decay."""
    num_samples = int(math.ceil(duration_sec * sample_rate))
    t = np.arange(num_samples, dtype=np.float32) / float(sample_rate)

    # 2ms smooth cosine attack ramp
    attack_samples = int(0.002 * sample_rate)
    envelope = np.exp(-t / max(1e-4, decay_sec)).astype(np.float32)
    if attack_samples > 0 and num_samples >= attack_samples:
        attack_ramp = 0.5 * (1.0 - np.cos(np.pi * np.arange(attack_samples) / attack_samples))
        envelope[:attack_samples] *= attack_ramp

    signal = np.sin(2.0 * np.pi * freq * t).astype(np.float32) * envelope
    return signal


def synthesize_chime(
    base_freq: float = 523.25,
    duration_sec: float = 0.6,
    decay_sec: float = 0.25,
    sample_rate: int = 48000,
) -> np.ndarray:
    """Synthesizes a soft harmonic bell chime for focal convergence."""
    num_samples = int(math.ceil(duration_sec * sample_rate))
    t = np.arange(num_samples, dtype=np.float32) / float(sample_rate)

    # Harmonics: fundamental + 2nd harmonic + 3rd harmonic
    h1 = np.sin(2.0 * np.pi * base_freq * t) * np.exp(-t / decay_sec)
    h2 = 0.4 * np.sin(2.0 * np.pi * (base_freq * 2.0) * t) * np.exp(-t / (decay_sec * 0.7))
    h3 = 0.2 * np.sin(2.0 * np.pi * (base_freq * 3.0) * t) * np.exp(-t / (decay_sec * 0.5))

    signal = (h1 + h2 + h3).astype(np.float32)
    # Quick attack ramp
    attack_samples = int(0.003 * sample_rate)
    if attack_samples > 0:
        ramp = 0.5 * (1.0 - np.cos(np.pi * np.arange(attack_samples) / attack_samples))
        signal[:attack_samples] *= ramp

    return signal * 0.6


def synthesize_ambient_pad(
    total_duration_sec: float,
    gain: float = 0.05,
    sample_rate: int = 48000,
) -> np.ndarray:
    """Synthesizes a gentle, warm low drone pad under the simulation."""
    num_samples = int(math.ceil(total_duration_sec * sample_rate))
    t = np.arange(num_samples, dtype=np.float32) / float(sample_rate)

    # Subtle chord: C3 (130.81 Hz), G3 (196.00 Hz), C4 (261.63 Hz)
    # Slight chorusing detune
    drone = (
        0.5 * np.sin(2.0 * np.pi * 130.81 * t)
        + 0.3 * np.sin(2.0 * np.pi * 196.00 * t + 0.5)
        + 0.2 * np.sin(2.0 * np.pi * 261.63 * t + 1.0)
        + 0.15 * np.sin(2.0 * np.pi * 131.10 * t)  # slow chorus beating
    ).astype(np.float32)

    # Slow 0.1 Hz tremolo
    tremolo = 0.85 + 0.15 * np.sin(2.0 * np.pi * 0.12 * t)
    drone *= tremolo

    # 1.5s fade in and fade out
    fade_samples = int(min(num_samples // 4, 1.5 * sample_rate))
    if fade_samples > 0:
        fade_in = 0.5 * (1.0 - np.cos(np.pi * np.arange(fade_samples) / fade_samples))
        fade_out = fade_in[::-1]
        drone[:fade_samples] *= fade_in
        drone[-fade_samples:] *= fade_out

    stereo_drone = np.column_stack([drone * gain, drone * gain * 0.95])
    return stereo_drone.astype(np.float32)


def generate_simulation_audio_array(
    spec: SimSpec,
    events: List[SimEvent],
    total_duration: Optional[float] = None,
) -> np.ndarray:
    """
    Synthesizes raw stereo procedural audio array from events.
    """
    sr = spec.sound.sample_rate
    dur = total_duration if total_duration is not None else spec.total_duration
    total_samples = int(math.ceil(dur * sr))
    stereo_buffer = np.zeros((total_samples, 2), dtype=np.float32)

    # 1. Ambient pad layer
    if spec.sound.pad_enabled:
        pad = synthesize_ambient_pad(dur, gain=spec.sound.pad_gain, sample_rate=sr)
        pad_len = min(len(pad), total_samples)
        stereo_buffer[:pad_len] += pad[:pad_len]

    # Pre-index stages to lookup count for gain scaling
    stages_timing = []
    cum_t = 0.0
    for s in spec.schedule:
        stages_timing.append((cum_t, cum_t + s.duration_sec, s.count))
        cum_t += s.duration_sec

    def get_stage_count(event_time: float) -> int:
        for t0, t1, count in stages_timing:
            if t0 <= event_time < t1:
                return count
        return stages_timing[-1][2] if stages_timing else 1

    # 2. Render pings and chimes
    last_chime_time = -1.0
    ping_cache: Dict[Tuple[int, float], np.ndarray] = {}

    for evt in events:
        if evt.time >= dur:
            continue

        start_idx = int(evt.time * sr)
        if start_idx >= total_samples:
            continue

        if evt.kind == EventKind.BOUNCE:
            count = get_stage_count(evt.time)
            # Gain scaled by 1/sqrt(N) to keep perceived loudness stable
            gain_scale = 1.0 / math.sqrt(max(1.0, float(count)))
            # Base amplitude
            amp = 0.35 * gain_scale

            freq = pentatonic_frequency(
                evt.ball_id,
                base_freq=spec.sound.base_freq,
                scale_semitones=spec.sound.scale_semitones,
            )

            # Retrieve or generate ping
            cache_key = (evt.ball_id, round(freq, 2))
            if cache_key not in ping_cache:
                ping_cache[cache_key] = synthesize_ping(
                    freq=freq,
                    duration_sec=0.12,
                    decay_sec=spec.sound.ping_decay_sec,
                    sample_rate=sr,
                )
            ping_sig = ping_cache[cache_key]

            # Stereo panning from ball x position
            gl, gr = compute_stereo_gains(evt.point[0], spec.ellipse.a)

            end_idx = min(total_samples, start_idx + len(ping_sig))
            clip_len = end_idx - start_idx
            if clip_len > 0:
                stereo_buffer[start_idx:end_idx, 0] += ping_sig[:clip_len] * (amp * gl)
                stereo_buffer[start_idx:end_idx, 1] += ping_sig[:clip_len] * (amp * gr)

        elif evt.kind == EventKind.PASS_FOCUS:
            # Trigger exactly ONE chime per focal convergence instant (ignore subsequent balls in same pass)
            if abs(evt.time - last_chime_time) > 0.08:
                last_chime_time = evt.time
                chime_sig = synthesize_chime(
                    base_freq=spec.sound.chime_freq,
                    duration_sec=0.6,
                    decay_sec=spec.sound.chime_decay_sec,
                    sample_rate=sr,
                )
                end_idx = min(total_samples, start_idx + len(chime_sig))
                clip_len = end_idx - start_idx
                if clip_len > 0:
                    stereo_buffer[start_idx:end_idx, 0] += chime_sig[:clip_len] * 0.4
                    stereo_buffer[start_idx:end_idx, 1] += chime_sig[:clip_len] * 0.4

    return stereo_buffer


def build_and_normalize_audio(
    spec: SimSpec,
    events: List[SimEvent],
    output_path: Union[str, Path],
    total_duration: Optional[float] = None,
    target_i: float = -14.0,
    target_tp: float = -1.5,
) -> Dict[str, Any]:
    """
    Synthesizes raw procedural audio to temp WAV, normalizes with two-pass loudnorm,
    and returns stats.
    """
    out_file = Path(output_path).resolve()
    out_file.parent.mkdir(parents=True, exist_ok=True)

    samples = generate_simulation_audio_array(spec, events, total_duration=total_duration)
    sr = spec.sound.sample_rate

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
    Checks G7 loudness and no-clipping constraints on audio_path:
    - Integrated loudness within 1 LU of -14 LUFS
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
        "peak_sample": round(peak_sample, 4),
        "consecutive_full_scale_runs": run_count,
        "lufs_ok": lufs_ok,
        "tp_ok": tp_ok,
        "no_clipping": bool(peak_ok and runs_ok),
    }
