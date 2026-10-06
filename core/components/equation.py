"""
EquationLine component for Quantum8Lines.
Visualizes LaTeX mathematical equations with semantic coloring of sub-expressions.
"""

from typing import Union, Optional, Dict, Any
from manim import MathTex, VGroup

from core.tokens import TEXT, PRIMARY, SECONDARY, HIGHLIGHT


class EquationLine(VGroup):
    """
    A LaTeX equation line with semantic coloring applied to sub-expressions.

    Arguments:
        equation_tex: LaTeX equation string, e.g. r"A \\vec{v} = \\lambda \\vec{v}",
                      or a dict from Facts containing an 'equation' or 'tex' key.
        color_map: Dictionary mapping LaTeX substrings to semantic color tokens,
                   e.g. {"A": PRIMARY, r"\\vec{v}": SECONDARY, r"\\lambda": HIGHLIGHT}.
        font_size: Font size for the equation (default: 44).
        default_color: Default color for unmapped equation tokens (default: TEXT).

    Usage example:
        >>> # Basic semantic coloring:
        >>> eq = EquationLine(
        ...     r"A \\vec{v} = \\lambda \\vec{v}",
        ...     color_map={"A": PRIMARY, r"\\vec{v}": SECONDARY, r"\\lambda": HIGHLIGHT}
        ... )
        >>> # From Facts:
        >>> facts = Facts.load("facts.json")
        >>> data = facts.require_verified("c_eq")
        >>> eq2 = EquationLine(data.get("equation", r"e^{i\\pi} + 1 = 0"))
    """

    def __init__(
        self,
        equation_tex: Union[str, Dict[str, Any]],
        color_map: Optional[Dict[str, Any]] = None,
        font_size: int = 44,
        default_color=TEXT,
        **kwargs
    ):
        super().__init__(**kwargs)

        # Extract tex string if passed via Facts dict
        if isinstance(equation_tex, dict):
            tex_str = (
                equation_tex.get("equation")
                or equation_tex.get("tex")
                or equation_tex.get("formula")
                or equation_tex.get("lhs", "")
            )
            if not tex_str:
                raise ValueError("Dictionary passed to EquationLine must contain 'equation', 'tex', or 'formula'.")
        else:
            tex_str = str(equation_tex)

        color_map = color_map or {}
        substrings = list(color_map.keys())

        if substrings:
            self.math_tex = MathTex(
                tex_str,
                substrings_to_isolate=substrings,
                font_size=font_size,
                color=default_color,
            )
            self.math_tex.set_color_by_tex_to_color_map(color_map)
        else:
            self.math_tex = MathTex(
                tex_str,
                font_size=font_size,
                color=default_color,
            )

        self.add(self.math_tex)
