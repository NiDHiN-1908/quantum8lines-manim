"""
Quality Gate G1: Script Verification (SPEC.md Section 9).
Validates schema, unique line IDs, allowed beats, allowed cuts, word count,
canonical beat progression, and claim references against facts.json.
"""

import difflib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Union

from pipeline.gates.models import Check, GateConfig, GateResult


def simple_stem(word: str) -> str:
    """Simple rule-based suffix stemmer for English content terms."""
    w = word.lower()
    for suffix in ("ing", "tion", "tions", "ies", "es", "ed", "ly", "s"):
        if w.endswith(suffix) and len(w) > len(suffix) + 2:
            return w[: -len(suffix)]
    return w


def load_prompt_example_lines(prompts_file: Optional[Union[str, Path]] = None) -> List[str]:
    """
    Extracts example narration lines from agents/scriptwriter.md.
    """
    path = Path(prompts_file) if prompts_file else Path("agents/scriptwriter.md")
    if not path.is_file():
        return [
            "Can a matrix transform the entire coordinate grid while leaving a special line completely unmoved?",
            "What if a matrix could transform space while keeping certain special directions completely unchanged? This is the central question of linear algebra.",
            "Imagine applying a transformation to every vector in the coordinate plane. Most vectors will rotate and stretch away from their initial orientation.",
            "However, along special lines through the origin, vectors only get scaled by a numerical factor rather than knocked off their span.",
            "This scaling factor is the eigenvalue of {{c1.value}}, and the span that preserves direction is the eigenspace. Everything falls into place naturally.",
            "Mastering these invariant directions unlocks quantum mechanics, data science, and vibrational physics. Join us as we explore the geometric landscape.",
            "Look closely at any smooth curve on your screen. If you zoom in far enough, the bend disappears and looks like a flat straight line.",
            "We start with a secant line connecting two distinct points. It measures the average rate of change across that entire interval.",
            "Now slide the second point closer and closer to the first. As the gap vanishes, the secant tilts toward a unique limiting direction.",
            "At that exact instant, the line becomes a tangent, and its slope equals the instantaneous derivative of {{c1.value}}.",
            "This single idea lets us measure changing speeds, track rocket trajectories, and find optimal peaks across all of mathematics.",
        ]
    content = path.read_text(encoding="utf-8")
    lines: List[str] = []
    for match in re.finditer(r'"text":\s*"([^"]+)"', content):
        line_val = match.group(1).strip()
        if line_val:
            lines.append(line_val)
    return lines


