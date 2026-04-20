"""
Obligation timeline with iCal export — Layer 3.

ObligationTimeline takes a list of obligations (from extraction) and an
effective date, resolves relative deadlines to absolute dates, and can
export to .ics (iCalendar) format for calendar integration.

Usage::

    from contractex.analysis import ObligationTimeline

    timeline = ObligationTimeline(
        obligations=result.obligations,
        effective_date="2024-01-01"
    )

    upcoming = timeline.upcoming(days=30)
    ics_text = timeline.to_ical()

    with open("contract_deadlines.ics", "w") as f:
        f.write(ics_text)
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Date parsing helpers
# ---------------------------------------------------------------------------

_RELATIVE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(\d+)\s+day", re.IGNORECASE), "days"),
    (re.compile(r"(\d+)\s+(?:business\s+)?day", re.IGNORECASE), "days"),
    (re.compile(r"(\d+)\s+(?:calendar\s+)?day", re.IGNORECASE), "days"),
    (re.compile(r"(\d+)\s+(?:week|wk)", re.IGNORECASE), "weeks"),
    (re.compile(r"(\d+)\s+month", re.IGNORECASE), "months"),
    (re.compile(r"(\d+)\s+year", re.IGNORECASE), "years"),
    (re.compile(r"thirty\s*\(30\)\s*day", re.IGNORECASE), "days:30"),
    (re.compile(r"sixty\s*\(60\)\s*day", re.IGNORECASE), "days:60"),
    (re.compile(r"ninety\s*\(90\)\s*day", re.IGNORECASE), "days:90"),
]

_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_US_DATE = re.compile(r"(\w+)\s+(\d{1,2}),?\s+(\d{4})")

_MONTH_MAP = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def _add_months(d: date, months: int) -> date:
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    day = min(d.day, [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return date(year, month, day)


def _parse_deadline(deadline_text: str, effective_date: date) -> date | None:
    """
    Convert a deadline string from extraction output to an absolute date.

    Handles:
      - ISO dates: "2024-06-30"
      - US dates: "June 30, 2024"
      - Relative: "within 30 days", "60 days after the Effective Date"
      - "upon termination", "on demand" → None (no absolute date)
    """
    if not deadline_text or not deadline_text.strip():
        return None

    # Absolute ISO date
    m = _ISO_DATE.search(deadline_text)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    # Absolute US-style date
    m2 = _US_DATE.search(deadline_text)
    if m2:
        month_str = m2.group(1).lower()
        if month_str in _MONTH_MAP:
            try:
                return date(int(m2.group(3)), _MONTH_MAP[month_str], int(m2.group(2)))
            except ValueError:
                pass

    # Relative deadlines from effective date
    for pattern, unit in _RELATIVE_PATTERNS:
        m3 = pattern.search(deadline_text)
        if m3:
            if ":" in unit:
                actual_unit, val = unit.split(":")
                n = int(val)
            else:
                actual_unit = unit
                n = int(m3.group(1))

            if actual_unit == "days":
                return effective_date + timedelta(days=n)
            elif actual_unit == "weeks":
                return effective_date + timedelta(weeks=n)
            elif actual_unit == "months":
                return _add_months(effective_date, n)
            elif actual_unit == "years":
                return _add_months(effective_date, n * 12)

    return None


# ---------------------------------------------------------------------------
# Obligation entry
# ---------------------------------------------------------------------------


@dataclass
class ObligationEntry:
    """An obligation with a resolved absolute deadline."""

    obligor: str
    action: str
    deadline_text: str  # original text from extraction
    source_section: str
    resolved_date: date | None  # None = could not resolve to absolute date
    condition: str = ""


# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------


class ObligationTimeline:
    """
    Resolve and manage obligation deadlines from contract extraction output.

    Args:
        obligations: List of obligation objects (from extraction result).
                     Accepts objects with .obligor, .action, .deadline,
                     .source_section attributes, or dicts with the same keys.
        effective_date: The contract effective date as "YYYY-MM-DD" or a date object.
    """

    def __init__(
        self,
        obligations: list,
        effective_date: str | date,
    ) -> None:
        if isinstance(effective_date, str):
            self._effective = date.fromisoformat(effective_date)
        else:
            self._effective = effective_date

        self._entries = self._build_entries(obligations)

    def _build_entries(self, obligations: list) -> list[ObligationEntry]:
        entries: list[ObligationEntry] = []
        for ob in obligations:
            obligor = self._attr(ob, "obligor", "")
            action = self._attr(ob, "action", "")
            deadline_text = self._attr(ob, "deadline", "")
            source_section = self._attr(ob, "source_section", "")
            condition = self._attr(ob, "condition", "")

            resolved = _parse_deadline(deadline_text, self._effective)
            entries.append(
                ObligationEntry(
                    obligor=obligor,
                    action=action,
                    deadline_text=deadline_text,
                    source_section=source_section,
                    resolved_date=resolved,
                    condition=condition,
                )
            )
        return entries

    @staticmethod
    def _attr(obj: object, name: str, default: str) -> str:
        if hasattr(obj, name):
            val = getattr(obj, name)
            return str(val) if val is not None else default
        if isinstance(obj, dict):
            return str(obj.get(name, default))
        return default

    # ------------------------------------------------------------------
    # Query methods
    # ------------------------------------------------------------------

    def upcoming(self, days: int = 30, reference: date | None = None) -> list[ObligationEntry]:
        """
        Return obligations due within the next *days* calendar days.

        Args:
            days: Look-ahead window in calendar days.
            reference: Reference date (default: today).

        Returns:
            List of ObligationEntry sorted by resolved_date ascending.
        """
        ref = reference or date.today()
        cutoff = ref + timedelta(days=days)
        results = [
            e
            for e in self._entries
            if e.resolved_date is not None and ref <= e.resolved_date <= cutoff
        ]
        return sorted(results, key=lambda e: e.resolved_date or date.min)

    def all_resolved(self) -> list[ObligationEntry]:
        """All entries with successfully resolved absolute dates, sorted by date."""
        results = [e for e in self._entries if e.resolved_date is not None]
        return sorted(results, key=lambda e: e.resolved_date or date.min)

    def unresolved(self) -> list[ObligationEntry]:
        """Entries where deadline could not be resolved to an absolute date."""
        return [e for e in self._entries if e.resolved_date is None]

    # ------------------------------------------------------------------
    # iCalendar export
    # ------------------------------------------------------------------

    def to_ical(self, calendar_name: str = "Contract Obligations") -> str:
        """
        Export resolved obligations as an iCalendar (.ics) string.

        Returns:
            A standards-compliant iCalendar string suitable for import
            into any calendar application (Google Calendar, Outlook, etc.).
        """
        lines: list[str] = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//ContractEx//ContractEx 1.0//EN",
            f"X-WR-CALNAME:{calendar_name}",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]

        now_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

        for entry in self.all_resolved():
            assert entry.resolved_date is not None
            date_str = entry.resolved_date.strftime("%Y%m%d")
            uid = str(uuid.uuid4())
            summary = f"{entry.obligor}: {entry.action[:60]}"
            description = (
                f"Section: {entry.source_section}\\n" f"Deadline: {entry.deadline_text}\\n"
            )
            if entry.condition:
                description += f"Condition: {entry.condition}\\n"

            lines.extend(
                [
                    "BEGIN:VEVENT",
                    f"UID:{uid}",
                    f"DTSTAMP:{now_str}",
                    f"DTSTART;VALUE=DATE:{date_str}",
                    f"DTEND;VALUE=DATE:{date_str}",
                    f"SUMMARY:{summary}",
                    f"DESCRIPTION:{description}",
                    "END:VEVENT",
                ]
            )

        lines.append("END:VCALENDAR")
        return "\r\n".join(lines)
