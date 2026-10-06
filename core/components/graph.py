"""
GraphPlot component for Quantum8Lines.
Visualizes mathematical functions derived from SymPy expressions via lambdify,
with coordinate axes and optional verified marked points.
"""

from typing import Union, Sequence, Optional, Dict, Any, List, Tuple
import sympy as sp
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)
import numpy as np
from manim import Axes, Dot, MathTex, VGroup, UR

from core.tokens import STATIC, PRIMARY, HIGHLIGHT, TEXT
from core.layout import Layout, LAYOUT_169
from core.mathengine.safe_parse import safe_parse


class GraphPlot(VGroup):
    """
    Coordinate axes with a plotted function from a SymPy expression and optional marked points.

    Arguments:
        expression: SymPy expression or string (e.g. "x**2 - 2" or "sin(x)"), or a dict
                    from Facts.require_verified() containing an 'expression' key.
        x_range: [x_min, x_max, x_step] for the x axis (default: [-4.0, 4.0, 1.0]).
        y_range: [y_min, y_max, y_step] for the y axis (default: [-3.0, 3.0, 1.0]).
        x_length: Physical width of axes in Manim units (default: 6.0).
        y_length: Physical height of axes in Manim units (default: 4.0).
        marked_points: Optional list of (x, y) coordinates or dictionaries to mark on the plot.
        variable: Independent variable symbol name (default: "x").
        curve_color: Color token for the plotted function curve (default: PRIMARY).
        axes_color: Color token for the axes (default: STATIC).
        point_color: Color token for marked points (default: HIGHLIGHT).

    Usage example:
        >>> # From Facts:
        >>> facts = Facts.load("facts.json")
        >>> data = facts.require_verified("c_plot")  # {"expression": "x**2 - 4", ...}
        >>> plot = GraphPlot(expression=data["expression"], marked_points=[(2, 0), (-2, 0)])
        >>> # Plain data:
        >>> plot2 = GraphPlot("sin(x)", x_range=[-3.14, 3.14, 1.57], y_range=[-1.5, 1.5, 0.5])
    """

    def __init__(
        self,
        expression: Union[str, sp.Basic, Dict[str, Any]],
        x_range: Sequence[float] = (-4.0, 4.0, 1.0),
        y_range: Sequence[float] = (-3.0, 3.0, 1.0),
        x_length: float = 6.0,
        y_length: float = 3.8,
        marked_points: Optional[Sequence[Union[Sequence[float], Dict[str, Any]]]] = None,
        variable: str = "x",
        curve_color=PRIMARY,
        axes_color=STATIC,
        point_color=HIGHLIGHT,
        **kwargs
    ):
        super().__init__(**kwargs)

        # Extract expression if passed via Facts dict
        if isinstance(expression, dict):
            expr_raw = expression.get("expression") or expression.get("lhs") or expression.get("formula")
            if expr_raw is None:
                raise ValueError("Dictionary passed to GraphPlot must contain 'expression', 'lhs', or 'formula' key.")
        else:
            expr_raw = expression

        # Parse to SymPy safely
        var_sym = sp.Symbol(variable)
        sym_expr = safe_parse(expr_raw)

        # Create numpy callable via lambdify
        self.func_callable = sp.lambdify(var_sym, sym_expr, modules=["numpy"])

        # Create Axes
        self.axes = Axes(
            x_range=list(x_range),
            y_range=list(y_range),
            x_length=x_length,
            y_length=y_length,
            tips=False,
            axis_config={"color": axes_color, "stroke_width": 2.0},
        )
        self.add(self.axes)

        # Plot function curve
        # Wrap callable to handle constant functions or vectorized inputs cleanly
        def plot_fn(x_val):
            val = self.func_callable(x_val)
            if isinstance(val, (int, float, np.number)):
                return float(val)
            # If array of constants
            return np.array(val, dtype=float)

        self.curve = self.axes.plot(
            plot_fn,
            x_range=[x_range[0], x_range[1]],
            color=curve_color,
            stroke_width=3.5,
        )
        self.add(self.curve)

        # Add marked points if specified
        self.dots_group = VGroup()
        if marked_points:
            for pt in marked_points:
                if isinstance(pt, dict):
                    x_pt = float(pt.get("x", 0.0))
                    y_pt = float(pt.get("y", 0.0))
                    label_str = pt.get("label")
                else:
                    x_pt = float(pt[0])
                    y_pt = float(pt[1])
                    label_str = None

                # Only plot if within visible axes ranges
                if x_range[0] <= x_pt <= x_range[1] and y_range[0] <= y_pt <= y_range[1]:
                    point_coord = self.axes.c2p(x_pt, y_pt)
                    dot = Dot(point=point_coord, color=point_color, radius=0.08)
                    self.dots_group.add(dot)

                    if label_str:
                        lbl = MathTex(label_str, color=TEXT, font_size=24)
                        lbl.next_to(dot, UR, buff=0.1)
                        self.dots_group.add(lbl)

        if len(self.dots_group) > 0:
            self.add(self.dots_group)
