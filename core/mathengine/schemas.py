"""
Pydantic schemas for mathematical claims and facts.json data structures.
Follows SPEC.md sections 5.3 and 7.
"""

from typing import Dict, Any, List, Optional, Literal
from pydantic import BaseModel, Field, model_validator

ClaimStatus = Literal["verified", "failed", "unverifiable"]


class Claim(BaseModel):
    """
    A single mathematical claim verified by the math engine.
    Fields match SPEC 5.3 and 7.
    """
    id: str
    type: str
    inputs: Dict[str, Any] = Field(default_factory=dict)
    status: ClaimStatus = "unverifiable"
    reason: Optional[str] = None

    @model_validator(mode="before")
    @classmethod
    def parse_flexible_inputs(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        d = dict(data)
        cid = d.get("id")
        ctype = d.get("type")
        status = d.get("status")
        reason = d.get("reason")
        inputs = d.get("inputs", {})

        # Handle SPEC 5.3 "verified": true/false legacy boolean
        if "verified" in d and status is None:
            status = "verified" if d["verified"] else "failed"

        # Any extra top-level fields (e.g. matrix, vector, value, lhs, rhs)
        # that are not standard metadata go into inputs
        known_keys = {"id", "type", "inputs", "status", "reason", "verified"}
        extra_keys = {k: v for k, v in d.items() if k not in known_keys}
        if extra_keys:
            merged_inputs = dict(inputs) if isinstance(inputs, dict) else {}
            merged_inputs.update(extra_keys)
            inputs = merged_inputs

        return {
            "id": cid,
            "type": ctype,
            "inputs": inputs,
            "status": status if status else "unverifiable",
            "reason": reason,
        }

    def get(self, key: str, default: Any = None) -> Any:
        """Convenience method to access inputs or fields."""
        if key in self.inputs:
            return self.inputs[key]
        return getattr(self, key, default)


class FactsData(BaseModel):
    """
    Top-level data structure for facts.json.
    Matches SPEC 5.3: {"claims": [...], "values": {...}}
    """
    claims: List[Claim] = Field(default_factory=list)
    values: Dict[str, Any] = Field(default_factory=dict)
