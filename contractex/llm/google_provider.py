"""Google Gemini provider implementation."""

import json
import logging
import os
import time
from typing import Optional

from pydantic import BaseModel

from contractex.exceptions import LLMProviderError
from contractex.llm.base import LLMProvider

logger = logging.getLogger(__name__)


class GoogleProvider(LLMProvider):
    """Google Gemini LLM provider supporting gemini-pro and other models."""

    # Token costs per 1M tokens (as of 2024)
    COSTS = {
        "gemini-1.5-pro": {"input": 1.25, "output": 5.00},
        "gemini-1.5-flash": {"input": 0.075, "output": 0.30},
        "gemini-pro": {"input": 0.50, "output": 1.50},
    }

    # Context windows
    CONTEXT_WINDOWS = {
        "gemini-1.5-pro": 2000000,  # 2M tokens
        "gemini-1.5-flash": 1000000,  # 1M tokens
        "gemini-pro": 32768,
    }

    def __init__(
        self,
        model: str = "models/gemini-2.0-flash",
        api_key: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 4000,
    ):
        """
        Initialize Google Gemini provider.

        Args:
            model: Model name (e.g., "models/gemini-2.0-flash", "models/gemini-2.5-pro")
            api_key: Google API key (defaults to GOOGLE_API_KEY env var)
            temperature: Default temperature for completions
            max_tokens: Default max tokens for completions
        """
        self._model = model
        self._temperature = temperature
        self._max_tokens = max_tokens

        # Get API key
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self._api_key:
            raise LLMProviderError(
                "Google API key not found. Set GOOGLE_API_KEY environment variable "
                "or pass api_key parameter."
            )

        # Initialize client
        try:
            # Try new package first
            try:
                from google import genai
                self.client_type = 'new'
                client = genai.Client(api_key=self._api_key)
                self.client = client.models.generate_content
                self._model_name = model
            except (ImportError, AttributeError):
                # Fall back to old deprecated package
                import google.generativeai as genai
                self.client_type = 'old'
                genai.configure(api_key=self._api_key)

                # Ensure model name has models/ prefix
                if not model.startswith("models/"):
                    model = f"models/{model}"

                self.client = genai.GenerativeModel(model)
                self._model_name = model
        except ImportError as e:
            raise LLMProviderError(
                "Google Generative AI package not installed. "
                "Install with: pip install google-genai (recommended) or google-generativeai"
            ) from e
        except Exception as e:
            raise LLMProviderError(f"Failed to initialize Google client: {str(e)}") from e

    @property
    def model(self) -> str:
        """Get the model name."""
        return self._model

    def _call_with_retry(self, fn, label: str, max_retries: int = 3, base_delay: float = 2.0):
        """Call fn() with exponential backoff on retryable errors."""
        last_error = None

        for attempt in range(1, max_retries + 1):
            try:
                return fn()
            except Exception as e:
                last_error = e
                is_retryable = self._is_retryable_error(e)

                if attempt < max_retries and is_retryable:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "%s failed (attempt %d/%d): %s — retrying in %.1fs",
                        label,
                        attempt,
                        max_retries,
                        str(e),
                        delay,
                    )
                    time.sleep(delay)
                else:
                    break

        raise LLMProviderError(f"{label} failed after {max_retries} attempts") from last_error

    def _is_retryable_error(self, exc: Exception) -> bool:
        """Check if error is retryable (rate limits, network, server errors)."""
        error_str = str(exc).lower()
        return any(
            keyword in error_str
            for keyword in ["rate limit", "timeout", "503", "429", "connection", "overloaded"]
        )

    def extract_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> BaseModel:
        """
        Extract structured data using Google Gemini.

        Args:
            prompt: The prompt describing what to extract
            schema: Pydantic model defining the expected structure
            temperature: Sampling temperature (0.0 = deterministic)
            max_tokens: Maximum tokens to generate

        Returns:
            Instance of schema with extracted data

        Raises:
            LLMProviderError: If extraction fails
        """
        max_tokens = max_tokens or self._max_tokens

        def _call():
            # Build JSON schema prompt
            json_schema = schema.model_json_schema()
            enhanced_prompt = f"""{prompt}

You must respond with valid JSON matching this exact schema:
{json.dumps(json_schema, indent=2)}

Requirements:
- Return ONLY valid JSON, no markdown code blocks
- Use double quotes for strings
- Ensure all strings are properly escaped
- Do not include any text before or after the JSON
"""

            # Call Gemini API
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }

            if self.client_type == 'old':
                response = self.client.generate_content(
                    enhanced_prompt, generation_config=generation_config
                )
                if not response or not response.text:
                    raise LLMProviderError("Empty response from Gemini")
                response_text = response.text.strip()
            else:
                # New API
                response = self.client(
                    model=self._model_name,
                    contents=enhanced_prompt,
                    config=generation_config
                )
                if not response or not response.text:
                    raise LLMProviderError("Empty response from Gemini")
                response_text = response.text.strip()

            # Remove markdown code blocks if present
            if response_text.startswith("```json"):
                response_text = response_text[7:]
            if response_text.startswith("```"):
                response_text = response_text[3:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()

            # Parse JSON
            try:
                data = json.loads(response_text)
                return schema(**data)
            except json.JSONDecodeError as e:
                logger.error(
                    "Failed to parse Gemini response as JSON.\n"
                    "Error: %s\n"
                    "Response (first 500 chars): %s",
                    str(e),
                    response_text[:500]
                )
                raise LLMProviderError(
                    f"Invalid JSON from Gemini: {str(e)}\n"
                    f"Response preview: {response_text[:200]}"
                ) from e
            except Exception as e:
                logger.error(
                    "Failed to validate response against schema.\n"
                    "Error: %s\n"
                    "Data: %s",
                    str(e),
                    str(data)[:500] if 'data' in locals() else 'N/A'
                )
                raise LLMProviderError(f"Schema validation failed: {str(e)}") from e

        return self._call_with_retry(_call, "Google Gemini structured extraction")

    def complete(
        self, prompt: str, temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs
    ) -> str:
        """
        Get text completion from Google Gemini.

        Args:
            prompt: The prompt text
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional arguments

        Returns:
            Generated text
        """
        max_tokens = max_tokens or self._max_tokens

        def _call():
            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }

            if self.client_type == 'old':
                response = self.client.generate_content(prompt, generation_config=generation_config)
            else:
                response = self.client(
                    model=self._model_name,
                    contents=prompt,
                    config=generation_config
                )

            if not response or not response.text:
                raise LLMProviderError("Empty response from Gemini")

            return response.text

        return self._call_with_retry(_call, "Google Gemini completion")

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.

        Note: Google doesn't provide a simple token counter in the SDK,
        so we use a rough approximation.
        """
        # Rough approximation: 1 token ≈ 4 characters for English text
        # This matches OpenAI's fallback behavior
        return len(text) // 4

    def estimate_cost(self, text: str) -> float:
        """Estimate cost for processing text."""
        tokens = self.count_tokens(text)

        # Get costs for this model
        model_base = self._model.split("-")[0] + "-" + self._model.split("-")[1]
        if model_base not in self.COSTS:
            model_base = self._model

        costs = self.COSTS.get(model_base, {"input": 0.50, "output": 1.50})

        # Estimate input + output tokens (assume 1:1 ratio)
        input_cost = (tokens / 1_000_000) * costs["input"]
        output_cost = (tokens / 1_000_000) * costs["output"]

        return input_cost + output_cost

    @property
    def context_window(self) -> int:
        """Get the context window size for the model."""
        return self.CONTEXT_WINDOWS.get(self._model, 32768)
