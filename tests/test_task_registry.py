"""TaskRegistry: built-in tasks load in any registry, not only the default one."""

from __future__ import annotations

import pytest

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType
from contractex.tasks import TaskPipeline, TaskRegistry
from contractex.tasks.registry import _BUILTIN_TASK_MODULES


@pytest.mark.parametrize("task_id", sorted(_BUILTIN_TASK_MODULES))
def test_fresh_registry_loads_every_builtin_task(task_id):
    registry = TaskRegistry()
    task = registry.get(task_id)
    assert task.task_id == task_id
    assert registry.get_class(task_id) is type(task)


def test_fresh_registry_does_not_share_instances_with_the_default_one():
    assert TaskRegistry().get("citation") is not TaskRegistry.default().get("citation")


def test_fresh_registry_builds_a_working_pipeline():
    pipeline = TaskRegistry().build_pipeline(["citation", "classification"])
    assert isinstance(pipeline, TaskPipeline)
    doc = LegalDoc(doc_type=DocType.CONTRACT, full_text="See 17 U.S.C. § 107; governing law.")
    out = pipeline.run(doc)
    assert out.extracted["citations"] and "governing_law" in out.extracted["cuad_labels"]


def test_builtin_task_reloads_after_unregister():
    registry = TaskRegistry()
    registry.get("citation")
    registry.unregister("citation")
    assert registry.get("citation").task_id == "citation"


def test_unknown_task_is_a_key_error():
    with pytest.raises(KeyError, match="not registered"):
        TaskRegistry().get("no_such_task")
