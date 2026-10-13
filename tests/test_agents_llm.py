"""
Tests for LLM providers, configuration loading, error handling, and lazy imports.
Follows SPEC.md Section 21.1 and Milestone M5a.
"""

import os
from pathlib import Path
import pytest

from agents.llm.base import LLMProvider
from agents.llm.mock import MockProvider
from agents.llm.ollama import OllamaProvider
from agents.llm.gemini import GeminiProvider
from agents.llm.config import (
    load_llm_config,
    get_role_config,
    create_provider,
    RoleConfig,
)
from agents.llm.env import load_dotenv


def test_load_llm_config_and_roles(tmp_path: Path):
    """Verify loading valid config/llm.json and retrieving role defaults."""
    config_file = tmp_path / "llm.json"
    config_file.write_text(
        """{
        "roles": {
            "default": {"provider": "mock", "model": "mock-v1", "temperature": 0.5, "max_retries": 3},
            "planner": {"provider": "mock", "model": "mock-planner", "temperature": 0.2, "max_retries": 2}
        }
    }""",
        encoding="utf-8",
    )

    cfg = load_llm_config(config_file)
    assert "default" in cfg.roles
    assert "planner" in cfg.roles

    role_planner = get_role_config("planner", config_path=config_file)
    assert role_planner.model == "mock-planner"
    assert role_planner.temperature == 0.2
    assert role_planner.max_retries == 2

    # Fallback to default
    role_unknown = get_role_config("unknown_agent", config_path=config_file)
    assert role_unknown.model == "mock-v1"


def test_missing_model_raises_clear_error(tmp_path: Path):
    """Real providers with '<fill-in>' or empty model must fail with an informative message."""
    config_file = tmp_path / "llm.json"
    config_file.write_text(
        """{
        "roles": {
            "scriptwriter": {"provider": "ollama", "model": "<fill-in>", "temperature": 0.5}
        }
    }""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Model for role 'scriptwriter' is not configured"):
        get_role_config("scriptwriter", config_path=config_file, check_model=True)


def test_mock_provider_canned_and_invalid_responses():
    """Verify MockProvider returns responses in order and handles invalid JSON simulation."""
    mock = MockProvider(
        responses={"agent_a": ['{"result": "first"}', '{"result": "second"}']},
        invalid_json_count=1,
    )

    # First call returns invalid JSON
    res1 = mock.complete("system", "user", agent_name="agent_a")
    assert "invalid_json" in res1
    assert "incomplete" in res1

    # Second call returns first canned response
    res2 = mock.complete("system", "user", agent_name="agent_a")
    assert res2 == '{"result": "first"}'

    # Third call returns second canned response
    res3 = mock.complete("system", "user", agent_name="agent_a")
    assert res3 == '{"result": "second"}'

    assert len(mock.call_history) == 3


def test_gemini_provider_lazy_import_and_missing_key(monkeypatch):
    """Verify GeminiProvider does not require google-generativeai at initialization, and fails if key is missing."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    provider = GeminiProvider()
    assert provider.name == "gemini"

    # Calling complete without API key raises ValueError
    with pytest.raises(ValueError, match="GEMINI_API_KEY environment variable is not set"):
        provider.complete("sys", "user", model="gemini-pro")


def test_load_dotenv(tmp_path: Path, monkeypatch):
    """Verify lightweight .env file parsing."""
    monkeypatch.delenv("TEST_Q8L_VAR", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("TEST_Q8L_VAR=\"secret_token_123\"\n# Comment line\nANOTHER_VAR=value\n", encoding="utf-8")

    vars_loaded = load_dotenv(env_file)
    assert vars_loaded.get("TEST_Q8L_VAR") == "secret_token_123"
    assert os.environ.get("TEST_Q8L_VAR") == "secret_token_123"
