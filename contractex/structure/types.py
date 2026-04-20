"""
Type definitions for Layer 1 (structural parse) output.

All types here are pure data containers — no LLM calls, no I/O.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Parse warnings
# ---------------------------------------------------------------------------


@dataclass
class ParseWarning:
    """
    Emitted when the parser encounters ambiguous or potentially incorrect
    structure rather than silently producing wrong output.
    """

    code: str  # machine-readable identifier, e.g. "AMBIGUOUS_NUMBERING"
    message: str  # human-readable description
    location: str = ""  # best-effort position hint, e.g. "section 4.2"
    text_snippet: str = ""  # up to 120 chars of relevant text


# ---------------------------------------------------------------------------
# Section tree
# ---------------------------------------------------------------------------


@dataclass
class Section:
    """
    A single node in the contract's section hierarchy.

    Numbering examples handled:
      1.          Numeric top-level
      1.1         Numeric sub-section
      4.1(a)      Alpha-numeric
      4.1(a)(i)   Deep alpha-numeric
      Section 4   Named numeric
      Article III Roman-numeral top-level
      (a)         Standalone lettered
      RECITALS    Named block (no number)
    """

    number: str  # parsed number/label, e.g. "4.1(a)"
    title: str  # heading text, empty string if none
    text: str  # body text (leaf content)
    level: int  # 0 = top-level, 1 = child, 2 = grandchild, …
    parent_number: str = ""  # empty string for top-level sections
    children: list[Section] = field(default_factory=list)

    # Source offsets in the original document text (char positions)
    start_char: int = 0
    end_char: int = 0

    @property
    def full_ref(self) -> str:
        """Return the canonical section reference, e.g. 'Section 4.1(a)'."""
        return f"Section {self.number}" if self.number else self.title

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0

    def iter_leaves(self) -> Iterator[Section]:
        """Depth-first iteration over all leaf sections."""
        if self.is_leaf:
            yield self
        else:
            for child in self.children:
                yield from child.iter_leaves()

    def iter_all(self) -> Iterator[Section]:
        """Depth-first iteration over self and all descendants."""
        yield self
        for child in self.children:
            yield from child.iter_all()

    def __repr__(self) -> str:
        child_count = len(self.children)
        snippet = self.text[:60].replace("\n", " ") if self.text else ""
        return (
            f"Section(number={self.number!r}, level={self.level}, "
            f"children={child_count}, text={snippet!r})"
        )


# ---------------------------------------------------------------------------
# Defined terms
# ---------------------------------------------------------------------------


@dataclass
class DefinedTerm:
    """
    A term formally defined within the contract.

    Captured from both definition patterns:
      1. Inline:   "Confidential Information" means any information ...
      2. Parenthetical: ... (the "Disclosing Party") ...
    """

    term: str  # the defined term as written, e.g. "Confidential Information"
    definition_text: str  # the full definition text
    definition_section: str  # section number where the term is defined
    usages: list[str] = field(default_factory=list)  # section numbers where the term appears


# ---------------------------------------------------------------------------
# Cross-reference
# ---------------------------------------------------------------------------


@dataclass
class CrossReference:
    """A resolved or unresolved cross-reference found in the contract text."""

    raw_text: str  # e.g. "Section 4.2(b)" or "Article III"
    source_section: str  # section number where the reference appears
    target_number: str  # normalised section number this points to, or ""
    resolved: bool = False  # True if target_number maps to an actual Section


# ---------------------------------------------------------------------------
# Structural metadata
# ---------------------------------------------------------------------------


@dataclass
class SignatureBlock:
    party_name: str
    role: str  # e.g. "Licensor", or "" if undetected
    signature_line_text: str


@dataclass
class Schedule:
    label: str  # e.g. "Schedule A", "Exhibit 1", "Annex I"
    title: str  # heading text following the label
    text: str  # full text of the schedule


# ---------------------------------------------------------------------------
# Root document structure
# ---------------------------------------------------------------------------


@dataclass
class DocumentStructure:
    """
    Complete structural parse of a contract document.

    This is the sole output of Layer 1.  No LLM calls are made to produce
    any field on this object.
    """

    sections: list[Section] = field(default_factory=list)
    defined_terms: dict[str, DefinedTerm] = field(default_factory=dict)
    cross_references: list[CrossReference] = field(default_factory=list)
    signature_blocks: list[SignatureBlock] = field(default_factory=list)
    schedules: list[Schedule] = field(default_factory=list)
    recitals: list[str] = field(default_factory=list)  # WHEREAS clause texts
    governing_law_hint: str = ""  # quick regex signal, e.g. "New York"
    warnings: list[ParseWarning] = field(default_factory=list)

    # Index built by the parser for fast look-up
    _section_index: dict[str, Section] = field(default_factory=dict, repr=False)

    @property
    def unresolved_refs(self) -> list[CrossReference]:
        """Cross-references that couldn't be mapped to a known section."""
        return [r for r in self.cross_references if not r.resolved]

    def resolve_ref(self, raw_text: str) -> Section | None:
        """
        Look up a section by its reference text.

        Accepts forms like "Section 4.2(b)", "4.2(b)", "Article III", "§ 4.2".
        Returns the matching Section or None if not found.
        """
        normalised = _normalise_ref_text(raw_text)
        return self._section_index.get(normalised)

    def get_section(self, number: str) -> Section | None:
        """Direct lookup by normalised section number."""
        return self._section_index.get(number.strip())

    def iter_all_sections(self) -> Iterator[Section]:
        """Depth-first iteration over the entire section tree."""
        for s in self.sections:
            yield from s.iter_all()


def _normalise_ref_text(raw: str) -> str:
    """
    Strip leading keywords and whitespace from a cross-reference string
    to get a bare section number suitable for index lookup.

    Examples:
      "Section 4.2(b)"  →  "4.2(b)"
      "Article III"     →  "III"
      "§ 4.2"           →  "4.2"
      "clause 2.1"      →  "2.1"
    """
    import re

    s = raw.strip()
    s = re.sub(
        r"^(section|article|clause|para(?:graph)?|exhibit|schedule|annex|§)\s*",
        "",
        s,
        flags=re.IGNORECASE,
    )
    return s.strip()
