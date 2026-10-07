"""
Unit tests for Audio-First BaseScene (SPEC.md Section 10 & Milestone M4a).
Tests padding arithmetic, BeatOverrunError on overrun, and registered snapshot tracking.
"""

import json
from pathlib import Path
import pytest
from manim import Dot, Circle, FadeIn, config, ORIGIN, RIGHT

from core.scene_base import BaseScene, BeatOverrunError, BeatSnapshot
from core.tokens import PRIMARY, SECONDARY


@pytest.fixture(autouse=True)
def setup_manim_test_config():
    """Ensure Manim runs in dry_run mode without rendering video files."""
    old_dry_run = config.dry_run
    config.dry_run = True
    config.verbosity = "ERROR"
    yield
    config.dry_run = old_dry_run


def test_basescene_standalone_behavior():
    """Verify BaseScene works cleanly without a chapter directory."""
    class StandaloneScene(BaseScene):
        def construct(self):
            with self.beat("intro"):
                d = Dot()
                self.register("dot", d, essential=True, kind="object")
                self.add(d)

    scene = StandaloneScene()
    scene.render()

    assert len(scene.snapshots) == 1
    snap = scene.snapshots[0]
    assert snap.beat_id == "intro"
    assert "dot" in snap.mobjects
    assert snap.mobjects["dot"]["essential"] is True
    assert snap.mobjects["dot"]["kind"] == "object"


def test_beat_padding_arithmetic():
    """Verify that if animations take less than the audio window, the beat is padded to the full duration."""
    storyboard = {
        "chapter": "ch01",
        "beats": [
            {"id": "b01", "line_ids": ["l01"]},
        ],
    }
    # Window duration = 2.0s
    timings = {
        "lines": [
            {"id": "l01", "start": 0.0, "end": 2.0},
        ],
    }

    class PaddedScene(BaseScene):
        def construct(self):
            with self.beat("b01"):
                # Animation runs for 0.5s
                d = Dot()
                self.play(FadeIn(d), run_time=0.5)

    scene = PaddedScene(storyboard_data=storyboard, timings_data=timings)
    scene.render()

    # The beat should be padded by 1.5s so total time is 2.0s
    assert abs(scene.time - 2.0) < 0.05
    assert len(scene.snapshots) == 1
    assert scene.snapshots[0].beat_id == "b01"
    assert abs(scene.snapshots[0].timestamp - 2.0) < 0.05


def test_beat_overrun_error_raised():
    """Verify that BeatOverrunError is raised when animations exceed the audio window."""
    storyboard = {
        "chapter": "ch01",
        "beats": [
            {"id": "b01", "line_ids": ["l01"]},
        ],
    }
    # Window duration = 1.0s
    timings = {
        "lines": [
            {"id": "l01", "start": 0.0, "end": 1.0},
        ],
    }

    class OverrunScene(BaseScene):
        def construct(self):
            with self.beat("b01"):
                # Animation runs for 1.8s (exceeds 1.0s)
                d = Dot()
                self.play(FadeIn(d), run_time=1.8)

    scene = OverrunScene(storyboard_data=storyboard, timings_data=timings)
    with pytest.raises(BeatOverrunError) as exc_info:
        scene.render()

    err = exc_info.value
    assert err.beat_id == "b01"
    assert err.overrun_sec >= 0.7


def test_snapshots_bounding_box_and_metadata():
    """Verify snapshot records bounding box [x_min, y_min, x_max, y_max], kind, essential flag, and color."""
    storyboard = {
        "chapter": "ch01",
        "beats": [
            {"id": "b01", "line_ids": ["l01"]},
        ],
    }
    timings = {
        "lines": [
            {"id": "l01", "start": 0.0, "end": 1.0},
        ],
    }

    class SnapshotScene(BaseScene):
        def construct(self):
            with self.beat("b01"):
                c = Circle(radius=1.0, color=PRIMARY)
                c.move_to(ORIGIN)
                self.register("circle", c, essential=True, kind="object")

                t = Dot(color=SECONDARY).move_to(2.0 * RIGHT)
                self.register("tracker", t, essential=False, kind="text")

                self.add(c, t)

    scene = SnapshotScene(storyboard_data=storyboard, timings_data=timings)
    scene.render()

    assert len(scene.snapshots) == 1
    beat_id, timestamp, mobjects = scene.snapshots[0]
    assert beat_id == "b01"
    assert abs(timestamp - 1.0) < 0.05

    # Check circle snapshot
    circle_info = mobjects["circle"]
    assert circle_info["name"] == "circle"
    assert circle_info["kind"] == "object"
    assert circle_info["essential"] is True
    # Circle of radius 1 at origin has bbox [-1.0, -1.0, 1.0, 1.0]
    assert circle_info["bbox"] == [-1.0, -1.0, 1.0, 1.0]
    assert circle_info["color"].lower() == str(PRIMARY).lower()

    # Check tracker snapshot
    tracker_info = mobjects["tracker"]
    assert tracker_info["name"] == "tracker"
    assert tracker_info["kind"] == "text"
    assert tracker_info["essential"] is False
    assert tracker_info["bbox"][0] > 1.0  # shifted right


def test_register_invalid_kind():
    """Verify register raises ValueError on unsupported kind."""
    scene = BaseScene()
    d = Dot()
    with pytest.raises(ValueError, match="Invalid kind 'widget'"):
        scene.register("bad", d, kind="widget")


def test_chapter_dir_loading(tmp_path: Path):
    """Verify BaseScene automatically loads script.json, audio/timings.json, and storyboard.json from chapter_dir."""
    ch_dir = tmp_path / "ch01"
    ch_dir.mkdir()
    audio_dir = ch_dir / "audio"
    audio_dir.mkdir()

    script = {"chapter": "ch01", "lines": [{"id": "l01", "text": "hello", "beat": "hook"}]}
    timings = {"lines": [{"id": "l01", "start": 0.0, "end": 2.5, "pause_after": 0.5}]}
    storyboard = {"chapter": "ch01", "beats": [{"id": "b01", "line_ids": ["l01"]}]}

    with open(ch_dir / "script.json", "w", encoding="utf-8") as f:
        json.dump(script, f)
    with open(audio_dir / "timings.json", "w", encoding="utf-8") as f:
        json.dump(timings, f)
    with open(ch_dir / "storyboard.json", "w", encoding="utf-8") as f:
        json.dump(storyboard, f)

    class ChapterScene(BaseScene):
        def construct(self):
            with self.beat("b01"):
                pass  # empty beat, should pad to full window (2.5 + 0.5 = 3.0s)

    scene = ChapterScene(chapter_dir=ch_dir)
    scene.render()

    assert abs(scene.time - 3.0) < 0.05
    assert len(scene.snapshots) == 1
    assert scene.snapshots[0].beat_id == "b01"
