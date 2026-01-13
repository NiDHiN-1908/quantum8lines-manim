# ===== BOOTSTRAP (DO NOT TOUCH) =====
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
# ===================================

from manim import (
    Scene, MathTex,
    FadeIn
)

from src.core.colors import *
from src.core.camera import setup_scene
from src.core.helpers import pause


class HighlightStructure(Scene):
    def construct(self):
        setup_scene(self)

        # Base equation
        eq = MathTex("x^2", "=", "4")
        eq[0].set_color(PRIMARY)    # variable term
        eq[1].set_color(STATIC)     # operator
        eq[2].set_color(SECONDARY)  # constant

        self.play(FadeIn(eq))
        pause(self, 0.8)

        # Step 1 — highlight variable structure
        self.play(
            eq[1].animate.set_opacity(0.2),
            eq[2].animate.set_opacity(0.2),
            eq[0].animate.set_color(HIGHLIGHT)
        )
        pause(self, 0.8)

        # Restore
        self.play(
            eq[1].animate.set_opacity(1),
            eq[2].animate.set_opacity(1),
            eq[0].animate.set_color(PRIMARY)
        )
        pause(self, 0.6)

        # Step 2 — highlight constant
        self.play(
            eq[0].animate.set_opacity(0.2),
            eq[1].animate.set_opacity(0.2),
            eq[2].animate.set_color(HIGHLIGHT)
        )
        pause(self, 0.8)

        # Restore all
        self.play(
            eq[0].animate.set_opacity(1),
            eq[1].animate.set_opacity(1),
            eq[2].animate.set_color(SECONDARY)
        )
        pause(self, 1.0)
