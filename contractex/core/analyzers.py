"""
Risk analyzer for detecting potential risks and issues in contracts.
"""

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from contractex.core.models import Clause, Contract, RiskFlag, RiskSeverity

if TYPE_CHECKING:
    from contractex.llm.base import LLMProvider

logger = logging.getLogger(__name__)

# Maximum characters of full text to send to the LLM for risk analysis (~5 K tokens)
_RISK_TEXT_CHARS = 20_000

# Valid severity strings returned by the LLM
_VALID_SEVERITIES = {s.value for s in RiskSeverity}


class RiskAnalyzer:
    """
    Analyzer for detecting risks in contracts using rule-based and LLM approaches.

    Rule-based analysis runs against a configurable playbook and works offline.
    LLM-based analysis identifies subtle risks that keyword rules miss; it
    requires an LLMProvider to be passed at construction time.
    """

    def __init__(
        self,
        playbook_path: Optional[str] = None,
        severity_thresholds: Optional[dict[str, float]] = None,
        use_llm: bool = True,
        llm_provider: Optional["LLMProvider"] = None,
    ):
        """
        Initialize the risk analyzer.

        Args:
            playbook_path: Path to custom risk playbook JSON
            severity_thresholds: Custom severity level thresholds
            use_llm: Whether to use LLM for risk analysis (requires llm_provider)
            llm_provider: LLM provider instance for LLM-based risk detection
        """
        self.playbook = self._load_playbook(playbook_path)
        self.severity_thresholds = severity_thresholds or {
            "critical": 0.9,
            "high": 0.7,
            "medium": 0.5,
            "low": 0.3,
        }
        self.use_llm = use_llm
        self.llm_provider = llm_provider

    def _load_playbook(self, playbook_path: Optional[str]) -> dict[str, Any]:
        """Load risk detection playbook."""
        if playbook_path and Path(playbook_path).exists():
            with open(playbook_path) as f:
                result: dict[str, Any] = json.load(f)
                return result

        # Default playbook with common risks
        return {
            "unlimited_liability": {
                "keywords": ["unlimited liability", "no limit on liability"],
                "severity": "critical",
                "description": "Contract contains unlimited liability exposure",
                "recommendation": "Negotiate a liability cap",
            },
            "auto_renewal": {
                "keywords": ["automatically renew", "auto-renew", "automatic renewal"],
                "severity": "medium",
                "description": "Contract auto-renews without explicit consent",
                "recommendation": "Add termination notice provision",
            },
            "non_compete": {
                "keywords": ["non-compete", "not compete", "refrain from competing"],
                "severity": "high",
                "description": "Contains non-compete clause",
                "recommendation": "Review scope and duration for reasonableness",
            },
            "unilateral_changes": {
                "keywords": ["may modify", "right to change", "unilateral modification"],
                "severity": "high",
                "description": "Allows unilateral contract modifications",
                "recommendation": "Require mutual consent for changes",
            },
        }

    def analyze(self, contract: Contract) -> list[RiskFlag]:
        """
        Analyze a contract for risks.

        Args:
            contract: Contract to analyze

        Returns:
            List of identified risk flags ordered by severity (critical first)
        """
        risks: list[RiskFlag] = []

        # Rule-based risk detection (always runs, no LLM required)
        risks.extend(self._rule_based_analysis(contract))

        # LLM-based risk detection (only when a provider is configured)
        if self.use_llm and self.llm_provider is not None:
            llm_risks = self._llm_based_analysis(contract)
            # Dedup against rule-based findings: same risk_type + same clause_reference = skip
            existing_keys = {(r.risk_type, r.clause_reference) for r in risks}
            for risk in llm_risks:
                if (risk.risk_type, risk.clause_reference) not in existing_keys:
                    risks.append(risk)
                    existing_keys.add((risk.risk_type, risk.clause_reference))

        # Sort by severity
        severity_order = {
            RiskSeverity.CRITICAL: 0,
            RiskSeverity.HIGH: 1,
            RiskSeverity.MEDIUM: 2,
            RiskSeverity.LOW: 3,
            RiskSeverity.INFO: 4,
        }
        risks.sort(key=lambda r: severity_order[r.severity])

        return risks

    def _rule_based_analysis(self, contract: Contract) -> list[RiskFlag]:
        """Perform rule-based risk detection using the playbook."""
        risks: list[RiskFlag] = []

        for clause in contract.clauses:
            for risk_type, risk_config in self.playbook.items():
                keywords = risk_config.get("keywords", [])
                text_lower = clause.text.lower()

                if any(keyword.lower() in text_lower for keyword in keywords):
                    risk = RiskFlag(  # type: ignore[call-arg]
                        risk_type=risk_type,
                        severity=RiskSeverity(risk_config["severity"]),
                        description=risk_config["description"],
                        clause_reference=clause.section_number,
                        clause_text=clause.text[:200] + ("..." if len(clause.text) > 200 else ""),
                        recommendation=risk_config.get("recommendation"),
                        confidence=0.8,
                    )
                    risks.append(risk)

        return risks

    def _llm_based_analysis(self, contract: Contract) -> list[RiskFlag]:
        """
        Perform LLM-based risk detection for subtle risks that keyword rules miss.

        Uses the contract's full text (up to _RISK_TEXT_CHARS characters) so that
        contextual risks — e.g. a liability cap that is unreasonably low given the
        contract value — can be identified.
        """
        if self.llm_provider is None:
            return []

        from contractex.core.extraction_schemas import LLMRiskResponse
        from contractex.prompts.risk_analysis import RISK_ANALYSIS_PROMPT

        text = (contract.full_text or "").strip()
        if not text:
            # Fall back to concatenating all clause texts
            text = "\n\n".join(c.text for c in contract.clauses)

        if not text:
            logger.debug("No text available for LLM risk analysis")
            return []

        text = text[:_RISK_TEXT_CHARS]
        prompt = RISK_ANALYSIS_PROMPT.format(contract_text=text)

        try:
            result = self.llm_provider.extract_structured(prompt, LLMRiskResponse)
            llm_response = result  # type: ignore[assignment]
        except Exception as e:
            logger.warning("LLM-based risk analysis failed: %s — skipping", e)
            return []

        risks: list[RiskFlag] = []
        for item in llm_response.risks:  # type: ignore[attr-defined]
            # Validate and normalise severity
            severity_str = (item.severity or "medium").lower()
            if severity_str not in _VALID_SEVERITIES:
                logger.debug(
                    "LLM returned unknown severity '%s' — defaulting to 'medium'", severity_str
                )
                severity_str = "medium"

            # Truncate clause_text to keep RiskFlag payload compact
            clause_text = item.clause_text
            if clause_text and len(clause_text) > 200:
                clause_text = clause_text[:200] + "..."

            risk = RiskFlag(  # type: ignore[call-arg]
                risk_type=item.risk_type,
                severity=RiskSeverity(severity_str),
                description=item.description,
                clause_reference=item.clause_reference,
                clause_text=clause_text,
                recommendation=item.recommendation,
                impact=item.impact,
                confidence=item.confidence,
            )
            risks.append(risk)

        logger.debug("LLM risk analysis found %d risks", len(risks))
        return risks

    def analyze_clause(self, clause: Clause) -> list[RiskFlag]:
        """
        Analyze a single clause for risks.

        Args:
            clause: Clause to analyze

        Returns:
            List of risks in this clause
        """
        temp_contract = Contract(clauses=[clause])  # type: ignore[call-arg]
        return self.analyze(temp_contract)
