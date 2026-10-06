"""
Mathematical claim checkers for Quantum8Lines.
Follows SPEC.md section 7:
One checker per claim type: equation_true, solution_set, eigenpair,
intersection, derivative, integral, value_at, plot_matches.

All checkers return (status, reason) where status is:
'verified' | 'failed' | 'unverifiable'.
Checkers NEVER raise for false claims.
"""

from typing import Dict, Any, Tuple, Optional, Callable, List
import sympy as sp
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)
import numpy as np

from core.mathengine.schemas import Claim, ClaimStatus
from core.mathengine.safe_parse import safe_parse, SafeParseError

_safe_parse = safe_parse


def check_equation_true(inputs: Dict[str, Any]) -> Tuple[ClaimStatus, Optional[str]]:
    """
    Verify that an equation holds true by substituting and simplifying with SymPy.
    Inputs can provide:
      - 'lhs' and 'rhs'
      - or 'equation' (e.g. "sin(x)**2 + cos(x)**2 = 1")
    """
    try:
        if "lhs" in inputs and "rhs" in inputs:
            lhs = _safe_parse(inputs["lhs"])
            rhs = _safe_parse(inputs["rhs"])
            diff = sp.simplify(lhs - rhs)
        elif "equation" in inputs:
            eq_str = str(inputs["equation"])
            if "=" in eq_str:
                parts = eq_str.split("=", 1)
                lhs = _safe_parse(parts[0])
                rhs = _safe_parse(parts[1])
                diff = sp.simplify(lhs - rhs)
            else:
                diff = sp.simplify(_safe_parse(eq_str))
        else:
            return "unverifiable", "Missing 'lhs'/'rhs' or 'equation' in inputs."

        if diff == 0:
            return "verified", None
        else:
            return "failed", f"Equation is false. Simplified LHS - RHS = {diff} != 0."
    except Exception as e:
        return "unverifiable", f"Could not verify equation: {str(e)}"


def check_solution_set(inputs: Dict[str, Any]) -> Tuple[ClaimStatus, Optional[str]]:
    """
    Solve an equation symbolically and compare to claimed solution set.
    Inputs:
      - 'equation' or ('lhs' and 'rhs')
      - 'variable': str (e.g. 'x')
      - 'solutions': list of claimed solutions
    """
    try:
        var_name = inputs.get("variable", "x")
        var = sp.Symbol(var_name)

        if "lhs" in inputs and "rhs" in inputs:
            lhs = _safe_parse(inputs["lhs"])
            rhs = _safe_parse(inputs["rhs"])
            eq = lhs - rhs
        elif "equation" in inputs:
            eq = _safe_parse(inputs["equation"])
        else:
            return "unverifiable", "Missing equation in inputs."

        claimed_raw = inputs.get("solutions")
        if claimed_raw is None:
            return "unverifiable", "Missing 'solutions' in inputs."

        if not isinstance(claimed_raw, (list, tuple, set)):
            claimed_raw = [claimed_raw]

        claimed_solutions = [sp.nsimplify(_safe_parse(s)) for s in claimed_raw]

        # Solve symbolically
        actual_solutions = sp.solve(eq, var)
        actual_set = [sp.nsimplify(s) for s in actual_solutions]

        # Check: each actual solution is in claimed, and each claimed is in actual
        missing = [a for a in actual_set if not any(sp.simplify(a - c) == 0 for c in claimed_solutions)]
        extra = [c for c in claimed_solutions if not any(sp.simplify(c - a) == 0 for a in actual_set)]

        if not missing and not extra:
            return "verified", None
        
        reasons = []
        if missing:
            reasons.append(f"Missing solutions: {missing}")
        if extra:
            reasons.append(f"Spurious/extra solutions claimed: {extra}")
        return "failed", "; ".join(reasons)
    except Exception as e:
        return "unverifiable", f"Could not solve equation: {str(e)}"


