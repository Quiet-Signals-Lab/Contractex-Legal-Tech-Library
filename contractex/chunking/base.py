"""Abstract base class for document chunking strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ChunkingStrategy(ABC):
    """Abstract base class for document chunking strategies."""

    @abstractmethod
    def chunk(self, text: str) -> list[str]:
        """
        Split text into chunks.

        Args:
            text: Full document text to chunk

        Returns:
            List of text chunks

        Raises:
            ChunkingError: If chunking fails
        """
        pass

    def count_tokens(self, text: str) -> int:
        """
        Estimate token count for text.

        Args:
            text: Text to count tokens for

        Returns:
            Approximate token count
        """
        # Rough estimate: 1 token ≈ 4 characters
        return len(text) // 4
