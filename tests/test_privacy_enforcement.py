"""
End-to-end privacy enforcement: TaskPipeline, the built-in LLM tasks and
LegalRAGPipeline must never put a ``secret`` document in a prompt, never send a
``restricted`` document to a non-local provider, and always redact
``confidential`` and ``restricted`` text before it leaves the process.

Every provider here is a spy that records prompts; no network is used.
"""

from __future__ import annotations

import pytest

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType
from contractex.privacy import PrivacyProfile
from contractex.privacy.router import PrivacyBlockedError, PrivacyRoutingError
from contractex.tasks import LegalTask, TaskPipeline, TaskRegistry
from tests._providers import SpyLocalProvider, SpyProvider

SECRET_TEXT = "Project Falcon: acquire Acme at $4.2bn. Contact 415-555-0132."
PHONE = "415-555-0132"


def make_doc(sensitivity: str, text: str = SECRET_TEXT) -> LegalDoc:
    return LegalDoc(
        doc_type=DocType.CONTRACT,
        full_text=text,
        privacy_profile=PrivacyProfile(sensitivity=sensitivity),
    )


def run_task(task_id: str, doc: LegalDoc, provider, **run_kwargs) -> LegalDoc:
    pipeline = TaskRegistry.default().build_pipeline(
        [task_id], task_kwargs={task_id: {"llm_provider": provider}}
    )
    return pipeline.run(doc, **run_kwargs)


LLM_TASKS = ["summarization", "timeline", "obligations", "contract_extraction", "risk_analysis"]


# ---------------------------------------------------------------------------
# Built-in LLM tasks
# ---------------------------------------------------------------------------


class TestTaskEnforcement:
    def test_public_doc_reaches_provider(self):
        spy = SpyProvider()
        run_task("summarization", make_doc("public"), spy)
        assert any(SECRET_TEXT in p for p in spy.prompts)

    @pytest.mark.parametrize("task_id", LLM_TASKS)
    @pytest.mark.parametrize("provider_cls", [SpyProvider, SpyLocalProvider])
    def test_secret_doc_never_reaches_any_provider(self, task_id, provider_cls):
        spy = provider_cls()
        with pytest.raises(PrivacyBlockedError):
            run_task(task_id, make_doc("secret"), spy)
        assert spy.prompts == []

    @pytest.mark.parametrize("task_id", LLM_TASKS)
    def test_restricted_doc_rejected_by_cloud_provider(self, task_id):
        spy = SpyProvider()
        with pytest.raises(PrivacyRoutingError):
            run_task(task_id, make_doc("restricted"), spy)
        assert spy.prompts == []

    @pytest.mark.parametrize("task_id", ["summarization", "timeline", "obligations"])
    def test_restricted_doc_redacted_for_local_provider(self, task_id):
        local = SpyLocalProvider()
        run_task(task_id, make_doc("restricted"), local)
        assert local.prompts and all(PHONE not in p for p in local.prompts)

    @pytest.mark.parametrize("task_id", LLM_TASKS)
    def test_confidential_doc_redacted_on_every_call(self, task_id):
        spy = SpyProvider()
        run_task(task_id, make_doc("confidential"), spy)
        assert spy.prompts and all(PHONE not in p for p in spy.prompts)

    def test_comparison_enforces_the_second_document(self):
        spy = SpyProvider()
        with pytest.raises(PrivacyBlockedError):
            run_task("comparison", make_doc("public", "Plain text."), spy, doc_b=make_doc("secret"))
        assert spy.prompts == []

    def test_non_llm_tasks_still_run_on_secret_docs(self):
        pipeline = TaskRegistry.default().build_pipeline(["pii_detection", "citation"])
        out = pipeline.run(make_doc("secret", "See 17 U.S.C. § 107. Call 415-555-0132."))
        assert out.extracted["citations"]
        assert out.privacy_profile.sensitivity == "secret"


# ---------------------------------------------------------------------------
# TaskPipeline — custom tasks
# ---------------------------------------------------------------------------


class _CustomLLMTask(LegalTask):
    task_id = "custom_llm_task"
    requires_llm = True

    def __init__(self, provider) -> None:
        self.provider = provider

    def run(self, doc: LegalDoc, **kwargs) -> LegalDoc:
        self.provider.complete(doc.full_text)
        return doc


class TestPipelineEnforcement:
    def test_pipeline_refuses_llm_task_on_secret_doc(self):
        spy = SpyProvider()
        with pytest.raises(PrivacyBlockedError):
            TaskPipeline([_CustomLLMTask(spy)]).run(make_doc("secret"))
        assert spy.prompts == []

    @pytest.mark.asyncio
    async def test_async_pipeline_refuses_llm_task_on_secret_doc(self):
        spy = SpyProvider()
        with pytest.raises(PrivacyBlockedError):
            await TaskPipeline([_CustomLLMTask(spy)]).run_async(make_doc("secret"))
        assert spy.prompts == []

    def test_pipeline_runs_llm_task_on_public_doc(self):
        spy = SpyProvider()
        TaskPipeline([_CustomLLMTask(spy)]).run(make_doc("public"))
        assert spy.prompts == [SECRET_TEXT]


