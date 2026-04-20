"""
Cross-reference resolver for contract documents.

Scans every section's text for references to other sections
("Section 4.2(b)", "Article III", "clause 2.1", "§ 4"), then
attempts to resolve each reference against the section index in
DocumentStructure.

Populates structure.cross_references and flags unresolved references
as a data quality signal.

Zero LLM calls.
"""

from __future__ import annotations

import re

from contractex.structure.types import CrossReference, DocumentStructure, _normalise_ref_text

# ---------------------------------------------------------------------------
# Reference detection pattern
# ---------------------------------------------------------------------------

# Captures explicit cross-reference phrases like:
#   "Section 4.2(b)"   "section 4"   "Article III"   "clause 2.1"
#   "§ 4.2"            "paragraph 3" "Exhibit A"
_REF_PATTERN = re.compile(
    r"""
    (?:
        (?:Section|Article|Clause|Para(?:graph)?|Exhibit|Schedule|Annex|§)\s*
        (?:[IVX]+|\d+(?:\.\d+)*(?:\([a-z0-9]+\))*)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


class CrossReferenceResolver:
    """
    Scan structure sections, detect cross-references, and attempt to resolve them.

    Usage::

        from contractex.structure.cross_refs import CrossReferenceResolver

        resolver = CrossReferenceResolver()
        resolver.resolve(structure)

        print(structure.unresolved_refs)
    """

    def resolve(self, structure: DocumentStructure) -> None:
        """
        Detect and resolve all cross-references in *structure* in-place.

        Populates structure.cross_references.
        Marks each reference as resolved=True if the target section exists.
        """
        refs: list[CrossReference] = []

        for section in structure.iter_all_sections():
            for m in _REF_PATTERN.finditer(section.text):
                raw_text = m.group(0).strip()
                target_number = _normalise_ref_text(raw_text)

                # Skip self-references
                if target_number == section.number:
                    continue

                resolved = target_number in structure._section_index
                refs.append(
                    CrossReference(
                        raw_text=raw_text,
                        source_section=section.number,
                        target_number=target_number,
                        resolved=resolved,
                    )
                )

        # Deduplicate: same raw_text + source pair only once
        seen: set[tuple[str, str]] = set()
        unique_refs: list[CrossReference] = []
        for r in refs:
            key = (r.raw_text, r.source_section)
            if key not in seen:
                seen.add(key)
                unique_refs.append(r)

        structure.cross_references = unique_refs
