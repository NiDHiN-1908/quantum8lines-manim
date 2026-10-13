"""
Tests for structured agent execution runtime, retries, and attempt logging.
Follows SPEC.md Section 21.2 and Milestone M5a.
"""

from pathlib import Path
import pytest
from pydantic import BaseModel, Field

from agents.runtime import run_agent, AgentFailure, strip_code_fences
from agents.llm.mock import MockProvider


class SampleOutputSchema(BaseModel):
    title: str
    count: int = Field(ge=1)


def test_strip_code_fences():
    """Verify stripping of json and plain code fences."""
    fenced_json = "```json\n{\"title\": \"demo\", \"count\": 2}\n```"
    assert strip_code_fences(fenced_json) == '{"title": "demo", "count": 2}'

    fenced_plain = "```\n{\"title\": \"demo\", \"count\": 2}\n```"
    assert strip_code_fences(fenced_plain) == '{"title": "demo", "count": 2}'

    clean_raw = "{\"title\": \"demo\", \"count\": 2}"
    assert strip_code_fences(clean_raw) == '{"title": "demo", "count": 2}'


def test_run_agent_success_first_try(tmp_path: Path):
    """Verify run_agent returns parsed pydantic model on first attempt."""
    mock = MockProvider(
        responses={"test_agent": '{"title": "First Try", "count": 5}'}
    )
    log_dir = tmp_path / "logs"

    result = run_agent(
        agent_name="test_agent",
        inputs={"prompt": "create schema"},
        schema=SampleOutputSchema,
        provider=mock,
        log_dir=log_dir,
        max_retries=3,
        model="mock-model",
    )

    assert result.title == "First Try"
    assert result.count == 5

    # Check log file
    log_file = log_dir / "test_agent_1.json"
    assert log_file.is_file()
    assert not (log_dir / "test_agent_2.json").exists()


def test_run_agent_success_after_two_invalid_outputs(tmp_path: Path):
    """Verify run_agent retries on invalid outputs and succeeds on the third attempt."""
    mock = MockProvider(
        responses={
            "test_agent": [
                '{"title": "Missing count"}',                           # Schema validation failure
                '{"title": "Count too low", "count": 0}',                # Count < 1 validation failure
                '{"title": "Valid Output", "count": 42}',                 # Valid
            ]
        }
    )
    log_dir = tmp_path / "logs"

    result = run_agent(
        agent_name="test_agent",
        inputs="input prompt",
        schema=SampleOutputSchema,
        provider=mock,
        log_dir=log_dir,
        max_retries=3,
        model="mock-model",
    )

    assert result.title == "Valid Output"
    assert result.count == 42

    # Check all three log files exist
    assert (log_dir / "test_agent_1.json").is_file()
    assert (log_dir / "test_agent_2.json").is_file()
    assert (log_dir / "test_agent_3.json").is_file()


def test_run_agent_failure_after_max_retries(tmp_path: Path):
    """Verify run_agent raises AgentFailure with attempt records when retries are exhausted."""
    mock = MockProvider(
        responses={
            "test_agent": [
                'not json',
                '{"title": 123, "count": "bad"}',
                '{"title": "bad count", "count": -1}',
            ]
        }
    )
    log_dir = tmp_path / "logs"

    with pytest.raises(AgentFailure) as exc_info:
        run_agent(
            agent_name="test_agent",
            inputs="input prompt",
            schema=SampleOutputSchema,
            provider=mock,
            log_dir=log_dir,
            max_retries=3,
            model="mock-model",
        )

    err = exc_info.value
    assert err.agent_name == "test_agent"
    assert len(err.attempts) == 3
    assert (log_dir / "test_agent_3.json").is_file()
