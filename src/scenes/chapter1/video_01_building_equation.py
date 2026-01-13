# ===== BOOTSTRAP (DO NOT TOUCH) =====
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
# ===================================

from manim import (
    Scene, MathTex,
    FadeIn, Transform,
    UP, DOWN
)

from src.core.colors import *
from src.core.camera import setup_scene
from src.core.helpers import pause


class BuildEquation(Scene):
    def construct(self):
        setup_scene(self)

        # Step 0 — empty space (expectation)
        pause(self, 0.6)

        # Step 1 — x
        x = MathTex("x", color=PRIMARY)
        self.play(FadeIn(x))
        pause(self, 0.6)

        # Step 2 — x^2 (power attaches, not appears)
        x2 = MathTex("x^2", color=PRIMARY)
        self.play(Transform(x, x2))
        pause(self, 0.6)

        # Step 3 — x^2 - 4
        expr = MathTex("x^2", "-", "4")
        expr[0].set_color(PRIMARY)
        expr[1].set_color(STATIC)
        expr[2].set_color(SECONDARY)

        self.play(Transform(x, expr))
        pause(self, 0.8)

        # Step 4 — = 0 appears LAST
        equation = MathTex("x^2", "-", "4", "=", "0")
        equation[0].set_color(PRIMARY)
        equation[1].set_color(STATIC)
        equation[2].set_color(SECONDARY)
        equation[3].set_color(STATIC)
        equation[4].set_color(SECONDARY)

        self.play(Transform(x, equation))
        pause(self, 1.0)

        # Step 5 — subtle structure emphasis (what matters?)
        self.play(equation[0].animate.set_color(HIGHLIGHT))
        pause(self, 0.4)
        self.play(equation[0].animate.set_color(PRIMARY))
        pause(self, 0.8)
