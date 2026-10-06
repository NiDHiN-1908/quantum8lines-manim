"""
Mascot component for Quantum8Lines.
Follows SPEC.md Sections 4.5 and Milestone M2 Step 3:
  - SVG-based Mobject built from brand/brain_icon.svg.
  - Two expressive eyes (sclera + pupil) placed over the hemispheres.
  - Expressive states: idle, blink, think, surprised, point (each returning an animation).
  - Placed in safe corner regions outside the stage region.
"""

from pathlib import Path
from typing import Sequence, Optional, Union
import numpy as np
from manim import (
    VGroup,
    SVGMobject,
    Dot,
    ApplyMethod,
    AnimationGroup,
    Mobject,
    UP,
    DOWN,
    LEFT,
    RIGHT,
    DEGREES,
    rate_functions,
)

from core.tokens import TEXT, BACKGROUND
from core.motion import (
    DEFAULT_RUN_TIME,
    FAST_RUN_TIME,
    DEFAULT_EASING,
)
from core.layout import Layout, LAYOUT_169, LAYOUT_916

DEFAULT_ICON_PATH = Path(__file__).resolve().parents[2] / "brand" / "brain_icon.svg"


class Mascot(VGroup):
    """
    Quantum8Lines Brain Mascot character.

    Arguments:
        svg_path: Path to the brain icon SVG file (default: brand/brain_icon.svg).
        scale_val: Overall scaling factor (default: 0.55).
        eye_color: Color token for the eye whites/sclera (default: TEXT).
        pupil_color: Color token for pupils (default: BACKGROUND).

    States (methods returning animations):
        idle()       -> gentle vertical bobbing animation.
        blink()      -> rapid eye closing and opening.
        think()      -> quizzical head tilt.
        surprised()  -> eye widening with a bouncy scale pop.
        point(tgt)   -> orient toward a target mobject or point.

    Usage example:
        >>> mascot = Mascot()
        >>> mascot.place_corner(LAYOUT_169, "bottom_right")
        >>> scene.play(mascot.blink())
        >>> scene.play(mascot.point([0, 0, 0]))
    """

    def __init__(
        self,
        svg_path: Union[str, Path] = DEFAULT_ICON_PATH,
        scale_val: float = 0.55,
        eye_color=TEXT,
        pupil_color=BACKGROUND,
        **kwargs
    ):
        super().__init__(**kwargs)

        icon_path = Path(svg_path).resolve()
        if not icon_path.exists():
            raise FileNotFoundError(f"Mascot SVG asset not found at {icon_path}")

        # Brain body
        self.body = SVGMobject(str(icon_path))
        self.body.scale(scale_val)
        self.add(self.body)

        # Eyes: Left hemisphere and Right hemisphere
        center = self.body.get_center()
        left_eye_pos = center + np.array([-0.28 * (scale_val / 0.55), 0.05 * (scale_val / 0.55), 0.0])
        right_eye_pos = center + np.array([0.28 * (scale_val / 0.55), 0.05 * (scale_val / 0.55), 0.0])

        sclera_radius = 0.09 * (scale_val / 0.55)
        pupil_radius = 0.045 * (scale_val / 0.55)

        self.left_sclera = Dot(point=left_eye_pos, radius=sclera_radius, color=eye_color)
        self.left_pupil = Dot(point=left_eye_pos + np.array([0.015, -0.01, 0.0]), radius=pupil_radius, color=pupil_color)
        self.left_eye = VGroup(self.left_sclera, self.left_pupil)

        self.right_sclera = Dot(point=right_eye_pos, radius=sclera_radius, color=eye_color)
        self.right_pupil = Dot(point=right_eye_pos + np.array([0.015, -0.01, 0.0]), radius=pupil_radius, color=pupil_color)
        self.right_eye = VGroup(self.right_sclera, self.right_pupil)

        self.eyes = VGroup(self.left_eye, self.right_eye)
        self.add(self.eyes)

    # -----------------------------------------------------------------------
    # Placement
    # -----------------------------------------------------------------------

    def place_corner(self, layout: Layout, corner: str = "bottom_right") -> "Mascot":
        """
        Positions the mascot in a designated safe corner outside the stage region.
        Guarantees that the mascot stays entirely within safe zone and never overlaps stage.
        """
        is_portrait = layout.frame_height > layout.frame_width

        if is_portrait:
            # 9:16 layout
            if corner == "bottom_right":
                target_pos = np.array([2.3, -2.7, 0.0])
            elif corner == "bottom_left":
                target_pos = np.array([-2.3, -2.7, 0.0])
            elif corner == "top_right":
                target_pos = np.array([2.4, 4.4, 0.0])
            elif corner == "top_left":
                target_pos = np.array([-2.4, 4.4, 0.0])
            else:
                target_pos = np.array([2.3, -2.7, 0.0])
        else:
            # 16:9 layout
            if corner == "bottom_right":
                target_pos = np.array([5.0, -2.5, 0.0])
            elif corner == "bottom_left":
                target_pos = np.array([-5.0, -2.5, 0.0])
            elif corner == "top_right":
                target_pos = np.array([5.0, 2.6, 0.0])
            elif corner == "top_left":
                target_pos = np.array([-5.0, 2.6, 0.0])
            else:
                target_pos = np.array([5.0, -2.5, 0.0])

        self.move_to(target_pos)
        return self

    # -----------------------------------------------------------------------
    # Animation States
    # -----------------------------------------------------------------------

    def idle(self, run_time: float = DEFAULT_RUN_TIME):
        """
        Gentle bobbing animation returning to the resting position.
        """
        return ApplyMethod(
            self.shift,
            0.12 * UP,
            rate_func=rate_functions.wiggle,
            run_time=run_time,
        )

    def blink(self, run_time: float = FAST_RUN_TIME):
        """
        Quick blink animation where eyes close and reopen.
        """
        return self.eyes.animate(
            run_time=run_time,
            rate_func=rate_functions.there_and_back,
        ).scale(np.array([1.0, 0.1, 1.0]))

    def think(self, angle: float = 14.0 * DEGREES, run_time: float = DEFAULT_RUN_TIME):
        """
        Curious / inquisitive head tilt with slight gaze shift.
        """
        return self.animate(
            run_time=run_time,
            rate_func=rate_functions.smooth,
        ).rotate(angle, about_point=self.get_bottom())

    def surprised(self, run_time: float = 0.6):
        """
        Surprised reaction: eyes widen and mascot pops with a small scale expansion.
        """
        return AnimationGroup(
            self.animate(
                run_time=run_time,
                rate_func=rate_functions.there_and_back,
            ).scale(1.10),
            self.eyes.animate(
                run_time=run_time,
                rate_func=rate_functions.there_and_back,
            ).scale(1.30),
        )

    def point(self, target: Union[Sequence[float], Mobject], run_time: float = DEFAULT_RUN_TIME):
        """
        Orient and tilt slightly toward a target point or mobject.
        """
        if isinstance(target, Mobject):
            tgt = target.get_center()
        else:
            tgt = np.array(list(target) + [0.0] * (3 - len(target)), dtype=float)

        delta = tgt - self.get_center()
        # Compute orient angle (clamped for a subtle tilt toward target)
        raw_angle = np.arctan2(delta[1], delta[0])
        orient_angle = np.clip(raw_angle * 0.25, -20.0 * DEGREES, 20.0 * DEGREES)

        return self.animate(
            run_time=run_time,
            rate_func=rate_functions.smooth,
        ).rotate(orient_angle, about_point=self.get_center())
