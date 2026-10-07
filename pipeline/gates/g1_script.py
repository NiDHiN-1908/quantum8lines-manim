"""
Quality Gate G1: Script Verification (SPEC.md Section 9).
Validates schema, unique line IDs, allowed beats, allowed cuts, word count,
canonical beat progression, and claim references against facts.json.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pipeline.gates.models import Check, GateConfig, GateResult


def run_g1_script(
    chapter_dir: Optional[Union[str, Path]] = None,
    script_data: Optional[Dict[str, Any]] = None,
    facts_data: Optional[Dict[str, Any]] = None,
    config: Optional[GateConfig] = None,
) -> GateResult:
    """
    Execute Gate G1 checks on script data.
    """
    cfg = config or GateConfig()
    checks: List[Check] = []

    # 1. Resolve script_data and facts_data from chapter_dir if needed
    if script_data is None and chapter_dir is not None:
        script_file = Path(chapter_dir) / "script.json"
        if script_file.exists():
            with open(script_file, "r", encoding="utf-8") as f:
                script_data = json.load(f)

    if facts_data is None and chapter_dir is not None:
        facts_file = Path(chapter_dir) / "facts.json"
        if facts_file.exists():
            with open(facts_file, "r", encoding="utf-8") as f:
                facts_data = json.load(f)

    if script_data is None:
        checks.append(
            Check(
                id="G1_schema",
                passed=False,
                severity="error",
                message="No script data provided or script.json not found.",
            )
        )
        return GateResult.create("G1", checks)

    # 2. Schema check (G1_schema)
    schema_passed = True
    schema_errs = []
    if not isinstance(script_data.get("chapter"), str):
        schema_passed = False
        schema_errs.append("Top-level 'chapter' string is missing.")

    lines = script_data.get("lines")
    if not isinstance(lines, list):
        schema_passed = False
        schema_errs.append("Top-level 'lines' list is missing.")
        lines = []
    else:
        for idx, line in enumerate(lines):
            if not isinstance(line, dict):
                schema_passed = False
                schema_errs.append(f"Line at index {idx} is not an object.")
                continue
            for req_field in ("id", "text", "beat", "cut"):
                if req_field not in line or not isinstance(line[req_field], str):
                    schema_passed = False
                    schema_errs.append(
                        f"Line {line.get('id', f'at index {idx}')} missing or invalid string field '{req_field}'."
                    )

    checks.append(
        Check(
            id="G1_schema",
            passed=schema_passed,
            severity="error",
            message="Script schema is valid."
            if schema_passed
            else f"Script schema invalid: {'; '.join(schema_errs[:3])}",
            details={"errors": schema_errs} if schema_errs else None,
        )
    )

    if not lines:
        return GateResult.create("G1", checks)

    # 3. Unique line IDs (G1_line_ids_unique)
    seen_ids = set()
    dup_ids = set()
    for line in lines:
        lid = line.get("id")
        if lid:
            if lid in seen_ids:
                dup_ids.add(lid)
            seen_ids.add(lid)

    checks.append(
        Check(
            id="G1_line_ids_unique",
            passed=len(dup_ids) == 0,
            severity="error",
            message="All line IDs are unique."
            if len(dup_ids) == 0
            else f"Duplicate line IDs found: {sorted(dup_ids)}",
            details={"duplicate_ids": sorted(dup_ids)} if dup_ids else None,
        )
    )

    # 4. Valid beat names (G1_beat_names)
    invalid_beats = [
        line.get("beat")
        for line in lines
        if line.get("beat") and line.get("beat") not in cfg.allowed_beats
    ]
    checks.append(
        Check(
            id="G1_beat_names",
            passed=len(invalid_beats) == 0,
            severity="error",
            message="All beat names are valid."
            if len(invalid_beats) == 0
            else f"Invalid beat names: {invalid_beats}. Allowed: {cfg.allowed_beats}",
            details={"invalid_beats": invalid_beats} if invalid_beats else None,
        )
    )

    # 5. Valid cut tags (G1_cut_tags)
    invalid_cuts = [
        line.get("cut")
        for line in lines
        if line.get("cut") and line.get("cut") not in cfg.allowed_cuts
    ]
    checks.append(
        Check(
            id="G1_cut_tags",
            passed=len(invalid_cuts) == 0,
            severity="error",
            message="All cut tags are valid."
            if len(invalid_cuts) == 0
            else f"Invalid cut tags: {invalid_cuts}. Allowed: {cfg.allowed_cuts}",
            details={"invalid_cuts": invalid_cuts} if invalid_cuts else None,
        )
    )

    # 6. Total word count (G1_word_count)
    total_words = sum(len(line.get("text", "").split()) for line in lines)
    wc_passed = cfg.min_words <= total_words <= cfg.max_words
    checks.append(
        Check(
            id="G1_word_count",
            passed=wc_passed,
            severity="error",
            message=f"Word count {total_words} is within allowed range [{cfg.min_words}, {cfg.max_words}]."
            if wc_passed
            else f"Word count {total_words} outside allowed range [{cfg.min_words}, {cfg.max_words}].",
            details={
                "total_words": total_words,
                "min_words": cfg.min_words,
                "max_words": cfg.max_words,
            },
        )
    )

    # 7. Beat order progression (G1_beat_order)
    order_passed = True
    order_err = None
    last_idx = -1
    last_beat = None

    for line in lines:
        beat = line.get("beat")
        if beat in cfg.canonical_beat_order:
            curr_idx = cfg.canonical_beat_order.index(beat)
            if curr_idx < last_idx:
                order_passed = False
                order_err = (
                    f"Beat '{beat}' appears after '{last_beat}', violating canonical order {cfg.canonical_beat_order}."
                )
                break
            last_idx = max(last_idx, curr_idx)
            last_beat = beat

    checks.append(
        Check(
            id="G1_beat_order",
            passed=order_passed,
            severity="error",
            message="Beats appear in canonical order."
            if order_passed
            else order_err,
            details={"canonical_order": cfg.canonical_beat_order}
            if not order_passed
            else None,
        )
    )

    # 8. Claim IDs exist in facts.json (G1_claim_ids_exist)
    all_referenced_claims = []
    for line in lines:
        claims = line.get("claims", [])
        if isinstance(claims, list):
            all_referenced_claims.extend(claims)

    missing_claim_ids = []
    if all_referenced_claims:
        if facts_data is None:
            missing_claim_ids = list(all_referenced_claims)
        else:
            existing_claim_ids = {
                c.get("id")
                for c in facts_data.get("claims", [])
                if isinstance(c, dict) and "id" in c
            }
            for cid in all_referenced_claims:
                if cid not in existing_claim_ids:
                    missing_claim_ids.append(cid)

    checks.append(
        Check(
            id="G1_claim_ids_exist",
            passed=len(missing_claim_ids) == 0,
            severity="error",
            message="All referenced claim IDs exist in facts.json."
            if len(missing_claim_ids) == 0
            else f"Referenced claim IDs missing from facts.json: {sorted(set(missing_claim_ids))}",
            details={"missing_claims": sorted(set(missing_claim_ids))}
            if missing_claim_ids
            else None,
        )
    )

    return GateResult.create("G1", checks)
