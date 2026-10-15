"""
Pure business logic for Sound Lab: scoring, aggregation, blind evaluation,
acceptance rule evaluation, approval, and simulation palette assignment.
Zero Streamlit dependencies so all logic is cleanly unit-testable.
Follows SPEC.md Section 22.5 and Milestone P2a Step 3.
"""

from pathlib import Path
import json
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from core.sims.sound.models import PRESET_CONFIGS, SoundPaletteSpec


# Documented starting assumptions for Sound Lab acceptance rule (SPEC Section 22.5)
DEFAULT_MIN_LISTENERS = 5
DEFAULT_MIN_PLEASANTNESS = 4.0
DEFAULT_MIN_KEEP_WATCHING_PCT = 70.0

ACCEPTANCE_RULES: Dict[str, Any] = {
    "min_listeners": DEFAULT_MIN_LISTENERS,
    "min_pleasantness": DEFAULT_MIN_PLEASANTNESS,
    "min_keep_watching_pct": DEFAULT_MIN_KEEP_WATCHING_PCT,
}

DEFAULT_SIM_DIR = Path("sims/ellipse_billiards")
DEFAULT_SCORES_PATH = DEFAULT_SIM_DIR / "sound_scores.json"


def get_sim_scores_path(sim_dir: Union[str, Path] = DEFAULT_SIM_DIR) -> Path:
    """Returns the sound_scores.json path for a given simulation."""
    return Path(sim_dir) / "sound_scores.json"


def load_sound_scores(scores_path: Path = DEFAULT_SCORES_PATH) -> List[Dict[str, Any]]:
    """Loads existing listener scores from JSON file."""
    p = Path(scores_path)
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_sound_scores(scores: List[Dict[str, Any]], scores_path: Path = DEFAULT_SCORES_PATH) -> None:
    """Saves listener scores list to JSON file."""
    p = Path(scores_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2)


