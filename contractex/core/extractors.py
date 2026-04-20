"""
Contract extractor - main orchestration logic for extracting contract data.
"""

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

from contractex.chunking.base import ChunkingStrategy
from contractex.core.extraction_schemas import (
    LLMClauseResult,
    LLMClausesResponse,
    LLMContractInfoResponse,
    LLMFinancialResponse,
    LLMFinancialResult,
    LLMFullExtractionResponse,
    LLMPartyResult,
)
from contractex.core.models import (
    Clause,
    Contract,
    ContractMetadata,
    ContractType,
    FinancialTerm,
    Party,
    PartyRole,
)
from contractex.exceptions import ExtractionError
from contractex.llm.base import LLMProvider
from contractex.loaders.base import DocumentLoader
from contractex.prompts.clause_extraction import CLAUSE_EXTRACTION_PROMPT, CONTRACT_INFO_PROMPT
from contractex.prompts.financial_extraction import FINANCIAL_EXTRACTION_PROMPT
from contractex.utils.normalizers import CurrencyNormalizer, DateNormalizer, EntityNormalizer

logger = logging.getLogger(__name__)

# Similarity threshold above which two clause texts are considered duplicates
_CLAUSE_DEDUP_RATIO = 0.90

# Maximum characters from the opening section used for contract-info extraction
# (~3 K tokens for most tokenisers)
_INFO_EXTRACTION_CHARS = 12_000


