"""
Contract extractor - main orchestration logic for extracting contract data.
"""

from typing import Optional, List, Dict, Any
from pathlib import Path

from contractex.core.models import Contract, ContractType
from contractex.llm.base import LLMProvider
from contractex.loaders.base import DocumentLoader
from contractex.chunking.base import ChunkingStrategy
from contractex.exceptions import ExtractionError


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
        
        elif "llama" in name_lower or "local" in name_lower:
            from contractex.llm import LocalProvider
            return LocalProvider(model=name)
        
        else:
            raise ValueError(f"Unknown LLM provider: {name}")
    
    def extract(
        self,
        document_path: str,
        contract_type: Optional[ContractType] = None,
        analyze_risks: bool = True,
        extract_financial: bool = True,
        known_parties: Optional[List[str]] = None,
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
        try:
            # Load document
            text = self.document_loader.load(document_path)
            
            # Get metadata
            doc_path = Path(document_path)
            metadata = {
                "filename": doc_path.name,
                "file_type": doc_path.suffix[1:],
                "llm_provider": self.llm_provider.__class__.__name__,
                "llm_model": getattr(self.llm_provider, 'model', None),
            }
            
            # Chunk document
            chunks = self.chunking_strategy.chunk(text)
            
            # Extract structured data using LLM
            contract_data = self._extract_from_chunks(
                chunks,
                contract_type=contract_type,
                known_parties=known_parties,
            )
            
            # Add metadata
            contract_data["metadata"] = metadata
            contract_data["full_text"] = text
            
            # Create Contract object
            contract = Contract(**contract_data)
            
            # Perform risk analysis if requested
            if analyze_risks:
                from contractex.core.analyzers import RiskAnalyzer
                analyzer = RiskAnalyzer()
                contract.risks = analyzer.analyze(contract)
            
            # Validate confidence threshold
            self._validate_confidence(contract)
            
            return contract
            
        except Exception as e:
            raise ExtractionError(f"Failed to extract contract: {str(e)}") from e
    
    def _extract_from_chunks(
        self,
        chunks: List[str],
        contract_type: Optional[ContractType] = None,
        known_parties: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Extract structured data from document chunks using LLM.
        
        Args:
            chunks: List of document text chunks
            contract_type: Optional contract type hint
            known_parties: Optional known party names
        
        Returns:
            Dictionary of extracted contract data
        """
        # This is a placeholder - actual implementation would:
        # 1. Use prompts from contractex.prompts
        # 2. Call LLM provider for each extraction task
        # 3. Merge results from multiple chunks
        # 4. Return structured data
        
        # For now, return minimal structure
        return {
            "contract_type": contract_type or ContractType.UNKNOWN,
            "parties": [],
            "clauses": [],
            "financial_terms": [],
        }
    
    def _validate_confidence(self, contract: Contract) -> None:
        """
        Validate that extractions meet confidence threshold.
        
        Args:
            contract: Contract to validate
        
        Raises:
            ConfidenceThresholdError: If any extraction is below threshold
        """
        from contractex.exceptions import ConfidenceThresholdError
        
        low_confidence_items = []
        
        for clause in contract.clauses:
            if clause.confidence < self.confidence_threshold:
                low_confidence_items.append(f"Clause: {clause.clause_type} ({clause.confidence:.2f})")
        
        for party in contract.parties:
            if party.confidence < self.confidence_threshold:
                low_confidence_items.append(f"Party: {party.name} ({party.confidence:.2f})")
        
        if low_confidence_items:
            warnings = "\n".join(low_confidence_items)
            contract.metadata.warnings.append(
                f"Some items below confidence threshold ({self.confidence_threshold}):\n{warnings}"
            )
    
    async def extract_async(self, document_path: str, **kwargs) -> Contract:
        """
        Async version of extract for better performance.
        
        Args:
            document_path: Path to the contract document
            **kwargs: Additional arguments passed to extract()
        
        Returns:
            Contract object with all extracted data
        """
        # Placeholder for async implementation
        # Would use async LLM calls and parallel chunk processing
        return self.extract(document_path, **kwargs)
    
    def extract_batch(
        self,
        document_paths: List[str],
        max_workers: int = 4,
        **kwargs
    ) -> List[Contract]:
        """
        Process multiple contracts in parallel.
        
        Args:
            document_paths: List of document paths to process
            max_workers: Maximum number of parallel workers
            **kwargs: Additional arguments passed to extract()
        
        Returns:
            List of Contract objects
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        contracts = []
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {
                executor.submit(self.extract, path, **kwargs): path
                for path in document_paths
            }
            
            for future in as_completed(future_to_path):
                path = future_to_path[future]
                try:
                    contract = future.result()
                    contracts.append(contract)
                except Exception as e:
                    print(f"Error processing {path}: {e}")
        
        return contracts
