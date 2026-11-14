"""Date and amount normalisers: a wrong value is worse than ``None``."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from contractex.utils.normalizers import CurrencyNormalizer, DateNormalizer


class TestDateNormalizer:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("2024-01-15", date(2024, 1, 15)),
            ("January 1, 2024", date(2024, 1, 1)),
            ("January 1 2024", date(2024, 1, 1)),
            ("effective as of March 15, 2024", date(2024, 3, 15)),
            ("March 15th, 2024", date(2024, 3, 15)),
            ("Mar 15, 2024", date(2024, 3, 15)),
            ("Sept. 3, 2024", date(2024, 9, 3)),
            ("15 March 2024", date(2024, 3, 15)),
            ("the 1st day of January, 2024", date(2024, 1, 1)),
            # One part above 12 says which is the day
            ("01/31/2024", date(2024, 1, 31)),
            ("31/01/2024", date(2024, 1, 31)),
            ("15-03-2024", date(2024, 3, 15)),
            ("05/05/2024", date(2024, 5, 5)),
            # Dotted dates are day first
            ("05.03.2024", date(2024, 3, 5)),
        ],
    )
    def test_parses(self, text, expected):
        assert DateNormalizer.normalize(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "net 30",
            "upon delivery",
            "05/03/2024",  # 5 March or 3 May
            "05-03-2024",
            "3/15/24",  # which century
            "February 30, 2024",
            "13/13/2024",
        ],
    )
    def test_returns_none_rather_than_guess(self, text):
        assert DateNormalizer.normalize(text) is None

    def test_first_date_in_the_string_wins(self):
        assert DateNormalizer.normalize("1 January 2024 (amended 3/15/2025)") == date(2024, 1, 1)
        assert DateNormalizer.normalize("12/31/2024 and 2023-01-01") == date(2024, 12, 31)

    def test_ambiguous_first_date_is_not_replaced_by_a_later_one(self):
        assert DateNormalizer.normalize("3/4/2025 (signed 1 January 2024)") is None


class TestExtractAmount:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("50000.00", "50000.00"),
            ("$1,234.56", "1234.56"),
            ("1,000,000", "1000000"),
            ("€1.234,56", "1234.56"),
            ("1.234.567,00 EUR", "1234567.00"),
            ("5,00", "5.00"),
            ("CHF 1'000.50", "1000.50"),
            ("$.50", "0.50"),
            ("-$500", "-500"),
            ("$1.5 million", "1500000"),
            ("USD 2 billion", "2000000000"),
            # The number next to the currency is the amount
            ("Section 5: $10,000", "10000"),
            ("USD 50,000 per year for 3 years", "50000"),
            # Contracts restate amounts in brackets; that is not a negative
            ("One Thousand Dollars ($1,000)", "1000"),
        ],
    )
    def test_parses(self, text, expected):
        assert CurrencyNormalizer.extract_amount(text) == Decimal(expected)

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "variable",
            "fifty thousand",
            "30 days: 5000",  # two numbers, neither marked as money
            "$10,000 - $20,000",
            "1 000 000",
            "10k",
            "USD 2M",
            "1,23456",
        ],
    )
    def test_returns_none_rather_than_guess(self, text):
        assert CurrencyNormalizer.extract_amount(text) is None
