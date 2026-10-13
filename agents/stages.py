"""
Agent stage orchestration functions: plan_topic, write_script, and verify_math.
Follows SPEC.md Section 8 and Milestone M5a.
"""

from pathlib import Path
import json
from typing import Any, Dict, Optional, Union

from agents.schemas import Bible, Script, BibleChapter
from agents.runtime import run_agent
from agents.llm.base import LLMProvider
from agents.llm.config import get_role_config, create_provider
from agents.math_verifier import evaluate_and_verify_claims
from core.mathengine.facts import Facts
from pipeline.gates.g1_script import run_g1_script
from pipeline.gates.g2_math import run_g2_math
from pipeline.status import update_stage_status, save_qa_report


def plan_topic(
    topic_dir: Union[str, Path],
    topic_name: Optional[str] = None,
    audience: Optional[str] = None,
    provider: Optional[LLMProvider] = None,
) -> Bible:
    """
    Curriculum planning stage:
    Takes topic and audience, runs Curriculum planner agent, writes bible.json,
    and updates status.json.
    """
    path = Path(topic_dir)
    path.mkdir(parents=True, exist_ok=True)

    # 1. Resolve topic metadata
    metadata_file = path / "topic.json"
    if metadata_file.is_file():
        meta = json.loads(metadata_file.read_text(encoding="utf-8"))
        topic_name = topic_name or meta.get("topic")
        audience = audience or meta.get("audience")

    topic_name = topic_name or path.name.replace("_", " ").title()
    audience = audience or "high school to undergraduate, comfortable with basic algebra"

    # 2. Resolve provider
    if provider is None:
        cfg = get_role_config("curriculum_planner")
        provider = create_provider(cfg.provider)

    inputs = {"topic": topic_name, "audience": audience}
    log_dir = path / "agent_logs"

    # 3. Run Curriculum planner agent
    bible: Bible = run_agent(
        agent_name="curriculum_planner",
        inputs=inputs,
        schema=Bible,
        provider=provider,
        log_dir=log_dir,
    )

    # 4. Save bible.json
    bible_file = path / "bible.json"
    bible_file.write_text(bible.model_dump_json(indent=2), encoding="utf-8")

    # 5. Update status
    update_stage_status(
        chapter_dir=path,
        stage="plan",
        status="passed",
        artifacts=["bible.json"],
    )

    return bible


