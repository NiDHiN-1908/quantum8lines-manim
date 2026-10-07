"""
Comprehensive unit and seeded-error tests for Quality Gates G5, G6, G7, G4g,
and the Gate Runner CLI (SPEC.md Section 9 & Milestone M4b).
Validates that clean fixtures pass all gates end-to-end on both layouts,
and exactly 14 seeded failure modes trip their intended check IDs with informative messages.
"""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import pytest
import soundfile as sf
import numpy as np

from core.layout import LAYOUT_169, LAYOUT_916
from pipeline.gates.models import GateConfig
from pipeline.gates.g4_code import run_g4_code
from pipeline.gates.g5_render import run_g5_render
from pipeline.gates.g6_visual import run_g6_visual
from pipeline.gates.g7_audio import run_g7_audio
from pipeline.render import RenderResult
from pipeline.run_gates import run_pipeline_gates
from pipeline.status import load_status, load_qa_report


CLEAN_CHAPTER_DIR = Path("tests/fixtures/seeded_b/clean_chapter")


# ============================================================================
# 1. Clean Fixture End-to-End Verification (Both Layouts)
# ============================================================================

def test_clean_fixture_passes_all_gates_both_layouts(tmp_path: Path):
    """
    Assert that the clean chapter fixture passes G1 through G7 end-to-end
    on both 16:9 and 9:16 layouts via the gate runner.
    Operates on an isolated copy in tmp_path to preserve fixture cleanliness.
    """
    clean_copy = tmp_path / "clean_chapter"
    shutil.copytree(CLEAN_CHAPTER_DIR, clean_copy)

    passed, gate_results = run_pipeline_gates(
        chapter_dir=clean_copy,
        layout="both",
    )
    assert passed is True, f"Gate runner failed on clean fixture: {[gr.gate_id for gr in gate_results if not gr.passed]}"

    gate_ids = [gr.gate_id for gr in gate_results]
    assert "G1" in gate_ids
    assert "G2" in gate_ids
    assert "G4" in gate_ids
    assert "G5_169" in gate_ids
    assert "G6_169" in gate_ids
    assert "G5_916" in gate_ids
    assert "G6_916" in gate_ids
    assert "G7" in gate_ids

    for gr in gate_results:
        assert gr.passed is True
        for c in gr.checks:
            if c.severity == "error":
                assert c.passed is True, f"Check {c.id} failed: {c.message}"

    # Verify status.json records G3 and G8 as needs_human
    status_data = load_status(clean_copy)
    assert status_data["gates"]["G3"] == "needs_human"
    assert status_data["gates"]["G8"] == "needs_human"
    assert status_data["stages"]["review"]["status"] == "needs_human"

    # Verify qa/report.json exists and reports overall passed
    report = load_qa_report(clean_copy)
    assert report is not None
    assert report["passed"] is True


# ============================================================================
# 2. Seeded Failure 1: Empty Scene -> G5b
# ============================================================================

def test_seeded_01_empty_scene_trips_g5b(tmp_path):
    """
    SEEDED ERROR 1: Empty scene with fewer than 0.2% non-background pixels -> G5b_no_empty_frames.
    """
    # Create a 2-second black video matching background #0e0e11
    video_path = tmp_path / "empty_video.mp4"
    import subprocess
    cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-f", "lavfi", "-i", "color=c=0x0e0e11:s=480x270:d=2:r=15",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(video_path)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    render_res = RenderResult(
        success=True,
        video_path=str(video_path),
        duration=2.0,
        chapter_dir=str(tmp_path),
        layout="169",
        quality="test",
    )

    g5 = run_g5_render(chapter_dir=tmp_path, render_result=render_res, layout="16:9")
    assert g5.passed is False
    failed_check = next((c for c in g5.checks if not c.passed), None)
    assert failed_check is not None
    assert failed_check.id == "G5b_no_empty_frames"
    assert "blank frames" in failed_check.message.lower()


# ============================================================================
# 3. Seeded Failure 2: Video Much Shorter Than Audio -> G5c
# ============================================================================

