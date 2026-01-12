# ===== BOOTSTRAP (DO NOT TOUCH) =====
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
# ===================================

from manim import (
    Scene, Dot,
    FadeIn,
    RIGHT, linear
)

from src.core.colors import *
from src.core.camera import setup_scene
from src.core.helpers import pause


class MotionVsPause(Scene):
    def construct(self):
        setup_scene(self)

        # ---- Version A: Continuous motion (bad clarity) ----
        dot_fast = Dot(radius=0.07, color=DYNAMIC)
        dot_fast.shift(LEFT * 3)

        self.play(FadeIn(dot_fast))
        self.play(
            dot_fast.animate.shift(RIGHT * 6),
            run_time=2.5,
            rate_func=linear
        )
        pause(self, 1)

        self.remove(dot_fast)

        # ---- Version B: Motion + pause (good clarity) ----
        dot_clear = Dot(radius=0.07, color=PRIMARY)
        dot_clear.shift(LEFT * 3)

        self.play(FadeIn(dot_clear))
        pause(self, 0.6)

        # Step 1
        self.play(dot_clear.animate.shift(RIGHT * 2), run_time=0.9, rate_func=linear)
        pause(self, 0.6)

        # Step 2
        self.play(dot_clear.animate.shift(RIGHT * 2), run_time=0.9, rate_func=linear)
        pause(self, 0.6)

        # Step 3
        self.play(dot_clear.animate.shift(RIGHT * 2), run_time=0.9, rate_func=linear)
        pause(self, 1.0)
