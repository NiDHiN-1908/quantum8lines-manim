"""
Comprehensive unit and seeded-error tests for Quality Gates G1, G2, G4 (SPEC.md Section 9 & Milestone M4a).
Validates that clean fixtures pass all gates, and exactly 10 seeded failure modes trip their intended check IDs.
"""

from copy import deepcopy
import json
from pathlib import Path
import pytest

from pipeline.gates.g1_script import run_g1_script
from pipeline.gates.g2_math import run_g2_math
from pipeline.gates.g4_code import run_g4_code
from pipeline.gates.models import GateConfig
from pipeline.status import (
    load_status,
    save_status,
    update_stage_status,
    save_qa_report,
    load_qa_report,
)


CLEAN_FIXTURE_DIR = Path("tests/fixtures/seeded/clean_chapter")


@pytest.fixture
def clean_chapter_data():
    """Load the clean fixture chapter JSONs and code."""
    with open(CLEAN_FIXTURE_DIR / "script.json", "r", encoding="utf-8") as f:
        script = json.load(f)
    with open(CLEAN_FIXTURE_DIR / "facts.json", "r", encoding="utf-8") as f:
        facts = json.load(f)
    with open(CLEAN_FIXTURE_DIR / "scene.py", "r", encoding="utf-8") as f:
        scene = f.read()
    return {"script": script, "facts": facts, "scene": scene}


# ============================================================================
# 1. Clean Fixture Verification
# ============================================================================

def test_clean_fixture_passes_all_gates(clean_chapter_data):
    """Verify that the clean chapter passes G1, G2, and G4 without any check failures."""
    g1 = run_g1_script(
        script_data=clean_chapter_data["script"],
        facts_data=clean_chapter_data["facts"],
    )
    assert g1.passed is True
    assert all(c.passed for c in g1.checks)

    g2 = run_g2_math(facts_data=clean_chapter_data["facts"])
    assert g2.passed is True
    assert all(c.passed for c in g2.checks)

    g4 = run_g4_code(
        chapter_dir=CLEAN_FIXTURE_DIR,
        scene_source=clean_chapter_data["scene"],
    )
    assert g4.passed is True
    assert all(c.passed for c in g4.checks)


def test_status_tracking_and_qa_report(tmp_path: Path, clean_chapter_data):
    """Verify status.json updating and qa/report.json generation."""
    ch_dir = tmp_path / "test_ch"
    ch_dir.mkdir()

    # Initial status
    status = load_status(ch_dir)
    assert status["stages"]["script"]["status"] == "pending"

    # Update status
    updated = update_stage_status(
        ch_dir,
        stage="script",
        status="passed",
        input_hash="abc123hash",
        artifacts=["script.json"],
    )
    assert updated["stages"]["script"]["status"] == "passed"
    assert updated["stages"]["script"]["input_hash"] == "abc123hash"
    assert updated["stages"]["script"]["completed_at"] is not None

    # Save and reload QA report
    g1 = run_g1_script(
        script_data=clean_chapter_data["script"],
        facts_data=clean_chapter_data["facts"],
    )
    g2 = run_g2_math(facts_data=clean_chapter_data["facts"])
    report_path = save_qa_report(ch_dir, [g1, g2])
    assert report_path.exists()

    report = load_qa_report(ch_dir)
    assert report is not None
    assert report["passed"] is True
    assert "G1" in report["gates"]
    assert "G2" in report["gates"]


# ============================================================================
# 2. Ten Seeded Error Test Cases
# ============================================================================

def test_case_01_eigenpair_with_wrong_eigenvalue(clean_chapter_data):
    """Case 1: Claim in facts.json has failed/unverifiable status -> trips G2_all_verified."""
    facts = deepcopy(clean_chapter_data["facts"])
    facts["claims"][0]["status"] = "failed"
    facts["claims"][0]["reason"] = "A*v = [2, 0] != 5*[1, 0]"

    res = run_g2_math(facts_data=facts)
    assert res.passed is False
    check = res.get_check("G2_all_verified")
    assert check is not None
    assert check.passed is False
    assert "not verified" in check.message.lower() or "failed" in check.message.lower()


def test_case_02_scene_with_hardcoded_number(clean_chapter_data):
    """Case 2: Scene with hard-coded number (e.g. 2.7) -> trips G4a_numeric_literals."""
    scene_code = clean_chapter_data["scene"] + "\nEXTRA_SCALE = 2.7\n"

    res = run_g4_code(scene_source=scene_code)
    assert res.passed is False
    check = res.get_check("G4a_numeric_literals")
    assert check is not None
    assert check.passed is False
    assert "2.7" in check.message


