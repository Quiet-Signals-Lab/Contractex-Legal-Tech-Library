"""
Privacy layer unit tests: PrivacyProfile, PIIDetector, PIIRedactor,
PrivacyAwareLLMRouter.

The detector is pinned to the regex fallback (``use_presidio=False``) so the
suite is deterministic and runs without the ``privacy`` extra.  Tests marked
``xfail(strict=True)`` document known defects; each fix flips one to passing.
"""

from __future__ import annotations

import sys

import pytest
from pydantic import BaseModel

from contractex.privacy import (
    PIIDetector,
    PIIRedactor,
    PrivacyAwareLLMRouter,
    PrivacyProfile,
    RedactionStrategy,
)
from contractex.privacy.detector import PIISpan, RegexPIIRecognizer
from contractex.privacy.router import PrivacyBlockedError, PrivacyRoutingError
from tests._providers import SpyLocalProvider, SpyProvider


def defect(reason: str):
    return pytest.mark.xfail(strict=True, reason=f"known defect: {reason}")


class Doc:
    """Minimal duck-typed document, as the router accepts any object."""

    def __init__(self, profile=None, language: str = "en") -> None:
        if profile is not None:
            self.privacy_profile = profile
        self.language = language


@pytest.fixture
def detector() -> PIIDetector:
    return PIIDetector(use_presidio=False)


@pytest.fixture
def router(detector) -> PrivacyAwareLLMRouter:
    return PrivacyAwareLLMRouter(detector=detector)


def redact_all(detector: PIIDetector, text: str) -> str:
    return PIIRedactor().redact(text, detector.detect(text)).text


# ---------------------------------------------------------------------------
# PrivacyProfile
# ---------------------------------------------------------------------------


class TestPrivacyProfile:
    @pytest.mark.parametrize(
        ("sensitivity", "routing"),
        [
            ("public", "any"),
            ("confidential", "any"),
            ("restricted", "local_only"),
            ("secret", "blocked"),
        ],
    )
    def test_routing_derived_from_sensitivity(self, sensitivity, routing):
        assert PrivacyProfile(sensitivity=sensitivity).llm_routing == routing

    def test_explicit_routing_override_wins(self):
        p = PrivacyProfile(sensitivity="public", llm_routing="blocked")
        assert p.is_blocked

    @pytest.mark.parametrize(
        ("sensitivity", "needs"),
        [("public", False), ("confidential", True), ("restricted", True), ("secret", False)],
    )
    def test_requires_redaction(self, sensitivity, needs):
        assert PrivacyProfile(sensitivity=sensitivity).requires_redaction is needs

    def test_unknown_sensitivity_rejected(self):
        with pytest.raises(ValueError):
            PrivacyProfile(sensitivity="top-secret")


# ---------------------------------------------------------------------------
# PIIDetector — regex fallback
# ---------------------------------------------------------------------------


