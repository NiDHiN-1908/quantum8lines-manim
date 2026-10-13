"""
Tests for agent stages (plan_topic, write_script, verify_math) and G1 regeneration loops.
Follows SPEC.md Section 8 and Milestone M5a.
"""

from pathlib import Path
import json
import pytest

from agents.schemas import Bible, Script
from agents.stages import plan_topic, write_script, verify_math
from agents.llm.mock import MockProvider
from pipeline.status import load_status


CANNED_BIBLE = {
    "topic": "Eigenvectors",
    "audience": "undergraduate linear algebra students",
    "arc": "from invariant directions to scaling factors and spectral decomposition",
    "notation": {"matrix": "A", "vector": "v", "eigenvalue": "λ"},
    "chapters": [
        {
            "id": "ch01",
            "title": "Directions That Refuse to Turn",
            "one_idea": "Special vectors only scale along their original line without rotating.",
            "question_it_raises": "How much do these invariant directions stretch?",
            "new_terms": ["eigenvalue", "transformation", "vector", "scaling", "eigenspace"],
        },
        {
            "id": "ch02",
            "title": "The Scaling Factor",
            "one_idea": "The eigenvalue λ measures the exact scalar expansion along the eigenvector.",
            "question_it_raises": "How do we find these values systematically?",
            "new_terms": ["characteristic polynomial", "trace"],
        },
        {
            "id": "ch03",
            "title": "The Characteristic Equation",
            "one_idea": "Eigenvalues satisfy the determinant equation det(A - λI) = 0.",
            "question_it_raises": "What happens once the eigenvalues are known?",
            "new_terms": ["determinant", "characteristic equation"],
        },
        {
            "id": "ch04",
            "title": "The Full Eigenbasis",
            "one_idea": "Transforming into an eigenbasis uncouples complex dynamical systems.",
            "question_it_raises": "Where does this geometric duality appear in modern physics?",
            "new_terms": ["eigenbasis", "diagonalization"],
        }
    ],
    "prereqs": ["matrix multiplication", "determinants"],
    "voice_profile": "",
    "cast": [],
    "sources": ["Gilbert Strang, Linear Algebra"]
}

# 102-word clean script with canonical beats and {{c1.value}} placeholder
CANNED_VALID_SCRIPT = {
    "chapter": "ch01",
    "lines": [
        {
            "id": "l01",
            "text": "Can a linear transformation warp the entire coordinate plane while leaving certain geometric directions completely invariant across the space?",
            "beat": "hook",
            "cut": "both",
            "claims": ["c1"],
        },
        {
            "id": "l02",
            "text": "When we apply a general matrix mapping to our coordinate grid, typical vectors rotate and tilt away from their initial orientations.",
            "beat": "setup",
            "cut": "both",
        },
        {
            "id": "l03",
            "text": "Yet along rare directional axes passing through the origin, vectors experience pure uniform scaling without departing from their original span in any way.",
            "beat": "build",
            "cut": "both",
            "no_math": True,
        },
        {
            "id": "l04",
            "text": "The resulting expansion factor turns out to equal {{c1.value}}, while the preserved directional axis forms an invariant subspace.",
            "beat": "aha",
            "cut": "both",
            "claims": ["c1"],
        },
        {
            "id": "l05",
            "text": "Identifying these invariant pathways reveals the fundamental geometric structure powering quantum states, structural vibrations, and dimensional reduction across modern mathematical physics.",
            "beat": "close",
            "cut": "both",
        }
    ],
    "claim_specs": [
        {
            "id": "c1",
            "type": "eigenpair",
            "matrix": [[2, 0], [0, 3]],
            "vector": [1, 0]
        }
    ]
}


def test_plan_topic_success(tmp_path: Path):
    """Verify plan_topic runs Curriculum planner and produces valid bible.json and status."""
    topic_dir = tmp_path / "eigenvectors"
    mock = MockProvider(
        responses={"curriculum_planner": json.dumps(CANNED_BIBLE)}
    )

    bible = plan_topic(topic_dir=topic_dir, topic_name="Eigenvectors", provider=mock)

    assert isinstance(bible, Bible)
    assert bible.topic == "Eigenvectors"
    assert len(bible.chapters) == 4

    bible_file = topic_dir / "bible.json"
    assert bible_file.is_file()

    status = load_status(topic_dir)
    assert status["stages"]["plan"]["status"] == "passed"
    assert "bible.json" in status["stages"]["plan"]["artifacts"]


def test_write_script_and_verify_math_success(tmp_path: Path):
    """Verify write_script produces a script passing G1 and verify_math verifies claims into facts.json passing G2."""
    topic_dir = tmp_path / "eigenvectors"
    topic_dir.mkdir(parents=True, exist_ok=True)
    (topic_dir / "bible.json").write_text(json.dumps(CANNED_BIBLE, indent=2), encoding="utf-8")

    chapter_dir = topic_dir / "chapters" / "ch01"
    chapter_dir.mkdir(parents=True, exist_ok=True)

    mock = MockProvider(
        responses={"scriptwriter": json.dumps(CANNED_VALID_SCRIPT)}
    )

    # 1. Write script stage
    script_data = write_script(chapter_dir=chapter_dir, provider=mock)
    assert script_data["chapter"] == "ch01"

    status = load_status(chapter_dir)
    assert status["stages"]["script"]["status"] == "passed"
    assert (chapter_dir / "script.json").is_file()
    assert (chapter_dir / "qa" / "report.json").is_file()

    # 2. Verify math stage
    facts = verify_math(chapter_dir=chapter_dir)
    assert facts.get_claim("c1").status == "verified"
    assert facts.spoken("c1.value") == "two"

    status_after_verify = load_status(chapter_dir)
    assert status_after_verify["stages"]["verify"]["status"] == "passed"
    assert (chapter_dir / "facts.json").is_file()


def test_seeded_bad_script_triggers_regeneration_and_passes(tmp_path: Path):
    """
    Verify that a script failing G1 (raw digit '2.7' in narration)
    triggers regeneration and passes on the second mock response.
    """
    topic_dir = tmp_path / "eigenvectors"
    topic_dir.mkdir(parents=True, exist_ok=True)
    (topic_dir / "bible.json").write_text(json.dumps(CANNED_BIBLE, indent=2), encoding="utf-8")

    chapter_dir = topic_dir / "chapters" / "ch01"
    chapter_dir.mkdir(parents=True, exist_ok=True)

    # Script 1: Trips G1h (contains raw digit 2.7)
    bad_script = dict(CANNED_VALID_SCRIPT)
    bad_script["lines"] = list(CANNED_VALID_SCRIPT["lines"])
    bad_line_4 = dict(bad_script["lines"][3])
    bad_line_4["text"] = "The resulting expansion factor turns out to equal 2.7, while the preserved directional axis forms an invariant subspace."
    bad_script["lines"][3] = bad_line_4

    # Script 2: Clean valid script passing G1
    good_script = CANNED_VALID_SCRIPT

    mock = MockProvider(
        responses={
            "scriptwriter": [
                json.dumps(bad_script),
                json.dumps(good_script),
            ]
        }
    )

    script_data = write_script(chapter_dir=chapter_dir, provider=mock, max_regen_attempts=3)

    # Assert regeneration occurred: exactly 2 calls were made to the scriptwriter
    script_calls = [c for c in mock.call_history if c.get("agent_name") == "scriptwriter"]
    assert len(script_calls) == 2

    # Second call included gate feedback
    assert "Gate G1 failed" in script_calls[1]["user"]

    # Final script passed G1
    status = load_status(chapter_dir)
    assert status["stages"]["script"]["status"] == "passed"
