"""
Abstract base class for LLM completion providers.
Follows SPEC.md Section 21.1 and Milestone M5a.
"""

from abc import ABC, abstractmethod
from typing import Optional, Any


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    name: str = "base"

    @abstractmethod
    def complete(
        self,
        system: str,
        user: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        num_ctx: Optional[int] = None,
        timeout: float = 60.0,
        **kwargs: Any,
    ) -> str:
        """
        Sends system and user prompt to the provider and returns text completion.
        """
        pass
