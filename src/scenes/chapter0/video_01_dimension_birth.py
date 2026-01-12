# ===== BOOTSTRAP (DO NOT TOUCH) =====
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
# ===================================

from manim import (
    Scene, Dot, Line,
    FadeIn,
    RIGHT, LEFT, UP,
    linear, smooth
)

from src.core.colors import *
from src.core.camera import setup_scene
from src.core.helpers import pause, traced, smooth_shift


class DimensionBirth(Scene):
    def construct(self):
        setup_scene(self)

        # 0D — POINT (existence)
        point = Dot(radius=0.06, color=PRIMARY)
        self.play(FadeIn(point, scale=0.5))
        pause(self, 0.6)

        # 1D — LINE (point in motion)
        moving_point = Dot(radius=0.05, color=PRIMARY)
        line_trace = traced(moving_point, color=SECONDARY)

        self.add(line_trace, moving_point)
        self.play(
            smooth_shift(
                moving_point,
                RIGHT,
                4,
                run_time=2,
                rate_func=linear
            )
        )
        pause(self, 0.5)

        self.remove(moving_point)

        # 2D — PLANE (line in motion)
        line = Line(LEFT * 2, RIGHT * 2, color=SECONDARY)
        line.shift(UP * -1.5)

        plane_trace = traced(line, color=DYNAMIC, width=6)
        self.add(plane_trace)

        self.play(
            smooth_shift(
                line,
                UP,
                3,
                run_time=2,
                rate_func=smooth
            )
        )

        pause(self, 1.0)
