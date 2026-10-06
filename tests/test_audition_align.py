"""
Tests for Audition Set, Whisper alignment, and Word Error Rate (WER) computation.
Follows SPEC.md Section 10 and Milestone M3a Step 4.
"""

from pathlib import Path
import json
import pytest

from pipeline.align import compute_wer
from pipeline.audition import DEFAULT_AUDITION_SET_PATH, get_candidate_profiles


def test_audition_set_json_structure():
    """Verify brand/voices/audition_set.json contains all 5 required lines and beats."""
    assert DEFAULT_AUDITION_SET_PATH.exists()
    with open(DEFAULT_AUDITION_SET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    lines = data.get("lines", [])
    assert len(lines) == 5

    expected_beats = ["hook", "explain", "equation", "aha", "close"]
    for i, expected_beat in enumerate(expected_beats):
        assert lines[i]["id"] == expected_beat
        assert lines[i]["beat"] == expected_beat
        assert len(lines[i]["text"]) > 10


def test_get_candidate_profiles():
    """Verify at least 6 candidate profiles are loaded from brand/voices/."""
    candidates = get_candidate_profiles()
    assert len(candidates) >= 6
    profile_ids = [c.id for c in candidates]
    assert "calm_curious_heart" in profile_ids
    assert "calm_curious_michael" in profile_ids
    assert "energetic_playful_bella" in profile_ids
    assert "energetic_playful_adam" in profile_ids
    assert "serious_cinematic_george" in profile_ids
    assert "serious_cinematic_fenrir" in profile_ids


def test_wer_identical_strings():
    """Identical strings must have 0.0 Word Error Rate."""
    ref = "A matrix takes every vector in the plane and moves it somewhere else."
    hyp = "A matrix takes every vector in the plane and moves it somewhere else."
    assert compute_wer(ref, hyp) == 0.0


def test_wer_case_and_punctuation_invariant():
    """Normalization must strip punctuation and ignore case differences."""
    ref = "What if some arrows refuse to turn, no matter how hard you push?"
    hyp = "what if some arrows refuse to turn no matter how hard you push"
    assert compute_wer(ref, hyp) == 0.0


def test_wer_single_substitution():
    """1 substitution in 4 words = 0.25 WER."""
    ref = "the quick brown fox"
    hyp = "the fast brown fox"
    assert compute_wer(ref, hyp) == 0.25


def test_wer_single_insertion():
    """1 insertion in 4 words = 0.25 WER."""
    ref = "the quick brown fox"
    hyp = "the very quick brown fox"
    assert compute_wer(ref, hyp) == 0.25


def test_wer_single_deletion():
    """1 deletion in 4 words = 0.25 WER."""
    ref = "the quick brown fox"
    hyp = "the brown fox"
    assert compute_wer(ref, hyp) == 0.25


def test_wer_empty_strings():
    """Empty strings edge cases."""
    assert compute_wer("", "") == 0.0
    assert compute_wer("some words", "") == 1.0
    assert compute_wer("", "some words") == 1.0
