"""
Ollama LLM Provider using direct HTTP.
Follows SPEC.md Section 21.1 and Milestone M5a.

Plain HTTP (urllib.request) is used rather than the third-party 'ollama' Python package
to keep repository dependencies lean, avoid external wheel conflicts, and maintain
direct control over request timeouts, network diagnostics, and endpoint semantics.
"""

import json
import re
from typing import Optional, Any, Dict
import urllib.request
import urllib.error

from agents.llm.base import LLMProvider


class OllamaProvider(LLMProvider):
    """
    Adapter for locally hosted or cloud-tunneled Ollama instances via HTTP API.
    Default endpoint: http://localhost:11434/api/chat
    Supports structured outputs with JSON schema format when supported,
    with automatic fallback to format "json".
    """

    name: str = "ollama"

    def __init__(self, host: str = "http://localhost:11434"):
        self.host = host.rstrip("/")
        self._supports_schema: Optional[bool] = None

    def check_schema_support(self, timeout: float = 3.0) -> bool:
        """
        Checks whether the installed Ollama daemon supports JSON schema structured output.
        Ollama introduced JSON schema format in version 0.5.0+ (and Windows builds 0.40.x+).
        """
        if self._supports_schema is not None:
            return self._supports_schema

        endpoint = f"{self.host}/api/version"
        try:
            req = urllib.request.Request(endpoint, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
                ver_str = data.get("version", "")
                parts = [int(p) for p in re.findall(r"\d+", ver_str)]
                if len(parts) >= 2:
                    supports = parts[0] > 0 or (parts[0] == 0 and parts[1] >= 5)
                    self._supports_schema = supports
                    return supports
        except Exception:
            pass

        # If version endpoint cannot be reached or parsed, default to True and allow HTTP 400 fallback
        return True

    def complete(
        self,
        system: str,
        user: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        num_ctx: Optional[int] = None,
        timeout: float = 60.0,
        schema: Optional[Any] = None,
        **kwargs: Any,
    ) -> str:
        if not model or model == "<fill-in>":
            raise ValueError(
                "Ollama model name is not set (found placeholder or empty). "
                "Configure a valid model in config/llm.json."
            )

        endpoint = f"{self.host}/api/chat"
        payload: Dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "temperature": float(temperature),
            },
        }
        if num_ctx is not None:
            payload["options"]["num_ctx"] = int(num_ctx)

        # Handle schema / structured output
        schema_dict: Optional[Dict[str, Any]] = None
        if schema is not None:
            if hasattr(schema, "model_json_schema"):
                schema_dict = schema.model_json_schema()
            elif isinstance(schema, dict):
                schema_dict = schema

        use_schema = False
        if schema_dict is not None and self.check_schema_support(timeout=min(timeout, 3.0)):
            payload["format"] = schema_dict
            use_schema = True
        elif schema_dict is not None:
            payload["format"] = "json"
        elif "format" in kwargs:
            payload["format"] = kwargs["format"]

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                resp_json = json.loads(response.read().decode("utf-8"))
                msg = resp_json.get("message", {}).get("content", "")
                return msg
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8", errors="replace")
            # If sending schema caused HTTP 400, fall back to format "json"
            if use_schema and e.code == 400:
                self._supports_schema = False
                payload["format"] = "json"
                fb_bytes = json.dumps(payload).encode("utf-8")
                fb_req = urllib.request.Request(
                    endpoint,
                    data=fb_bytes,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(fb_req, timeout=timeout) as fb_response:
                        resp_json = json.loads(fb_response.read().decode("utf-8"))
                        return resp_json.get("message", {}).get("content", "")
                except Exception as fb_err:
                    raise RuntimeError(
                        f"Ollama HTTP error after falling back to format 'json' at {endpoint}: {fb_err}"
                    ) from fb_err

            raise RuntimeError(
                f"Ollama HTTP error {e.code} ({e.reason}) at {endpoint}: {err_body}"
            ) from e
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Failed to connect to Ollama at {self.host}. Is the Ollama daemon running? Error: {e.reason}"
            ) from e
        except TimeoutError as e:
            raise TimeoutError(
                f"Ollama request to {endpoint} timed out after {timeout} seconds."
            ) from e
