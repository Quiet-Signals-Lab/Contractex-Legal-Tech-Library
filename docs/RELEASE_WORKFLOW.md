# Release Workflow

This document describes the end-to-end steps for releasing a new version of ContractEx to PyPI.

---

## Pre-release Quality Gate

Run all checks locally before touching versions or git tags.  The `make pre-release` command is the canonical way to do this:

```bash
make pre-release
```

This runs in order:

| Step | Command | What it checks |
|---|---|---|
| Format | `black --check contractex/ tests/` | Consistent code style |
| Lint | `ruff check contractex/ tests/` | Unused imports, style issues, anti-patterns |
| Type check | `mypy contractex/` | Static type correctness |
| Unit tests | `pytest -m unit` | Core logic without external deps |

**All four must pass before proceeding.**  Fix any failures first:

```bash
# Auto-fix formatting
black contractex/ tests/

# Auto-fix safe lint issues
ruff check --fix contractex/ tests/

# Then re-run the gate
make pre-release
```

---

## Release Steps

### 1. Commit feature work on `main`

```bash
git add .
git commit -m "feat: <description>"
```

### 2. Bump the version

Edit two files:

- `contractex/__version__.py` → `__version__ = "X.Y.Z"`
- `pyproject.toml` → `version = "X.Y.Z"`

Commit as a standalone change:

```bash
git add contractex/__version__.py pyproject.toml
git commit -m "chore: bump version to X.Y.Z"
```

### 3. Update CHANGELOG.md

Add an entry under `## [Unreleased]` (or create a new versioned heading):

```markdown
## [X.Y.Z] - YYYY-MM-DD

### Added
- …

### Fixed
- …
```

Commit:

```bash
git add CHANGELOG.md
git commit -m "docs: update changelog for X.Y.Z"
```

### 4. Push to main

```bash
git push origin main
```

### 5. Build the distribution

```bash
rm -rf dist/
python3 -m build
```

Verify the output:

```bash
ls dist/
# contractex-X.Y.Z-py3-none-any.whl
# contractex-X.Y.Z.tar.gz
```

### 6. Publish to PyPI

```bash
python3 -m twine upload dist/*
```

You will be prompted for your PyPI API token (or it can be set via `TWINE_PASSWORD`).

### 7. Tag the release

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

---

## CI Checks (GitHub Actions)

The `.github/workflows/tests.yml` CI pipeline runs automatically on every push and PR.  It executes:

1. `black --check contractex/` — formatting
2. `ruff check contractex/` — linting
3. `mypy contractex/` — type checking
4. `pytest` — full test suite with coverage upload to Codecov

A PR cannot be merged if any CI check fails.

---

## Quick Reference

```bash
# Run all QA checks (no tests)
make qa

# Run QA + unit tests (full pre-release gate)
make pre-release

# Format + lint + type-check individually
make format-check
make lint
make type-check
```
