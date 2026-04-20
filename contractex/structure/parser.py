"""
Deterministic section-hierarchy parser for contract documents.

Zero LLM calls. Every decision is rule-based and testable in isolation.

Supports numbering schemes found in real commercial contracts:
  Numeric         1.   1.1   1.1.1
  Alpha-numeric   4.1(a)   4.1(a)(i)   Section 4(b)
  Lettered        A.   B.   (a)   (i)
  Roman           Article I   Article III
  Named blocks    RECITALS   WHEREAS   SCHEDULE A

Emits ParseWarning rather than silently producing wrong output when
structure is ambiguous.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from contractex.structure.types import (
    DocumentStructure,
    ParseWarning,
    Schedule,
    Section,
    SignatureBlock,
)

# ---------------------------------------------------------------------------
# Numbering patterns (order matters — more specific before more general)
# ---------------------------------------------------------------------------

# Matches a section header line and captures (number, title_rest)
_HEADER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # "Article I — Definitions" / "Article 1." / "Article III"
    (
        "article",
        re.compile(
            r"^(Article\s+(?:[IVX]+|\d+)\.?)\s*(.*)?$",
            re.IGNORECASE,
        ),
    ),
    # "Section 4.2(b)" / "Section 4" / "SECTION 12"
    (
        "named_numeric",
        re.compile(
            r"^(Section\s+\d+(?:\.\d+)*(?:\([a-z0-9]+\))*)\s*(.*)?$",
            re.IGNORECASE,
        ),
    ),
    # "4.1.2(a)(i)." — deep numeric-alpha
    (
        "deep_numeric",
        re.compile(
            r"^(\d+(?:\.\d+)+(?:\([a-z0-9]+\))*\.?)\s+(.*)?$",
            re.IGNORECASE,
        ),
    ),
    # "4." or "4 " — top-level numeric
    (
        "numeric_top",
        re.compile(
            r"^(\d+\.)\s+(.+)$",
        ),
    ),
    # "(a)(i)" or "(a)" — parenthetical alpha/numeric
    (
        "paren_alpha",
        re.compile(
            r"^(\([a-z]\)(?:\([ivx]+\))?)\s*(.*)?$",
            re.IGNORECASE,
        ),
    ),
    # "A." or "B." — capital-letter top-level
    (
        "alpha_top",
        re.compile(
            r"^([A-Z]\.)\s+(.+)$",
        ),
    ),
    # ALL-CAPS heading (no number) — e.g. "RECITALS", "DEFINITIONS"
    (
        "caps_heading",
        re.compile(
            r"^([A-Z][A-Z\s\-]{2,60})$",
        ),
    ),
]

# Schedule/exhibit/annex header
_SCHEDULE_PATTERN = re.compile(
    r"^(Schedule|Exhibit|Annex|Attachment)\s+([A-Z0-9]+\.?)\s*(.*)?$",
    re.IGNORECASE,
)

# Signature block indicators
_SIGNATURE_PATTERNS = [
    re.compile(r"IN\s+WITNESS\s+WHEREOF", re.IGNORECASE),
    re.compile(r"AGREED\s+AND\s+ACCEPTED", re.IGNORECASE),
    re.compile(r"EXECUTED\s+(?:as\s+of|on|by)", re.IGNORECASE),
    re.compile(r"SIGNED\s+(?:by|on\s+behalf\s+of)", re.IGNORECASE),
]

# WHEREAS / recitals pattern
_RECITAL_PATTERN = re.compile(r"^WHEREAS[,;:]?\s+(.+)$", re.IGNORECASE)

# Governing law quick-detection (used to populate hint without LLM)
_GOV_LAW_PATTERNS = [
    re.compile(
        r"laws?\s+of\s+(?:the\s+(?:State|Commonwealth)\s+of\s+)?([A-Z][a-zA-Z\s]+)", re.IGNORECASE
    ),
    re.compile(
        r"(?:governed|construed)\s+(?:by|under|in\s+accordance\s+with)\s+(?:the\s+laws?\s+of\s+)?([A-Z][a-zA-Z\s,]+?)(?:\.|,|;|$)",
        re.IGNORECASE,
    ),
]


# ---------------------------------------------------------------------------
# Internal line representation
# ---------------------------------------------------------------------------


@dataclass
class _Line:
    text: str
    stripped: str
    char_offset: int  # byte offset from start of doc


@dataclass
class _ParsedHeader:
    kind: str  # pattern name
    number: str  # extracted number/label
    title: str  # text after the number
    line_idx: int
    char_offset: int


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class ContractStructureParser:
    """
    Parse a contract's plain text into a DocumentStructure.

    Usage::

        from contractex.structure import parse_structure
        from contractex.loaders import load

        doc = load("agreement.pdf")
        structure = parse_structure(doc.full_text)
    """

    def __init__(
        self,
        min_section_chars: int = 20,
        warn_on_ambiguous: bool = True,
    ) -> None:
        self._min_section_chars = min_section_chars
        self._warn_on_ambiguous = warn_on_ambiguous

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def parse(self, text: str) -> DocumentStructure:
        """
        Parse *text* and return a complete DocumentStructure.

        Args:
            text: Full plain-text content of the contract document.

        Returns:
            DocumentStructure with section tree, defined terms, cross-refs,
            schedules, recitals, governing-law hint, and any parse warnings.
        """
        lines = self._split_lines(text)
        headers = self._detect_headers(lines)
        warnings: list[ParseWarning] = []

        sections = self._build_section_tree(lines, headers, warnings)
        recitals = self._extract_recitals(lines)
        schedules = self._extract_schedules(lines, headers)
        sig_blocks = self._extract_signature_blocks(lines)
        gov_hint = self._extract_governing_law_hint(text)

        # Remove schedule headers from main section tree
        schedule_numbers = {s.label for s in schedules}
        sections = [s for s in sections if s.number not in schedule_numbers]

        structure = DocumentStructure(
            sections=sections,
            recitals=recitals,
            schedules=schedules,
            signature_blocks=sig_blocks,
            governing_law_hint=gov_hint,
            warnings=warnings,
        )

        self._build_section_index(structure)
        return structure

    # ------------------------------------------------------------------
    # Line splitting
    # ------------------------------------------------------------------

    def _split_lines(self, text: str) -> list[_Line]:
        lines: list[_Line] = []
        offset = 0
        for raw in text.split("\n"):
            lines.append(_Line(text=raw, stripped=raw.strip(), char_offset=offset))
            offset += len(raw) + 1  # +1 for the '\n'
        return lines

    # ------------------------------------------------------------------
    # Header detection
    # ------------------------------------------------------------------

    def _detect_headers(self, lines: list[_Line]) -> list[_ParsedHeader]:
        headers: list[_ParsedHeader] = []
        seen_numbers: dict[str, int] = {}  # number → first line_idx

        for i, line in enumerate(lines):
            s = line.stripped
            if not s or len(s) < 2:
                continue

            match_found = False
            for kind, pattern in _HEADER_PATTERNS:
                m = pattern.match(s)
                if not m:
                    continue

                number = m.group(1).strip().rstrip(".")
                title = m.group(2).strip() if len(m.groups()) >= 2 else ""

                # De-duplicate: same number seen before is suspicious
                if number in seen_numbers:
                    pass  # warnings handled later during tree build

                seen_numbers.setdefault(number, i)
                headers.append(
                    _ParsedHeader(
                        kind=kind,
                        number=number,
                        title=title,
                        line_idx=i,
                        char_offset=line.char_offset,
                    )
                )
                match_found = True
                break  # first matching pattern wins

            # Schedules are detected separately; skip them here
            if not match_found and _SCHEDULE_PATTERN.match(s):
                continue

        return headers

    # ------------------------------------------------------------------
    # Section tree construction
    # ------------------------------------------------------------------

    def _build_section_tree(
        self,
        lines: list[_Line],
        headers: list[_ParsedHeader],
        warnings: list[ParseWarning],
    ) -> list[Section]:
        """Convert the flat list of parsed headers + their body text into a tree."""

        if not headers:
            warnings.append(
                ParseWarning(
                    code="NO_SECTIONS_FOUND",
                    message="No section headers detected in the document.",
                )
            )
            return []

        # Pair each header with its body text
        flat_sections: list[Section] = []
        for idx, hdr in enumerate(headers):
            body_start = hdr.line_idx + 1
            body_end = headers[idx + 1].line_idx if idx + 1 < len(headers) else len(lines)
            body_lines = [lines[j].text for j in range(body_start, body_end)]
            body_text = "\n".join(body_lines).strip()

            level = self._infer_level(hdr)
            flat_sections.append(
                Section(
                    number=hdr.number,
                    title=hdr.title,
                    text=body_text,
                    level=level,
                    start_char=hdr.char_offset,
                    end_char=hdr.char_offset + len(body_text),
                )
            )

        # Warn on duplicate section numbers
        number_counts: dict[str, int] = {}
        for sec in flat_sections:
            number_counts[sec.number] = number_counts.get(sec.number, 0) + 1
        for number, count in number_counts.items():
            if count > 1:
                warnings.append(
                    ParseWarning(
                        code="DUPLICATE_SECTION_NUMBER",
                        message=f"Section number '{number}' appears {count} times.",
                        location=number,
                    )
                )

        # Detect numbering scheme switches mid-document
        self._detect_scheme_switch(flat_sections, warnings)

        # Build tree via level-based parent assignment
        roots: list[Section] = []
        stack: list[Section] = []  # stack[-1] is the most recent ancestor candidate

        for sec in flat_sections:
            # Pop stack until we find a valid parent (lower level)
            while stack and stack[-1].level >= sec.level:
                stack.pop()

            if stack:
                parent = stack[-1]
                sec.parent_number = parent.number
                parent.children.append(sec)
            else:
                roots.append(sec)

            stack.append(sec)

        return roots

    def _infer_level(self, hdr: _ParsedHeader) -> int:
        """Estimate depth level from the header pattern kind and number structure."""
        if hdr.kind in ("article", "caps_heading", "alpha_top"):
            return 0
        if hdr.kind == "numeric_top":
            return 0
        if hdr.kind == "named_numeric":
            # Count dots in the numeric part
            m = re.search(r"(\d[\d.]*)", hdr.number)
            if m:
                return m.group(1).count(".")
            return 0
        if hdr.kind == "deep_numeric":
            # e.g. "4.1.2(a)" → two dots = level 2, plus paren = +1
            dot_count = hdr.number.count(".")
            paren_count = len(re.findall(r"\([a-z0-9]+\)", hdr.number, re.IGNORECASE))
            return dot_count + paren_count
        if hdr.kind == "paren_alpha":
            # e.g. "(a)(i)" → two layers
            return len(re.findall(r"\([a-z0-9]+\)", hdr.number, re.IGNORECASE))
        return 0

    def _detect_scheme_switch(
        self,
        sections: list[Section],
        warnings: list[ParseWarning],
    ) -> None:
        """
        Detect when the document switches numbering scheme mid-document,
        which is common in contracts that blend article-level + clause-level numbering.
        """
        top_level = [s for s in sections if s.level == 0]
        if len(top_level) < 2:
            return

        kinds_seen: set[str] = set()
        for sec in top_level:
            if re.match(r"^[IVX]+$", sec.number):
                kinds_seen.add("roman")
            elif re.match(r"^\d+$", sec.number):
                kinds_seen.add("numeric")
            elif re.match(r"^[A-Z]$", sec.number.rstrip(".")):
                kinds_seen.add("alpha")
            elif re.match(r"^Article", sec.number, re.IGNORECASE):
                kinds_seen.add("article")

        if len(kinds_seen) > 1:
            warnings.append(
                ParseWarning(
                    code="MIXED_NUMBERING_SCHEMES",
                    message=(
                        f"Document uses multiple top-level numbering schemes: "
                        f"{', '.join(sorted(kinds_seen))}. "
                        f"Section hierarchy may be inaccurate."
                    ),
                )
            )

    # ------------------------------------------------------------------
    # Recitals
    # ------------------------------------------------------------------

    def _extract_recitals(self, lines: list[_Line]) -> list[str]:
        recitals: list[str] = []
        for line in lines:
            m = _RECITAL_PATTERN.match(line.stripped)
            if m:
                recitals.append(m.group(1).strip())
        return recitals

    # ------------------------------------------------------------------
    # Schedules / exhibits
    # ------------------------------------------------------------------

    def _extract_schedules(
        self, lines: list[_Line], headers: list[_ParsedHeader]
    ) -> list[Schedule]:
        schedules: list[Schedule] = []
        schedule_line_indices: list[int] = []

        for i, line in enumerate(lines):
            m = _SCHEDULE_PATTERN.match(line.stripped)
            if m:
                schedule_line_indices.append(i)
                kind_word = m.group(1)
                label_num = m.group(2).rstrip(".")
                label = f"{kind_word} {label_num}"
                title = m.group(3).strip() if m.group(3) else ""

                # Body: everything until the next schedule or end of doc
                next_start = (
                    schedule_line_indices[1] if len(schedule_line_indices) > 1 else len(lines)
                )
                body = "\n".join(lines[j].text for j in range(i + 1, next_start)).strip()

                schedules.append(Schedule(label=label, title=title, text=body))

        return schedules

    # ------------------------------------------------------------------
    # Signature blocks
    # ------------------------------------------------------------------

    def _extract_signature_blocks(self, lines: list[_Line]) -> list[SignatureBlock]:
        blocks: list[SignatureBlock] = []
        in_sig_block = False
        party_name_pattern = re.compile(r"^(?:By|Name|Title|Signature):\s*(.*)?$", re.IGNORECASE)
        party_line_pattern = re.compile(r"^([A-Z][A-Z\s,\.]+(?:LLC|Inc|Corp|Ltd|LP|LLP|PLC)\.?)$")

        current_name = ""
        current_role = ""

        for line in lines:
            s = line.stripped

            # Detect start of signature block
            if any(p.search(s) for p in _SIGNATURE_PATTERNS):
                in_sig_block = True
                continue

            if not in_sig_block:
                continue

            # Heuristic: all-caps company names often appear in sig blocks
            if party_line_pattern.match(s):
                if current_name:
                    blocks.append(
                        SignatureBlock(
                            party_name=current_name,
                            role=current_role,
                            signature_line_text=s,
                        )
                    )
                current_name = s
                current_role = ""
                continue

            m = party_name_pattern.match(s)
            if m and m.group(1):
                current_name = m.group(1).strip()

        if current_name:
            blocks.append(
                SignatureBlock(
                    party_name=current_name,
                    role=current_role,
                    signature_line_text="",
                )
            )

        return blocks

    # ------------------------------------------------------------------
    # Governing law hint
    # ------------------------------------------------------------------

    def _extract_governing_law_hint(self, text: str) -> str:
        for pattern in _GOV_LAW_PATTERNS:
            m = pattern.search(text)
            if m:
                return m.group(1).strip().rstrip(".,;")
        return ""

    # ------------------------------------------------------------------
    # Section index
    # ------------------------------------------------------------------

    def _build_section_index(self, structure: DocumentStructure) -> None:
        """Populate structure._section_index for O(1) look-ups."""
        index: dict[str, Section] = {}
        for sec in structure.iter_all_sections():
            index[sec.number] = sec
            # Also index stripped variants
            index[sec.number.lstrip("0")] = sec
        structure._section_index = index
