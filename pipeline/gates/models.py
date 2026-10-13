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

    # G1 Quality Thresholds (M5a-quality)
    banned_meta_words: List[str] = Field(
        default_factory=lambda: [
            "narration",
            "script",
            "placeholder",
            "json",
            "claim",
            "beat",
            "written for the ear",
        ]
    )
    prompt_echo_ratio_threshold: float = 0.8
    prompt_echo_ngram_len: int = 6
    min_line_words: int = 4
    max_line_words: int = 40
    min_hook_words: int = 6
    allowed_line_endings: List[str] = Field(
        default_factory=lambda: [".", "?", "!"]
    )
    stopwords: List[str] = Field(
        default_factory=lambda: [
            "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
            "of", "with", "is", "was", "are", "were", "be", "been", "being",
            "it", "its", "this", "that", "these", "those", "from", "by", "as",
            "into", "through", "about", "above", "after", "again", "all", "am",
            "any", "before", "below", "between", "both", "can", "could", "did",
            "do", "does", "doing", "down", "during", "each", "few", "further",
            "had", "has", "have", "having", "he", "her", "here", "hers", "herself",
            "him", "himself", "his", "how", "i", "if", "me", "more", "most", "my",
            "myself", "no", "nor", "not", "off", "once", "only", "other", "ought",
            "our", "ours", "ourselves", "out", "over", "own", "same", "she",
            "should", "so", "some", "such", "than", "their", "theirs", "them",
            "themselves", "then", "there", "they", "under", "until", "up", "very",
            "we", "what", "when", "where", "which", "while", "who", "whom", "why",
            "will", "would", "you", "your", "yours", "yourself", "yourselves",
        ]
    )
    # G5 Render Test Thresholds
    empty_frame_sample_sec: float = 0.5
    blank_pixel_diff_threshold: float = 0.002  # 0.2%
    max_blank_frame_fraction: float = 0.15  # 15%
    duration_match_tolerance_sec: float = 0.3  # 0.3 s

    # G6 Visual Thresholds
    visual_overlap_tolerance: float = 0.02  # Manim unit overlap tolerance
    min_label_text_height_px: float = 48.0
    min_keyword_text_height_px: float = 72.0
    min_contrast_ratio: float = 4.5
    max_character_count: int = 2

    # G7 Audio Thresholds
    target_lufs: float = -14.0
    lufs_tolerance: float = 1.0  # +/- 1 LU
    max_true_peak_dbtp: float = -1.0
    max_peak_sample: float = 0.999
    max_consecutive_full_scale: int = 3
    caption_timing_tolerance_sec: float = 0.3

