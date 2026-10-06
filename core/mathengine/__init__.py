"""
Core Math Engine package for Quantum8Lines.
Truth-first computation and verification.
"""

from core.mathengine.schemas import Claim, FactsData, ClaimStatus
from core.mathengine.checkers import (
    CHECKERS,
    verify_claim,
    check_equation_true,
    check_solution_set,
    check_eigenpair,
    check_intersection,
    check_derivative,
    check_integral,
    check_value_at,
    check_plot_matches,
)
from core.mathengine.facts import Facts, UnverifiedClaimError

__all__ = [
    "Claim",
    "FactsData",
    "ClaimStatus",
    "CHECKERS",
    "verify_claim",
    "check_equation_true",
    "check_solution_set",
    "check_eigenpair",
    "check_intersection",
    "check_derivative",
    "check_integral",
    "check_value_at",
    "check_plot_matches",
    "Facts",
    "UnverifiedClaimError",
]
