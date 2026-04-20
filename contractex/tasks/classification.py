"""Classification task — wraps CUADClassifier as a pipeline stage."""

from __future__ import annotations

from typing import Any

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType
from contractex.tasks.base import LegalTask
from contractex.tasks.registry import TaskRegistry


class ClassificationTask(LegalTask):
    """
    Classify clauses using the CUAD taxonomy and write results to
    ``doc.extracted["cuad_labels"]``.

    Parameters
    ----------
    model_name:
        HuggingFace model identifier for CUAD classification.
    confidence_threshold:
        Minimum score to report a label.
    """

    task_id = "classification"
    doc_types = [DocType.CONTRACT]
    requires_llm = False

    def __init__(
        self,
        model_name: str = "nlpaueb/legal-bert-base-uncased",
        confidence_threshold: float = 0.5,
    ) -> None:
        self._model_name = model_name
        self._confidence_threshold = confidence_threshold
        self._classifier: Any | None = None

    def _get_classifier(self) -> Any:
        if self._classifier is None:
            from contractex.core.classifiers import CUADClassifier

            self._classifier = CUADClassifier(
                confidence_threshold=self._confidence_threshold,
            )
        return self._classifier

    def run(self, doc: LegalDoc, **kwargs: Any) -> LegalDoc:
        if not doc.full_text:
            return doc

        classifier = self._get_classifier()
        labels = classifier.classify(doc.full_text)

        doc = doc.model_copy(
            update={
                "extracted": {**doc.extracted, "cuad_labels": labels},
            }
        )
        return doc


# Self-register
TaskRegistry.default().register(ClassificationTask)
