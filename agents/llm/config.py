"""
Configuration loader and validator for LLM providers.
Follows SPEC.md Section 21.1 and Milestone M5a.
"""

from pathlib import Path
import json
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

from agents.llm.base import LLMProvider
from agents.llm.ollama import OllamaProvider
from agents.llm.gemini import GeminiProvider
from agents.llm.mock import MockProvider


class RoleConfig(BaseModel):
    """Configuration for a specific agent role or default."""

    provider: str = "ollama"
    model: str = "<fill-in>"
    temperature: float = 0.7
    num_ctx: int = 4096
    timeout: float = 60.0
    max_retries: int = Field(default=3, ge=1)


class LLMConfigFile(BaseModel):
    """Schema for config/llm.json."""

    roles: Dict[str, RoleConfig] = Field(default_factory=dict)


def load_llm_config(config_path: str | Path = "config/llm.json") -> LLMConfigFile:
    """Loads and parses config/llm.json."""
    p = Path(config_path)
    if not p.is_file():
        return LLMConfigFile(roles={"default": RoleConfig()})

    data = json.loads(p.read_text(encoding="utf-8"))
    return LLMConfigFile.model_validate(data)


def get_role_config(
    role: str = "default",
    config_path: str | Path = "config/llm.json",
    check_model: bool = True,
) -> RoleConfig:
    """
    Retrieves the RoleConfig for a specific role.
    If check_model is True and the provider is real (e.g. ollama, gemini),
    raises ValueError if the model name is unset or '<fill-in>'.
    """
    cfg_file = load_llm_config(config_path)
    cfg = cfg_file.roles.get(role) or cfg_file.roles.get("default") or RoleConfig()

    if check_model and cfg.provider in ("ollama", "gemini"):
        if not cfg.model or cfg.model == "<fill-in>":
            raise ValueError(
                f"Model for role '{role}' is not configured (found placeholder '{cfg.model}'). "
                f"Please configure an active model in '{config_path}'."
            )

    return cfg


def create_provider(
    provider_name: str,
    mock_responses: Optional[Dict[str, Any]] = None,
) -> LLMProvider:
    """Factory creating an LLMProvider instance by name."""
    name = provider_name.lower().strip()
    if name == "ollama":
        return OllamaProvider()
    elif name == "gemini":
        return GeminiProvider()
    elif name == "mock":
        return MockProvider(responses=mock_responses)
    else:
        raise ValueError(f"Unknown provider '{provider_name}'. Supported: ollama, gemini, mock.")
