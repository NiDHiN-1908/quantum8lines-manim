"""
Facts loader, saver, and verifier for Quantum8Lines.
Follows SPEC.md sections 5.3 and 7.
Provides require_verified(claim_id) which raises UnverifiedClaimError
if a claim is failed or unverifiable.
"""

from pathlib import Path
import json
from typing import Dict, Any, List, Optional, Union

from core.mathengine.schemas import Claim, FactsData
from core.mathengine.checkers import verify_claim


class UnverifiedClaimError(Exception):
    """
    Raised when require_verified is called for a claim that is not verified.
    Prevents scenes from drawing an unverified or mathematically false number.
    """
    pass


class Facts:
    """
    Container for topic/chapter mathematical facts and claims.
    Enforces truth by blocking access to values from failed claims.
    """

    def __init__(self, data: Optional[FactsData] = None):
        self.data = data or FactsData()

    @property
    def claims(self) -> List[Claim]:
        return self.data.claims

    @property
    def values(self) -> Dict[str, Any]:
        return self.data.values

    @classmethod
    def load(cls, path: Union[str, Path]) -> "Facts":
        """Load facts from a JSON file."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Facts file not found at: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        data = FactsData.model_validate(raw_data)
        return cls(data=data)

    def save(self, path: Union[str, Path]) -> None:
        """Save facts to a JSON file."""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.data.model_dump(), f, indent=2)

    def add_claim(self, claim: Union[Claim, Dict[str, Any]]) -> Claim:
        """Add a claim to the facts dataset."""
        if isinstance(claim, dict):
            c = Claim.model_validate(claim)
        else:
            c = claim
        self.data.claims.append(c)
        return c

    def set_value(self, key: str, value: Any) -> None:
        """Set a named value in values dict."""
        self.data.values[key] = value

    def get_claim(self, claim_id: str) -> Claim:
        """Retrieve a claim by its ID."""
        for c in self.data.claims:
            if c.id == claim_id:
                return c
        raise KeyError(f"Claim with id '{claim_id}' not found in Facts.")

    def verify_all(self) -> None:
        """Verify all claims using the math engine checkers."""
        for claim in self.data.claims:
            verify_claim(claim)

    def require_verified(self, claim_id: str) -> Dict[str, Any]:
        """
        Return the verified inputs and associated values for claim_id.
        Raises UnverifiedClaimError if the claim status is not 'verified'.
        """
        claim = self.get_claim(claim_id)

        if claim.status != "verified":
            raise UnverifiedClaimError(
                f"Cannot use values from claim '{claim_id}': status is '{claim.status}'. "
                f"Reason: {claim.reason or 'Not verified by math engine'}"
            )

        # Merge claim inputs with values if any
        res = dict(claim.inputs)
        if claim_id in self.data.values:
            res["_fact_value"] = self.data.values[claim_id]
        return res
