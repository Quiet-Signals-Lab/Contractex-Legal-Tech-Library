"""
Validators for confidence scoring and data validation.
"""

from typing import List, Tuple
from contractex.core.models import Contract, Clause, Party, FinancialTerm


class ConfidenceValidator:
    """Validator for confidence scoring of extractions."""
    
    def __init__(self, threshold: float = 0.7):
        """
        Initialize confidence validator.
        
        Args:
            threshold: Minimum acceptable confidence score
        """
        self.threshold = threshold
    
    def validate_contract(self, contract: Contract) -> Tuple[bool, List[str]]:
        """
        Validate all extractions in a contract meet confidence threshold.
        
        Args:
            contract: Contract to validate
        
        Returns:
            Tuple of (is_valid, list of warnings)
        """
        warnings = []
        
        # Check clauses
        for i, clause in enumerate(contract.clauses):
            if clause.confidence < self.threshold:
                warnings.append(
                    f"Clause {i+1} ({clause.clause_type}) has low confidence: {clause.confidence:.2f}"
                )
        
        # Check parties
        for party in contract.parties:
            if party.confidence < self.threshold:
                warnings.append(
                    f"Party '{party.name}' has low confidence: {party.confidence:.2f}"
                )
        
        # Check financial terms
        for term in contract.financial_terms:
            if term.confidence < self.threshold:
                warnings.append(
                    f"Financial term '{term.term_type}' has low confidence: {term.confidence:.2f}"
                )
        
        is_valid = len(warnings) == 0
        return is_valid, warnings


class DataValidator:
    """Validator for data consistency and completeness."""
    
    def validate_contract(self, contract: Contract) -> Tuple[bool, List[str]]:
        """
        Validate contract data for consistency and completeness.
        
        Args:
            contract: Contract to validate
        
        Returns:
            Tuple of (is_valid, list of errors)
        """
        errors = []
        
        # Check required fields
        if not contract.parties:
            errors.append("Contract must have at least one party")
        
        # Validate dates
        if contract.effective_date and contract.expiration_date:
            if contract.expiration_date < contract.effective_date:
                errors.append("Expiration date cannot be before effective date")
        
        # Validate currency codes
        for term in contract.financial_terms:
            if term.currency and len(term.currency) != 3:
                errors.append(f"Invalid currency code: {term.currency}")
        
        is_valid = len(errors) == 0
        return is_valid, errors
