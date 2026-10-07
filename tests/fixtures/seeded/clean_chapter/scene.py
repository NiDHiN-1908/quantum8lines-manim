"""
Clean scene code fixture for seeded quality gate tests.
Conforms to all G4 rules: no disallowed numerics, no raw colors, restricted imports, BaseScene subclass.
"""

from manim import Dot, FadeIn, ORIGIN, RIGHT
from core.scene_base import BaseScene
from core.tokens import PRIMARY


class CleanChapterScene(BaseScene):
    """Clean scene definition adhering to all G4 quality standards."""

    def construct(self):
        with self.beat("b01"):
            dot = Dot(point=ORIGIN, color=PRIMARY)
            self.register("dot_v", dot, essential=True, kind="object")
            self.play(FadeIn(dot), run_time=1)