def check_eigenpair(inputs: Dict[str, Any]) -> Tuple[ClaimStatus, Optional[str]]:
    """
    Verify A @ v == lambda * v exactly (rational arithmetic where possible).
    Inputs:
      - 'matrix': 2D list
      - 'vector': 1D list
      - 'eigenvalue' (or 'value' or 'lambda'): scalar
    """
    try:
        matrix_raw = inputs.get("matrix")
        vector_raw = inputs.get("vector")
        lambda_raw = inputs.get("eigenvalue")
        if lambda_raw is None:
            lambda_raw = inputs.get("value")
        if lambda_raw is None:
            lambda_raw = inputs.get("lambda")

        if matrix_raw is None or vector_raw is None or lambda_raw is None:
            return "unverifiable", "Missing 'matrix', 'vector', or 'eigenvalue' in inputs."

        # Convert to exact SymPy matrices using Rational/nsimplify
        A = sp.Matrix([[sp.nsimplify(x) for x in row] for row in matrix_raw])
        v = sp.Matrix([sp.nsimplify(x) for x in vector_raw])
        lam = sp.nsimplify(lambda_raw)

        # Vector cannot be zero vector
        if v.is_zero_matrix:
            return "failed", "Eigenvector cannot be the zero vector."

        if A.shape[1] != v.shape[0]:
            return "failed", f"Matrix columns ({A.shape[1]}) do not match vector dimension ({v.shape[0]})."

        Av = A * v
        lam_v = lam * v

        diff = sp.simplify(Av - lam_v)
        if diff.is_zero_matrix:
            return "verified", None
        else:
            av_list = [str(x) for x in list(Av)]
            lam_v_list = [str(x) for x in list(lam_v)]
            return "failed", f"A @ v != λ * v. A @ v = {av_list}, but λ * v = {lam_v_list}."
    except Exception as e:
        return "unverifiable", f"Could not verify eigenpair: {str(e)}"


def check_intersection(inputs: Dict[str, Any]) -> Tuple[ClaimStatus, Optional[str]]:
    """
    Solve the system of curves and compare to claimed points.
    Inputs:
      - 'curves': list of equation strings (e.g. ["y = x**2", "y = 4"])
        or 'curve1', 'curve2'
      - 'points': list of claimed points, e.g. [[2, 4], [-2, 4]]
        or list of x values if 1D
      - 'variables': optional list of var names (default ['x', 'y'])
    """
    try:
        curves_raw = inputs.get("curves")
        if not curves_raw:
            if "curve1" in inputs and "curve2" in inputs:
                curves_raw = [inputs["curve1"], inputs["curve2"]]
            else:
                return "unverifiable", "Missing 'curves' in inputs."

        var_names = inputs.get("variables", ["x", "y"])
        syms = [sp.Symbol(v) for v in var_names]

        # Parse curve equations
        equations = []
        for c in curves_raw:
            if "=" in str(c):
                parts = str(c).split("=", 1)
                equations.append(_safe_parse(parts[0]) - _safe_parse(parts[1]))
            else:
                equations.append(_safe_parse(c))

        # Solve system
        solutions = sp.solve(equations, syms, dict=True)
        if not solutions:
            # Try solving for first variable if second variable was an explicit definition
            solutions = sp.solve(equations, dict=True)

        claimed_points = inputs.get("points")
        if claimed_points is None:
            # Also accept 'x_values' or 'solutions'
            claimed_points = inputs.get("x_values") or inputs.get("solutions")
        if claimed_points is None:
            return "unverifiable", "Missing claimed 'points' in inputs."

        if not isinstance(claimed_points, (list, tuple)):
            claimed_points = [claimed_points]

        # Standardize claimed points
        # Case A: claimed points are single coordinates (e.g. only x=2)
        if len(syms) == 2 and solutions and all(isinstance(p, (int, float, sp.Basic)) for p in claimed_points):
            # Check against x coordinates
            actual_x = [sp.nsimplify(sol[syms[0]]) for sol in solutions if syms[0] in sol]
            claimed_x = [sp.nsimplify(p) for p in claimed_points]
            missing = [ax for ax in actual_x if not any(sp.simplify(ax - cx) == 0 for cx in claimed_x)]
            extra = [cx for cx in claimed_x if not any(sp.simplify(cx - ax) == 0 for ax in actual_x)]
            if not missing and not extra:
                return "verified", None
            return "failed", f"Claimed x-coordinates {claimed_points} do not match intersection x-coordinates {actual_x}. Missing: {missing}, Extra: {extra}."

        # Case B: claimed points are (x, y) pairs
        parsed_claimed = []
        for pt in claimed_points:
            if isinstance(pt, dict):
                parsed_claimed.append({sp.Symbol(k): sp.nsimplify(_safe_parse(v)) for k, v in pt.items()})
            elif isinstance(pt, (list, tuple)):
                parsed_claimed.append({syms[i]: sp.nsimplify(_safe_parse(pt[i])) for i in range(len(pt))})
            else:
                parsed_claimed.append({syms[0]: sp.nsimplify(_safe_parse(pt))})

        # Compare actual solutions against parsed_claimed
        missing_sols = []
        for sol in solutions:
            match = False
            for claim in parsed_claimed:
                if all(sp.simplify(sol[k] - claim[k]) == 0 for k in claim if k in sol):
                    match = True
                    break
            if not match:
                missing_sols.append(sol)

        extra_claims = []
        for claim in parsed_claimed:
            match = False
            for sol in solutions:
                if all(sp.simplify(sol[k] - claim[k]) == 0 for k in claim if k in sol):
                    match = True
                    break
            if not match:
                extra_claims.append(claim)

        if not missing_sols and not extra_claims:
            return "verified", None

        reasons = []
        if missing_sols:
            reasons.append(f"Missing intersection points: {missing_sols}")
        if extra_claims:
            reasons.append(f"Spurious claimed points: {extra_claims}")
        return "failed", "; ".join(reasons)
    except Exception as e:
        return "unverifiable", f"Could not solve curve intersection: {str(e)}"


