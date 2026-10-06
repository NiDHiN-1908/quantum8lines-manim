# Math Engine & Truth Verification

Follows **SPEC.md Section 7** and **Section 5.3**.

The Quantum8Lines math engine enforces mathematical accuracy across all animations. Scenes never invent or compute numbers; they query verified values from `Facts`. If a claim is mathematically false or unverifiable, attempting to use its values raises an `UnverifiedClaimError`, preventing incorrect math from rendering on screen.

---

## 1. Core Architecture

- **`core.mathengine.schemas`**: Pydantic models for individual claims (`Claim`) and the top-level dataset (`FactsData`).
- **`core.mathengine.checkers`**: Pure mathematical claim checkers powered by SymPy symbolic and exact rational arithmetic. Checkers never raise exceptions on false claims; they return status `"failed"` with human-readable diagnostic messages.
- **`core.mathengine.facts`**: The `Facts` runtime container, providing loading, saving, verification passes, and gatekeeper enforcement via `require_verified(claim_id)`.

---

## 2. Claim Structure & Lifecycle

Each claim is represented by the `Claim` model:

```json
{
  "id": "c1",
  "type": "eigenpair",
  "inputs": {
    "matrix": [[2, 1], [0, 3]],
    "vector": [1, 1],
    "eigenvalue": 3
  },
  "status": "verified",
  "reason": null
}
```

### Claim Statuses

1. `"verified"`: Claim was verified mathematically by SymPy.
2. `"failed"`: Claim is mathematically false (e.g., $Av \ne \lambda v$ or derivative incorrect).
3. `"unverifiable"`: Inputs were malformed, incomplete, or the computation could not be determined.

---

## 3. Claim Types & Checkers

| Claim Type | Inputs | Verification Method | Example / Seeded Error Caught |
|---|---|---|---|
| `equation_true` | `lhs`, `rhs` (or `equation`) | Symbolic simplification of `lhs - rhs == 0` | `"sin(x)**2 + cos(x)**2 = 1"` |
| `solution_set` | `equation`, `variable`, `solutions` | Exact symbolic solving via `sympy.solve` | `x**2 - 9 = 0` requires `[-3, 3]`; claiming `[3]` fails |
| `eigenpair` | `matrix`, `vector`, `eigenvalue` | Exact rational verification $A v = \lambda v$ | $A=\begin{pmatrix}2&1\\0&3\end{pmatrix}, v=\begin{pmatrix}1\\0\end{pmatrix}, \lambda=3 \implies$ **failed** |
| `intersection` | `curves`, `points`, `variables` | Simultaneous system solution | $y=x^2, y=4$ claiming only $x=2 \implies$ **failed** (misses $x=-2$) |
| `derivative` | `expression`, `variable`, `derivative`, `order` | Exact symbolic differentiation | $\frac{d}{dx}(x^3)$ claiming $2x^2 \implies$ **failed** |
| `integral` | `expression`, `variable`, `integral`, `limits` | Symbolic definite/indefinite integration | $\int 3x^2 dx = x^3$ |
| `value_at` | `expression`, `point` / `subs`, `value` | Exact rational evaluation | $f(x)=x^2+1$ at $x=3$ claiming $11 \implies$ **failed** |
| `plot_matches` | `expression`, `function`, `domain`, `tolerance` | Numerical sampling against SymPy reference callable | Compares plotted samples to SymPy within tolerance (e.g. $10^{-4}$) |

---

## 4. `Facts` & Enforcement

```python
from core.mathengine import Facts, UnverifiedClaimError

facts = Facts.load("topics/eigenvectors/chapters/ch01/facts.json")

# This succeeds only if claim 'c1' is verified
c1_data = facts.require_verified("c1")

# If claim 'c_bad' has status 'failed' or 'unverifiable', this raises UnverifiedClaimError:
try:
    bad_data = facts.require_verified("c_bad")
except UnverifiedClaimError as e:
    print(f"Blocked unverified claim: {e}")
```

This guarantees that scene scripts cannot construct visuals with unverified parameters.
