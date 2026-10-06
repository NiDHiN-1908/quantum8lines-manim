"""
Unit tests for the Quantum8Lines Math Engine.
Verifies all 8 claim checkers with positive and negative cases,
including required seeded errors, plus Facts require_verified enforcement.
"""

from pathlib import Path
import pytest

from core.mathengine.schemas import Claim, FactsData
from core.mathengine.checkers import (
    check_equation_true,
    check_solution_set,
    check_eigenpair,
    check_intersection,
    check_derivative,
    check_integral,
    check_value_at,
    check_plot_matches,
    verify_claim,
)
from core.mathengine.facts import Facts, UnverifiedClaimError


# ---------------------------------------------------------------------------
# 1. Equation True Checker Tests
# ---------------------------------------------------------------------------

def test_equation_true_positive():
    status, reason = check_equation_true({"lhs": "sin(x)**2 + cos(x)**2", "rhs": "1"})
    assert status == "verified"
    assert reason is None

    status2, _ = check_equation_true({"equation": "(x - 1)*(x + 1) = x**2 - 1"})
    assert status2 == "verified"


def test_equation_true_negative():
    status, reason = check_equation_true({"lhs": "x + 1", "rhs": "x + 2"})
    assert status == "failed"
    assert reason is not None


# ---------------------------------------------------------------------------
# 2. Solution Set Checker Tests
# ---------------------------------------------------------------------------

def test_solution_set_positive():
    status, reason = check_solution_set({
        "equation": "x**2 - 9 = 0",
        "variable": "x",
        "solutions": [-3, 3]
    })
    assert status == "verified"
    assert reason is None


def test_solution_set_negative():
    status, reason = check_solution_set({
        "equation": "x**2 - 9 = 0",
        "variable": "x",
        "solutions": [3]
    })
    assert status == "failed"
    assert "Missing solutions" in reason


# ---------------------------------------------------------------------------
# 3. Eigenpair Checker Tests (Seeded Error)
# ---------------------------------------------------------------------------

def test_eigenpair_positive():
    # Matrix [[2,1],[0,3]] has eigenvector [1, 1] with eigenvalue 3
    # A @ [1, 1]^T = [3, 3]^T = 3 * [1, 1]^T
    status, reason = check_eigenpair({
        "matrix": [[2, 1], [0, 3]],
        "vector": [1, 1],
        "eigenvalue": 3
    })
    assert status == "verified"
    assert reason is None


def test_eigenpair_seeded_error_failed():
    """
    SEEDED ERROR: eigenpair A=[[2,1],[0,3]], v=[1,0], lambda=3 -> failed
    A @ [1,0] = [2,0] != 3 * [1,0] = [3,0]
    """
    status, reason = check_eigenpair({
        "matrix": [[2, 1], [0, 3]],
        "vector": [1, 0],
        "eigenvalue": 3
    })
    assert status == "failed"
    assert "A @ v != λ * v" in reason


# ---------------------------------------------------------------------------
# 4. Intersection Checker Tests (Seeded Error)
# ---------------------------------------------------------------------------

def test_intersection_positive():
    status, reason = check_intersection({
        "curves": ["y = x**2", "y = 4"],
        "points": [[-2, 4], [2, 4]],
        "variables": ["x", "y"]
    })
    assert status == "verified"
    assert reason is None


def test_intersection_seeded_error_failed():
    """
    SEEDED ERROR: intersection of y=x^2 and y=4 reported as only x=2 -> failed
    """
    status, reason = check_intersection({
        "curves": ["y = x**2", "y = 4"],
        "points": [2],
        "variables": ["x", "y"]
    })
    assert status == "failed"
    assert "Missing" in reason or "do not match" in reason


# ---------------------------------------------------------------------------
# 5. Derivative Checker Tests (Seeded Error)
# ---------------------------------------------------------------------------

def test_derivative_positive():
    status, reason = check_derivative({
        "expression": "x**3",
        "variable": "x",
        "derivative": "3*x**2"
    })
    assert status == "verified"
    assert reason is None


def test_derivative_seeded_error_failed():
    """
    SEEDED ERROR: derivative of x^3 reported as 2x^2 -> failed
    """
    status, reason = check_derivative({
        "expression": "x**3",
        "variable": "x",
        "derivative": "2*x**2"
    })
    assert status == "failed"
    assert "Derivative of x**3" in reason