def check_derivative(inputs: Dict[str, Any]) -> Tuple[ClaimStatus, Optional[str]]:
    """
    Differentiate symbolically and compare.
    Inputs:
      - 'expression': str or SymPy expr
      - 'variable': str (default 'x')
      - 'derivative': str or SymPy expr (claimed derivative)
      - 'order': optional int (default 1)
    """
    try:
        expr_raw = inputs.get("expression")
        claimed_raw = inputs.get("derivative")
        var_name = inputs.get("variable", "x")
        order = inputs.get("order", 1)

        if expr_raw is None or claimed_raw is None:
            return "unverifiable", "Missing 'expression' or 'derivative' in inputs."

        var = sp.Symbol(var_name)
        expr = _safe_parse(expr_raw)
        claimed = _safe_parse(claimed_raw)

        actual = sp.diff(expr, var, order)
        diff = sp.simplify(actual - claimed)

        if diff == 0:
            return "verified", None
        else:
            return "failed", f"Derivative of {expr_raw} with respect to {var_name} is {actual}, but claimed {claimed_raw} (diff: {diff})."
    except Exception as e:
        return "unverifiable", f"Could not compute derivative: {str(e)}"


def check_integral(inputs: Dict[str, Any]) -> Tuple[ClaimStatus, Optional[str]]:
    """
    Integrate symbolically and compare.
    Inputs:
      - 'expression': integrand
      - 'variable': integration variable (default 'x')
      - 'integral': claimed integral result
      - 'limits': optional [lower, upper] for definite integral
    """
    try:
        expr_raw = inputs.get("expression")
        claimed_raw = inputs.get("integral")
        var_name = inputs.get("variable", "x")
        limits = inputs.get("limits")

        if expr_raw is None or claimed_raw is None:
            return "unverifiable", "Missing 'expression' or 'integral' in inputs."

        var = sp.Symbol(var_name)
        expr = _safe_parse(expr_raw)

        if limits:
            lower = sp.nsimplify(_safe_parse(limits[0]))
            upper = sp.nsimplify(_safe_parse(limits[1]))
            actual = sp.integrate(expr, (var, lower, upper))
            claimed = sp.nsimplify(_safe_parse(claimed_raw))
            diff = sp.simplify(actual - claimed)
            if diff == 0:
                return "verified", None
            else:
                return "failed", f"Definite integral of {expr_raw} from {lower} to {upper} is {actual}, but claimed {claimed_raw}."
        else:
            # Indefinite integral: test diff(claimed, var) == expr
            claimed = _safe_parse(claimed_raw)
            diff = sp.simplify(sp.diff(claimed, var) - expr)
            if diff == 0:
                return "verified", None
            else:
                return "failed", f"Derivative of claimed integral is {sp.diff(claimed, var)}, which does not match integrand {expr_raw}."
    except Exception as e:
        return "unverifiable", f"Could not compute integral: {str(e)}"


def check_value_at(inputs: Dict[str, Any]) -> Tuple[ClaimStatus, Optional[str]]:
    """
    Evaluate expression at a point using exact substitution.
    Inputs:
      - 'expression': expression string
      - 'point' or 'at' or 'subs': dict of variable substitutions, e.g. {'x': 3}
      - 'value': claimed result
    """
    try:
        expr_raw = inputs.get("expression")
        claimed_raw = inputs.get("value")
        subs_raw = inputs.get("point") or inputs.get("subs") or inputs.get("at")

        if expr_raw is None or claimed_raw is None or subs_raw is None:
            return "unverifiable", "Missing 'expression', 'point', or 'value' in inputs."

        expr = _safe_parse(expr_raw)
        claimed = sp.nsimplify(_safe_parse(claimed_raw))

        if not isinstance(subs_raw, dict):
            # Single variable fallback e.g. at=3
            var_name = inputs.get("variable", "x")
            subs_dict = {sp.Symbol(var_name): sp.nsimplify(_safe_parse(subs_raw))}
        else:
            subs_dict = {sp.Symbol(k): sp.nsimplify(_safe_parse(v)) for k, v in subs_raw.items()}

        actual = sp.nsimplify(expr.subs(subs_dict))
        diff = sp.simplify(actual - claimed)

        if diff == 0:
            return "verified", None
        else:
            return "failed", f"Value of {expr_raw} at {subs_raw} is {actual}, but claimed {claimed_raw}."
    except Exception as e:
        return "unverifiable", f"Could not evaluate expression at point: {str(e)}"