class TestDetectorRegexFallback:
    def test_not_using_presidio(self, detector):
        assert detector.using_presidio is False

    def test_empty_text(self, detector):
        assert detector.detect("") == []

    @pytest.mark.parametrize(
        ("entity", "text", "value"),
        [
            ("PHONE_NUMBER", "Call 415-555-0132 today", "415-555-0132"),
            ("PASSPORT_NUMBER", "Passport X1234567 issued", "X1234567"),
            ("DATE_OF_BIRTH", "DOB: 04/05/1985.", "04/05/1985"),
        ],
    )
    def test_detects(self, detector, entity, text, value):
        spans = detector.detect(text)
        assert [(s.entity_type, s.text) for s in spans] == [(entity, value)]
        assert text[spans[0].start : spans[0].end] == value

    @pytest.mark.parametrize(
        ("entity", "text", "value"),
        [
            ("EMAIL_ADDRESS", "Mail jane.doe@acme.com now", "jane.doe@acme.com"),
            ("US_SSN", "SSN 123-45-6789 on file", "123-45-6789"),
            ("CREDIT_CARD", "Card 4111 1111 1111 1111 expires", "4111 1111 1111 1111"),
            ("IBAN_CODE", "IBAN GB82WEST12345698765432 ok", "GB82WEST12345698765432"),
        ],
    )
    def test_detects_high_threshold_entities(self, detector, entity, text, value):
        assert (entity, value) in [(s.entity_type, s.text) for s in detector.detect(text)]

    def test_known_limitation_no_person_or_location_without_presidio(self, detector):
        """The regex fallback has no name or place recogniser.  Documented, not fixed."""
        spans = detector.detect("Jane Doe of 10 Downing Street, London signed.")
        assert not {s.entity_type for s in spans} & {"PERSON", "LOCATION", "ORGANIZATION"}

    def test_parenthesised_area_code_digits_covered(self, detector):
        assert redact_all(detector, "Call (415) 555-0132 today") == "Call (<PHONE_NUMBER_1> today"

    def test_spans_sorted_and_offsets_exact(self, detector):
        text = "DOB: 01/02/1990 then call 415-555-0132 and passport X7654321"
        spans = detector.detect(text)
        assert [s.start for s in spans] == sorted(s.start for s in spans)
        for s in spans:
            assert text[s.start : s.end] == s.text

    def test_entities_filter(self):
        d = PIIDetector(entities=["PHONE_NUMBER"], use_presidio=False)
        assert [s.entity_type for s in d.detect("415-555-0132, DOB: 01/02/1990")] == [
            "PHONE_NUMBER"
        ]

    def test_custom_recognizer(self, detector):
        detector.add_recognizer(RegexPIIRecognizer(entity_type="CASE_NO", pattern=r"CX-\d{5}"))
        spans = detector.detect("Matter CX-12345 opened")
        assert [(s.entity_type, s.text) for s in spans] == [("CASE_NO", "CX-12345")]

    def test_custom_recognizer_language_scoped(self, detector):
        detector.add_recognizer(
            RegexPIIRecognizer(entity_type="RO_ID", pattern=r"\b\d{13}\b", languages=["ro"])
        )
        assert detector.detect("ID 1234567890123", language="en") == []
        assert detector.detect("ID 1234567890123", language="ro")[0].entity_type == "RO_ID"

    def test_threshold_override_can_suppress(self, detector):
        detector.set_threshold("PHONE_NUMBER", 0.99)
        assert detector.detect("Call 415-555-0132") == []


class TestDetectorAdversarial:
    """PII that is disguised so a naive pattern misses it must still be redacted."""

    def test_zero_width_space_inside_phone(self, detector):
        text = "Call 415-555\u200b-0132 now"
        assert "0132" not in redact_all(detector, text)

    @pytest.mark.parametrize("dash", ["\u2010", "\u2011", "\u2013", "\u2212"])
    def test_unicode_dash_in_phone(self, detector, dash):
        text = f"Call 415{dash}555{dash}0132 now"
        assert "0132" not in redact_all(detector, text)

    def test_unicode_dash_in_ssn(self, detector):
        assert "6789" not in redact_all(detector, "SSN 123\u201345\u20136789 on file")

    def test_zero_width_joiner_inside_email(self, detector):
        assert "acme" not in redact_all(detector, "Mail jane\u200d.doe@acme.com now")

    def test_offsets_index_original_text_when_format_chars_present(self, detector):
        text = "\ufeffCall 415-555\u200b-0132 now"
        (s,) = detector.detect(text)
        assert text[s.start : s.end] == s.text == "415-555\u200b-0132"

    def test_fullwidth_digits_in_phone(self, detector):
        # Python's \d matches any Unicode decimal digit, so this already works.
        text = "Call \uff14\uff11\uff15-\uff15\uff15\uff15-\uff10\uff11\uff13\uff12 now"
        assert "\uff10\uff11\uff13\uff12" not in redact_all(detector, text)

    def test_cyrillic_homoglyph_in_email_local_part(self, detector):
        text = "Mail j\u0430ne.doe@acme.com now"  # U+0430 CYRILLIC SMALL LETTER A
        redacted = redact_all(detector, text)
        assert "@acme.com" not in redacted
        assert "j\u0430ne" not in redacted

    def test_overlapping_detections_redact_union(self, detector):
        detector.add_recognizer(RegexPIIRecognizer(entity_type="ACCT", pattern=r"ACCT-\d{4}"))
        detector.add_recognizer(RegexPIIRecognizer(entity_type="SORT", pattern=r"\d{4}-\d{4}"))
        redacted = redact_all(detector, "Pay ACCT-1234-5678 today")
        assert "1234" not in redacted and "5678" not in redacted


