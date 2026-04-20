"""Clause-aware chunking that preserves clause boundaries."""

from __future__ import annotations

import re

from contractex.chunking.base import ChunkingStrategy
from contractex.exceptions import ChunkingError


class ClauseAwareChunker(ChunkingStrategy):
    """
    Clause-aware chunking strategy that tries to keep legal clauses intact.

    This chunker identifies section headers and clause boundaries to avoid
    splitting in the middle of important provisions.
    """

    # Common patterns that indicate section/clause boundaries
    SECTION_PATTERNS = [
        r"^\d+\.",  # 1. Section
        r"^Article\s+\d+",  # Article 1
        r"^Section\s+\d+",  # Section 1
        r"^\([a-z]\)",  # (a) subsection
        r"^\([0-9]+\)",  # (1) subsection
        r"^\w+\s+TERMINATION",  # TERMINATION sections
    ]

    def __init__(
        self,
        max_chunk_size: int = 4000,
        overlap: int = 200,
        preserve_sentences: bool = True,
    ):
        """
        Initialize clause-aware chunker.

        Args:
            max_chunk_size: Maximum size of each chunk in tokens
            overlap: Number of tokens to overlap between chunks
            preserve_sentences: Try to split on sentence boundaries
        """
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap
        self.preserve_sentences = preserve_sentences

        # Compile patterns
        self.section_regex = re.compile(
            "|".join(self.SECTION_PATTERNS), re.MULTILINE | re.IGNORECASE
        )

    def chunk(self, text: str) -> list[str]:
        """
        Split text into chunks while preserving clause boundaries.

        Args:
            text: Full document text

        Returns:
            List of text chunks
        """
        try:
            # First, split into sections/clauses
            sections = self._split_into_sections(text)

            # Then, combine sections into chunks that fit max_chunk_size
            chunks = self._combine_sections(sections)

            return chunks

        except Exception as e:
            raise ChunkingError(f"Chunking failed: {str(e)}") from e

    def _split_into_sections(self, text: str) -> list[str]:
        """
        Split text into logical sections based on headers.

        Args:
            text: Text to split

        Returns:
            List of sections
        """
        sections = []
        lines = text.split("\n")

        current_section: list[str] = []

        for line in lines:
            # Check if line is a section header
            if self.section_regex.match(line.strip()):
                # Save previous section
                if current_section:
                    sections.append("\n".join(current_section))

                # Start new section
                current_section = [line]
            else:
                current_section.append(line)

        # Add last section
        if current_section:
            sections.append("\n".join(current_section))

        # If no sections were found, split by paragraphs
        if len(sections) <= 1:
            sections = text.split("\n\n")

        return [s.strip() for s in sections if s.strip()]

    def _combine_sections(self, sections: list[str]) -> list[str]:
        """
        Combine sections into chunks that fit within max_chunk_size.

        Args:
            sections: List of sections to combine

        Returns:
            List of chunks
        """
        chunks = []
        current_chunk: list[str] = []
        current_size = 0

        for section in sections:
            section_size = self.count_tokens(section)

            # If single section exceeds max size, split it
            if section_size > self.max_chunk_size:
                # Save current chunk if any
                if current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_size = 0

                # Split large section
                split_sections = self._split_large_section(section)
                chunks.extend(split_sections)

            # If adding this section would exceed max size, start new chunk
            elif current_size + section_size > self.max_chunk_size:
                chunks.append("\n\n".join(current_chunk))

                # Handle overlap
                if self.overlap > 0 and current_chunk:
                    overlap_text = current_chunk[-1][
                        -self.overlap * 4 :
                    ]  # Approximate chars from tokens
                    current_chunk = [overlap_text, section]
                    current_size = self.count_tokens(overlap_text) + section_size
                else:
                    current_chunk = [section]
                    current_size = section_size

            # Add section to current chunk
            else:
                current_chunk.append(section)
                current_size += section_size

        # Add final chunk
        if current_chunk:
            chunks.append("\n\n".join(current_chunk))

        return chunks

    def _split_large_section(self, section: str) -> list[str]:
        """
        Split a large section that exceeds max_chunk_size.

        Args:
            section: Section to split

        Returns:
            List of chunks
        """
        # Split by sentences if preserve_sentences is True
        if self.preserve_sentences:
            sentences = re.split(r"(?<=[.!?])\s+", section)
        else:
            # Split by character count
            char_limit = self.max_chunk_size * 4  # Convert tokens to chars
            sentences = [section[i : i + char_limit] for i in range(0, len(section), char_limit)]

        # Combine sentences into chunks
        chunks = []
        current: list[str] = []
        current_size = 0

        for sentence in sentences:
            sentence_size = self.count_tokens(sentence)

            if current_size + sentence_size > self.max_chunk_size:
                if current:
                    chunks.append(" ".join(current))
                current = [sentence]
                current_size = sentence_size
            else:
                current.append(sentence)
                current_size += sentence_size

        if current:
            chunks.append(" ".join(current))

        return chunks