# ---------------------------------------------------------------------------
# LegalRAGPipeline
# ---------------------------------------------------------------------------


class _ConstantEmbedder:
    def encode(self, text):
        return [1.0, 0.0]


@pytest.fixture
def rag_factory(monkeypatch):
    from contractex.rag import LegalRAGPipeline

    monkeypatch.setattr(LegalRAGPipeline, "_get_embedder", lambda self: _ConstantEmbedder())

    def make(provider):
        return LegalRAGPipeline(llm_provider=provider, conflict_detector=None)

    return make


class TestRAGEnforcement:
    def test_ingest_legaldocs(self, rag_factory):
        rag = rag_factory(SpyProvider())
        result = rag.ingest([make_doc("public", "Governing law is Delaware.")])
        assert result.ingested == 1 and result.failed == 0

    def test_query_context_respects_every_sensitivity(self, rag_factory):
        spy = SpyProvider()
        rag = rag_factory(spy)
        rag.ingest(
            [
                make_doc("public", "PUBLIC-CLAUSE governing law is Delaware."),
                make_doc("confidential", "CONF-CLAUSE contact 415-555-0132."),
                make_doc("restricted", "RESTRICTED-CLAUSE merger terms."),
                make_doc("secret", "SECRET-CLAUSE board minutes."),
            ]
        )
        rag.query("What is the governing law?", top_k=10)
        (prompt,) = spy.prompts
        assert "PUBLIC-CLAUSE" in prompt and "CONF-CLAUSE" in prompt
        assert PHONE not in prompt
        assert "RESTRICTED-CLAUSE" not in prompt and "SECRET-CLAUSE" not in prompt

    def test_local_provider_may_see_restricted_but_never_secret(self, rag_factory):
        local = SpyLocalProvider()
        rag = rag_factory(local)
        rag.ingest(
            [
                make_doc("restricted", "RESTRICTED-CLAUSE merger terms."),
                make_doc("secret", "SECRET-CLAUSE board minutes."),
            ]
        )
        rag.query("Summarise.", top_k=10)
        (prompt,) = local.prompts
        assert "RESTRICTED-CLAUSE" in prompt and "SECRET-CLAUSE" not in prompt

    def test_ingest_path_as_public(self, rag_factory, tmp_path):
        path = tmp_path / "msa.txt"
        path.write_text("PATH-CLAUSE governing law is Delaware.", encoding="utf-8")
        spy = SpyProvider()
        rag = rag_factory(spy)
        assert rag.ingest([path]).ingested == 1
        rag.query("Governing law?")
        assert "PATH-CLAUSE" in spy.prompts[0]

    def test_streaming_query_is_redacted(self, rag_factory):
        spy = SpyProvider(reply="answer")
        rag = rag_factory(spy)
        rag.ingest([make_doc("confidential", "CONF-CLAUSE contact 415-555-0132.")])
        final = list(rag.query("Who to contact?", stream=True))[-1]
        assert final.answer == "answer"
        assert "CONF-CLAUSE" in spy.prompts[0] and PHONE not in spy.prompts[0]


# ---------------------------------------------------------------------------
# No implicit provider: the library never picks a vendor or model
# ---------------------------------------------------------------------------


class TestNoDefaultProvider:
    def test_task_without_provider_raises(self):
        pipeline = TaskRegistry.default().build_pipeline(["summarization"])
        with pytest.raises(ValueError, match="no LLM provider configured"):
            pipeline.run(make_doc("public"))

    def test_contract_extractor_without_provider_raises(self):
        from contractex.core.extractors import ContractExtractor

        with pytest.raises(ValueError, match="No LLM provider configured"):
            ContractExtractor()

    @pytest.mark.parametrize("name", ["openai", "anthropic", "gpt", "Claude"])
    def test_vendor_name_without_model_raises(self, name):
        from contractex.core.extractors import ContractExtractor

        with pytest.raises(ValueError, match="does not name a model"):
            ContractExtractor._create_provider(name)

    def test_extract_contract_requires_llm(self):
        import inspect

        from contractex import extract_contract

        assert inspect.signature(extract_contract).parameters["llm"].default is inspect._empty


def test_classification_task_labels_text_without_llm():
    doc = make_doc("secret", "Either party may terminate for convenience on 30 days notice.")
    out = TaskRegistry.default().build_pipeline(["classification"]).run(doc)
    assert "termination_for_convenience" in out.extracted["cuad_labels"]