# ---------------------------------------------------------------------------
# PIIRedactor
# ---------------------------------------------------------------------------


def span(text: str, value: str, entity: str = "PERSON", score: float = 0.9) -> PIISpan:
    start = text.index(value)
    return PIISpan(entity, start, start + len(value), score, value)


class TestRedactorReplace:
    def test_placeholder_and_roundtrip(self):
        text = "Jane Doe signed for Acme."
        r = PIIRedactor().redact(text, [span(text, "Jane Doe")])
        assert r.text == "<PERSON_1> signed for Acme."
        assert r.span_count == 1 and r.entity_types_redacted == {"PERSON"}
        assert PIIRedactor().restore(r.text, r.redaction_map) == text

    def test_same_value_same_placeholder(self):
        text = "Jane met Bob. Jane left."
        spans = [
            PIISpan("PERSON", 0, 4, 0.9, "Jane"),
            PIISpan("PERSON", 9, 12, 0.9, "Bob"),
            PIISpan("PERSON", 14, 18, 0.9, "Jane"),
        ]
        r = PIIRedactor().redact(text, spans)
        assert r.text.count(r.redaction_map.original_to_placeholder["Jane"]) == 2
        assert PIIRedactor().restore(r.text, r.redaction_map) == text

    def test_ten_plus_placeholders_restore_exactly(self):
        names = [f"Name{i:02d}" for i in range(12)]
        text = " ".join(names)
        spans, pos = [], 0
        for n in names:
            spans.append(PIISpan("PERSON", pos, pos + len(n), 0.9, n))
            pos += len(n) + 1
        r = PIIRedactor().redact(text, spans)
        assert "<PERSON_1>" in r.text and "<PERSON_12>" in r.text
        assert PIIRedactor().restore(r.text, r.redaction_map) == text

    def test_restore_ignores_unknown_placeholders(self):
        text = "Jane signed."
        r = PIIRedactor().redact(text, [span(text, "Jane")])
        out = PIIRedactor().restore("<PERSON_1> and <PERSON_9> agreed.", r.redaction_map)
        assert out == "Jane and <PERSON_9> agreed."

    def test_serialise_roundtrip(self):
        from contractex.privacy import RedactionMap

        text = "Jane signed."
        r = PIIRedactor().redact(text, [span(text, "Jane")])
        rmap = RedactionMap.from_dict(r.redaction_map.serialise())
        assert PIIRedactor().restore(r.text, rmap) == text

    def test_placeholder_collision_with_source_text(self):
        text = "Template field <PERSON_1> is filled by Jane."
        r = PIIRedactor().redact(text, [span(text, "Jane")])
        assert PIIRedactor().restore(r.text, r.redaction_map) == text

    def test_unsorted_spans(self):
        text = "Jane met Bob."
        spans = [PIISpan("PERSON", 9, 12, 0.9, "Bob"), PIISpan("PERSON", 0, 4, 0.9, "Jane")]
        r = PIIRedactor().redact(text, spans)
        assert "Jane" not in r.text and "Bob" not in r.text
        assert PIIRedactor().restore(r.text, r.redaction_map) == text

    def test_overlapping_spans_redact_union(self):
        text = "ID AB12345678901 end"
        spans = [
            PIISpan("PASSPORT_NUMBER", 3, 11, 0.9, text[3:11]),
            PIISpan("NATIONAL_ID", 5, 16, 0.8, text[5:16]),
        ]
        r = PIIRedactor().redact(text, spans)
        assert r.text == "ID <PASSPORT_NUMBER_1> end"
        assert PIIRedactor().restore(r.text, r.redaction_map) == text


