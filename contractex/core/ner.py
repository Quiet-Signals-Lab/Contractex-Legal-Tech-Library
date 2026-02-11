"""
Named Entity Recognition for legal documents.

Provides spaCy-based entity extraction with support for legal-specific models
like Blackstone for extracting parties, legal entities, and other contract elements.
"""

import logging
from typing import Any

from contractex.exceptions import ContractExError

logger = logging.getLogger(__name__)


class NERError(ContractExError):
    """Raised when NER operations fail."""

    pass


class LegalNER:
    """
    Named Entity Recognition for legal documents using spaCy.

    Supports both general spaCy models and legal-specific models like Blackstone
    for enhanced extraction of legal entities, parties, and contract elements.
    """

    # Legal entity types recognized by Blackstone
    LEGAL_ENTITY_TYPES = {
        "CASENAME",  # Names of legal cases
        "CITATION",  # Legal citations
        "INSTRUMENT",  # Legal instruments (contracts, statutes, etc.)
        "PROVISION",  # Specific legal provisions
        "COURT",  # Court names
        "JUDGE",  # Judge names
    }

    # Entity types for identifying parties
    PARTY_ENTITY_TYPES = {"ORG", "PERSON", "GPE"}

    def __init__(self, model_name: str = "en_core_web_sm"):
        """
        Initialize the Legal NER model.

        Args:
            model_name: Name of the spaCy model to load
                       - "en_blackstone_proto": Legal-specific Blackstone model
                       - "en_core_web_sm": General English model (default)
                       - Any other installed spaCy model

        Raises:
            NERError: If spaCy is not installed or model cannot be loaded
        """
        try:
            import spacy
        except ImportError as e:
            raise NERError(
                "spaCy not installed. Install with: pip install 'contractex[spacy]' "
                "or pip install spacy"
            ) from e

        try:
            self.nlp = spacy.load(model_name)
            logger.info(f"Loaded spaCy model: {model_name}")
        except OSError:
            if model_name == "en_blackstone_proto":
                logger.warning(
                    "Blackstone model not found. Install with: "
                    "pip install https://blackstone-model.s3-eu-west-1.amazonaws.com/"
                    "en_blackstone_proto-0.0.1.tar.gz"
                )
                logger.info("Falling back to en_core_web_sm")
                try:
                    self.nlp = spacy.load("en_core_web_sm")
                except OSError as e:
                    raise NERError(
                        "Default spaCy model not found. Install with: "
                        "python -m spacy download en_core_web_sm"
                    ) from e
            else:
                raise NERError(
                    f"spaCy model '{model_name}' not found. "
                    f"Install with: python -m spacy download {model_name}"
                ) from None

        self.model_name = model_name

    def extract_entities(self, text: str) -> list[dict[str, Any]]:
        """
        Extract named entities from text.

        Args:
            text: Input text

        Returns:
            List of dictionaries containing entity information:
            - text: Entity text
            - label: Entity type/label
            - start: Character start position
            - end: Character end position
        """
        doc = self.nlp(text)
        entities = []

        for ent in doc.ents:
            entities.append(
                {
                    "text": ent.text,
                    "label": ent.label_,
                    "start": ent.start_char,
                    "end": ent.end_char,
                }
            )

        return entities

    def extract_legal_entities(self, text: str) -> dict[str, list[str]]:
        """
        Extract and categorize legal-specific entities.

        When using Blackstone model, recognizes:
        - CASENAME: Names of legal cases
        - CITATION: Legal citations
        - INSTRUMENT: Legal instruments (contracts, statutes, etc.)
        - PROVISION: Specific legal provisions
        - COURT: Court names
        - JUDGE: Judge names

        Args:
            text: Input legal text

        Returns:
            Dictionary with entity types as keys and lists of entity texts as values
        """
        doc = self.nlp(text)
        categorized = {}

        for ent in doc.ents:
            if ent.label_ not in categorized:
                categorized[ent.label_] = []
            categorized[ent.label_].append(ent.text)

        return categorized

    def extract_parties(self, text: str) -> list[str]:
        """
        Extract party names from contract text.

        Identifies organizations, persons, and geopolitical entities that
        may represent contract parties.

        Args:
            text: Contract text

        Returns:
            List of unique party names
        """
        doc = self.nlp(text)
        parties: set[str] = set()

        for ent in doc.ents:
            if ent.label_ in self.PARTY_ENTITY_TYPES:
                parties.add(ent.text)

        return sorted(parties)  # Return sorted for consistency

    def extract_dates(self, text: str) -> list[dict[str, Any]]:
        """
        Extract dates from text.

        Args:
            text: Input text

        Returns:
            List of dictionaries with date information:
            - text: Date text
            - start: Character start position
            - end: Character end position
        """
        doc = self.nlp(text)
        dates = []

        for ent in doc.ents:
            if ent.label_ == "DATE":
                dates.append({"text": ent.text, "start": ent.start_char, "end": ent.end_char})

        return dates

    def extract_monetary_values(self, text: str) -> list[dict[str, Any]]:
        """
        Extract monetary values from text.

        Args:
            text: Input text

        Returns:
            List of dictionaries with monetary value information:
            - text: Monetary value text
            - start: Character start position
            - end: Character end position
        """
        doc = self.nlp(text)
        values = []

        for ent in doc.ents:
            if ent.label_ == "MONEY":
                values.append({"text": ent.text, "start": ent.start_char, "end": ent.end_char})

        return values

    def process_contract(self, text: str) -> dict[str, Any]:
        """
        Comprehensive NER processing of contract text.

        Extracts all entity types, legal entities, parties, dates, and monetary values.

        Args:
            text: Full contract text

        Returns:
            Dictionary containing all extracted information:
            - entities: All entities with positions
            - legal_entities: Categorized legal entities
            - parties: Unique party names
            - dates: Extracted dates
            - monetary_values: Extracted monetary amounts
        """
        return {
            "entities": self.extract_entities(text),
            "legal_entities": self.extract_legal_entities(text),
            "parties": self.extract_parties(text),
            "dates": self.extract_dates(text),
            "monetary_values": self.extract_monetary_values(text),
        }

    def __repr__(self) -> str:
        return f"LegalNER(model='{self.model_name}')"
