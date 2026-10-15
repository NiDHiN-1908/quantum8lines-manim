"""
Procedural sound engine package for simulation shorts.
Replaces monolithic sound.py while preserving full backwards compatibility
for existing callers and tests.
Follows SPEC.md Section 22.5 and Milestone P2a.
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from core.sims.sound.dynamics import (
    ActiveVoice,
    PolyphonyManager,
    apply_soft_saturation,
)
from core.sims.sound.engine import (
    build_and_normalize_audio,
    generate_simulation_audio_array,
    verify_audio_quality,
)
from core.sims.sound.models import (
    PRESET_CONFIGS,
    SoundPaletteSpec,
)
from core.sims.sound.palettes import (
    PALETTE_RENDERERS,
    render_bell,
    render_chime,
    render_glass,
    render_legacy_ping,
    render_marimba,
    render_note,
    render_pad,
    render_pluck,
)
from core.sims.sound.rhythm import (
    MAX_QUANTIZE_SHIFT_SEC,
    quantize_event_time,
    quantize_events,
)
from core.sims.sound.scales import (
    NOTE_SEMITONES,
    SCALES,
    event_to_pitch,
    get_note_frequency,
    parse_root_hz,
)
from core.sims.sound.space import (
    apply_schroeder_reverb,
    compute_stereo_gains,
)


# Legacy backwards compatibility functions
def pentatonic_frequency(
    ball_id: int,
    base_freq: float = 261.63,
    scale_semitones: Optional[List[int]] = None,
) -> float:
    """Computes a frequency from a major pentatonic scale based on ball ID."""
    scale = scale_semitones or [0, 2, 4, 7, 9]
    scale_len = len(scale)
    octave = (ball_id // scale_len) % 3
    note_idx = ball_id % scale_len
    semitones = octave * 12 + scale[note_idx]
    return base_freq * (2.0 ** (semitones / 12.0))


def synthesize_ping(
    freq: float,
    duration_sec: float = 0.12,
    decay_sec: float = 0.08,
    sample_rate: int = 48000,
) -> np.ndarray:
    """Legacy helper: synthesizes soft decaying sine ping."""
    return render_legacy_ping(
        pitch_hz=freq,
        duration_sec=duration_sec,
        sample_rate=sample_rate,
    )


def synthesize_chime(
    base_freq: float = 523.25,
    duration_sec: float = 0.6,
    decay_sec: float = 0.25,
    sample_rate: int = 48000,
) -> np.ndarray:
    """Legacy helper: synthesizes focal convergence chime."""
    return render_chime(
        base_freq=base_freq,
        duration_sec=duration_sec,
        sample_rate=sample_rate,
        decay_sec=decay_sec,
    )


def synthesize_ambient_pad(
    total_duration_sec: float,
    gain: float = 0.05,
    sample_rate: int = 48000,
) -> np.ndarray:
    """Legacy helper: synthesizes ambient pad chord."""
    return render_pad(
        total_duration_sec=total_duration_sec,
        sample_rate=sample_rate,
        gain=gain,
    )


__all__ = [
    # Core orchestration
    "build_and_normalize_audio",
    "generate_simulation_audio_array",
    "verify_audio_quality",
    # Models & presets
    "SoundPaletteSpec",
    "PRESET_CONFIGS",
    # Palettes
    "PALETTE_RENDERERS",
    "render_note",
    "render_pluck",
    "render_marimba",
    "render_bell",
    "render_glass",
    "render_legacy_ping",
    "render_chime",
    "render_pad",
    # Scales
    "SCALES",
    "NOTE_SEMITONES",
    "parse_root_hz",
    "get_note_frequency",
    "event_to_pitch",
    # Rhythm
    "MAX_QUANTIZE_SHIFT_SEC",
    "quantize_event_time",
    "quantize_events",
    # Space
    "compute_stereo_gains",
    "apply_schroeder_reverb",
    # Dynamics
    "ActiveVoice",
    "PolyphonyManager",
    "apply_soft_saturation",
    # Backwards compatibility
    "pentatonic_frequency",
    "synthesize_ping",
    "synthesize_chime",
    "synthesize_ambient_pad",
]
