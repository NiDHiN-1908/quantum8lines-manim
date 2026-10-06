"""
Pure business logic for Voice Lab: scoring, aggregation, blind evaluation,
acceptance rule evaluation, approval, and topic assignment.
Zero Streamlit dependencies so all logic is cleanly unit-testable.
Follows SPEC.md Section 10 and Milestone M3b Step 3.
"""

from pathlib import Path
import json
import time
from typing import Dict, Any, List, Tuple, Union, Optional


# Documented starting assumptions for Voice Lab acceptance rule (SPEC Section 10)
DEFAULT_MIN_LISTENERS = 5
DEFAULT_MIN_NATURALNESS = 4.0
DEFAULT_MIN_KEEP_WATCHING_PCT = 70.0

ACCEPTANCE_RULES: Dict[str, Any] = {
    "min_listeners": DEFAULT_MIN_LISTENERS,
    "min_naturalness": DEFAULT_MIN_NATURALNESS,
    "min_keep_watching_pct": DEFAULT_MIN_KEEP_WATCHING_PCT,
}

DEFAULT_SCORES_PATH = Path("brand/voices/scores.json")
DEFAULT_VOICES_DIR = Path("brand/voices")


def load_scores(scores_path: Path = DEFAULT_SCORES_PATH) -> List[Dict[str, Any]]:
    """Loads existing listener scores from JSON file."""
    if not scores_path.exists():
        return []
    try:
        with open(scores_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_scores(scores: List[Dict[str, Any]], scores_path: Path = DEFAULT_SCORES_PATH) -> None:
    """Saves listener scores list to JSON file."""
    scores_path.parent.mkdir(parents=True, exist_ok=True)
    with open(scores_path, "w", encoding="utf-8") as f:
        json.dump(scores, f, indent=2)


def record_evaluation(
    listener: str,
    profile_id: str,
    line_id: str,
    score: int,
    keep_watching: bool,
    blind: bool = True,
    scores_path: Path = DEFAULT_SCORES_PATH,
) -> Dict[str, Any]:
    """
    Records an individual listener evaluation entry and appends to scores.json.
    """
    if not (1 <= score <= 5):
        raise ValueError(f"Score must be an integer between 1 and 5, got {score}")

    entry = {
        "listener": listener.strip(),
        "profile_id": profile_id,
        "line_id": line_id,
        "score": int(score),
        "keep_watching": bool(keep_watching),
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "blind": bool(blind),
    }

    scores = load_scores(scores_path)
    scores.append(entry)
    save_scores(scores, scores_path)
    return entry


def aggregate_scores(
    scores: List[Dict[str, Any]],
    rules: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Aggregates listener evaluations per profile:
    - Unique listeners count
    - Total evaluations count
    - Mean naturalness score (1.0 to 5.0)
    - Keep-watching percentage (0.0% to 100.0%)
    - Acceptance pass/fail status based on rules
    """
    active_rules = dict(ACCEPTANCE_RULES)
    if rules:
        active_rules.update(rules)

    min_listeners = active_rules["min_listeners"]
    min_nat = active_rules["min_naturalness"]
    min_kw = active_rules["min_keep_watching_pct"]

    # Group scores by profile_id
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for entry in scores:
        pid = entry["profile_id"]
        grouped.setdefault(pid, []).append(entry)

    results: Dict[str, Dict[str, Any]] = {}
    for pid, entries in grouped.items():
        listeners = set(e["listener"] for e in entries if e["listener"])
        listener_count = len(listeners)
        scores_list = [e["score"] for e in entries]
        kw_list = [1 if e["keep_watching"] else 0 for e in entries]

        mean_naturalness = round(sum(scores_list) / len(scores_list), 2) if scores_list else 0.0
        kw_pct = round((sum(kw_list) / len(kw_list)) * 100.0, 1) if kw_list else 0.0

        failure_reasons = []
        if listener_count < min_listeners:
            failure_reasons.append(
                f"Listener count {listener_count} is below required {min_listeners}"
            )
        if mean_naturalness < min_nat:
            failure_reasons.append(
                f"Mean naturalness {mean_naturalness:.2f} is below required {min_nat:.2f}"
            )
        if kw_pct < min_kw:
            failure_reasons.append(
                f"Keep-watching rate {kw_pct:.1f}% is below required {min_kw:.1f}%"
            )

        passed = len(failure_reasons) == 0

        results[pid] = {
            "profile_id": pid,
            "listener_count": listener_count,
            "listeners": sorted(list(listeners)),
            "evaluations_count": len(entries),
            "mean_naturalness": mean_naturalness,
            "keep_watching_pct": kw_pct,
            "passed": passed,
            "failure_reasons": failure_reasons,
        }

    return results


def approve_profile(
    profile_id_or_path: Union[str, Path],
    scores_path: Optional[Path] = None,
    allow_override: bool = False,
    override_reason: Optional[str] = None,
    rules: Optional[Dict[str, Any]] = None,
    voices_dir: Path = DEFAULT_VOICES_DIR,
) -> Dict[str, Any]:
    """
    Sets status: 'approved' on the voice profile JSON:
    - Only allowed if the profile meets acceptance criteria, OR if allow_override=True with a non-empty reason.
    - Records override=True and override_reason when forced.
    """
    p = Path(profile_id_or_path)
    if not p.exists() and not str(p).endswith(".json"):
        p = voices_dir / f"{profile_id_or_path}.json"

    if not p.exists():
        raise FileNotFoundError(f"Voice profile file not found: {p}")

    with open(p, "r", encoding="utf-8") as f:
        profile_data = json.load(f)

    profile_id = profile_data.get("id", p.stem)

    # Check evaluation status
    target_scores_path = scores_path or DEFAULT_SCORES_PATH
    scores = load_scores(target_scores_path)
    aggregates = aggregate_scores(scores, rules=rules)
    prof_stats = aggregates.get(profile_id)

    passed = prof_stats["passed"] if prof_stats else False

    if not passed:
        if not allow_override:
            reasons = prof_stats["failure_reasons"] if prof_stats else ["No evaluations recorded"]
            raise ValueError(
                f"Cannot approve profile '{profile_id}': Acceptance criteria not met ({'; '.join(reasons)}). "
                f"Use override option to force approval."
            )
        if not override_reason or not override_reason.strip():
            raise ValueError("Approval with override requires a non-empty override_reason.")

        profile_data["override"] = True
        profile_data["override_reason"] = override_reason.strip()
    else:
        profile_data.pop("override", None)
        profile_data.pop("override_reason", None)

    profile_data["status"] = "approved"

    with open(p, "w", encoding="utf-8") as f:
        json.dump(profile_data, f, indent=2)

    return profile_data


def assign_profile_to_topic(
    profile_id_or_path: Union[str, Path],
    topic_dir: Union[str, Path],
    voices_dir: Path = DEFAULT_VOICES_DIR,
) -> Tuple[Path, bool]:
    """
    Writes voice_profile into the topic's bible.json.
    - Strictly rejects unapproved profiles.
    - Creates minimal bible.json if absent and returns (bible_path, created_minimal).
    """
    p = Path(profile_id_or_path)
    if not p.exists() and not str(p).endswith(".json"):
        p = voices_dir / f"{profile_id_or_path}.json"

    if not p.exists():
        raise FileNotFoundError(f"Voice profile file not found: {p}")

    with open(p, "r", encoding="utf-8") as f:
        profile_data = json.load(f)

    profile_id = profile_data.get("id", p.stem)
    status = profile_data.get("status")

    if status != "approved":
        raise ValueError(
            f"Cannot assign profile '{profile_id}' to topic: Status is '{status}'. "
            f"Only 'approved' profiles can be assigned to a topic."
        )

    t_dir = Path(topic_dir)
    t_dir.mkdir(parents=True, exist_ok=True)
    bible_path = t_dir / "bible.json"

    created_minimal = False
    if not bible_path.exists():
        bible_data = {
            "topic": t_dir.name,
            "title": t_dir.name.replace("_", " ").title(),
            "voice_profile": profile_id,
            "chapters": [],
        }
        created_minimal = True
    else:
        with open(bible_path, "r", encoding="utf-8") as f:
            bible_data = json.load(f)
        bible_data["voice_profile"] = profile_id

    with open(bible_path, "w", encoding="utf-8") as f:
        json.dump(bible_data, f, indent=2)

    return bible_path, created_minimal
