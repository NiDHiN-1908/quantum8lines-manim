"""
Structured agent execution runtime with retry loops and attempt logging.
Follows SPEC.md Section 21.2 and Milestone M5a.
"""

from pathlib import Path
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type, TypeVar, Union
from pydantic import BaseModel, ValidationError

from agents.llm.base import LLMProvider
from agents.llm.config import get_role_config

T = TypeVar("T", bound=BaseModel)


class AgentFailure(Exception):
    """Raised when an agent fails to produce valid structured output after all retries."""

    def __init__(self, message: str, agent_name: str, attempts: List[Dict[str, Any]]):
        super().__init__(message)
        self.agent_name = agent_name
        self.attempts = attempts


def strip_code_fences(text: str) -> str:
    """
    Strips markdown code fences (```json ... ``` or ``` ... ```) from model output.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1 :]
        else:
            cleaned = ""
        # Remove trailing ```
        r_cleaned = cleaned.rstrip()
        if r_cleaned.endswith("```"):
            last_fence = r_cleaned.rfind("```")
            cleaned = r_cleaned[:last_fence]
    return cleaned.strip()


def load_agent_prompt(agent_name: str, prompts_dir: Union[str, Path] = "agents") -> str:
    """Loads system prompt from agents/<agent_name>.md."""
    path = Path(prompts_dir) / f"{agent_name}.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return f"You are the {agent_name} agent for Quantum8Lines."


def run_agent(
    agent_name: str,
    inputs: Union[str, Dict[str, Any], BaseModel],
    schema: Type[T],
    provider: LLMProvider,
    log_dir: Optional[Union[str, Path]] = None,
    prompts_dir: Union[str, Path] = "agents",
    max_retries: Optional[int] = None,
    model: Optional[str] = None,
    temperature: Optional[float] = None,
    num_ctx: Optional[int] = None,
    timeout: Optional[float] = None,
) -> T:
    """
    Runs an agent through the provider with structured JSON validation and retries.

    1. Loads system prompt from agents/<agent_name>.md.
    2. Builds user prompt from inputs.
    3. Calls provider.complete().
    4. Strips code fences, parses JSON, and validates with pydantic schema.
    5. On validation or JSON error: retries up to max_retries feeding back the error.
    6. Logs each attempt to <log_dir>/<agent_name>_<n>.json.
    7. Raises AgentFailure if all attempts fail.
    """
    # Resolve config defaults for this agent role
    role_cfg = get_role_config(agent_name, check_model=(provider.name in ("ollama", "gemini")))
    effective_model = model or role_cfg.model
    effective_temp = temperature if temperature is not None else role_cfg.temperature
    effective_ctx = num_ctx if num_ctx is not None else role_cfg.num_ctx
    effective_timeout = timeout if timeout is not None else role_cfg.timeout
    effective_retries = max_retries if max_retries is not None else role_cfg.max_retries

    system_prompt = load_agent_prompt(agent_name, prompts_dir=prompts_dir)

    if isinstance(inputs, BaseModel):
        user_prompt_base = inputs.model_dump_json(indent=2)
    elif isinstance(inputs, dict):
        user_prompt_base = json.dumps(inputs, indent=2)
    else:
        user_prompt_base = str(inputs)

    attempts: List[Dict[str, Any]] = []
    current_user_prompt = user_prompt_base

    if log_dir is not None:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
    else:
        log_path = None

    for attempt_idx in range(1, effective_retries + 1):
        start_time = time.perf_counter()
        raw_response = ""
        error_msg: Optional[str] = None
        parsed_result: Optional[T] = None

        try:
            raw_response = provider.complete(
                system=system_prompt,
                user=current_user_prompt,
                model=effective_model,
                temperature=effective_temp,
                num_ctx=effective_ctx,
                timeout=effective_timeout,
                agent_name=agent_name,
                schema=schema,
            )

            # Strip code fences and parse JSON
            cleaned_json = strip_code_fences(raw_response)
            parsed_data = json.loads(cleaned_json)
            parsed_result = schema.model_validate(parsed_data)

        except json.JSONDecodeError as e:
            error_msg = f"JSON parse error: {str(e)}"
        except ValidationError as e:
            error_msg = f"Schema validation error: {str(e)}"
        except Exception as e:
            error_msg = f"Provider or runtime error: {str(e)}"

        duration = time.perf_counter() - start_time

        attempt_record = {
            "attempt": attempt_idx,
            "agent": agent_name,
            "provider": getattr(provider, "name", "unknown"),
            "model": effective_model,
            "system_prompt": system_prompt,
            "user_prompt": current_user_prompt,
            "response": raw_response,
            "error": error_msg,
            "duration_sec": round(duration, 4),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        attempts.append(attempt_record)

        if log_path is not None:
            attempt_file = log_path / f"{agent_name}_{attempt_idx}.json"
            attempt_file.write_text(json.dumps(attempt_record, indent=2), encoding="utf-8")

        if parsed_result is not None:
            return parsed_result

        # Prepare feedback for retry
        current_user_prompt = (
            f"{user_prompt_base}\n\n"
            f"[RETRY FEEDBACK - Attempt {attempt_idx} failed]\n"
            f"The previous output was invalid and could not be validated:\n"
            f"{error_msg}\n\n"
            f"Please return ONLY a valid JSON object matching the required schema without errors."
        )

    raise AgentFailure(
        f"Agent '{agent_name}' failed after {effective_retries} attempts. Last error: {attempts[-1]['error']}",
        agent_name=agent_name,
        attempts=attempts,
    )
