# ===== BOOTSTRAP (DO NOT TOUCH) =====
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))
# ===================================

from manim import *
import numpy as np

from src.core.colors import *
from src.core.camera import setup_scene
from src.core.helpers import pause


class EigenvectorRefusal(Scene):
    def construct(self):
        setup_scene(self)

        # -------------------------------
        # 1. Empty space (reset)
        # -------------------------------
        pause(self, 0.8)

        # -------------------------------
        # 2. Create vectors
        # -------------------------------
        directions = [
            np.array([1, 0, 0]),
            np.array([0.6, 0.8, 0]),
            np.array([-0.7, 0.5, 0]),
            np.array([-0.4, -0.9, 0]),
            np.array([0.3, -0.6, 0]),
        ]

        vectors = VGroup()
        for d in directions:
            v = Arrow(
                ORIGIN,
                2 * d,
                buff=0,
                stroke_width=4,
                color=STATIC,
            )
            vectors.add(v)

        self.play(FadeIn(vectors))
        pause(self, 0.6)

        # -------------------------------
        # 3. Mark the special direction
        # -------------------------------
        eigen_direction = np.array([1, 0, 0])
        eigen_vector = Arrow(
            ORIGIN,
            2 * eigen_direction,
            buff=0,
            stroke_width=6,
            color=PRIMARY,
        )

        self.play(ReplacementTransform(vectors[0], eigen_vector))
        pause(self, 0.6)

        # Replace group
        vectors.remove(vectors[0])
        vectors.add(eigen_vector)

        # -------------------------------
        # 4. Apply linear transformation
        # -------------------------------
        # This matrix stretches x and shears y
        transform_matrix = np.array([
            [2.0, 0.0],
            [0.6, 0.7],
        ])

        self.play(
            ApplyMatrix(transform_matrix, vectors),
            run_time=2.5,
        )

        # -------------------------------
        # 5. Hold (let the viewer notice)
        # -------------------------------
        pause(self, 1.8)

        # -------------------------------
        # 6. Optional sentence (quiet)
        # -------------------------------
        sentence = Text(
            "This direction doesn’t rotate.",
            font_size=36,
            color=HIGHLIGHT,
        ).to_edge(DOWN)

        self.play(FadeIn(sentence))
        pause(self, 1.5)
        self.play(FadeOut(sentence))

        pause(self, 1.0)
