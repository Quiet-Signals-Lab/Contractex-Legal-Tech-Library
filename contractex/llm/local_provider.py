"""Local LLM provider using Ollama for privacy-first deployments."""

from __future__ import annotations

import json
import logging
import os
import time

from pydantic import BaseModel

from contractex.exceptions import LLMProviderError
from contractex.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class LocalProvider(LLMProvider):
    """
    Local LLM provider using Ollama.

    Supports running models locally for complete privacy and data sovereignty.
    """

    # Default context windows for common models
    CONTEXT_WINDOWS = {
        "llama-3.1-70b": 128000,
        "llama-3.1-8b": 128000,
        "llama-3-70b": 8192,
        "llama-3-8b": 8192,
        "mistral": 32768,
        "mixtral": 32768,
        "phi-3": 128000,
    }

    def __init__(
        self,
        model: str = "llama-3.1-70b",
        host: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4000,
    ):
        """
        Initialize local LLM provider.

        Args:
            model: Model name (must be pulled in Ollama)
            host: Ollama host URL (defaults to OLLAMA_HOST env var or localhost)
            temperature: Default temperature for completions
            max_tokens: Default max tokens for completions
        """
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

        # Get Ollama host
        self._host = host or os.getenv("OLLAMA_HOST", "http://localhost:11434")

        # Initialize Ollama client
        try:
            import ollama

            self.client = ollama.Client(host=self._host)
        except ImportError as e:
            raise LLMProviderError(
                "Ollama package not installed. Install with: pip install ollama"
            ) from e

        # Check if model is available
        try:
            self.client.show(self._model)
        except Exception as e:
            raise LLMProviderError(
                f"Model '{self._model}' not found in Ollama. "
                f"Pull it first with: ollama pull {self._model}"
            ) from e

    def _call_with_retry(self, fn, label: str, max_retries: int = 3, base_delay: float = 2.0):
        """
        Call fn() with exponential backoff on any exception.

        Local models may be slow to load or temporarily unavailable, so we use a
        longer base_delay (2 s) compared to cloud providers.
        """
        last_exc: Exception = Exception("unreachable")
        for attempt in range(max_retries):
            try:
                return fn()
            except LLMProviderError:
                raise
            except Exception as exc:
                last_exc = exc
                if attempt < max_retries - 1:
                    delay = base_delay * (2**attempt)
                    logger.warning(
                        "%s failed (attempt %d/%d): %s — retrying in %.1fs",
                        label,
                        attempt + 1,
                        max_retries,
                        exc,
                        delay,
                    )
                    time.sleep(delay)
        raise LLMProviderError(
            f"{label} failed after {max_retries} retries: {last_exc}"
        ) from last_exc

    def extract_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> BaseModel:
        """Extract structured data using local LLM with JSON mode."""
        json_schema = schema.model_json_schema()
        enhanced_prompt = (
            f"{prompt}\n\nYou must respond with valid JSON that matches this schema:\n"
            f"{json.dumps(json_schema, indent=2)}\n\nRespond ONLY with the JSON object, no additional text."
        )

        def _call():
            response = self.client.generate(
                model=self._model,
                prompt=enhanced_prompt,
                format="json",
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens or self._max_tokens,
                },
            )
            content = response["response"]
            data = json.loads(content)
            return schema(**data)

        return self._call_with_retry(_call, "Local LLM structured extraction")  # type: ignore[no-any-return]

    def complete(
        self, prompt: str, temperature: float = 0.7, max_tokens: int | None = None, **kwargs
    ) -> str:
        """Get text completion from local LLM."""

        def _call():
            response = self.client.generate(
                model=self._model,
                prompt=prompt,
                options={
                    "temperature": temperature,
                    "num_predict": max_tokens or self._max_tokens,
                },
            )
            result: str = response["response"]
            return result

        return self._call_with_retry(_call, "Local LLM completion")  # type: ignore[no-any-return]

    def estimate_cost(self, text: str) -> float:
        """
        Local LLMs have no API cost.

        Returns:
            Always returns 0.0 for local models
        """
        return 0.0

    def count_tokens(self, text: str) -> int:
        """
        Count tokens using rough estimation.

        Note: Ollama doesn't provide a token counting API.
        """
        # Rough estimate: 1 token ≈ 4 characters
        # This is approximate and model-dependent
        return len(text) // 4

    @property
    def context_window(self) -> int:
        """Get context window size."""
        # Try to match model name to known context windows
        for model_prefix, window in self.CONTEXT_WINDOWS.items():
            if model_prefix in self._model.lower():
                return window

        # Default to conservative 8K
        return 8192

    @property
    def model(self) -> str:
        """Get model name."""
        return self._model
