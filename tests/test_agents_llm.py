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


def test_ollama_structured_output_schema_in_request_body(monkeypatch):
    """Checks that OllamaProvider sends the Pydantic JSON schema in the request's 'format' field."""
    from pydantic import BaseModel, Field
    import json
    import io

    class DemoOutput(BaseModel):
        title: str = Field(description="A test title")
        value: int = Field(description="A test number")

    captured_requests = []

    class MockHTTPResponse:
        def __init__(self, data: bytes):
            self._io = io.BytesIO(data)

        def read(self):
            return self._io.read()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        # Return valid mock Ollama response
        resp_payload = {
            "model": "llama3.1:latest",
            "message": {
                "role": "assistant",
                "content": '{"title": "Test", "value": 42}',
            },
        }
        return MockHTTPResponse(json.dumps(resp_payload).encode("utf-8"))

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    provider = OllamaProvider()
    provider._supports_schema = True  # Explicitly enabled or detected

    res = provider.complete(
        system="You are a helper.",
        user="Produce demo output.",
        model="llama3.1:latest",
        schema=DemoOutput,
    )

    assert res == '{"title": "Test", "value": 42}'
    assert len(captured_requests) == 1

    req = captured_requests[0]
    body = json.loads(req.data.decode("utf-8"))
    assert "format" in body
    assert body["format"] == DemoOutput.model_json_schema()
    assert body["format"]["properties"]["title"]["description"] == "A test title"


def test_ollama_structured_output_fallback_when_unsupported(monkeypatch):
    """Checks that OllamaProvider falls back to format 'json' when schema is unsupported."""
    from pydantic import BaseModel
    import json
    import io

    class DemoOutput(BaseModel):
        summary: str

    captured_requests = []

    class MockHTTPResponse:
        def __init__(self, data: bytes):
            self._io = io.BytesIO(data)

        def read(self):
            return self._io.read()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_urlopen(req, timeout=None):
        captured_requests.append(req)
        resp_payload = {
            "model": "llama3.1:latest",
            "message": {"role": "assistant", "content": '{"summary": "Fallback works"}'},
        }
        return MockHTTPResponse(json.dumps(resp_payload).encode("utf-8"))

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    provider = OllamaProvider()
    provider._supports_schema = False  # Older Ollama version without schema support

    res = provider.complete(
        system="sys",
        user="user",
        model="llama3.1:latest",
        schema=DemoOutput,
    )

    assert res == '{"summary": "Fallback works"}'
    assert len(captured_requests) == 1
    body = json.loads(captured_requests[0].data.decode("utf-8"))
    assert body["format"] == "json"


def test_ollama_structured_output_http400_fallback(monkeypatch):
    """Checks that OllamaProvider catches HTTP 400 on schema format and falls back to 'json'."""
    from pydantic import BaseModel
    import json
    import io
    import urllib.error

    class DemoOutput(BaseModel):
        status: str

    captured_requests = []
    attempt_count = 0

    class MockHTTPResponse:
        def __init__(self, data: bytes):
            self._io = io.BytesIO(data)

        def read(self):
            return self._io.read()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            pass

    def mock_urlopen(req, timeout=None):
        nonlocal attempt_count
        attempt_count += 1
        captured_requests.append(req)

        if attempt_count == 1:
            # Simulate Ollama 400 rejecting schema in format
            fp = io.BytesIO(b'{"error": "cannot unmarshal object into Go struct field"}')
            raise urllib.error.HTTPError(
                url=req.full_url,
                code=400,
                msg="Bad Request",
                hdrs={},
                fp=fp,
            )

        # Second attempt with format 'json' succeeds
        resp_payload = {
            "model": "llama3.1:latest",
            "message": {"role": "assistant", "content": '{"status": "ok"}'},
        }
        return MockHTTPResponse(json.dumps(resp_payload).encode("utf-8"))

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", mock_urlopen)

    provider = OllamaProvider()
    # Assume True initially
    provider._supports_schema = True

    res = provider.complete(
        system="sys",
        user="user",
        model="llama3.1:latest",
        schema=DemoOutput,
    )

    assert res == '{"status": "ok"}'
    assert len(captured_requests) == 2
    # First request sent schema
    assert json.loads(captured_requests[0].data.decode("utf-8"))["format"] == DemoOutput.model_json_schema()
    # Second request fell back to "json"
    assert json.loads(captured_requests[1].data.decode("utf-8"))["format"] == "json"
    # Cached flag updated
    assert provider._supports_schema is False
