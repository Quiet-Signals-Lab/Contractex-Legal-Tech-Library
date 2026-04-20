"""LangChain LLM provider adapter for compatibility."""

from __future__ import annotations

from pydantic import BaseModel

from contractex.exceptions import LLMProviderError
from contractex.llm.base import LLMProvider


class LangChainProvider(LLMProvider):
    """
    Adapter to use LangChain LLMs with ContractEx.

    This allows using any LangChain-compatible LLM with ContractEx.
    """

    def __init__(self, langchain_llm, default_max_tokens: int = 4000):
        """
        Initialize LangChain provider adapter.

        Args:
            langchain_llm: Any LangChain LLM instance
            default_max_tokens: Default max tokens for completions
        """
        self.langchain_llm = langchain_llm
        self._default_max_tokens = default_max_tokens

        # Get model name if available
        model_name: str = getattr(langchain_llm, "model_name", langchain_llm.__class__.__name__)
        self._model_name: str = model_name

    def extract_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> BaseModel:
        """
        Extract structured data using LangChain LLM.

        Uses LangChain's structured output if available, otherwise falls back
        to JSON parsing.
        """
        try:
            # Try to use structured output if available
            if hasattr(self.langchain_llm, "with_structured_output"):
                structured_llm = self.langchain_llm.with_structured_output(schema)
                result: BaseModel = structured_llm.invoke(prompt)
                return result
            else:
                # Fallback to JSON parsing
                import json

                json_schema = schema.model_json_schema()
                enhanced_prompt = f"""
{prompt}

Respond with valid JSON matching this schema:
{json.dumps(json_schema, indent=2)}
"""

                response = self.complete(enhanced_prompt, temperature, max_tokens)

                # Try to extract JSON
                if not response.strip().startswith("{"):
                    start = response.find("{")
                    end = response.rfind("}") + 1
                    if start != -1 and end > start:
                        response = response[start:end]

                data = json.loads(response)
                return schema(**data)

        except Exception as e:
            raise LLMProviderError(f"LangChain structured extraction failed: {str(e)}") from e

    def complete(
        self, prompt: str, temperature: float = 0.7, max_tokens: int | None = None, **kwargs
    ) -> str:
        """Get text completion from LangChain LLM."""
        try:
            # Set temperature if possible
            original_temp = None
            if hasattr(self.langchain_llm, "temperature"):
                original_temp = self.langchain_llm.temperature
                self.langchain_llm.temperature = temperature

            # Invoke LLM
            response = self.langchain_llm.invoke(prompt, **kwargs)

            # Restore temperature
            if original_temp is not None:
                self.langchain_llm.temperature = original_temp

            # Handle different response types
            if isinstance(response, str):
                return response
            elif hasattr(response, "content"):
                content: str = response.content
                return content
            else:
                return str(response)

        except Exception as e:
            raise LLMProviderError(f"LangChain completion failed: {str(e)}") from e

    def estimate_cost(self, text: str) -> float:
        """
        Estimate cost for processing text.

        Returns 0.0 if LangChain LLM doesn't provide pricing info.
        """
        # LangChain doesn't have standardized cost estimation
        return 0.0

    def count_tokens(self, text: str) -> int:
        """Count tokens using LangChain's method if available."""
        if hasattr(self.langchain_llm, "get_num_tokens"):
            result: int = self.langchain_llm.get_num_tokens(text)
            return result
        else:
            # Fallback estimate
            return len(text) // 4

    @property
    def context_window(self) -> int:
        """Get context window size."""
        # Try to get from LLM attributes
        if hasattr(self.langchain_llm, "max_context_size"):
            size: int = self.langchain_llm.max_context_size
            return size
        elif hasattr(self.langchain_llm, "max_tokens"):
            tokens: int = self.langchain_llm.max_tokens
            return tokens
        else:
            # Conservative default
            return 8192

    @property
    def model(self) -> str:
        """Get model name."""
        return self._model_name
