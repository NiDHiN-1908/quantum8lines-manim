"""
Quantum8Lines LLM Provider Layer.
Follows SPEC.md Section 21 and Milestone M5a.
"""

from agents.llm.base import LLMProvider
from agents.llm.ollama import OllamaProvider
from agents.llm.gemini import GeminiProvider
from agents.llm.mock import MockProvider
from agents.llm.config import (
    RoleConfig,
    LLMConfigFile,
    load_llm_config,
    get_role_config,
    create_provider,
)
from agents.llm.env import load_dotenv

__all__ = [
    "LLMProvider",
    "OllamaProvider",
    "GeminiProvider",
    "MockProvider",
    "RoleConfig",
    "LLMConfigFile",
    "load_llm_config",
    "get_role_config",
    "create_provider",
    "load_dotenv",
]