def record_sound_evaluation(
    listener: str,
    preset_id: str,
    sim_id: str = "ellipse_billiards",
    score: int = 5,
    keep_watching: bool = True,
    blind: bool = True,
    scores_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Records an individual listener evaluation entry and appends to sound_scores.json.
    """
    if not (1 <= score <= 5):
        raise ValueError(f"Score must be an integer between 1 and 5, got {score}")

    entry = {
        "listener": listener.strip(),
        "preset_id": preset_id.strip(),
        "sim_id": sim_id.strip(),
        "score": int(score),
        "keep_watching": bool(keep_watching),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "blind": bool(blind),
    }

    target_path = Path(scores_path) if scores_path else DEFAULT_SCORES_PATH
    scores = load_sound_scores(target_path)
    scores.append(entry)
    save_sound_scores(scores, target_path)
    return entry


def aggregate_sound_scores(
    scores: List[Dict[str, Any]],
    rules: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Aggregates listener evaluations per preset:
    - Unique listeners count (>= 5 required)
    - Mean pleasantness score (1.0 to 5.0, >= 4.0 required)
    - Keep-watching percentage (0.0% to 100.0%, >= 70% required)
    - Acceptance pass/fail status based on rules
    """
    active_rules = dict(ACCEPTANCE_RULES)
    if rules:
        active_rules.update(rules)

    min_listeners = active_rules["min_listeners"]
    min_pleasant = active_rules["min_pleasantness"]
    min_kw = active_rules["min_keep_watching_pct"]

    # Group scores by preset_id
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for entry in scores:
        pid = entry["preset_id"]
        grouped.setdefault(pid, []).append(entry)

    results: Dict[str, Dict[str, Any]] = {}
    for pid, entries in grouped.items():
        listeners = set(e["listener"] for e in entries if e.get("listener"))
        listener_count = len(listeners)
        scores_list = [e["score"] for e in entries]
        kw_list = [1 if e["keep_watching"] else 0 for e in entries]

        mean_pleasantness = round(sum(scores_list) / len(scores_list), 2) if scores_list else 0.0
        kw_pct = round((sum(kw_list) / len(kw_list)) * 100.0, 1) if kw_list else 0.0

        failure_reasons = []
        if listener_count < min_listeners:
            failure_reasons.append(
                f"Listener count {listener_count} is below required {min_listeners}"
            )
        if mean_pleasantness < min_pleasant:
            failure_reasons.append(
                f"Mean pleasantness {mean_pleasantness:.2f} is below required {min_pleasant:.2f}"
            )
        if kw_pct < min_kw:
            failure_reasons.append(
                f"Keep-watching rate {kw_pct:.1f}% is below required {min_kw:.1f}%"
            )

        passed = len(failure_reasons) == 0

        results[pid] = {
            "preset_id": pid,
            "listener_count": listener_count,
            "listeners": sorted(list(listeners)),
            "evaluations_count": len(entries),
            "mean_pleasantness": mean_pleasantness,
            "keep_watching_pct": kw_pct,
            "passed": passed,
            "failure_reasons": failure_reasons,
        }

    return results


def approve_preset(
    preset_id: str,
    sim_id: str = "ellipse_billiards",
    scores_path: Optional[Path] = None,
    allow_override: bool = False,
    override_reason: Optional[str] = None,
    rules: Optional[Dict[str, Any]] = None,
    approvals_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Approves a preset if it meets acceptance criteria (or with explicit override).
    Raises ValueError if criteria are not met and allow_override is False.
    """
    target_scores = Path(scores_path) if scores_path else DEFAULT_SCORES_PATH
    scores = load_sound_scores(target_scores)
    aggregates = aggregate_sound_scores(scores, rules=rules)
    preset_stats = aggregates.get(preset_id)

    passed = preset_stats["passed"] if preset_stats else False

    if not passed:
        if not allow_override:
            reasons = preset_stats["failure_reasons"] if preset_stats else ["No evaluations recorded"]
            raise ValueError(
                f"Cannot approve preset '{preset_id}': Acceptance criteria not met ({'; '.join(reasons)}). "
                f"Use override option to force approval."
            )
        if not override_reason or not override_reason.strip():
            raise ValueError("Approval with override requires a non-empty override_reason.")

    approval_record = {
        "preset_id": preset_id,
        "sim_id": sim_id,
        "status": "approved",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "override": bool(not passed and allow_override),
        "override_reason": override_reason.strip() if (not passed and allow_override and override_reason) else None,
        "metrics": preset_stats,
    }

    if approvals_path:
        app_path = Path(approvals_path)
        app_path.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if app_path.exists():
            try:
                with open(app_path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = {}
        existing[preset_id] = approval_record
        with open(app_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)

    return approval_record


def assign_palette_to_sim(
    preset_or_spec: Union[str, Dict[str, Any], SoundPaletteSpec],
    sim_dir: Union[str, Path] = DEFAULT_SIM_DIR,
) -> Path:
    """
    Assigns a sound palette preset to a simulation short by writing the sound_palette block
    into sims/<id>/sim_spec.json.
    """
    s_dir = Path(sim_dir)
    spec_path = s_dir / "sim_spec.json"
    if not spec_path.is_file():
        raise FileNotFoundError(f"Simulation spec file not found: {spec_path}")

    # Resolve palette spec dict
    if isinstance(preset_or_spec, str):
        if preset_or_spec not in PRESET_CONFIGS:
            raise ValueError(f"Unknown sound preset '{preset_or_spec}'. Supported: {list(PRESET_CONFIGS.keys())}")
        palette_dict = PRESET_CONFIGS[preset_or_spec].model_dump()
    elif isinstance(preset_or_spec, SoundPaletteSpec):
        palette_dict = preset_or_spec.model_dump()
    elif isinstance(preset_or_spec, dict):
        palette_dict = SoundPaletteSpec.model_validate(preset_or_spec).model_dump()
    else:
        raise TypeError(f"Invalid preset type: {type(preset_or_spec)}")

    with open(spec_path, "r", encoding="utf-8") as f:
        spec_data = json.load(f)

    spec_data["sound_palette"] = palette_dict

    with open(spec_path, "w", encoding="utf-8") as f:
        json.dump(spec_data, f, indent=2)

    return spec_path
