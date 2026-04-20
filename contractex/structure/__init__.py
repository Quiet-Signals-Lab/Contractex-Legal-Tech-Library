"""
contractex.structure — Layer 1: Deterministic structural parse.

Public API::

    from contractex.structure import parse_structure

    structure = parse_structure(full_text)

    # Section tree
    for section in structure.iter_all_sections():
        print(section.number, section.title)

    # Defined terms (no LLM)
    print(structure.defined_terms["Confidential Information"])

    # Cross-references
    section = structure.resolve_ref("Section 4.2(b)")
    print(structure.unresolved_refs)

    # Structural metadata
    print(structure.governing_law_hint)
    print(structure.signature_blocks)
    print(structure.schedules)
    print(structure.recitals)

    # Parse quality signals
    for warning in structure.warnings:
        print(warning.code, warning.message)
"""

from __future__ import annotations

from contractex.structure.cross_refs import CrossReferenceResolver
from contractex.structure.defined_terms import DefinedTermsRegistry
from contractex.structure.parser import ContractStructureParser
from contractex.structure.types import (
    CrossReference,
    DefinedTerm,
    DocumentStructure,
    ParseWarning,
    Schedule,
    Section,
    SignatureBlock,
)


def parse_structure(text: str) -> DocumentStructure:
    """
    Parse contract plain text into a fully resolved DocumentStructure.

    This is the main entry point for Layer 1.  No LLM calls are made.

    Steps:
      1. Detect section headers and build a section hierarchy tree.
      2. Extract recitals, schedules, and signature blocks.
      3. Detect governing law via regex.
      4. Build defined-terms registry.
      5. Resolve cross-references.

    Args:
        text: Full plain-text content of the contract.

    Returns:
        DocumentStructure — section tree, defined terms, cross-refs,
        structural metadata, and any parse warnings.

    Example::

        structure = parse_structure(open("agreement.txt").read())
        ip_section = structure.resolve_ref("Section 4.2(b)")
        print(structure.defined_terms.keys())
    """
    parser = ContractStructureParser()
    structure = parser.parse(text)

    registry = DefinedTermsRegistry()
    registry.populate(structure, text)

    resolver = CrossReferenceResolver()
    resolver.resolve(structure)

    return structure


__all__ = [
    "parse_structure",
    "ContractStructureParser",
    "DefinedTermsRegistry",
    "CrossReferenceResolver",
    "DocumentStructure",
    "Section",
    "DefinedTerm",
    "CrossReference",
    "ParseWarning",
    "Schedule",
    "SignatureBlock",
]
