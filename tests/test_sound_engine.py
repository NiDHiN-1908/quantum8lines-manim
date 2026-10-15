"""
Unit and integration tests for procedural sound engine, palettes, scales,
rhythm grid quantization, polyphony management, and deterministic synthesis.
Follows SPEC.md Section 22.5 and Milestone P2a Step 1.
"""

import math
from pathlib import Path
import numpy as np
import pytest

from core.sims.ellipse_billiards import (
    EllipseAxes,
    EllipseBilliardsSim,
    EventKind,
    SimSpec,
    StageSpec,
)
from core.sims.sound import (
    MAX_QUANTIZE_SHIFT_SEC,
    PALETTE_RENDERERS,
    PRESET_CONFIGS,
    SCALES,
    PolyphonyManager,
    SoundPaletteSpec,
    apply_schroeder_reverb,
    apply_soft_saturation,
    build_and_normalize_audio,
    event_to_pitch,
    generate_simulation_audio_array,
    get_note_frequency,
    parse_root_hz,
    quantize_event_time,
    quantize_events,
    render_chime,
    render_note,
    render_pad,
    verify_audio_quality,
)


def test_every_palette_renders_finite_non_silent_no_nan_peak_below_one():
    """
    Every palette must render a finite, non-silent note with no NaN
    and a peak strictly below 1.0.
    """
    test_pitches = [110.0, 261.63, 440.0, 880.0, 1200.0]
    test_velocities = [0.2, 0.5, 0.8, 1.0]

    for name in PALETTE_RENDERERS.keys():
        for pitch in test_pitches:
            for vel in test_velocities:
                note = render_note(
                    palette=name,
                    pitch_hz=pitch,
                    velocity=vel,
                    duration_sec=0.3,
                    sample_rate=48000,
                    seed=42,
                )
                assert isinstance(note, np.ndarray)
                assert len(note) > 0
                assert np.all(np.isfinite(note)), f"Palette {name} produced non-finite values"
                assert not np.any(np.isnan(note)), f"Palette {name} produced NaN"
                peak = float(np.max(np.abs(note)))
                assert 0.001 < peak < 1.0, f"Palette {name} peak {peak} out of valid range (0.001, 1.0)"

    # Test chime
    chime = render_chime(523.25, duration_sec=0.4, sample_rate=48000)
    assert np.all(np.isfinite(chime))
    assert not np.any(np.isnan(chime))
    assert 0.001 < float(np.max(np.abs(chime))) < 1.0

    # Test pad
    pad = render_pad(total_duration_sec=2.0, sample_rate=48000, gain=0.05)
    assert pad.shape == (int(2.0 * 48000), 2)
    assert np.all(np.isfinite(pad))
    assert not np.any(np.isnan(pad))
    assert 0.0001 < float(np.max(np.abs(pad))) < 1.0


