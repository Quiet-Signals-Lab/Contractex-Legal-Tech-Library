"""Semantic chunking based on sentence and paragraph boundaries."""

import re

from contractex.chunking.base import ChunkingStrategy
from contractex.exceptions import ChunkingError


class SemanticChunker(ChunkingStrategy):
    """
    Semantic chunking strategy that splits on natural language boundaries.

    Splits text into chunks based on paragraphs and sentences while
    maintaining semantic coherence.
    """

    def __init__(
        self,
        max_chunk_size: int = 4000,
        overlap: int = 200,
        split_on: str = "paragraph",  # 'paragraph' or 'sentence'
    ):
        """
        Initialize semantic chunker.

        Args:
            max_chunk_size: Maximum size of each chunk in tokens
            overlap: Number of tokens to overlap between chunks
            split_on: Primary split unit ('paragraph' or 'sentence')
        """
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap
        self.split_on = split_on

    def chunk(self, text: str) -> list[str]:
        """
        Split text into semantic chunks.

        Args:
            text: Full document text

        Returns:
            List of text chunks
        """
        try:
            if self.split_on == "paragraph":
                units = self._split_paragraphs(text)
            else:
                units = self._split_sentences(text)

            # Combine units into chunks
            chunks = self._combine_units(units)

            return chunks

        except Exception as e:
            raise ChunkingError(f"Semantic chunking failed: {str(e)}") from e

    def _split_paragraphs(self, text: str) -> list[str]:
        """Split text into paragraphs."""
        # Split on double newlines or 2+ newlines
        paragraphs = re.split(r"\n\s*\n", text)
        return [p.strip() for p in paragraphs if p.strip()]

    def _split_sentences(self, text: str) -> list[str]:
        """Split text into sentences."""
        # Split on sentence boundaries (.!?) followed by space and capital letter
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        return [s.strip() for s in sentences if s.strip()]

    def _combine_units(self, units: list[str]) -> list[str]:
        """
        Combine units into chunks that fit max_chunk_size.

        Args:
            units: List of paragraphs or sentences

        Returns:
            List of chunks
        """
        chunks = []
        current_chunk: list[str] = []
        current_size = 0

        for unit in units:
            unit_size = self.count_tokens(unit)

            # If single unit exceeds max size, split it further
            if unit_size > self.max_chunk_size:
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_size = 0

                # Force split large unit
                sub_chunks = self._force_split(unit)
                chunks.extend(sub_chunks)

            # Start new chunk if this would exceed max size
            elif current_size + unit_size > self.max_chunk_size:
                chunks.append("\n\n".join(current_chunk))

                # Add overlap
                if self.overlap > 0 and current_chunk:
                    overlap_text = current_chunk[-1][-self.overlap * 4 :]
                    current_chunk = [overlap_text, unit]
                    current_size = self.count_tokens(overlap_text) + unit_size
                else:
                    current_chunk = [unit]
                    current_size = unit_size

            # Add to current chunk
            else:
                current_chunk.append(unit)
                current_size += unit_size

        # Add final chunk
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    def _force_split(self, text: str) -> list[str]:
        """Force split text that exceeds max_chunk_size."""
        char_limit = self.max_chunk_size * 4  # Convert tokens to chars
        chunks = []

        for i in range(0, len(text), char_limit):
            chunk = text[i : i + char_limit]
            if chunk.strip():
                chunks.append(chunk.strip())

        return chunks
