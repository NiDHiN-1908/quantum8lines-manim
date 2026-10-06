"""
MatrixView component for Quantum8Lines.
Visualizes numerical or symbolic matrices with optional entry highlighting.
"""

from typing import Union, Sequence, Optional, Dict, Any, List, Tuple
from manim import Matrix, MathTex, VGroup, SurroundingRectangle, LEFT, RIGHT

from core.tokens import TEXT, HIGHLIGHT, STATIC, PRIMARY


class MatrixView(VGroup):
    """
    A formatted matrix display with optional entry highlighting and label.

    Arguments:
        matrix: 2D list of numbers/strings, or a dict from Facts.require_verified()
                containing a 'matrix' key.
        label: Optional LaTeX string prefix (e.g. "A =" or r"M =").
        highlight_entries: Optional list of (row, col) 0-indexed tuples, or dict
                           mapping (row, col) to a semantic color token.
        highlight_color: Default color for highlighted entries (default: HIGHLIGHT).
        bracket_color: Color of the surrounding brackets (default: STATIC).
        entry_color: Color of standard entries (default: TEXT).
        h_buff: Horizontal spacing between entries (default: 0.8).
        v_buff: Vertical spacing between entries (default: 0.7).

    Usage example:
        >>> # From Facts:
        >>> facts = Facts.load("facts.json")
        >>> data = facts.require_verified("c1")  # {"matrix": [[2, 1], [0, 3]], ...}
        >>> m = MatrixView(matrix=data["matrix"], label="A =", highlight_entries=[(0, 0), (1, 1)])
        >>> # Plain data:
        >>> m2 = MatrixView([[1, 0], [0, 1]], bracket_color=PRIMARY)
    """

    def __init__(
        self,
        matrix: Union[Sequence[Sequence[Any]], Dict[str, Any]],
        label: Optional[str] = None,
        highlight_entries: Optional[Union[List[Tuple[int, int]], Dict[Tuple[int, int], Any]]] = None,
        highlight_color=HIGHLIGHT,
        bracket_color=STATIC,
        entry_color=TEXT,
        h_buff: float = 0.8,
        v_buff: float = 0.7,
        **kwargs
    ):
        super().__init__(**kwargs)

        # Extract 2D matrix if passed via Facts dict
        if isinstance(matrix, dict):
            raw = matrix.get("matrix") or matrix.get("A") or matrix.get("values")
            if raw is None:
                raise ValueError("Dictionary passed to MatrixView must contain 'matrix', 'A', or 'values' key.")
        else:
            raw = matrix

        # Convert entries to strings for Manim Matrix
        formatted_matrix = [[str(elem) for elem in row] for row in raw]
        num_rows = len(formatted_matrix)
        num_cols = len(formatted_matrix[0]) if num_rows > 0 else 0

        self.matrix_mobject = Matrix(
            formatted_matrix,
            h_buff=h_buff,
            v_buff=v_buff,
            bracket_h_buff=0.15,
            bracket_v_buff=0.15,
        )

        # Color brackets and default entries
        for bracket in self.matrix_mobject.get_brackets():
            bracket.set_color(bracket_color)
        for entry in self.matrix_mobject.get_entries():
            entry.set_color(entry_color)

        # Handle entry highlights
        self.highlights_group = VGroup()
        if highlight_entries:
            if isinstance(highlight_entries, (list, tuple, set)):
                hl_dict = {tuple(pos): highlight_color for pos in highlight_entries}
            else:
                hl_dict = highlight_entries

            for (r, c), col in hl_dict.items():
                if 0 <= r < num_rows and 0 <= c < num_cols:
                    entry_mob = self.matrix_mobject.get_entries()[r * num_cols + c]
                    entry_mob.set_color(col)
                    # Add subtle highlighting box around highlighted entries
                    box = SurroundingRectangle(entry_mob, color=col, buff=0.1, stroke_width=1.5)
                    self.highlights_group.add(box)

        self.add(self.matrix_mobject)
        if len(self.highlights_group) > 0:
            self.add(self.highlights_group)

        # Add optional prefix label
        self.label_mobject: Optional[MathTex] = None
        if label:
            self.label_mobject = MathTex(label, color=TEXT)
            self.label_mobject.next_to(self.matrix_mobject, LEFT, buff=0.25)
            self.add(self.label_mobject)

    def get_entry(self, row: int, col: int):
        """Return the Mobject for entry at (row, col)."""
        num_cols = len(self.matrix_mobject.get_columns())
        return self.matrix_mobject.get_entries()[row * num_cols + col]
