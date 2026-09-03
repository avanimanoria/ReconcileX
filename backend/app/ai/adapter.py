"""Model adapter interface and implementations for LLM providers."""

import json
import os
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from backend.app.ai.prompt import PROMPT_VERSION, SYSTEM_INSTRUCTION
from backend.app.ai.schemas import ModelMetadata


class BaseLLMAdapter(ABC):
    """Abstract interface for LLM provider adapters."""

    @abstractmethod
    def generate(self, user_prompt: str) -> str:
        """Invoke model with prompt and return raw text/JSON response."""
        pass

    @abstractmethod
    def get_metadata(self) -> ModelMetadata:
        """Return model and prompt metadata."""
        pass


class GeminiLLMAdapter(BaseLLMAdapter):
    """REST adapter for Google Gemini models via generativelanguage API."""

    def __init__(
        self,
        api_key: str,
        model_id: str = "gemini-1.5-flash",
        timeout_seconds: float = 10.0,
    ) -> None:
        self.api_key = api_key
        self.model_id = model_id
        self.timeout_seconds = timeout_seconds

    def generate(self, user_prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model_id}:generateContent?key={self.api_key}"
        payload = {
            "systemInstruction": {
                "parts": [{"text": SYSTEM_INSTRUCTION}]
            },
            "contents": [
                {
                    "parts": [{"text": user_prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        req_data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=req_data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                res_body = response.read().decode("utf-8")
                res_json = json.loads(res_body)
                candidates = res_json.get("candidates", [])
                if not candidates:
                    raise RuntimeError("Gemini returned no candidates in response.")
                content_parts = candidates[0].get("content", {}).get("parts", [])
                if not content_parts:
                    raise RuntimeError("Gemini candidate contains no content parts.")
                return content_parts[0].get("text", "")
        except urllib.error.HTTPError as e:
            err_msg = e.read().decode("utf-8", errors="ignore")
            raise RuntimeError(f"Gemini API HTTP Error {e.code}: {err_msg}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Gemini API Connection Error: {e.reason}")

    def get_metadata(self) -> ModelMetadata:
        return ModelMetadata(
            provider="google",
            model_id=self.model_id,
            model_version=f"{self.model_id}-latest",
            prompt_version=PROMPT_VERSION,
        )


class MockLLMAdapter(BaseLLMAdapter):
    """Configurable mock adapter for deterministic unit tests and benchmarks."""

    def __init__(
        self,
        canned_response: Optional[str] = None,
        should_timeout: bool = False,
        should_error: bool = False,
        error_message: str = "Simulated mock provider failure",
        model_id: str = "mock-model",
        provider: str = "mock-provider",
    ) -> None:
        self.canned_response = canned_response
        self.should_timeout = should_timeout
        self.should_error = should_error
        self.error_message = error_message
        self.model_id = model_id
        self.provider = provider

    def generate(self, user_prompt: str) -> str:
        if self.should_timeout:
            import socket
            raise TimeoutError("Mock provider connection timed out.")
        if self.should_error:
            raise RuntimeError(self.error_message)
        if self.canned_response is not None:
            return self.canned_response
        return "{}"

    def get_metadata(self) -> ModelMetadata:
        return ModelMetadata(
            provider=self.provider,
            model_id=self.model_id,
            model_version="mock-v1",
            prompt_version=PROMPT_VERSION,
        )


def get_configured_llm_adapter() -> Optional[BaseLLMAdapter]:
    """Inspect environment variables and return configured LLM adapter, or None if unconfigured."""
    provider = os.getenv("LLM_PROVIDER", "google").lower()
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")

    if not api_key or not api_key.strip():
        return None

    model_id = os.getenv("LLM_MODEL", "gemini-1.5-flash")

    if provider == "google":
        return GeminiLLMAdapter(api_key=api_key.strip(), model_id=model_id)

    # If an unknown provider is given with a key, default safely to None
    return None
