"""Custom exceptions for ContractEx."""

from __future__ import annotations


class ContractExError(Exception):
    """Base exception for all ContractEx errors."""

    pass


class DocumentLoadError(ContractExError):
    """Raised when a document cannot be loaded or parsed."""

    pass


class ExtractionError(ContractExError):
    """Raised when extraction fails."""

    pass


class LLMProviderError(ContractExError):
    """Raised when LLM provider encounters an error."""

    pass


class ValidationError(ContractExError):
    """Raised when extracted data fails validation."""

    pass


class ChunkingError(ContractExError):
    """Raised when document chunking fails."""

    pass


class ClassificationError(ContractExError):
    """Raised when clause classification fails."""

    pass


class UnsupportedFileTypeError(DocumentLoadError):
    """Raised when attempting to load an unsupported file type."""

    pass


class ConfidenceThresholdError(ValidationError):
    """Raised when extraction confidence is below threshold."""

    pass
