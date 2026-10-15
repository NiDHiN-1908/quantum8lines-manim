"""
Procedural sound timbres: pluck (Karplus-Strong), marimba (additive inharmonic),
bell (FM synthesis), glass (high sine cluster with shimmer), legacy ping, and pad.
Follows SPEC.md Section 22.5 and Milestone P2a.
"""

import math
from typing import Callable, Dict, Optional
import numpy as np
import scipy.signal


def render_pluck(
    pitch_hz: float,
    velocity: float = 0.8,
    duration_sec: float = 0.5,
    sample_rate: int = 48000,
    seed: int = 42,
) -> np.ndarray:
    """
    Synthesizes a plucked string note using the Karplus-Strong physical modeling algorithm.
    Finite, non-silent, no NaN, peak strictly below 1.0.
    """
    pitch_hz = max(20.0, min(pitch_hz, sample_rate * 0.45))
    period_samples = max(2, int(round(sample_rate / pitch_hz)))
    num_samples = int(math.ceil(duration_sec * sample_rate))

    # Deterministic noise excitation
    # Derive unique per-note seed deterministically
    note_seed = (int(seed) * 31 + int(round(pitch_hz * 10))) & 0xFFFFFFFF
    rng = np.random.RandomState(note_seed)
    noise = rng.uniform(-0.7, 0.7, size=period_samples).astype(np.float64)

    # IIR filter for Karplus-Strong feedback loop:
    # y[n] = x[n] + 0.5 * rho * (y[n - N] + y[n - N - 1])
    # H(z) = 1 / (1 - 0.5*rho*z^-N - 0.5*rho*z^-(N+1))
    rho = 0.992
    a = np.zeros(period_samples + 2, dtype=np.float64)
    a[0] = 1.0
    a[period_samples] = -0.5 * rho
    a[period_samples + 1] = -0.5 * rho
    b = np.array([1.0], dtype=np.float64)

    x = np.zeros(num_samples, dtype=np.float64)
    x[:period_samples] = noise

    y = scipy.signal.lfilter(b, a, x).astype(np.float32)

    # Fade out last 3ms to avoid end click
    fade_len = int(min(0.005 * sample_rate, num_samples // 4))
    if fade_len > 0:
        fade = 0.5 * (1.0 + np.cos(np.pi * np.arange(fade_len) / fade_len))
        y[-fade_len:] *= fade.astype(np.float32)

    vel = max(0.1, min(1.0, float(velocity)))
    signal = y * (0.75 * vel)
    peak = float(np.max(np.abs(signal)))
    if peak >= 0.98:
        signal = signal * (0.95 / peak)

    return signal.astype(np.float32)


def render_marimba(
    pitch_hz: float,
    velocity: float = 0.8,
    duration_sec: float = 0.35,
    sample_rate: int = 48000,
    seed: int = 42,
) -> np.ndarray:
    """
    Synthesizes a warm marimba/wooden bar note using additive synthesis
    with inharmonic flexural modes and rapid decay of upper partials.
    """
    pitch_hz = max(20.0, min(pitch_hz, sample_rate * 0.45))
    num_samples = int(math.ceil(duration_sec * sample_rate))
    t = np.arange(num_samples, dtype=np.float32) / float(sample_rate)

    # Inharmonic modes of an undercut wooden marimba bar
    # (Fundamental, double octave overtone 3.98x, mode 3 ~9.25x, strike click ~13.5x)
    modes = [
        (1.00, 1.00, 0.160),
        (3.98, 0.42, 0.035),
        (9.25, 0.18, 0.012),
        (13.50, 0.08, 0.005),
    ]

    nyquist = sample_rate * 0.48
    signal = np.zeros(num_samples, dtype=np.float32)

    for ratio, amp, decay in modes:
        f = pitch_hz * ratio
        if f >= nyquist:
            continue
        env = np.exp(-t / decay).astype(np.float32)
        signal += (amp * np.sin(2.0 * np.pi * f * t).astype(np.float32)) * env

    # Smooth 1.5ms cosine attack ramp
    attack_samples = int(0.0015 * sample_rate)
    if attack_samples > 0 and num_samples >= attack_samples:
        ramp = 0.5 * (1.0 - np.cos(np.pi * np.arange(attack_samples) / attack_samples))
        signal[:attack_samples] *= ramp.astype(np.float32)

    vel = max(0.1, min(1.0, float(velocity)))
    signal = signal * (0.55 * vel)
    peak = float(np.max(np.abs(signal)))
    if peak >= 0.98:
        signal = signal * (0.95 / peak)

    return signal.astype(np.float32)


def render_bell(
    pitch_hz: float,
    velocity: float = 0.8,
    duration_sec: float = 0.6,
    sample_rate: int = 48000,
    seed: int = 42,
) -> np.ndarray:
    """
    Synthesizes a resonant metallic bell using Chowning Frequency Modulation (FM).
    Carrier and modulator with inharmonic ratio, decaying modulation index.
    """
    pitch_hz = max(20.0, min(pitch_hz, sample_rate * 0.45))
    num_samples = int(math.ceil(duration_sec * sample_rate))
    t = np.arange(num_samples, dtype=np.float32) / float(sample_rate)

    fc = pitch_hz
    fm = 1.414 * pitch_hz  # Inharmonic bell ratio
    # Decaying FM index from 2.5 down to 0
    mod_index = 2.5 * np.exp(-t / 0.22).astype(np.float32)
    # Amplitude envelope
    amp_env = np.exp(-t / 0.45).astype(np.float32)

    modulator = np.sin(2.0 * np.pi * fm * t).astype(np.float32)
    signal = amp_env * np.sin(2.0 * np.pi * fc * t + mod_index * modulator).astype(np.float32)

    # 2.0ms cosine attack
    attack_samples = int(0.002 * sample_rate)
    if attack_samples > 0 and num_samples >= attack_samples:
        ramp = 0.5 * (1.0 - np.cos(np.pi * np.arange(attack_samples) / attack_samples))
        signal[:attack_samples] *= ramp.astype(np.float32)

    vel = max(0.1, min(1.0, float(velocity)))
    signal = signal * (0.65 * vel)
    peak = float(np.max(np.abs(signal)))
    if peak >= 0.98:
        signal = signal * (0.95 / peak)

    return signal.astype(np.float32)


def render_glass(
    pitch_hz: float,
    velocity: float = 0.8,
    duration_sec: float = 0.5,
    sample_rate: int = 48000,
    seed: int = 42,
) -> np.ndarray:
    """
    Synthesizes a crystalline glass tone: high sine cluster with slow shimmer beating.
    """
    pitch_hz = max(40.0, min(pitch_hz, sample_rate * 0.45))
    num_samples = int(math.ceil(duration_sec * sample_rate))
    t = np.arange(num_samples, dtype=np.float32) / float(sample_rate)

    # Cluster of detuned high sines
    partials = [
        (1.000, 0.50, 0.35),
        (1.004, 0.40, 0.35),  # slight detuning produces slow ethereal chorus beating
        (1.503, 0.25, 0.25),  # musical fifth
        (2.001, 0.15, 0.20),  # octave
        (2.752, 0.10, 0.15),  # high glass ring
    ]

    nyquist = sample_rate * 0.48
    signal = np.zeros(num_samples, dtype=np.float32)

    for ratio, amp, decay in partials:
        f = pitch_hz * ratio
        if f >= nyquist:
            continue
        env = np.exp(-t / decay).astype(np.float32)
        signal += (amp * np.sin(2.0 * np.pi * f * t).astype(np.float32)) * env

    # Slow shimmer tremolo (4.0 Hz)
    shimmer = (1.0 + 0.15 * np.sin(2.0 * np.pi * 4.0 * t)).astype(np.float32)
    signal *= shimmer

    # 4ms attack ramp
    attack_samples = int(0.004 * sample_rate)
    if attack_samples > 0 and num_samples >= attack_samples:
        ramp = 0.5 * (1.0 - np.cos(np.pi * np.arange(attack_samples) / attack_samples))
        signal[:attack_samples] *= ramp.astype(np.float32)

    vel = max(0.1, min(1.0, float(velocity)))
    signal = signal * (0.50 * vel)
    peak = float(np.max(np.abs(signal)))
    if peak >= 0.98:
        signal = signal * (0.95 / peak)

    return signal.astype(np.float32)


def render_legacy_ping(
    pitch_hz: float,
    velocity: float = 0.8,
    duration_sec: float = 0.15,
    sample_rate: int = 48000,
    seed: int = 42,
) -> np.ndarray:
    """
    Synthesizes the legacy P1 ping: sine wave with 2ms attack and 0.08s exponential decay.
    """
    pitch_hz = max(20.0, min(pitch_hz, sample_rate * 0.45))
    num_samples = int(math.ceil(duration_sec * sample_rate))
    t = np.arange(num_samples, dtype=np.float32) / float(sample_rate)

    envelope = np.exp(-t / 0.08).astype(np.float32)
    attack_samples = int(0.002 * sample_rate)
    if attack_samples > 0 and num_samples >= attack_samples:
        ramp = 0.5 * (1.0 - np.cos(np.pi * np.arange(attack_samples) / attack_samples))
        envelope[:attack_samples] *= ramp.astype(np.float32)

    signal = np.sin(2.0 * np.pi * pitch_hz * t).astype(np.float32) * envelope
    vel = max(0.1, min(1.0, float(velocity)))
    signal = signal * (0.60 * vel)
    return signal.astype(np.float32)


def render_chime(
    base_freq: float = 523.25,
    duration_sec: float = 0.6,
    sample_rate: int = 48000,
    decay_sec: float = 0.30,
) -> np.ndarray:
    """
    Synthesizes a soft harmonic bell chime for focal convergence.
    """
    num_samples = int(math.ceil(duration_sec * sample_rate))
    t = np.arange(num_samples, dtype=np.float32) / float(sample_rate)

    h1 = np.sin(2.0 * np.pi * base_freq * t) * np.exp(-t / decay_sec)
    h2 = 0.4 * np.sin(2.0 * np.pi * (base_freq * 2.0) * t) * np.exp(-t / (decay_sec * 0.7))
    h3 = 0.2 * np.sin(2.0 * np.pi * (base_freq * 3.0) * t) * np.exp(-t / (decay_sec * 0.5))

    signal = (h1 + h2 + h3).astype(np.float32)
    attack_samples = int(0.003 * sample_rate)
    if attack_samples > 0 and num_samples >= attack_samples:
        ramp = 0.5 * (1.0 - np.cos(np.pi * np.arange(attack_samples) / attack_samples))
        signal[:attack_samples] *= ramp.astype(np.float32)

    return (signal * 0.6).astype(np.float32)


def render_pad(
    total_duration_sec: float,
    sample_rate: int = 48000,
    gain: float = 0.05,
    root_freq: float = 130.81,
) -> np.ndarray:
    """
    Synthesizes a quiet, warm generated ambient pad chord under the simulation.
    Returns stereo array shape (num_samples, 2).
    """
    num_samples = int(math.ceil(total_duration_sec * sample_rate))
    t = np.arange(num_samples, dtype=np.float32) / float(sample_rate)

    # Chord over root: Root + Fifth (1.5x) + Octave (2.0x) with detuning
    drone = (
        0.50 * np.sin(2.0 * np.pi * root_freq * t)
        + 0.30 * np.sin(2.0 * np.pi * (root_freq * 1.498) * t + 0.5)
        + 0.20 * np.sin(2.0 * np.pi * (root_freq * 2.001) * t + 1.0)
        + 0.15 * np.sin(2.0 * np.pi * (root_freq + 0.3) * t)  # slow chorus beating
    ).astype(np.float32)

    # Subtle 0.1 Hz tremolo
    tremolo = (0.85 + 0.15 * np.sin(2.0 * np.pi * 0.12 * t)).astype(np.float32)
    drone *= tremolo

    # 1.5s fade in and fade out
    fade_samples = int(min(num_samples // 4, 1.5 * sample_rate))
    if fade_samples > 0:
        fade_in = 0.5 * (1.0 - np.cos(np.pi * np.arange(fade_samples) / fade_samples))
        fade_out = fade_in[::-1]
        drone[:fade_samples] *= fade_in.astype(np.float32)
        drone[-fade_samples:] *= fade_out.astype(np.float32)

    stereo_drone = np.column_stack([drone * gain, drone * gain * 0.95])
    return stereo_drone.astype(np.float32)


PALETTE_RENDERERS: Dict[str, Callable[..., np.ndarray]] = {
    "pluck": render_pluck,
    "marimba": render_marimba,
    "bell": render_bell,
    "glass": render_glass,
    "legacy_ping": render_legacy_ping,
}


def render_note(
    palette: str,
    pitch_hz: float,
    velocity: float = 0.8,
    duration_sec: float = 0.4,
    sample_rate: int = 48000,
    seed: int = 42,
) -> np.ndarray:
    """
    Renders a note for any registered palette.
    Guaranteed: finite, non-silent, no NaN, peak strictly below 1.0.
    """
    renderer = PALETTE_RENDERERS.get(palette, render_marimba)
    return renderer(
        pitch_hz=pitch_hz,
        velocity=velocity,
        duration_sec=duration_sec,
        sample_rate=sample_rate,
        seed=seed,
    )
