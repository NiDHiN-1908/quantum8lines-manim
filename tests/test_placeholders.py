"""
Tests for mathematical placeholders, spoken-form generation, and G1 checks (G1h, G1i).
Follows SPEC.md Sections 5.2, 5.3, 7, and Milestone M5a Step 3.
"""

from pathlib import Path
import pytest
import sympy as sp

from core.mathengine.facts import Facts, UnverifiedClaimError
from core.mathengine.placeholders import to_spoken, resolve_placeholders, int_to_words
from pipeline.gates.g1_script import run_g1_script
from pipeline.gates.models import GateConfig


# ============================================================================
# 1. Spoken-Form Table Tests
# ============================================================================

@pytest.mark.parametrize(
    "input_val, expected_spoken",
    [
        # Integers
        (0, "zero"),
        (1, "one"),
        (2, "two"),
        (15, "fifteen"),
        (42, "forty-two"),
        (100, "one hundred"),
        (-1, "minus one"),
        (-5, "minus five"),
        (-42, "minus forty-two"),
        # Fractions
        (sp.Rational(1, 2), "one half"),
        (sp.Rational(-1, 2), "minus one half"),
        (sp.Rational(1, 3), "one third"),
        (sp.Rational(2, 3), "two thirds"),
        (sp.Rational(1, 4), "one quarter"),
        (sp.Rational(3, 4), "three quarters"),
        (sp.Rational(3, 5), "three fifths"),
        (sp.Rational(-2, 3), "minus two thirds"),
        # Powers
        (sp.sympify("x**2"), "x squared"),
        (sp.sympify("x**3"), "x cubed"),
        (sp.sympify("x**4"), "x to the four"),
        (sp.sympify("x**n"), "x to the n"),
        (sp.sympify("v**2"), "v squared"),
    ],
)
def test_spoken_form_table(input_val, expected_spoken):
    """Verify exact translation of integers, fractions, and powers to spoken English."""
    result = to_spoken(input_val)
    # Allow hyphen or space for compound numbers like forty-two / forty two
    assert result.replace("-", " ") == expected_spoken.replace("-", " ")


def test_unsupported_math_shape_raises():
    """Verify that unsupported mathematical shapes raise ValueError without guessing."""
    with pytest.raises(ValueError, match="Unsupported math shape"):
        to_spoken(sp.sin(sp.Symbol("x")))


# ============================================================================
# 2. Facts.spoken and Placeholder Resolution Tests
# ============================================================================

def test_facts_spoken_and_unverified_claim_raises():
    """Verify Facts.spoken retrieves verified values and raises on unverified claims."""
    facts = Facts()
    facts.add_claim({
        "id": "c1",
        "type": "eigenpair",
        "inputs": {"value": 2, "matrix": [[2, 0], [0, 3]], "vector": [1, 0]},
        "status": "verified",
    })
    facts.add_claim({
        "id": "c2_unverified",
        "type": "eigenpair",
        "inputs": {"value": 5, "matrix": [[2, 0], [0, 3]], "vector": [1, 0]},
        "status": "failed",
    })

    # Verified claim succeeds
    assert facts.spoken("c1.value") == "two"
    assert facts.spoken("c1") == "two"

    # Unverified claim raises UnverifiedClaimError
    with pytest.raises(UnverifiedClaimError):
        facts.spoken("c2_unverified.value")

    with pytest.raises(UnverifiedClaimError):
        facts.spoken("c2_unverified")

    # Unknown placeholder raises KeyError
    with pytest.raises(KeyError):
        facts.spoken("nonexistent_claim")


def test_resolve_placeholders_spoken_and_latex():
    """Verify resolve_placeholders in spoken and latex modes."""
    facts = Facts()
    facts.add_claim({
        "id": "c1",
        "type": "eigenpair",
        "inputs": {"value": 2, "matrix": [[2, 0], [0, 3]], "vector": [1, 0]},
        "status": "verified",
    })

    text = "The eigenvalue is {{c1.value}} and v stays on its line."
    spoken = resolve_placeholders(text, facts, mode="spoken")
    assert spoken == "The eigenvalue is two and v stays on its line."

    latex = resolve_placeholders("Matrix is {{c1.matrix}}", facts, mode="latex")
    assert "\\begin{matrix}" in latex


# ============================================================================
# 3. Quality Gate G1 Checks: G1h and G1i
# ============================================================================

def test_g1h_fails_on_digits_outside_placeholders():
    """Verify G1h flags literal digits like 2.7 as errors when outside placeholders."""
    # Line with raw digit 2.7 fails G1h
    script_bad = {
        "chapter": "ch01",
        "lines": [
            {
                "id": "l01",
                "text": "The scale factor reaches 2.7 units across space.",
                "beat": "hook",
                "cut": "both",
            }
        ],
    }
    cfg = GateConfig(min_words=1, max_words=100)
    g1_bad = run_g1_script(script_data=script_bad, config=cfg)
    c_bad = g1_bad.get_check("G1h_no_digits_in_narration")
    assert c_bad is not None
    assert c_bad.passed is False
    assert c_bad.severity == "error"
    assert "l01" in c_bad.message

    # Line with digits inside placeholder {{c1.value}} passes G1h
    script_good = {
        "chapter": "ch01",
        "lines": [
            {
                "id": "l01",
                "text": "The scale factor reaches {{c1.value}} units across space.",
                "beat": "hook",
                "cut": "both",
            }
        ],
    }
    g1_good = run_g1_script(script_data=script_good, config=cfg)
    c_good = g1_good.get_check("G1h_no_digits_in_narration")
    assert c_good is not None
    assert c_good.passed is True


def test_g1i_warns_on_number_words_outside_placeholders():
    """Verify G1i emits a warning listing line id when words like 'two' appear outside placeholders."""
    script_with_word = {
        "chapter": "ch01",
        "lines": [
            {
                "id": "l01",
                "text": "There are two special directions in this coordinate frame.",
                "beat": "hook",
                "cut": "both",
            }
        ],
    }
    cfg = GateConfig(min_words=1, max_words=100)
    g1 = run_g1_script(script_data=script_with_word, config=cfg)
    c_warn = g1.get_check("G1i_number_words")
    assert c_warn is not None
    assert c_warn.passed is True
    assert c_warn.severity == "warning"
    assert "l01" in c_warn.message
    assert "two" in str(c_warn.details).lower()
