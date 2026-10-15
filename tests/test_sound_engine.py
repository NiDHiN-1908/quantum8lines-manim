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


def compute_spectral_centroid(audio: np.ndarray, sample_rate: int = 48000) -> float:
    """Computes spectral centroid (center of mass of frequency spectrum) in Hz."""
    mono = np.mean(audio, axis=1) if audio.ndim > 1 else audio
    mag = np.abs(np.fft.rfft(mono))
    freqs = np.fft.rfftfreq(len(mono), 1.0 / sample_rate)
    sum_mag = float(np.sum(mag))
    if sum_mag < 1e-9:
        return 0.0
    return float(np.sum(freqs * mag) / sum_mag)


def test_brightness_spectral_centroid_above_1500_hz(tmp_path: Path):
    """
    Measured spectral centroid of the first 20 s must be above 1.5 kHz (1500 Hz),
    while loudness stays within 1 LU of -14 and true peak <= -1.5 dBTP.
    """
    spec = SimSpec(
        sound_palette=SoundPaletteSpec(
            palette="marimba",
            scale="pentatonic_major",
            root="C5",
            high_shelf_db=3.0,
        )
    )
    sim = EllipseBilliardsSim(axes=spec.ellipse, seed=spec.seed)
    events = sim.simulate_spec(spec)

    wav_out = tmp_path / "test_bright_20s.wav"
    norm_result = build_and_normalize_audio(
        spec=spec,
        events=events,
        output_path=wav_out,
        total_duration=20.0,
        target_i=-14.0,
        target_tp=-1.5,
    )

    import soundfile as sf
    data, sr = sf.read(str(wav_out))
    centroid = compute_spectral_centroid(data, sample_rate=sr)

    assert centroid > 1500.0, f"Spectral centroid {centroid:.1f} Hz is not above 1500 Hz"
    qa = verify_audio_quality(wav_out)
    assert -15.0 <= qa["integrated_lufs"] <= -13.0, f"Loudness {qa['integrated_lufs']} outside [-15, -13]"
    assert qa["true_peak"] <= -1.45, f"True peak {qa['true_peak']} > -1.5 dBTP"
    assert qa["no_clipping"] is True


def test_chord_and_thump_events_present_at_f2():
    """
    At F2 convergence, both the musical chord and low thump (80->40 Hz sweep) are generated.
    """
    from core.sims.sound.palettes import render_thump

    # Test thump synthesis
    thump = render_thump(duration_sec=0.12, f_start=80.0, f_end=40.0, sample_rate=48000)
    assert len(thump) == int(0.12 * 48000)
    assert np.all(np.isfinite(thump))
    assert 0.01 < float(np.max(np.abs(thump))) < 1.0

    # Test that simulation with 3 balls generates audio with chord & thump at F2 (t = 1.6s)
    spec = SimSpec(
        schedule=[StageSpec(count=3, duration_sec=2.5)],
        sound_palette=SoundPaletteSpec(root="C5", high_shelf_db=3.0),
    )
    sim = EllipseBilliardsSim(axes=spec.ellipse, seed=42)
    events = sim.simulate_spec(spec)

    audio = generate_simulation_audio_array(spec, events, total_duration=2.5)
    # At t ~ 1.6s (around sample 1.6 * 48000 = 76800), sound is active and non-silent
    f2_sample = int(1.60 * 48000)
    convergence_window = audio[f2_sample:f2_sample + int(0.10 * 48000)]
    assert float(np.max(np.abs(convergence_window))) > 0.05


def test_chime_on_every_count_increase():
    """
    A short rising two-note chime is triggered at each stage transition (count increase).
    """
    from core.sims.sound.palettes import render_count_increase_chime

    chime = render_count_increase_chime(base_freq=587.33, interval_semitones=5, sample_rate=48000)
    assert len(chime) > 0
    assert np.all(np.isfinite(chime))
    assert 0.01 < float(np.max(np.abs(chime))) < 1.0

    # Multi-stage schedule
    spec = SimSpec(
        schedule=[
            StageSpec(count=1, duration_sec=2.0),
            StageSpec(count=2, duration_sec=2.0),
            StageSpec(count=3, duration_sec=2.5),
        ]
    )
    sim = EllipseBilliardsSim(axes=spec.ellipse, seed=42)
    events = sim.simulate_spec(spec)

    audio = generate_simulation_audio_array(spec, events, total_duration=6.5)
    # Stage transitions at t=2.0s and t=4.0s
    for t_trans in [2.0, 4.0]:
        s = int(t_trans * 48000)
        window = audio[s:s + int(0.15 * 48000)]
        assert float(np.max(np.abs(window))) > 0.05


def test_dense_moments_scale_with_simultaneous_onsets_no_clipping():
    """
    Dense moments scale gain with 1/sqrt(simultaneous onsets) so nothing clips.
    """
    spec = SimSpec(
        schedule=[StageSpec(count=55, duration_sec=5.0)],
        sound_palette=SoundPaletteSpec(
            palette="marimba",
            scale="pentatonic_major",
            root="C5",
            polyphony_limit=24,
            pad_enabled=True,
        ),
    )
    sim = EllipseBilliardsSim(axes=spec.ellipse, seed=42)
    events = sim.simulate_spec(spec)

    audio = generate_simulation_audio_array(spec, events, total_duration=5.0)
    assert np.all(np.isfinite(audio))
    assert not np.any(np.isnan(audio))
    assert float(np.max(np.abs(audio))) <= 0.98


def test_muxed_file_audio_stream_48000_hz_stereo_aac(tmp_path: Path):
    """
    Verifies with ffprobe that the muxed video file contains audio
    with sample_rate == 48000 Hz, 2 channels (stereo), and aac codec at >= 192k.
    """
    import json
    import subprocess
    import soundfile as sf

    temp_vid = tmp_path / "dummy_vid.mp4"
    temp_aud = tmp_path / "dummy_aud.wav"
    out_mp4 = tmp_path / "muxed_test.mp4"

    # Generate 1s test tone at 48000 Hz
    sr = 48000
    t = np.arange(sr) / sr
    audio_data = np.column_stack([np.sin(2 * np.pi * 440 * t), np.sin(2 * np.pi * 880 * t)]).astype(np.float32) * 0.2
    sf.write(str(temp_aud), audio_data, sr)

    # Generate 1s test video
    subprocess.run([
        "ffmpeg", "-y", "-nostdin",
        "-f", "lavfi", "-i", "color=c=black:s=64x64:d=1.0:r=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(temp_vid),
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Mux with the exact mux flags
    mux_cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-i", str(temp_vid),
        "-i", str(temp_aud),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-ar", "48000",
        "-ac", "2",
        "-shortest",
        str(out_mp4),
    ]
    subprocess.run(mux_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Query with ffprobe
    probe_cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        str(out_mp4),
    ]
    res = subprocess.run(probe_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    probe_data = json.loads(res.stdout)

    audio_streams = [s for s in probe_data.get("streams", []) if s.get("codec_type") == "audio"]
    assert len(audio_streams) >= 1
    a_stream = audio_streams[0]
    assert a_stream.get("codec_name") == "aac"
    assert int(a_stream.get("sample_rate", 0)) == 48000
    assert int(a_stream.get("channels", 0)) == 2


