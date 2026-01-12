# ===== BOOTSTRAP (DO NOT TOUCH) =====
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
# ===================================

from manim import (
    Scene, Dot, Circle,
    FadeIn, FadeOut,
    RIGHT, linear
)

from src.core.colors import *
from src.core.camera import setup_scene
from src.core.helpers import pause


class ColorIsMeaning(Scene):
    def construct(self):
        setup_scene(self)

        # PRIMARY — existence
        dot = Dot(radius=0.08, color=PRIMARY)
        self.play(FadeIn(dot))
        pause(self, 0.6)

        # DYNAMIC — change
        self.play(dot.animate.set_color(DYNAMIC))
        self.play(
            dot.animate.shift(RIGHT * 3),
            run_time=1.6,
            rate_func=linear
        )
        pause(self, 0.4)

        # SECONDARY — result
        self.play(dot.animate.set_color(SECONDARY))
        pause(self, 0.6)

        # HIGHLIGHT — attention
        ring = Circle(radius=0.22, color=HIGHLIGHT)
        ring.move_to(dot)
        self.play(FadeIn(ring))
        pause(self, 0.3)
        self.play(FadeOut(ring))
        pause(self, 0.8)
