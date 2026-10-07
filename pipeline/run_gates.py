"""
Gate Runner CLI for Quantum8Lines pipeline (SPEC.md Section 9 & Milestone M4b).
Runs gates in order: G1 -> G2 -> G4 -> test render -> G5 -> G6 -> G7.
Stops at the first failed gate, writes qa/report.json and status.json,
prints a readable summary, and records G3 and G8 as 'needs_human'.
Exit code 0 on pass, 1 on failure.

Usage:
    uv run python -m pipeline.run_gates topics/<topic>/chapters/<ch> [--layout 169|916|both]
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional, Tuple, Union

from core.layout import Layout, LAYOUT_169, LAYOUT_916
from pipeline.gates.models import Check, GateConfig, GateResult
from pipeline.gates.g1_script import run_g1_script
from pipeline.gates.g2_math import run_g2_math
from pipeline.gates.g4_code import run_g4_code
from pipeline.gates.g5_render import run_g5_render
from pipeline.gates.g6_visual import run_g6_visual
from pipeline.gates.g7_audio import run_g7_audio
from pipeline.render import render_chapter, RenderResult
from pipeline.status import (
    load_status,
    save_status,
    save_qa_report,
    update_stage_status,
)


def format_gate_summary_table(
    gate_results: List[GateResult],
    overall_passed: bool,
    chapter_dir: Path,
) -> str:
    """Format an ANSI-styled or clean text summary table of gate results."""
    lines = []
    bar = "=" * 80
    sep = "-" * 80
    lines.append(bar)
    lines.append(f"{'QUANTUM8LINES QUALITY GATES SUMMARY':^80}")
    lines.append(f"{'Chapter: ' + str(chapter_dir):^80}")
    lines.append(bar)
    lines.append(f"{'Gate':<10} {'Status':<12} {'Checks':<10} {'Summary / First Failure'}")
    lines.append(sep)

    for gr in gate_results:
        total = len(gr.checks)
        passed = sum(1 for c in gr.checks if c.passed)
        status_str = "PASSED" if gr.passed else "FAILED"
        ratio_str = f"{passed}/{total}"

        # Find summary message
        first_failure = next((c.message for c in gr.checks if not c.passed), None)
        msg = first_failure if first_failure else (gr.checks[0].message if gr.checks else "OK")
        if len(msg) > 46:
            msg = msg[:43] + "..."

        lines.append(f"{gr.gate_id:<10} {status_str:<12} {ratio_str:<10} {msg}")

    # Display pending human gates
    lines.append(sep)
    lines.append(f"{'G3':<10} {'NEEDS_HUMAN':<12} {'---':<10} Plan review: script & storyboard approval required")
    lines.append(f"{'G8':<10} {'NEEDS_HUMAN':<12} {'---':<10} Final review: dual-layout render approval required")
    lines.append(bar)

    if overall_passed:
        lines.append("OVERALL RESULT: PASSED (All automated gates passed cleanly)")
    else:
        lines.append("OVERALL RESULT: FAILED (Execution halted at first failing gate)")
    lines.append(f"Report: {chapter_dir / 'qa' / 'report.json'}")
    lines.append(f"Status: {chapter_dir / 'status.json'}")
    lines.append(bar)
    return "\n".join(lines)


def update_status_records(
    chapter_dir: Path,
    gate_results: List[GateResult],
    overall_passed: bool,
) -> None:
    """Update status.json with stage statuses and gate statuses including G3 & G8 needs_human."""
    status_data = load_status(chapter_dir)
    gates_dict = status_data.setdefault("gates", {})

    # Map gates to status.json stages
    gate_stage_map = {
        "G1": "script",
        "G2": "verify",
        "G4": "code",
        "G5": "test_render",
        "G5_169": "test_render",
        "G5_916": "test_render",
        "G6": "qa_visual",
        "G6_169": "qa_visual",
        "G6_916": "qa_visual",
        "G7": "mix",
    }

    for gr in gate_results:
        gates_dict[gr.gate_id] = "passed" if gr.passed else "failed"
        stage_name = gate_stage_map.get(gr.gate_id)
        if stage_name and stage_name in status_data.get("stages", {}):
            status_data["stages"][stage_name]["status"] = "passed" if gr.passed else "failed"

    # Summarize base gate names G5 and G6
    g5_gates = [gr for gr in gate_results if gr.gate_id.startswith("G5")]
    if g5_gates:
        gates_dict["G5"] = "passed" if all(g.passed for g in g5_gates) else "failed"

    g6_gates = [gr for gr in gate_results if gr.gate_id.startswith("G6")]
    if g6_gates:
        gates_dict["G6"] = "passed" if all(g.passed for g in g6_gates) else "failed"

    # G3 and G8 are always recorded as needs_human
    gates_dict["G3"] = "needs_human"
    gates_dict["G8"] = "needs_human"
    if "storyboard" in status_data.get("stages", {}):
        if status_data["stages"]["storyboard"]["status"] == "pending":
            status_data["stages"]["storyboard"]["status"] = "needs_human"
    if "review" in status_data.get("stages", {}):
        status_data["stages"]["review"]["status"] = "needs_human"

    save_status(chapter_dir, status_data)


def run_pipeline_gates(
    chapter_dir: Union[str, Path],
    layout: str = "both",
    config: Optional[GateConfig] = None,
) -> Tuple[bool, List[GateResult]]:
    """
    Run gates G1, G2, G4, test renders, G5, G6, G7 in sequence.
    Halts at the first failed gate.
    Returns (overall_passed, list_of_executed_gate_results).
    """
    ch_path = Path(chapter_dir).resolve()
    cfg = config or GateConfig()
    results: List[Check] = []
    gate_results: List[GateResult] = []

    # 1. Gate G1: Script
    g1 = run_g1_script(chapter_dir=ch_path, config=cfg)
    gate_results.append(g1)
    if not g1.passed:
        save_qa_report(ch_path, gate_results)
        update_status_records(ch_path, gate_results, overall_passed=False)
        return False, gate_results

    # 2. Gate G2: Math
    g2 = run_g2_math(chapter_dir=ch_path, config=cfg)
    gate_results.append(g2)
    if not g2.passed:
        save_qa_report(ch_path, gate_results)
        update_status_records(ch_path, gate_results, overall_passed=False)
        return False, gate_results

    # 3. Gate G4: Code
    g4 = run_g4_code(chapter_dir=ch_path, config=cfg)
    gate_results.append(g4)
    if not g4.passed:
        save_qa_report(ch_path, gate_results)
        update_status_records(ch_path, gate_results, overall_passed=False)
        return False, gate_results

    # 4. Determine layouts for render and visual checks
    target_layouts: List[Layout] = []
    if layout in ("169", "16:9"):
        target_layouts = [LAYOUT_169]
    elif layout in ("916", "9:16"):
        target_layouts = [LAYOUT_916]
    else:  # "both"
        target_layouts = [LAYOUT_169, LAYOUT_916]

    # 5. Render test quality and run G5, G6 per layout
    for ly in target_layouts:
        slug = ly.slug
        # Test render
        render_res = render_chapter(ch_path, layout=ly, quality="test")

        # G5 Render Check
        g5 = run_g5_render(
            chapter_dir=ch_path,
            render_result=render_res,
            layout=ly,
            quality="test",
            config=cfg,
            gate_id=f"G5_{slug}",
        )
        gate_results.append(g5)
        if not g5.passed:
            save_qa_report(ch_path, gate_results)
            update_status_records(ch_path, gate_results, overall_passed=False)
            return False, gate_results

        # G6 Visual Check
        g6 = run_g6_visual(
            chapter_dir=ch_path,
            layout=ly,
            config=cfg,
            gate_id=f"G6_{slug}",
        )
        gate_results.append(g6)
        if not g6.passed:
            save_qa_report(ch_path, gate_results)
            update_status_records(ch_path, gate_results, overall_passed=False)
            return False, gate_results

    # 6. Gate G7: Audio Verification
    g7 = run_g7_audio(chapter_dir=ch_path, config=cfg)
    gate_results.append(g7)
    if not g7.passed:
        save_qa_report(ch_path, gate_results)
        update_status_records(ch_path, gate_results, overall_passed=False)
        return False, gate_results

    # All executed gates passed!
    save_qa_report(ch_path, gate_results)
    update_status_records(ch_path, gate_results, overall_passed=True)
    return True, gate_results


def main():
    parser = argparse.ArgumentParser(
        description="Run Quantum8Lines quality gates (G1, G2, G4, G5, G6, G7) on a chapter."
    )
    parser.add_argument(
        "chapter_dir",
        type=str,
        help="Path to the chapter directory (e.g. topics/<topic>/chapters/<ch>)",
    )
    parser.add_argument(
        "--layout",
        type=str,
        default="both",
        choices=["169", "916", "both"],
        help="Layout to evaluate ('169', '916', or 'both'). Default: both.",
    )
    args = parser.parse_args()

    chapter_path = Path(args.chapter_dir).resolve()
    if not chapter_path.exists():
        print(f"Error: Chapter directory does not exist: {chapter_path}", file=sys.stderr)
        sys.exit(1)

    passed, results = run_pipeline_gates(chapter_path, layout=args.layout)
    table_str = format_gate_summary_table(results, overall_passed=passed, chapter_dir=chapter_path)
    print(table_str)

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
