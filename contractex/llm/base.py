"""
Abstract base class for LLM providers.

All LLM providers must implement this interface to be compatible with ContractEx.
"""

from abc import ABC, abstractmethod
from typing import Optional

from pydantic import BaseModel


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def extract_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> BaseModel:
        """
        Extract structured data from text using the LLM.

        Args:
            prompt: The prompt to send to the LLM
            schema: Pydantic model schema for the expected output
            temperature: Temperature for generation (0.0-1.0)
            max_tokens: Maximum tokens to generate

        Returns:
            Instance of the schema with extracted data

        Raises:
            LLMProviderError: If extraction fails
        """
        pass

    @abstractmethod
    def complete(
        self, prompt: str, temperature: float = 0.7, max_tokens: Optional[int] = None, **kwargs
    ) -> str:
        """
        Get a text completion from the LLM.

        Args:
            prompt: The prompt to complete
            temperature: Temperature for generation
            max_tokens: Maximum tokens to generate
            **kwargs: Additional provider-specific arguments

        Returns:
            Completion text

        Raises:
            LLMProviderError: If completion fails
        """
        pass

    @abstractmethod
    def estimate_cost(self, text: str) -> float:
        """
        Estimate the API cost for processing this text.

        Args:
            text: Text to estimate cost for

        Returns:
            Estimated cost in USD
        """
        pass

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text using provider's tokenizer.

        Args:
            text: Text to count tokens for

        Returns:
            Number of tokens
        """
        pass

    @property
    @abstractmethod
    def context_window(self) -> int:
        """
        Get the maximum context window size for this provider.

        Returns:
            Context window size in tokens
        """
        pass

    @property
    @abstractmethod
    def model(self) -> str:
        """
        Get the model name/identifier.

        Returns:
            Model name
        """
        pass

    def supports_structured_output(self) -> bool:
        """
        Check if this provider supports structured output.

        Returns:
            True if structured output is supported
        """
        return True
