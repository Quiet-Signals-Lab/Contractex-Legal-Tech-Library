"""
ClauseAwareChunker boundary handling.

Invariants every chunk must satisfy, because provenance (SourceSpan offsets)
and the "a clause is never split across chunks" claim depend on them:

* each chunk is an exact substring of the source text;
* no chunk exceeds ``max_chunk_size`` (tokens, estimated as chars // 4);
* with ``overlap=0`` no content is lost or duplicated;
* a chunk never starts or ends in the middle of a word;
* a section heading stays in the same chunk as the start of its body.

"""

from __future__ import annotations

import pytest

from contractex.chunking import ClauseAwareChunker


def words(prefix: str, n: int) -> str:
    """n distinct words, so every chunk's position in the source is unambiguous."""
    return " ".join(f"{prefix}{i}" for i in range(n)) + "."


def section(num: int, title: str, body_words: int) -> str:
    return f"{num}. {title}.\n{words(title.lower(), body_words)}\n"


CONTRACT = "".join(
    [
        "MASTER SERVICES AGREEMENT\n\n",
        section(1, "Definitions", 60),
        section(2, "Term", 60),
        section(3, "Payment", 60),
        section(4, "Termination", 60),
    ]
)


# Short sections, so several are packed into one chunk
SHORT_SECTIONS = "".join(section(i, f"Clause{i}", 10) for i in range(1, 13))


def squash(s: str) -> str:
    return "".join(s.split())


# ---------------------------------------------------------------------------
# Boundaries
# ---------------------------------------------------------------------------


class TestBoundaries:
    def test_empty_text(self):
        assert ClauseAwareChunker().chunk("") == []

    def test_small_document_is_one_chunk(self):
        text = "1. Term.\nThis Agreement lasts one year.\n2. Law.\nDelaware law applies."
        assert ClauseAwareChunker(max_chunk_size=1000).chunk(text) == [text]

    def test_splits_at_numbered_headings(self):
        chunks = ClauseAwareChunker(max_chunk_size=150, overlap=0).chunk(CONTRACT)
        heads = [c.split("\n", 1)[0] for c in chunks]
        assert "2. Term." in heads and "3. Payment." in heads and "4. Termination." in heads

    @pytest.mark.parametrize(
        "heading",
        ["Article 2 Term", "ARTICLE 2 TERM", "Section 2 Term", "(b) Term", "(2) Term", "2.1 Term"],
    )
    def test_recognised_heading_styles(self, heading):
        text = f"Preamble {words('p', 40)}\n{heading}\n{words('t', 40)}"
        chunks = ClauseAwareChunker(max_chunk_size=60, overlap=0).chunk(text)
        assert any(c.startswith(heading) for c in chunks)

    def test_paragraph_fallback_without_headings(self):
        text = f"{words('a', 60)}\n\n{words('b', 60)}\n\n{words('c', 60)}"
        chunks = ClauseAwareChunker(max_chunk_size=80, overlap=0).chunk(text)
        assert len(chunks) == 3
        assert [c.split()[0] for c in chunks] == ["a0", "b0", "c0"]

    @pytest.mark.parametrize("text", [CONTRACT, SHORT_SECTIONS])
    def test_no_content_lost_or_duplicated_without_overlap(self, text):
        chunks = ClauseAwareChunker(max_chunk_size=100, overlap=0).chunk(text)
        assert squash("".join(chunks)) == squash(text)

    def test_leading_whitespace_before_heading_is_allowed(self):
        text = f"Intro {words('i', 40)}\n   2. Term.\n{words('t', 40)}"
        chunks = ClauseAwareChunker(max_chunk_size=60, overlap=0).chunk(text)
        assert any(c.startswith("2. Term.") for c in chunks)


# ---------------------------------------------------------------------------
# Invariants
# ---------------------------------------------------------------------------


