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


# ---------------------------------------------------------------------------
# One public name, one class
# ---------------------------------------------------------------------------


def test_risk_severity_is_one_enum():
    from contractex.core.models import RiskSeverity
    from contractex.playbooks import RiskSeverity as PlaybookSeverity

    assert PlaybookSeverity is RiskSeverity


def test_playbook_analyzer_returns_playbook_flags():
    from contractex import PlaybookFlag, RiskAnalyzer, RiskFlag, StandardNDAPlaybook

    clause = type("C", (), {"clause_type": "indemnification", "text": "Recipient shall pay."})()
    flags = RiskAnalyzer(StandardNDAPlaybook()).analyze(type("R", (), {"clauses": [clause]})())
    assert flags
    assert all(isinstance(f, PlaybookFlag) for f in flags)
    assert PlaybookFlag is not RiskFlag  # RiskFlag is the item type of Contract.risks


def test_old_names_still_import_with_a_deprecation_warning():
    import pytest

    import contractex.analysis
    import contractex.analysis.risk
    import contractex.core.analyzers

    with pytest.warns(DeprecationWarning, match="PlaybookFlag"):
        assert contractex.analysis.RiskFlag is contractex.analysis.PlaybookFlag
    with pytest.warns(DeprecationWarning, match="PlaybookFlag"):
        assert contractex.analysis.risk.RiskFlag is contractex.analysis.PlaybookFlag
    with pytest.warns(DeprecationWarning, match="LLMRiskAnalyzer"):
        assert contractex.core.analyzers.RiskAnalyzer is contractex.core.analyzers.LLMRiskAnalyzer
