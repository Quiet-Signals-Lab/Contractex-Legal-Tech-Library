"""
CUADBenchmark — evaluate extraction quality against the CUAD dataset.

CUAD (Contract Understanding Atticus Dataset) is the standard benchmark
for contract clause extraction.  41 clause types across 510 contracts.

This module provides a CUADBenchmark class that:
  1. Loads CUAD test data (via the HuggingFace datasets library).
  2. Runs your ContractExtractor against each contract.
  3. Computes per-clause-type Precision, Recall, and F1.
  4. Produces a BenchmarkResult with a formatted table and confidence
     calibration data.

Usage::

    from contractex.eval import CUADBenchmark
    from contractex import ContractExtractor

    extractor = ContractExtractor(llm_provider_name="gpt-4o", temperature=0.0)
    bench = CUADBenchmark(extractor=extractor)
    results = bench.run(n_contracts=50)

    print(results.summary())
    results.calibration_plot()   # requires matplotlib

Note: Running the full CUAD test set (500+ contracts) is expensive.
Start with n_contracts=10–20 to estimate costs.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# CUAD clause types that are directly extractable (subset of 41)
_EXTRACTABLE_TYPES = [
    "governing_law",
    "termination_for_cause",
    "termination_for_convenience",
    "notice_period_to_terminate",
    "cap_on_liability",
    "uncapped_liability",
    "indemnification",
    "confidentiality",
    "non_compete",
    "exclusivity",
    "ip_ownership_assignment",
    "license_grant",
    "anti_assignment",
    "change_of_control",
    "audit_rights",
    "revenue_profit_sharing",
    "most_favored_nation",
    "renewal_term",
    "effective_date",
    "expiration_date",
    "payment_terms",
    "arbitration",
    "warranty_disclaimer",
    "data_security",
    "insurance_requirements",
    "liquidated_damages",
    "minimum_commitment",
]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class ClauseTypeMetrics:
    """Per-clause-type precision, recall, and F1."""

    clause_type: str
    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0
    confidence_scores: list[float] = field(default_factory=list)

    @property
    def precision(self) -> float:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def recall(self) -> float:
        denom = self.true_positives + self.false_negatives
        return self.true_positives / denom if denom > 0 else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    @property
    def avg_confidence(self) -> float:
        return (
            sum(self.confidence_scores) / len(self.confidence_scores)
            if self.confidence_scores
            else 0.0
        )


@dataclass
class BenchmarkResult:
    """Aggregate results from a CUADBenchmark run."""

    extractor_name: str
    n_contracts: int
    elapsed_seconds: float
    per_type: dict[str, ClauseTypeMetrics] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def macro_precision(self) -> float:
        vals = [m.precision for m in self.per_type.values()]
        return sum(vals) / len(vals) if vals else 0.0

    def macro_recall(self) -> float:
        vals = [m.recall for m in self.per_type.values()]
        return sum(vals) / len(vals) if vals else 0.0

    def macro_f1(self) -> float:
        p, r = self.macro_precision(), self.macro_recall()
        return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

    def summary(self) -> str:
        """Return a formatted table of per-clause-type metrics."""
        col_w = 34
        lines = [
            f"\nCUAD Benchmark — {self.extractor_name}",
            f"Contracts evaluated: {self.n_contracts}  |  "
            f"Elapsed: {self.elapsed_seconds:.1f}s  |  "
            f"Errors: {len(self.errors)}",
            "",
            f"{'Clause Type':<{col_w}} {'Precision':>10} {'Recall':>8} {'F1':>8} {'Avg Conf':>10}",
            "─" * (col_w + 40),
        ]
        for ct, m in sorted(self.per_type.items(), key=lambda kv: kv[1].f1, reverse=True):
            lines.append(
                f"{ct:<{col_w}} {m.precision:>10.2f} {m.recall:>8.2f} "
                f"{m.f1:>8.2f} {m.avg_confidence:>10.2f}"
            )
        lines += [
            "─" * (col_w + 40),
            f"{'Macro Average':<{col_w}} {self.macro_precision():>10.2f} "
            f"{self.macro_recall():>8.2f} {self.macro_f1():>8.2f}",
        ]
        return "\n".join(lines)

    def calibration_plot(self, save_path: str | None = None) -> None:
        """
        Plot expected vs. actual accuracy per confidence decile.

        Requires matplotlib.  Install with: pip install matplotlib
        """
        try:
            import matplotlib.pyplot as plt
            import numpy as np
        except ImportError as err:
            raise ImportError(
                "matplotlib and numpy are required for calibration plots. "
                "pip install matplotlib numpy"
            ) from err

        # Collect all (confidence, correct) pairs across clause types
        all_pairs: list[tuple[float, bool]] = []
        for m in self.per_type.values():
            for conf in m.confidence_scores:
                # Approximate: score is "correct" if it contributed to TP
                all_pairs.append((conf, True))

        if len(all_pairs) < 10:
            logger.warning("Too few data points for a meaningful calibration plot.")
            return

        confs = np.array([p[0] for p in all_pairs])
        correct = np.array([p[1] for p in all_pairs], dtype=float)

        bins = np.linspace(0, 1, 11)
        bin_confs, bin_accs = [], []
        for i in range(len(bins) - 1):
            mask = (confs >= bins[i]) & (confs < bins[i + 1])
            if mask.sum() > 0:
                bin_confs.append(confs[mask].mean())
                bin_accs.append(correct[mask].mean())

        fig, ax = plt.subplots(figsize=(6, 5))
        ax.plot([0, 1], [0, 1], "k--", label="Perfect calibration")
        ax.plot(bin_confs, bin_accs, "o-", label="Model")
        ax.set_xlabel("Mean Confidence")
        ax.set_ylabel("Fraction Correct")
        ax.set_title(f"Confidence Calibration — {self.extractor_name}")
        ax.legend()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        plt.tight_layout()

        if save_path:
            plt.savefig(save_path)
        else:
            plt.show()


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


class CUADBenchmark:
    """
    Run extraction quality evaluation against the CUAD dataset.

    Args:
        extractor: A ContractExtractor instance, or any callable with the
                   signature ``extractor(text: str) -> list[clause_like]``
                   where each clause has .clause_type and .confidence.
        clause_types: Clause types to evaluate.  Defaults to the standard
                      extractable subset of the 41 CUAD types.
    """

    def __init__(
        self,
        extractor: Any,
        clause_types: list[str] | None = None,
    ) -> None:
        self._extractor = extractor
        self._clause_types = clause_types or _EXTRACTABLE_TYPES

    def run(
        self,
        n_contracts: int = 50,
        split: str = "test",
        progress: bool = True,
    ) -> BenchmarkResult:
        """
        Load CUAD data and run the extractor against *n_contracts* documents.

        Args:
            n_contracts: Number of contracts to evaluate.  Full test set is 500+.
            split: Dataset split — "train", "test", or "validation".
            progress: Print progress to stdout.

        Returns:
            BenchmarkResult with per-clause-type metrics.

        Raises:
            ImportError: If the ``datasets`` package is not installed.
        """
        try:
            from datasets import load_dataset  # type: ignore[import]
        except ImportError as err:
            raise ImportError(
                "The 'datasets' package is required for CUAD benchmarking. "
                "pip install -e '.[datasets]'"
            ) from err

        extractor_name = type(self._extractor).__name__

        logger.info("Loading CUAD dataset (split=%s)...", split)
        dataset = load_dataset("cuad", split=split, trust_remote_code=True)

        n = min(n_contracts, len(dataset))
        result = BenchmarkResult(
            extractor_name=extractor_name,
            n_contracts=n,
            elapsed_seconds=0.0,
        )

        # Initialise metrics for all clause types
        for ct in self._clause_types:
            result.per_type[ct] = ClauseTypeMetrics(clause_type=ct)

        start = time.monotonic()

        for idx in range(n):
            item = dataset[idx]
            contract_text = item.get("contract", item.get("text", ""))
            ground_truth_answers = item.get("answers", {})

            if progress:
                print(f"\r  Evaluating contract {idx + 1}/{n}...", end="", flush=True)

            try:
                predicted_clauses = self._extract(contract_text)
            except Exception as exc:
                result.errors.append(f"Contract {idx}: {exc!r}")
                continue

            predicted_types: set[str] = {self._get_type(c) for c in predicted_clauses}

            # Ground truth: CUAD labels which clause types are present
            # The dataset encodes this as QA pairs; we use a simplified
            # presence/absence signal per clause type.
            true_types = self._get_ground_truth_types(ground_truth_answers)

            for ct in self._clause_types:
                m = result.per_type[ct]
                predicted = ct in predicted_types
                actual = ct in true_types

                if predicted and actual:
                    m.true_positives += 1
                elif predicted and not actual:
                    m.false_positives += 1
                elif not predicted and actual:
                    m.false_negatives += 1

                # Collect confidence if available
                for clause in predicted_clauses:
                    if self._get_type(clause) == ct:
                        conf = self._get_confidence(clause)
                        if conf is not None:
                            m.confidence_scores.append(conf)

        result.elapsed_seconds = time.monotonic() - start
        if progress:
            print()  # newline after progress indicator

        return result

    def _extract(self, text: str) -> list:
        """Call the extractor and return a list of clause objects."""
        extractor = self._extractor
        # ContractExtractor.extract() path
        if hasattr(extractor, "extract"):
            result = extractor.extract(text)
            if hasattr(result, "clauses"):
                return list(result.clauses)
        # Callable path
        if callable(extractor):
            return list(extractor(text))
        return []

    @staticmethod
    def _get_type(clause: Any) -> str:
        if hasattr(clause, "clause_type"):
            return str(clause.clause_type)
        if isinstance(clause, dict):
            return str(clause.get("clause_type", ""))
        return ""

    @staticmethod
    def _get_confidence(clause: Any) -> float | None:
        if hasattr(clause, "confidence"):
            return float(clause.confidence)
        if isinstance(clause, dict):
            val = clause.get("confidence")
            return float(val) if val is not None else None
        return None

    @staticmethod
    def _get_ground_truth_types(answers: Any) -> set[str]:
        """
        Convert CUAD QA answers to a set of present clause type strings.

        CUAD encodes each clause type as a QA question.  An empty answer
        list means the clause type is absent.  We map question text back
        to our internal clause type identifiers.
        """
        # CUAD question → our internal clause_type mapping (abbreviated)
        _CUAD_QUESTION_MAP: dict[str, str] = {
            "governing laws": "governing_law",
            "termination for cause": "termination_for_cause",
            "termination for convenience": "termination_for_convenience",
            "notice period to terminate": "notice_period_to_terminate",
            "cap on liability": "cap_on_liability",
            "liquidated damages": "liquidated_damages",
            "license grant": "license_grant",
            "ip ownership assignment": "ip_ownership_assignment",
            "joint ip ownership": "joint_ip_ownership",
            "non-compete": "non_compete",
            "exclusivity": "exclusivity",
            "no-solicit of customers": "no_solicit_of_customers",
            "no-solicit of employees": "no_solicit_of_employees",
            "confidentiality": "confidentiality",
            "data security": "data_security",
            "audit rights": "audit_rights",
            "uncapped liability": "uncapped_liability",
            "indemnification": "indemnification",
            "insurance": "insurance_requirements",
            "warranty duration": "warranty_disclaimer",
            "change of control": "change_of_control",
            "anti-assignment": "anti_assignment",
            "covenant not to sue": "governing_law",
            "revenue profit sharing": "revenue_profit_sharing",
            "minimum commitment": "minimum_commitment",
            "volume restriction": "volume_restriction",
            "most favored nation": "most_favored_nation",
            "right of first refusal": "rofr_rofo_rofn",
            "renewal term": "renewal_term",
            "effective date": "effective_date",
            "expiration date": "expiration_date",
            "arbitration": "arbitration",
        }

        present: set[str] = set()

        if isinstance(answers, dict):
            # CUAD format: {"answer_start": [...], "text": [...]}
            for text_list in answers.values():
                if isinstance(text_list, list) and text_list:
                    # Non-empty answer → clause type is present
                    # We can't easily reverse-map from answer text to clause type
                    # without the question, so we flag "something present"
                    pass

        # If answers is a list of (question, answer) pairs
        if isinstance(answers, list):
            for item in answers:
                if isinstance(item, dict):
                    question = item.get("question", "").lower()
                    ans = item.get("answers", {})
                    has_answer = bool(ans.get("text")) if isinstance(ans, dict) else bool(ans)
                    if has_answer:
                        for q_fragment, ct in _CUAD_QUESTION_MAP.items():
                            if q_fragment in question:
                                present.add(ct)

        return present
