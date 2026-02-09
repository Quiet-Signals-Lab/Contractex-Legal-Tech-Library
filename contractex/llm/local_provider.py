"""Local LLM provider using Ollama for privacy-first deployments."""

from typing import Type, Optional
from pydantic import BaseModel
import os
import json

from contractex.llm.base import LLMProvider
from contractex.exceptions import LLMProviderError


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
        host: Optional[str] = None,
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
        except ImportError:
            raise LLMProviderError(
                "Ollama package not installed. Install with: pip install ollama"
            )
        
        # Check if model is available
        try:
            self.client.show(self._model)
        except Exception:
            raise LLMProviderError(
                f"Model '{self._model}' not found in Ollama. "
                f"Pull it first with: ollama pull {self._model}"
            )
    
    def extract_structured(
        self,
        prompt: str,
        schema: Type[BaseModel],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> BaseModel:
        """
        Extract structured data using local LLM with JSON mode.
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
            
            # Get completion with JSON format
            response = self.client.generate(
                model=self._model,
                prompt=enhanced_prompt,
                format='json',
                options={
                    'temperature': temperature,
                    'num_predict': max_tokens or self._max_tokens,
                }
            )
            
            # Parse JSON response
            content = response['response']
            
            # Parse and validate
            data = json.loads(content)
            return schema(**data)
            
        except Exception as e:
            raise LLMProviderError(f"Local LLM structured extraction failed: {str(e)}") from e
    
    def complete(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """Get text completion from local LLM."""
        try:
            response = self.client.generate(
                model=self._model,
                prompt=prompt,
                options={
                    'temperature': temperature,
                    'num_predict': max_tokens or self._max_tokens,
                }
            )
            
            return response['response']
            
        except Exception as e:
            raise LLMProviderError(f"Local LLM completion failed: {str(e)}") from e
    
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
