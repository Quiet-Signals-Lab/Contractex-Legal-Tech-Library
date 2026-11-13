"""The top-level package: what it exports and how it behaves as a library."""

from __future__ import annotations

import logging
from importlib import resources

import contractex


def test_everything_in_all_is_importable():
    missing = [name for name in contractex.__all__ if getattr(contractex, name, None) is None]
    assert missing == []


def test_exceptions_are_importable_from_the_top_level():
    from contractex import ContractExError, DocumentLoadError, ExtractionError, LLMProviderError

    for exc in (DocumentLoadError, ExtractionError, LLMProviderError):
        assert issubclass(exc, ContractExError)
    assert "ContractExError" in contractex.__all__


def test_core_components_are_exported_not_optional():
    from contractex.privacy import PrivacyProfile
    from contractex.rag import LegalRAGPipeline
    from contractex.tasks import TaskRegistry

    assert contractex.PrivacyProfile is PrivacyProfile
    assert contractex.TaskRegistry is TaskRegistry
    assert contractex.LegalRAGPipeline is LegalRAGPipeline
    assert {"PrivacyProfile", "TaskRegistry", "LegalRAGPipeline"} <= set(contractex.__all__)


def test_package_ships_type_marker():
    assert resources.files("contractex").joinpath("py.typed").is_file()


def test_library_logger_has_a_null_handler():
    handlers = logging.getLogger("contractex").handlers
    assert any(isinstance(h, logging.NullHandler) for h in handlers)
