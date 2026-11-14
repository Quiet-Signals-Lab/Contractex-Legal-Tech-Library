"""
Task options must do what they say: a document that is only partly read is
marked as such, ``severity_threshold`` filters, and an option that does
nothing says so.
"""

from __future__ import annotations

import logging
from typing import Any

import pytest

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType
from contractex.tasks import TaskRegistry
from tests._providers import SpyProvider

LONG = "The Supplier shall deliver the goods. " * 400  # about 15,000 characters
SHORT = "The Supplier shall deliver the goods."


def run(
    tasks: list[str], text: str, provider: SpyProvider | None = None, **task_kwargs: Any
) -> LegalDoc:
    provider = provider or SpyProvider()
    kwargs = {t: {"llm_provider": provider, **task_kwargs.get(t, {})} for t in tasks}
    pipeline = TaskRegistry.default().build_pipeline(tasks, task_kwargs=kwargs)
    return pipeline.run(LegalDoc(doc_type=DocType.CONTRACT, full_text=text))


class TestPartlyReadDocumentsAreMarked:
    @pytest.mark.parametrize("task_id", ["summarization", "timeline", "obligations"])
    def test_long_document_is_marked_truncated(self, task_id, caplog):
        with caplog.at_level(logging.WARNING, logger="contractex"):
            out = run([task_id], LONG)
        assert out.extracted["truncated"] == [task_id]
        assert any("12000" in r.getMessage() for r in caplog.records)

    @pytest.mark.parametrize("task_id", ["summarization", "timeline", "obligations"])
    def test_document_that_fits_is_not_marked(self, task_id):
        assert "truncated" not in run([task_id], SHORT).extracted

    def test_each_task_that_cut_the_document_is_listed_once(self):
        out = run(["timeline", "obligations", "summarization"], LONG)
        assert out.extracted["truncated"] == ["timeline", "obligations", "summarization"]

    def test_limit_is_the_tasks_own(self):
        out = run(["summarization"], SHORT, summarization={"max_input_chars": 10})
        assert out.extracted["truncated"] == ["summarization"]

    @pytest.mark.parametrize(("a", "b"), [(LONG, SHORT), (SHORT, LONG)])
    def test_comparison_is_marked_when_either_document_is_cut(self, a, b):
        pipeline = TaskRegistry.default().build_pipeline(
            ["comparison"], task_kwargs={"comparison": {"llm_provider": SpyProvider()}}
        )
        out = pipeline.run(LegalDoc(full_text=a), doc_b=LegalDoc(full_text=b))
        assert out.extracted["truncated"] == ["comparison"]


RISKS = {
    "risks": [
        {"risk_type": "unlimited_liability", "severity": "critical", "description": "No cap."},
        {"risk_type": "auto_renewal", "severity": "medium", "description": "Renews yearly."},
        {"risk_type": "notice_period", "severity": "info", "description": "30 days."},
    ]
}


class TestSeverityThreshold:
    def severities(self, **options: Any) -> list[str]:
        out = run(["risk_analysis"], SHORT, SpyProvider(structured=RISKS), risk_analysis=options)
        return [r.severity.value for r in out.extracted["risks"]]

    def test_default_keeps_every_risk(self):
        assert self.severities() == ["critical", "medium", "info"]

    @pytest.mark.parametrize(
        ("threshold", "kept"),
        [
            ("low", ["critical", "medium"]),
            ("medium", ["critical", "medium"]),
            ("high", ["critical"]),
        ],
    )
    def test_risks_below_the_threshold_are_dropped(self, threshold, kept):
        assert self.severities(severity_threshold=threshold) == kept

    def test_unknown_threshold_is_rejected(self):
        with pytest.raises(ValueError, match="severity_threshold"):
            self.severities(severity_threshold="severe")


class TestCitationUseLlm:
    def test_option_that_does_nothing_says_so(self):
        from contractex.tasks.citation import CitationTask

        with pytest.warns(DeprecationWarning, match="use_llm"):
            task = CitationTask(use_llm=True)
        # no model is called, so a blocked document need not be refused
        assert task.requires_llm is False

    def test_default_does_not_warn(self, recwarn):
        from contractex.tasks.citation import CitationTask

        CitationTask()
        assert not [w for w in recwarn if issubclass(w.category, DeprecationWarning)]
