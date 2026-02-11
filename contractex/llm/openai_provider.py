"""OpenAI provider implementation for GPT models."""

from typing import Type, Optional
from pydantic import BaseModel
import os

from contractex.llm.base import LLMProvider
from contractex.exceptions import LLMProviderError


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
        api_key: Optional[str] = None,
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
        except ImportError:
            raise LLMProviderError(
                "OpenAI package not installed. Install with: pip install openai"
            )
    
    def extract_structured(
        self,
        prompt: str,
        schema: Type[BaseModel],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> BaseModel:
        """Extract structured data using OpenAI's structured output feature."""
        try:
            response = self.client.beta.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": "You are a legal document extraction assistant."},
                    {"role": "user", "content": prompt}
                ],
                response_format=schema,
                temperature=temperature,
                max_tokens=max_tokens or self._max_tokens,
            )
            
            parsed = response.choices[0].message.parsed
            if parsed is None:
                raise LLMProviderError("OpenAI returned None for parsed response")
            return parsed
            
        except Exception as e:
            raise LLMProviderError(f"OpenAI structured extraction failed: {str(e)}") from e
    
    def complete(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Get text completion from OpenAI."""
        try:
            response = self.client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens or self._max_tokens,
                **kwargs
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            raise LLMProviderError(f"OpenAI completion failed: {str(e)}") from e
    
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
        return self._model
