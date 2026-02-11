"""
Risk analyzer for detecting potential risks and issues in contracts.
"""

import json
from pathlib import Path
from typing import Any, Optional

from contractex.core.models import Clause, Contract, RiskFlag, RiskSeverity


class RiskAnalyzer:
    """
    Analyzer for detecting risks in contracts using rule-based and LLM approaches.
    """

    def __init__(
        self,
        playbook_path: Optional[str] = None,
        severity_thresholds: Optional[dict[str, float]] = None,
        use_llm: bool = True,
    ):
        """
        Initialize the risk analyzer.

        Args:
            playbook_path: Path to custom risk playbook JSON
            severity_thresholds: Custom severity level thresholds
            use_llm: Whether to use LLM for risk analysis
        """
        self.playbook = self._load_playbook(playbook_path)
        self.severity_thresholds = severity_thresholds or {
            "critical": 0.9,
            "high": 0.7,
            "medium": 0.5,
            "low": 0.3,
        }
        self.use_llm = use_llm

    def _load_playbook(self, playbook_path: Optional[str]) -> dict[str, Any]:
        """Load risk detection playbook."""
        if playbook_path and Path(playbook_path).exists():
            with open(playbook_path) as f:
                return json.load(f)

        # Default playbook with common risks
        return {
            "unlimited_liability": {
                "keywords": ["unlimited liability", "no limit on liability"],
                "severity": "critical",
                "description": "Contract contains unlimited liability exposure",
                "recommendation": "Negotiate a liability cap"
            },
            "auto_renewal": {
                "keywords": ["automatically renew", "auto-renew", "automatic renewal"],
                "severity": "medium",
                "description": "Contract auto-renews without explicit consent",
                "recommendation": "Add termination notice provision"
            },
            "non_compete": {
                "keywords": ["non-compete", "not compete", "refrain from competing"],
                "severity": "high",
                "description": "Contains non-compete clause",
                "recommendation": "Review scope and duration for reasonableness"
            },
            "unilateral_changes": {
                "keywords": ["may modify", "right to change", "unilateral modification"],
                "severity": "high",
                "description": "Allows unilateral contract modifications",
                "recommendation": "Require mutual consent for changes"
            },
        }

    def analyze(self, contract: Contract) -> list[RiskFlag]:
        """
        Analyze a contract for risks.

        Args:
            contract: Contract to analyze

        Returns:
            List of identified risk flags
        """
        risks = []

        # Rule-based risk detection
        risks.extend(self._rule_based_analysis(contract))

        # LLM-based risk detection (if enabled)
        if self.use_llm:
            risks.extend(self._llm_based_analysis(contract))

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
        """
        Perform rule-based risk detection using playbook.

        Args:
            contract: Contract to analyze

        Returns:
            List of detected risks
        """
        risks = []

        for clause in contract.clauses:
            for risk_type, risk_config in self.playbook.items():
                # Check if any keywords match
                keywords = risk_config.get("keywords", [])
                text_lower = clause.text.lower()

                if any(keyword.lower() in text_lower for keyword in keywords):
                    risk = RiskFlag(  # type: ignore[call-arg]
                        risk_type=risk_type,
                        severity=RiskSeverity(risk_config["severity"]),
                        description=risk_config["description"],
                        clause_reference=clause.section_number,
                        clause_text=clause.text[:200] + "...",  # First 200 chars
                        recommendation=risk_config.get("recommendation"),
                        confidence=0.8,  # Rule-based has lower confidence
                    )
                    risks.append(risk)

        return risks

    def _llm_based_analysis(self, contract: Contract) -> list[RiskFlag]:
        """
        Perform LLM-based risk detection for complex risks.

        Args:
            contract: Contract to analyze

        Returns:
            List of detected risks
        """
        # Placeholder for LLM-based analysis
        # Would use prompts to identify subtle risks that rules miss
        return []

    def analyze_clause(self, clause: Clause) -> list[RiskFlag]:
        """
        Analyze a single clause for risks.

        Args:
            clause: Clause to analyze

        Returns:
            List of risks in this clause
        """
        # Create a minimal contract object for analysis
        temp_contract = Contract(clauses=[clause])  # type: ignore[call-arg]
        return self.analyze(temp_contract)