class TestRedactorOtherStrategies:
    def test_mask_is_irreversible(self):
        text = "Jane signed."
        r = PIIRedactor(default_strategy=RedactionStrategy.MASK).redact(text, [span(text, "Jane")])
        assert r.text == "*** signed."
        assert PIIRedactor().restore(r.text, r.redaction_map) == "*** signed."

    def test_hash_is_keyed_and_deterministic(self):
        text = "Jane signed."
        s = [span(text, "Jane")]
        a = PIIRedactor(default_strategy=RedactionStrategy.HASH, hmac_key=b"k" * 32)
        b = PIIRedactor(default_strategy=RedactionStrategy.HASH, hmac_key=b"k" * 32)
        c = PIIRedactor(default_strategy=RedactionStrategy.HASH, hmac_key=b"x" * 32)
        assert a.redact(text, s).text == b.redact(text, s).text != c.redact(text, s).text
        assert "Jane" not in a.redact(text, s).text

    def test_strategy_override_per_entity(self):
        text = "Jane paid 415-555-0132."
        spans = [span(text, "Jane"), span(text, "415-555-0132", "PHONE_NUMBER")]
        r = PIIRedactor(strategy_overrides={"PHONE_NUMBER": RedactionStrategy.MASK}).redact(
            text, spans
        )
        assert r.text == "<PERSON_1> paid ***."

    def test_encrypt_roundtrip_and_no_plaintext_in_text(self):
        pytest.importorskip("cryptography")
        text = "Call 415-555-0132."
        r = PIIRedactor(default_strategy=RedactionStrategy.ENCRYPT).redact(
            text, [span(text, "415-555-0132", "PHONE_NUMBER")]
        )
        assert "415-555-0132" not in r.text and "<PHONE_NUMBER_ENC:" in r.text
        assert PIIRedactor().restore(r.text, r.redaction_map) == text

    def test_encrypt_serialised_map_has_no_plaintext(self):
        pytest.importorskip("cryptography")
        text = "Call 415-555-0132."
        r = PIIRedactor(default_strategy=RedactionStrategy.ENCRYPT).redact(
            text, [span(text, "415-555-0132", "PHONE_NUMBER")]
        )
        assert "415-555-0132" not in repr(r.redaction_map.serialise())

    def test_encrypt_tampered_token_left_in_place(self):
        pytest.importorskip("cryptography")
        text = "Call 415-555-0132."
        r = PIIRedactor(default_strategy=RedactionStrategy.ENCRYPT).redact(
            text, [span(text, "415-555-0132", "PHONE_NUMBER")]
        )
        token = r.text[len("Call ") : -1]
        tampered = token[:-3] + ("0" if token[-2] != "0" else "1") + ">"
        out = PIIRedactor().restore(f"{tampered} and {token}", r.redaction_map)
        assert out == f"{tampered} and 415-555-0132"

    def test_encrypt_without_cryptography_fails_loudly(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "cryptography.hazmat.primitives.ciphers.aead", None)
        text = "Call 415-555-0132."
        with pytest.raises(ImportError):
            PIIRedactor(default_strategy=RedactionStrategy.ENCRYPT).redact(
                text, [span(text, "415-555-0132", "PHONE_NUMBER")]
            )


class TestNoPIISurvives:
    DOC = (
        "Contact jane.doe@acme.com or 415\u2011555\u20110132. SSN 123-45-6789, "
        "card 4111-1111-1111-1111, IBAN GB82WEST12345698765432, passport X1234567, "
        "DOB: 04/05/1985, alt email j\u0430ne@acme.com, phone 212-555\u200b-0199."
    )
    SECRETS = [
        "jane.doe",
        "0132",
        "6789",
        "1111",
        "GB82WEST",
        "X1234567",
        "04/05/1985",
        "j\u0430ne",
        "0199",
    ]

    @pytest.mark.parametrize("strategy", list(RedactionStrategy))
    def test_mixed_document(self, detector, strategy):
        if strategy is RedactionStrategy.ENCRYPT:
            pytest.importorskip("cryptography")
        redactor = PIIRedactor(default_strategy=strategy)
        r = redactor.redact(self.DOC, detector.detect(self.DOC))
        assert [s for s in self.SECRETS if s in r.text] == []
        if strategy in (RedactionStrategy.REPLACE, RedactionStrategy.ENCRYPT):
            assert redactor.restore(r.text, r.redaction_map) == self.DOC


# ---------------------------------------------------------------------------
# PrivacyAwareLLMRouter
# ---------------------------------------------------------------------------


class Party(BaseModel):
    name: str = ""


class Summary(BaseModel):
    signatory: str = ""
    parties: list[Party] = []


