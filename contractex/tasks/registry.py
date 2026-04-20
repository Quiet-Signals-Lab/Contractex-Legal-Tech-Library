"""
TaskRegistry — central registry of all ContractEx legal NLP tasks.

Tasks register themselves (or are registered explicitly).  The registry
is a singleton accessed via ``TaskRegistry.default()``.

Usage
-----
::

    from contractex.tasks import TaskRegistry

    # Discover all built-in tasks
    registry = TaskRegistry.default()
    print(list(registry.task_ids))

    # Build a pipeline
    pipeline = registry.build_pipeline([
        "pii_detection",
        "contract_extraction",
        "risk_analysis",
    ])
    result_doc = pipeline.run(doc)

    # Register a custom task
    registry.register(MyCustomTask)
"""

from __future__ import annotations

import importlib
import logging
from typing import Any

from contractex.tasks.base import LegalTask, TaskPipeline

logger = logging.getLogger(__name__)

# Module paths for built-in tasks (imported lazily to avoid circular imports
# and heavy optional dependencies being loaded at import time)
_BUILTIN_TASK_MODULES: dict[str, str] = {
    "pii_detection": "contractex.tasks.pii_detection",
    "contract_extraction": "contractex.tasks.extraction",
    "classification": "contractex.tasks.classification",
    "risk_analysis": "contractex.tasks.risk_analysis",
    "ner": "contractex.tasks.ner",
    "summarization": "contractex.tasks.summarization",
    "timeline": "contractex.tasks.timeline",
    "obligations": "contractex.tasks.obligations",
    "comparison": "contractex.tasks.comparison",
    "citation": "contractex.tasks.citation",
}


class TaskRegistry:
    """
    Registry of available ``LegalTask`` implementations.

    Attributes
    ----------
    task_ids: set[str]
        IDs of all currently registered tasks.
    """

    _default_instance: TaskRegistry | None = None

    def __init__(self) -> None:
        self._tasks: dict[str, type[LegalTask]] = {}
        self._instances: dict[str, LegalTask] = {}

    # ------------------------------------------------------------------
    # Singleton accessor
    # ------------------------------------------------------------------

    @classmethod
    def default(cls) -> TaskRegistry:
        """
        Return the shared global registry.

        Built-in tasks are loaded lazily on first access.
        """
        if cls._default_instance is None:
            cls._default_instance = cls()
        return cls._default_instance

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, task: type[LegalTask] | LegalTask) -> None:
        """
        Register a task class or instance.

        Parameters
        ----------
        task:
            A ``LegalTask`` subclass or instance.  The ``task_id`` class
            attribute is used as the registry key.

        Raises
        ------
        ValueError
            If ``task_id`` is empty or already registered.
        """
        if isinstance(task, LegalTask):
            instance = task
            task_cls = type(task)
        else:
            task_cls = task
            instance = task_cls()

        task_id = task_cls.task_id
        if not task_id:
            raise ValueError(f"Cannot register {task_cls.__name__}: task_id is empty.")

        if task_id in self._tasks:
            logger.debug("Re-registering task %r (overwriting)", task_id)

        self._tasks[task_id] = task_cls
        self._instances[task_id] = instance
        logger.debug("Registered task %r", task_id)

    def unregister(self, task_id: str) -> None:
        """Remove a task from the registry."""
        self._tasks.pop(task_id, None)
        self._instances.pop(task_id, None)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, task_id: str) -> LegalTask:
        """
        Return a task instance by *task_id*.

        Built-in tasks are loaded lazily the first time they are requested.

        Raises
        ------
        KeyError
            If *task_id* is not registered.
        """
        if task_id not in self._instances:
            self._lazy_load(task_id)
        return self._instances[task_id]

    def get_class(self, task_id: str) -> type[LegalTask]:
        """Return the task class for *task_id*."""
        if task_id not in self._tasks:
            self._lazy_load(task_id)
        return self._tasks[task_id]

    @property
    def task_ids(self) -> set[str]:
        """Set of all registered task IDs (does not trigger lazy loading)."""
        return set(self._tasks) | set(_BUILTIN_TASK_MODULES)

    # ------------------------------------------------------------------
    # Pipeline construction
    # ------------------------------------------------------------------

    def build_pipeline(
        self,
        task_ids: list[str],
        task_kwargs: dict[str, dict[str, Any]] | None = None,
        **pipeline_kwargs: Any,
    ) -> TaskPipeline:
        """
        Build a ``TaskPipeline`` from an ordered list of task IDs.

        Parameters
        ----------
        task_ids:
            Ordered list of task IDs to include.
        task_kwargs:
            Optional per-task constructor kwargs, e.g.
            ``{"contract_extraction": {"confidence_threshold": 0.8}}``.
        **pipeline_kwargs:
            Passed to ``TaskPipeline.__init__``.

        Returns
        -------
        TaskPipeline

        Raises
        ------
        KeyError
            If any task_id is not registered.
        """
        task_kwargs = task_kwargs or {}
        tasks: list[LegalTask] = []

        for tid in task_ids:
            if tid in task_kwargs:
                # Construct a fresh instance with the supplied kwargs
                cls = self.get_class(tid)
                tasks.append(cls(**task_kwargs[tid]))
            else:
                tasks.append(self.get(tid))

        return TaskPipeline(tasks, **pipeline_kwargs)

    # ------------------------------------------------------------------
    # Internal — lazy loading
    # ------------------------------------------------------------------

    def _lazy_load(self, task_id: str) -> None:
        """
        Import the module for a built-in task and register it.

        Raises
        ------
        KeyError
            If *task_id* has no known module path.
        """
        module_path = _BUILTIN_TASK_MODULES.get(task_id)
        if not module_path:
            raise KeyError(
                f"Task {task_id!r} is not registered.  "
                f"Available built-in tasks: {sorted(_BUILTIN_TASK_MODULES)}"
            )

        try:
            importlib.import_module(module_path)
        except ImportError as exc:
            raise ImportError(
                f"Could not load task {task_id!r} from {module_path!r}: {exc}\n"
                "You may need to install optional dependencies — see the docs."
            ) from exc

        # The module registers itself via module-level code
        # (``TaskRegistry.default().register(...)`` at the bottom of each
        # task module).  If it didn't, look for a class matching task_id.
        if task_id not in self._tasks:
            logger.warning("Module %r did not self-register task %r", module_path, task_id)
