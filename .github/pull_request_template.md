## What and why

<!-- One change per pull request. Link the issue if there is one. -->

## Checks

- [ ] `ruff check`, `black --check`, `mypy contractex` and `pytest` pass
- [ ] Privacy-related changes start with a test that failed before the fix
- [ ] Docs examples still run (`pytest tests/test_docs.py`); outputs shown are real
- [ ] `python -m benchmarks --check` passes, or results were regenerated and the diff is explained
- [ ] `CHANGELOG.md` updated under "Unreleased" for user-visible changes
