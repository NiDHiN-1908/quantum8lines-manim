"""
Callout component for Quantum8Lines.
Visualizes a short text box with an orientable pointer indicating a target point or object.
"""

from typing import Union, Sequence, Optional
import numpy as np
from manim import (
    VGroup,
    Text,
    RoundedRectangle,
    Arrow,
    ORIGIN,
    DOWN,
    UP,
    LEFT,
    RIGHT,
    Mobject,
)

from core.tokens import TEXT, STATIC, BACKGROUND, HIGHLIGHT
from core.fonts import get_inter_font


class Callout(VGroup):
    """
    A short text box with an orientable pointer arrow.

    Arguments:
        text: Short string to display in the callout box.
        target_point: Optional coordinate [x, y, z] or Mobject that the pointer aims toward.
        direction: Relative placement direction from target (default: UP).
        font_size: Font size for Inter text (default: 28).
        box_color: Border stroke color token (default: HIGHLIGHT).
        text_color: Text color token (default: TEXT).
        bg_color: Box fill background color token (default: BACKGROUND).
        buff: Padding inside the box around the text (default: 0.25).
        pointer_length: Length of pointer arrow (default: 0.4).

    Usage example:
        >>> dot = Dot([1.0, 1.0, 0.0])
        >>> callout = Callout("Critical Point", target_point=dot, direction=UP)
        >>> # Plain coordinate target:
        >>> callout2 = Callout("Eigenvector line", target_point=[2.0, 0.0, 0.0], direction=UR)
    """

    def __init__(
        self,
        text: str,
        target_point: Optional[Union[Sequence[float], Mobject]] = None,
        direction: Sequence[float] = UP,
        font_size: int = 28,
        box_color=HIGHLIGHT,
        text_color=TEXT,
        bg_color=BACKGROUND,
        buff: float = 0.25,
        pointer_length: float = 0.45,
        **kwargs
    ):
        super().__init__(**kwargs)

        font_name = get_inter_font()
        self.text_mobject = Text(
            text,
            font=font_name,
            font_size=font_size,
            color=text_color,
        )

        width = self.text_mobject.width + 2 * buff
        height = self.text_mobject.height + 2 * buff

        self.box = RoundedRectangle(
            corner_radius=0.15,
            width=width,
            height=height,
            fill_color=bg_color,
            fill_opacity=0.92,
            stroke_color=box_color,
            stroke_width=2.0,
        )
        self.text_mobject.move_to(self.box.get_center())

        self.box_group = VGroup(self.box, self.text_mobject)
        self.add(self.box_group)

        self.pointer: Optional[Arrow] = None
        if target_point is not None:
            if isinstance(target_point, Mobject):
                tgt = target_point.get_center()
            else:
                tgt = np.array(list(target_point) + [0.0] * (3 - len(target_point)), dtype=float)

            dir_norm = np.array(list(direction) + [0.0] * (3 - len(direction)), dtype=float)
            norm = np.linalg.norm(dir_norm)
            if norm > 1e-6:
                dir_norm = dir_norm / norm
            else:
                dir_norm = UP

            # Place box offset from target along direction
            box_offset = tgt + dir_norm * (pointer_length + max(width, height) / 2.0)
            self.box_group.move_to(box_offset)

            # Pointer points from box edge to target
            box_edge = self.box.get_critical_point(-dir_norm)
            self.pointer = Arrow(
                start=box_edge,
                end=tgt,
                buff=0.05,
                color=box_color,
                stroke_width=2.5,
                max_tip_length_to_length_ratio=0.3,
            )
            self.add(self.pointer)