def write_script(
    chapter_dir: Union[str, Path],
    provider: Optional[LLMProvider] = None,
    max_regen_attempts: int = 3,
    chapter_id: Optional[Union[str, int]] = None,
) -> Dict[str, Any]:
    """
    Scriptwriting stage:
    Takes bible.json and chapter spec, generates script.json with placeholders,
    runs Quality Gate G1, and feeds failing checks back to the scriptwriter
    for up to max_regen_attempts if G1 fails.
    """
    ch_path = Path(chapter_dir)
    ch_path.mkdir(parents=True, exist_ok=True)

    # 1. Locate bible.json
    bible_path = None
    for cand in (
        ch_path.parent.parent / "bible.json",
        ch_path.parent / "bible.json",
        ch_path / "bible.json",
    ):
        if cand.is_file():
            bible_path = cand
            break

    if bible_path is not None:
        bible_data = json.loads(bible_path.read_text(encoding="utf-8"))
        bible = Bible.model_validate(bible_data)
        # Match chapter spec by index or id or default to first
        if isinstance(chapter_id, int):
            ch_idx = max(0, min(chapter_id - 1, len(bible.chapters) - 1))
            matched_ch = bible.chapters[ch_idx]
        elif isinstance(chapter_id, str):
            matched_ch = next((c for c in bible.chapters if c.id == chapter_id), bible.chapters[0])
        else:
            ch_id = ch_path.name
            matched_ch = next((c for c in bible.chapters if c.id == ch_id), bible.chapters[0])
    else:
        # Fallback default chapter spec
        bible = Bible(
            topic=ch_path.name.title(),
            audience="general",
            arc="intro to concept",
            chapters=[
                BibleChapter(
                    id="ch01",
                    title="Introduction",
                    one_idea="Core definition",
                    question_it_raises="Next step",
                ),
                BibleChapter(id="ch02", title="Setup", one_idea="Setup", question_it_raises="Why?"),
                BibleChapter(id="ch03", title="Build", one_idea="Build", question_it_raises="How?"),
                BibleChapter(id="ch04", title="Payoff", one_idea="Payoff", question_it_raises="Done"),
            ],
        )
        matched_ch = bible.chapters[0]

    # 2. Resolve provider
    if provider is None:
        cfg = get_role_config("scriptwriter")
        provider = create_provider(cfg.provider)

    log_dir = ch_path / "agent_logs"
    current_inputs: Dict[str, Any] = {
        "bible": bible.model_dump(),
        "chapter": matched_ch.model_dump(),
    }

    last_script_dict: Optional[Dict[str, Any]] = None
    last_g1 = None

    # 3. Regeneration loop evaluating G1
    for regen_idx in range(1, max_regen_attempts + 1):
        script_model: Script = run_agent(
            agent_name="scriptwriter",
            inputs=current_inputs,
            schema=Script,
            provider=provider,
            log_dir=log_dir,
        )

        last_script_dict = script_model.model_dump()
        last_g1 = run_g1_script(
            chapter_dir=ch_path,
            script_data=last_script_dict,
            chapter_data=matched_ch.model_dump(),
            bible_data=bible.model_dump(),
        )

        if last_g1.passed:
            break

        # Feed back failing check IDs and messages
        failing_checks = [f"{c.id}: {c.message}" for c in last_g1.checks if not c.passed]
        current_inputs = {
            "bible": bible.model_dump(),
            "chapter": matched_ch.model_dump(),
            "gate_feedback": (
                f"[REGENERATION ATTEMPT {regen_idx} - Gate G1 failed]\n"
                f"Failing checks:\n" + "\n".join(failing_checks) + "\n\n"
                "Please fix these issues:\n"
                "- Replace raw digits with {{claim_id.field}} placeholders.\n"
                "- Remove all meta-language ('narration', 'script', 'placeholder', 'json', 'claim', 'beat', 'written for the ear') and unclosed braces.\n"
                "- Do NOT echo prompt examples; write original phrasing.\n"
                "- Ensure every line ends with terminal punctuation ('.', '?', '!') and word count is between 100 and 180 words.\n"
                "- Directly address the chapter's one_idea and do NOT use terms introduced in later chapters."
            ),
        }

    # 4. Save script.json
    script_file = ch_path / "script.json"
    script_file.write_text(json.dumps(last_script_dict, indent=2), encoding="utf-8")

    # 5. Update status and save QA report
    status_str = "passed" if (last_g1 and last_g1.passed) else "failed"
    update_stage_status(
        chapter_dir=ch_path,
        stage="script",
        status=status_str,
        artifacts=["script.json"],
    )
    if last_g1:
        save_qa_report(ch_path, [last_g1])

    return last_script_dict


def verify_math(chapter_dir: Union[str, Path]) -> Facts:
    """
    Math verification stage (Code only):
    Takes script.json, evaluates claim_specs into facts.json,
    runs Quality Gate G2, and updates status.json.
    """
    ch_path = Path(chapter_dir)
    script_file = ch_path / "script.json"
    if not script_file.is_file():
        raise FileNotFoundError(f"script.json not found in {ch_path}")

    script_data = json.loads(script_file.read_text(encoding="utf-8"))
    claim_specs = script_data.get("claim_specs", [])

    # 1. Compute and verify claims deterministically
    facts: Facts = evaluate_and_verify_claims(claim_specs)

    # 2. Save facts.json
    facts_file = ch_path / "facts.json"
    facts.save(facts_file)

    # 3. Run Gate G2
    g2 = run_g2_math(facts_data=facts.data.model_dump())

    # 4. Update status and save QA report
    status_str = "passed" if g2.passed else "failed"
    update_stage_status(
        chapter_dir=ch_path,
        stage="verify",
        status=status_str,
        artifacts=["facts.json"],
    )
    save_qa_report(ch_path, [g2])

    return facts