class TestRouterRouting:
    @pytest.mark.parametrize("call", ["route", "route_completion"])
    def test_secret_blocked_before_provider_is_called(self, router, call):
        spy = SpyProvider()
        doc = Doc(PrivacyProfile(sensitivity="secret"))
        with pytest.raises(PrivacyBlockedError):
            if call == "route":
                router.route(doc, "prompt", Summary, spy)
            else:
                router.route_completion(doc, "prompt", spy)
        assert spy.prompts == []

    def test_secret_blocked_even_for_local_provider(self, router):
        local = SpyLocalProvider()
        with pytest.raises(PrivacyBlockedError):
            router.route_completion(Doc(PrivacyProfile(sensitivity="secret")), "p", local)
        assert local.prompts == []

    def test_blocked_override_on_public_doc(self, router):
        spy = SpyProvider()
        doc = Doc(PrivacyProfile(sensitivity="public", llm_routing="blocked"))
        with pytest.raises(PrivacyBlockedError):
            router.route_completion(doc, "p", spy)
        assert spy.prompts == []

    def test_restricted_rejects_cloud_provider(self, router):
        spy = SpyProvider()
        with pytest.raises(PrivacyRoutingError):
            router.route_completion(Doc(PrivacyProfile(sensitivity="restricted")), "p", spy)
        assert spy.prompts == []

    def test_restricted_allows_local_provider_and_redacts(self, router):
        local = SpyLocalProvider()
        router.route_completion(
            Doc(PrivacyProfile(sensitivity="restricted")), "Call 415-555-0132", local
        )
        assert local.prompts == ["Call <PHONE_NUMBER_1>"]

    def test_public_prompt_passes_unchanged(self, router):
        spy = SpyProvider()
        router.route_completion(Doc(PrivacyProfile()), "Call 415-555-0132", spy)
        assert spy.prompts == ["Call 415-555-0132"]

    def test_missing_profile_uses_default_profile(self, detector):
        spy = SpyProvider()
        strict = PrivacyAwareLLMRouter(
            detector=detector, default_profile=PrivacyProfile(sensitivity="secret")
        )
        with pytest.raises(PrivacyBlockedError):
            strict.route_completion(Doc(), "p", spy)

    def test_restricted_rejects_cloud_provider_named_like_local(self, router):
        class NotLocalOpenAIProxy(SpyProvider):
            pass

        spy = NotLocalOpenAIProxy()
        with pytest.raises(PrivacyRoutingError):
            router.route_completion(Doc(PrivacyProfile(sensitivity="restricted")), "p", spy)

    def test_dict_profile_is_enforced(self, router):
        spy = SpyProvider()
        with pytest.raises(PrivacyBlockedError):
            router.route_completion(Doc({"sensitivity": "secret"}), "p", spy)
        assert spy.prompts == []

    def test_legaldoc_json_roundtrip_stays_blocked(self, router):
        from contractex.core.document import LegalDoc

        doc = LegalDoc(full_text="x", privacy_profile=PrivacyProfile(sensitivity="secret"))
        reloaded = LegalDoc.model_validate(doc.model_dump(mode="json"))
        spy = SpyProvider()
        with pytest.raises(PrivacyBlockedError):
            router.route_completion(reloaded, "p", spy)
        assert spy.prompts == []

    def test_unrecognised_profile_type_fails_closed(self, router):
        spy = SpyProvider()
        with pytest.raises((TypeError, ValueError, PrivacyBlockedError)):
            router.route_completion(Doc(object()), "p", spy)
        assert spy.prompts == []


