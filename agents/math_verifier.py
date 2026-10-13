"""
Math Verifier stage (Code only, NO LLM).
Follows SPEC.md Sections 5.3, 6, 7, and Milestone M5a.

Turns claim specifications proposed by the Scriptwriter into facts.json
using core.mathengine checkers and safe_parse.
Computes deterministic values without LLM involvement.
"""

from pathlib import Path
from typing import Any, Dict, List, Union, Optional
import sympy as sp

from core.mathengine.facts import Facts
from core.mathengine.schemas import Claim
from core.mathengine.checkers import verify_claim
from core.mathengine.safe_parse import safe_parse
from agents.schemas import ClaimSpec


def evaluate_and_verify_claims(
    claim_specs: List[Union[ClaimSpec, Dict[str, Any]]]
) -> Facts:
    """
    Takes claim specifications (symbolic inputs only, NO computed values)
    and computes exact mathematical values, then runs mathengine checkers.
    Returns a populated Facts container.
    """
    facts = Facts()

    for item in claim_specs:
        if isinstance(item, ClaimSpec):
            spec_dict = item.model_dump(exclude_none=True)
        else:
            spec_dict = dict(item)

        cid = spec_dict.get("id", "c1")
        ctype = spec_dict.get("type", "equation_true")

        # Gather inputs dict
        inputs: Dict[str, Any] = dict(spec_dict.get("inputs") or {})
        for k, v in spec_dict.items():
            if k not in ("id", "type", "inputs") and v is not None:
                inputs[k] = v

        # -------------------------------------------------------------
        # Compute exact values based on claim type
        # -------------------------------------------------------------
        if ctype == "eigenpair":
            # Compute eigenvalue if not already provided
            matrix_raw = inputs.get("matrix")
            vector_raw = inputs.get("vector")
            if matrix_raw is not None and vector_raw is not None:
                try:
                    A = sp.Matrix([[sp.nsimplify(x) for x in row] for row in matrix_raw])
                    v = sp.Matrix([sp.nsimplify(x) for x in vector_raw])
                    Av = A * v
                    # Check collinearity
                    if not v.is_zero_matrix and A.shape[1] == v.shape[0]:
                        # Find first non-zero component of v
                        for i in range(v.shape[0]):
                            if v[i] != 0:
                                lam = sp.nsimplify(Av[i] / v[i])
                                if sp.simplify(Av - lam * v).is_zero_matrix:
                                    # Exact eigenpair
                                    val = int(lam) if lam.is_integer else lam
                                    inputs["value"] = val
                                    inputs["eigenvalue"] = val
                                break
                except Exception:
                    pass

        elif ctype == "derivative":
            expr_raw = inputs.get("expression")
            var_name = inputs.get("variable", "x")
            order = inputs.get("order", 1)
            if expr_raw is not None:
                try:
                    var = sp.Symbol(var_name)
                    expr = safe_parse(expr_raw)
                    actual = sp.diff(expr, var, order)
                    inputs["derivative"] = str(actual)
                    inputs["value"] = str(actual)
                except Exception:
                    pass

        elif ctype == "integral":
            expr_raw = inputs.get("expression")
            var_name = inputs.get("variable", "x")
            limits = inputs.get("limits")
            if expr_raw is not None:
                try:
                    var = sp.Symbol(var_name)
                    expr = safe_parse(expr_raw)
                    if limits:
                        actual = sp.integrate(expr, (var, safe_parse(limits[0]), safe_parse(limits[1])))
                        val = int(actual) if getattr(actual, "is_integer", False) else actual
                        inputs["integral"] = val
                        inputs["value"] = val
                    else:
                        actual = sp.integrate(expr, var)
                        inputs["integral"] = str(actual)
                        inputs["value"] = str(actual)
                except Exception:
                    pass

        elif ctype == "value_at":
            expr_raw = inputs.get("expression")
            subs_raw = inputs.get("point") or inputs.get("at") or inputs.get("subs")
            if expr_raw is not None and subs_raw is not None:
                try:
                    expr = safe_parse(expr_raw)
                    if isinstance(subs_raw, dict):
                        subs_dict = {sp.Symbol(k): safe_parse(v) for k, v in subs_raw.items()}
                    else:
                        var_name = inputs.get("variable", "x")
                        subs_dict = {sp.Symbol(var_name): safe_parse(subs_raw)}
                    actual = sp.nsimplify(expr.subs(subs_dict))
                    val = int(actual) if getattr(actual, "is_integer", False) else actual
                    inputs["value"] = val
                except Exception:
                    pass

        elif ctype == "solution_set":
            eq_raw = inputs.get("equation") or (inputs.get("lhs"), inputs.get("rhs"))
            var_name = inputs.get("variable", "x")
            if eq_raw:
                try:
                    var = sp.Symbol(var_name)
                    if isinstance(eq_raw, tuple):
                        eq = safe_parse(eq_raw[0]) - safe_parse(eq_raw[1])
                    else:
                        eq = safe_parse(str(eq_raw))
                    sols = sp.solve(eq, var)
                    inputs["solutions"] = [int(s) if getattr(s, "is_integer", False) else s for s in sols]
                except Exception:
                    pass

        # Build claim and run verification
        claim = Claim(id=cid, type=ctype, inputs=inputs)
        verify_claim(claim)
        facts.add_claim(claim)

        # Record primary value in facts.values if scalar/matrix present
        if "value" in inputs:
            facts.set_value(cid, inputs["value"])
        elif "matrix" in inputs:
            facts.set_value(f"{cid}_matrix", inputs["matrix"])

    return facts
