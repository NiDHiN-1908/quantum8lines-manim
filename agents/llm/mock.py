"""
Mock LLM Provider for offline, deterministic testing of agent workflows.
Follows SPEC.md Section 21.1 and Milestone M5a.
"""

from pathlib import Path
import json
from typing import Optional, Any, Dict, List, Union

from agents.llm.base import LLMProvider


class MockProvider(LLMProvider):
    """
    Mock provider returning canned responses keyed by agent name or sequential queues.
    Can intentionally inject invalid JSON a specified number of times to test retry loops.
    """

    name: str = "mock"

    def __init__(
        self,
        responses: Optional[Dict[str, Union[str, List[str]]]] = None,
        fixture_path: Optional[Union[str, Path]] = None,
        invalid_json_count: int = 0,
    ):
        self.responses: Dict[str, List[str]] = {}
        if fixture_path is not None:
            p = Path(fixture_path)
            if p.is_file():
                raw = json.loads(p.read_text(encoding="utf-8"))
                for k, v in raw.items():
                    self.responses[k] = [v] if isinstance(v, str) else list(v)

        if responses is not None:
            for k, v in responses.items():
                self.responses[k] = [v] if isinstance(v, str) else list(v)

        self.invalid_json_count = invalid_json_count
        self._current_invalid_count = 0
        self.call_history: List[Dict[str, Any]] = []

    def set_invalid_count(self, count: int) -> None:
        """Set or reset how many times to emit invalid JSON before returning valid responses."""
        self.invalid_json_count = count
        self._current_invalid_count = 0

    def add_response(self, key: str, response: str) -> None:
        """Append a canned response for a given key or agent name."""
        if key not in self.responses:
            self.responses[key] = []
        self.responses[key].append(response)

    def complete(
        self,
        system: str,
        user: str,
        model: Optional[str] = "mock-model",
        temperature: float = 0.7,
        num_ctx: Optional[int] = None,
        timeout: float = 60.0,
        agent_name: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        call_record = {
            "system": system,
            "user": user,
            "model": model,
            "temperature": temperature,
            "agent_name": agent_name,
        }
        self.call_history.append(call_record)

        # Check if we should inject invalid JSON
        if self._current_invalid_count < self.invalid_json_count:
            self._current_invalid_count += 1
            return '{"invalid_json": true, incomplete: ...'

        # Lookup candidate key (agent_name, or from kwargs, or 'default')
        key = agent_name or kwargs.get("key") or "default"
        if key in self.responses and self.responses[key]:
            return self.responses[key].pop(0)

        # Fallback to 'default' if present
        if "default" in self.responses and self.responses["default"]:
            return self.responses["default"].pop(0)

        # If no canned responses remain, return a safe minimal empty JSON
        return "{}"