class TestInvariants:
    @pytest.mark.parametrize("overlap", [0, 20])
    def test_every_chunk_is_a_substring_of_the_source(self, overlap):
        chunks = ClauseAwareChunker(max_chunk_size=100, overlap=overlap).chunk(SHORT_SECTIONS)
        assert len(chunks) > 1
        for c in chunks:
            assert c in SHORT_SECTIONS

    def test_no_chunk_exceeds_max_chunk_size(self):
        text = "1. Term.\n" + " ".join(f"w{i}" for i in range(2000)) + "\n2. Law.\nDelaware."
        chunker = ClauseAwareChunker(max_chunk_size=100, overlap=0)
        assert all(chunker.count_tokens(c) <= 100 for c in chunker.chunk(text))

    def test_overlap_starts_on_a_word_boundary(self):
        chunks = ClauseAwareChunker(max_chunk_size=150, overlap=15).chunk(CONTRACT)
        for c in chunks[1:]:
            i = CONTRACT.find(c)
            assert i == 0 or CONTRACT[i - 1].isspace(), c[:30]

    def test_heading_stays_with_body_in_oversized_section(self):
        text = "1. Term.\n" + " ".join(f"w{i}" for i in range(400)) + "\n2. Law.\nDelaware."
        chunks = ClauseAwareChunker(max_chunk_size=100, overlap=0).chunk(text)
        first = next(c for c in chunks if "1. Term." in c)
        assert "w0" in first


class TestHeadingPatterns:
    @pytest.mark.parametrize(
        "line",
        [
            "1. Definitions",
            "10. Payment",
            "2.1 Term",
            "2.1. Term",
            '1.1 "Affiliate" means',
            "1.1 \u201cAffiliate\u201d means",
            "   3. Indented heading",
            "Article 4",
            "SECTION 5 Notices",
            "(a) the Supplier",
            "(B) the Customer",
            "(12) notices",
            "EARLY TERMINATION",
        ],
    )
    def test_heading(self, line):
        assert ClauseAwareChunker().section_regex.match(line)

    @pytest.mark.parametrize(
        "line",
        [
            "10. million units ship first.",
            "2024. was a good year",
            "Early termination fees apply.",
            "The fee is $10.",
            "Articles of association",
        ],
    )
    def test_not_heading(self, line):
        assert not ClauseAwareChunker().section_regex.match(line)

    def test_wrapped_number_does_not_start_a_chunk(self):
        text = f"1. Payment.\nThe fee is $10.\n10. million units ship first. {words('x', 30)}"
        chunks = ClauseAwareChunker(max_chunk_size=30, overlap=0).chunk(text)
        assert not any(c.startswith("10. million") for c in chunks)


class TestInvariantsFuzz:
    """Seeded random documents: the invariants hold for every size and overlap."""

    @staticmethod
    def document(rng) -> str:
        parts = []
        for i in range(rng.randint(1, 25)):
            if rng.random() < 0.7:
                parts.append(rng.choice([f"{i + 1}. Heading {i}", f"({chr(97 + i % 26)}) sub", ""]))
            sentences = [
                " ".join(f"t{rng.randint(0, 999)}" for _ in range(rng.randint(1, 60))) + "."
                for _ in range(rng.randint(1, 8))
            ]
            parts.append(" ".join(sentences))
        sep = rng.choice(["\n", "\n\n", "\n  \n"])
        return sep.join(parts)

    @pytest.mark.parametrize("seed", range(40))
    def test_invariants(self, seed):
        import random

        rng = random.Random(seed)
        text = self.document(rng)
        max_size = rng.choice([8, 20, 50, 200])
        overlap = rng.choice([0, 0, 5, 30])
        chunker = ClauseAwareChunker(
            max_chunk_size=max_size, overlap=overlap, preserve_sentences=rng.random() < 0.8
        )
        chunks = chunker.chunk(text)
        for c in chunks:
            assert c and c in text
            assert chunker.count_tokens(c) <= max_size
            i = text.find(c)
            assert i == 0 or text[i - 1].isspace() or not text[i - 1].isalnum()
        if overlap == 0:
            assert squash("".join(chunks)) == squash(text)