class TestRouterRedaction:
    def test_confidential_redacts_and_restores(self, router):
        spy = SpyProvider(reply="Please call <PHONE_NUMBER_1>.")
        out = router.route_completion(
            Doc(PrivacyProfile(sensitivity="confidential")),
            "Call 415-555-0132",
            spy,
            restore_redaction=True,
        )
        assert spy.prompts == ["Call <PHONE_NUMBER_1>"]
        assert out == "Please call 415-555-0132."

    def test_confidential_updates_profile_entities(self, router):
        doc = Doc(PrivacyProfile(sensitivity="confidential"))
        router.route_completion(doc, "Call 415-555-0132", SpyProvider())
        assert doc.privacy_profile.contains_pii
        assert "PHONE_NUMBER" in doc.privacy_profile.pii_entities_found

    def test_auto_redact_disabled(self, detector):
        spy = SpyProvider()
        r = PrivacyAwareLLMRouter(detector=detector, auto_redact=False)
        r.route_completion(Doc(PrivacyProfile(sensitivity="confidential")), "415-555-0132", spy)
        assert spy.prompts == ["415-555-0132"]

    def test_every_call_on_a_confidential_doc_is_redacted(self, router):
        spy = SpyProvider()
        doc = Doc(PrivacyProfile(sensitivity="confidential"))
        router.route_completion(doc, "Call 415-555-0132 re: contract", spy)
        router.route_completion(doc, "Call 415-555-0132 re: summary", spy)
        assert all("415-555-0132" not in p for p in spy.prompts)

    def test_route_restores_flat_string_fields(self, router):
        spy = SpyProvider(structured={"signatory": "<PHONE_NUMBER_1>"})
        out = router.route(
            Doc(PrivacyProfile(sensitivity="confidential")),
            "Call 415-555-0132",
            Summary,
            spy,
            restore_redaction=True,
        )
        assert out.signatory == "415-555-0132"

    def test_route_restores_nested_fields(self, router):
        spy = SpyProvider(structured={"parties": [{"name": "<PHONE_NUMBER_1>"}]})
        out = router.route(
            Doc(PrivacyProfile(sensitivity="confidential")),
            "Call 415-555-0132",
            Summary,
            spy,
            restore_redaction=True,
        )
        assert out.parties[0].name == "415-555-0132"


class TestGuard:
    def test_guard_raises_immediately_for_secret_doc(self, router):
        with pytest.raises(PrivacyBlockedError):
            router.guard(SpyProvider(), Doc(PrivacyProfile(sensitivity="secret")))

    def test_guard_raises_immediately_for_restricted_doc_and_cloud(self, router):
        with pytest.raises(PrivacyRoutingError):
            router.guard(SpyProvider(), Doc(PrivacyProfile(sensitivity="restricted")))

    def test_guard_applies_strictest_profile_across_docs(self, router):
        docs = [Doc(PrivacyProfile()), Doc({"sensitivity": "secret"})]
        with pytest.raises(PrivacyBlockedError):
            router.guard(SpyLocalProvider(), *docs)

    def test_guard_combines_routing_and_redaction(self, router):
        local = SpyLocalProvider()
        docs = [
            Doc(PrivacyProfile(sensitivity="confidential")),
            Doc(PrivacyProfile(llm_routing="local_only")),
        ]
        with pytest.raises(PrivacyRoutingError):
            router.guard(SpyProvider(), *docs)
        router.guard(local, *docs).complete("Call 415-555-0132")
        assert local.prompts == ["Call <PHONE_NUMBER_1>"]

    def test_guarded_complete_redacts_and_restores(self, router):
        spy = SpyProvider(reply="Ring <PHONE_NUMBER_1>")
        llm = router.guard(spy, Doc(PrivacyProfile(sensitivity="confidential")))
        assert llm.complete("Call 415-555-0132") == "Ring 415-555-0132"
        assert spy.prompts == ["Call <PHONE_NUMBER_1>"]

    def test_guarded_extract_structured_restores_nested(self, router):
        spy = SpyProvider(structured={"parties": [{"name": "<PHONE_NUMBER_1>"}]})
        llm = router.guard(spy, Doc(PrivacyProfile(sensitivity="confidential")))
        assert (
            llm.extract_structured("Call 415-555-0132", Summary).parties[0].name == "415-555-0132"
        )

    def test_guarded_stream_is_redacted(self, router):
        spy = SpyProvider(reply="done")
        llm = router.guard(spy, Doc(PrivacyProfile(sensitivity="confidential")))
        assert list(llm.stream_complete("Call 415-555-0132")) == ["done"]
        assert spy.prompts == ["Call <PHONE_NUMBER_1>"]

    def test_guarded_provider_delegates_metadata(self, router):
        llm = router.guard(SpyProvider(), Doc(PrivacyProfile()))
        assert (llm.model, llm.context_window, llm.count_tokens("abcd")) == ("spy", 100_000, 1)
