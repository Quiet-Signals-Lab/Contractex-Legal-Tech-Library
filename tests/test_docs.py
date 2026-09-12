"""
Execute every Python code block in the README and the docs site, and every
script in examples/, against the current API.

* Blocks in one page run in order in a shared namespace, like a reader would.
* A ```python block immediately followed by a ```text block must print
  exactly that text, so every output shown in the docs is real.
* A block preceded by ``<!-- no-run -->`` is skipped (use sparingly, e.g. for
  a snippet that needs a live database).
* LLM providers are stubbed: constructors skip network and API-key checks and
  calls return empty results, so docs never show model output as if real.
"""

from __future__ import annotations

import contextlib
import io
import re
import runpy
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
PAGES = [ROOT / "README.md", *sorted((ROOT / "docs").rglob("*.md"))]
EXAMPLES = sorted((ROOT / "examples").glob("*.py"))

_FENCE = re.compile(
    r"(?P<skip><!-- no-run -->\s*\n)?```(?P<lang>\w*)[^\n]*\n(?P<body>.*?)\n```", re.S
)


def blocks(path: Path) -> list[tuple[int, str, str | None]]:
    """(line, code, expected output) for each runnable python block."""
    text = path.read_text(encoding="utf-8")
    fences = list(_FENCE.finditer(text))
    out = []
    for i, m in enumerate(fences):
        if m.group("lang") != "python" or m.group("skip"):
            continue
        expected = None
        nxt = fences[i + 1] if i + 1 < len(fences) else None
        if (
            nxt is not None
            and nxt.group("lang") == "text"
            and not text[m.end() : nxt.start()].strip()
        ):
            expected = nxt.group("body")
        out.append((text.count("\n", 0, m.start()) + 1, m.group("body"), expected))
    return out


@pytest.fixture
def stub_llms(monkeypatch):
    """No network: every provider constructs offline and returns empty results."""
    from contractex.llm import AnthropicProvider, GoogleProvider, LocalProvider, OpenAIProvider

    def init(self, model: str, *args: Any, **kwargs: Any) -> None:
        self._model = model
        self._model_name = model

    def complete(self, prompt: str, *args: Any, **kwargs: Any) -> str:
        return ""

    def extract_structured(self, prompt: str, schema: type[BaseModel], *a: Any, **k: Any):
        return schema()

    for cls in (LocalProvider, OpenAIProvider, AnthropicProvider, GoogleProvider):
        monkeypatch.setattr(cls, "__init__", init)
        monkeypatch.setattr(cls, "complete", complete)
        monkeypatch.setattr(cls, "extract_structured", extract_structured)
        monkeypatch.setattr(cls, "model", property(lambda self: self._model))
    monkeypatch.chdir(ROOT)


def page_id(path: Path) -> str:
    return str(path.relative_to(ROOT))


@pytest.mark.parametrize("path", [p for p in PAGES if blocks(p)], ids=page_id)
def test_doc_page_examples(path: Path, stub_llms) -> None:
    namespace: dict[str, Any] = {"__name__": "__docs__"}
    for line, code, expected in blocks(path):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            exec(compile(code, f"{page_id(path)}:{line}", "exec"), namespace)
        if expected is not None:
            assert buf.getvalue().rstrip("\n") == expected.rstrip("\n"), f"{page_id(path)}:{line}"


@pytest.mark.parametrize("script", EXAMPLES, ids=lambda p: p.name)
def test_example_scripts(script: Path, stub_llms) -> None:
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(str(script), run_name="__main__")