def check_plot_matches(inputs: Dict[str, Any]) -> Tuple[ClaimStatus, Optional[str]]:
    """
    Sample the plotted function and compare to SymPy within tolerance.
    Inputs:
      - 'expression': SymPy expression or string (e.g. 'x**2')
      - 'function': callable or lambdified function
      - 'domain': [x_min, x_max] (default [-5.0, 5.0])
      - 'tolerance': float (default 1e-4)
      - 'num_samples': int (default 100)
    """
    try:
        expr_raw = inputs.get("expression")
        func = inputs.get("function")
        domain = inputs.get("domain", [-5.0, 5.0])
        tolerance = float(inputs.get("tolerance", 1e-4))
        num_samples = int(inputs.get("num_samples", 100))

        if expr_raw is None:
            return "unverifiable", "Missing 'expression' in inputs."

        expr = _safe_parse(expr_raw)
        var_name = inputs.get("variable", "x")
        var = sp.Symbol(var_name)

        # Create reference callable from SymPy
        sym_callable = sp.lambdify(var, expr, modules=["numpy"])

        if func is None:
            # If function not supplied directly, inputs may provide sampled points
            if "samples" in inputs:
                samples = inputs["samples"]
                xs = np.array([s[0] for s in samples], dtype=float)
                ys_plotted = np.array([s[1] for s in samples], dtype=float)
                ys_sympy = np.array([float(sym_callable(x)) for x in xs], dtype=float)
                errs = np.abs(ys_plotted - ys_sympy)
                max_err = float(np.max(errs))
                if max_err <= tolerance:
                    return "verified", None
                idx = int(np.argmax(errs))
                return "failed", f"Plot samples diverge from SymPy: max error {max_err:.6e} at x={xs[idx]:.4f} exceeds tolerance {tolerance}."
            return "unverifiable", "Missing 'function' or 'samples' to verify plot."

        xs = np.linspace(float(domain[0]), float(domain[1]), num_samples)
        try:
            ys_plotted = np.array([float(func(x)) for x in xs], dtype=float)
            ys_sympy = np.array([float(sym_callable(x)) for x in xs], dtype=float)
        except Exception as eval_err:
            return "failed", f"Error evaluating function during sampling: {eval_err}"

        # Handle NaNs or Infs
        invalid_mask = np.isnan(ys_plotted) | np.isnan(ys_sympy) | np.isinf(ys_plotted) | np.isinf(ys_sympy)
        if np.all(invalid_mask):
            return "failed", "All sampled points evaluated to NaN or Inf."

        valid_xs = xs[~invalid_mask]
        valid_plotted = ys_plotted[~invalid_mask]
        valid_sympy = ys_sympy[~invalid_mask]

        errs = np.abs(valid_plotted - valid_sympy)
        max_err = float(np.max(errs))

        if max_err <= tolerance:
            return "verified", None
        else:
            idx = int(np.argmax(errs))
            return "failed", f"Plot diverges from SymPy: max error {max_err:.6e} at x={valid_xs[idx]:.4f} (plotted={valid_plotted[idx]:.4f}, sympy={valid_sympy[idx]:.4f}) exceeds tolerance {tolerance}."
    except Exception as e:
        return "unverifiable", f"Could not verify plot match: {str(e)}"


CHECKERS: Dict[str, Callable[[Dict[str, Any]], Tuple[ClaimStatus, Optional[str]]]] = {
    "equation_true": check_equation_true,
    "solution_set": check_solution_set,
    "eigenpair": check_eigenpair,
    "intersection": check_intersection,
    "derivative": check_derivative,
    "integral": check_integral,
    "value_at": check_value_at,
    "plot_matches": check_plot_matches,
}


def verify_claim(claim: Claim) -> Claim:
    """
    Dispatches claim to the appropriate checker.
    Updates claim.status and claim.reason.
    Never raises an exception for false claims.
    """
    checker = CHECKERS.get(claim.type)
    if not checker:
        claim.status = "unverifiable"
        claim.reason = f"Unknown claim type: '{claim.type}'. Available: {list(CHECKERS.keys())}"
        return claim

    status, reason = checker(claim.inputs)
    claim.status = status
    claim.reason = reason
    return claim
