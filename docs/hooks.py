"""
MkDocs hook: suppress griffe docstring linting warnings that originate
from source files in contractex/ that we cannot modify.

Two specific patterns are suppressed:
  - "Confusing indentation for continuation line" — six-space list indentation
    in estimate_extraction_cost()'s Returns block; griffe expects eight spaces
    for the Google-style parser.  Cosmetic, not a broken reference.
  - "No type or annotation for parameter '**kwargs'" — Contract.to_json() passes
    **kwargs through to json.dumps; the intentional lack of annotation triggers
    a griffe lint but does not affect API usability.

All other griffe messages (missing modules, broken autodoc references, etc.)
are preserved and will still fail the strict build.

Implementation note: MkDocs sets mkdocs.propagate = False and places its
CountHandler on logging.getLogger('mkdocs').  mkdocstrings re-logs griffe
warnings through the mkdocs logger hierarchy, so we filter by attaching to
every handler on logging.getLogger('mkdocs').  CountHandler.handle() does
call self.filter(), so this correctly prevents those records from being counted.
The CountHandler is added to the mkdocs logger before on_config is called.
"""

import logging


class _GriffeDocstringFilter(logging.Filter):
    _SUPPRESSED = (
        "Confusing indentation for continuation line",
        "No type or annotation for parameter '**kwargs'",
    )

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return not any(pattern in msg for pattern in self._SUPPRESSED)


_FILTER = _GriffeDocstringFilter()


def on_config(config):  # noqa: ANN001, ANN201
    # CountHandler (strict mode warning counter) lives on the 'mkdocs' logger,
    # not on root.  Add the filter there so it is consulted before counting.
    for handler in logging.getLogger("mkdocs").handlers:
        handler.addFilter(_FILTER)
    return config
