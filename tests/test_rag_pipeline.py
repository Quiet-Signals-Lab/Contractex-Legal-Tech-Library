"""
LegalRAGPipeline behaviour other than the routing matrix (which is in
test_privacy_enforcement.py): metadata filters, the profile stored for
unprofiled documents, source sync, citation strings and the conflict prompt.

Every provider is a spy and the embedder is a constant; no network is used.
"""

from __future__ import annotations

import pytest

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType
from contractex.privacy import PrivacyAwareLLMRouter, PrivacyProfile
from contractex.privacy.router import PrivacyBlockedError, PrivacyRoutingError
from contractex.rag import ConflictDetector, LegalRAGPipeline
from contractex.rag.conflict import Conflict, ConflictType
from contractex.taxonomy.authority import AuthorityLevel, AuthorityProfile
from tests._providers import SpyLocalProvider, SpyProvider

PHONE = "415-555-0132"


class _ConstantEmbedder:
    def encode(self, text):
        return [1.0, 0.0]


@pytest.fixture(autouse=True)
def constant_embedder(monkeypatch):
    monkeypatch.setattr(LegalRAGPipeline, "_get_embedder", lambda self: _ConstantEmbedder())


def make_rag(provider, **kwargs) -> LegalRAGPipeline:
    kwargs.setdefault("conflict_detector", None)
    return LegalRAGPipeline(llm_provider=provider, **kwargs)


# ---------------------------------------------------------------------------
# Metadata filters
# ---------------------------------------------------------------------------


class TestFilters:
    def test_doc_type_filter_excludes_other_documents(self):
        spy = SpyProvider()
        rag = make_rag(spy)
        rag.ingest(
            [
                LegalDoc(doc_type=DocType.STATUTE, full_text="STATUTE-TEXT erase after 30 days."),
                LegalDoc(doc_type=DocType.CONTRACT, full_text="CONTRACT-TEXT retain for 10 years."),
            ]
        )
        rag.query("Retention?", filters={"doc_type": "statute"})
        (prompt,) = spy.prompts
        assert "STATUTE-TEXT" in prompt
        assert "CONTRACT-TEXT" not in prompt

    def test_filter_on_source_keeps_other_matters_out_of_the_prompt(self):
        spy = SpyProvider()
        rag = make_rag(spy)
        ours = LegalDoc(full_text="OUR-MATTER governing law is Delaware.")
        theirs = LegalDoc(full_text="OTHER-MATTER governing law is Texas.")
        rag.ingest([ours, theirs])
        rag.query("Governing law?", filters={"source_url": ours.doc_id})
        (prompt,) = spy.prompts
        assert "OUR-MATTER" in prompt and "OTHER-MATTER" not in prompt

    def test_no_filter_returns_everything(self):
        spy = SpyProvider()
        rag = make_rag(spy)
        rag.ingest([LegalDoc(full_text="FIRST-TEXT."), LegalDoc(full_text="SECOND-TEXT.")])
        rag.query("Anything?")
        assert "FIRST-TEXT" in spy.prompts[0] and "SECOND-TEXT" in spy.prompts[0]


# ---------------------------------------------------------------------------
# Unprofiled documents take the router's default profile
# ---------------------------------------------------------------------------


