"""
The ``risk_analysis`` task next to ``contract_extraction``: the risk prompt is
sent once, a failed model call is visible in the result, and a contract's
``prompt_versions`` name only the prompts that ran.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel

from contractex.core.document import LegalDoc
from contractex.core.extractors import ContractExtractor
from contractex.core.legal_document import DocType
from contractex.tasks import TaskRegistry
from tests._providers import SpyProvider

TEXT = "1. Term\nThis Agreement runs for two years.\n\n2. Liability\nLiability is unlimited."
RISK_PROMPT = "seasoned contract attorney"


class _FailingProvider(SpyProvider):
    def extract_structured(self, prompt: str, schema: type[BaseModel], **kwargs: Any) -> BaseModel:
        self.prompts.append(prompt)
        raise RuntimeError("401 invalid x-api-key\nprompt was: " + prompt)


def run(tasks: list[str], provider: SpyProvider, **task_kwargs: dict[str, Any]) -> LegalDoc:
    kwargs = {t: {"llm_provider": provider, **task_kwargs.get(t, {})} for t in tasks}
    pipeline = TaskRegistry.default().build_pipeline(tasks, task_kwargs=kwargs)
    return pipeline.run(LegalDoc(doc_type=DocType.CONTRACT, full_text=TEXT))


def risk_prompts(spy: SpyProvider) -> int:
    return sum(RISK_PROMPT in p for p in spy.prompts)


class TestRiskPromptIsSentOnce:
    def test_documented_pipeline(self):
        spy = SpyProvider()
        out = run(["contract_extraction", "risk_analysis"], spy)
        assert risk_prompts(spy) == 1
        assert len(out.extracted["risks"]) == len(out.extracted["contract"]["risks"])

    def test_risk_task_asks_the_model_when_extraction_did_not(self):
        spy = SpyProvider()
        run(
            ["contract_extraction", "risk_analysis"],
            spy,
            contract_extraction={"analyze_risks": False},
        )
        assert risk_prompts(spy) == 1

    def test_risk_task_on_its_own_asks_the_model(self):
        spy = SpyProvider()
        out = run(["risk_analysis"], spy)
        assert risk_prompts(spy) == 1
        assert out.extracted["risk_warnings"] == []


class TestFailedModelCallIsVisible:
    def test_failure_is_listed_in_risk_warnings(self):
        out = run(["risk_analysis"], _FailingProvider())
        (warning,) = out.extracted["risk_warnings"]
        assert "401 invalid x-api-key" in warning
        assert TEXT not in warning  # first line of the error only
        assert out.extracted["risks"] == []  # rule results only


class TestPromptVersions:
    @pytest.mark.parametrize(
        ("options", "expected"),
        [
            (
                {"analyze_risks": False, "extract_financial": False},
                {"contract_info", "clause_extraction"},
            ),
            (
                {"analyze_risks": True, "extract_financial": True},
                {"contract_info", "clause_extraction", "financial_extraction", "risk_analysis"},
            ),
        ],
    )
    def test_only_the_prompts_that_ran_are_recorded(self, options, expected):
        contract = ContractExtractor(llm_provider=SpyProvider()).extract_from_text(TEXT, **options)
        assert set(contract.metadata.prompt_versions) == expected
