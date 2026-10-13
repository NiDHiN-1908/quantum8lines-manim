"""
Gemini LLM Provider with lazy imports.
Follows SPEC.md Section 21.1 and Milestone M5a.
"""

import os
from typing import Optional, Any

from agents.llm.base import LLMProvider
from agents.llm.env import load_dotenv


class GeminiProvider(LLMProvider):
    """
    Adapter for Google Gemini APIs.
    Import is performed lazily so the repository runs offline and without google packages.
    """

    name: str = "gemini"

    def __init__(self, api_key: Optional[str] = None):
        load_dotenv()
        self._explicit_key = api_key

    def _get_api_key(self) -> str:
        key = self._explicit_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise ValueError(
                "GEMINI_API_KEY environment variable is not set. "
                "Provide an API key via environment variable or .env file."
            )
        return key

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
                "Gemini model name is not set (found placeholder or empty). "
                "Configure a valid model in config/llm.json."
            )

        api_key = self._get_api_key()

        # Lazy import of google package
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise ImportError(
                "google-generativeai is not installed. "
                "Install it with 'uv add google-generativeai' to use GeminiProvider."
            ) from exc

        genai.configure(api_key=api_key)
        gemini_model = genai.GenerativeModel(
            model_name=model,
            system_instruction=system if system else None,
            generation_config={"temperature": float(temperature)},
        )

        response = gemini_model.generate_content(user, request_options={"timeout": timeout})
        return getattr(response, "text", "") or ""