class TestRouterDefaultProfile:
    TEXT = f"UNPROFILED-TEXT call {PHONE}."

    def _router(self, sensitivity: str) -> PrivacyAwareLLMRouter:
        return PrivacyAwareLLMRouter(default_profile=PrivacyProfile(sensitivity=sensitivity))

    def test_restricted_default_keeps_unprofiled_doc_from_cloud_provider(self):
        spy = SpyProvider()
        rag = make_rag(spy, privacy_router=self._router("restricted"))
        public = LegalDoc(
            full_text="EXPLICIT-PUBLIC text.", privacy_profile=PrivacyProfile(sensitivity="public")
        )
        rag.ingest([LegalDoc(full_text=self.TEXT), public])
        rag.query("Phone?")
        (prompt,) = spy.prompts
        assert "EXPLICIT-PUBLIC" in prompt
        assert "UNPROFILED-TEXT" not in prompt and PHONE not in prompt

    def test_restricted_default_with_nothing_else_to_show_refuses_cloud_provider(self):
        spy = SpyProvider()
        rag = make_rag(spy, privacy_router=self._router("restricted"))
        rag.ingest([LegalDoc(full_text=self.TEXT)])
        with pytest.raises(PrivacyRoutingError):
            rag.query("Phone?")
        assert spy.prompts == []

    def test_restricted_default_redacts_unprofiled_doc_for_local_provider(self):
        local = SpyLocalProvider()
        rag = make_rag(local, privacy_router=self._router("restricted"))
        rag.ingest([LegalDoc(full_text=self.TEXT)])
        rag.query("Phone?")
        (prompt,) = local.prompts
        assert "UNPROFILED-TEXT" in prompt and PHONE not in prompt

    def test_secret_default_keeps_unprofiled_doc_from_every_provider(self):
        local = SpyLocalProvider()
        rag = make_rag(local, privacy_router=self._router("secret"))
        rag.ingest([LegalDoc(full_text=self.TEXT)])
        with pytest.raises(PrivacyBlockedError):
            rag.query("Phone?")
        assert local.prompts == []

    def test_explicit_profile_wins_over_router_default(self):
        spy = SpyProvider()
        rag = make_rag(spy, privacy_router=self._router("restricted"))
        doc = LegalDoc(
            full_text="EXPLICIT-PUBLIC text.", privacy_profile=PrivacyProfile(sensitivity="public")
        )
        rag.ingest([doc])
        rag.query("Text?")
        assert "EXPLICIT-PUBLIC" in spy.prompts[0]

    def test_paths_stay_public_under_a_strict_default(self, tmp_path):
        path = tmp_path / "msa.txt"
        path.write_text("PATH-CLAUSE governing law is Delaware.", encoding="utf-8")
        spy = SpyProvider()
        rag = make_rag(spy, privacy_router=self._router("restricted"))
        assert rag.ingest([path]).ingested == 1
        rag.query("Governing law?")
        assert "PATH-CLAUSE" in spy.prompts[0]


# ---------------------------------------------------------------------------
# sync_sources
# ---------------------------------------------------------------------------


class _FakeWeb:
    """Stands in for the loader: serves ``pages[url]`` and counts fetches."""

    def __init__(self, monkeypatch, pages: dict[str, str]) -> None:
        from contractex.loaders.auto import AutoLoader
        from contractex.loaders.source_adapter import URLLoader

        self.pages = pages
        self.fetches = 0
        web = self

        def load(self, source: str) -> str:
            web.fetches += 1
            if web.fetches > 50:
                raise AssertionError("sync_sources keeps re-fetching the same URL")
            return web.pages[source]

        def not_a_file(self, source: str) -> str:
            raise AssertionError(f"{source} is a URL but was loaded as a file")

        monkeypatch.setattr(URLLoader, "load", load)
        monkeypatch.setattr(AutoLoader, "load", not_a_file)


class TestSyncSources:
    URL = "https://example.com/terms"

    def test_sync_terminates_and_does_not_duplicate_unchanged_source(self, monkeypatch):
        web = _FakeWeb(monkeypatch, {self.URL: "URL-TEXT version one."})
        rag = make_rag(SpyProvider())
        rag.ingest([self.URL])
        chunks = len(rag._vector_store)

        result = rag.sync_sources()

        assert (result.checked, result.updated, result.unchanged) == (1, 0, 1)
        assert result.errors == []
        assert len(rag._vector_store) == chunks
        assert web.fetches == 2  # one ingest, one sync

    def test_sync_replaces_changed_source(self, monkeypatch):
        web = _FakeWeb(monkeypatch, {self.URL: "OLD-TEXT version one."})
        spy = SpyProvider()
        rag = make_rag(spy)
        rag.ingest([self.URL])
        web.pages[self.URL] = "NEW-TEXT version two."

        result = rag.sync_sources()
        assert (result.checked, result.updated, result.unchanged) == (1, 1, 0)

        rag.query("Which version?")
        assert "NEW-TEXT" in spy.prompts[0] and "OLD-TEXT" not in spy.prompts[0]

        # A second sync finds nothing new and still checks the URL only once
        assert rag.sync_sources().checked == 1
        assert len(rag._vector_store) == 1

    def test_sync_reports_fetch_errors_and_keeps_the_old_copy(self, monkeypatch):
        web = _FakeWeb(monkeypatch, {self.URL: "KEPT-TEXT version one."})
        spy = SpyProvider()
        rag = make_rag(spy)
        rag.ingest([self.URL])
        del web.pages[self.URL]  # the next fetch raises

        result = rag.sync_sources()
        assert (result.checked, result.updated, result.unchanged) == (1, 0, 0)
        assert len(result.errors) == 1 and self.URL in result.errors[0]

        rag.query("Which version?")
        assert "KEPT-TEXT" in spy.prompts[0]

    def test_ingesting_the_same_url_twice_replaces_the_first_copy(self, monkeypatch):
        _FakeWeb(monkeypatch, {self.URL: "URL-TEXT version one."})
        rag = make_rag(SpyProvider())
        rag.ingest([self.URL])
        rag.ingest([self.URL])
        assert len(rag._vector_store) == 1


