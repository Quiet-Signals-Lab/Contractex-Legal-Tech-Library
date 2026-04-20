"""NER task — wraps LegalNER as a pipeline stage."""

from __future__ import annotations

from typing import Any

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType
from contractex.tasks.base import LegalTask
from contractex.tasks.registry import TaskRegistry


class NERTask(LegalTask):
    """
    Named entity recognition over legal text.  Requires ``pip install
    contractex[spacy]``.

    Results are written to ``doc.extracted["ner_entities"]``.
    """

    task_id = "ner"
    doc_types: list[DocType] = []  # all types
    requires_llm = False

    def __init__(self, model: str = "en_core_web_trf") -> None:
        self._model = model
        self._ner: Any | None = None

    def _get_ner(self) -> Any:
        if self._ner is None:
            from contractex.core.ner import LegalNER

            self._ner = LegalNER(model_name=self._model)
        return self._ner

    def run(self, doc: LegalDoc, **kwargs: Any) -> LegalDoc:
        if not doc.full_text:
            return doc

        ner = self._get_ner()
        entities = ner.extract(doc.full_text)

        doc = doc.model_copy(
            update={
                "extracted": {**doc.extracted, "ner_entities": entities},
            }
        )
        return doc


# Self-register
TaskRegistry.default().register(NERTask)