def run_g1_script(
    chapter_dir: Optional[Union[str, Path]] = None,
    script_data: Optional[Dict[str, Any]] = None,
    facts_data: Optional[Dict[str, Any]] = None,
    config: Optional[GateConfig] = None,
    chapter_data: Optional[Dict[str, Any]] = None,
    bible_data: Optional[Dict[str, Any]] = None,
) -> GateResult:
    """
    Execute Gate G1 checks on script data.
    """
    cfg = config or GateConfig()
    checks: List[Check] = []

    # 1. Resolve script_data, facts_data, bible_data, chapter_data from chapter_dir if needed
    if chapter_dir is not None:
        ch_p = Path(chapter_dir)
        if script_data is None:
            script_file = ch_p / "script.json"
            if script_file.exists():
                with open(script_file, "r", encoding="utf-8") as f:
                    script_data = json.load(f)

        if facts_data is None:
            facts_file = ch_p / "facts.json"
            if facts_file.exists():
                with open(facts_file, "r", encoding="utf-8") as f:
                    facts_data = json.load(f)

        if bible_data is None:
            for cand in (ch_p / "bible.json", ch_p.parent / "bible.json", ch_p.parent.parent / "bible.json"):
                if cand.is_file():
                    try:
                        with open(cand, "r", encoding="utf-8") as f:
                            bible_data = json.load(f)
                        break
                    except Exception:
                        pass

    if chapter_data is None and bible_data is not None and script_data is not None:
        ch_id = script_data.get("chapter") or (Path(chapter_dir).name if chapter_dir else "")
        for ch in bible_data.get("chapters", []):
            if ch.get("id") == ch_id:
                chapter_data = ch
                break

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

    # 11. Math lines have claims (G1j_math_lines_have_claims)
    math_lines_missing_claims = []
    for line in lines:
        beat = line.get("beat")
        if beat in ("build", "aha"):
            claims = line.get("claims", [])
            has_claims = isinstance(claims, list) and len(claims) > 0
            no_math = bool(line.get("no_math", False))
            if not has_claims and not no_math:
                math_lines_missing_claims.append(str(line.get("id", "")))

    g1j_passed = len(math_lines_missing_claims) == 0
    checks.append(
        Check(
            id="G1j_math_lines_have_claims",
            passed=g1j_passed,
            severity="error",
            message="All build and aha lines reference at least one claim or specify no_math: true."
            if g1j_passed
            else f"Line(s) {math_lines_missing_claims} with beat 'build' or 'aha' must list at least one claim ID or carry 'no_math': true.",
            details={"missing_math_claim_lines": math_lines_missing_claims}
            if math_lines_missing_claims
            else None,
        )
    )

    # 12. No meta-text or unresolved placeholder delimiters (G1k_no_meta_text)
    meta_errs = []
    for line in lines:
        lid = str(line.get("id", ""))
        text = str(line.get("text", ""))
        for bw in cfg.banned_meta_words:
            if re.search(r"\b" + re.escape(bw) + r"\b", text, re.IGNORECASE):
                meta_errs.append(f"Line {lid} contains banned meta term '{bw}'")
        clean_delims = re.sub(r"\{\{\s*[a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)?\s*\}\}", "", text)
        if "{{" in clean_delims or "}}" in clean_delims:
            meta_errs.append(f"Line {lid} contains unresolved placeholder delimiters '{{{{' or '}}}}'")

    checks.append(
        Check(
            id="G1k_no_meta_text",
            passed=len(meta_errs) == 0,
            severity="error",
            message="No meta-text or unresolved placeholder delimiters detected in narration."
            if len(meta_errs) == 0
            else f"Meta-text violations detected: {'; '.join(meta_errs[:3])}",
            details={"errors": meta_errs} if meta_errs else None,
        )
    )

    # 13. No prompt echo (G1k2_no_prompt_echo)
    example_lines = load_prompt_example_lines()
    echo_errs = []

    for line in lines:
        lid = str(line.get("id", ""))
        text = str(line.get("text", "")).strip()
        text_lower = text.lower()
        line_words = re.findall(r"\b\w+\b", text_lower)

        for ex in example_lines:
            ex_clean = ex.strip()
            ex_lower = ex_clean.lower()
            ex_words = re.findall(r"\b\w+\b", ex_lower)

            ratio = difflib.SequenceMatcher(None, text_lower, ex_lower).ratio()
            if ratio >= cfg.prompt_echo_ratio_threshold:
                echo_errs.append(
                    f"Line {lid} has difflib ratio {ratio:.2f} >= {cfg.prompt_echo_ratio_threshold} with prompt example '{ex_clean[:40]}...'"
                )
                break

            if len(line_words) >= cfg.prompt_echo_ngram_len and len(ex_words) >= cfg.prompt_echo_ngram_len:
                has_run = False
                for i in range(len(line_words) - cfg.prompt_echo_ngram_len + 1):
                    ngram = tuple(line_words[i : i + cfg.prompt_echo_ngram_len])
                    for j in range(len(ex_words) - cfg.prompt_echo_ngram_len + 1):
                        if ngram == tuple(ex_words[j : j + cfg.prompt_echo_ngram_len]):
                            echo_errs.append(
                                f"Line {lid} shares a 6-word run '{' '.join(ngram)}' with prompt example '{ex_clean[:40]}...'"
                            )
                            has_run = True
                            break
                    if has_run:
                        break
                if has_run:
                    break

    checks.append(
        Check(
            id="G1k2_no_prompt_echo",
            passed=len(echo_errs) == 0,
            severity="error",
            message="No prompt example echoing detected in narration."
            if len(echo_errs) == 0
            else f"Prompt echo detected: {'; '.join(echo_errs[:2])}",
            details={"echo_errors": echo_errs} if echo_errs else None,
        )
    )

    # 14. Line quality (G1n_line_quality)
    quality_errs = []
    seen_texts = {}

    for idx, line in enumerate(lines):
        lid = str(line.get("id", f"idx_{idx}"))
        text = str(line.get("text", "")).strip()
        words = text.split()
        wc = len(words)

        if wc < cfg.min_line_words or wc > cfg.max_line_words:
            quality_errs.append(
                f"Line {lid} word count {wc} outside [{cfg.min_line_words}, {cfg.max_line_words}]."
            )

        if not any(text.endswith(p) for p in cfg.allowed_line_endings):
            quality_errs.append(
                f"Line {lid} does not end with terminal punctuation ({cfg.allowed_line_endings})."
            )

        norm = " ".join(words).lower()
        if norm in seen_texts:
            quality_errs.append(f"Duplicate line detected between {seen_texts[norm]} and {lid}.")
        else:
            seen_texts[norm] = lid

    hook_line = next((l for l in lines if l.get("beat") == "hook"), lines[0])
    hook_text = str(hook_line.get("text", "")).strip()
    is_question = hook_text.endswith("?") or "?" in hook_text
    hook_words = len(hook_text.split())
    if not is_question and hook_words < cfg.min_hook_words:
        quality_errs.append(
            f"Hook line {hook_line.get('id')} must be a question or at least {cfg.min_hook_words} words (found {hook_words} words, non-question)."
        )

    checks.append(
        Check(
            id="G1n_line_quality",
            passed=len(quality_errs) == 0,
            severity="error",
            message="All lines meet length, punctuation, uniqueness, and hook quality standards."
            if len(quality_errs) == 0
            else f"Line quality issues: {'; '.join(quality_errs[:3])}",
            details={"quality_errors": quality_errs} if quality_errs else None,
        )
    )

    # 15. Chapter idea content overlap (G1l_chapter_fit)
    one_idea = None
    if chapter_data is not None:
        one_idea = str(chapter_data.get("one_idea", "")).strip()

    if one_idea:
        raw_words = re.findall(r"\b[a-zA-Z]{3,}\b", one_idea.lower())
        content_words = [w for w in raw_words if w not in cfg.stopwords]
        stemmed_idea = {simple_stem(w) for w in content_words}

        script_full_text = " ".join(str(l.get("text", "")) for l in lines).lower()
        script_words = re.findall(r"\b[a-zA-Z]{3,}\b", script_full_text)
        stemmed_script = {simple_stem(w) for w in script_words if w not in cfg.stopwords}

        overlap = stemmed_idea & stemmed_script
        if len(overlap) == 0:
            checks.append(
                Check(
                    id="G1l_chapter_fit",
                    passed=False,
                    severity="error",
                    message=f"Script content has zero overlap with chapter idea '{one_idea}'.",
                    details={"one_idea": one_idea, "overlap": []},
                )
            )
        elif len(overlap) < 2:
            checks.append(
                Check(
                    id="G1l_chapter_fit",
                    passed=True,
                    severity="warning",
                    message=f"Low content word overlap ({len(overlap)} term: {sorted(overlap)}) with chapter idea '{one_idea}'. Expected >= 2 terms.",
                    details={"one_idea": one_idea, "overlap": sorted(overlap)},
                )
            )
        else:
            checks.append(
                Check(
                    id="G1l_chapter_fit",
                    passed=True,
                    severity="error",
                    message=f"Script aligns with chapter idea ({len(overlap)} matching terms: {sorted(overlap)}).",
                    details={"one_idea": one_idea, "overlap": sorted(overlap)},
                )
            )
    else:
        checks.append(
            Check(
                id="G1l_chapter_fit",
                passed=True,
                severity="error",
                message="No chapter idea provided; skipped fit check.",
            )
        )

    # 16. No future chapter terms (G1m_no_future_terms)
    if bible_data is not None and "chapters" in bible_data:
        chapters = bible_data.get("chapters", [])
        curr_ch_id = script_data.get("chapter") or (chapter_data.get("id") if chapter_data else "")
        curr_idx = -1
        for i, ch in enumerate(chapters):
            if ch.get("id") == curr_ch_id:
                curr_idx = i
                break
        if curr_idx == -1 and chapters:
            curr_idx = 0

        future_terms = []
        for fut_ch in chapters[curr_idx + 1 :]:
            for term in fut_ch.get("new_terms", []):
                if term and isinstance(term, str) and term.strip():
                    future_terms.append((term.strip(), fut_ch.get("id", "")))

        future_term_violations = []
        for term, f_id in future_terms:
            pat = re.compile(r"\b" + re.escape(term) + r"\b", re.IGNORECASE)
            for line in lines:
                if pat.search(str(line.get("text", ""))):
                    future_term_violations.append({
                        "term": term,
                        "future_chapter": f_id,
                        "line_id": str(line.get("id", "")),
                    })

        if future_term_violations:
            terms_found = sorted(set(v["term"] for v in future_term_violations))
            checks.append(
                Check(
                    id="G1m_no_future_terms",
                    passed=False,
                    severity="error",
                    message=f"Script uses term(s) reserved for later chapters: {terms_found}. Early chapters must not introduce future terms.",
                    details={"violations": future_term_violations},
                )
            )
        else:
            checks.append(
                Check(
                    id="G1m_no_future_terms",
                    passed=True,
                    severity="error",
                    message="No terms reserved for future chapters found in script.",
                )
            )
    else:
        checks.append(
            Check(
                id="G1m_no_future_terms",
                passed=True,
                severity="error",
                message="No bible specification provided; skipped future terms check.",
            )
        )

    return GateResult.create("G1", checks)