# ---------------------------------------------------------------------------
# 6. Integral Checker Tests
# ---------------------------------------------------------------------------

def test_integral_positive_indefinite():
    status, reason = check_integral({
        "expression": "3*x**2",
        "variable": "x",
        "integral": "x**3"
    })
    assert status == "verified"
    assert reason is None


def test_integral_positive_definite():
    status, reason = check_integral({
        "expression": "2*x",
        "variable": "x",
        "limits": [0, 3],
        "integral": 9
    })
    assert status == "verified"
    assert reason is None


def test_integral_negative():
    status, reason = check_integral({
        "expression": "3*x**2",
        "variable": "x",
        "integral": "x**2"
    })
    assert status == "failed"
    assert "does not match" in reason


# ---------------------------------------------------------------------------
# 7. Value At Checker Tests
# ---------------------------------------------------------------------------

def test_value_at_positive():
    status, reason = check_value_at({
        "expression": "x**2 + 1",
        "point": {"x": 3},
        "value": 10
    })
    assert status == "verified"
    assert reason is None


def test_value_at_negative():
    status, reason = check_value_at({
        "expression": "x**2 + 1",
        "point": {"x": 3},
        "value": 11
    })
    assert status == "failed"
    assert "Value of x**2 + 1" in reason


# ---------------------------------------------------------------------------
# 8. Plot Matches Checker Tests
# ---------------------------------------------------------------------------

def test_plot_matches_positive():
    status, reason = check_plot_matches({
        "expression": "x**2",
        "function": lambda x: x**2,
        "domain": [-2.0, 2.0],
        "tolerance": 1e-4,
        "num_samples": 50
    })
    assert status == "verified"
    assert reason is None


def test_plot_matches_negative():
    # Artificially shift function by 0.05 when tolerance is 1e-4
    status, reason = check_plot_matches({
        "expression": "x**2",
        "function": lambda x: x**2 + 0.05,
        "domain": [-2.0, 2.0],
        "tolerance": 1e-4,
        "num_samples": 50
    })
    assert status == "failed"
    assert "exceeds tolerance" in reason


# ---------------------------------------------------------------------------
# 9. Facts Class and require_verified Enforcement
# ---------------------------------------------------------------------------

def test_facts_save_load_round_trip(tmp_path: Path):
    facts_file = tmp_path / "test_facts.json"
    facts = Facts()
    facts.set_value("A", [[2, 1], [0, 3]])
    facts.add_claim({
        "id": "c1",
        "type": "eigenpair",
        "matrix": [[2, 1], [0, 3]],
        "vector": [1, 1],
        "eigenvalue": 3
    })

    facts.verify_all()
    assert facts.get_claim("c1").status == "verified"

    facts.save(facts_file)
    assert facts_file.exists()

    loaded = Facts.load(facts_file)
    assert loaded.values["A"] == [[2, 1], [0, 3]]
    assert loaded.get_claim("c1").status == "verified"


def test_facts_require_verified_success():
    facts = Facts()
    claim = facts.add_claim({
        "id": "c_valid",
        "type": "derivative",
        "expression": "x**3",
        "derivative": "3*x**2"
    })
    verify_claim(claim)
    assert claim.status == "verified"

    vals = facts.require_verified("c_valid")
    assert vals["expression"] == "x**3"
    assert vals["derivative"] == "3*x**2"


def test_facts_require_verified_raises_on_failed():
    facts = Facts()
    claim = facts.add_claim({
        "id": "c_bad",
        "type": "derivative",
        "expression": "x**3",
        "derivative": "2*x**2"
    })
    verify_claim(claim)
    assert claim.status == "failed"

    with pytest.raises(UnverifiedClaimError) as exc_info:
        facts.require_verified("c_bad")
    assert "status is 'failed'" in str(exc_info.value)


def test_facts_require_verified_raises_on_unverifiable():
    facts = Facts()
    facts.add_claim({
        "id": "c_unverified",
        "type": "derivative",
        "expression": "x**3",
        "derivative": "3*x**2",
        "status": "unverifiable"
    })

    with pytest.raises(UnverifiedClaimError) as exc_info:
        facts.require_verified("c_unverified")
    assert "status is 'unverifiable'" in str(exc_info.value)
