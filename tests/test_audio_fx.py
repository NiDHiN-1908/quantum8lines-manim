"""
Tests for audio loudness normalization, postfx presets, and ducked mixing.
Follows SPEC.md Section 10 and Milestone M3b Step 1.
"""

from pathlib import Path
import subprocess
import pytest
import numpy as np
import soundfile as sf

from pipeline.audio_fx import measure_loudness, normalize, mix, POSTFX_PRESETS


def _create_synthetic_tone(path: Path, duration_sec: float = 4.0, freq_hz: float = 440.0, volume: float = 0.2):
    """Generates a synthetic sine tone WAV file."""
    sr = 24000
    t = np.linspace(0, duration_sec, int(duration_sec * sr), endpoint=False, dtype=np.float32)
    samples = (volume * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)
    sf.write(str(path), samples, sr)


def test_measure_loudness_and_normalization(tmp_path):
    """
    Test two-pass normalization on synthetic tone:
    Output integrated loudness within 1 LU of -14, true peak at or below -1.0 dBTP, no clipping.
    """
    in_wav = tmp_path / "raw_tone.wav"
    out_wav = tmp_path / "norm_tone.wav"
    _create_synthetic_tone(in_wav, duration_sec=5.0, freq_hz=300.0, volume=0.1)

    initial_stats = measure_loudness(in_wav)
    assert "integrated_lufs" in initial_stats
    assert "true_peak" in initial_stats

    res = normalize(in_wav, out_wav, target_i=-14.0, target_tp=-1.0)
    after = res["after"]

    # Integrated loudness within 1 LU of -14
    assert -15.0 <= after["integrated_lufs"] <= -13.0, (
        f"Normalized loudness {after['integrated_lufs']} LUFS is outside [-15, -13]"
    )

    # True peak at or below -1.0 dBTP (within 0.1 tolerance)
    assert after["true_peak"] <= -0.9, (
        f"Normalized true peak {after['true_peak']} dBTP exceeds -1.0 dBTP limit"
    )

    # No clipping (must be strictly < 0 dBTP)
    assert after["true_peak"] < 0.0


@pytest.mark.parametrize("preset", ["clean", "warm_narration"])
def test_normalization_with_postfx(tmp_path, preset):
    """
    Test normalization chained with postfx presets.
    """
    in_wav = tmp_path / f"raw_{preset}.wav"
    out_wav = tmp_path / f"norm_{preset}.wav"
    _create_synthetic_tone(in_wav, duration_sec=5.0, freq_hz=220.0, volume=0.15)

    res = normalize(in_wav, out_wav, target_i=-14.0, target_tp=-1.0, postfx=preset)
    after = res["after"]

    assert -15.5 <= after["integrated_lufs"] <= -13.0
    assert after["true_peak"] <= -0.9
    assert after["true_peak"] < 0.0


def test_mix_ducking_with_generated_tone(tmp_path):
    """
    Test ducked mixing with synthetic voice and music tracks.
    """
    voice_wav = tmp_path / "voice.wav"
    music_wav = tmp_path / "music.wav"
    mix_wav = tmp_path / "final_mix.wav"

    # Voice tone: 4.0 seconds at 440 Hz
    _create_synthetic_tone(voice_wav, duration_sec=4.0, freq_hz=440.0, volume=0.25)
    # Music tone: 5.0 seconds at 180 Hz
    _create_synthetic_tone(music_wav, duration_sec=5.0, freq_hz=180.0, volume=0.15)

    out_path = mix(narration=voice_wav, music=music_wav, out=mix_wav, duck_music_db=-18.0)
    assert out_path.exists()

    stats = measure_loudness(out_path)
    assert -15.5 <= stats["integrated_lufs"] <= -13.0
    assert stats["true_peak"] <= -0.9
