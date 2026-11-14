"""contractex.structure: deterministic section, reference and defined-term parsing."""

from __future__ import annotations

import pytest

from contractex.structure import parse_structure

NUMBERED = (
    "1. Definitions\n"
    "In this Agreement the following terms apply.\n"
    "\n"
    "2. Term\n"
    "This Agreement lasts two years.\n"
    "It may be renewed.\n"
)


class TestSections:
    def test_empty_and_headingless_text(self):
        assert parse_structure("").sections == []
        assert [w.code for w in parse_structure("hello").warnings] == ["NO_SECTIONS_FOUND"]

    def test_numbers_titles_and_bodies(self):
        sections = list(parse_structure(NUMBERED).iter_all_sections())
        assert [(s.number, s.title) for s in sections] == [("1", "Definitions"), ("2", "Term")]
        assert sections[1].text == "This Agreement lasts two years.\nIt may be renewed."

    @pytest.mark.parametrize("text", [NUMBERED, NUMBERED.replace("\n", "\r\n")])
    def test_offsets_cover_the_heading_and_its_body(self, text):
        for s in parse_structure(text).iter_all_sections():
            source = text[s.start_char : s.end_char]
            assert source.startswith(f"{s.number}. {s.title}")
            assert source.endswith(s.text)
        first, second = parse_structure(text).iter_all_sections()
        assert first.end_char <= second.start_char

    def test_subsections_nest(self):
        structure = parse_structure(
            "4. Fees\nIntro.\n4.1 Invoices\nMonthly.\n4.2 Tax\nExclusive.\n"
        )
        (fees,) = structure.sections
        assert [c.number for c in fees.children] == ["4.1", "4.2"]
        assert structure.get_section("4.2").parent_number == "4"


class TestCrossReferences:
    def test_article_and_section_headings_resolve(self):
        text = (
            "Article I Definitions\nTerms are defined here.\n"
            "Article II Payment\nFees are due as set out in Article I and Section 3.\n"
            "Section 3 Term\nSee Article II and Article IX.\n"
        )
        structure = parse_structure(text)
        assert [(r.raw_text, r.resolved) for r in structure.cross_references] == [
            ("Article I", True),
            ("Section 3", True),
            ("Article II", True),
            ("Article IX", False),
        ]
        assert structure.resolve_ref("Article I").title == "Definitions"
        assert structure.resolve_ref("Section 3").title == "Term"
        assert structure.resolve_ref("Article IX") is None

    def test_numeric_headings_resolve(self):
        structure = parse_structure(
            "1. A\nSee Section 2, clause 2 and § 3.\n2. B\nSee Section 2.\n"
        )
        assert [(r.raw_text, r.resolved) for r in structure.cross_references] == [
            ("Section 2", True),
            ("clause 2", True),
            ("§ 3", False),
        ]

    def test_ordinary_words_are_not_references(self):
        text = (
            "1. General\nThis clause violates nothing. The exhibition is open. "
            "This Article is binding. A paragraph victory. Section vii applies.\n"
        )
        assert parse_structure(text).cross_references == []

    def test_lettered_exhibits_and_schedules(self):
        text = (
            "1. Services\nThe Services are described in Exhibit A and priced in Schedule B. "
            "Exhibit C is reserved. An exhibit Attached hereto.\n"
            "Exhibit A Services\nHosting.\n"
            "SCHEDULE B\nFees.\n"
        )
        refs = {r.raw_text: r.resolved for r in parse_structure(text).cross_references}
        assert refs == {"Exhibit A": True, "Schedule B": True, "Exhibit C": False}


class TestSchedules:
    def test_each_schedule_has_its_own_body(self):
        text = (
            "1. Main\nBody.\n"
            "Schedule A Fees\nfee text\n"
            "Schedule B Services\nservice text\nmore services\n"
            "Schedule C Data\ndata text\n"
        )
        schedules = parse_structure(text).schedules
        assert [(s.label, s.title, s.text) for s in schedules] == [
            ("Schedule A", "Fees", "fee text"),
            ("Schedule B", "Services", "service text\nmore services"),
            ("Schedule C", "Data", "data text"),
        ]


class TestGoverningLawHint:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("This Agreement is governed by the laws of the State of Delaware.", "Delaware"),
            (
                "governed by the laws of the State of New York without regard to its "
                "conflict of laws principles.",
                "New York",
            ),
            (
                "governed by the laws of England and Wales and the parties submit to the "
                "courts of London.",
                "England and Wales",
            ),
            (
                "in accordance with applicable laws of general application. This Agreement "
                "is governed by the laws of Delaware.",
                "Delaware",
            ),
            ("GOVERNED BY THE LAWS OF THE STATE OF NEW YORK.", "NEW YORK"),
            ("construed under the laws of the Commonwealth of Massachusetts;", "Massachusetts"),
            ("governed by the laws of the United States of America.", "United States of America"),
            ("This Agreement shall be governed by New York law.", "New York"),
            ("Each party is governed by the terms of this Agreement.", ""),
            ("Delaware law governs this Agreement.", ""),
            ("No law is mentioned.", ""),
        ],
    )
    def test_hint_is_the_jurisdiction_only(self, text, expected):
        assert parse_structure(text).governing_law_hint == expected


class TestDefinedTerms:
    def test_straight_and_curly_quotes(self):
        text = (
            "1. Definitions\n"
            "“Confidential Information” means any non-public information disclosed.\n"
            '"Purpose" means evaluating a possible transaction.\n'
            'Acme Corporation (the “Company”) and Beta LLC ("Beta") agree.\n'
            "2. Use\n"
            'The “Purpose” limits use of "Confidential Information".\n'
        )
        terms = parse_structure(text).defined_terms
        assert sorted(terms) == ["Beta", "Company", "Confidential Information", "Purpose"]
        assert terms["Confidential Information"].definition_text.startswith("any non-public")
        assert terms["Confidential Information"].definition_section == "1"
        assert terms["Purpose"].usages == ["2"]
        assert terms["Confidential Information"].usages == ["2"]


def test_recitals():
    structure = parse_structure("WHEREAS, the parties wish to cooperate;\n1. Term\nOne year.\n")
    assert structure.recitals == ["the parties wish to cooperate;"]
