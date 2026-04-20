"""Normalization utilities for dates, currencies, and entities."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal


class DateNormalizer:
    """Normalize various date formats to standard format."""

    # Common date patterns
    PATTERNS = [
        (r"(\d{1,2})/(\d{1,2})/(\d{4})", "%m/%d/%Y"),  # MM/DD/YYYY
        (r"(\d{4})-(\d{2})-(\d{2})", "%Y-%m-%d"),  # YYYY-MM-DD
        (r"(\d{1,2})-(\d{1,2})-(\d{4})", "%m-%d-%Y"),  # MM-DD-YYYY
        (r"(\w+)\s+(\d{1,2}),?\s+(\d{4})", "%B %d %Y"),  # Month DD, YYYY
    ]

    @staticmethod
    def normalize(date_string: str) -> date | None:
        """
        Normalize a date string to a date object.

        Args:
            date_string: String representation of a date

        Returns:
            date object or None if parsing fails
        """
        if not date_string:
            return None

        date_string = date_string.strip()

        # Try each pattern
        for pattern, format_string in DateNormalizer.PATTERNS:
            try:
                match = re.search(pattern, date_string)
                if match:
                    return datetime.strptime(match.group(0), format_string).date()
            except (ValueError, AttributeError):
                continue

        return None


class CurrencyNormalizer:
    """Normalize currency amounts and codes."""

    # Currency symbols to codes
    SYMBOL_TO_CODE = {
        "$": "USD",
        "€": "EUR",
        "£": "GBP",
        "¥": "JPY",
        "₹": "INR",
        "C$": "CAD",
        "A$": "AUD",
    }

    @staticmethod
    def extract_amount(text: str) -> Decimal | None:
        """
        Extract numeric amount from text.

        Args:
            text: Text containing amount

        Returns:
            Decimal amount or None
        """
        # Remove currency symbols and commas
        cleaned = re.sub(r"[$€£¥₹,]", "", text)

        # Find number
        match = re.search(r"[\d,]+\.?\d*", cleaned)
        if match:
            try:
                return Decimal(match.group(0).replace(",", ""))
            except Exception:
                return None

        return None

    @staticmethod
    def extract_currency(text: str) -> str:
        """
        Extract currency code from text.

        Args:
            text: Text containing currency

        Returns:
            ISO 4217 currency code or "USD" as default
        """
        # Check for ISO codes (3 uppercase letters)
        iso_match = re.search(r"\b([A-Z]{3})\b", text)
        if iso_match:
            return iso_match.group(1)

        # Check for currency symbols
        for symbol, code in CurrencyNormalizer.SYMBOL_TO_CODE.items():
            if symbol in text:
                return code

        # Default to USD
        return "USD"

    @staticmethod
    def format_amount(amount: Decimal | float | int, currency: str = "USD") -> str:
        """
        Format amount with currency.

        Args:
            amount: Numeric amount
            currency: Currency code

        Returns:
            Formatted string
        """
        if isinstance(amount, (int, float)):
            amount = Decimal(str(amount))

        # Format with commas
        formatted = f"{amount:,.2f}"

        return f"{currency} {formatted}"


class EntityNormalizer:
    """Normalize entity names (companies, people, etc.)."""

    # Common legal entity suffixes
    LEGAL_SUFFIXES = [
        "Inc.",
        "Inc",
        "LLC",
        "L.L.C.",
        "Corp.",
        "Corporation",
        "Ltd.",
        "Limited",
        "LLP",
        "L.L.P.",
        "LP",
        "L.P.",
        "Co.",
        "Company",
        "GmbH",
        "AG",
        "SA",
        "PLC",
    ]

    @staticmethod
    def normalize_company_name(name: str) -> str:
        """
        Normalize company name to consistent format.

        Args:
            name: Company name to normalize

        Returns:
            Normalized company name
        """
        if not name:
            return ""

        # Remove extra whitespace
        normalized = " ".join(name.split())

        # Standardize legal suffixes (add period if missing)
        for suffix in EntityNormalizer.LEGAL_SUFFIXES:
            # Look for suffix without period
            no_period = suffix.replace(".", "")
            if normalized.endswith(f" {no_period}") and "." not in suffix:
                normalized = normalized[: -len(no_period)] + suffix

        return normalized

    @staticmethod
    def extract_legal_entity_type(name: str) -> str | None:
        """
        Extract legal entity type from company name.

        Args:
            name: Company name

        Returns:
            Entity type or None
        """
        for suffix in EntityNormalizer.LEGAL_SUFFIXES:
            if suffix.replace(".", "") in name.replace(".", ""):
                return suffix.replace(".", "")

        return None


class TextNormalizer:
    """General text normalization utilities."""

    @staticmethod
    def clean_whitespace(text: str) -> str:
        """Remove extra whitespace and normalize line breaks."""
        # Replace multiple spaces with single space
        text = re.sub(r" +", " ", text)

        # Replace multiple newlines with double newline
        text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

        return text.strip()

    @staticmethod
    def normalize_section_numbers(text: str) -> str:
        """Normalize section numbering format."""
        # Ensure consistent format for section numbers
        # 1.1 -> 1.1
        # 1. -> 1.0
        # etc.
        return text  # Placeholder for more complex logic