def test_seeded_02_video_shorter_than_audio_trips_g5c(tmp_path):
    """
    SEEDED ERROR 2: Video duration (1.0s) much shorter than audio duration (3.0s) -> G5c_duration_matches_audio.
    """
    video_path = tmp_path / "short_video.mp4"
    import subprocess
    cmd = [
        "ffmpeg", "-y", "-nostdin",
        "-f", "lavfi", "-i", "color=c=blue:s=480x270:d=1:r=15",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(video_path)
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    # Write timings with 3.0s total duration
    timings = {"total_duration": 3.0, "lines": [{"id": "l01", "start": 0.0, "end": 3.0}]}
    (tmp_path / "audio").mkdir(parents=True, exist_ok=True)
    with open(tmp_path / "audio" / "timings.json", "w", encoding="utf-8") as f:
        json.dump(timings, f)

    render_res = RenderResult(
        success=True,
        video_path=str(video_path),
        duration=1.0,
        chapter_dir=str(tmp_path),
        layout="169",
        quality="test",
    )

    g5 = run_g5_render(chapter_dir=tmp_path, render_result=render_res, layout="16:9")
    assert g5.passed is False
    failed_check = next((c for c in g5.checks if not c.passed), None)
    assert failed_check is not None
    assert failed_check.id == "G5c_duration_matches_audio"
    assert "1.00s" in failed_check.message and "3.00s" in failed_check.message


# ============================================================================
# 4. Seeded Failure 3: Animation Longer Than Audio Window -> G5d
# ============================================================================

def test_seeded_03_beat_overrun_trips_g5d(tmp_path):
    """
    SEEDED ERROR 3: An animation longer than its audio window -> G5d_beat_overrun.
    """
    render_res = RenderResult(
        success=False,
        error="Beat overrun",
        overrun_error={"beat_id": "b02_build", "overrun_sec": 0.85},
        chapter_dir=str(tmp_path),
        layout="169",
        quality="test",
    )

    g5 = run_g5_render(chapter_dir=tmp_path, render_result=render_res, layout="16:9")
    assert g5.passed is False
    failed_check = next((c for c in g5.checks if not c.passed), None)
    assert failed_check is not None
    assert failed_check.id == "G5d_beat_overrun"
    assert "b02_build" in failed_check.message
    assert "0.85" in failed_check.message


# ============================================================================
# 5. Seeded Failure 4: Essential Object in 9:16 Bottom Unsafe Zone -> G6a
# ============================================================================

def test_seeded_04_object_in_bottom_unsafe_zone_trips_g6a():
    """
    SEEDED ERROR 4: An essential object in the 9:16 bottom unsafe zone -> G6a_inside_safe.
    """
    # 9:16 safe_y_min is approximately -5.0. Placing an essential object at y = -6.5 breaches bottom zone.
    snapshots = [
        {
            "beat_id": "b01",
            "label": "b01",
            "timestamp": 1.0,
            "mobjects": {
                "danger_box": {
                    "name": "danger_box",
                    "kind": "object",
                    "essential": True,
                    "bbox": [-1.0, -7.0, 1.0, -6.0],  # y_min = -7.0, breaches safe_y_min
                }
            }
        }
    ]

    g6 = run_g6_visual(snapshots=snapshots, layout=LAYOUT_916)
    assert g6.passed is False
    failed_check = next((c for c in g6.checks if not c.passed), None)
    assert failed_check is not None
    assert failed_check.id == "G6a_inside_safe"
    assert "danger_box" in failed_check.message
    assert "b01" in failed_check.message


# ============================================================================
# 6. Seeded Failure 5: Two Overlapping Essential Texts -> G6b
# ============================================================================

def test_seeded_05_overlapping_essential_texts_trips_g6b():
    """
    SEEDED ERROR 5: Two overlapping essential texts -> G6b_no_overlap.
    """
    snapshots = [
        {
            "beat_id": "b02",
            "label": "b02",
            "timestamp": 1.5,
            "mobjects": {
                "heading_a": {
                    "name": "heading_a",
                    "kind": "text",
                    "essential": True,
                    "group": None,
                    "bbox": [-1.0, 0.0, 1.0, 1.0],
                },
                "heading_b": {
                    "name": "heading_b",
                    "kind": "text",
                    "essential": True,
                    "group": None,
                    "bbox": [-0.5, 0.2, 1.5, 1.2],  # significantly overlaps heading_a
                }
            }
        }
    ]

    g6 = run_g6_visual(snapshots=snapshots, layout=LAYOUT_169)
    assert g6.passed is False
    failed_check = next((c for c in g6.checks if not c.passed), None)
    assert failed_check is not None
    assert failed_check.id == "G6b_no_overlap"
    assert "heading_a" in failed_check.message or "heading_b" in failed_check.message


# ============================================================================
# 7. Seeded Failure 6: Text Smaller Than Minimum -> G6c
# ============================================================================

def test_seeded_06_text_smaller_than_minimum_trips_g6c():
    """
    SEEDED ERROR 6: Text height below 48px minimum -> G6c_min_text_size.
    """
    snapshots = [
        {
            "beat_id": "b03",
            "label": "b03",
            "timestamp": 2.0,
            "mobjects": {
                "tiny_label": {
                    "name": "tiny_label",
                    "kind": "text",
                    "essential": True,
                    "key": False,
                    "text": "tiny text",
                    "height_px": 28.5,  # below 48 px
                    "bbox": [-0.5, -0.1, 0.5, 0.1],
                }
            }
        }
    ]

    g6 = run_g6_visual(snapshots=snapshots, layout=LAYOUT_169)
    assert g6.passed is False
    failed_check = next((c for c in g6.checks if not c.passed), None)
    assert failed_check is not None
    assert failed_check.id == "G6c_min_text_size"
    assert "tiny_label" in failed_check.message
    assert "28.5" in failed_check.message


# ============================================================================
# 8. Seeded Failure 7: Dark Text on Dark Background -> G6d
# ============================================================================

def test_seeded_07_dark_text_on_dark_background_trips_g6d():
    """
    SEEDED ERROR 7: Dark text on dark background (#0e0e11) -> G6d_contrast.
    """
    snapshots = [
        {
            "beat_id": "b01",
            "label": "b01",
            "timestamp": 0.5,
            "mobjects": {
                "murky_text": {
                    "name": "murky_text",
                    "kind": "text",
                    "essential": True,
                    "text": "Hard to read",
                    "color": "#141418",  # WCAG contrast ratio ~ 1.05 < 4.5
                    "height_px": 50.0,
                    "bbox": [-1.0, 0.0, 1.0, 0.5],
                }
            }
        }
    ]

    g6 = run_g6_visual(snapshots=snapshots, layout=LAYOUT_169)
    assert g6.passed is False
    failed_check = next((c for c in g6.checks if not c.passed), None)
    assert failed_check is not None
    assert failed_check.id == "G6d_contrast"
    assert "murky_text" in failed_check.message
    assert "#141418" in failed_check.message


# ============================================================================
# 9. Seeded Failure 8: expect.visible Name Never Registered -> G6e
# ============================================================================

def test_seeded_08_missing_expect_visible_trips_g6e():
    """
    SEEDED ERROR 8: An expect.visible name in storyboard that was never registered -> G6e_expect_visible.
    """
    storyboard = {
        "chapter": "ch01",
        "beats": [
            {
                "id": "b01",
                "expect": {
                    "visible": ["phantom_formula"]
                }
            }
        ]
    }
    snapshots = [
        {
            "beat_id": "b01",
            "label": "b01",
            "timestamp": 1.0,
            "mobjects": {
                "other_formula": {
                    "name": "other_formula",
                    "kind": "text",
                    "height_px": 50.0,
                    "bbox": [-1.0, 0.0, 1.0, 0.5],
                }
            }
        }
    ]

    g6 = run_g6_visual(snapshots=snapshots, storyboard_data=storyboard, layout=LAYOUT_169)
    assert g6.passed is False
    failed_check = next((c for c in g6.checks if c.id == "G6e_expect_visible"), None)
    assert failed_check is not None
    assert failed_check.passed is False
    assert "phantom_formula" in failed_check.message
    assert "b01" in failed_check.message


# ============================================================================
# 10. Seeded Failure 9: Character Intersects Essential / 3 Characters -> G6f
# ============================================================================

def test_seeded_09a_character_covering_essential_trips_g6f():
    """
    SEEDED ERROR 9a: A character mobject intersecting an essential object -> G6f_characters.
    """
    snapshots = [
        {
            "beat_id": "b04",
            "label": "b04",
            "timestamp": 2.0,
            "mobjects": {
                "theta_mascot": {
                    "name": "theta_mascot",
                    "kind": "character",
                    "bbox": [0.0, 0.0, 2.0, 2.0],
                },
                "key_equation": {
                    "name": "key_equation",
                    "kind": "text",
                    "height_px": 50.0,
                    "essential": True,
                    "bbox": [0.5, 0.5, 2.5, 1.5],  # overlapping with theta_mascot
                }
            }
        }
    ]

    g6 = run_g6_visual(snapshots=snapshots, layout=LAYOUT_169)
    assert g6.passed is False
    failed_check = next((c for c in g6.checks if c.id == "G6f_characters"), None)
    assert failed_check is not None
    assert failed_check.passed is False
    assert "theta_mascot" in failed_check.message
    assert "key_equation" in failed_check.message


def test_seeded_09b_three_characters_trips_g6f():
    """
    SEEDED ERROR 9b: Snapshot with 3 characters on screen (> 2 limit) -> G6f_characters.
    """
    snapshots = [
        {
            "beat_id": "b05",
            "label": "b05",
            "timestamp": 2.5,
            "mobjects": {
                "char1": {"name": "char1", "kind": "character", "bbox": [-3.0, 0.0, -2.0, 1.0]},
                "char2": {"name": "char2", "kind": "character", "bbox": [-1.0, 0.0, 0.0, 1.0]},
                "char3": {"name": "char3", "kind": "character", "bbox": [1.0, 0.0, 2.0, 1.0]},
            }
        }
    ]

    g6 = run_g6_visual(snapshots=snapshots, layout=LAYOUT_169)
    assert g6.passed is False
    failed_check = next((c for c in g6.checks if c.id == "G6f_characters"), None)
    assert failed_check is not None
    assert failed_check.passed is False
    assert "exceeds limit" in failed_check.message


# ============================================================================
# 11. Seeded Failure 10: Too-Quiet Audio Mix (-25 LUFS) -> G7a
# ============================================================================

def test_seeded_10_too_quiet_audio_trips_g7a(tmp_path):
    """
    SEEDED ERROR 10: Too-quiet audio mix (approx -25 LUFS) -> G7a_loudness.
    """
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / "narration_mix.wav"

    # Generate very quiet 440 Hz tone (-25 LUFS is ~ 0.02 amplitude)
    sr = 48000
    duration = 2.0
    t = np.linspace(0, duration, int(sr * duration), endpoint=False)
    quiet_samples = 0.02 * np.sin(2 * np.pi * 440.0 * t)
    sf.write(str(audio_path), quiet_samples, sr)

    g7 = run_g7_audio(chapter_dir=tmp_path, audio_path=audio_path)
    assert g7.passed is False
    failed_check = next((c for c in g7.checks if c.id == "G7a_loudness"), None)
    assert failed_check is not None
    assert failed_check.passed is False
    assert "loudness" in failed_check.message.lower()


# ============================================================================
# 12. Seeded Failure 11: Clipped Audio File -> G7b
# ============================================================================

def test_seeded_11_clipped_audio_trips_g7b(tmp_path):
    """
    SEEDED ERROR 11: Clipped audio file with full-scale samples -> G7b_no_clipping.
    """
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_path = audio_dir / "narration_mix.wav"

    # Base on clean normalized tone, but inject a run of 5 consecutive full-scale 1.0 samples
    clean_audio_path = CLEAN_CHAPTER_DIR / "audio" / "narration.wav"
    samples, sr = sf.read(str(clean_audio_path))
    samples[1000:1005] = 1.0
    sf.write(str(audio_path), samples, sr)

    g7 = run_g7_audio(chapter_dir=tmp_path, audio_path=audio_path)
    assert g7.passed is False
    failed_check = next((c for c in g7.checks if c.id == "G7b_no_clipping"), None)
    assert failed_check is not None
    assert failed_check.passed is False
    assert "clipping" in failed_check.message.lower()


# ============================================================================
# 13. Seeded Failure 12: Captions Do Not Match Script -> G7c
# ============================================================================

def test_seeded_12_caption_mismatch_trips_g7c(tmp_path):
    """
    SEEDED ERROR 12: Captions do not match script text -> G7c_caption_text.
    """
    clean_audio_path = CLEAN_CHAPTER_DIR / "audio" / "narration.wav"

    script_data = {
        "chapter": "ch01",
        "lines": [
            {"id": "l01", "text": "The geometric transformation rotates the coordinate plane."}
        ]
    }
    captions_path = tmp_path / "captions.ass"
    captions_content = (
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:01.00,Default,,0,0,0,,A completely different sentence about biology.\n"
    )
    captions_path.write_text(captions_content, encoding="utf-8")

    g7 = run_g7_audio(
        chapter_dir=tmp_path,
        audio_path=clean_audio_path,
        captions_path=captions_path,
        script_data=script_data,
    )
    assert g7.passed is False
    failed_check = next((c for c in g7.checks if c.id == "G7c_caption_text"), None)
    assert failed_check is not None
    assert failed_check.passed is False
    assert "mismatch" in failed_check.message.lower()


# ============================================================================
# 14. Seeded Failure 13: Captions Running Past Audio End -> G7d
# ============================================================================

def test_seeded_13_captions_running_past_audio_end_trips_g7d(tmp_path):
    """
    SEEDED ERROR 13: Captions run past audio duration -> G7d_caption_timing.
    """
    clean_audio_path = CLEAN_CHAPTER_DIR / "audio" / "narration.wav"

    script_data = {
        "chapter": "ch01",
        "lines": [{"id": "l01", "text": "Valid text here."}]
    }
    captions_path = tmp_path / "captions.ass"
    # Clean audio is 2.50s; caption ends at 5.00s
    captions_content = (
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,Valid text here.\n"
    )
    captions_path.write_text(captions_content, encoding="utf-8")

    g7 = run_g7_audio(
        chapter_dir=tmp_path,
        audio_path=clean_audio_path,
        captions_path=captions_path,
        script_data=script_data,
    )
    assert g7.passed is False
    failed_check = next((c for c in g7.checks if c.id == "G7d_caption_timing"), None)
    assert failed_check is not None
    assert failed_check.passed is False
    assert "exceeds audio duration" in failed_check.message.lower()


# ============================================================================
# 15. Seeded Failure 14: MathTex("x = 2.7") Digit Literal & Escape Hatch -> G4g
# ============================================================================

def test_seeded_14a_digit_literal_in_mathtex_trips_g4g(tmp_path):
    """
    SEEDED ERROR 14a: MathTex('x = 2.7') contains digit literal without escape hatch -> G4g fails with error.
    """
    scene_code = """
from manim import MathTex, Scene
from core.scene_base import BaseScene

class BadDigitsScene(BaseScene):
    def construct(self):
        eq = MathTex("x = 2.7")
        self.add(eq)
"""
    g4 = run_g4_code(chapter_dir=tmp_path, scene_source=scene_code)
    assert g4.passed is False
    failed_check = next((c for c in g4.checks if not c.passed), None)
    assert failed_check is not None
    assert failed_check.id == "G4g_digits_in_text"
    assert failed_check.severity == "error"
    assert "2.7" in failed_check.message
    assert "Line 7" in failed_check.message


def test_seeded_14b_digit_literal_with_escape_hatch_passes_warning(tmp_path):
    """
    SEEDED ERROR 14b: MathTex('x = 2.7') with escape comment passes G4g with warning severity.
    """
    scene_code = """
from manim import MathTex, Scene
from core.scene_base import BaseScene

class AllowedDigitsScene(BaseScene):
    def construct(self):
        eq = MathTex("x = 2.7")  # q8l: allow-digits benchmark reference point
        self.add(eq)
"""
    g4 = run_g4_code(chapter_dir=tmp_path, scene_source=scene_code)
    # The check should pass, but record a warning
    g4g_check = next((c for c in g4.checks if c.id == "G4g_digits_in_text"), None)
    assert g4g_check is not None
    assert g4g_check.passed is True
    assert g4g_check.severity == "warning"
    assert "benchmark reference point" in g4g_check.message


# ============================================================================
# 16. G7c Strictness Tests (100-word Caption)
# ============================================================================

def test_g7c_strictness_100_words(tmp_path):
    """
    Verify G7c caption text matching is strictly word-for-word on a ~100-word text:
    - exact match passes
    - changing ONE word fails
    - dropping ONE word fails
    - adding ONE word fails
    """
    clean_audio_path = CLEAN_CHAPTER_DIR / "audio" / "narration.wav"

    words_100 = [
        "quantum", "mechanics", "reveals", "that", "physical", "systems", "evolve",
        "according", "to", "linear", "transformations", "in", "complex", "vector",
        "spaces", "where", "every", "observable", "corresponds", "directly", "to",
        "a", "hermitian", "operator", "whose", "eigenvalues", "represent", "all",
        "possible", "measurement", "outcomes", "that", "an", "experimenter", "can",
        "ever", "obtain", "under", "ideal", "laboratory", "conditions", "furthermore",
        "the", "state", "vector", "remains", "unbroken", "until", "an", "interaction",
        "occurs", "collapsing", "the", "superposition", "into", "a", "definite",
        "basis", "state", "with", "probabilities", "governed", "strictly", "by",
        "the", "born", "rule", "this", "fundamental", "geometric", "duality",
        "connects", "abstract", "algebraic", "structures", "with", "tangible",
        "empirical", "observations", "illuminating", "the", "underlying", "architecture",
        "of", "our", "universe", "in", "astonishing", "clarity", "and", "depth",
        "leaving", "no", "room", "for", "ambiguity", "or", "error", "here", "today"
    ]
    assert len(words_100) == 100
    full_text = " ".join(words_100)

    script_data = {
        "chapter": "ch_strict",
        "lines": [{"id": "l01", "text": full_text}]
    }

    def make_ass(text):
        return (
            "[Script Info]\nScriptType: v4.00+\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
            f"Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,{text}\n"
        )

    # 1. Exact match passes
    p_exact = tmp_path / "exact.ass"
    p_exact.write_text(make_ass(full_text), encoding="utf-8")
    g7_exact = run_g7_audio(chapter_dir=tmp_path, audio_path=clean_audio_path, captions_path=p_exact, script_data=script_data)
    c_exact = next(c for c in g7_exact.checks if c.id == "G7c_caption_text")
    assert c_exact.passed is True

    # 2. Changing ONE word fails
    words_changed = list(words_100)
    words_changed[42] = "modifiedword"
    p_changed = tmp_path / "changed.ass"
    p_changed.write_text(make_ass(" ".join(words_changed)), encoding="utf-8")
    g7_changed = run_g7_audio(chapter_dir=tmp_path, audio_path=clean_audio_path, captions_path=p_changed, script_data=script_data)
    c_changed = next(c for c in g7_changed.checks if c.id == "G7c_caption_text")
    assert c_changed.passed is False
    assert "mismatch" in c_changed.message.lower()

    # 3. Dropping ONE word fails
    words_dropped = list(words_100)
    words_dropped.pop(50)
    p_dropped = tmp_path / "dropped.ass"
    p_dropped.write_text(make_ass(" ".join(words_dropped)), encoding="utf-8")
    g7_dropped = run_g7_audio(chapter_dir=tmp_path, audio_path=clean_audio_path, captions_path=p_dropped, script_data=script_data)
    c_dropped = next(c for c in g7_dropped.checks if c.id == "G7c_caption_text")
    assert c_dropped.passed is False
    assert "mismatch" in c_dropped.message.lower()

    # 4. Adding ONE word fails
    words_added = list(words_100)
    words_added.insert(25, "extraword")
    p_added = tmp_path / "added.ass"
    p_added.write_text(make_ass(" ".join(words_added)), encoding="utf-8")
    g7_added = run_g7_audio(chapter_dir=tmp_path, audio_path=clean_audio_path, captions_path=p_added, script_data=script_data)
    c_added = next(c for c in g7_added.checks if c.id == "G7c_caption_text")
    assert c_added.passed is False
    assert "mismatch" in c_added.message.lower()


# ============================================================================
# 17. G6c Minimum Text Size Boundary Tests
# ============================================================================

def test_g6c_min_text_size_boundary(tmp_path):
    """
    Verify G6c text size boundaries:
    - Text label at exactly 48.0 px passes G6c
    - Text label at 90% of 48.0 px (43.2 px) fails G6c
    - Key text at exactly 72.0 px passes G6c
    - Key text at 90% of 72.0 px (64.8 px) fails G6c
    """
    storyboard = {"chapter": "ch01", "beats": [{"id": "b01"}]}

    # 1. Label at exactly 48.0 px passes
    snap_label_48 = [{
        "beat_id": "b01",
        "label": "b01",
        "mobjects": {
            "lbl": {"name": "lbl", "kind": "text", "essential": True, "key": False, "bbox": [0, 0, 1, 0.355], "height_px": 48.0, "color": "#f4f4f6"}
        }
    }]
    g6_pass = run_g6_visual(chapter_dir=tmp_path, layout="16:9", snapshots=snap_label_48, storyboard_data=storyboard)
    c_pass = next(c for c in g6_pass.checks if c.id == "G6c_min_text_size")
    assert c_pass.passed is True

    # 2. Label at 90% of 48 px (43.2 px) fails
    snap_label_43 = [{
        "beat_id": "b01",
        "label": "b01",
        "mobjects": {
            "lbl": {"name": "lbl", "kind": "text", "essential": True, "key": False, "bbox": [0, 0, 1, 0.32], "height_px": 48.0 * 0.9, "color": "#f4f4f6"}
        }
    }]
    g6_fail = run_g6_visual(chapter_dir=tmp_path, layout="16:9", snapshots=snap_label_43, storyboard_data=storyboard)
    c_fail = next(c for c in g6_fail.checks if c.id == "G6c_min_text_size")
    assert c_fail.passed is False
    assert "below required" in c_fail.message.lower()

    # 3. Key text at exactly 72.0 px passes
    snap_key_72 = [{
        "beat_id": "b01",
        "label": "b01",
        "mobjects": {
            "key_txt": {"name": "key_txt", "kind": "text", "essential": True, "key": True, "bbox": [0, 0, 1, 0.533], "height_px": 72.0, "color": "#f4f4f6"}
        }
    }]
    g6_key_pass = run_g6_visual(chapter_dir=tmp_path, layout="16:9", snapshots=snap_key_72, storyboard_data=storyboard)
    c_key_pass = next(c for c in g6_key_pass.checks if c.id == "G6c_min_text_size")
    assert c_key_pass.passed is True

    # 4. Key text at 90% of 72 px (64.8 px) fails
    snap_key_64 = [{
        "beat_id": "b01",
        "label": "b01",
        "mobjects": {
            "key_txt": {"name": "key_txt", "kind": "text", "essential": True, "key": True, "bbox": [0, 0, 1, 0.48], "height_px": 72.0 * 0.9, "color": "#f4f4f6"}
        }
    }]
    g6_key_fail = run_g6_visual(chapter_dir=tmp_path, layout="16:9", snapshots=snap_key_64, storyboard_data=storyboard)
    c_key_fail = next(c for c in g6_key_fail.checks if c.id == "G6c_min_text_size")
    assert c_key_fail.passed is False
    assert "below required" in c_key_fail.message.lower()


# ============================================================================
# 18. G4g Digits-in-Text Advanced Rules (f-string, facts.latex, Figure 1)
# ============================================================================

def test_g4g_fstring_and_facts_latex_pass(tmp_path):
    """
    Verify G4g:
    - An f-string built from verified facts passes
    - MathTex(facts.latex(...)) passes
    """
    scene_code = """
from manim import Text, MathTex, Scene
from core.scene_base import BaseScene

class VerifiedMathScene(BaseScene):
    def construct(self):
        val = self.facts.get("lambda_1")
        lbl = Text(f"Eigenvalue is {val}")
        eq = MathTex(self.facts.latex("matrix_A"))
        self.add(lbl, eq)
"""
    g4 = run_g4_code(chapter_dir=tmp_path, scene_source=scene_code)
    g4g_check = next((c for c in g4.checks if c.id == "G4g_digits_in_text"), None)
    assert g4g_check is not None
    assert g4g_check.passed is True
    assert g4g_check.severity == "error"


def test_g4g_figure_1_flagged_unless_allow_digits(tmp_path):
    """
    Verify G4g:
    - Text('Figure 1') is flagged as an error
    - Text('Figure 1') with '# q8l: allow-digits <reason>' passes with a warning
    """
    # 1. Unescaped Text("Figure 1") fails G4g
    scene_bad = """
from manim import Text, Scene
from core.scene_base import BaseScene

class FigureScene(BaseScene):
    def construct(self):
        fig = Text("Figure 1")
        self.add(fig)
"""
    g4_bad = run_g4_code(chapter_dir=tmp_path, scene_source=scene_bad)
    c_bad = next(c for c in g4_bad.checks if c.id == "G4g_digits_in_text")
    assert c_bad.passed is False
    assert c_bad.severity == "error"
    assert "Figure 1" in c_bad.message

    # 2. Text("Figure 1") with escape hatch passes with warning
    scene_good = """
from manim import Text, Scene
from core.scene_base import BaseScene

class FigureScene(BaseScene):
    def construct(self):
        fig = Text("Figure 1")  # q8l: allow-digits diagram label for textbook figure
        self.add(fig)
"""
    g4_good = run_g4_code(chapter_dir=tmp_path, scene_source=scene_good)
    c_good = next(c for c in g4_good.checks if c.id == "G4g_digits_in_text")
    assert c_good.passed is True
    assert c_good.severity == "warning"
    assert "diagram label for textbook figure" in c_good.message

