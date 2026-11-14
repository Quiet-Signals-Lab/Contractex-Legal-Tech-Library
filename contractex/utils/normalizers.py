"""Normalization utilities for dates, currencies, and entities."""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

_MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
_MONTH = (
    r"(?P<mon>jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
)
_ORDINAL = r"(?:st|nd|rd|th)?"


class DateNormalizer:
    """Normalize various date formats to standard format."""

    # Common date patterns
    PATTERNS = [
        # YYYY-MM-DD
        re.compile(r"(?<!\d)(?P<y>\d{4})-(?P<m>\d{1,2})-(?P<d>\d{1,2})(?!\d)"),
        # MM/DD/YYYY or DD/MM/YYYY, also with - or .
        re.compile(
            r"(?<!\d)(?P<a>\d{1,2})(?P<sep>[/.-])(?P<b>\d{1,2})(?P=sep)(?P<y>\d{4}|\d{2})(?!\d)"
        ),
        # Month DD, YYYY
        re.compile(rf"\b{_MONTH}\s+(?P<d>\d{{1,2}}){_ORDINAL},?\s+(?P<y>\d{{4}})\b", re.I),
        # DD Month YYYY, "1st day of Month, YYYY"
        re.compile(
            rf"(?<!\d)(?P<d>\d{{1,2}}){_ORDINAL}(?:\s+day)?(?:\s+of)?\s+{_MONTH},?\s+(?P<y>\d{{4}})\b",
            re.I,
        ),
    ]

    @staticmethod
    def normalize(date_string: str) -> date | None:
        """
        Normalize a date string to a date object.

        The first date in the string is used.  An all-numeric date where
        either part could be the month (``05/03/2024``) and a two-digit year
        give None: a wrong date is worse than none.

        Args:
            date_string: String representation of a date

        Returns:
            date object or None if parsing fails
        """
        if not date_string:
            return None

        matches = [m for p in DateNormalizer.PATTERNS if (m := p.search(date_string))]
        if not matches:
            return None
        g = min(matches, key=lambda m: m.start()).groupdict()

        if len(g["y"]) != 4:
            return None
        if "a" in g:
            a, b = int(g["a"]), int(g["b"])
            if g["sep"] == "." or a > 12 >= b:  # dotted dates are day first
                day, month = a, b
            elif b > 12 >= a or a == b:
                month, day = a, b
            else:
                return None
        else:
            day = int(g["d"])
            month = int(g["m"]) if "m" in g else _MONTHS.index(g["mon"][:3].lower()) + 1

        try:
            return date(int(g["y"]), month, day)
        except ValueError:
            return None


class CurrencyNormalizer:
    """Normalize currency amounts and codes."""

    # A number with an optional sign, currency symbol or ISO code, and magnitude word
    _AMOUNT = re.compile(
        r"(?<![\w.,'])(?P<neg1>[-−])?"
        r"(?P<sym>[A-Z]{0,3}[$€£¥₹]\s*|[A-Z]{3}\s+)?(?P<neg2>[-−])?"
        r"(?P<num>\d[\d.,']*\d|\d|\.\d+)(?!\w)"
        r"(?:\s*(?P<mag>(?i:thousand|million|billion|trillion))\b)?"
        r"(?:\s*(?P<code>[A-Z]{3})\b)?"
    )
    _MAGNITUDE = {"thousand": 10**3, "million": 10**6, "billion": 10**9, "trillion": 10**12}
    # 1,234.56 and 1.234,56; a leading 0 is never a thousands group
    _US_NUMBER = re.compile(r"(?:[1-9]\d{0,2}(?:,\d{3})+|\d*)(?:\.\d+)?")
    _EU_NUMBER = re.compile(r"(?:[1-9]\d{0,2}(?:\.\d{3})+|\d+),\d{1,2}|[1-9]\d{0,2}(?:\.\d{3}){2,}")

    @staticmethod
    def extract_amount(text: str) -> Decimal | None:
        """
        Extract numeric amount from text.

        When the text holds several numbers, the one written with a currency
        symbol or code is the amount.  Returns None when that is not exactly
        one number, or its format is ambiguous.

        Args:
            text: Text containing amount

        Returns:
            Decimal amount or None
        """
        matches = list(CurrencyNormalizer._AMOUNT.finditer(text))
        if len(matches) > 1:
            matches = [m for m in matches if m["sym"] or m["code"]]
        if len(matches) != 1:
            return None
        m = matches[0]

        number = m["num"].replace("'", "")
        if CurrencyNormalizer._US_NUMBER.fullmatch(number):
            amount = Decimal(number.replace(",", ""))
        elif CurrencyNormalizer._EU_NUMBER.fullmatch(number):
            amount = Decimal(number.replace(".", "").replace(",", "."))
        else:
            return None

        if m["mag"]:
            amount *= CurrencyNormalizer._MAGNITUDE[m["mag"].lower()]
        return -amount if m["neg1"] or m["neg2"] else amount


class EntityNormalizer:
    """Normalize entity names (companies, people, etc.)."""

    @staticmethod
    def normalize_company_name(name: str) -> str:
        """
        Collapse runs of whitespace in a company name.

        Args:
            name: Company name to normalize

        Returns:
            Normalized company name
        """
        if not name:
            return ""

        return " ".join(name.split())
