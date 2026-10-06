"""
Safe mathematical expression parser for Quantum8Lines.
Follows SPEC.md Section 7 and Milestone M3a Step 0f.

Validates and parses mathematical text expressions using AST inspection and SymPy parse_expr
with restricted global_dict/local_dict:
  - Whitelist of symbols: x, y, z, t, n
  - Whitelist of constants and standard math functions
  - Rejection of double underscores, attribute access, imports, and unknown identifiers.
"""

import ast
from typing import Any, Dict, Set
import sympy as sp
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)

# Standard mathematical transformations (supports implicit multiplication e.g. 2x -> 2*x, and ^ as power)
TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)

ALLOWED_SYMBOLS: Dict[str, sp.Symbol] = {
    "x": sp.Symbol("x"),
    "y": sp.Symbol("y"),
    "z": sp.Symbol("z"),
    "t": sp.Symbol("t"),
    "n": sp.Symbol("n"),
}

ALLOWED_CONSTANTS: Dict[str, Any] = {
    "pi": sp.pi,
    "E": sp.E,
    "e": sp.E,
    "I": sp.I,
}

ALLOWED_FUNCTIONS: Dict[str, Any] = {
    "sin": sp.sin,
    "cos": sp.cos,
    "tan": sp.tan,
    "sec": sp.sec,
    "csc": sp.csc,
    "cot": sp.cot,
    "asin": sp.asin,
    "acos": sp.acos,
    "atan": sp.atan,
    "sinh": sp.sinh,
    "cosh": sp.cosh,
    "tanh": sp.tanh,
    "exp": sp.exp,
    "log": sp.log,
    "ln": sp.log,
    "sqrt": sp.sqrt,
    "abs": sp.Abs,
    "Abs": sp.Abs,
    "floor": sp.floor,
    "ceiling": sp.ceiling,
}

SAFE_INTERNAL_SYMPY: Dict[str, Any] = {
    "Integer": sp.Integer,
    "Float": sp.Float,
    "Rational": sp.Rational,
    "Symbol": sp.Symbol,
}

ALLOWED_NAMES: Set[str] = (
    set(ALLOWED_SYMBOLS.keys())
    | set(ALLOWED_CONSTANTS.keys())
    | set(ALLOWED_FUNCTIONS.keys())
    | set(SAFE_INTERNAL_SYMPY.keys())
)

SAFE_GLOBAL_DICT: Dict[str, Any] = {"__builtins__": {}, **SAFE_INTERNAL_SYMPY}
SAFE_LOCAL_DICT: Dict[str, Any] = {
    **ALLOWED_CONSTANTS,
    **ALLOWED_FUNCTIONS,
    **ALLOWED_SYMBOLS,
    **SAFE_INTERNAL_SYMPY,
}


class SafeParseError(ValueError):
    """Raised when an expression contains unauthorized or dangerous syntax."""
    pass


def validate_expression_ast(expr_str: str) -> None:
    """
    Inspects expression string using Python AST before passing to SymPy.
    Strictly forbids:
      - Double underscores (e.g. __import__, __class__)
      - Attribute access (e.g. x.__class__, os.system)
      - Imports or module access
      - Calls to unapproved functions
      - Symbols/names outside the approved whitelist
    """
    if "__" in expr_str:
        raise SafeParseError(
            f"Double underscores are prohibited in mathematical expressions: '{expr_str}'"
        )

    # Replace '^' with '**' for valid Python AST parsing
    ast_input = expr_str.replace("^", "**")

    # If equation '=' present, validate each side
    if "=" in ast_input and not any(op in ast_input for op in ["==", "<=", ">="]):
        parts = ast_input.split("=", 1)
        validate_expression_ast(parts[0])
        validate_expression_ast(parts[1])
        return

    try:
        tree = ast.parse(ast_input, mode="eval")
    except SyntaxError as e:
        # If AST parsing fails directly (e.g. implicit multiplication like '2x'),
        # verify tokens manually
        _validate_tokens_fallback(expr_str)
        return

    for node in ast.walk(tree):
        # Attribute access: obj.attr
        if isinstance(node, ast.Attribute):
            raise SafeParseError(
                f"Attribute access is strictly prohibited: '{node.attr}' in '{expr_str}'"
            )

        # Imports
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            raise SafeParseError(
                f"Imports are strictly prohibited in mathematical expressions: '{expr_str}'"
            )

        # Function calls
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise SafeParseError(
                    f"Only direct calls to whitelisted math functions are permitted: '{expr_str}'"
                )
            if node.func.id not in ALLOWED_FUNCTIONS:
                raise SafeParseError(
                    f"Function '{node.func.id}' is not in approved math function whitelist: '{expr_str}'"
                )

        # Names / Identifiers
        if isinstance(node, ast.Name):
            if node.id not in ALLOWED_NAMES:
                raise SafeParseError(
                    f"Unknown or unauthorized symbol/function: '{node.id}' in '{expr_str}'. "
                    f"Allowed symbols: {sorted(list(ALLOWED_SYMBOLS.keys()))}."
                )


def _validate_tokens_fallback(expr_str: str) -> None:
    """Fallback scanner for expressions with syntax like implicit multiplication."""
    import re
    # Check for disallowed words
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expr_str)
    for w in words:
        if w.startswith("__") or w.endswith("__"):
            raise SafeParseError(f"Double underscores prohibited: '{w}' in '{expr_str}'")
        if w not in ALLOWED_NAMES:
            raise SafeParseError(f"Unknown or unauthorized symbol: '{w}' in '{expr_str}'")


def safe_parse(expr_input: Any) -> Any:
    """
    Safely parses mathematical expression strings into SymPy expressions.
    Accepts numbers, SymPy expressions, or sanitized string formulas.

    Raises:
        SafeParseError: If expression contains malicious, unauthorized, or malformed syntax.
    """
    if isinstance(expr_input, (sp.Basic, sp.Matrix)):
        return expr_input
    if isinstance(expr_input, (int, float)):
        return sp.nsimplify(expr_input)
    if not isinstance(expr_input, str):
        raise SafeParseError(f"Unsupported expression type: {type(expr_input)}")

    cleaned = expr_input.strip()
    if not cleaned:
        raise SafeParseError("Empty expression string cannot be parsed.")

    # 1. AST Validation
    validate_expression_ast(cleaned)

    # 2. Equation splitting (e.g. "x**2 = 4" -> x**2 - 4)
    if "=" in cleaned and not any(op in cleaned for op in ["==", "<=", ">="]):
        lhs_str, rhs_str = cleaned.split("=", 1)
        lhs = safe_parse(lhs_str.strip())
        rhs = safe_parse(rhs_str.strip())
        return lhs - rhs

    # 3. SymPy Parsing with restricted dictionaries
    try:
        parsed = parse_expr(
            cleaned,
            local_dict=SAFE_LOCAL_DICT,
            global_dict=SAFE_GLOBAL_DICT,
            transformations=TRANSFORMATIONS,
            evaluate=True,
        )
        return parsed
    except Exception as e:
        raise SafeParseError(f"SymPy safe parsing error on '{cleaned}': {str(e)}") from e
