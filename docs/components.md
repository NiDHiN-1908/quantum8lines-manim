# Visual Components Library

Follows **SPEC.md Section 4** and **Milestone M2**.

All components in `core.components` adhere to the channel's core design system:
- **No hard-coded numbers**: Coordinates, matrices, and expressions originate from `Facts.require_verified()` results or caller-provided parameters. Layout positions derive from `core.layout`.
- **Semantic color tokens**: Colors use `core.tokens` (`PRIMARY`, `SECONDARY`, `DYNAMIC`, `STATIC`, `HIGHLIGHT`, `TEXT`, `BACKGROUND`).
- **Typography**: Labels use `Inter` via `core.fonts` or LaTeX `MathTex`.
- **Multi-layout compatibility**: Every component operates cleanly in both 16:9 landscape (`LAYOUT_169`) and 9:16 portrait (`LAYOUT_916`).

---

## 1. VectorArrow

Visualizes 2D or 3D vectors with directional arrowheads and optional LaTeX labels.

```python
from core.components import VectorArrow
from core.tokens import PRIMARY, SECONDARY

# From Facts verification:
vector_data = facts.require_verified("c1")  # {"vector": [2, 1], ...}
arrow = VectorArrow(vector=vector_data["vector"], label=r"\vec{v}", color=PRIMARY)

# From plain coordinates:
arrow2 = VectorArrow(vector=[1.5, 3.0], color=SECONDARY, label=r"\vec{w}")
```

### Arguments
- `vector`: `[x, y]` or `[x, y, z]` coordinate sequence or Facts dictionary containing `'vector'`.
- `start`: Start point in Manim coordinates (default: `ORIGIN`).
- `label`: Optional LaTeX label string (e.g. `r"\vec{v}"`).
- `color`: Semantic color token (default: `PRIMARY`).
- `stroke_width`: Line width (default: `4.0`).
- `max_tip_length_to_length_ratio`: Arrow tip proportion (default: `0.25`).

---

## 2. MatrixView

Renders numerical or symbolic matrices with bracket styling and optional entry highlighting.

```python
from core.components import MatrixView
from core.tokens import HIGHLIGHT

# Matrix with specific entries highlighted:
mat = MatrixView(
    matrix=[[2, 1], [0, 3]],
    label="A =",
    highlight_entries=[(0, 0), (1, 1)],
    highlight_color=HIGHLIGHT
)
```

### Arguments
- `matrix`: 2D list of numbers/strings or Facts dictionary containing `'matrix'`.
- `label`: Optional LaTeX prefix label (e.g. `"A ="`).
- `highlight_entries`: List of `(row, col)` 0-indexed tuples, or dict mapping `(row, col)` to colors.
- `highlight_color`: Semantic color for highlighted entries (default: `HIGHLIGHT`).
- `bracket_color`: Color for bracket outlines (default: `STATIC`).
- `entry_color`: Color for standard numbers (default: `TEXT`).

---

## 3. GraphPlot

Visualizes continuous functions evaluated symbolically with SymPy via `lambdify`, over coordinate axes, with optional verified discrete points.

```python
from core.components import GraphPlot

# Plotting a parabola with root points:
plot = GraphPlot(
    expression="x**2 - 4",
    x_range=[-4.0, 4.0, 1.0],
    y_range=[-5.0, 5.0, 2.0],
    marked_points=[[-2, 0], [2, 0]]
)
```

### Arguments
- `expression`: SymPy expression string or symbolic object.
- `x_range`: `[x_min, x_max, x_step]` for horizontal axis.
- `y_range`: `[y_min, y_max, y_step]` for vertical axis.
- `x_length`, `y_length`: Physical dimensions in Manim frame units.
- `marked_points`: List of coordinates or dictionaries to mark with dots and labels.
- `curve_color`: Color for function curve (default: `PRIMARY`).
- `axes_color`: Color for axes lines (default: `STATIC`).
- `point_color`: Color for marked dots (default: `HIGHLIGHT`).

---

## 4. EquationLine

Renders clean LaTeX formulas with semantic coloring applied to designated sub-expressions.

```python
from core.components import EquationLine
from core.tokens import PRIMARY, SECONDARY, HIGHLIGHT

eq = EquationLine(
    r"A \vec{v} = \lambda \vec{v}",
    color_map={
        "A": PRIMARY,
        r"\vec{v}": SECONDARY,
        r"\lambda": HIGHLIGHT
    },
    font_size=44
)
```

### Arguments
- `equation_tex`: LaTeX string or Facts dictionary containing `'equation'`.
- `color_map`: Mapping of LaTeX substrings to semantic color tokens.
- `font_size`: Font size for formula (default: `44`).
- `default_color`: Color for unmapped tokens (default: `TEXT`).

---

## 5. Callout

Renders an explanatory text container with an orientable pointer arrow directed toward a target object or location.

```python
from core.components import Callout
from manim import UP, Dot

dot = Dot([1.0, 2.0, 0.0])
callout = Callout("Eigenvector line", target_point=dot, direction=UP)
```

### Arguments
- `text`: String text displayed inside the callout box.
- `target_point`: Target coordinates `[x, y, z]` or Mobject that the pointer arrow aims toward.
- `direction`: Unit vector indicating placement offset relative to the target (default: `UP`).
- `box_color`: Border color token (default: `HIGHLIGHT`).
- `text_color`: Text typography color token (default: `TEXT`).
- `bg_color`: Background fill color token (default: `BACKGROUND`).

---

## 6. Mascot

See [docs/mascot.md](file:///c:/Users/nidhi/Desktop/quantum8lines-manim/docs/mascot.md) for full character specification, design decisions, and state animations.
