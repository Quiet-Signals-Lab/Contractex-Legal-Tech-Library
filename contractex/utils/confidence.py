"""Confidence scoring utilities."""

from typing import List
from contractex.core.models import Contract, Clause


def calculate_overall_confidence(contract: Contract) -> float:
    """
    Calculate overall confidence score for a contract extraction.
    
    Args:
        contract: Contract to score
    
    Returns:
        Overall confidence score (0.0-1.0)
    """
    scores = []
    
    # Clause confidences
    if contract.clauses:
        clause_scores = [c.confidence for c in contract.clauses if c.confidence > 0]
        if clause_scores:
            scores.append(sum(clause_scores) / len(clause_scores))
    
    # Party confidences
    if contract.parties:
        party_scores = [p.confidence for p in contract.parties if p.confidence > 0]
        if party_scores:
            scores.append(sum(party_scores) / len(party_scores))
    
    # Financial term confidences
    if contract.financial_terms:
        financial_scores = [ft.confidence for ft in contract.financial_terms if ft.confidence > 0]
        if financial_scores:
            scores.append(sum(financial_scores) / len(financial_scores))
    
    # Risk confidences
    if contract.risks:
        risk_scores = [r.confidence for r in contract.risks if r.confidence > 0]
        if risk_scores:
            scores.append(sum(risk_scores) / len(risk_scores))
    
    # Overall average
    if scores:
        return round(sum(scores) / len(scores), 3)
    else:
        return 0.0


def get_low_confidence_items(
    contract: Contract,
    threshold: float = 0.7
) -> List[str]:
    """
    Get list of items with confidence below threshold.
    
    Args:
        contract: Contract to check
        threshold: Confidence threshold
    
    Returns:
        List of warnings about low-confidence items
    """
    warnings = []
    
    for clause in contract.clauses:
        if clause.confidence < threshold:
            warnings.append(
                f"Low confidence clause: {clause.clause_type} ({clause.confidence:.2f})"
            )
    
    for party in contract.parties:
        if party.confidence < threshold:
            warnings.append(
                f"Low confidence party: {party.name} ({party.confidence:.2f})"
            )
    
    for term in contract.financial_terms:
        if term.confidence < threshold:
            warnings.append(
                f"Low confidence financial term: {term.term_type} ({term.confidence:.2f})"
            )
    
    return warnings


def adjust_confidence_score(
    base_score: float,
    factors: dict
) -> float:
    """
    Adjust confidence score based on various factors.
    
    Args:
        base_score: Initial confidence score
        factors: Dictionary of adjustment factors
    
    Returns:
        Adjusted confidence score
    """
    score = base_score
    
    # Apply adjustments
    if 'multiple_sources' in factors and factors['multiple_sources']:
        score *= 1.1  # Boost if confirmed by multiple sources
    
    if 'ambiguous_language' in factors and factors['ambiguous_language']:
        score *= 0.9  # Reduce if language is ambiguous
    
    if 'ocr_extraction' in factors and factors['ocr_extraction']:
        score *= 0.85  # Reduce for OCR (less reliable)
    
    if 'manual_verification' in factors and factors['manual_verification']:
        score *= 1.2  # Boost if manually verified
    
    # Clamp to [0, 1]
    return max(0.0, min(1.0, score))
