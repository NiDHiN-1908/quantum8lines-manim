"""
Pydantic data schemas for agent inputs and outputs.
Follows SPEC.md Section 5 and Milestone M5a.
"""

from typing import Dict, List, Optional, Any, Union
from pydantic import BaseModel, Field


class BibleChapter(BaseModel):
    """Specification of a single chapter within a topic curriculum."""

    id: str = Field(description="Chapter ID, e.g. 'ch01'")
    title: str = Field(description="Engaging, concise title")
    one_idea: str = Field(description="The single core concept taught in this chapter")
    question_it_raises: str = Field(description="The natural question leading to the next chapter")
    new_terms: List[str] = Field(default_factory=list, description="Key mathematical terms introduced in this chapter")


class Bible(BaseModel):
    """Topic curriculum specification produced by Curriculum planner (SPEC Section 5.1)."""

    topic: str
    audience: str
    arc: str
    notation: Dict[str, str] = Field(default_factory=dict)
    chapters: List[BibleChapter] = Field(min_length=4, max_length=8)
    prereqs: List[str] = Field(default_factory=list)
    voice_profile: str = Field(default="", description="Voice profile ID (left empty for Voice Lab assignment)")
    cast: List[Dict[str, str]] = Field(default_factory=list)
    sources: List[str] = Field(default_factory=list)


class ClaimSpec(BaseModel):
    """
    Symbolic mathematical claim specification proposed by Scriptwriter.
    Contains ONLY type and symbolic inputs (NO computed values).
    """

    id: str = Field(description="Unique claim ID, e.g. 'c1'")
    type: str = Field(description="Checker type: eigenpair, equation_true, derivative, integral, value_at, solution_set, etc.")
    matrix: Optional[Any] = None
    vector: Optional[Any] = None
    expression: Optional[str] = None
    variable: Optional[str] = None
    equation: Optional[str] = None
    lhs: Optional[str] = None
    rhs: Optional[str] = None
    point: Optional[Any] = None
    limits: Optional[Any] = None
    inputs: Optional[Dict[str, Any]] = None


class ScriptLine(BaseModel):
    """A single narration beat line within a chapter script (SPEC Section 5.2)."""

    id: str = Field(description="Unique line ID, e.g. 'l01'")
    text: str = Field(description="Narration text with {{claim_id.field}} placeholders for all numbers")
    beat: str = Field(description="Beat tag: hook, setup, build, aha, close")
    cut: str = Field(default="both", description="Cut tag: both, short, long")
    claims: List[str] = Field(default_factory=list, description="Referenced claim IDs in this line")
    no_math: bool = Field(default=False, description="Flag indicating this beat line has no mathematical claims")
    pronounce: Dict[str, str] = Field(default_factory=dict, description="Phonetic respellings for lexicon")


class Script(BaseModel):
    """Chapter script produced by Scriptwriter (SPEC Section 5.2)."""

    chapter: str
    lines: List[ScriptLine]
    claim_specs: List[ClaimSpec] = Field(default_factory=list, description="Claim specifications to be evaluated by Math verifier")
