"""
Playbook base class for contract risk analysis.

A Playbook is a versioned, serializable set of rules that governs what
clauses are expected in a contract, what constitutes a risk, and what
remedial language is recommended.

Playbooks are serializable to YAML so that non-engineers (e.g. lawyers,
compliance officers) can author and maintain them without touching Python.

Inheritance model:
  - Subclass Playbook to create a practice-area-specific playbook.
  - Override required_clauses and rules as class attributes.
  - Call super().__init__() and then customize in __init__ if dynamic
    configuration is needed.
  - Use inherit_from() to compose playbooks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Optional YAML support (pyyaml); only required for load/save operations
try:
    import yaml as _yaml

    _YAML_AVAILABLE = True
except ImportError:
    _YAML_AVAILABLE = False


class RiskSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class PlaybookRule:
    """
    A single risk-detection rule.

    Rules can be evaluated against extracted clause text without any LLM call.
    """

    id: str  # e.g. "nda.indemnification.must_be_bilateral"
    clause_type: str  # CUAD clause type this rule targets
    description: str  # human-readable problem description
    severity: RiskSeverity
    recommended_language: str = ""  # sample remedial language

    # Pattern-match conditions (at least one should be set)
    required_keywords: list[str] = field(default_factory=list)  # ALL must be absent to flag
    forbidden_keywords: list[str] = field(default_factory=list)  # ANY triggers a flag
    required_pattern: str = ""  # regex that must match
    forbidden_pattern: str = ""  # regex that must not match

    # When True: flag if the clause_type is absent entirely (missing-clause check)
    flag_if_missing: bool = False

    def matches(self, clause_text: str) -> bool:
        """
        Return True if this rule fires (a risk is present) for the given clause text.
        """
        text_lower = clause_text.lower()

        # Forbidden keywords: any hit → flag
        for kw in self.forbidden_keywords:
            if kw.lower() in text_lower:
                return True

        # Required keywords: if all are absent → flag
        if self.required_keywords:
            if not all(kw.lower() in text_lower for kw in self.required_keywords):
                return True

        # Required pattern: if absent → flag
        if self.required_pattern:
            if not re.search(self.required_pattern, clause_text, re.IGNORECASE):
                return True

        # Forbidden pattern: if present → flag
        if self.forbidden_pattern:
            if re.search(self.forbidden_pattern, clause_text, re.IGNORECASE):
                return True

        return False


@dataclass
class Playbook:
    """
    A versioned collection of rules and required-clause checks for a
    specific practice area or contract type.

    Subclass this to create domain-specific playbooks (NDA, SaaS, etc.).
    """

    name: str
    version: str
    description: str = ""
    required_clauses: list[str] = field(default_factory=list)  # CUAD types that must be present
    rules: list[PlaybookRule] = field(default_factory=list)
    _parent: Playbook | None = field(default=None, repr=False)

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------

    def inherit_from(self, parent: Playbook) -> None:
        """
        Inherit all rules and required clauses from *parent*, then apply
        this playbook's overrides on top.

        Rules with matching IDs override the parent's rule.
        """
        self._parent = parent
        parent_rule_ids = {r.id for r in self.rules}
        for rule in parent.rules:
            if rule.id not in parent_rule_ids:
                self.rules.append(rule)
        for clause in parent.required_clauses:
            if clause not in self.required_clauses:
                self.required_clauses.append(clause)

    # ------------------------------------------------------------------
    # YAML serialization
    # ------------------------------------------------------------------

    def to_yaml(self) -> str:
        """Serialize this playbook to a YAML string."""
        if not _YAML_AVAILABLE:
            raise ImportError("pyyaml is required for YAML serialization. pip install pyyaml")

        data: dict[str, Any] = {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "required_clauses": self.required_clauses,
            "rules": [
                {
                    "id": r.id,
                    "clause_type": r.clause_type,
                    "description": r.description,
                    "severity": r.severity.value,
                    "recommended_language": r.recommended_language,
                    "required_keywords": r.required_keywords,
                    "forbidden_keywords": r.forbidden_keywords,
                    "required_pattern": r.required_pattern,
                    "forbidden_pattern": r.forbidden_pattern,
                    "flag_if_missing": r.flag_if_missing,
                }
                for r in self.rules
            ],
        }
        return str(_yaml.dump(data, default_flow_style=False, sort_keys=False))

    @classmethod
    def from_yaml(cls, yaml_text: str) -> Playbook:
        """Deserialize a Playbook from a YAML string."""
        if not _YAML_AVAILABLE:
            raise ImportError("pyyaml is required. pip install pyyaml")

        data = _yaml.safe_load(yaml_text)
        rules = [
            PlaybookRule(
                id=r["id"],
                clause_type=r["clause_type"],
                description=r["description"],
                severity=RiskSeverity(r["severity"]),
                recommended_language=r.get("recommended_language", ""),
                required_keywords=r.get("required_keywords", []),
                forbidden_keywords=r.get("forbidden_keywords", []),
                required_pattern=r.get("required_pattern", ""),
                forbidden_pattern=r.get("forbidden_pattern", ""),
                flag_if_missing=r.get("flag_if_missing", False),
            )
            for r in data.get("rules", [])
        ]
        return cls(
            name=data["name"],
            version=data["version"],
            description=data.get("description", ""),
            required_clauses=data.get("required_clauses", []),
            rules=rules,
        )

    @classmethod
    def from_yaml_file(cls, path: str) -> Playbook:
        """Load a playbook from a YAML file."""
        with open(path) as f:
            return cls.from_yaml(f.read())

    def to_yaml_file(self, path: str) -> None:
        """Save this playbook to a YAML file."""
        with open(path, "w") as f:
            f.write(self.to_yaml())
