"""Anthropic provider implementation for Claude models."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import cast

from pydantic import BaseModel

from contractex.exceptions import LLMProviderError
from contractex.llm.base import LLMProvider

logger = logging.getLogger(__name__)

try:
    from anthropic import APIConnectionError as _ANTConnectionError
    from anthropic import APIStatusError as _ANTStatusError
    from anthropic import APITimeoutError as _ANTTimeoutError
    from anthropic import RateLimitError as _ANTRateLimitError

    _ANTHROPIC_RETRYABLE = (
        _ANTRateLimitError,
        _ANTConnectionError,
        _ANTTimeoutError,
    )
except ImportError:
    _ANTHROPIC_RETRYABLE = ()  # type: ignore[assignment]
    _ANTStatusError = None  # type: ignore[assignment,misc]


def _anthropic_is_retryable(exc: Exception) -> bool:
    if _ANTHROPIC_RETRYABLE and isinstance(exc, _ANTHROPIC_RETRYABLE):
        return True
    if _ANTStatusError and isinstance(exc, _ANTStatusError):  # type: ignore[truthy-function]
        return bool(exc.status_code >= 500)
    return False


class AnthropicProvider(LLMProvider):
    """Anthropic LLM provider supporting Claude 3.5 Sonnet and other models."""

    # Token costs per 1M tokens (as of 2024)
    COSTS = {
        "claude-3-5-sonnet-20241022": {"input": 3.00, "output": 15.00},
        "claude-3-5-sonnet-20240620": {"input": 3.00, "output": 15.00},
        "claude-3-opus-20240229": {"input": 15.00, "output": 75.00},
        "claude-3-sonnet-20240229": {"input": 3.00, "output": 15.00},
        "claude-3-haiku-20240307": {"input": 0.25, "output": 1.25},
    }

    # Context windows
    CONTEXT_WINDOWS = {
        "claude-3-5-sonnet-20241022": 200000,
        "claude-3-5-sonnet-20240620": 200000,
        "claude-3-opus-20240229": 200000,
        "claude-3-sonnet-20240229": 200000,
        "claude-3-haiku-20240307": 200000,
    }

    def __init__(
        self,
        model: str = "claude-3-5-sonnet-20241022",
        api_key: str | None = None,
        temperature: float = 0.0,
        max_tokens: int = 4000,
    ):
        """
        Initialize Anthropic provider.

        Args:
            model: Model name (e.g., "claude-3-5-sonnet-20241022")
            api_key: Anthropic API key (defaults to ANTHROPIC_API_KEY env var)
            temperature: Default temperature for completions
            max_tokens: Default max tokens for completions
        """
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

        # Get API key
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise LLMProviderError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter."
            )

        # Initialize Anthropic client
        try:
            from anthropic import Anthropic

            self.client = Anthropic(api_key=api_key)
        except ImportError as e:
            raise LLMProviderError(
                "Anthropic package not installed. Install with: pip install anthropic"
            ) from e

    def _call_with_retry(self, fn, label: str, max_retries: int = 3, base_delay: float = 1.0):
        """Call fn() with exponential backoff on transient Anthropic errors."""
        last_exc: Exception = Exception("unreachable")
        for attempt in range(max_retries):
            try:
                return fn()
            except LLMProviderError:
                raise
            except Exception as exc:
                if not _anthropic_is_retryable(exc):
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
        """
        Extract structured data using Claude with JSON schema.

        Claude doesn't have native structured output, so we inject the JSON
        schema into the prompt and parse the response.
        """
        json_schema = schema.model_json_schema()
        enhanced_prompt = (
            f"{prompt}\n\nYou must respond with valid JSON that matches this schema:\n"
            f"{json.dumps(json_schema, indent=2)}\n\nRespond ONLY with the JSON object, no additional text."
        )

        def _call():
            response = self.client.messages.create(
                model=self._model,
                max_tokens=max_tokens or self._max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": enhanced_prompt}],
            )
            block = response.content[0]
            if not hasattr(block, "text"):
                raise LLMProviderError(f"Unexpected response block type: {type(block).__name__}")
            content = cast(str, block.text)
            if not content.strip().startswith("{"):
                start = content.find("{")
                end = content.rfind("}") + 1
                if start != -1 and end > start:
                    content = content[start:end]
            data = json.loads(content)
            return schema(**data)

        return self._call_with_retry(_call, "Anthropic structured extraction")  # type: ignore[no-any-return]

    def stream_complete(
        self, prompt: str, temperature: float = 0.7, max_tokens: int | None = None, **kwargs
    ):
        """Stream a text completion from Anthropic token-by-token."""
        from collections.abc import Iterator

        def _generate() -> Iterator[str]:
            with self.client.messages.stream(
                model=self._model,
                max_tokens=max_tokens or self._max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            ) as stream:
                yield from stream.text_stream

        return _generate()

    def complete(
        self, prompt: str, temperature: float = 0.7, max_tokens: int | None = None, **kwargs
    ) -> str:
        """Get text completion from Anthropic."""

        def _call():
            response = self.client.messages.create(
                model=self._model,
                max_tokens=max_tokens or self._max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )
            block = response.content[0]
            if not hasattr(block, "text"):
                raise LLMProviderError(f"Unexpected response block type: {type(block).__name__}")
            return cast(str, block.text)

        return self._call_with_retry(_call, "Anthropic completion")  # type: ignore[no-any-return]

    def estimate_cost(self, text: str) -> float:
        """Estimate cost for processing text."""
        tokens = self.count_tokens(text)

        # Get costs for this model
        costs = self.COSTS.get(self._model, self.COSTS["claude-3-5-sonnet-20241022"])

        # Estimate input + output tokens (assume 1:1 ratio)
        input_cost = (tokens / 1_000_000) * costs["input"]
        output_cost = (tokens / 1_000_000) * costs["output"]

        return input_cost + output_cost

    def count_tokens(self, text: str) -> int:
        """
        Count tokens using Anthropic's count method.

        Falls back to character-based estimation if API unavailable.
        """
        try:
            # Use Anthropic's token counting
            response = self.client.messages.count_tokens(
                model=self._model, messages=[{"role": "user", "content": text}]
            )
            return response.input_tokens
        except Exception:
            # Fallback: Claude uses similar tokenization to GPT
            # Rough estimate: 1 token ≈ 4 characters
            return len(text) // 4

    @property
    def context_window(self) -> int:
        """Get context window size."""
        return self.CONTEXT_WINDOWS.get(self._model, 200000)

    @property
    def model(self) -> str:
        """Get model name."""
        result: str = self._model
        return result
