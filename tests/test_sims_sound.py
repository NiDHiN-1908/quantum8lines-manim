"""
Unit and integration tests for procedural simulation audio and G7 compliance.
Follows Milestone P1 Step 3.
"""

from pathlib import Path
import pytest

from core.sims.ellipse_billiards import (
    EllipseAxes,
    EllipseBilliardsSim,
    EventKind,
    SimSpec,
    StageSpec,
)
from core.sims.sound import (
    build_and_normalize_audio,
    compute_stereo_gains,
    pentatonic_frequency,
    verify_audio_quality,
)


def test_stereo_panning_and_frequency_generation():
    """Verify constant-power stereo panning and pentatonic frequency scale."""
    a_axis = 0.6
    # Left edge
    gl, gr = compute_stereo_gains(-a_axis, a_axis)
    assert gl > 0.99
    assert gr < 0.05

    # Center
    gl_c, gr_c = compute_stereo_gains(0.0, a_axis)
    assert abs(gl_c - gr_c) < 1e-6
    assert abs(gl_c**2 + gr_c**2 - 1.0) < 1e-6

    # Right edge
    gl_r, gr_r = compute_stereo_gains(a_axis, a_axis)
    assert gr_r > 0.99
    assert gl_r < 0.05

    # Pentatonic frequencies: must be positive and ascending within octaves
    f0 = pentatonic_frequency(0, base_freq=261.63)
    f1 = pentatonic_frequency(1, base_freq=261.63)
    f4 = pentatonic_frequency(4, base_freq=261.63)
    assert f0 < f1 < f4
    assert 200.0 < f0 < 300.0


def test_sound_synthesis_and_g7_normalization(tmp_path: Path):
    """
    Synthesizes and normalizes procedural simulation audio, verifying:
    - Integrated loudness within 1 LU of -14 LUFS ([-15.0, -13.0])
    - True peak at or below -1.0 dBTP
    - No clipping (sample < 0.999, 0 consecutive full-scale runs)
    - Event count matches the simulation
    """
    # 5.0 second simulation test schedule
    test_spec = SimSpec(
        schedule=[
            StageSpec(count=3, duration_sec=2.5),
            StageSpec(count=5, duration_sec=2.5),
        ]
    )

    sim = EllipseBilliardsSim(axes=test_spec.ellipse, seed=test_spec.seed)
    events = sim.simulate_spec(test_spec)

    bounce_events = [e for e in events if e.kind == EventKind.BOUNCE]
    focus_events = [e for e in events if e.kind == EventKind.PASS_FOCUS]
    assert len(bounce_events) > 0
    assert len(focus_events) > 0

    wav_out = tmp_path / "test_sim_audio.wav"
    norm_report = build_and_normalize_audio(
        spec=test_spec,
        events=events,
        output_path=wav_out,
        total_duration=5.0,
        target_i=-14.0,
        target_tp=-1.5,
    )

    assert wav_out.is_file()
    assert wav_out.stat().st_size > 10000

    qa = verify_audio_quality(wav_out)
    assert qa["passed"] is True
    assert -15.0 <= qa["integrated_lufs"] <= -13.0
    assert qa["true_peak"] <= -1.0
    assert qa["no_clipping"] is True
    assert qa["consecutive_full_scale_runs"] == 0

    # Verify event count matches simulation
    assert len(events) == len(bounce_events) + len(focus_events) + (3 + 5)
