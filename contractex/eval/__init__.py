"""
contractex.eval — evaluation harness for extraction quality regression testing.

Load labeled eval suites from YAML/JSON, run them against any extractor
callable, and get per-field accuracy metrics with a pytest-friendly interface.

Quick start::

    from contractex.eval import EvalHarness, EvalSuite

    suite = EvalSuite.load("tests/eval/immigration_cases.yaml")

    def extractor(case):
        doc = pipeline.process(case.input_path or case.input_text)
        return doc.extracted_fields

    harness = EvalHarness(extractor_fn=extractor)
    metrics = harness.run(suite)
    print(metrics.report())
    assert metrics.field_accuracy >= 0.90
"""

from contractex.eval.cases import EvalCase, EvalSuite
from contractex.eval.harness import EvalHarness
from contractex.eval.metrics import CaseResult, ExtractionMetrics, FieldResult

__all__ = [
    "EvalCase",
    "EvalSuite",
    "EvalHarness",
    "FieldResult",
    "CaseResult",
    "ExtractionMetrics",
]