class ContractExtractor:
    """
    Main extraction orchestrator that coordinates document loading, chunking,
    LLM-based extraction, and result assembly.
    """

    def __init__(
        self,
        llm_provider: Optional[LLMProvider] = None,
        llm_provider_name: Optional[str] = None,
        document_loader: Optional[DocumentLoader] = None,
        chunking_strategy: Optional[ChunkingStrategy] = None,
        confidence_threshold: float = 0.7,
        parallel_processing: bool = True,
    ):
        """
        Initialize the contract extractor.

        Args:
            llm_provider: Custom LLM provider instance
            llm_provider_name: Name of provider to use ("gpt-4o", "claude-3.5-sonnet")
            document_loader: Custom document loader
            chunking_strategy: Custom chunking strategy
            confidence_threshold: Minimum confidence score for extractions
            parallel_processing: Whether to process chunks in parallel
        """
        self.confidence_threshold = confidence_threshold
        self.parallel_processing = parallel_processing

        # Initialize LLM provider
        if llm_provider:
            self.llm_provider = llm_provider
        elif llm_provider_name:
            self.llm_provider = self._create_provider(llm_provider_name)
        else:
            # Default to GPT-4o
            self.llm_provider = self._create_provider("gpt-4o")

        # Initialize document loader
        if document_loader:
            self.document_loader = document_loader
        else:
            from contractex.loaders import AutoLoader

            self.document_loader = AutoLoader()

        # Initialize chunking strategy
        if chunking_strategy:
            self.chunking_strategy = chunking_strategy
        else:
            from contractex.chunking import ClauseAwareChunker

            self.chunking_strategy = ClauseAwareChunker()

    def estimate_extraction_cost(self, document_path: str) -> dict[str, Any]:
        """
        Estimate the API cost of extracting a document without running extraction.

        Loads and chunks the document, then uses the configured LLM provider's
        cost model to estimate the total token usage and USD cost across all
        extraction phases.

        Args:
            document_path: Path to the contract document.

        Returns:
            Dict with keys:
              - ``estimated_cost``   (float) total estimated USD
              - ``estimated_tokens`` (int)   total estimated input tokens
              - ``num_chunks``       (int)   number of chunks the document produces
              - ``llm_provider``     (str)   provider class name
              - ``llm_model``        (str)   model identifier
              - ``breakdown``        (dict)  per-phase cost/token estimates

        Example::

            extractor = ContractExtractor(llm_provider_name="gpt-4o")
            estimate = extractor.estimate_extraction_cost("contract.pdf")
            print(f"Estimated cost: ${estimate['estimated_cost']:.4f}")
        """
        text = self.document_loader.load(document_path)
        chunks = self.chunking_strategy.chunk(text)

        # Phase 1: contract info — first 2 chunks capped at _INFO_EXTRACTION_CHARS
        info_text = "\n\n".join(chunks[:2])[:_INFO_EXTRACTION_CHARS]
        info_tokens = self.llm_provider.count_tokens(info_text)
        info_cost = self.llm_provider.estimate_cost(info_text)

        # Phase 2: clause + financial extraction — one pass per chunk
        chunk_tokens = sum(self.llm_provider.count_tokens(c) for c in chunks)
        chunk_cost = sum(self.llm_provider.estimate_cost(c) for c in chunks)

        # Phase 3: risk analysis — first 20 K chars of full text
        risk_text = text[:20_000]
        risk_tokens = self.llm_provider.count_tokens(risk_text)
        risk_cost = self.llm_provider.estimate_cost(risk_text)

        total_tokens = info_tokens + chunk_tokens + risk_tokens
        total_cost = info_cost + chunk_cost + risk_cost

        return {
            "estimated_cost": round(total_cost, 4),
            "estimated_tokens": total_tokens,
            "num_chunks": len(chunks),
            "llm_provider": self.llm_provider.__class__.__name__,
            "llm_model": getattr(self.llm_provider, "model", "unknown"),
            "breakdown": {
                "contract_info": {
                    "tokens": info_tokens,
                    "cost": round(info_cost, 4),
                },
                "clause_extraction": {
                    "tokens": chunk_tokens,
                    "cost": round(chunk_cost, 4),
                },
                "risk_analysis": {
                    "tokens": risk_tokens,
                    "cost": round(risk_cost, 4),
                },
            },
        }

    def _create_provider(self, name: str) -> LLMProvider:
        """Create an LLM provider by name."""
        name_lower = name.lower()

        if "gpt" in name_lower or "openai" in name_lower:
            from contractex.llm import OpenAIProvider

            model = name if name.startswith("gpt-") else "gpt-4o"
            return OpenAIProvider(model=model)

        elif "claude" in name_lower or "anthropic" in name_lower:
            from contractex.llm import AnthropicProvider

            model = name if name.startswith("claude-") else "claude-3-5-sonnet-20241022"
            return AnthropicProvider(model=model)

        else:
            # Treat as a local Ollama model name (llama, mistral, phi, qwen, etc.)
            from contractex.llm import LocalProvider

            return LocalProvider(model=name)

    def extract(
        self,
        document_path: str,
        contract_type: Optional[ContractType] = None,
        analyze_risks: bool = True,
        extract_financial: bool = True,
        known_parties: Optional[list[str]] = None,
    ) -> Contract:
        """
        Extract all data from a contract document.

        Args:
            document_path: Path to the contract document
            contract_type: Optional contract type hint
            analyze_risks: Whether to perform risk analysis
            extract_financial: Whether to extract financial terms
            known_parties: Optional list of known party names (hints)

        Returns:
            Contract object with all extracted data

        Raises:
            ExtractionError: If extraction fails
        """
        start_time = time.monotonic()

        try:
            # Load document
            text = self.document_loader.load(document_path)

            # Gather file metadata
            doc_path = Path(document_path)
            file_metadata: dict[str, Any] = {
                "filename": doc_path.name,
                "file_type": doc_path.suffix.lstrip("."),
                "llm_provider": self.llm_provider.__class__.__name__,
                "llm_model": getattr(self.llm_provider, "model", None),
            }

            # Chunk document
            chunks = self.chunking_strategy.chunk(text)
            logger.info(
                "Chunked '%s' into %d chunk(s) for extraction",
                doc_path.name,
                len(chunks),
            )

            # Extract structured data using LLM
            contract_data = self._extract_from_chunks(
                chunks,
                contract_type=contract_type,
                known_parties=known_parties,
                extract_financial=extract_financial,
            )

            # Merge file metadata into extraction metadata
            extraction_meta: dict[str, Any] = contract_data.pop("_metadata", {})
            extraction_meta.update(file_metadata)

            # Attach full text
            contract_data["full_text"] = text

            # Build ContractMetadata
            processing_time = time.monotonic() - start_time
            contract_metadata = ContractMetadata(  # type: ignore[call-arg]
                filename=extraction_meta.get("filename"),
                file_type=extraction_meta.get("file_type"),
                llm_provider=extraction_meta.get("llm_provider"),
                llm_model=extraction_meta.get("llm_model"),
                processing_time_seconds=round(processing_time, 2),
                token_usage=extraction_meta.get("token_usage"),
                warnings=extraction_meta.get("warnings", []),
            )
            contract_data["metadata"] = contract_metadata

            # Create Contract object
            contract = Contract(**contract_data)

            # Perform risk analysis if requested
            if analyze_risks:
                from contractex.core.analyzers import RiskAnalyzer

                analyzer = RiskAnalyzer(llm_provider=self.llm_provider)
                contract.risks = analyzer.analyze(contract)

            # Attach confidence warnings
            self._validate_confidence(contract)

            logger.info(
                "Extraction complete: %d parties, %d clauses, %d financial terms, "
                "%d risks in %.1fs",
                len(contract.parties),
                len(contract.clauses),
                len(contract.financial_terms),
                len(contract.risks),
                processing_time,
            )

            return contract

        except ExtractionError:
            raise
        except Exception as e:
            raise ExtractionError(f"Failed to extract contract: {str(e)}") from e

    # ------------------------------------------------------------------
    # Core extraction logic
    # ------------------------------------------------------------------

    def _extract_from_chunks(
        self,
        chunks: list[str],
        contract_type: Optional[ContractType] = None,
        known_parties: Optional[list[str]] = None,
        extract_financial: bool = True,
    ) -> dict[str, Any]:
        """
        Extract structured contract data from a list of text chunks.

        Strategy:
          - Phase 1: Contract info + parties from the opening section.
          - Phase 2a (1 chunk): Full extraction in one combined LLM call.
          - Phase 2b (N chunks): Parallel per-chunk clause + financial extraction.
          - Phase 3: Deduplicate and convert to public models.

        Returns:
            Dict matching Contract model field names plus '_metadata' for
            extraction provenance (token_usage, warnings).
        """
        warnings: list[str] = []
        total_tokens = 0

        # ------------------------------------------------------------------
        # Phase 1: Contract info + parties from preamble (first 1-2 chunks)
        # ------------------------------------------------------------------
        info_text = "\n\n".join(chunks[:2])[:_INFO_EXTRACTION_CHARS]
        contract_info = self._extract_contract_info(
            info_text,
            contract_type_hint=contract_type,
            known_parties=known_parties,
        )
        total_tokens += self.llm_provider.count_tokens(info_text)

        # ------------------------------------------------------------------
        # Phase 2: Clause (and optionally financial) extraction per chunk
        # ------------------------------------------------------------------
        if len(chunks) == 1:
            raw_clauses, raw_financial = self._extract_single_chunk(
                chunks[0], extract_financial=extract_financial
            )
            total_tokens += self.llm_provider.count_tokens(chunks[0])
        else:
            raw_clauses, raw_financial, chunk_warnings = self._extract_multi_chunk(
                chunks, extract_financial=extract_financial
            )
            warnings.extend(chunk_warnings)
            for c in chunks:
                total_tokens += self.llm_provider.count_tokens(c)

        # ------------------------------------------------------------------
        # Phase 3: Dedup + convert to public models
        # ------------------------------------------------------------------
        parties = self._build_parties(contract_info.parties)
        clauses = self._build_clauses(self._deduplicate_clauses(raw_clauses))
        financial_terms = (
            self._build_financial_terms(self._deduplicate_financial_terms(raw_financial))
            if extract_financial
            else []
        )

        resolved_contract_type = self._resolve_contract_type(
            contract_info.contract_type, contract_type
        )
        effective_date = DateNormalizer.normalize(contract_info.effective_date or "")
        expiration_date = DateNormalizer.normalize(contract_info.expiration_date or "")
        signature_date = DateNormalizer.normalize(contract_info.signature_date or "")

        return {
            "contract_type": resolved_contract_type,
            "title": contract_info.title,
            "effective_date": effective_date,
            "expiration_date": expiration_date,
            "signature_date": signature_date,
            "governing_law": contract_info.governing_law,
            "parties": parties,
            "clauses": clauses,
            "financial_terms": financial_terms,
            "_metadata": {
                "token_usage": {
                    "input_tokens": total_tokens,
                    "output_tokens": 0,  # per-call output tracking not exposed by base interface
                    "total_tokens": total_tokens,
                },
                "warnings": warnings,
            },
        }

    # ------------------------------------------------------------------
    # LLM call helpers
    # ------------------------------------------------------------------

    def _extract_contract_info(
        self,
        text: str,
        contract_type_hint: Optional[ContractType] = None,
        known_parties: Optional[list[str]] = None,
    ) -> LLMContractInfoResponse:
        """Extract contract metadata and parties from the opening section."""
        hint_lines: list[str] = []
        if contract_type_hint:
            hint_lines.append(f"Hint: This is likely a {contract_type_hint.value} agreement.")
        if known_parties:
            hint_lines.append(
                f"Known parties (may be referenced by short names): {', '.join(known_parties)}"
            )
        hint = ("\n\n" + "\n".join(hint_lines)) if hint_lines else ""

        prompt = CONTRACT_INFO_PROMPT.format(contract_text=text + hint)
        try:
            result = self.llm_provider.extract_structured(prompt, LLMContractInfoResponse)
            return result  # type: ignore[return-value]
        except Exception as e:
            logger.warning("Contract info extraction failed: %s — returning empty info", e)
            return LLMContractInfoResponse()  # type: ignore[call-arg]

    def _extract_single_chunk(
        self,
        text: str,
        extract_financial: bool = True,
    ) -> tuple[list[LLMClauseResult], list[LLMFinancialResult]]:
        """
        Extract clauses and financial terms from a single chunk.

        Tries a combined LLMFullExtractionResponse call first; falls back to
        two separate calls if the combined schema proves too complex for the model.
        """
        if extract_financial:
            combined_prompt = (
                CLAUSE_EXTRACTION_PROMPT.format(contract_text=text)
                + "\n\nAlso extract all financial terms "
                "(fees, payments, penalties, deposits, royalties, etc.).\n"
            )
            try:
                result = self.llm_provider.extract_structured(
                    combined_prompt, LLMFullExtractionResponse
                )
                full = result  # type: ignore[assignment]
                return full.clauses, full.financial_terms  # type: ignore[attr-defined]
            except Exception as e:
                logger.debug(
                    "Combined single-chunk extraction failed (%s) — falling back to separate calls",
                    e,
                )

        clauses = self._extract_clauses_from_text(text)
        financial: list[LLMFinancialResult] = []
        if extract_financial:
            financial = self._extract_financial_from_text(text)
        return clauses, financial

    def _extract_multi_chunk(
        self,
        chunks: list[str],
        extract_financial: bool = True,
    ) -> tuple[list[LLMClauseResult], list[LLMFinancialResult], list[str]]:
        """Extract clauses and financial terms from multiple chunks, optionally in parallel."""
        all_clauses: list[LLMClauseResult] = []
        all_financial: list[LLMFinancialResult] = []
        warnings: list[str] = []

        if self.parallel_processing and len(chunks) > 1:
            max_workers = min(4, len(chunks))
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(self._extract_chunk, chunk, extract_financial): idx
                    for idx, chunk in enumerate(chunks)
                }
                for future in as_completed(futures):
                    idx = futures[future]
                    try:
                        chunk_clauses, chunk_financial = future.result()
                        all_clauses.extend(chunk_clauses)
                        all_financial.extend(chunk_financial)
                    except Exception as e:
                        msg = f"Chunk {idx} extraction failed: {e}"
                        logger.warning(msg)
                        warnings.append(msg)
        else:
            for idx, chunk in enumerate(chunks):
                try:
                    chunk_clauses, chunk_financial = self._extract_chunk(
                        chunk, extract_financial
                    )
                    all_clauses.extend(chunk_clauses)
                    all_financial.extend(chunk_financial)
                except Exception as e:
                    msg = f"Chunk {idx} extraction failed: {e}"
                    logger.warning(msg)
                    warnings.append(msg)

        return all_clauses, all_financial, warnings

    def _extract_chunk(
        self,
        text: str,
        extract_financial: bool = True,
    ) -> tuple[list[LLMClauseResult], list[LLMFinancialResult]]:
        """Extract clauses and financial terms from one chunk (multi-chunk path)."""
        clauses = self._extract_clauses_from_text(text)
        financial: list[LLMFinancialResult] = []
        if extract_financial:
            financial = self._extract_financial_from_text(text)
        return clauses, financial

    def _extract_clauses_from_text(self, text: str) -> list[LLMClauseResult]:
        """Call the LLM to extract clauses from a text chunk."""
        try:
            prompt = CLAUSE_EXTRACTION_PROMPT.format(contract_text=text)
            result = self.llm_provider.extract_structured(prompt, LLMClausesResponse)
            return result.clauses  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning("Clause extraction from chunk failed: %s", e)
            return []

    def _extract_financial_from_text(self, text: str) -> list[LLMFinancialResult]:
        """Call the LLM to extract financial terms from a text chunk."""
        try:
            prompt = FINANCIAL_EXTRACTION_PROMPT.format(contract_text=text)
            result = self.llm_provider.extract_structured(prompt, LLMFinancialResponse)
            return result.financial_terms  # type: ignore[attr-defined]
        except Exception as e:
            logger.warning("Financial extraction from chunk failed: %s", e)
            return []

    # ------------------------------------------------------------------
    # Deduplication helpers
    # ------------------------------------------------------------------

    def _deduplicate_clauses(
        self, clauses: list[LLMClauseResult]
    ) -> list[LLMClauseResult]:
        """
        Remove near-duplicate clauses produced by chunk overlap.

        Priority:
          1. Containment: if A's text is fully contained in B's, keep B (more complete).
          2. Similarity: if SequenceMatcher ratio >= 0.90, keep the longer / higher-confidence entry.
        """
        if len(clauses) <= 1:
            return clauses

        kept: list[LLMClauseResult] = []
        for candidate in clauses:
            is_dup = False
            c_text = candidate.text.strip()
            for i, existing in enumerate(kept):
                e_text = existing.text.strip()

                # Containment checks (O(n) string ops, fast)
                if c_text in e_text:
                    is_dup = True
                    break
                if e_text in c_text:
                    kept[i] = candidate  # candidate is more complete
                    is_dup = True
                    break

                # Similarity check (slower, only if neither contains the other)
                ratio = SequenceMatcher(None, c_text, e_text).ratio()
                if ratio >= _CLAUSE_DEDUP_RATIO:
                    if len(c_text) > len(e_text) or (
                        len(c_text) == len(e_text)
                        and candidate.confidence > existing.confidence
                    ):
                        kept[i] = candidate
                    is_dup = True
                    break

            if not is_dup:
                kept.append(candidate)

        logger.debug(
            "Clause dedup: %d raw → %d unique (removed %d duplicates)",
            len(clauses),
            len(kept),
            len(clauses) - len(kept),
        )
        return kept

    def _deduplicate_financial_terms(
        self, terms: list[LLMFinancialResult]
    ) -> list[LLMFinancialResult]:
        """
        Remove duplicate financial terms across chunks.

        Dedup key: (term_type, amount, currency).  Keeps the entry with the
        highest confidence when duplicates exist.
        """
        if len(terms) <= 1:
            return terms

        seen: dict[tuple[str, str, str], LLMFinancialResult] = {}
        for term in terms:
            key = (
                term.term_type.lower().strip(),
                (term.amount or "").strip(),
                term.currency.upper(),
            )
            if key not in seen or term.confidence > seen[key].confidence:
                seen[key] = term
        return list(seen.values())

    # ------------------------------------------------------------------
    # Model conversion helpers
    # ------------------------------------------------------------------

    def _build_parties(self, llm_parties: list[LLMPartyResult]) -> list[Party]:
        """Convert LLM party results to public Party models, deduplicating by normalised name."""
        seen: dict[str, Party] = {}
        for p in llm_parties:
            if not p.name:
                continue
            normalised = EntityNormalizer.normalize_company_name(p.name)
            key = normalised.lower()

            role: Optional[PartyRole] = None
            if p.role:
                try:
                    role = PartyRole(p.role.lower())
                except ValueError:
                    logger.debug("Unknown party role '%s' — defaulting to None", p.role)

            party = Party(  # type: ignore[call-arg]
                name=normalised,
                role=role,
                entity_type=p.entity_type,
                jurisdiction=p.jurisdiction,
                address=p.address,
                confidence=p.confidence,
            )

            if key not in seen or party.confidence > seen[key].confidence:
                seen[key] = party

        return list(seen.values())

    def _build_clauses(self, llm_clauses: list[LLMClauseResult]) -> list[Clause]:
        """Convert deduplicated LLM clause results to public Clause models."""
        result: list[Clause] = []
        for c in llm_clauses:
            if not c.text or not c.clause_type:
                continue
            if c.confidence < self.confidence_threshold:
                logger.debug(
                    "Skipping low-confidence clause ('%s', conf=%.2f < threshold=%.2f)",
                    c.clause_type,
                    c.confidence,
                    self.confidence_threshold,
                )
                continue
            result.append(
                Clause(  # type: ignore[call-arg]
                    clause_type=c.clause_type,
                    text=c.text.strip(),
                    section_number=c.section_number,
                    confidence=c.confidence,
                )
            )
        return result

    def _build_financial_terms(
        self, llm_terms: list[LLMFinancialResult]
    ) -> list[FinancialTerm]:
        """Convert deduplicated LLM financial results to public FinancialTerm models."""
        result: list[FinancialTerm] = []
        for t in llm_terms:
            if not t.term_type:
                continue

            amount: Optional[Decimal] = None
            if t.amount:
                parsed = CurrencyNormalizer.extract_amount(t.amount)
                if parsed is not None:
                    amount = parsed
                else:
                    try:
                        amount = Decimal(t.amount.replace(",", ""))
                    except InvalidOperation:
                        logger.debug("Could not parse amount string '%s'", t.amount)

            due_date = DateNormalizer.normalize(t.due_date or "")

            result.append(
                FinancialTerm(  # type: ignore[call-arg]
                    term_type=t.term_type,
                    amount=amount,
                    currency=t.currency.upper(),
                    frequency=t.frequency,
                    due_date=due_date,
                    description=t.description,
                    conditions=t.conditions,
                    confidence=t.confidence,
                )
            )
        return result

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _resolve_contract_type(
        self,
        llm_type: Optional[str],
        hint: Optional[ContractType],
    ) -> Optional[ContractType]:
        """Map the LLM-returned type string to a ContractType enum value."""
        if hint:
            return hint
        if llm_type:
            try:
                return ContractType(llm_type.lower())
            except ValueError:
                logger.debug("LLM returned unknown contract type '%s'", llm_type)
        return None

    def _validate_confidence(self, contract: Contract) -> None:
        """
        Attach warnings for items below the confidence threshold.

        Low-confidence items are kept in the Contract so the caller can
        decide whether to filter them; they are never silently dropped here.
        """
        low: list[str] = []
        for clause in contract.clauses:
            if clause.confidence < self.confidence_threshold:
                low.append(f"Clause '{clause.clause_type}' (conf={clause.confidence:.2f})")
        for party in contract.parties:
            if party.confidence < self.confidence_threshold:
                low.append(f"Party '{party.name}' (conf={party.confidence:.2f})")

        if low:
            contract.metadata.warnings.append(
                f"Items below confidence threshold ({self.confidence_threshold}): "
                + "; ".join(low)
            )

    # ------------------------------------------------------------------
    # Async / batch entry points
    # ------------------------------------------------------------------

    async def extract_async(self, document_path: str, **kwargs: Any) -> Contract:
        """
        Async version of extract — runs the synchronous extractor in a thread pool.

        Args:
            document_path: Path to the contract document
            **kwargs: Additional arguments passed to extract()
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: self.extract(document_path, **kwargs)
        )

    def extract_batch(
        self,
        document_paths: list[str],
        max_workers: int = 4,
        **kwargs: Any,
    ) -> list[Contract]:
        """
        Process multiple contracts in parallel.

        Args:
            document_paths: List of document paths to process
            max_workers: Maximum number of parallel workers
            **kwargs: Additional arguments passed to extract()

        Returns:
            List of successfully extracted Contract objects (failed paths are skipped).
        """
        results: list[Optional[Contract]] = [None] * len(document_paths)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self.extract, path, **kwargs): idx
                for idx, path in enumerate(document_paths)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result()
                except Exception as e:
                    logger.error("Error processing '%s': %s", document_paths[idx], e)

        return [c for c in results if c is not None]
