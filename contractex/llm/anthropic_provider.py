"""Anthropic provider implementation for Claude models."""

import json
import os
from typing import Optional

from pydantic import BaseModel

from contractex.exceptions import LLMProviderError
from contractex.llm.base import LLMProvider


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
        api_key: Optional[str] = None,
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

    def extract_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> BaseModel:
        """
        Extract structured data using Claude with JSON schema.

        Claude doesn't have native structured output, so we use JSON mode
        with schema in the prompt.
        """
        try:
            # Get JSON schema
            json_schema = schema.model_json_schema()

            # Create enhanced prompt with schema
            enhanced_prompt = f"""
{prompt}

You must respond with valid JSON that matches this schema:
{json.dumps(json_schema, indent=2)}

Respond ONLY with the JSON object, no additional text.
"""

            # Get completion
            response = self.client.messages.create(
                model=self._model,
                max_tokens=max_tokens or self._max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": enhanced_prompt}],
            )

            # Parse JSON response
            content = response.content[0].text

            # Try to extract JSON if there's extra text
            if not content.strip().startswith("{"):
                # Find first { and last }
                start = content.find("{")
                end = content.rfind("}") + 1
                if start != -1 and end > start:
                    content = content[start:end]

            # Parse and validate
            data = json.loads(content)
            return schema(**data)

        except Exception as e:
            raise LLMProviderError(f"Anthropic structured extraction failed: {str(e)}") from e

    def complete(
        self, prompt: str, temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs
    ) -> str:
        """Get text completion from Anthropic."""
        try:
            response = self.client.messages.create(
                model=self._model,
                max_tokens=max_tokens or self._max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
                **kwargs,
            )

            return response.content[0].text

        except Exception as e:
            raise LLMProviderError(f"Anthropic completion failed: {str(e)}") from e

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
        return self._model
