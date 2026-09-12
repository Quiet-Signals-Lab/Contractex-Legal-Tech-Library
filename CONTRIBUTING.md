# Contributing to Contractex

Contractex is maintained by one person.  Bug reports with a reproduction,
fixes with tests, and documentation corrections are the most useful
contributions.  For anything larger, open an issue first so we can agree on
the approach before you write code.

## Setup

```bash
git clone https://github.com/Quiet-Signals-Lab/Contractex-Legal-Tech-Library.git
cd Contractex-Legal-Tech-Library
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

No API keys, model downloads or database are needed for the test suite.
Tests that need PostgreSQL skip unless `POSTGRES_USER` (and the other
`POSTGRES_*` variables) point at a server.

## Checks

CI runs these on every pull request.  Run them before you push:

```bash
ruff check contractex tests benchmarks
black --check contractex tests benchmarks
mypy contractex
pytest                          # includes every code example in README.md and docs/
python -m benchmarks --check    # committed benchmark results match a fresh run
```

Tests run on Python 3.11 to 3.14.

## Rules for changes

- **Privacy code** (`contractex/privacy`, and anything that calls a model):
  write a failing test that shows the problem before changing the code.  The
  routing rules and the guarantee that `secret` text never reaches a model
  are load-bearing.
- **Documentation examples are executed.**  A ```` ```python ```` block
  followed by a ```` ```text ```` block must print exactly that text.  Never
  show model output as if it were real.
- **Numbers in the docs come from `python -m benchmarks`.**  If a change
  affects results, regenerate them and commit the diff.  Do not write results
  by hand.
- **No new required dependencies** without discussion.  Vendor SDKs belong in
  extras.

## Pull requests

Branch from `main`, keep each commit to one change, and describe what changed
and why.  Commit messages follow
[Conventional Commits](https://www.conventionalcommits.org/) (`fix:`, `feat:`,
`docs:`, `test:`, `build:`, `ci:`, `chore:`).

## Reporting bugs

Open an [issue](https://github.com/Quiet-Signals-Lab/Contractex-Legal-Tech-Library/issues)
with the Contractex version (`python -c "import contractex; print(contractex.__version__)"`),
your Python version and OS, the extras installed, a minimal example, and the
full traceback.  Do not paste real client documents: reduce the problem to
synthetic text.

Security problems, including any way for document text to reach a model
against its privacy profile, go to the address in [SECURITY.md](https://github.com/Quiet-Signals-Lab/Contractex-Legal-Tech-Library/blob/main/SECURITY.md),
not the issue tracker.

## License

Contributions are licensed under the [Apache License 2.0](https://github.com/Quiet-Signals-Lab/Contractex-Legal-Tech-Library/blob/main/LICENSE).
