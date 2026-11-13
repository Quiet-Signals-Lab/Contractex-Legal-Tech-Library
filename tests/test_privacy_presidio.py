"""
PIIDetector against the real Presidio engine.

Skipped unless ``contractex[privacy]`` and the ``en_core_web_sm`` spaCy model
are installed (the CI ``presidio`` job installs both).  The small model is
enough: these tests are about identifiers Presidio scores below the detector's
thresholds, which do not depend on the language model.
"""

from __future__ import annotations

import pytest

pytest.importorskip("presidio_analyzer")
pytest.importorskip("en_core_web_sm")

from presidio_analyzer import AnalyzerEngine  # noqa: E402
from presidio_analyzer.nlp_engine import NlpEngineProvider  # noqa: E402

from contractex.privacy import PIIDetector, PIIRedactor  # noqa: E402


@pytest.fixture(scope="module")
def detector() -> PIIDetector:
    nlp = NlpEngineProvider(
        nlp_configuration={
            "nlp_engine_name": "spacy",
            "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
        }
    ).create_engine()
    engine = AnalyzerEngine(nlp_engine=nlp, supported_languages=["en"])
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(PIIDetector, "_build_presidio_analyzer", lambda self: engine)
        d = PIIDetector()
    assert d.using_presidio
    return d


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("The employee's number is 536-90-4399 as recorded.", "536-90-4399"),
        ("Call 415-555-0132 before noon.", "415-555-0132"),
        ("Holder of document AB1234567.", "AB1234567"),
        ("Licence D1234567 was presented.", "D1234567"),
        ("Jane was born 04/12/1988 in Leeds.", "04/12/1988"),
        ("Charged to 4111 1111 1111 1111.", "4111 1111 1111 1111"),
        ("Pay to NL91ABNA0417164300.", "NL91ABNA0417164300"),
        ("Write to jan@example.com.", "jan@example.com"),
    ],
)
def test_identifier_without_context_words_is_redacted(detector, text, value):
    redacted = PIIRedactor().redact(text, detector.detect(text)).text
    assert value not in redacted


def test_presidio_is_not_asked_for_entities_it_lacks(detector, caplog):
    with caplog.at_level("WARNING", logger="presidio-analyzer"):
        detector.detect("Holder of document AB1234567.")
    assert not [r for r in caplog.records if "corresponding recognizer" in r.getMessage()]


def test_presidio_adds_names_the_patterns_cannot_find(detector):
    text = "Signed by Jane Doe on behalf of the Supplier."
    assert "Jane Doe" not in PIIRedactor().redact(text, detector.detect(text)).text
    assert PIIDetector(use_presidio=False).detect(text) == []
