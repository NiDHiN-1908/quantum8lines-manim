"""
Smoke script executing Curriculum Planner, Scriptwriter, and Math Verifier stages.
Follows Milestone M5a-live Step 4.

Usage:
    python -m agents.smoke --topic "Eigenvectors" \\
        --audience "high school to first-year university" \\
        --chapter 1 \\
        --workdir temp_renders/smoke
"""

import argparse
import json
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional

from agents.runtime import AgentFailure
from agents.stages import plan_topic, write_script, verify_math
from agents.llm.base import LLMProvider
from agents.llm.config import get_role_config, create_provider
from agents.llm.mock import MockProvider
from core.mathengine.facts import Facts
from core.mathengine.placeholders import resolve_placeholders
from pipeline.gates.g1_script import run_g1_script
from pipeline.gates.g2_math import run_g2_math


def ensure_workdir_in_gitignore(workdir: Path) -> None:
    """Ensures the specified workdir is covered by .gitignore."""
    gitignore_path = Path(".gitignore")
    if not gitignore_path.is_file():
        return

    content = gitignore_path.read_text(encoding="utf-8")
    rel_path_str = str(workdir).replace("\\", "/").strip("/") + "/"
    # Check if parent or directory itself is already in gitignore
    first_part = rel_path_str.split("/")[0] + "/"
    if rel_path_str in content or first_part in content:
        return

    # Append to .gitignore
    with open(gitignore_path, "a", encoding="utf-8") as f:
        f.write(f"\n{rel_path_str}\n")


def build_mock_provider() -> MockProvider:
    """Constructs a deterministic MockProvider with valid canned topic and script."""
    canned_bible = json.dumps(
        {
            "topic": "Eigenvectors",
            "audience": "high school to first-year university",
            "arc": "geometric intuition of invariant directions under linear transformations",
            "notation": {"matrix": "A", "vector": "v", "eigenvalue": "lambda"},
            "chapters": [
                {
                    "id": "ch01",
                    "title": "Invariant Directions",
                    "one_idea": "Matrices can transform space while preserving special directions",
                    "question_it_raises": "How do we compute the scaling factor along these invariant directions?",
                },
                {
                    "id": "ch02",
                    "title": "Scaling Factors",
                    "one_idea": "Eigenvalues quantify stretching along invariant directions",
                    "question_it_raises": "How do we find these values without guessing?",
                },
                {
                    "id": "ch03",
                    "title": "The Characteristic Equation",
                    "one_idea": "Setting determinant to zero uncovers eigenvalues",
                    "question_it_raises": "Can every matrix be completely described by its eigenvectors?",
                },
                {
                    "id": "ch04",
                    "title": "Diagonalization and Beyond",
                    "one_idea": "Decoupling systems into independent eigen-coordinates",
                    "question_it_raises": "Where does this geometric framework apply in the real world?",
                },
            ],
            "prereqs": ["matrix multiplication", "vectors in 2D coordinate space"],
            "voice_profile": "",
            "cast": [],
            "sources": [],
        },
        indent=2,
    )

    canned_script = json.dumps(
        {
            "chapter": "ch01",
            "lines": [
                {
                    "id": "l01",
                    "text": "What if a matrix could transform space while keeping certain special directions completely unchanged? This is the central question of linear algebra.",
                    "beat": "hook",
                    "cut": "both",
                    "claims": ["c1"],
                    "no_math": False,
                },
                {
                    "id": "l02",
                    "text": "Imagine applying a transformation to every vector in the coordinate plane. Most vectors will rotate and stretch away from their initial orientation.",
                    "beat": "setup",
                    "cut": "both",
                    "no_math": True,
                },
                {
                    "id": "l03",
                    "text": "However along special lines through the origin vectors only get scaled by a numerical factor rather than knocked off their span completely.",
                    "beat": "build",
                    "cut": "both",
                    "no_math": True,
                },
                {
                    "id": "l04",
                    "text": "This scaling factor is the eigenvalue of {{c1.value}} and the span that preserves direction is the eigenspace. Everything falls into place naturally.",
                    "beat": "aha",
                    "cut": "both",
                    "claims": ["c1"],
                    "no_math": False,
                },
                {
                    "id": "l05",
                    "text": "Mastering these invariant directions unlocks quantum mechanics data science and vibrational physics. Join us as we explore the geometric landscape.",
                    "beat": "close",
                    "cut": "both",
                    "no_math": True,
                },
            ],
            "claim_specs": [
                {
                    "id": "c1",
                    "type": "eigenpair",
                    "matrix": [[2, 0], [0, 3]],
                    "vector": [1, 0],
                }
            ],
        },
        indent=2,
    )

    return MockProvider(
        responses={
            "curriculum_planner": canned_bible,
            "scriptwriter": canned_script,
        }
    )


