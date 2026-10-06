"""
Tests for Voice Lab business logic: scoring, aggregation math, threshold pass/fail,
approval rules, and topic assignment.
Follows SPEC.md Section 10 and Milestone M3b Step 3.
"""

from pathlib import Path
import json
import pytest

from review_ui.voice_lab_logic import (
    ACCEPTANCE_RULES,
    load_scores,
    save_scores,
    record_evaluation,
    aggregate_scores,
    approve_profile,
    assign_profile_to_topic,
)


@pytest.fixture
def tmp_scores_file(tmp_path):
    return tmp_path / "scores.json"


@pytest.fixture
def sample_profile_file(tmp_path):
    prof_path = tmp_path / "test_profile.json"
    data = {
        "id": "test_profile",
        "engine": "kokoro",
        "voice": "af_heart",
        "speed": 0.95,
        "tone": "calm_curious",
        "pause_ms": {"sentence": 300, "aha": 600},
        "lexicon": "brand/lexicon.json",
        "postfx": "warm_narration",
        "license_note": "Apache-2.0",
        "status": "candidate",
    }
    with open(prof_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    return prof_path


def test_record_and_load_evaluation(tmp_scores_file):
    """Verify recording evaluation entries to scores.json."""
    entry = record_evaluation(
        listener="Alice",
        profile_id="calm_curious_heart",
        line_id="hook",
        score=5,
        keep_watching=True,
        blind=True,
        scores_path=tmp_scores_file,
    )
    assert entry["listener"] == "Alice"
    assert entry["score"] == 5

    loaded = load_scores(tmp_scores_file)
    assert len(loaded) == 1
    assert loaded[0]["profile_id"] == "calm_curious_heart"

    with pytest.raises(ValueError, match="between 1 and 5"):
        record_evaluation("Bob", "calm_curious_heart", "hook", score=6, keep_watching=True, scores_path=tmp_scores_file)


def test_aggregate_scores_pass():
    """5 listeners, 4.2 mean naturalness, 80% keep watching -> PASS."""
    scores = [
        {"listener": "L1", "profile_id": "p1", "score": 4, "keep_watching": True},
        {"listener": "L2", "profile_id": "p1", "score": 5, "keep_watching": True},
        {"listener": "L3", "profile_id": "p1", "score": 4, "keep_watching": True},
        {"listener": "L4", "profile_id": "p1", "score": 4, "keep_watching": True},
        {"listener": "L5", "profile_id": "p1", "score": 4, "keep_watching": False}, # 4/5 = 80%
    ]
    # Mean = (4+5+4+4+4)/5 = 4.20
    results = aggregate_scores(scores)
    stats = results["p1"]

    assert stats["listener_count"] == 5
    assert stats["mean_naturalness"] == 4.20
    assert stats["keep_watching_pct"] == 80.0
    assert stats["passed"] is True
    assert len(stats["failure_reasons"]) == 0


def test_aggregate_scores_fail_insufficient_listeners():
    """4 listeners (< 5) fails even with 5.0 score and 100% keep-watching."""
    scores = [
        {"listener": "L1", "profile_id": "p1", "score": 5, "keep_watching": True},
        {"listener": "L2", "profile_id": "p1", "score": 5, "keep_watching": True},
        {"listener": "L3", "profile_id": "p1", "score": 5, "keep_watching": True},
        {"listener": "L4", "profile_id": "p1", "score": 5, "keep_watching": True},
    ]
    results = aggregate_scores(scores)
    stats = results["p1"]

    assert stats["listener_count"] == 4
    assert stats["passed"] is False
    assert any("Listener count 4 is below required 5" in r for r in stats["failure_reasons"])


def test_aggregate_scores_fail_low_naturalness():
    """5 listeners, 3.8 mean naturalness (< 4.0), 100% keep watching fails."""
    scores = [
        {"listener": "L1", "profile_id": "p1", "score": 4, "keep_watching": True},
        {"listener": "L2", "profile_id": "p1", "score": 4, "keep_watching": True},
        {"listener": "L3", "profile_id": "p1", "score": 4, "keep_watching": True},
        {"listener": "L4", "profile_id": "p1", "score": 4, "keep_watching": True},
        {"listener": "L5", "profile_id": "p1", "score": 3, "keep_watching": True},
    ]
    # Mean = 19/5 = 3.80
    results = aggregate_scores(scores)
    stats = results["p1"]

    assert stats["mean_naturalness"] == 3.80
    assert stats["passed"] is False
    assert any("Mean naturalness 3.80 is below required 4.00" in r for r in stats["failure_reasons"])


def test_aggregate_scores_fail_low_keep_watching():
    """5 listeners, 4.4 naturalness, 60% keep watching (< 70%) fails."""
    scores = [
        {"listener": "L1", "profile_id": "p1", "score": 5, "keep_watching": True},
        {"listener": "L2", "profile_id": "p1", "score": 4, "keep_watching": True},
        {"listener": "L3", "profile_id": "p1", "score": 5, "keep_watching": True},
        {"listener": "L4", "profile_id": "p1", "score": 4, "keep_watching": False},
        {"listener": "L5", "profile_id": "p1", "score": 4, "keep_watching": False},
    ]
    # Mean = 22/5 = 4.40, KW = 3/5 = 60%
    results = aggregate_scores(scores)
    stats = results["p1"]

    assert stats["keep_watching_pct"] == 60.0
    assert stats["passed"] is False
    assert any("Keep-watching rate 60.0% is below required 70.0%" in r for r in stats["failure_reasons"])


def test_approve_profile_refuses_failing_profile(sample_profile_file, tmp_scores_file):
    """approve_profile refuses a failing profile without override."""
    # Empty scores -> fails
    with pytest.raises(ValueError, match="Cannot approve profile"):
        approve_profile(sample_profile_file, scores_path=tmp_scores_file, allow_override=False)


def test_approve_profile_succeeds_on_passing(sample_profile_file, tmp_scores_file):
    """approve_profile succeeds when profile passes acceptance criteria."""
    scores = [
        {"listener": f"L{i}", "profile_id": "test_profile", "score": 5, "keep_watching": True}
        for i in range(5)
    ]
    save_scores(scores, tmp_scores_file)

    approved = approve_profile(sample_profile_file, scores_path=tmp_scores_file)
    assert approved["status"] == "approved"
    assert "override" not in approved

    with open(sample_profile_file, "r", encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["status"] == "approved"


def test_approve_profile_with_override(sample_profile_file, tmp_scores_file):
    """approve_profile allows force approval with documented override."""
    # Fails criteria, but override provided
    approved = approve_profile(
        sample_profile_file,
        scores_path=tmp_scores_file,
        allow_override=True,
        override_reason="Director creative decision for pilot episode",
    )
    assert approved["status"] == "approved"
    assert approved["override"] is True
    assert approved["override_reason"] == "Director creative decision for pilot episode"

    # Reject override if reason is empty
    with pytest.raises(ValueError, match="requires a non-empty override_reason"):
        approve_profile(
            sample_profile_file,
            scores_path=tmp_scores_file,
            allow_override=True,
            override_reason="",
        )


def test_assign_profile_to_topic(sample_profile_file, tmp_path):
    """assign_profile_to_topic writes voice_profile into bible.json, refusing unapproved profiles."""
    topic_dir = tmp_path / "linear_algebra"

    # Unapproved profile (status="candidate") must be refused
    with pytest.raises(ValueError, match="Only 'approved' profiles can be assigned"):
        assign_profile_to_topic(sample_profile_file, topic_dir)

    # Approve profile
    with open(sample_profile_file, "r", encoding="utf-8") as f:
        d = json.load(f)
    d["status"] = "approved"
    with open(sample_profile_file, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=2)

    # Now assignment should succeed and create minimal bible.json
    bible_path, created_minimal = assign_profile_to_topic(sample_profile_file, topic_dir)
    assert created_minimal is True
    assert bible_path.exists()

    with open(bible_path, "r", encoding="utf-8") as f:
        bible = json.load(f)
    assert bible["voice_profile"] == "test_profile"
    assert bible["topic"] == "linear_algebra"

    # Second assignment updates existing bible.json without overwriting entire file
    bible_path, created_minimal = assign_profile_to_topic(sample_profile_file, topic_dir)
    assert created_minimal is False
