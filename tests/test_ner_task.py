"""The ``ner`` task must run against LegalNER as it is.  spaCy is replaced by a stub."""

from __future__ import annotations

from types import SimpleNamespace

from contractex.core.document import LegalDoc
from contractex.core.ner import LegalNER
from contractex.tasks import TaskPipeline
from contractex.tasks.ner import NERTask

TEXT = "Acme Inc. shall pay Jane Roe $5,000."


def _stub_nlp(text: str) -> SimpleNamespace:
    """Stands in for a loaded spaCy pipeline: tags two fixed spans."""
    ents = []
    for label, value in (("ORG", "Acme Inc."), ("PERSON", "Jane Roe")):
        start = text.index(value)
        ents.append(
            SimpleNamespace(text=value, label_=label, start_char=start, end_char=start + len(value))
        )
    return SimpleNamespace(ents=ents)


def make_task() -> NERTask:
    ner = LegalNER.__new__(LegalNER)  # skip loading a spaCy model
    ner.nlp = _stub_nlp
    ner.model_name = "stub"
    task = NERTask()
    task._ner = ner
    return task


def test_ner_task_writes_entities_with_offsets():
    out = TaskPipeline([make_task()]).run(LegalDoc(full_text=TEXT))
    assert out.extracted["ner_entities"] == [
        {"text": "Acme Inc.", "label": "ORG", "start": 0, "end": 9},
        {"text": "Jane Roe", "label": "PERSON", "start": 20, "end": 28},
    ]
    for ent in out.extracted["ner_entities"]:
        assert TEXT[ent["start"] : ent["end"]] == ent["text"]


def test_ner_task_result_survives_json_round_trip():
    out = make_task().run(LegalDoc(full_text=TEXT))
    reloaded = LegalDoc.model_validate_json(out.model_dump_json())
    assert reloaded.extracted["ner_entities"] == out.extracted["ner_entities"]


def test_ner_task_skips_empty_document():
    assert "ner_entities" not in make_task().run(LegalDoc(full_text="")).extracted