def test_case_03_scene_using_blue_and_hex_color(clean_chapter_data):
    """Case 3: Scene using BLUE / raw hex -> trips G4b_no_raw_colors."""
    # Test 3a: raw Manim color BLUE
    scene_code_blue = clean_chapter_data["scene"] + "\nMY_COLOR = BLUE\n"
    res_blue = run_g4_code(scene_source=scene_code_blue)
    assert res_blue.passed is False
    check_blue = res_blue.get_check("G4b_no_raw_colors")
    assert check_blue is not None
    assert check_blue.passed is False
    assert "BLUE" in check_blue.message

    # Test 3b: raw hex string
    scene_code_hex = clean_chapter_data["scene"] + "\nHEX_VAL = '#58c4dd'\n"
    res_hex = run_g4_code(scene_source=scene_code_hex)
    assert res_hex.passed is False
    check_hex = res_hex.get_check("G4b_no_raw_colors")
    assert check_hex is not None
    assert check_hex.passed is False
    assert "#58c4dd" in check_hex.message


def test_case_04_scene_importing_os(clean_chapter_data):
    """Case 4: Scene importing os -> trips G4c_imports."""
    scene_code = "import os\n" + clean_chapter_data["scene"]

    res = run_g4_code(scene_source=scene_code)
    assert res.passed is False
    check = res.get_check("G4c_imports")
    assert check is not None
    assert check.passed is False
    assert "os" in check.message


def test_case_05_scene_calling_eval(clean_chapter_data):
    """Case 5: Scene calling eval -> trips G4d_forbidden_names."""
    scene_code = clean_chapter_data["scene"] + "\neval('1 + 1')\n"

    res = run_g4_code(scene_source=scene_code)
    assert res.passed is False
    check = res.get_check("G4d_forbidden_names")
    assert check is not None
    assert check.passed is False
    assert "eval" in check.message


def test_case_06_scene_missing_basescene_subclass(clean_chapter_data):
    """Case 6: Scene missing BaseScene subclass -> trips G4e_basescene_subclass."""
    scene_code = """
from manim import Dot
class NotABaseScene:
    def construct(self):
        pass
"""
    res = run_g4_code(scene_source=scene_code)
    assert res.passed is False
    check = res.get_check("G4e_basescene_subclass")
    assert check is not None
    assert check.passed is False


def test_case_07_scene_raising_during_construct(clean_chapter_data):
    """Case 7: Scene raising during construct() -> trips G4f_dry_run_construct."""
    scene_code = """
from manim import ORIGIN
from core.scene_base import BaseScene

class BrokenScene(BaseScene):
    def construct(self):
        raise RuntimeError("Simulated scene construct crash")
"""
    res = run_g4_code(scene_source=scene_code)
    assert res.passed is False
    check = res.get_check("G4f_dry_run_construct")
    assert check is not None
    assert check.passed is False
    assert "Simulated scene construct crash" in check.message


def test_case_08_script_word_count_out_of_range(clean_chapter_data):
    """Case 8: Script too short (< 100 words) -> trips G1_word_count."""
    script = deepcopy(clean_chapter_data["script"])
    # Truncate to just one very short line
    script["lines"] = [
        {
            "id": "l01",
            "text": "This script is way too brief.",
            "beat": "hook",
            "cut": "both",
        }
    ]

    res = run_g1_script(script_data=script, config=GateConfig(min_words=100, max_words=180))
    assert res.passed is False
    check = res.get_check("G1_word_count")
    assert check is not None
    assert check.passed is False
    assert "outside allowed range" in check.message


def test_case_09_script_referencing_missing_claim_id(clean_chapter_data):
    """Case 9: Script referencing missing claim ID -> trips G1_claim_ids_exist."""
    script = deepcopy(clean_chapter_data["script"])
    script["lines"][0]["claims"] = ["c999_nonexistent"]

    res = run_g1_script(
        script_data=script,
        facts_data=clean_chapter_data["facts"],
    )
    assert res.passed is False
    check = res.get_check("G1_claim_ids_exist")
    assert check is not None
    assert check.passed is False
    assert "c999_nonexistent" in check.message


def test_case_10_script_with_out_of_order_beats(clean_chapter_data):
    """Case 10: Script with out-of-order beats (build before setup) -> trips G1_beat_order."""
    script = deepcopy(clean_chapter_data["script"])
    # Swap beats of line 1 (was setup) and line 2 (was build) -> hook, build, setup
    script["lines"][1]["beat"] = "build"
    script["lines"][2]["beat"] = "setup"

    res = run_g1_script(
        script_data=script,
        facts_data=clean_chapter_data["facts"],
    )
    assert res.passed is False
    check = res.get_check("G1_beat_order")
    assert check is not None
    assert check.passed is False
    assert "canonical order" in check.message.lower()
