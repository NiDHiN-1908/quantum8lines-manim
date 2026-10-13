"""
Ollama LLM Provider using direct HTTP.
Follows SPEC.md Section 21.1 and Milestone M5a.

Plain HTTP (urllib.request) is used rather than the third-party 'ollama' Python package
to keep repository dependencies lean, avoid external wheel conflicts, and maintain
direct control over request timeouts, network diagnostics, and endpoint semantics.
"""

import json
from typing import Optional, Any, Dict
import urllib.request
import urllib.error

from agents.llm.base import LLMProvider


class OllamaProvider(LLMProvider):
    """
    Adapter for locally hosted or cloud-tunneled Ollama instances via HTTP API.
    Default endpoint: http://localhost:11434/api/chat
    """

    name: str = "ollama"

    def __init__(self, host: str = "http://localhost:11434"):
        self.host = host.rstrip("/")

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
