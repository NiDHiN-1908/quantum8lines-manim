from manim import Scene
from core.scene_base import BaseScene, HelloScene


def test_scene_hierarchy():
    """Verify that BaseScene and HelloScene subclass Manim Scene properly."""
    assert issubclass(BaseScene, Scene)
    assert issubclass(HelloScene, BaseScene)


def test_mathengine_prerequisites():
    """Verify NumPy and SymPy imports and basic symbolic evaluation."""
    import numpy as np
    import sympy as sp

    x = sp.Symbol("x")
    expr = x**2 - 4
    roots = sp.solve(expr, x)
    assert roots == [-2, 2]

    arr = np.array([1.0, 0.0])
    assert arr.shape == (2,)
