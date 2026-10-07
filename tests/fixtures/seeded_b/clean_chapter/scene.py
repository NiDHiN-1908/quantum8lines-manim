from manim import MathTex, ORIGIN, Rectangle
from core.tokens import PRIMARY, TEXT
from core.scene_base import BaseScene


class CleanScene(BaseScene):
    """Clean scene fixture adhering strictly to all Quantum8Lines Quality Gates."""

    def construct(self):
        # Background card to guarantee non-empty frames (> 0.2% non-background pixels)
        bg = Rectangle(width=1, height=1, color=PRIMARY, fill_color=PRIMARY, fill_opacity=1)
        bg.move_to(ORIGIN)
        self.register("bg_box", bg, kind="object", essential=True, group="main")

        # Mathematical equation utilizing verified facts via Facts.latex
        val_latex = self.facts.latex("c01")
        title = MathTex(f"x + {val_latex} = x", color=TEXT)
        title.height = 1
        title.move_to(ORIGIN)
        self.register("title_text", title, kind="text", essential=True, group="main")

        self.add(bg, title)

        with self.beat("b01"):
            pass
        with self.beat("b02"):
            pass
        with self.beat("b03"):
            pass
        with self.beat("b04"):
            pass
        with self.beat("b05"):
            pass
