"""
Defined terms registry builder.

Identifies and indexes terms formally defined in a contract using two
patterns common to commercial contracts:

  Pattern A — Inline definition:
      "Confidential Information" means any information ...
      "Term" shall mean a period of twenty-four (24) months ...

  Pattern B — Parenthetical designation:
      ... Acme Corporation ("the Company") ...
      ... a period of twenty-four months (the "Term") ...

The registry maps each term to the section where it is defined and
records every other section where the term appears (usages).

Zero LLM calls.
"""

from __future__ import annotations

import re

from contractex.structure.types import DefinedTerm, DocumentStructure

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Pattern A: "Term" means / "Term" shall mean
_INLINE_DEF_PATTERN = re.compile(
    r'"([^"]{2,80})"\s+(?:means?|shall\s+means?|refers?\s+to|is\s+defined\s+as)\s+(.{10,})',
    re.IGNORECASE,
)

# Pattern B: ("Term") or (the "Term") — parenthetical designation
_PAREN_DEF_PATTERN = re.compile(
    r'\((?:the\s+)?"([^"]{2,80})"\)',
    re.IGNORECASE,
)

# Minimum length for a term to be worth tracking
_MIN_TERM_LEN = 3


class DefinedTermsRegistry:
    """
    Build a defined-terms registry from a DocumentStructure.

    Usage::

        from contractex.structure import parse_structure
        from contractex.structure.defined_terms import DefinedTermsRegistry

        structure = parse_structure(full_text)
        registry = DefinedTermsRegistry()
        registry.populate(structure, full_text)

        # structure.defined_terms is now populated
        print(structure.defined_terms["Confidential Information"])
    """

    def populate(self, structure: DocumentStructure, full_text: str) -> None:
        """
        Scan *structure* and *full_text* to build structure.defined_terms in-place.

        Two passes:
          1. Find definition sites (sections that define a term).
          2. Find usage sites (sections where the term appears as a quoted string).
        """
        # Pass 1: find definitions
        defined: dict[str, DefinedTerm] = {}

        for section in structure.iter_all_sections():
            combined_text = f"{section.title} {section.text}"

            # Pattern A: inline definition
            for m in _INLINE_DEF_PATTERN.finditer(combined_text):
                term = m.group(1).strip()
                definition_text = m.group(2).strip()
                if len(term) >= _MIN_TERM_LEN and term not in defined:
                    defined[term] = DefinedTerm(
                        term=term,
                        definition_text=definition_text,
                        definition_section=section.number,
                    )

            # Pattern B: parenthetical designation
            # We only treat these as definitions if they appear in the preamble
            # (first ~2000 chars) or in a section titled "Definitions"
            is_def_section = re.search(r"definition", section.title, re.IGNORECASE) is not None
            is_early_section = section.start_char < 3000
            if is_def_section or is_early_section:
                for m in _PAREN_DEF_PATTERN.finditer(section.text):
                    term = m.group(1).strip()
                    if len(term) >= _MIN_TERM_LEN and term not in defined:
                        # Context: use the sentence containing the match as the definition
                        start = max(0, m.start() - 200)
                        snippet = section.text[start : m.end() + 50].strip()
                        defined[term] = DefinedTerm(
                            term=term,
                            definition_text=snippet,
                            definition_section=section.number,
                        )

        # Pass 2: find usages
        # For each defined term, search for quoted occurrences in each section
        for section in structure.iter_all_sections():
            section_text = section.text
            for term, dt in defined.items():
                # Match the term as a quoted string (both single and double quotes)
                pattern = re.compile(
                    r'["\u201c\u201d]' + re.escape(term) + r'["\u201c\u201d]',
                    re.IGNORECASE,
                )
                if pattern.search(section_text):
                    if section.number != dt.definition_section:
                        if section.number not in dt.usages:
                            dt.usages.append(section.number)

        structure.defined_terms = defined
