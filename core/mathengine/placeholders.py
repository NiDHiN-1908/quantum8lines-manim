"""
Placeholder syntax, resolution engine, and mathematical spoken-English translation.
Follows SPEC.md Sections 5.2, 5.3, 7, and Milestone M5a Step 3.
"""

import re
from typing import Any, Union
import sympy as sp

from core.mathengine.safe_parse import safe_parse

_ONES = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]

_TENS = [
    "",
    "",
    "twenty",
    "thirty",
    "forty",
    "fifty",
    "sixty",
    "seventy",
    "eighty",
    "ninety",
]

_ORDINAL_DENOMINATORS = {
    2: ("half", "halves"),
    3: ("third", "thirds"),
    4: ("quarter", "quarters"),
    5: ("fifth", "fifths"),
    6: ("sixth", "sixths"),
    7: ("seventh", "sevenths"),
    8: ("eighth", "eighths"),
    9: ("ninth", "ninths"),
    10: ("tenth", "tenths"),
}


def int_to_words(n: int) -> str:
    """Convert an integer in [-999999, 999999] to spoken English words."""
    if n < 0:
        return f"minus {int_to_words(-n)}"
    if n < 20:
        return _ONES[n]
    if n < 100:
        ten, rem = divmod(n, 10)
        return _TENS[ten] if rem == 0 else f"{_TENS[ten]} {_ONES[rem]}"
    if n < 1000:
        hundred, rem = divmod(n, 100)
        prefix = f"{_ONES[hundred]} hundred"
        return prefix if rem == 0 else f"{prefix} {int_to_words(rem)}"
    if n < 1000000:
        thousand, rem = divmod(n, 1000)
        prefix = f"{int_to_words(thousand)} thousand"
        return prefix if rem == 0 else f"{prefix} {int_to_words(rem)}"
    raise ValueError(f"Integer {n} is too large for simple spoken conversion.")


def to_spoken(val: Any) -> str:
    """
    Translates exact mathematical values and expressions to spoken English.
    Supports:
      - Integers (e.g. 2 -> 'two', -3 -> 'minus three')
      - Simple fractions (e.g. 1/2 -> 'one half', 3/4 -> 'three quarters', -2/3 -> 'minus two thirds')
      - Simple powers (e.g. x**2 -> 'x squared', x**3 -> 'x cubed', x**n -> 'x to the n', x**4 -> 'x to the four')
    Raises ValueError for unsupported shapes (no guessing).
    """
    if val is None:
        raise ValueError("Cannot convert None to spoken English.")

    # 1. Python primitive ints
    if isinstance(val, int) and not isinstance(val, bool):
        return int_to_words(val)

    # 2. Convert to SymPy object if needed
    if isinstance(val, (int, float, str)):
        if isinstance(val, str):
            # Try plain int first
            try:
                int_v = int(val.strip())
                return int_to_words(int_v)
            except ValueError:
                pass
            sym_obj = safe_parse(val)
        elif isinstance(val, float):
            sym_obj = sp.nsimplify(val)
        else:
            sym_obj = sp.sympify(val)
    elif isinstance(val, sp.Basic):
        sym_obj = val
    else:
        raise ValueError(f"Unsupported object type for spoken conversion: {type(val)} ({val})")

    # 3. Handle SymPy Integers
    if sym_obj.is_Integer:
        return int_to_words(int(sym_obj))

    # 4. Handle SymPy Rational (fractions)
    if sym_obj.is_Rational:
        num = int(sym_obj.p)
        den = int(sym_obj.q)
        is_neg = num < 0
        abs_num = abs(num)

        if den in _ORDINAL_DENOMINATORS:
            singular, plural = _ORDINAL_DENOMINATORS[den]
            num_words = int_to_words(abs_num)
            unit_word = singular if abs_num == 1 else plural
            spoken_frac = f"{num_words} {unit_word}"
        else:
            num_words = int_to_words(abs_num)
            den_words = int_to_words(den)
            spoken_frac = f"{num_words} over {den_words}"

        return f"minus {spoken_frac}" if is_neg else spoken_frac

    # 5. Handle SymPy Pow (simple powers)
    if sym_obj.is_Pow:
        base, exp = sym_obj.as_base_exp()
        base_str = str(base)

        if exp == 2:
            return f"{base_str} squared"
        if exp == 3:
            return f"{base_str} cubed"
        if exp.is_Integer:
            exp_int = int(exp)
            if exp_int > 0:
                return f"{base_str} to the {int_to_words(exp_int)}"
            else:
                return f"{base_str} to the minus {int_to_words(abs(exp_int))}"
        if exp.is_Symbol:
            return f"{base_str} to the {str(exp)}"

    # 6. Handle single symbol
    if sym_obj.is_Symbol:
        return str(sym_obj)

    # 7. Unsupported complex shape
    raise ValueError(f"Unsupported math shape for spoken conversion: {sym_obj}")


_PLACEHOLDER_REGEX = re.compile(r"\{\{\s*([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)?)\s*\}\}")


def resolve_placeholders(text: str, facts: Any, mode: str = "spoken") -> str:
    """
    Resolves placeholders of the form {{claim_id.field}} or {{claim_id}} in text.
    
    Arguments:
        text: Narration or string containing placeholders.
        facts: Facts container instance.
        mode: 'spoken' (for TTS audio and captions) or 'latex' (for visual/math display).
    
    Returns:
        String with all placeholders resolved.
    """
    if not text:
        return ""

    def _replace_match(match: re.Match) -> str:
        key = match.group(1)
        if mode == "spoken":
            return facts.spoken(key)
        elif mode == "latex":
            return facts.latex(key)
        else:
            raise ValueError(f"Unknown resolution mode: '{mode}'. Must be 'spoken' or 'latex'.")

    return _PLACEHOLDER_REGEX.sub(_replace_match, text)