def count_agent_attempts(log_dir: Path, agent_name: str) -> int:
    """Counts number of logged attempts for a given agent in log_dir."""
    if not log_dir.is_dir():
        return 1
    attempts = list(log_dir.glob(f"{agent_name}_*.json"))
    return max(1, len(attempts))


def run_smoke(
    topic: str,
    audience: str,
    chapter: int,
    workdir_path: Path,
    provider_override: Optional[str] = None,
) -> int:
    """Runs the three agent stages and prints detailed diagnostics."""
    print("=" * 70)
    print("QUANTUM8LINES AGENT RUNTIME SMOKE TEST")
    print(f"Topic:       {topic}")
    print(f"Audience:    {audience}")
    print(f"Chapter:     {chapter}")
    print(f"Workdir:     {workdir_path}")
    print(f"Provider:    {provider_override or 'Configured (config/llm.json)'}")
    print("=" * 70)

    workdir_path.mkdir(parents=True, exist_ok=True)
    ensure_workdir_in_gitignore(workdir_path)
    log_dir = workdir_path / "agent_logs"

    # Resolve providers
    planner_provider: Optional[LLMProvider] = None
    writer_provider: Optional[LLMProvider] = None

    if provider_override == "mock":
        mock_p = build_mock_provider()
        planner_provider = mock_p
        writer_provider = mock_p
    elif provider_override is not None:
        planner_provider = create_provider(provider_override)
        writer_provider = create_provider(provider_override)

    # -------------------------------------------------------------------------
    # STAGE 1: plan_topic
    # -------------------------------------------------------------------------
    print("\n[STAGE 1/3] Running Curriculum Planner (plan_topic)...")
    t0 = time.perf_counter()
    try:
        bible = plan_topic(
            topic_dir=workdir_path,
            topic_name=topic,
            audience=audience,
            provider=planner_provider,
        )
    except AgentFailure as e:
        print("\n[FAILURE] Curriculum Planner failed after retries:")
        print(f"Agent: {e.agent_name}")
        print(f"Attempts used: {len(e.attempts)}")
        if e.attempts:
            print(f"Last Error: {e.attempts[-1].get('error')}")
            print(f"Last Response:\n{e.attempts[-1].get('response')}")
        return 1
    except Exception as e:
        print(f"\n[FAILURE] Unexpected error in plan_topic: {e}")
        return 1

    stage1_duration = time.perf_counter() - t0
    planner_attempts = count_agent_attempts(log_dir, "curriculum_planner")

    print(f"-> Stage 1 Complete in {stage1_duration:.2f}s (Attempts used: {planner_attempts})")
    print(f"-> Topic Bible Chapters ({len(bible.chapters)} total):")
    for idx, ch in enumerate(bible.chapters, start=1):
        print(f"   [{idx}] ID: {ch.id:<6} Title: {ch.title}")

    # -------------------------------------------------------------------------
    # STAGE 2: write_script
    # -------------------------------------------------------------------------
    print(f"\n[STAGE 2/3] Running Scriptwriter for Chapter {chapter} (write_script)...")
    t0 = time.perf_counter()
    try:
        script_dict = write_script(
            chapter_dir=workdir_path,
            provider=writer_provider,
            chapter_id=chapter,
            max_regen_attempts=3,
        )
    except AgentFailure as e:
        print("\n[FAILURE] Scriptwriter failed after retries:")
        print(f"Agent: {e.agent_name}")
        print(f"Attempts used: {len(e.attempts)}")
        if e.attempts:
            print(f"Last Error: {e.attempts[-1].get('error')}")
            print(f"Last Response:\n{e.attempts[-1].get('response')}")
        return 1
    except Exception as e:
        print(f"\n[FAILURE] Unexpected error in write_script: {e}")
        return 1

    stage2_duration = time.perf_counter() - t0
    writer_attempts = count_agent_attempts(log_dir, "scriptwriter")

    g1_result = run_g1_script(chapter_dir=workdir_path, script_data=script_dict)
    print(f"-> Stage 2 Complete in {stage2_duration:.2f}s (Attempts used: {writer_attempts})")
    print(f"-> Gate G1 Script Result: {'PASSED' if g1_result.passed else 'FAILED'}")
    for c in g1_result.checks:
        status_tag = "PASS" if c.passed else f"FAIL ({c.severity.upper()})"
        print(f"   [{status_tag:<9}] {c.id:<28} {c.message}")

    if not g1_result.passed:
        print("\n[FAILURE] Gate G1 Script failed validation checks.")
        return 1

    # -------------------------------------------------------------------------
    # STAGE 3: verify_math
    # -------------------------------------------------------------------------
    print(f"\n[STAGE 3/3] Running Math Verifier (verify_math)...")
    t0 = time.perf_counter()
    try:
        facts: Facts = verify_math(chapter_dir=workdir_path)
    except Exception as e:
        print(f"\n[FAILURE] Unexpected error in verify_math: {e}")
        return 1

    stage3_duration = time.perf_counter() - t0
    g2_result = run_g2_math(facts_data=facts.data.model_dump())

    print(f"-> Stage 3 Complete in {stage3_duration:.2f}s")
    print(f"-> Gate G2 Math Result: {'PASSED' if g2_result.passed else 'FAILED'}")
    for c in g2_result.checks:
        status_tag = "PASS" if c.passed else f"FAIL ({c.severity.upper()})"
        print(f"   [{status_tag:<9}] {c.id:<28} {c.message}")

    # Display Claims Status
    print(f"\n-> Facts & Verified Claims ({len(facts.data.claims)} total):")
    for cl in facts.data.claims:
        computed_val = cl.inputs.get("value", facts.values.get(f"{cl.id}.value", "N/A"))
        print(
            f"   Claim ID: {cl.id:<6} Type: {cl.type:<16} Status: {cl.status:<10} Value: {computed_val}"
        )

    # Display Resolved Narration Text
    print("\n-> Resolved Script Narration Text:")
    lines = script_dict.get("lines", [])
    for line in lines:
        raw_text = line.get("text", "")
        try:
            resolved = resolve_placeholders(raw_text, facts, mode="spoken")
        except Exception as e:
            resolved = f"[Resolution Error: {e}] {raw_text}"
        print(f"   [{line.get('id', '??'):<4}] ({line.get('beat', ''):<5}) {resolved}")

    # Summary of artifacts
    print("\n" + "=" * 70)
    print("SMOKE TEST SUMMARY & ARTIFACTS")
    artifacts = ["bible.json", "script.json", "facts.json"]
    for art in artifacts:
        p = workdir_path / art
        size = p.stat().st_size if p.exists() else 0
        print(f" - {art:<14} {'EXISTS' if p.exists() else 'MISSING':<8} ({size} bytes)")
    log_files = list(log_dir.glob("*.json")) if log_dir.is_dir() else []
    print(f" - agent_logs/    {len(log_files)} attempt log file(s)")
    print(f"Total pipeline elapsed time: {stage1_duration + stage2_duration + stage3_duration:.2f}s")
    print("=" * 70)

    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test for Quantum8Lines agent stages.")
    parser.add_argument("--topic", type=str, default="Eigenvectors", help="Curriculum topic name")
    parser.add_argument(
        "--audience",
        type=str,
        default="high school to first-year university",
        help="Target audience description",
    )
    parser.add_argument("--chapter", type=int, default=1, help="Chapter index to write script for")
    parser.add_argument(
        "--workdir",
        type=str,
        default="temp_renders/smoke",
        help="Directory to save generated artifacts and logs",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default=None,
        help="LLM provider override (e.g. 'mock' or 'ollama')",
    )

    args = parser.parse_args()
    workdir_path = Path(args.workdir)
    sys.exit(
        run_smoke(
            topic=args.topic,
            audience=args.audience,
            chapter=args.chapter,
            workdir_path=workdir_path,
            provider_override=args.provider,
        )
    )


if __name__ == "__main__":
    main()
