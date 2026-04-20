# Release Workflow

This document describes the end-to-end steps for releasing a new version of ContractEx to PyPI.

> **MANDATORY**: The pre-release quality gate in Step 0 is **never optional**.
> No version bump, no tag, no PyPI upload until every check passes locally.
> Skipping it guarantees CI failures and a broken release.

---

## Step 0 — Pre-release Quality Gate (MANDATORY, NEVER SKIP)

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

# Auto-fix all safe lint issues (isort, UP-series, C4, etc.)
ruff check --fix contractex/ tests/

# Manually fix anything ruff could not auto-fix (B904, F841, etc.)
ruff check contractex/ tests/   # re-run to see remaining manual fixes

# Run mypy — all errors must be resolved before proceeding
mypy contractex/
# Common fixes:
#   Missing stubs  → pip install types-<package>  (e.g. types-PyYAML)
#   Optional[X] in sort key → use `value or X.min` to guarantee a non-None return
#   Third-party package syntax errors → add [[tool.mypy.overrides]] with follow_imports = "skip"

# Then re-run the full gate — it must be completely clean
make pre-release
```

Do **not** proceed to Step 1 until `make pre-release` exits 0 with no errors.

---

## Release Steps

### Step 1 — Commit feature work on `main`

```bash
git add .
git commit -m "feat: <description>"
```

### Step 2 — Bump the version

Edit two files:

- `contractex/__version__.py` → `__version__ = "X.Y.Z"`
- `pyproject.toml` → `version = "X.Y.Z"`

Commit as a standalone change:

```bash
git add contractex/__version__.py pyproject.toml
git commit -m "chore: bump version to X.Y.Z"
```

### Step 3 — Update CHANGELOG.md

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

### Step 4 — Push to main

```bash
git push origin main
```

### Step 5 — Build the distribution

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

### Step 6 — Publish to PyPI

```bash
python3 -m twine upload dist/* -u __token__
```

Set your PyPI API token via the environment variable to avoid interactive prompts:

```bash
export TWINE_PASSWORD="pypi-..."
python3 -m twine upload dist/* -u __token__
```

### Step 7 — Tag the release

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
