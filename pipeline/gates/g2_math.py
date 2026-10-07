"""
Quality Gate G2: Math Verification (SPEC.md Section 9).
Requires 100% of claims in facts.json to have status == 'verified'.
Fails if any claim is failed, unverifiable, or missing verification.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pipeline.gates.models import Check, GateConfig, GateResult


def run_g2_math(
    chapter_dir: Optional[Union[str, Path]] = None,
    facts_data: Optional[Dict[str, Any]] = None,
    config: Optional[GateConfig] = None,
) -> GateResult:
    """
    Execute Gate G2 checks on facts.json / claims data.
    """
    checks: List[Check] = []

    if facts_data is None and chapter_dir is not None:
        facts_file = Path(chapter_dir) / "facts.json"
        if facts_file.exists():
            with open(facts_file, "r", encoding="utf-8") as f:
                facts_data = json.load(f)

    if facts_data is None:
        checks.append(
            Check(
                id="G2_schema",
                passed=False,
                severity="error",
                message="No facts data provided or facts.json not found.",
            )
        )
        return GateResult.create("G2", checks)

    claims = facts_data.get("claims")
    if not isinstance(claims, list):
        checks.append(
            Check(
                id="G2_schema",
                passed=False,
                severity="error",
                message="Top-level 'claims' list is missing in facts.json.",
            )
        )
        return GateResult.create("G2", checks)

    checks.append(
        Check(
            id="G2_schema",
            passed=True,
            severity="error",
            message="Facts schema is valid.",
        )
    )

    unverified_claims = []
    for claim in claims:
        if not isinstance(claim, dict):
            unverified_claims.append({
                "id": "unknown",
                "status": "malformed",
                "reason": "Claim entry is not a dict.",
            })
            continue

        cid = claim.get("id", "unknown")
        status = claim.get("status")
        if status != "verified":
            unverified_claims.append({
                "id": cid,
                "status": status,
                "reason": claim.get("reason", "Status is not 'verified'"),
            })

    total_claims = len(claims)
    all_verified = len(unverified_claims) == 0

    if all_verified:
        msg = f"All {total_claims} claims verified." if total_claims > 0 else "No claims present (trivially verified)."
    else:
        failed_summaries = [
            f"{c['id']} (status: {c['status']}, reason: {c['reason']})"
            for c in unverified_claims[:5]
        ]
        msg = f"{len(unverified_claims)}/{total_claims} claims not verified: {'; '.join(failed_summaries)}"

    checks.append(
        Check(
            id="G2_all_verified",
            passed=all_verified,
            severity="error",
            message=msg,
            details={
                "total_claims": total_claims,
                "unverified_count": len(unverified_claims),
                "unverified_claims": unverified_claims,
            }
            if not all_verified
            else None,
        )
    )

    return GateResult.create("G2", checks)
