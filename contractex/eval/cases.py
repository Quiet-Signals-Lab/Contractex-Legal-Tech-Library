"""
EvalCase and EvalSuite — labeled test cases for extraction quality regression.

Cases can be loaded from YAML or JSON files.  Each case specifies the input
(document path or inline text), the expected extracted field values, and
optional per-field importance weights.

YAML schema::

    # Bare list of cases, or a dict with name/description + cases list
    - id: us_statute_fair_use
      description: "17 USC 107 — fair use"
      doc_type: statute
      input_text: |
        Notwithstanding the provisions of sections 106 and 106A ...
      expected_fields:
        jurisdiction: US-Federal
        citation: "17 U.S.C. § 107"
      field_weights:
        citation: 2.0   # citation accuracy matters twice as much

    - id: spanish_passport_john
      description: "Sample Spanish passport extraction"
      doc_type: identity_doc
      input_path: tests/fixtures/passport_sample.pdf
      expected_fields:
        surname: GARCIA
        given_name: JOSE
        nationality: ESP
        mrz_valid: true
      tags: [passport, spanish, immigration]
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class EvalCase(BaseModel):
    """A single labeled eval case."""

    id: str = Field(..., description="Unique case identifier")
    description: str = Field("", description="Human-readable description")
    doc_type: str | None = Field(None, description="Expected document type")

    # --- Input (exactly one must be set) ---
    input_path: str | None = Field(
        None,
        description="Path to the input document (relative to project root)",
    )
    input_text: str | None = Field(
        None,
        description="Inline document text (for small / synthetic cases)",
    )

    # --- Ground truth ---
    expected_fields: dict[str, Any] = Field(
        default_factory=dict,
        description="Expected extracted field values (field_name → value)",
    )

    # --- Per-field importance weights (default 1.0) ---
    field_weights: dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Optional importance weight per field.  Higher-weight fields "
            "contribute more to the weighted field accuracy metric."
        ),
    )

    # --- Privacy / redaction ground truth ---
    expected_pii_entities: list[str] | None = Field(
        None,
        description=(
            "Entity types expected to be detected (e.g. ['PERSON', 'EMAIL_ADDRESS']). "
            "When set, the harness will evaluate PII recall and precision."
        ),
    )
    should_be_blocked: bool = Field(
        False,
        description=(
            "True when the LLM call for this document should be blocked by "
            "the privacy router (e.g. sensitivity='secret').  The harness "
            "records a pass when the router raises PrivacyBlockedError."
        ),
    )
    expected_redaction_count: int | None = Field(
        None,
        description=(
            "Expected number of redacted spans after PIIRedactor is applied. "
            "Useful for regression-testing that all PII is masked."
        ),
    )

    # --- Metadata ---
    tags: list[str] = Field(default_factory=list, description="Arbitrary tags for filtering")
    metadata: dict[str, Any] = Field(default_factory=dict)

    def get_weight(self, field_name: str) -> float:
        """Return the importance weight for *field_name* (default 1.0)."""
        return self.field_weights.get(field_name, 1.0)

    def has_input(self) -> bool:
        """Return True if at least one input source is set."""
        return bool(self.input_path or self.input_text)


class EvalSuite(BaseModel):
    """A named collection of EvalCases."""

    name: str = Field(..., description="Suite name")
    description: str = Field("", description="Suite description")
    cases: list[EvalCase] = Field(default_factory=list)

    # ------------------------------------------------------------------
    # Loaders
    # ------------------------------------------------------------------

    @classmethod
    def from_yaml(cls, path: str | Path) -> EvalSuite:
        """Load an EvalSuite from a YAML file."""
        try:
            import yaml  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "PyYAML is required to load YAML eval suites. " "Install with: pip install pyyaml"
            ) from exc

        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls._from_raw(data, stem=Path(path).stem)

    @classmethod
    def from_json(cls, path: str | Path) -> EvalSuite:
        """Load an EvalSuite from a JSON file."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls._from_raw(data, stem=Path(path).stem)

    @classmethod
    def load(cls, path: str | Path) -> EvalSuite:
        """Auto-detect format from file extension (.yml/.yaml or .json)."""
        path = Path(path)
        if path.suffix in (".yml", ".yaml"):
            return cls.from_yaml(path)
        if path.suffix == ".json":
            return cls.from_json(path)
        raise ValueError(
            f"Unsupported eval suite format: {path.suffix!r}. " "Expected .yml, .yaml, or .json"
        )

    @classmethod
    def from_cases(cls, cases: list[EvalCase], name: str = "inline") -> EvalSuite:
        """Build a suite directly from a list of EvalCase objects."""
        return cls(name=name, cases=cases)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def filter_by_tag(self, tag: str) -> EvalSuite:
        """Return a new EvalSuite containing only cases with *tag*."""
        return EvalSuite(
            name=self.name,
            description=self.description,
            cases=[c for c in self.cases if tag in c.tags],
        )

    def filter_by_doc_type(self, doc_type: str) -> EvalSuite:
        """Return a new EvalSuite containing only cases matching *doc_type*."""
        return EvalSuite(
            name=self.name,
            description=self.description,
            cases=[c for c in self.cases if c.doc_type == doc_type],
        )

    def __len__(self) -> int:
        return len(self.cases)

    def __repr__(self) -> str:
        return f"EvalSuite(name={self.name!r}, cases={len(self.cases)})"

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @classmethod
    def _from_raw(cls, data: Any, stem: str) -> EvalSuite:
        """Parse raw YAML/JSON data into an EvalSuite."""
        if isinstance(data, list):
            # Bare list of case dicts
            return cls(
                name=stem,
                cases=[EvalCase.model_validate(c) for c in data],
            )
        if isinstance(data, dict):
            return cls.model_validate(data)
        raise ValueError(f"Expected a list or dict, got {type(data).__name__}")
