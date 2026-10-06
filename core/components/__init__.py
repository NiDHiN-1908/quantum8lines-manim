"""
Core visual components library for Quantum8Lines.
Follows SPEC.md Section 4 and Milestone M2:
All components use core.tokens colors, core.fonts, and layout engine safe zones.
"""

from core.components.vector import VectorArrow
from core.components.matrix import MatrixView
from core.components.graph import GraphPlot
from core.components.equation import EquationLine
from core.components.callout import Callout
from core.components.mascot import Mascot

__all__ = [
    "VectorArrow",
    "MatrixView",
    "GraphPlot",
    "EquationLine",
    "Callout",
    "Mascot",
]
