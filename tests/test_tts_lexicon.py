"""
Tests for TTS Engine interfaces, Voice Profiles, and Lexicon processing.
Follows SPEC.md Section 10 and Milestone M3a Steps 1 and 2.
"""

from pathlib import Path
import pytest
import numpy as np

from pipeline.lexicon import prepare_text, load_lexicon, DEFAULT_LEXICON_PATH
from pipeline.tts.schemas import VoiceProfile, load_voice_profile
from pipeline.tts import get_tts_engine, KokoroEngine


# ============================================================================
# Step 2 Lexicon Tests
# ============================================================================

def test_lexicon_whole_word_matching():
    """Whole-word matching: 'eigenvectors' must not be corrupted by 'eigenvector'."""
    lexicon = {
        "eigenvector": "eye-gen vector",
        "eigenvalue": "eye-gen value",
        "eigen": "eye-gen",
    }
    # Plural must remain untouched because no plural entry exists
    result_plural = prepare_text("These eigenvectors refuse to turn.", lexicon=lexicon)
    assert "eigenvectors" in result_plural
    assert "eye-gen vector" not in result_plural
    assert "eye-gen" not in result_plural

    # Singular must match
    result_singular = prepare_text("An eigenvector refuses to turn.", lexicon=lexicon)
    assert "eye-gen vector" in result_singular
    assert "eigenvector" not in result_singular


def test_lexicon_case_insensitivity():
    """Case-insensitive matching for lexicon entries."""
    lexicon = {
        "eigenvector": "eye-gen vector",
        "quantum8lines": "Quantum Eight Lines",
    }
    assert prepare_text("The EIGENVECTOR points up.", lexicon=lexicon) == "The eye-gen vector points up."
    assert prepare_text("An EigenVector points up.", lexicon=lexicon) == "An eye-gen vector points up."
    assert prepare_text("Welcome to QUANTUM8LINES!", lexicon=lexicon) == "Welcome to Quantum Eight Lines!"
    assert prepare_text("Welcome to Quantum8Lines!", lexicon=lexicon) == "Welcome to Quantum Eight Lines!"


def test_lexicon_compound_priority():
    """Ensure longer terms like 'eigenvector' match before 'eigen'."""
    lexicon = {
        "eigen": "eye-gen",
        "eigenvector": "eye-gen vector",
        "eigenvalue": "eye-gen value",
    }
    result = prepare_text("The eigenvector and eigenvalue are eigen things.", lexicon=lexicon)
    assert result == "The eye-gen vector and eye-gen value are eye-gen things."


def test_lexicon_per_line_override_priority():
    """Per-line 'pronounce' dict in script line overrides global lexicon."""
    global_lexicon = {
        "eigenvector": "eye-gen vector",
        "lambda": "LAM-duh",
    }
    line = {
        "id": "l01",
        "text": "The eigenvector has eigenvalue lambda.",
        "pronounce": {
            "eigenvector": "CUSTOM-PRONUNCIATION",
        }
    }
    prepared = prepare_text(line, lexicon=global_lexicon)
    assert "CUSTOM-PRONUNCIATION" in prepared
    assert "eye-gen vector" not in prepared
    # 'lambda' should still be handled by global lexicon
    assert "LAM-duh" in prepared

    # Ensure original text in line dict is NOT modified
    assert line["text"] == "The eigenvector has eigenvalue lambda."


def test_brand_lexicon_file_content():
    """Verify brand/lexicon.json exists and contains required seed entries."""
    assert DEFAULT_LEXICON_PATH.exists()
    lexicon = load_lexicon(DEFAULT_LEXICON_PATH)
    assert "eigenvector" in lexicon
    assert "eigenvalue" in lexicon
    assert "eigen" in lexicon
    assert "Quantum8Lines" in lexicon
    assert lexicon["eigenvector"] == "eye-gen vector"
    assert lexicon["eigenvalue"] == "eye-gen value"
    assert lexicon["eigen"] == "eye-gen"
    assert lexicon["Quantum8Lines"] == "Quantum Eight Lines"


# ============================================================================
# Step 1 VoiceProfile Schema and Candidate Profiles Tests
# ============================================================================

EXPECTED_CANDIDATE_IDS = [
    "calm_curious_heart",
    "calm_curious_michael",
    "energetic_playful_bella",
    "energetic_playful_adam",
    "serious_cinematic_george",
    "serious_cinematic_fenrir",
]


@pytest.mark.parametrize("profile_id", EXPECTED_CANDIDATE_IDS)
def test_candidate_voice_profiles_valid(profile_id):
    """Verify all 6 candidate profiles exist and validate against VoiceProfile schema."""
    profile_path = Path("brand/voices") / f"{profile_id}.json"
    assert profile_path.exists(), f"Profile file missing: {profile_path}"

    profile = load_voice_profile(profile_path)
    assert profile.id == profile_id
    assert profile.engine == "kokoro"
    assert profile.status == "candidate"
    assert 0.5 <= profile.speed <= 2.0
    assert profile.tone in ["calm_curious", "energetic_playful", "serious_cinematic"]
    assert "sentence" in profile.pause_ms
    assert "aha" in profile.pause_ms
    assert profile.pause_ms["sentence"] > 0
    assert profile.pause_ms["aha"] > 0
    assert "Apache-2.0" in profile.license_note
    assert "https://huggingface.co/hexgrad/Kokoro-82M" in profile.license_note


def test_voice_profile_pause_helpers():
    """Verify pause conversion to seconds."""
    profile = VoiceProfile(
        id="test_voice",
        engine="kokoro",
        voice="af_heart",
        speed=1.0,
        tone="calm_curious",
        pause_ms={"sentence": 350, "aha": 750},
        license_note="Apache-2.0",
    )
    assert profile.get_sentence_pause_sec() == 0.35
    assert profile.get_aha_pause_sec() == 0.75


# ============================================================================
# Step 1 TTSEngine and Kokoro Adapter Tests
# ============================================================================

def test_tts_engine_factory():
    """Verify TTSEngine factory lookup."""
    engine = get_tts_engine("kokoro")
    assert isinstance(engine, KokoroEngine)
    assert engine.name == "kokoro"

    with pytest.raises(ValueError, match="Unknown TTS engine"):
        get_tts_engine("non_existent_engine")


def test_kokoro_model_discovery_or_clean_skip():
    """
    Kokoro tests must skip cleanly when models/ files are missing,
    as models/ is git-ignored.
    """
    engine = KokoroEngine()
    if not engine.is_available:
        pytest.skip(
            "Kokoro model files not found in models/ "
            "(kokoro-v1.0.int8.onnx and/or voices-v1.0.bin missing). "
            "Skipping cleanly per SPEC rules."
        )

    voices = engine.get_voices()
    assert isinstance(voices, list)
    assert len(voices) > 0
    # Confirm candidate voices are in the catalog
    for voice_name in ["af_heart", "am_michael", "af_bella", "am_adam", "bm_george", "am_fenrir"]:
        assert voice_name in voices, f"Voice '{voice_name}' should be in Kokoro voices catalog"


def test_kokoro_invalid_voice_raises():
    """Verify that requesting an invalid voice raises ValueError."""
    engine = KokoroEngine()
    if not engine.is_available:
        pytest.skip("Kokoro models missing, skipping clean.")

    invalid_profile = VoiceProfile(
        id="invalid_test",
        engine="kokoro",
        voice="invalid_voice_name_12345",
        speed=1.0,
        tone="calm_curious",
        license_note="Apache-2.0",
    )
    with pytest.raises(ValueError, match="not found in Kokoro catalog"):
        engine.synthesize("Hello world", invalid_profile)
