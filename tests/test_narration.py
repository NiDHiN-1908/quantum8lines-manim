"""
Tests for Narration Builder: audio concatenation, pause handling, timing arithmetic,
and checkpointing using synthetic audio (NO TTS calls).
Follows SPEC.md Sections 5.2, 8, 10 and Milestone M3a Step 3.
"""

from pathlib import Path
import json
from typing import Tuple, List
import pytest
import numpy as np
import soundfile as sf

from pipeline.tts.base import TTSEngine
from pipeline.tts.schemas import VoiceProfile
from pipeline.narration import build_narration


class MockToneTTSEngine(TTSEngine):
    """
    Synthetic mock TTS engine generating pure sine tones without any model dependencies.
    Duration is configurable or fixed per synthesis call.
    """

    def __init__(self, sample_rate: int = 24000, duration_sec: float = 1.0):
        self.sample_rate = sample_rate
        self.duration_sec = duration_sec
        self.call_count = 0
        self.synthesized_texts: List[str] = []

    @property
    def name(self) -> str:
        return "mock_tone"

    @property
    def is_available(self) -> bool:
        return True

    def get_voices(self) -> List[str]:
        return ["mock_voice_1", "mock_voice_2"]

    def synthesize(self, text: str, profile: VoiceProfile) -> Tuple[np.ndarray, int]:
        self.call_count += 1
        self.synthesized_texts.append(text)

        # Generate a 440 Hz sine tone for self.duration_sec
        num_samples = int(self.duration_sec * self.sample_rate)
        t = np.linspace(0, self.duration_sec, num_samples, endpoint=False, dtype=np.float32)
        samples = 0.5 * np.sin(2 * np.pi * 440 * t)
        return samples, self.sample_rate


@pytest.fixture
def mock_profile():
    return VoiceProfile(
        id="test_mock_profile",
        engine="mock_tone",
        voice="mock_voice_1",
        speed=1.0,
        tone="calm_curious",
        pause_ms={"sentence": 300, "aha": 600},
        license_note="Mock engine test",
        status="candidate",
    )


@pytest.fixture
def sample_chapter(tmp_path):
    chapter_dir = tmp_path / "ch01"
    chapter_dir.mkdir()
    script_data = {
        "chapter": "ch01",
        "lines": [
            {
                "id": "l01",
                "beat": "hook",
                "text": "What if some arrows refuse to turn?",
                "pronounce": {},
            },
            {
                "id": "l02",
                "beat": "aha",
                "text": "An eigenvector is a special direction.",
                "pronounce": {"eigenvector": "custom-vector"},
            },
            {
                "id": "l03",
                "beat": "close",
                "text": "See you in the next chapter.",
                "pronounce": {},
            }
        ]
    }
    with open(chapter_dir / "script.json", "w", encoding="utf-8") as f:
        json.dump(script_data, f, indent=2)
    return chapter_dir


def test_narration_timing_and_concatenation(sample_chapter, mock_profile):
    """
    Test timing arithmetic and pause insertion:
    - Line 1 (hook): 1.0s duration + 0.3s sentence pause -> next line starts at 1.3s
    - Line 2 (aha): 1.0s duration + 0.6s aha pause -> next line starts at 2.9s
    - Line 3 (close): 1.0s duration + 0.3s sentence pause -> total = 4.2s
    """
    engine = MockToneTTSEngine(sample_rate=24000, duration_sec=1.0)
    timings = build_narration(sample_chapter, mock_profile, engine=engine)

    assert timings["chapter"] == "ch01"
    assert timings["profile_id"] == "test_mock_profile"
    assert timings["sample_rate"] == 24000
    assert engine.call_count == 3

    lines = timings["lines"]
    assert len(lines) == 3

    # Line 1: hook (standard pause: 0.3s)
    assert lines[0]["id"] == "l01"
    assert lines[0]["start"] == pytest.approx(0.0, abs=1e-3)
    assert lines[0]["end"] == pytest.approx(1.0, abs=1e-3)
    assert lines[0]["duration"] == pytest.approx(1.0, abs=1e-3)
    assert lines[0]["pause_after"] == pytest.approx(0.3, abs=1e-3)

    # Line 2: aha (aha pause: 0.6s)
    assert lines[1]["id"] == "l02"
    assert lines[1]["start"] == pytest.approx(1.3, abs=1e-3)
    assert lines[1]["end"] == pytest.approx(2.3, abs=1e-3)
    assert lines[1]["duration"] == pytest.approx(1.0, abs=1e-3)
    assert lines[1]["pause_after"] == pytest.approx(0.6, abs=1e-3)
    # Check pronunciation override
    assert "custom-vector" in lines[1]["prepared_text"]
    assert lines[1]["text"] == "An eigenvector is a special direction."

    # Line 3: close (standard pause: 0.3s)
    assert lines[2]["id"] == "l03"
    assert lines[2]["start"] == pytest.approx(2.9, abs=1e-3)
    assert lines[2]["end"] == pytest.approx(3.9, abs=1e-3)
    assert lines[2]["duration"] == pytest.approx(1.0, abs=1e-3)
    assert lines[2]["pause_after"] == pytest.approx(0.3, abs=1e-3)

    # Total duration = 1.0 + 0.3 + 1.0 + 0.6 + 1.0 + 0.3 = 4.2 seconds
    expected_total = 4.2
    assert timings["total_duration"] == pytest.approx(expected_total, abs=1e-3)

    # Verify generated audio files
    audio_dir = sample_chapter / "audio"
    assert (audio_dir / "narration.wav").exists()
    assert (audio_dir / "lines" / "l01.wav").exists()
    assert (audio_dir / "lines" / "l02.wav").exists()
    assert (audio_dir / "lines" / "l03.wav").exists()
    assert (audio_dir / "timings.json").exists()

    # Verify narration.wav audio length matches total duration
    narr_samples, narr_sr = sf.read(str(audio_dir / "narration.wav"))
    assert narr_sr == 24000
    assert len(narr_samples) == int(round(expected_total * 24000))


def test_narration_checkpointing(sample_chapter, mock_profile):
    """
    Test checkpointing logic:
    - First run synthesizes all 3 lines.
    - Second run with identical script skips all synthesis calls (0 calls).
    - Modifying 1 line re-synthesizes ONLY that line (1 call).
    """
    engine = MockToneTTSEngine(sample_rate=24000, duration_sec=1.0)

    # First run
    build_narration(sample_chapter, mock_profile, engine=engine)
    assert engine.call_count == 3

    # Second run without changes
    engine.call_count = 0
    build_narration(sample_chapter, mock_profile, engine=engine)
    assert engine.call_count == 0, "Unchanged lines should be skipped via checkpoints"

    # Modify line 2
    script_path = sample_chapter / "script.json"
    with open(script_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["lines"][1]["text"] = "A modified line text here."
    with open(script_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    # Third run: only line 2 should be synthesized
    engine.call_count = 0
    build_narration(sample_chapter, mock_profile, engine=engine)
    assert engine.call_count == 1, "Only modified line should be re-synthesized"
    assert "A modified line text here." in engine.synthesized_texts
