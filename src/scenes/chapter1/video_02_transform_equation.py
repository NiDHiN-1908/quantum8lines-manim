# ===== BOOTSTRAP (DO NOT TOUCH) =====
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
# ===================================

from manim import (
    Scene, MathTex,
    Transform, FadeIn,
    UP
)

from src.core.colors import *
from src.core.camera import setup_scene
from src.core.helpers import pause


class TransformEquation(Scene):
    def construct(self):
        setup_scene(self)

        # Initial equation: x^2 - 4 = 0
        eq1 = MathTex("x^2", "-", "4", "=", "0")
        eq1[0].set_color(PRIMARY)
        eq1[1].set_color(STATIC)
        eq1[2].set_color(SECONDARY)
        eq1[3].set_color(STATIC)
        eq1[4].set_color(SECONDARY)

        self.play(FadeIn(eq1))
        pause(self, 0.8)

        # Emphasize the moving term (-4)
        self.play(eq1[2].animate.set_color(HIGHLIGHT))
        pause(self, 0.6)

        # Target equation: x^2 = 4
        eq2 = MathTex("x^2", "=", "4")
        eq2[0].set_color(PRIMARY)
        eq2[1].set_color(STATIC)
        eq2[2].set_color(SECONDARY)

        eq2.move_to(eq1)

        # Transform visually (continuity preserved)
        self.play(Transform(eq1, eq2))
        pause(self, 1.2)
