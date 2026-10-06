"""
VectorArrow component for Quantum8Lines.
Visualizes vectors derived from Facts verification or coordinate data.
"""

from typing import Union, Sequence, Optional, Dict, Any
import numpy as np
from manim import Arrow, MathTex, VGroup, ORIGIN, RIGHT, UR

from core.tokens import PRIMARY, TEXT
from core.layout import Layout, LAYOUT_169


class VectorArrow(VGroup):
    """
    A 2D/3D vector arrow with an optional semantic label.

    Arguments:
        vector: Coordinates [x, y] or [x, y, z], or a dict from Facts.require_verified()
                containing a 'vector' key.
        start: Starting point in Manim coordinates (default ORIGIN: [0, 0, 0]).
        label: Optional LaTeX string label (e.g. r"\\vec{v}").
        color: Semantic color token from core.tokens (default: PRIMARY).
        stroke_width: Line stroke width (default: 4.0).
        max_tip_length_to_length_ratio: Tip scaling ratio (default: 0.25).

    Usage example:
        >>> # From Facts:
        >>> facts = Facts.load("facts.json")
        >>> data = facts.require_verified("c1")  # {"vector": [2, 1], ...}
        >>> v = VectorArrow(vector=data["vector"], label=r"\\vec{v}")
        >>> # Or plain data:
        >>> v2 = VectorArrow(vector=[3.0, 1.5], color=SECONDARY, label=r"\\vec{w}")
    """

    def __init__(
        self,
        vector: Union[Sequence[float], Dict[str, Any]],
        start: Sequence[float] = ORIGIN,
        label: Optional[str] = None,
        color=PRIMARY,
        stroke_width: float = 4.0,
        max_tip_length_to_length_ratio: float = 0.25,
        **kwargs
    ):
        super().__init__(**kwargs)

        # Extract coordinates if passed as a Facts dictionary
        if isinstance(vector, dict):
            coords = vector.get("vector") or vector.get("values") or vector.get("point")
            if coords is None:
                raise ValueError("Dictionary passed to VectorArrow must contain 'vector', 'values', or 'point' key.")
        else:
            coords = vector

        # Convert to 3D numpy array
        start_pt = np.array(list(start) + [0.0] * (3 - len(start)), dtype=float)
        coord_list = list(coords)
        if len(coord_list) == 2:
            end_pt = start_pt + np.array([float(coord_list[0]), float(coord_list[1]), 0.0])
        elif len(coord_list) >= 3:
            end_pt = start_pt + np.array([float(coord_list[0]), float(coord_list[1]), float(coord_list[2])])
        else:
            raise ValueError(f"Vector coordinates must have at least 2 elements, got {len(coord_list)}")

        self.arrow = Arrow(
            start=start_pt,
            end=end_pt,
            buff=0.0,
            color=color,
            stroke_width=stroke_width,
            max_tip_length_to_length_ratio=max_tip_length_to_length_ratio,
        )
        self.add(self.arrow)

        self.label_mobject: Optional[MathTex] = None
        if label:
            self.label_mobject = MathTex(label, color=color)
            # Position label slightly offset from the arrow tip along the vector direction
            direction = end_pt - start_pt
            norm = np.linalg.norm(direction)
            unit_dir = direction / norm if norm > 1e-6 else RIGHT
            self.label_mobject.next_to(self.arrow.get_end(), unit_dir + 0.3 * UR, buff=0.15)
            self.add(self.label_mobject)

    @property
    def tip(self):
        return self.arrow.get_end()
