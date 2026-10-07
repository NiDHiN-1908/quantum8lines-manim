"""
Pipeline status and QA report tracking (SPEC.md Section 8 & Section 9).
Manages topics/<topic>/chapters/<ch>/status.json and qa/report.json.
"""

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from pipeline.gates.models import GateResult

STAGES = [
    "plan",
    "script",
    "verify",
    "storyboard",
    "tts",
    "align",
    "code",
    "test_render",
    "qa_visual",
    "final_render",
    "mix",
    "captions",
    "assemble",
    "export",
    "review",
]

VALID_STATUSES = {"pending", "running", "passed", "failed", "needs_human"}


def get_default_status() -> Dict[str, Any]:
    """Generate default initial status for all pipeline stages."""
    return {
        "stages": {
            stage: {
                "status": "pending",
                "input_hash": None,
                "started_at": None,
                "completed_at": None,
                "artifacts": [],
            }
            for stage in STAGES
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def load_status(chapter_dir: Union[str, Path]) -> Dict[str, Any]:
    """
    Load status.json for a chapter. If absent, returns default initialized status.
    """
    path = Path(chapter_dir) / "status.json"
    if not path.exists():
        return get_default_status()

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Ensure all stages exist
    default = get_default_status()
    for stage in STAGES:
        if stage not in data.get("stages", {}):
            data.setdefault("stages", {})[stage] = default["stages"][stage]

    return data


def save_status(chapter_dir: Union[str, Path], status_data: Dict[str, Any]) -> Path:
    """Save status.json for a chapter, ensuring parent directory exists."""
    path = Path(chapter_dir) / "status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    status_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(status_data, f, indent=2)
    return path


def update_stage_status(
    chapter_dir: Union[str, Path],
    stage: str,
    status: str,
    input_hash: Optional[str] = None,
    artifacts: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Update a pipeline stage status with timestamps, input hash, and artifact paths.
    """
    if stage not in STAGES:
        raise ValueError(f"Unknown pipeline stage '{stage}'. Allowed stages: {STAGES}")
    if status not in VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Allowed statuses: {VALID_STATUSES}"
        )

    status_data = load_status(chapter_dir)
    stage_info = status_data["stages"][stage]
    now_iso = datetime.now(timezone.utc).isoformat()

    stage_info["status"] = status
    if status == "running":
        stage_info["started_at"] = now_iso
        stage_info["completed_at"] = None
    elif status in ("passed", "failed", "needs_human"):
        if not stage_info.get("started_at"):
            stage_info["started_at"] = now_iso
        stage_info["completed_at"] = now_iso

    if input_hash is not None:
        stage_info["input_hash"] = input_hash
    if artifacts is not None:
        stage_info["artifacts"] = artifacts

    save_status(chapter_dir, status_data)
    return status_data


def save_qa_report(
    chapter_dir: Union[str, Path],
    gate_results: List[GateResult],
    extra: Optional[Dict[str, Any]] = None,
) -> Path:
    """
    Save quality gate results to <chapter_dir>/qa/report.json.
    """
    report_path = Path(chapter_dir) / "qa" / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)

    all_passed = all(gr.passed for gr in gate_results)
    gates_data = {
        gr.gate_id: {
            "passed": gr.passed,
            "checks": [c.model_dump() for c in gr.checks],
        }
        for gr in gate_results
    }

    report = {
        "passed": all_passed,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "gates": gates_data,
    }
    if extra:
        report["extra"] = extra

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    return report_path


def load_qa_report(chapter_dir: Union[str, Path]) -> Optional[Dict[str, Any]]:
    """Load QA report from <chapter_dir>/qa/report.json if present."""
    report_path = Path(chapter_dir) / "qa" / "report.json"
    if not report_path.exists():
        return None
    with open(report_path, "r", encoding="utf-8") as f:
        return json.load(f)