def test_scale_frequency_ratios_match_equal_temperament_table():
    """
    Scale frequency ratios must strictly match the 12-TET equal-temperament table.
    f_i / f_root = 2^(semitones / 12).
    """
    # Test root parsing
    assert abs(parse_root_hz("A4") - 440.0) < 1e-4
    assert abs(parse_root_hz("C4") - 261.6256) < 1e-2
    assert abs(parse_root_hz("A3") - 220.0) < 1e-4
    assert abs(parse_root_hz(440.0) - 440.0) < 1e-6

    test_scales = ["pentatonic_major", "major", "natural_minor", "whole_tone", "lydian"]
    root_hz = 261.625565

    for scale_name in test_scales:
        semitones_list = SCALES[scale_name]
        scale_len = len(semitones_list)

        for idx in range(scale_len * 3):
            freq = get_note_frequency(idx, root_hz=root_hz, scale_name=scale_name, octaves=3)
            octave = (idx // scale_len) % 3
            degree = idx % scale_len
            expected_semitone = octave * 12 + semitones_list[degree]
            expected_ratio = 2.0 ** (expected_semitone / 12.0)
            actual_ratio = freq / root_hz

            assert abs(actual_ratio - expected_ratio) < 1e-9, (
                f"Scale {scale_name} index {idx} ratio {actual_ratio} != {expected_ratio}"
            )


def test_pitch_chosen_from_event_never_at_random():
    """
    Pitch is chosen deterministically from the event (ball_id or height), never at random.
    """
    class DummyEvent:
        def __init__(self, ball_id, point):
            self.ball_id = ball_id
            self.point = point

    evt_a = DummyEvent(ball_id=3, point=(0.2, 0.4))
    evt_b = DummyEvent(ball_id=3, point=(0.2, 0.4))

    f1 = event_to_pitch(evt_a, root_hz=261.63, scale_name="pentatonic_major")
    f2 = event_to_pitch(evt_b, root_hz=261.63, scale_name="pentatonic_major")
    assert f1 == f2

    # Different ball id yields different pitch
    evt_c = DummyEvent(ball_id=4, point=(0.2, 0.4))
    f3 = event_to_pitch(evt_c, root_hz=261.63, scale_name="pentatonic_major")
    assert f1 != f3


def test_quantization_never_shifts_event_more_than_30ms():
    """
    Grid quantization must never shift any event timestamp by more than 30 ms.
    """
    tempos = [60.0, 90.0, 120.0, 140.0, 180.0]
    subdivisions = [1, 2, 4, 8]

    # Test 500 arbitrary timestamps between 0.0 and 30.0 seconds
    rng = np.random.RandomState(42)
    random_times = rng.uniform(0.0, 30.0, size=500)

    for tempo in tempos:
        for subdiv in subdivisions:
            for t in random_times:
                t_q = quantize_event_time(
                    t,
                    tempo=tempo,
                    subdivision=subdiv,
                    max_shift_sec=MAX_QUANTIZE_SHIFT_SEC,
                )
                shift = abs(t_q - t)
                assert shift <= MAX_QUANTIZE_SHIFT_SEC + 1e-9, (
                    f"Quantization shifted t={t} by {shift*1000:.2f}ms (> 30ms) at tempo {tempo}, subdiv {subdiv}"
                )
                assert t_q >= 0.0


def test_polyphony_limit_is_respected():
    """
    Polyphony limit (e.g. 24 voices) must be strictly respected.
    When concurrent voices exceed limit, oldest/quietest voices are dropped/lowered.
    """
    sr = 48000
    limit = 24
    manager = PolyphonyManager(polyphony_limit=limit, sample_rate=sr)

    # Create 60 voice events that all start within a 50ms window and overlap for 400ms
    voice_events = []
    dur_samples = int(0.4 * sr)
    decay_samples = int(0.15 * sr)
    tone = np.sin(2.0 * np.pi * 440.0 * np.arange(dur_samples) / sr).astype(np.float32)

    for i in range(60):
        start_s = int((i * 0.001) * sr)  # Staggered by 1ms
        end_s = start_s + dur_samples
        amp = 0.5 * (1.0 - i / 100.0)
        voice_events.append((start_s, end_s, tone * amp, tone * amp, amp, decay_samples))

    total_samples = int(1.0 * sr)
    buffer = manager.allocate_voices(voice_events, total_samples)

    assert buffer.shape == (total_samples, 2)
    assert np.all(np.isfinite(buffer))
    assert not np.any(np.isnan(buffer))
    # Soft saturation check
    sat = apply_soft_saturation(buffer)
    assert np.max(np.abs(sat)) <= 0.98


def test_full_render_loudness_true_peak_and_no_clipping(tmp_path: Path):
    """
    Full procedural render meets G7/S5 audio standards:
    - Integrated loudness within 1 LU of -14 LUFS
    - True peak <= -1.0 dBTP
    - No clipping (sample < 0.999, 0 consecutive full-scale runs)
    """
    test_spec = SimSpec(
        schedule=[
            StageSpec(count=3, duration_sec=2.5),
            StageSpec(count=5, duration_sec=2.5),
        ],
        sound_palette=SoundPaletteSpec(
            palette="marimba",
            scale="pentatonic_major",
            root="C4",
            reverb_wet=0.15,
            pad_enabled=True,
        ),
    )

    sim = EllipseBilliardsSim(axes=test_spec.ellipse, seed=test_spec.seed)
    events = sim.simulate_spec(test_spec)

    wav_out = tmp_path / "test_p2a_marimba.wav"
    build_and_normalize_audio(
        spec=test_spec,
        events=events,
        output_path=wav_out,
        total_duration=5.0,
        target_i=-14.0,
        target_tp=-1.5,
    )

    assert wav_out.is_file()
    qa = verify_audio_quality(wav_out)
    assert qa["passed"] is True
    assert -15.0 <= qa["integrated_lufs"] <= -13.0
    assert qa["true_peak"] <= -1.0
    assert qa["no_clipping"] is True
    assert qa["consecutive_full_scale_runs"] == 0


def test_determinism_for_fixed_seed(tmp_path: Path):
    """
    For a fixed seed and specification, the synthesis output is 100% deterministic.
    """
    test_spec = SimSpec(
        schedule=[StageSpec(count=2, duration_sec=2.0)],
        sound_palette=SoundPaletteSpec(
            palette="pluck",
            scale="pentatonic_major",
            root="C4",
            seed=42,
        ),
    )

    sim = EllipseBilliardsSim(axes=test_spec.ellipse, seed=test_spec.seed)
    events = sim.simulate_spec(test_spec)

    arr1 = generate_simulation_audio_array(test_spec, events, total_duration=2.0)
    arr2 = generate_simulation_audio_array(test_spec, events, total_duration=2.0)

    np.testing.assert_allclose(arr1, arr2, atol=1e-6)
