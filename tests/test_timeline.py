"""ObligationTimeline: deadline resolution and iCalendar export."""

from __future__ import annotations

from datetime import date

import pytest

from contractex.analysis import ObligationTimeline


def resolve(deadline: str, effective: str = "2025-01-01") -> date | None:
    timeline = ObligationTimeline(
        [{"obligor": "A", "action": "act", "deadline": deadline}], effective
    )
    (entry,) = timeline._entries
    return entry.resolved_date


class TestResolution:
    @pytest.mark.parametrize(
        ("deadline", "expected"),
        [
            ("2024-06-30", date(2024, 6, 30)),
            ("no later than June 30, 2024", date(2024, 6, 30)),
            ("within 30 days", date(2025, 1, 31)),
            ("60 days after the Effective Date", date(2025, 3, 2)),
            ("within thirty (30) days of the Effective Date", date(2025, 1, 31)),
            ("30 calendar days from the date of this Agreement", date(2025, 1, 31)),
            ("2 weeks", date(2025, 1, 15)),
            ("3 months", date(2025, 4, 1)),
            ("2 years", date(2027, 1, 1)),
            ("upon termination", None),
            ("", None),
        ],
    )
    def test_supported_forms(self, deadline, expected):
        assert resolve(deadline) == expected

    @pytest.mark.parametrize(
        ("effective", "deadline", "expected"),
        [
            ("2025-01-31", "within 1 month", date(2025, 2, 28)),
            ("2025-01-30", "1 month", date(2025, 2, 28)),
            ("2024-01-31", "1 month", date(2024, 2, 29)),
            ("2024-02-29", "1 year", date(2025, 2, 28)),
            ("2025-03-31", "1 month", date(2025, 4, 30)),
            ("2025-11-30", "3 months", date(2026, 2, 28)),
        ],
    )
    def test_month_arithmetic_clamps_to_the_month_end(self, effective, deadline, expected):
        assert resolve(deadline, effective) == expected

    @pytest.mark.parametrize(
        "deadline",
        [
            "within 30 days after termination",
            "30 days of receipt of the invoice",
            "ninety (90) days following expiry of the Term",
            "6 months before the renewal date",
            "10 days prior to the audit",
        ],
    )
    def test_deadline_relative_to_another_event_is_unresolved(self, deadline):
        assert resolve(deadline) is None

    @pytest.mark.parametrize(
        "deadline",
        ["10 business days", "within five (5) Business Days", "3 working days"],
    )
    def test_business_days_are_unresolved(self, deadline):
        assert resolve(deadline) is None


class TestEntries:
    def test_none_values_become_empty_strings(self):
        timeline = ObligationTimeline(
            [{"obligor": None, "action": "pay", "deadline": None, "condition": None}],
            date(2025, 1, 1),
        )
        (entry,) = timeline.unresolved()
        assert (entry.obligor, entry.deadline_text, entry.condition) == ("", "", "")

    def test_objects_and_dicts(self):
        class Ob:
            obligor = "B"
            action = "deliver"
            deadline = "2025-02-01"
            source_section = "4"
            condition = None

        (entry,) = ObligationTimeline([Ob()], "2025-01-01").all_resolved()
        assert (entry.obligor, entry.source_section, entry.condition) == ("B", "4", "")

    def test_upcoming_window(self):
        timeline = ObligationTimeline(
            [{"deadline": "2025-01-10"}, {"deadline": "2025-03-01"}, {"deadline": "on demand"}],
            "2025-01-01",
        )
        upcoming = timeline.upcoming(days=30, reference=date(2025, 1, 1))
        assert [e.resolved_date for e in upcoming] == [date(2025, 1, 10)]


class TestICal:
    def test_one_event_per_resolved_obligation(self):
        ics = ObligationTimeline(
            [
                {"obligor": "A", "action": "pay", "deadline": "2025-03-01", "source_section": "2"},
                {"obligor": "A", "action": "wait", "deadline": "upon termination"},
            ],
            "2025-01-01",
        ).to_ical()
        assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR")
        assert ics.count("BEGIN:VEVENT") == 1
        assert "DTSTART;VALUE=DATE:20250301" in ics
        assert "SUMMARY:A: pay" in ics
        assert "DESCRIPTION:Section: 2\\nDeadline: 2025-03-01\\n" in ics

    def test_text_is_escaped(self):
        ics = ObligationTimeline(
            [
                {
                    "obligor": "Acme, Inc.",
                    "action": "x\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nSUMMARY:injected",
                    "deadline": "2025-03-01; or earlier",
                    "condition": "a\\b\nc",
                }
            ],
            "2025-01-01",
        ).to_ical(calendar_name="Deadlines; Q1")
        lines = ics.split("\r\n")
        assert lines.count("BEGIN:VEVENT") == lines.count("END:VEVENT") == 1
        assert not any(line.startswith("SUMMARY:injected") for line in lines)
        assert "X-WR-CALNAME:Deadlines\\; Q1" in lines
        (summary,) = [line for line in lines if line.startswith("SUMMARY:")]
        assert summary.startswith("SUMMARY:Acme\\, Inc.: x\\nEND:VEVENT\\nBEGIN:VEVENT")
        (description,) = [line for line in lines if line.startswith("DESCRIPTION:")]
        assert "Deadline: 2025-03-01\\; or earlier\\n" in description
        assert "Condition: a\\\\b\\nc\\n" in description