# ---------------------------------------------------------------------------
# Citations
# ---------------------------------------------------------------------------


class TestCitationStrings:
    @pytest.mark.parametrize(
        ("style", "expected"),
        [
            ("inline", "({src}, {src})"),
            ("footnote", "[1] {src} <{src}>."),
            ("bluebook", "{src} ({src})."),
        ],
    )
    def test_citation_string_is_populated_in_the_requested_style(self, style, expected):
        rag = make_rag(SpyProvider(), citation_format=style)
        doc = LegalDoc(full_text="Governing law is Delaware.")
        rag.ingest([doc])
        response = rag.query("Governing law?")
        assert [c.citation_string for c in response.citations] == [expected.format(src=doc.doc_id)]

    def test_streaming_responses_carry_citation_strings(self):
        rag = make_rag(SpyProvider(reply="answer"))
        rag.ingest([LegalDoc(full_text="Governing law is Delaware.")])
        final = list(rag.query("Governing law?", stream=True))[-1]
        assert final.citations and all(c.citation_string for c in final.citations)


# ---------------------------------------------------------------------------
# Conflict prompt
# ---------------------------------------------------------------------------


def _authority(year: int) -> AuthorityProfile:
    return AuthorityProfile(level=AuthorityLevel.BINDING_STATUTE, publication_year=year)


class TestConflictPrompt:
    def test_date_difference_alone_is_not_presented_as_conflicting_positions(self):
        spy = SpyProvider()
        rag = make_rag(spy, conflict_detector=ConflictDetector())
        same = "Personal data must be erased when no longer necessary."
        rag.ingest(
            [
                LegalDoc(full_text=same, authority_profile=_authority(2016)),
                LegalDoc(full_text=same, authority_profile=_authority(2024)),
            ]
        )
        response = rag.query("When must data be erased?")

        assert [c.conflict_type for c in response.conflicts] == [ConflictType.TEMPORAL_CONFLICT]
        (prompt,) = spy.prompts
        assert "2016" in prompt and "2024" in prompt  # the model is still told about the dates
        assert "CONFLICTING SOURCES DETECTED" not in prompt
        assert "contain conflicting positions" not in prompt
        assert "You MUST present BOTH positions" not in prompt

    @pytest.mark.parametrize("conflict_type", list(ConflictType))
    def test_a_metadata_difference_is_never_announced_as_a_disagreement(self, conflict_type):
        # The detector compares jurisdiction, authority and dates.  It never
        # reads the sources, so it cannot know that they disagree.
        conflict = Conflict(
            conflict_type=conflict_type,
            source_a_id="a",
            source_b_id="b",
            description="Source A applies to US-CA while Source B applies to US-TX.",
        )
        addendum = ConflictDetector().build_conflict_prompt_addendum([conflict])
        assert "US-CA" in addendum
        assert "CONFLICTING SOURCES DETECTED" not in addendum
        assert "contain conflicting positions" not in addendum
        assert "You MUST present BOTH positions" not in addendum
        # the model is still told what to do if they do disagree
        assert "If they take different positions" in addendum
        assert "Do not merge them into one answer" in addendum

    def test_no_conflicts_adds_nothing(self):
        assert ConflictDetector().build_conflict_prompt_addendum([]) == ""
