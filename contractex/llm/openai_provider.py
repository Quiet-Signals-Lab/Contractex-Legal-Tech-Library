"""OpenAI provider implementation for GPT models."""

from __future__ import annotations

import logging
import os
import time
from typing import cast

from pydantic import BaseModel

from contractex.exceptions import LLMProviderError
from contractex.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# Errors that warrant a retry (rate limits, network, server errors)
try:
    from openai import APIConnectionError as _OAIConnectionError
    from openai import APIStatusError as _OAIStatusError
    from openai import APITimeoutError as _OAITimeoutError
    from openai import RateLimitError as _OAIRateLimitError

    _OPENAI_RETRYABLE = (
        _OAIRateLimitError,
        _OAIConnectionError,
        _OAITimeoutError,
    )
except ImportError:  # openai not installed yet (shouldn't happen, it's in deps)
    _OPENAI_RETRYABLE = ()  # type: ignore[assignment]
    _OAIStatusError = None  # type: ignore[assignment,misc]


def _openai_is_retryable(exc: Exception) -> bool:
    """Return True if the exception is worth retrying."""
    if _OPENAI_RETRYABLE and isinstance(exc, _OPENAI_RETRYABLE):
        return True
    # Retry 5xx server errors (but not 4xx client errors)
    if _OAIStatusError and isinstance(exc, _OAIStatusError):  # type: ignore[truthy-function]
        return bool(exc.status_code >= 500)
    return False


class OpenAIProvider(LLMProvider):
    """OpenAI LLM provider supporting GPT-4o, GPT-4o-mini, and other models."""

    # Token costs per 1M tokens (as of 2024)
    COSTS = {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
        "gpt-4": {"input": 30.00, "output": 60.00},
        "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    }

    # Context windows
    CONTEXT_WINDOWS = {
        "gpt-4o": 128000,
        "gpt-4o-mini": 128000,
        "gpt-4-turbo": 128000,
        "gpt-4": 8192,
        "gpt-3.5-turbo": 16385,
    }

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4000,
    ):
        """
        Initialize OpenAI provider.

        Args:
            model: Model name (e.g., "gpt-4o", "gpt-4o-mini")
            api_key: OpenAI API key (defaults to OPENAI_API_KEY env var)
            temperature: Default temperature for completions
            max_tokens: Default max tokens for completions
        """
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

        # Get API key
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise LLMProviderError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable "
                "or pass api_key parameter."
            )

        # Initialize OpenAI client
        try:
            from openai import OpenAI

            self.client = OpenAI(api_key=api_key)
        except ImportError as e:
            raise LLMProviderError(
                "OpenAI package not installed. Install with: pip install openai"
            ) from e

    def _call_with_retry(self, fn, label: str, max_retries: int = 3, base_delay: float = 1.0):
        """
        Call fn() with exponential backoff on transient OpenAI errors.

        Retries on rate limits, connection errors, timeouts, and 5xx responses.
        Non-retryable errors (4xx auth/validation) are raised immediately.
        """
        last_exc: Exception = Exception("unreachable")
        for attempt in range(max_retries):
            try:
                return fn()
            except LLMProviderError:
                raise  # Already wrapped — don't retry
            except Exception as exc:
                if not _openai_is_retryable(exc):
                    raise LLMProviderError(f"{label} failed: {exc}") from exc
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
        """Extract structured data using OpenAI's structured output feature."""

        def _call():
            response = self.client.beta.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You are a legal document extraction assistant."},
                    {"role": "user", "content": prompt},
                ],
                response_format=schema,
                temperature=temperature,
                max_tokens=max_tokens or self._max_tokens,
            )
            parsed = response.choices[0].message.parsed
            if parsed is None:
                raise LLMProviderError("OpenAI returned None for parsed response")
            return parsed

        return self._call_with_retry(_call, "OpenAI structured extraction")  # type: ignore[no-any-return]

    def stream_complete(
        self, prompt: str, temperature: float = 0.7, max_tokens: int | None = None, **kwargs
    ):
        """Stream a text completion from OpenAI token-by-token."""
        from typing import Iterator

        def _generate() -> Iterator[str]:
            stream = self.client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens or self._max_tokens,
                stream=True,
                **kwargs,
            )
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    yield delta.content

        return _generate()

    def complete(
        self, prompt: str, temperature: float = 0.7, max_tokens: int | None = None, **kwargs
    ) -> str:
        """Get text completion from OpenAI."""

        def _call():
            response = self.client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens or self._max_tokens,
                **kwargs,
            )
            content = response.choices[0].message.content
            if content is None:
                raise LLMProviderError("OpenAI returned empty response")
            return cast(str, content)

        return self._call_with_retry(_call, "OpenAI completion")  # type: ignore[no-any-return]

    def estimate_cost(self, text: str) -> float:
        """Estimate cost for processing text."""
        tokens = self.count_tokens(text)

        # Get costs for this model
        costs = self.COSTS.get(self._model, self.COSTS["gpt-4o"])

        # Estimate input + output tokens (assume 1:1 ratio)
        input_cost = (tokens / 1_000_000) * costs["input"]
        output_cost = (tokens / 1_000_000) * costs["output"]

        return input_cost + output_cost

    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken."""
        try:
            import tiktoken  # type: ignore[import-not-found]

            # Get encoding for model
            if "gpt-4" in self._model:
                encoding = tiktoken.encoding_for_model("gpt-4")
            else:
                encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")

            return len(encoding.encode(text))

        except ImportError:
            # Fallback: rough estimate (1 token ≈ 4 characters)
            return len(text) // 4

    @property
    def context_window(self) -> int:
        """Get context window size."""
        return self.CONTEXT_WINDOWS.get(self._model, 128000)

    @property
    def model(self) -> str:
        """Get model name."""
        result: str = self._model
        return result
