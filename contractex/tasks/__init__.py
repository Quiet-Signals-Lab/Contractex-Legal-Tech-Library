"""
Task registry for ContractEx.

All legal NLP tasks are implemented as ``LegalTask`` subclasses and registered
in the ``TaskRegistry``.  Tasks are composable — the output of one is the
input of the next.

Quick start::

    from contractex.tasks import TaskRegistry

    registry = TaskRegistry.default()
    pipeline = registry.build_pipeline([
        "pii_detection",
        "contract_extraction",
        "risk_analysis",
    ])
    doc = pipeline.run(doc)

Available built-in tasks
------------------------
* ``pii_detection``       — PIIDetector wrapper
* ``contract_extraction`` — ContractExtractor wrapper
* ``classification``      — CUADClassifier wrapper
* ``risk_analysis``       — RiskAnalyzer wrapper
* ``ner``                 — LegalNER wrapper
* ``summarization``       — LLM-powered summarization
* ``timeline``            — extract dates / obligations timeline
* ``obligations``         — extract obligations and duties
* ``comparison``          — compare two documents
* ``citation``            — extract and format legal citations
"""

from __future__ import annotations

from contractex.tasks.base import LegalTask, TaskPipeline
from contractex.tasks.registry import TaskRegistry

__all__ = [
    "LegalTask",
    "TaskPipeline",
    "TaskRegistry",
]
