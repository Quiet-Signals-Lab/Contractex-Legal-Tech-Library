"""
Privacy: PII detection and redaction on a committed synthetic fixture, and a
routing matrix proving which documents reach which provider.

Detection (regex fallback, i.e. without Presidio)
-------------------------------------------------
fixtures/privacy_cases.jsonl holds contract-style sentences with one planted
PII value each (all values are fictitious: reserved .test domains, 555-01xx
phone numbers, published test card/IBAN numbers) plus non-PII distractors
(amounts, section numbers, agreement dates).  Each case has a *variant*:

* plain         — the value as usually written
* zero_width    — a zero-width space inside the value
* unicode_dash  — separators replaced by U+2011 / U+2013
* fullwidth     — digits replaced by fullwidth digits
* homoglyph     — a Cyrillic letter inside an email address
* unsupported   — formats the regex fallback is not designed to catch
                  (names, addresses, international phones, spaced IBANs,
                  dates of birth written in words)

A planted value is *caught* when every letter and digit of it lies inside a
detected span, i.e. nothing identifying survives redaction (a leftover
bracket or separator is not counted).  In the fixture, text before a ``|`` in
a value is context (e.g. "DOB: ") and not part of the PII.  A distractor is a
*false positive* when any detected span overlaps it.  Entity-type recall and
blocking accuracy are also computed with EvalHarness.run_privacy().

Routing matrix
--------------
Every sensitivity level x {cloud provider, LocalProvider} x entry point
(PrivacyAwareLLMRouter, TaskPipeline, comparison task's second document,
LegalRAGPipeline).  Providers are recording stubs; a cell passes when the
outcome matches the policy and the provider never saw text it must not see.

    python -m benchmarks.privacy build   # regenerate the fixture
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType
from contractex.eval import EvalCase, EvalHarness, EvalSuite
from contractex.llm.base import LLMProvider
from contractex.llm.local_provider import LocalProvider
from contractex.privacy import (
    PIIDetector,
    PIIRedactor,
    PrivacyAwareLLMRouter,
    PrivacyBlockedError,
    PrivacyProfile,
    PrivacyRoutingError,
)
from contractex.tasks import TaskRegistry

FIXTURE = Path(__file__).parent / "fixtures" / "privacy_cases.jsonl"

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

TEMPLATES = [
    "Notices to the Licensee shall be sent to {v} no later than 30 days after the Effective Date.",
    "Pursuant to Section 12.3, the Supplier's representative ({v}) shall approve the $1,250,000 payment.",
    "As of January 1, 2024, the counterparty identified by {v} accepts the terms of Agreement No. 2024-117.",
    "The Customer confirms that {v} is correct and that 15% of fees are payable under Schedule 4.",
]
DISTRACTORS = [
    "30 days",
    "Section 12.3",
    "$1,250,000",
    "January 1, 2024",
    "2024-117",
    "15%",
    "Schedule 4",
]

_ZW = "\u200b"
_FW = str.maketrans("0123456789", "".join(chr(0xFF10 + i) for i in range(10)))

VALUES: dict[str, dict[str, list[str]]] = {
    "EMAIL_ADDRESS": {
        "plain": ["jane.doe@acme.test", "legal-notices@supplier.test"],
        "zero_width": [f"jane.doe{_ZW}@acme.test"],
        "homoglyph": ["j\u0430ne.doe@acme.test"],
    },
    "PHONE_NUMBER": {
        "plain": ["415-555-0132", "(212) 555-0199", "212.555.0147"],
        "zero_width": [f"415-555{_ZW}-0132"],
        "unicode_dash": ["415\u2011555\u20110132", "212\u2013555\u20130199"],
        "fullwidth": ["415-555-0132".translate(_FW)],
        "unsupported": ["+44 20 7946 0958", "+49 30 901820"],
    },
    "US_SSN": {
        "plain": ["123-45-6789", "078-05-1120"],
        "unicode_dash": ["123\u201345\u20136789"],
        "fullwidth": ["123-45-6789".translate(_FW)],
    },
    "CREDIT_CARD": {
        "plain": ["4111 1111 1111 1111", "5500-0000-0000-0004"],
        "zero_width": [f"4111 1111{_ZW} 1111 1111"],
        "unsupported": ["3782 822463 10005"],
    },
    "IBAN_CODE": {
        "plain": ["GB82WEST12345698765432", "DE89370400440532013000"],
        "unsupported": ["GB82 WEST 1234 5698 7654 32"],
    },
    "PASSPORT_NUMBER": {"plain": ["X1234567", "AB9876543"]},
    "DATE_OF_BIRTH": {
        "plain": ["DOB: |04/05/1985", "born |12/31/1970"],
        "unsupported": ["born on |3 March 1985"],
    },
    "PERSON": {"unsupported": ["Jane Doe", "Rafael Ortiz-Kowalski"]},
    "LOCATION": {"unsupported": ["10 Downing Street, London"]},
}


def build_fixture() -> list[dict[str, Any]]:
    rng = random.Random(0)
    cases = []
    for entity, variants in VALUES.items():
        for variant, values in variants.items():
            for spec in values:
                context, _, value = spec.rpartition("|")
                for t, template in enumerate(TEMPLATES):
                    text = template.format(v=context + value)
                    start = text.index(context + value) + len(context)
                    cases.append(
                        {
                            "id": f"{entity.lower()}-{variant}-{len(cases)}",
                            "entity": entity,
                            "variant": variant,
                            "text": text,
                            "pii": [start, start + len(value)],
                            "distractors": [
                                [text.index(d), text.index(d) + len(d)]
                                for d in DISTRACTORS
                                if d in text
                            ],
                            "template": t,
                        }
                    )
    rng.shuffle(cases)
    return cases


def load_fixture() -> list[dict[str, Any]]:
    return [json.loads(line) for line in FIXTURE.read_text(encoding="utf-8").splitlines()]


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def covered(spans: list[Any], text: str, start: int, end: int) -> bool:
    """Every letter and digit of text[start:end] is inside a detected span."""
    return all(
        any(s.start <= i < s.end for s in spans) for i in range(start, end) if text[i].isalnum()
    )


def detection(cases: list[dict[str, Any]]) -> dict[str, Any]:
    detector = PIIDetector(use_presidio=False)
    redactor = PIIRedactor()
    table: dict[str, dict[str, list[int]]] = {}
    fp = n_distractors = 0
    for case in cases:
        text = case["text"]
        spans = detector.detect(text)
        start, end = case["pii"]
        caught = covered(spans, text, start, end)
        if caught:  # consistency check: a caught value must not survive redaction
            assert text[start:end] not in redactor.redact(text, spans).text
        cell = table.setdefault(case["entity"], {}).setdefault(case["variant"], [0, 0])
        cell[0] += caught
        cell[1] += 1
        for ds, de in case["distractors"]:
            n_distractors += 1
            fp += any(s.start < de and ds < s.end for s in spans)

    harness = EvalHarness(extractor_fn=lambda c: {}).run_privacy(
        EvalSuite.from_cases(
            [
                EvalCase(id=c["id"], input_text=c["text"], expected_pii_entities=[c["entity"]])
                for c in cases
                if c["variant"] != "unsupported"
            ]
        ),
        pii_detector_fn=lambda c: sorted({s.entity_type for s in detector.detect(c.input_text)}),
    )
    return {
        "backend": "regex fallback, use_presidio=False",
        "caught": table,
        "distractors": n_distractors,
        "distractor_false_positives": fp,
        "harness_entity_type_recall": round(harness.pii_recall or 0.0, 4),
        "harness_entity_type_precision": round(harness.pii_precision or 0.0, 4),
    }


# ---------------------------------------------------------------------------
# Routing matrix
# ---------------------------------------------------------------------------

SECRET_MARK = "FALCON-7"
PHONE = "415-555-0132"
BODY = f"Project {SECRET_MARK}: the counterparty contact is {PHONE}."


class _Spy:
    def _init(self) -> None:
        self.prompts: list[str] = []

    def complete(self, prompt: str, temperature: float = 0.7, max_tokens=None, **kwargs) -> str:
        self.prompts.append(prompt)
        return "ok"

    def extract_structured(self, prompt, schema, temperature=0.0, max_tokens=None) -> BaseModel:
        self.prompts.append(prompt)
        return schema.model_validate({})

    def estimate_cost(self, text: str) -> float:
        return 0.0

    def count_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 100_000

    @property
    def model(self) -> str:
        return "stub"


class CloudStub(_Spy, LLMProvider):
    def __init__(self) -> None:
        self._init()


class LocalStub(_Spy, LocalProvider):
    def __init__(self) -> None:
        self._init()


def _doc(sensitivity: str, text: str = BODY) -> LegalDoc:
    return LegalDoc(
        doc_type=DocType.CONTRACT,
        full_text=text,
        privacy_profile=PrivacyProfile(sensitivity=sensitivity),
    )


class _Embedder:
    def encode(self, text: str) -> list[float]:
        return [1.0, 0.0]


def _entry_points() -> dict[str, Any]:
    from contractex.rag import LegalRAGPipeline

    def router(sensitivity: str, provider: Any) -> None:
        PrivacyAwareLLMRouter(detector=PIIDetector(use_presidio=False)).route_completion(
            _doc(sensitivity), BODY, provider
        )

    def pipeline(sensitivity: str, provider: Any) -> None:
        TaskRegistry.default().build_pipeline(
            ["summarization"], task_kwargs={"summarization": {"llm_provider": provider}}
        ).run(_doc(sensitivity))

    def comparison_doc_b(sensitivity: str, provider: Any) -> None:
        TaskRegistry.default().build_pipeline(
            ["comparison"], task_kwargs={"comparison": {"llm_provider": provider}}
        ).run(_doc("public", "Plain public text."), doc_b=_doc(sensitivity))

    def rag(sensitivity: str, provider: Any) -> None:
        pipe = LegalRAGPipeline(llm_provider=provider, conflict_detector=None)
        pipe._get_embedder = lambda: _Embedder()  # type: ignore[method-assign]
        pipe.ingest([_doc(sensitivity)])
        pipe.query("Who is the contact?")

    return {
        "router": router,
        "pipeline": pipeline,
        "comparison_doc_b": comparison_doc_b,
        "rag": rag,
    }


def _expected(sensitivity: str, local: bool, entry: str) -> str:
    """The outcome the privacy policy requires."""
    withheld = "excluded" if entry == "rag" else None
    if sensitivity == "secret":
        return withheld or "blocked"
    if sensitivity == "restricted" and not local:
        return withheld or "routing_error"
    if sensitivity in ("confidential", "restricted"):
        return "sent_redacted"
    return "sent_raw"


def _observed(run: Any, sensitivity: str, provider: Any) -> str:
    try:
        run(sensitivity, provider)
    except PrivacyBlockedError:
        return "blocked" if not provider.prompts else "LEAKED"
    except PrivacyRoutingError:
        return "routing_error" if not provider.prompts else "LEAKED"
    seen = "\n".join(provider.prompts)
    if SECRET_MARK not in seen:
        return "excluded"
    return "sent_raw" if PHONE in seen else "sent_redacted"


def routing() -> dict[str, Any]:
    cells = []
    for entry, run in _entry_points().items():
        for sensitivity in ("public", "confidential", "restricted", "secret"):
            for local in (False, True):
                provider = LocalStub() if local else CloudStub()
                expected = _expected(sensitivity, local, entry)
                observed = _observed(run, sensitivity, provider)
                cells.append(
                    {
                        "entry_point": entry,
                        "sensitivity": sensitivity,
                        "provider": "local" if local else "cloud",
                        "expected": expected,
                        "observed": observed,
                        "pass": expected == observed,
                    }
                )

    def blocked(case: EvalCase) -> bool:
        # A LocalProvider is permitted for every level except secret, so only
        # secret should raise PrivacyBlockedError (counted as blocked).
        PrivacyAwareLLMRouter().route_completion(_doc(case.metadata["s"]), BODY, LocalStub())
        return False

    harness = EvalHarness(extractor_fn=lambda c: {}).run_privacy(
        EvalSuite.from_cases(
            [
                EvalCase(id=s, input_text=BODY, should_be_blocked=s == "secret", metadata={"s": s})
                for s in ("public", "confidential", "restricted", "secret")
            ]
        ),
        router_fn=blocked,
    )
    return {
        "cells": cells,
        "passed": sum(c["pass"] for c in cells),
        "total": len(cells),
        "harness_blocking_accuracy": harness.blocking_accuracy,
    }


def run() -> dict[str, Any]:
    return {"detection": detection(load_fixture()), "routing": routing()}


if __name__ == "__main__" and sys.argv[1:] == ["build"]:
    rows = build_fixture()
    FIXTURE.write_text(
        "".join(json.dumps(r, ensure_ascii=True) + "\n" for r in rows), encoding="utf-8"
    )
    print(f"wrote {FIXTURE} ({len(rows)} cases)")
