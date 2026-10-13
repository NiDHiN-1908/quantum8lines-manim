"""
Quality Gate G1: Script Verification (SPEC.md Section 9).
Validates schema, unique line IDs, allowed beats, allowed cuts, word count,
canonical beat progression, and claim references against facts.json.
"""

import json
import re
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
        existing_claim_ids = set()
        if facts_data is not None:
            existing_claim_ids.update(
                c.get("id")
                for c in facts_data.get("claims", [])
                if isinstance(c, dict) and "id" in c
            )
        # Also check claim_specs proposed within script_data
        claim_specs = script_data.get("claim_specs", [])
        if isinstance(claim_specs, list):
            for cs in claim_specs:
                cid_val = cs.get("id") if isinstance(cs, dict) else getattr(cs, "id", None)
                if cid_val:
                    existing_claim_ids.add(cid_val)

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

    # 9. No raw digits outside placeholders (G1h_no_digits_in_narration)
    lines_with_digits = []
    for line in lines:
        lid = str(line.get("id", ""))
        text = str(line.get("text", ""))
        # Strip placeholders {{...}}
        clean_text = re.sub(r"\{\{.*?\}\}", "", text)
        digits_found = re.findall(r"\d+", clean_text)
        if digits_found:
            lines_with_digits.append({"line_id": lid, "digits": digits_found})

    checks.append(
        Check(
            id="G1h_no_digits_in_narration",
            passed=len(lines_with_digits) == 0,
            severity="error",
            message="No digits found in narration outside placeholders."
            if len(lines_with_digits) == 0
            else f"Digits found outside placeholders in line(s): {[x['line_id'] for x in lines_with_digits]}. Numbers must come from verified claims as {{{{claim_id.field}}}}.",
            details={"lines_with_digits": lines_with_digits} if lines_with_digits else None,
        )
    )

    # 10. Number words outside placeholders (G1i_number_words)
    num_words_list = [
        "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
        "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen",
        "nineteen", "twenty", "hundred", "thousand", "half", "third", "quarter"
    ]
    num_pattern = re.compile(r"\b(" + "|".join(num_words_list) + r")\b", re.IGNORECASE)

    lines_with_words = []
    for line in lines:
        lid = str(line.get("id", ""))
        text = str(line.get("text", ""))
        clean_text = re.sub(r"\{\{.*?\}\}", "", text)
        words_found = num_pattern.findall(clean_text)
        if words_found:
            lines_with_words.append({"line_id": lid, "words": [w.lower() for w in words_found]})

    if lines_with_words:
        checks.append(
            Check(
                id="G1i_number_words",
                passed=True,
                severity="warning",
                message=f"Number words outside placeholders detected in line(s) {[x['line_id'] for x in lines_with_words]}: {lines_with_words}. Review at G3.",
                details={"lines_with_number_words": lines_with_words},
            )
        )
    else:
        checks.append(
            Check(
                id="G1i_number_words",
                passed=True,
                severity="error",
                message="No number words detected in narration outside placeholders.",
            )
        )

    return GateResult.create("G1", checks)

