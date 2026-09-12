# Evaluation

A model's output cannot be assumed correct.  `EvalHarness` runs your
extraction function over a labelled suite, reports field-level accuracy, and
provides assertions that fail a CI run when quality drops.  The same harness
scores privacy behaviour.

## A labelled suite

Suites are YAML or JSON.  Each case gives its input (a file path or inline
text), the expected field values, and optional per-field weights.
[`examples/data/eval_suite.yaml`](https://github.com/Quiet-Signals-Lab/Contractex-Legal-Tech-Library/blob/main/examples/data/eval_suite.yaml)
has three cases for the deterministic structure parser.  The third uses a
phrasing its governing-law heuristic does not recognise.

## Running it

The harness accepts any function `(EvalCase) -> dict`.  Here it wraps the
structure parser; in practice it would wrap your LLM pipeline.

```python
from contractex.eval import EvalHarness, EvalSuite
from contractex.structure import parse_structure


def extract(case):
    text = case.input_text or open(case.input_path, encoding="utf-8").read()
    structure = parse_structure(text)
    return {
        "governing_law": structure.governing_law_hint,
        "unresolved_references": len(structure.unresolved_refs),
    }


suite = EvalSuite.load("examples/data/eval_suite.yaml")
metrics = EvalHarness(extract).run(suite)
print(metrics.report())
```

```text
==============================================================
  Contractex Eval Report
==============================================================
  Suite size:     3 cases
  Passed:         2 (66.7% case accuracy)
  Errors:         0
  Field accuracy: 77.8% (weighted)

  Per-field accuracy:
  Field                             Correct   Total  Acc
  --------------------------------------------------------
  governing_law                           2       3  67%
  unresolved_references                   3       3  100%
==============================================================
```

Strings match case-insensitively after trimming whitespace, booleans match
strictly, and a field the extractor did not return never matches.  *Field
accuracy* is weighted by `field_weights`.  *Case accuracy* counts cases where
every field matched.

## Gating CI

The assertions raise `AssertionError` with the report attached, so they work
directly as pytest tests:

```python
try:
    metrics.assert_min_field_accuracy(0.90)
except AssertionError as exc:
    print(str(exc).splitlines()[0])
```

```text
Field accuracy 77.8% < required 90.0%
```

```python
metrics.assert_min_field_accuracy(0.70)  # passes: accuracy is above 70%
```

## Privacy evaluation

`run_privacy()` scores three things per case, each only when you supply the
function for it:

- **PII detection** (`pii_detector_fn`, returning entity types): precision and
  recall over entity *types*.  Detecting one of five email addresses counts as
  recall 1.0 for `EMAIL_ADDRESS`, so check individual values separately.
- **Redaction count** (`redactor_fn`): whether at least the expected number of
  spans was redacted.
- **Blocking** (`router_fn`): whether the call was blocked when it should have
  been.  Raising `PrivacyBlockedError` counts as blocked.

A function that raises any other exception is recorded in the case's `error`
and scored as a failure.  It is never skipped.

```python
from contractex import LegalDoc
from contractex.eval import EvalCase
from contractex.llm.base import LLMProvider
from contractex.privacy import PIIDetector, PrivacyAwareLLMRouter, PrivacyProfile


class Offline(LLMProvider):
    """Never called: guard() decides before any call is made."""

    context_window = 8_000
    model = "offline"

    def complete(self, prompt, **kwargs):
        raise AssertionError("not called")

    def extract_structured(self, prompt, schema, **kwargs):
        raise AssertionError("not called")

    def estimate_cost(self, text):
        return 0.0

    def count_tokens(self, text):
        return len(text) // 4


detector = PIIDetector(use_presidio=False)
router = PrivacyAwareLLMRouter(detector=detector)
note = "Notices go to Priya Raman at priya.raman@harbourline.test or 415-555-0132."

cases = EvalSuite.from_cases(
    [
        EvalCase(id="notice", input_text=note, expected_pii_entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"]),
        EvalCase(id="public", input_text=note, metadata={"sensitivity": "public"}),
        EvalCase(id="secret", input_text=note, should_be_blocked=True, metadata={"sensitivity": "secret"}),
    ]
)


def detect(case):
    return sorted({s.entity_type for s in detector.detect(case.input_text)})


def blocked(case):
    profile = PrivacyProfile(sensitivity=case.metadata.get("sensitivity", "public"))
    router.guard(Offline(), LegalDoc(full_text=case.input_text, privacy_profile=profile))
    return False


privacy = EvalHarness(extract).run_privacy(cases, pii_detector_fn=detect, router_fn=blocked)
print(f"PII recall {privacy.pii_recall:.2f}, blocking accuracy {privacy.blocking_accuracy:.0%}")
privacy.assert_perfect_blocking()
```

```text
PII recall 0.67, blocking accuracy 100%
```

Recall is below 1.0 because the regex fallback does not detect names (see
[Limitations](../limitations.md)).  The [benchmarks](../benchmarks.md) use
the same harness on a larger synthetic fixture.
