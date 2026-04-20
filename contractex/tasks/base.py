"""
LegalTask — abstract base class for all ContractEx task types.

Every legal NLP operation (extraction, classification, summarization, PII
detection, …) is implemented as a ``LegalTask`` subclass.  Tasks are designed
to be composable: ``TaskPipeline`` chains them so the output ``LegalDoc`` of
one task becomes the input of the next.

Implementing a custom task
--------------------------
::

    from contractex.tasks.base import LegalTask
    from contractex.core.document import LegalDoc
    from contractex.core.legal_document import DocType

    class MyObligationExtractor(LegalTask):
        task_id = "my_obligation_extractor"
        doc_types = [DocType.CONTRACT, DocType.PLEADING]
        requires_llm = True

        def run(self, doc: LegalDoc, **kwargs) -> LegalDoc:
            # ... call LLM, populate doc.extracted ...
            doc.extracted["obligations"] = [...]
            return doc

    # Register it
    from contractex.tasks.registry import TaskRegistry
    TaskRegistry.default().register(MyObligationExtractor)
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType

logger = logging.getLogger(__name__)


class LegalTask(ABC):
    """
    Abstract base for all ContractEx legal NLP tasks.

    Subclasses must set class-level attributes and implement ``run()``.

    Class attributes
    ----------------
    task_id: str
        Unique snake_case identifier (e.g. ``"contract_extraction"``).
        Used as the key in ``TaskRegistry``.
    doc_types: list[DocType]
        Document types this task can process.  Empty list means all types.
    requires_llm: bool
        Whether the task calls an external or local LLM.  Used for cost
        estimation and routing.
    """

    task_id: str = ""
    doc_types: list[DocType] = []
    requires_llm: bool = False

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def run(self, doc: LegalDoc, **kwargs: Any) -> LegalDoc:
        """
        Execute the task on *doc*.

        Parameters
        ----------
        doc:
            Input document.  May be mutated in-place or a new ``LegalDoc``
            may be returned — callers should always use the returned value.
        **kwargs:
            Task-specific options (e.g. ``confidence_threshold``).

        Returns
        -------
        LegalDoc
            Document with task results merged into ``doc.extracted``.
        """
        ...

    # ------------------------------------------------------------------
    # Optional overrides
    # ------------------------------------------------------------------

    async def run_async(self, doc: LegalDoc, **kwargs: Any) -> LegalDoc:
        """
        Async version of ``run()``.

        Default implementation wraps the synchronous ``run()`` in a thread
        executor so it does not block the event loop.  Override for native
        async providers.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self.run(doc, **kwargs))

    def estimate_cost(self, doc: LegalDoc) -> float:
        """
        Estimate the API cost (USD) for processing *doc* with this task.

        Default returns 0.0.  Override for tasks that call external LLMs.
        """
        return 0.0

    def supports(self, doc: LegalDoc) -> bool:
        """
        Return ``True`` if this task can process *doc*.

        Returns ``True`` for all doc types if ``self.doc_types`` is empty.
        """
        if not self.doc_types:
            return True
        return doc.doc_type in self.doc_types

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"<{type(self).__name__} task_id={self.task_id!r}>"


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class TaskPipeline:
    """
    An ordered sequence of ``LegalTask`` objects applied to a ``LegalDoc``.

    Tasks are applied in order.  If a task does not support the document's
    ``doc_type``, it is skipped with a warning rather than raising.

    Usage
    -----
    ::

        pipeline = TaskPipeline([pii_task, extraction_task, risk_task])
        doc = pipeline.run(doc)
        # doc.extracted now contains results from all tasks

    Parameters
    ----------
    tasks:
        Ordered list of ``LegalTask`` instances.
    skip_unsupported:
        If ``True`` (default), tasks that don't support the document type
        are silently skipped.  If ``False``, an error is raised.
    record_timings:
        If ``True`` (default), task run times are written to
        ``doc.extracted["_task_timings"]``.
    """

    def __init__(
        self,
        tasks: list[LegalTask],
        skip_unsupported: bool = True,
        record_timings: bool = True,
    ) -> None:
        self._tasks = tasks
        self._skip_unsupported = skip_unsupported
        self._record_timings = record_timings

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, doc: LegalDoc, **kwargs: Any) -> LegalDoc:
        """
        Run all tasks in order and return the final ``LegalDoc``.

        Parameters
        ----------
        doc:
            Input document.
        **kwargs:
            Passed to every task's ``run()`` method.

        Returns
        -------
        LegalDoc
            Document with all task results attached to ``doc.extracted``.
        """
        timings: dict[str, float] = {}

        for task in self._tasks:
            if not task.supports(doc):
                if self._skip_unsupported:
                    logger.debug(
                        "Skipping task %r — doc_type=%r not supported",
                        task.task_id,
                        doc.doc_type,
                    )
                    continue
                raise ValueError(
                    f"Task {task.task_id!r} does not support doc_type={doc.doc_type!r}"
                )

            logger.debug("Running task %r", task.task_id)
            t0 = time.perf_counter()
            doc = task.run(doc, **kwargs)
            elapsed = time.perf_counter() - t0
            timings[task.task_id] = round(elapsed, 4)
            logger.debug("Task %r completed in %.3fs", task.task_id, elapsed)

        if self._record_timings and timings:
            doc.extracted.setdefault("_task_timings", {}).update(timings)

        return doc

    async def run_async(self, doc: LegalDoc, **kwargs: Any) -> LegalDoc:
        """Async version of ``run()``.  Awaits each task in sequence."""
        timings: dict[str, float] = {}

        for task in self._tasks:
            if not task.supports(doc):
                if self._skip_unsupported:
                    continue
                raise ValueError(
                    f"Task {task.task_id!r} does not support doc_type={doc.doc_type!r}"
                )

            t0 = time.perf_counter()
            doc = await task.run_async(doc, **kwargs)
            timings[task.task_id] = round(time.perf_counter() - t0, 4)

        if self._record_timings and timings:
            doc.extracted.setdefault("_task_timings", {}).update(timings)

        return doc

    def estimate_total_cost(self, doc: LegalDoc) -> float:
        """Sum cost estimates across all tasks that support *doc*."""
        return sum(
            t.estimate_cost(doc) for t in self._tasks if t.supports(doc)
        )

    def __len__(self) -> int:
        return len(self._tasks)

    def __repr__(self) -> str:
        ids = [t.task_id for t in self._tasks]
        return f"<TaskPipeline tasks={ids}>"
