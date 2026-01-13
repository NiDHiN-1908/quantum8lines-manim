from manim import *
import numpy as np


class EigenvectorRefusal(Scene):
    def construct(self):
        self.camera.background_color = "#0e0e11"

        # Pause in empty space
        self.wait(0.8)

        # Create multiple vectors
        directions = [
            np.array([1.0, 0.0, 0]),
            np.array([0.6, 0.8, 0]),
            np.array([-0.7, 0.5, 0]),
            np.array([-0.4, -0.9, 0]),
            np.array([0.3, -0.6, 0]),
        ]

        vectors = VGroup()
        for d in directions:
            v = Arrow(
                ORIGIN,
                2.5 * d,
                buff=0,
                stroke_width=4,
                color=GREY_B,
            )
            vectors.add(v)

        self.play(FadeIn(vectors), run_time=1.2)
        self.wait(0.5)

        # Highlight invariant direction
        eigen_vector = Arrow(
            ORIGIN,
            2.5 * np.array([1, 0, 0]),
            buff=0,
            stroke_width=6,
            color=BLUE,
        )

        self.play(ReplacementTransform(vectors[0], eigen_vector))
        vectors.remove(vectors[0])
        vectors.add(eigen_vector)

        self.wait(0.6)

        # Apply linear transformation
        transform_matrix = np.array([
            [2.0, 0.0],
            [0.6, 0.7],
        ])

        self.play(
            ApplyMatrix(transform_matrix, vectors),
            run_time=2.5,
        )

        # Let it register
        self.wait(1.8)

        sentence = Text(
            "This direction doesn’t rotate.",
            font_size=36,
            color=GREY_A,
        ).to_edge(DOWN)

        self.play(FadeIn(sentence))
        self.wait(1.4)
        self.play(FadeOut(sentence))

        self.wait(1.0)
