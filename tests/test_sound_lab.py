"""
Unit tests for Sound Lab pure business logic: scoring, aggregation,
approval gate refusal/override, and simulation spec assignment.
Zero Streamlit dependencies.
Follows SPEC.md Section 22.5 and Milestone P2a Step 3.
"""

from pathlib import Path
import json
import pytest

from review_ui.sound_lab_logic import (
    ACCEPTANCE_RULES,
    aggregate_sound_scores,
    approve_preset,
    assign_palette_to_sim,
    load_sound_scores,
    record_sound_evaluation,
    save_sound_scores,
)
from core.sims.sound.models import PRESET_CONFIGS, SoundPaletteSpec


def test_sound_score_recording_and_validation(tmp_path: Path):
    """Verifies score recording, range validation [1, 5], and persistence."""
    scores_file = tmp_path / "sound_scores.json"

    # Valid evaluation
    entry = record_sound_evaluation(
        listener="Alice",
        preset_id="marimba+pentatonic",
        sim_id="ellipse_billiards",
        score=5,
        keep_watching=True,
        scores_path=scores_file,
    )
    assert entry["listener"] == "Alice"
    assert entry["score"] == 5
    assert entry["keep_watching"] is True

    # Check file contents
    loaded = load_sound_scores(scores_file)
    assert len(loaded) == 1
    assert loaded[0]["listener"] == "Alice"

    # Invalid score < 1
    with pytest.raises(ValueError, match="between 1 and 5"):
        record_sound_evaluation(
            listener="Bob",
            preset_id="marimba+pentatonic",
            score=0,
            scores_path=scores_file,
        )

    # Invalid score > 5
    with pytest.raises(ValueError, match="between 1 and 5"):
        record_sound_evaluation(
            listener="Bob",
            preset_id="marimba+pentatonic",
            score=6,
            scores_path=scores_file,
        )


def test_sound_score_aggregation_and_acceptance_rules(tmp_path: Path):
    """
    Verifies pass rule:
    - At least 5 unique listeners
    - Mean pleasantness score >= 4.0
    - Keep-watching rate >= 70%
    """
    scores_file = tmp_path / "sound_scores.json"

    # Case 1: Passing preset (5 listeners, mean 4.6, keep-watching 100%)
    passing_preset = "marimba+pentatonic"
    for i in range(5):
        record_sound_evaluation(
            listener=f"Listener_{i}",
            preset_id=passing_preset,
            score=4 if i % 2 == 0 else 5,
            keep_watching=True,
            scores_path=scores_file,
        )

    # Case 2: Insufficient listeners (< 5 listeners)
    few_listeners = "bell+lydian"
    for i in range(3):
        record_sound_evaluation(
            listener=f"Listener_{i}",
            preset_id=few_listeners,
            score=5,
            keep_watching=True,
            scores_path=scores_file,
        )

    # Case 3: Low pleasantness (< 4.0)
    low_score = "pluck+pentatonic"
    for i in range(5):
        record_sound_evaluation(
            listener=f"Listener_{i}",
            preset_id=low_score,
            score=3,
            keep_watching=True,
            scores_path=scores_file,
        )

    # Case 4: Low keep-watching (< 70%)
    low_keep = "glass+whole-tone"
    for i in range(5):
        record_sound_evaluation(
            listener=f"Listener_{i}",
            preset_id=low_keep,
            score=5,
            keep_watching=(i == 0),  # 1 out of 5 = 20%
            scores_path=scores_file,
        )

    scores = load_sound_scores(scores_file)
    agg = aggregate_sound_scores(scores)

    # Case 1 assertions
    assert agg[passing_preset]["passed"] is True
    assert agg[passing_preset]["listener_count"] == 5
    assert agg[passing_preset]["mean_pleasantness"] >= 4.0
    assert agg[passing_preset]["keep_watching_pct"] == 100.0

    # Case 2 assertions (insufficient listeners)
    assert agg[few_listeners]["passed"] is False
    assert any("Listener count" in r for r in agg[few_listeners]["failure_reasons"])

    # Case 3 assertions (low pleasantness)
    assert agg[low_score]["passed"] is False
    assert any("Mean pleasantness" in r for r in agg[low_score]["failure_reasons"])

    # Case 4 assertions (low keep-watching)
    assert agg[low_keep]["passed"] is False
    assert any("Keep-watching" in r for r in agg[low_keep]["failure_reasons"])


