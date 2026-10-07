"""
Pydantic data models for Quality Gate framework (SPEC.md Section 9 & Milestone M4a).
Defines Check, GateResult, and GateConfig.
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class Check(BaseModel):
    """An individual validation check within a quality gate."""

    id: str
    passed: bool
    severity: Literal["error", "warning"] = "error"
    message: str
    details: Optional[Dict[str, Any]] = None


class GateResult(BaseModel):
    """Aggregate result of a quality gate containing all executed checks."""

    gate_id: str
    passed: bool
    checks: List[Check] = Field(default_factory=list)

    @classmethod
    def create(cls, gate_id: str, checks: List[Check]) -> "GateResult":
        """
        Create a GateResult where gate passes only if no check with
        severity == 'error' has passed == False.
        """
        gate_passed = all(
            c.passed for c in checks if c.severity == "error"
        )
        return cls(gate_id=gate_id, passed=gate_passed, checks=checks)

    def get_check(self, check_id: str) -> Optional[Check]:
        """Find a specific check by its ID."""
        for c in self.checks:
            if c.id == check_id:
                return c
        return None


class GateConfig(BaseModel):
    """Configurable parameters and threshold limits for quality gates."""

    min_words: int = 100
    max_words: int = 180
    allowed_beats: List[str] = Field(
        default_factory=lambda: ["hook", "setup", "build", "aha", "close"]
    )
    canonical_beat_order: List[str] = Field(
        default_factory=lambda: ["hook", "setup", "build", "aha", "close"]
    )
    allowed_cuts: List[str] = Field(
        default_factory=lambda: ["both", "short", "long"]
    )
