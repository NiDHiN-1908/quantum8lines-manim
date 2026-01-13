# ===== BOOTSTRAP (DO NOT TOUCH) =====
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
# ===================================

from manim import (
    Scene, MathTex, Axes,
    Create, FadeIn,
    Dot
)

from src.core.colors import *
from src.core.camera import setup_scene
from src.core.helpers import pause


class AlgebraToGeometry(Scene):
    def construct(self):
        setup_scene(self)

        # Equation (algebra view)
        eq = MathTex("x^2", "=", "4")
        eq[0].set_color(PRIMARY)
        eq[1].set_color(STATIC)
        eq[2].set_color(SECONDARY)

        self.play(FadeIn(eq))
        pause(self, 0.8)

        # Move equation up (make space for geometry)
        self.play(eq.animate.shift(UP * 2))
        pause(self, 0.6)

        # Axes (geometry view)
        axes = Axes(
            x_range=[-3, 3, 1],
            y_range=[0, 5, 1],
            x_length=6,
            y_length=4,
            tips=False
        )

        self.play(Create(axes))
        pause(self, 0.6)

        # Parabola y = x^2
        parabola = axes.plot(
            lambda x: x**2,
            color=PRIMARY
        )

        self.play(Create(parabola))
        pause(self, 0.6)

        # Horizontal line y = 4
        line = axes.plot(
            lambda x: 4,
            color=SECONDARY
        )

        self.play(Create(line))
        pause(self, 0.6)

        # Intersection points (solutions)
        p1 = Dot(axes.coords_to_point(2, 4), color=HIGHLIGHT)
        p2 = Dot(axes.coords_to_point(-2, 4), color=HIGHLIGHT)

        self.play(FadeIn(p1), FadeIn(p2))
        pause(self, 1.2)