def test_approval_refusal_and_override_handling(tmp_path: Path):
    """
    Verifies that unapproved presets cannot be approved without an explicit override reason.
    """
    scores_file = tmp_path / "sound_scores.json"
    approvals_file = tmp_path / "approvals.json"

    # Record 2 low evaluations (fails criteria)
    failing_preset = "bell+lydian"
    record_sound_evaluation(listener="Alice", preset_id=failing_preset, score=2, keep_watching=False, scores_path=scores_file)
    record_sound_evaluation(listener="Bob", preset_id=failing_preset, score=3, keep_watching=False, scores_path=scores_file)

    # 1. Approval must be refused when criteria fail and allow_override is False
    with pytest.raises(ValueError, match="Acceptance criteria not met"):
        approve_preset(
            preset_id=failing_preset,
            scores_path=scores_file,
            allow_override=False,
            approvals_path=approvals_file,
        )

    # 2. Refusal when allow_override is True but reason is empty
    with pytest.raises(ValueError, match="requires a non-empty override_reason"):
        approve_preset(
            preset_id=failing_preset,
            scores_path=scores_file,
            allow_override=True,
            override_reason="   ",
            approvals_path=approvals_file,
        )

    # 3. Success when allow_override is True with valid reason
    record = approve_preset(
        preset_id=failing_preset,
        scores_path=scores_file,
        allow_override=True,
        override_reason="Director artistic preference for experimental short",
        approvals_path=approvals_file,
    )
    assert record["status"] == "approved"
    assert record["override"] is True
    assert "Director artistic preference" in record["override_reason"]

    # 4. Success for passing preset without override
    passing_preset = "marimba+pentatonic"
    for i in range(5):
        record_sound_evaluation(
            listener=f"User_{i}",
            preset_id=passing_preset,
            score=5,
            keep_watching=True,
            scores_path=scores_file,
        )

    passing_rec = approve_preset(
        preset_id=passing_preset,
        scores_path=scores_file,
        allow_override=False,
        approvals_path=approvals_file,
    )
    assert passing_rec["status"] == "approved"
    assert passing_rec["override"] is False


def test_assign_palette_to_sim_writes_spec(tmp_path: Path):
    """
    Verifies that assigning a preset writes the sound_palette block into sims/<id>/sim_spec.json.
    """
    sim_dir = tmp_path / "test_sim"
    sim_dir.mkdir(parents=True)
    spec_file = sim_dir / "sim_spec.json"

    # Base sim_spec without sound_palette
    base_spec = {
        "title": "Test Sim",
        "counter_label": "Units",
        "schedule": [{"count": 1, "duration_sec": 3.0}],
    }
    with open(spec_file, "w", encoding="utf-8") as f:
        json.dump(base_spec, f, indent=2)

    # Assign preset by string name
    updated_path = assign_palette_to_sim("marimba+pentatonic", sim_dir=sim_dir)
    assert updated_path == spec_file

    with open(spec_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "sound_palette" in data
    assert data["sound_palette"]["palette"] == "marimba"
    assert data["sound_palette"]["scale"] == "pentatonic_major"
    assert data["sound_palette"]["root"] == "C5"

    # Assign with custom SoundPaletteSpec object
    custom_spec = SoundPaletteSpec(
        palette="pluck",
        scale="lydian",
        root="D4",
        reverb_wet=0.30,
    )
    assign_palette_to_sim(custom_spec, sim_dir=sim_dir)

    with open(spec_file, "r", encoding="utf-8") as f:
        data2 = json.load(f)

    assert data2["sound_palette"]["palette"] == "pluck"
    assert data2["sound_palette"]["scale"] == "lydian"
    assert data2["sound_palette"]["root"] == "D4"
    assert data2["sound_palette"]["reverb_wet"] == 0.30

    # Reject invalid preset
    with pytest.raises(ValueError, match="Unknown sound preset"):
        assign_palette_to_sim("non_existent_preset_xyz", sim_dir=sim_dir)
